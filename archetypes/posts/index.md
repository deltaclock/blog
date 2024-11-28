+++
date = "{{ .Date }}"
draft = true
title = "{{ replace .File.ContentBaseName "_" " " | title }}"
description = "For metadata."
summary = "A small summary."
tags = ["tag"]
+++