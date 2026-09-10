---
layout: installation
title: Installation
permalink: /installation/
---

TI-Toolbox runs its scientific tools and interface in one Docker image. Open that interface
in the Electron desktop app or your browser. This page owns installation and artifact
availability; [launcher options]({{ site.baseurl }}/installation/bash-cli/) and the platform
pages cover configuration details.

<a id="internal-colleague-testing"></a>

## Artifact availability

The current source ref is `release/3.0.0`; its internal image is
`idossha/ti-toolbox:internal-20260909.1` on Docker Hub. Pull before testing to obtain the
latest internal rebuild. Record the resolved image digest with any bug report because this
internal testing tag may be replaced during the current testing round. No public desktop
installer or stable release is advertised here yet.

## Install from source

### 1. Install Docker and choose a project

Install and start [Docker Desktop](https://www.docker.com/products/docker-desktop/) on macOS
or Windows, or [Docker Engine](https://docs.docker.com/engine/install/) on Linux. For the
Bash launcher, install curl and the Docker Compose plugin; Python is not required. The
Python launcher requires Python 3.11+. Install git for a source checkout. The Electron development app additionally
needs Node 22.12+. SimNIBS, FastSurfer, Python science dependencies, and the viewer are in the
image; no X11 server is needed.

Use a copy of your project when evaluating a new version. Platform setup:
[macOS]({{ site.baseurl }}/installation/macos/) ·
[Windows]({{ site.baseurl }}/installation/windows/) ·
[Linux]({{ site.baseurl }}/installation/linux/).

### 2. Check out the selected source ref

Choose the branch or tag paired with your image. The commands work with a release branch,
a release tag, or `main` after the corresponding change is merged:

```bash
TIT_SOURCE_REF=release/3.0.0
git clone --branch "$TIT_SOURCE_REF" git@github.com:idossha/TI-toolbox.git TI-Toolbox
cd TI-Toolbox
git rev-parse HEAD
```

Record the printed commit for reproducibility. Run the following commands inside this checkout;
its root `loader.py` uses the selected source without installing a different package revision.

### 3. Make the matching image available

Set the image reference supplied with your selected source revision. For the current pairing:

```bash
TIT_IMAGE=idossha/ti-toolbox:internal-20260909.1
docker pull "$TIT_IMAGE"
docker image inspect "$TIT_IMAGE" --format {% raw %}'{{json .RepoTags}}'{% endraw %}
```

For offline testing, load a supplied archive with
`docker load --input /path/to/supplied-image.tar`. Keep the checkout paired with its designated
image; similar version numbers do not guarantee matching code.

### 4. Open the interface

**Browser (default):** from the repository root, choose a project in the terminal:

```bash
python3 loader.py
# or
bash loader.sh
```

Enter your project copy's path, or press Enter to reuse the displayed last project. To skip
the prompt and set the image explicitly, supply arguments:

```bash
python3 loader.py --project /path/to/project-copy --image "$TIT_IMAGE"
```

The launcher asks Recreate (the Enter default) or Attach if a TI-Toolbox container is already running, then opens
its browser interface. Closing the browser leaves the container running; use `--stop` to stop it.
Use `--desktop` for Electron. Overview provides project opening and switching. Closing the
window or choosing Quit stops its container and exits the application.
Desktop mode needs an installed executable selected with `TIT_ELECTRON_EXECUTABLE`, or the
checkout's desktop app built with `npm ci` and `npm run build` in `desktop/`. See the
[command-line reference]({{ site.baseurl }}/installation/bash-cli/) for SSH, logs, and stop.

**Electron from source:** open the desktop welcome screen without building a release installer:

```bash
cd desktop
npm ci
npm run dev
```

Overview shows the full sidebar and a project field with **Browse**. No `.env.dev` or project
selection is required before starting the app. Enter or select your project, then open it;
the app starts Docker's project container after checking for existing sessions.

Use **Switch project** in Overview to enter or select a different directory. Confirming stops
the current container and its jobs before loading the new project's data. Cancelling or an
invalid destination leaves the current project open. Closing Electron stops its container and
exits. Project files and named volumes are preserved.

Rerun `npm run dev` after UI changes. New desktop development containers mount the checkout
and reload Python changes; Attach retains the selected session's existing configuration.
Optional `.env.dev` image/path defaults and browser development with live renderer reload are
covered in [Develop from source]({{ site.baseurl }}/installation/bash-cli/#develop-from-source).

### 5. Verify the project

Confirm that subjects appear, open an existing output in the viewer, and complete a small
simulation or analysis used in your work. Record the source commit, image reference, host OS,
and job ID when reporting a problem. Existing-result guidance lives in the
[scientific corrections record]({{ site.baseurl }}/releases/v3.0.0/#scientific-corrections).

## Desktop installers

The packaged Electron app selects a project folder and manages its Docker container. Use an
installer paired with the same image; [Artifact availability](#artifact-availability) records
what can be obtained. macOS uses a DMG, Windows an EXE, and Linux an AppImage or DEB.
Platform-specific launch notes are on the pages linked above.

## HPC (Apptainer/Singularity)

For clusters where Docker is unavailable, see
[HPC deployment]({{ site.baseurl }}/installation/hpc-apptainer/).

## System requirements

| | Minimum | Recommended |
|---|---|---|
| RAM | 32 GB | 64 GB+ |
| Disk | ~20 GB free for the image and its layers | plus room for your project |
| CPU | 4 cores | 8+ cores |

The image is built for `linux/amd64`. On Apple Silicon Docker Desktop runs it under emulation,
which works but is markedly slower for FEM solves and segmentation.

Host dependency requirements are on the
**[Dependencies]({{ site.baseurl }}/installation/dependencies/)** page; problems and their
fixes are on **[Troubleshooting]({{ site.baseurl }}/installation/troubleshooting/)**.

<br>

## What's in the image

`idossha/ti-toolbox:<version>` is one image containing:

- **SimNIBS 4.6** (`simnibs_python`, `charm`) — head modeling and FEM solves
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

## Platforms

| Platform | Support | Notes |
|----------|---------|-------|
| **Linux x86_64** | Native | Docker Engine |
| **Windows x64** | Native (via WSL2) | Docker Desktop + WSL2 |
| **macOS (Apple Silicon)** | Emulated | The image is `linux/amd64`; Docker Desktop runs it under emulation. Measured FastSurfer runtime under this emulation has not yet been benchmarked — see the [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/) page for the native number and status. |
| **macOS (Intel)** | Native | `linux/amd64`, same architecture as the image |

The image targets `linux/amd64` only; there is no native `arm64` build. On Apple
Silicon and any other non-x86_64 host, Docker Desktop emulates it — expect slower FEM
solves and slower FastSurfer than on native x86_64 hardware.

## Disk size

One image, `idossha/ti-toolbox:<version>` — **final candidate download and disk sizes pending measurement**.
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

## Container engines

| Engine | Support |
|--------|---------|
| **Docker Desktop** (macOS, Windows, Linux) | Supported |
| **Docker Engine** (Linux) | Supported |
| **Colima / OrbStack** | Best-effort — not actively tested |
| **Podman** | Not supported |

## Troubleshooting

For known problems and verified fixes, start with the
[maintained Troubleshooting Archive]({{ site.baseurl }}/wiki/troubleshooting/).
For Docker and launcher setup, see
[installation troubleshooting]({{ site.baseurl }}/installation/troubleshooting/).

## Docker access is a trust boundary

The server authenticates with a bearer token, generated for each new container and passed to the
container as an environment variable. The desktop app and command-line loaders reuse the
selected container's token only after an explicit Attach choice.

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
