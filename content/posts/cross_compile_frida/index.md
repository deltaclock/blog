+++
date = "2024-12-10T18:11:41+02:00"
title = "Frida cross compilation"
description = "Insights on compiling Frida for foreign architectures such as armel."
summary = "Insights on compiling Frida for foreign architectures such as armel."
tags = ["Frida"]
+++


During my recent personal research, I came across an embedded device running a custom Linux-based system. One of my goals, when evaluating its security, was to programmatically monitor the system's processes and hook various custom libraries for logging their actions.

# Objective

Through my preceding research, I have identified a target library (`target.so`) that was being referenced by various other ELFs. Some of these processes were already running, while others could be invoked by dynamic events or run periodically at unknown intervals.

Since the function I wanted to hook was pretty simple, one of my early ideas was to just modify `/etc/ld.so.preload` to include my _hook_ shared library in all future processes. This turned out to be problematic as most of the system's partitions were _read-only_, enforced at the hardware level. Of course, this big limitation also prevented me from setting any additional environment variables like `LD_PRELOAD`.

# Enter Frida

The next obvious choice was [Frida](https://frida.re/), an extremely powerful dynamic instrumentation toolkit.
Although maybe a bit overkill for my purpose, _Frida_ would allow me to easily reproduce my results in the future and provide me the ability to create more complex hooks with ease.

At the same time, this was also the point where many major frustrations arose.

## The problems

Even though my target's device CPU supported the hard-float ABI (`armhf`), the system's developers opted to compile all binaries in soft-float ABI (`armel`). This might seem like an obvious point of caution to people more experienced with embedded systems, but personally, apart from maybe size constraints, it doesn't make much sense.

When I first gained a root shell on the device, I checked to see exactly what kind of system I'm dealing with. One of my data points was the CPU model or supported features.

```bash
root@target:/# cat /proc/cpuinfo
processor       : 0
model name      : ARMv7 Processor rev 5 (v7l)
BogoMIPS        : 100.00
Features        : half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt vfpd32 lpae 
CPU implementer : 0x41
CPU architecture: 7
CPU variant     : 0x0
CPU part        : 0xc07
CPU revision    : 5
```

As we can see, the CPU clearly supports `armhf`. As a result, for _simpler_ tools like [dropbear](https://github.com/mkj/dropbear) or [gdbserver](https://sourceware.org/pub/gdb/releases/), choosing a [musl](https://musl.libc.org/)-based cross-compiler with `armhf` support and statically compiling, proved sufficient.

> One such compiler is conveniently provided by Void Linux: https://pkgs.org/search/?q=musleabihf

## Frida Server

Unfortunately, running a _frida server_ on the device wasn't as simple.

During my initial attempts, I thought I could just download the precompiled _frida-server-armhf_ variant from GitHub and proceed with my hooking efforts.
The binary could run on the target, after replacing the interpreter path with the correct `ld` path found on the device.

```sh
patchelf --set-interpreter /lib/ld-linux.so.3 frida-server-16.6.6-linux-armhf
```

The screenshot below depicts the subsequent problems encountered. Despite _frida-server_ successfully starting and being able to communicate with a Frida client, it was <u>unable</u> to actually attach to any processes, throwing the error _«Failed to attach: unable to load library»_.

{{< figure src="images/frida_error.png" alt="Frida attach error." caption="Frida attach error emitted by [loader.c](https://github.com/frida/frida-core/blob/2ebec1addff5e0bc908a7f0a5979dd86452b05b8/src/linux/helpers/loader.c#L150)" >}}

Analyzing Frida's loader, we can see this error message is emitted when _frida-server_ fails to dynamically load the _friga-agent_ shared object.
The root cause of the `libc->dlopen` failure stems from the inability of the dynamic loader (`ld`) to load a hard-float ABI object, as mentioned previously.

{{< codeimporter url="https://raw.githubusercontent.com/frida/frida-core/2ebec1addff5e0bc908a7f0a5979dd86452b05b8/src/linux/helpers/loader.c" type="c" startLine="116" endLine="129" >}}

> Source: https://github.com/frida/frida-core/blob/9594e1a8b81f151f49dedafeca1d85a33654137c/src/linux/helpers/loader.c#L116

# Compiling Frida

While probably other tricks exist, to avoid compiling the whole project, it's safer to assume a compilation will have higher chances of success than anything else.

In order to compile such a project on my _x86-64_ PC, I required a toolchain that:

- Can compile for ARM soft-float ABI, as most cross-toolchains support by default only `armhf`.
- Builds against GNU libc, and especially as close to libc version `2.24` as possible.
- Can be run on an environment modern enough, to support all <cite>Frida building requirements[^1]</cite>, especially Node 18.

[^1]: Building Frida: https://frida.re/docs/building/

For my use case, I discovered two methods that both resulted in a fully capable _frida-server_ running on the embedded device.

## Correct way: Crosstool-NG

The reason I've labeled this as the _correct_ way, stems from the ability of [crosstool-NG](https://crosstool-ng.github.io/docs/introduction/) to build toolchains for almost any kind of system configuration. Despite this, I avoided this method when I was rushing to get something running, due to my unfamiliarity with the project.\
After I achieved my research goals, I revisited the project and took some time to build Frida using it.

Due to Frida requiring Node as a build dependency, I've chosen to run all subsequent compilation steps in a Docker container, using as base the `node:18` image.

### Generating the toolchain

Having installed _crosstool-NG_ in the container, we need to configure our toolchain.

As a safe starting point, I've chosen the `arm-unknown-linux-gnueabi` template. Below, we can see the default configuration of this template, which we will need to tweak to match our needs.

```sh
root@dad2bad6b3a5:/crosstool# ct-ng show-arm-unknown-linux-gnueabi
[G...]   arm-unknown-linux-gnueabi
    Languages       : C,C++
    OS              : linux-6.13
    Binutils        : binutils-2.43.1
    Compiler        : gcc-14.2.0
    Linkers         :
    C library       : glibc-2.41
    Debug tools     : duma-2_5_21 gdb-16.2 ltrace-0.7.3 strace-6.13
    Companion libs  : expat-2.5.0 gettext-0.23.1 gmp-6.3.0 isl-0.26 libelf-0.8.13 libiconv-1.16 mpc-1.3.1 mpfr-4.2.1 ncurses-6.4 zlib-1.3.1 zstd-1.5.6
    Companion tools :
```

In order to tweak this configuration, we first need to load it to our current directory with the command: `ct-ng arm-unknown-linux-gnueabi`.

Then we can start changing its options to our target values with the command: `ct-ng menuconfig`.

{{< figure src="images/crosstool.png" alt="Crosstool-NG menu." caption="Crosstool-NG ncurses menu having selected glibc-2.24" >}}

For my case, I tried to keep things simple, not to risk breaking the toolchain. I only selected glibc version 2.24 and Linux kernel version 4.19, all other important settings like soft-float ABI were already preconfigured from the selected template.

After 10 minutes of compiling, a new directory will be created housing the toolchain libraries and executables.

{{< figure src="images/crosstool_done.png" alt="Newly created toolchain." caption="Newly created toolchain featuring the latest gcc version while linking against glibc-2.24" >}}

### Building the Frida server

Finally, all we have to do is add the toolchain into our `PATH` and follow the instructions from <cite>Frida's building documentation[^1]</cite>.

This can be summed up in 3 steps:

1) Clone https://github.com/frida/frida.git in a folder.
2) Run the `./configure` script specifying the components to enable/disable and the _suffix_ of our cross-compiler under the `--host=` switch.
3) Compile everything into a single binary with `make`.

