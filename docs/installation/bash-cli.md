---
layout: installation
title: Command-line launcher
permalink: /installation/bash-cli/
---

Open TI-Toolbox in your browser from a terminal. Install and start Docker first.

## Requirements

- **Bash:** Docker, Docker Compose and curl. No host Python is needed.
- **Python:** Docker and Python 3.11 or newer.

The scientific tools run inside Docker; you do not need to install SimNIBS separately.

## Launch

Download [loader.py](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/loader.py),
[loader.sh](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/loader.sh), and
[docker-compose.yml](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/docker-compose.yml).
Save all three in the **same folder**, keeping their filenames unchanged. If a link opens as text,
use **Save As** (without adding `.txt`). You do not need the full repository.

Open a terminal in that folder and run **one** launcher:

```bash
python3 loader.py
```

or, on macOS/Linux:

```bash
bash loader.sh
```

Enter your project directory when prompted; TI-Toolbox opens in your browser.
Python needs version 3.11+; Bash needs curl and Docker Compose.

These downloads are the v3 preview. The first launch needs an internet connection to prepare
the launcher and download the toolbox image. To choose a project directly:

```bash
python3 loader.py --project /path/to/project
```

## Existing containers

If a TI-Toolbox container is already running, select it and choose:

- **Recreate (default):** stop and remove the selected container, then start your requested
  project. Any jobs in that container stop; project files are preserved.
- **Attach:** open the existing container with its current project and version.

Press Ctrl-C to cancel without changing anything. Legacy v2 containers cannot attach to
the v3 interface.

## Stop or check a session

Closing the browser **leaves the container running**. To stop it:

```bash
python3 loader.py --project /path/to/project --stop
```

Use `--status` to check the session or `--logs` to see its log:

```bash
python3 loader.py --project /path/to/project --status
python3 loader.py --project /path/to/project --logs
```

The Bash launcher accepts the same options. For all options, run `python3 loader.py --help`
or `bash loader.sh --help`.

## Over SSH

On the remote host, start without opening a browser:

```bash
python3 loader.py --project /path/to/project --no-open
```

Forward the printed port from your computer (8765 in this example):

```bash
ssh -N -L 8765:127.0.0.1:8765 you@remote-host
```

Open the launcher's authenticated URL locally using `127.0.0.1:8765`. Keep its session
token private.

## What is different in a browser

The browser has the same scientific tools, jobs, notebooks and viewer. File exports use
browser downloads, and notifications appear in the app. Choose the project through the
loader; native folder picking, project switching and file-manager integration are available
in the desktop app.

## Troubleshooting

Check that Docker is running. If startup fails, inspect `--logs` and visit the
[troubleshooting guide]({{ site.baseurl }}/installation/troubleshooting/).

<a id="run-the-latest-unreleased-version"></a>
<a id="develop-from-source"></a>
<a id="build-a-development-image"></a>
<a id="advanced-native-without-docker"></a>

Source builds, developer loaders, custom images and automation are covered in
[Development & Testing]({{ site.baseurl }}/wiki/development/).
