---
layout: installation
title: Windows Installation
permalink: /installation/windows/
---

Use the [installation procedure]({{ site.baseurl }}/installation/) for the selected source
ref, matching image, and launch commands. This page explains Windows Docker and path setup.

## Docker Desktop and WSL2

Install Docker Desktop with its WSL2 backend and an Ubuntu WSL distribution. Start Docker
Desktop, open **Settings → Resources → WSL Integration**, and enable your Ubuntu distribution.
Open Ubuntu and check that `docker version` can reach the engine.

![Docker settings on Windows]({{ site.baseurl }}/assets/imgs/installation/docker_windows.png){:style="max-width: 800px;"}

No VcXsrv or X11 forwarding is required for the toolbox interface.

## Browser from a source checkout

Run the shared installation commands inside Ubuntu/WSL2, with Docker Compose, curl and git installed (Python 3.11+ only for `loader.py`)
there. Use WSL paths for projects: `C:\Users\YourName\datasets\project-copy` becomes
`/mnt/c/Users/YourName/datasets/project-copy`. The same path is used for the Docker bind mount.

The launcher prints an authenticated URL at `http://127.0.0.1:<port>/auth/session?...`.
Open that URL in your Windows browser; if the browser does not open automatically, pass
`--no-open` and use the printed URL. Do not share its session token.

## Electron on Windows

The native desktop app talks to Docker Desktop through its Windows named pipe. For Electron
source development, use a Windows checkout with Node 22.12+, git, and native Windows project
paths in `desktop/.env.dev`. Follow the same source-ref and image pairing procedure; do not
mix a WSL project path into the native Windows app configuration.

An EXE is the packaged desktop format. Artifact availability is listed on the installation
page. If Docker Desktop was just installed or updated, restart it before launching the app.

## Troubleshooting

If the Ubuntu launcher cannot reach Docker, check WSL Integration and restart Docker Desktop.
For job and application problems, use the
[troubleshooting archive]({{ site.baseurl }}/wiki/troubleshooting/).
