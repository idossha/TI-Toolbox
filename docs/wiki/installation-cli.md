---
layout: installation
title: Command-line launcher
permalink: /installation/bash-cli/
---

Start TI-Toolbox from a terminal. The launcher opens the desktop app, or your browser with `--browser`. Install and start Docker first.

## Requirements

- **Bash:** Docker, Docker Compose and curl. No host Python is needed.
- **Python:** Docker and Python 3.11 or newer. On Debian, Ubuntu and WSL, also `python3-venv`: the launcher creates its own environment.

The scientific tools run inside Docker; you do not need to install SimNIBS separately.

## Launch

Download **one launcher** — [loader.py](https://raw.githubusercontent.com/idossha/TI-Toolbox/main/loader.py)
or [loader.sh](https://raw.githubusercontent.com/idossha/TI-Toolbox/main/loader.sh) — plus
[docker-compose.yml](https://raw.githubusercontent.com/idossha/TI-Toolbox/main/docker-compose.yml).
Keep these **two files in the same folder**, with their filenames unchanged. If a link opens as text,
use **Save As** (without adding `.txt`). No repository checkout is needed: regular launches use
the code already inside the image and mount your project data without replacing that code.

Open a terminal in that folder and run **one** launcher:

```bash
python3 loader.py
```

or, on macOS/Linux:

```bash
bash loader.sh
```

The launcher's job is to start the **desktop app**: on first run it downloads the build for your
platform (macOS, or Linux x86_64), verifies its SHA256 against the release's `SHA256SUMS`, caches
it under your user data directory and starts it. On native Windows there is no download: use the
EXE from the [Quick Start]({{ site.baseurl }}/installation/#download), or run the launcher inside
WSL2, where it opens your Windows browser. On Linux arm64 the launcher falls back to the browser.
`--project` is optional for the app — without it the app opens its own project page. `--desktop`
refuses to fall back; `--browser` and `--no-open` use the browser instead and need `--project` (or
`--interactive`, which asks for the directory); `--no-open` prints the session URL only.
Python needs version 3.11+; Bash needs curl and Docker Compose.

`loader.py` refreshes its launcher from GitHub on every start, always from the release it belongs
to (the `v3.1.1` tag for this release, never the development branch), so it needs an internet
connection, except for `--stop`, `--status` and `--logs`. `loader.sh` has no launcher to refresh
(without a `docker-compose.yml` beside it, it downloads its own release's copy); when it cannot
pull the image it warns and uses the cached one. To choose a project directly:

```bash
python3 loader.py --project /path/to/project
```

## Browser mode

The two sections below apply when the launcher opens your browser (`--browser`, `--no-open`, or no
desktop build for your machine). The desktop app asks about an existing container in its own
dialog, and closing the app stops its container.

### Existing containers

If a TI-Toolbox container is already running, select it and choose:

- **Recreate (default):** stop and remove the selected container, then start your requested
  project. Any jobs in that container stop; project files are preserved.
- **Attach:** open the existing container with its current project and version.

Press Ctrl-C to cancel without changing anything. Legacy v2 containers cannot attach to
the v3 interface.

### Stop or check a session

In browser mode, closing the tab **leaves the container running**. To stop it:

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

The browser has the same scientific tools, jobs and notebooks. The Viewer cannot launch TetraVox
from a browser; it offers **Download prepared scene for TetraVox** instead. File exports use
browser downloads, and notifications appear in the app. Choose the project through the
loader; native folder picking, project switching and file-manager integration are available
in the desktop app.

## Troubleshooting

Check that Docker is running. If startup fails, inspect `--logs` and visit the
[troubleshooting guide]({{ site.baseurl }}/wiki/troubleshooting/).

<a id="run-the-latest-unreleased-version"></a>
<a id="develop-from-source"></a>
<a id="build-a-development-image"></a>
<a id="advanced-native-without-docker"></a>

Source builds, developer loaders, custom images and automation are covered in
[Development & Testing]({{ site.baseurl }}/wiki/development/).