#### More frustrations

> While I wish I wouldn't have to write this section, it may be useful in case anyone else faces these problems in the future.

Remember earlier, I've chosen for my toolchain the latest version of GCC compiler 14.2. Turns out, with every GCC release greater than version 6, the resulting `frida-server` binary depended on the `libatomic.so` library, which didn't exist on my embedded device.

This library requirement presumably originated from the [openssl](https://github.com/frida/openssl) dependency of Frida. Reading the [code](https://github.com/frida/openssl/blob/ca4781aaf7910b623d3ae21c6a017e7e9ca6936c/include/internal/tsan_assist.h#L51) responsible for adding support for atomic operations, let me to believe that defining the preprocessor variable `__STDC_NO_ATOMICS__` would make _openssl_ fallback to using locks, removing the `libatomic` requirement, albeit making the code somewhat slower.

> The only way I've found to add a preprocessor variable, without patching Frida's build scripts, was to append meson options to the `./configure` script. Environment variables like `CFLAGS` or `CXXFLAGS` weren't picked up.\
> Example: `./configure --switch1 --switch2 -- -Dc_args="-D__STDC_NO_ATOMICS__=1"`

Unfortunately, this wasn't enough; while I could see `__STDC_NO_ATOMICS__` being defined in openssl's compilation command line, the resulting ELF **still** depended on `libatomic`. To overcome this problem, I decided to use GCC version 6, the same GCC version that the `libc` found on my target device was compiled with.

### Crosstool-NG - Dockerfile

The following `Dockerfile` includes all previously described steps for compiling a `frida-server` for my target device.\
Running the command `docker build -o . .` should save a `frida-server` binary in the current directory.

```Dockerfile
FROM node:18 AS builder

# crosstool-ng deps
RUN apt-get update && \
    apt-get install -y gcc g++ gperf bison flex texinfo help2man make libncurses5-dev \
    python3-dev autoconf automake libtool libtool-bin gawk wget bzip2 xz-utils unzip \
    patch libstdc++6 rsync git meson ninja-build

# install crosstool-ng
ARG crosstool_ver=1.27.0

WORKDIR /crosstool

RUN wget https://github.com/crosstool-ng/crosstool-ng/releases/download/crosstool-ng-${crosstool_ver}/crosstool-ng-${crosstool_ver}.tar.xz && \
    tar -xvf crosstool-ng-${crosstool_ver}.tar.xz && \
    cd crosstool-ng-${crosstool_ver} && \
    ./configure --prefix=/ && \
    make && make install


# build the cross-toolchain
WORKDIR /toolchain

COPY <<EOF ./defconfig
CT_CONFIG_VERSION="4"
CT_EXPERIMENTAL=y
CT_ALLOW_BUILD_AS_ROOT=y
CT_ALLOW_BUILD_AS_ROOT_SURE=y
# CT_REMOVE_DOCS is not set
CT_ARCH_ARM=y
CT_ARCH_FLOAT_SW=y
CT_TARGET_VENDOR="frida"
CT_KERNEL_LINUX=y
CT_LINUX_V_4_19=y
CT_BINUTILS_LINKER_LD_GOLD=y
CT_BINUTILS_GOLD_THREADS=y
CT_BINUTILS_LD_WRAPPER=y
CT_BINUTILS_PLUGINS=y
CT_GLIBC_V_2_24=y
CT_GCC_V_6=y
# CT_CC_GCC_SJLJ_EXCEPTIONS is not set
CT_CC_LANG_CXX=y
CT_COMP_LIBS_EXPAT=y
CT_COMP_LIBS_LIBELF=y
EOF

RUN ct-ng defconfig && ct-ng build.24

ENV PATH="${PATH}:/root/x-tools/arm-frida-linux-gnueabi/bin/"

# build frida-server
WORKDIR /build

RUN git clone --depth=1 https://github.com/frida/frida.git && \
    cd frida/ && mkdir build && cd build/ && \
    ../configure --host=arm-frida-linux-gnueabi --without-prebuilds=sdk:host --enable-server \
    --disable-frida-tools --disable-graft-tool --disable-gadget --disable-inject --disable-frida-python && \
    make -j24

# export just frida-server
FROM scratch

COPY --from=builder /build/frida/build/subprojects/frida-core/server/frida-server /
```

## Hacky way: Debian

As mentioned previously, during my research _rush_, I didn't have the time to fully investigate _crosstool-ng_. I needed something that could help me get Frida compiled and running on the device as fast as possible. The idea was to think like the system's developers, meaning the combination of glibc and GCC versions, would probably **not** be something very _exotic_.

A quick search on the awesome website https://pkgs.org, [revealed](https://pkgs.org/search/?q=armel#) that indeed the _biggest_ Linux distributions offered pre-built `armel` compilers; the only problem was their included glibc version.

Taking a look at Debian's package search results for `libc6-armel-cross`, we can see that Debian _buster_ offers glibc version 2.28, close but not exactly my target's 2.24.

{{< figure src="images/debian_pkgs.png" alt="Debian libc6-armel-cross package search." caption="Debian [libc6-armel-cross](https://packages.debian.org/search?keywords=libc6-armel-cross&searchon=names&suite=all&section=all) package search results." >}}

I needed to pick, hopefully, one version before Debian _stretch_. The only reliable source of versioning for such old packages I found to be https://distrowatch.com.

Loading the full package list from distrowatch's page, allowed me to confirm my hypothesis! Debian _stretch_ contained exactly the package I was looking for!

{{< figure src="images/distrowatch.png" alt="Debian's _stretch_ libc6-armel-cross package version from distrowatch." caption="Debian's _stretch_ libc6-armel-cross package version from [distrowatch](https://distrowatch.com/table.php?distribution=debian&pkglist=true&version=9#pkglist)." >}}

### Hacky way - Dockerfile

The only thing left to do now, is to force install such old packages into the much newer Debian _bookworm_ that `node:18` is based upon.

One way to solve this problem, was to download these very old packages (along with their dependencies) from `debian:stretch` and _force install_ them onto the `node:18` container. This is essentially based on the fact that programs built for older glibc versions should be able to run on newer glibc versions, following glibc backward-compatible guarantees.

This forceful installation added the `arm-linux-gnueabi-*` family of tools and libraries in the standard system paths, as if they were installed with `apt`.

The build process remains largely the same as before, with the only minor difference being that a plain `./configure` didn't work for this case. Again, more _openssl_ errors were generated, but these were quickly avoided by using `./releng/deps.py build` before retrying to configure the project.

```Dockerfile
FROM debian:stretch AS stretch

RUN sed -i -re 's/deb.debian.org|security.debian.org/archive.debian.org/g' /etc/apt/sources.list && \
    sed -i -re 's/-updates/-proposed-updates/g' /etc/apt/sources.list

RUN apt-get update && \
    apt-get install -y --download-only g++-arm-linux-gnueabi

FROM node:18 AS builder

RUN apt-get update && \
    apt-get install -y python3 git build-essential

WORKDIR /oldgcc

COPY --from=stretch /var/cache/apt/archives/*.deb ./

RUN dpkg -i --force-all *.deb

WORKDIR /build

RUN git clone --depth=1 https://github.com/frida/frida.git && \
    cd frida/ && mkdir build && cd build/ && \
    ../configure --enable-server --disable-frida-tools --disable-graft-tool --disable-gadget --disable-inject --disable-frida-python --host=arm-linux-gnueabi; \
    ../releng/deps.py build --bundle=sdk --host=arm-linux-gnueabi --exclude v8 && \
    ../configure --enable-server --disable-frida-tools --disable-graft-tool --disable-gadget --disable-inject --disable-frida-python --host=arm-linux-gnueabi && \
    make -j24

FROM scratch

COPY --from=builder /build/frida/build/subprojects/frida-core/server/frida-server /
```

# Conclusions

Frida is a very powerful tool, and it's unfortunate there aren't many available blogs for using it beyond mobile applications.
I hope this article can help people, in similar situations, solve their Frida compilation problems.

> All the build processes and Dockerfiles, have been last tested and confirmed to be working as of March 2025.