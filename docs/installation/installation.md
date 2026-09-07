---
layout: installation
title: Installation
permalink: /installation/
---

TI-Toolbox ships as a single Docker image. Docker Desktop (macOS/Windows) or Docker Engine
(Linux) is the only thing you install yourself — SimNIBS, FastSurfer, the TI-Toolbox UI and
the built-in viewer are all baked into the image.

There are three ways to run it, and **they all land on the same interface**. The UI is served
by the container; the desktop application is a shell around it, and the command-line launcher
puts the same page in your browser instead of in a window. Pick the row that describes you:

| | You get | You need | Best for |
|---|---|---|---|
| **[1. Desktop app](#option-1-desktop-app)** | An application in your dock | Docker | Everyone. Start here. |
| **[2. Command line](#option-2-command-line-no-electron)** | The UI in a browser tab | Docker, Python 3.11+ | Remote/SSH machines, lab servers, scripted setups |
| **[3. From source](#option-3-run-the-latest-unreleased-version)** | The unreleased code | Docker, Node 22.12+, git | Trying a fix before it ships; contributing |

The first launch downloads `idossha/ti-toolbox:{version}` — **≈ 2.3 GB to download, ≈ 9 GB unpacked on disk**. It is downloaded once and reused by all three options.

<br>

## Option 1: Desktop App

Download the pre-built desktop application for your platform from the
**[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Platform | Download |
|----------|----------|
| **macOS (Apple Silicon)** | `TI-Toolbox-{version}-arm64.dmg` |
| **macOS (Intel)** | `TI-Toolbox-{version}.dmg` |
| **Windows** | `TI-Toolbox.Setup.{version}.exe` |
| **Linux** | `TI-Toolbox-{version}.AppImage` or `ti-toolbox_{version}_amd64.deb` |

Install and launch. The app asks for a **project folder**, then talks to Docker directly over
its Engine API — no Docker CLI and no `docker compose` on your machine — to pull the image,
start the container and load the toolbox in its own window. Nothing else to configure: there
is no X server to install and no separate FreeSurfer license for the core workflow.

The container it starts is named `ti-toolbox-<hash>-tit-1` and stays running after you close
the window, so the next launch attaches in a second or two. Settings → Docker stops it.

Per-platform notes: **[macOS]({{ site.baseurl }}/installation/macos/)** ·
**[Windows]({{ site.baseurl }}/installation/windows/)** ·
**[Linux]({{ site.baseurl }}/installation/linux/)**.

<br>

## Option 2: Command Line (no Electron)

The same UI, in your browser, driven by a small Python launcher. Useful when the desktop app
is not an option: a machine you reach over SSH, a shared lab server, a container host, or a
setup you want to script.

```bash
pip install tit                       # or: pipx install tit
tit launch --project ~/datasets/000
```

`tit launch` checks Docker, pulls the image if it is missing, starts the container, waits for
the server, then prints and opens a URL. Full options, the `loader.py` / `loader.sh` bootstraps and the
advanced "already have SimNIBS on this host" path are on the
**[Command-line launcher]({{ site.baseurl }}/installation/bash-cli/)** page.

The launcher needs only CPython 3.11+ and the `docker` CLI — **not** SimNIBS, numpy or Node.
The toolbox itself lives in the container.

<br>

## Option 3: Run the latest unreleased version

Build the app from a checkout to get changes that have not been released yet. One command
brings up the whole system — container, renderer dev server and the app window, already
connected:

```bash
git clone https://github.com/idossha/TI-Toolbox.git
cd TI-Toolbox/desktop
cp .env.dev.example .env.dev          # edit TIT_DEV_PROJECT_DIR
npm ci
npm run dev
```

Requirements and what to expect on the first run — including building the image, which takes
30–60+ minutes — are on the
**[Command-line launcher]({{ site.baseurl }}/installation/bash-cli/#run-the-latest-unreleased-version)**
page.

<br>

## Option 4: HPC (Apptainer/Singularity)

For high-performance computing clusters where Docker is unavailable. Users build the `.sif`
image from the definition file — see
**[HPC / Apptainer]({{ site.baseurl }}/installation/hpc-apptainer/)**.

<br>

## System requirements

| | Minimum | Recommended |
|---|---|---|
| RAM | 32 GB | 64 GB+ |
| Disk | ~20 GB free for the image and its layers | plus room for your project |
| CPU | 4 cores | 8+ cores |

The image is built for `linux/amd64`. On Apple Silicon Docker Desktop runs it under emulation,
which works but is markedly slower for FEM solves and segmentation.

Detailed per-tool versions are on the
**[Dependencies]({{ site.baseurl }}/installation/dependencies/)** page; problems and their
fixes are on **[Troubleshooting]({{ site.baseurl }}/installation/troubleshooting/)**.

<br>

## What's in the image

`idossha/ti-toolbox:<version>` is one image containing:

- **SimNIBS 4.6** (`simnibs_python`, `charm`, `gmsh`) — head modeling and FEM solves
- **FastSurfer**, `--seg_only` mode, with its checkpoints pre-downloaded — fast cortical/
  subcortical segmentation, replacing FreeSurfer `recon-all` (see [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/))
- **Tetravox Embed** — the in-window 3D/volume viewer (see [Viewer]({{ site.baseurl }}/wiki/visualizers/))
- **The TI-Toolbox UI** — served by the container over HTTP at `/`, rendered inside the
  Electron shell or in your browser; the same bundle either way
- **The `tit` Python package** and a Jupyter kernel, for notebooks and scripts

There is no separate FreeSurfer image and no FreeSurfer license needed for this core
workflow. A FreeSurfer license is only required if you additionally run **QSIPrep/QSIRecon
with anatomically-constrained tractography (ACT)** for diffusion data — QSIPrep/QSIRecon are
pulled as separate images on demand; put the license file where the [Diffusion
Processing]({{ site.baseurl }}/wiki/diffusion-processing/) guide's QSIPrep section says to
mount it (`$FS_LICENSE`, or the default path TI-Toolbox looks for).

## Supported platforms

| Platform | Support | Notes |
|----------|---------|-------|
| **Linux x86_64** | Native | Docker Engine |
| **Windows x64** | Native (via WSL2) | Docker Desktop + WSL2 |
| **macOS (Apple Silicon)** | Emulated | The image is `linux/amd64`; Docker Desktop runs it under emulation. Measured FastSurfer runtime under this emulation has not yet been benchmarked — see the [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/) page for the native number and status. |
| **macOS (Intel)** | Native | `linux/amd64`, same architecture as the image |

The image is published for `linux/amd64` only; there is no native `arm64` build. On Apple
Silicon and any other non-x86_64 host, Docker Desktop emulates it — expect slower FEM
solves and slower FastSurfer than on native x86_64 hardware.

## Disk size

One image, `idossha/ti-toolbox:<version>` — **≈ 2.3 GB to download, ≈ 9 GB unpacked on disk**.
This replaces the previous two-image stack (`idossha/simnibs` plus a separate FreeSurfer
image, together tens of GB); dropping FreeSurfer from the core product (see
[Architecture]({{ site.baseurl }}/wiki/desktop-app/)) accounts for nearly all of the
reduction.

`docker images` can report a different number for the same image on a given machine — that is
Docker's own local disk accounting, not a different image: the column most Docker Desktop
versions print by default is *disk usage*, snapshot layers actually occupying space on that
machine right now, which double-counts base layers shared with any other locally-cached image
built from the same SimNIBS base. `docker system df -v` breaks this into `SHARED SIZE` +
`UNIQUE SIZE`, and `SHARED SIZE` goes away the moment nothing else on that host references
those layers.

## Supported container engines

| Engine | Support |
|--------|---------|
| **Docker Desktop** (macOS, Windows, Linux) | Supported |
| **Docker Engine** (Linux) | Supported |
| **Colima / OrbStack** | Best-effort — not actively tested |
| **Podman** | Not supported |

## Docker access is a trust boundary

The server authenticates with a bearer token, generated fresh per launch and passed to the
container only as an environment variable — nothing writes it to a file on the host. This is
true of all three launch paths: the desktop app, `tit launch` and `npm run dev` each generate
one and read it back out of the container when they re-attach.

That token is readable by anything with access to the Docker socket: {% raw %}`docker inspect
<container> --format '{{range .Config.Env}}{{println .}}{{end}}'`{% endraw %}, `docker exec
<container> env`, or reading `/proc/<pid>/environ` for the container's own process all show it
in plain text. On a single-user machine this changes nothing — Docker socket access is already
root-equivalent there. On a **shared multi-user host** (a lab workstation where several
accounts are conventionally added to the `docker` group for convenience), it does: any other
member of that group can read a running TI-Toolbox session's token and, since the server binds
to `127.0.0.1` and is reachable by every local user on that host, use it to read or run jobs
against that session's project data. Do not add mutually-untrusted accounts to the same
`docker` group on a host anyone runs TI-Toolbox on.

## Optional: AI Assistant Plugin

If you use an AI coding assistant, install the TI-Toolbox plugin so it can answer questions
from the wiki, write correct scripts, and inspect your project folder. In Claude Code:

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```

Codex, Cursor and other MCP clients: see the
**[AI Assistant guide]({{ site.baseurl }}/wiki/ai-assistant/)**.

<br>

⚠️ **Security Notice**: Only run bash scripts and download applications from official sources.
