import re
import requests
from uuid import uuid4

# from https://fonts.google.com/specimen/JetBrains+Mono
URL = "https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&display=swap"

# https://regex101.com/r/RVNHw1/1
REGEX = re.compile(r"\/\* (\w+(-ext)?) \*\/.+?url\((.+?)\).+?}", re.S)

CSS = requests.get(URL, headers={"User-Agent": "AppleWebKit/ Chrome/135"}).text

for m in REGEX.finditer(CSS):
    if "latin" in m.group(1):
        with requests.get(m.group(3), stream=True) as r:
            r.raise_for_status()
            filename = f"{uuid4()}.woff2"
            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        print(m.group(0).replace(m.group(3), f"/fonts/{filename}"))
        
