---
layout: installation
title: Windows Installation
permalink: /installation/windows/
---

Start with the [quick start]({{ site.baseurl }}/installation/) to choose the desktop app or
command-line launcher. This page covers Windows setup.

## Docker Desktop and WSL2

Install Docker Desktop with its WSL2 backend and an Ubuntu WSL distribution. Start Docker
Desktop, open **Settings → Resources → WSL Integration**, and enable your Ubuntu distribution.
Open Ubuntu and check that `docker version` can reach the engine.

![Docker settings on Windows]({{ site.baseurl }}/assets/imgs/installation/docker_windows.png){:style="max-width: 800px;"}

No VcXsrv or X11 forwarding is required for the toolbox interface.

## Command-line launcher

Run the [command-line launcher]({{ site.baseurl }}/installation/bash-cli/) inside Ubuntu/WSL2.
Bash needs Docker Compose and curl; `loader.py` needs Python 3.11+. Use WSL paths for projects: `C:\Users\YourName\datasets\project-copy` becomes
`/mnt/c/Users/YourName/datasets/project-copy`. The same path is used for the Docker bind mount.

The launcher prints an authenticated URL at `http://127.0.0.1:<port>/auth/session?...`.
Open that URL in your Windows browser; if the browser does not open automatically, pass
`--no-open` and use the printed URL. Do not share its session token.

## Electron on Windows

Use native Windows project paths in the desktop app, such as
`C:\Users\YourName\datasets\project-copy`; do not use WSL paths.

An EXE is the packaged desktop format. Artifact availability is listed on the installation
page. If Docker Desktop was just installed or updated, restart it before launching the app.

## Troubleshooting

If the Ubuntu launcher cannot reach Docker, check WSL Integration and restart Docker Desktop.
For job and application problems, use the
[troubleshooting archive]({{ site.baseurl }}/wiki/troubleshooting/).
