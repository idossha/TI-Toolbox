---
layout: installation
title: Installation
permalink: /installation/
---

TI-Toolbox ships as a single Docker image. Docker Desktop (macOS/Windows) or Docker Engine
(Linux) is the only thing you install yourself — SimNIBS, FastSurfer, and the TI-Toolbox UI
are all baked into the image and pulled automatically the first time you launch it.

## Option 1: Desktop App

Download the pre-built desktop application for your platform from the **[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Platform | Download |
|----------|----------|
| **macOS (Apple Silicon)** | `TI-Toolbox-{version}-arm64.dmg` |
| **macOS (Intel)** | `TI-Toolbox-{version}.dmg` |
| **Windows** | `TI-Toolbox.Setup.{version}.exe` |
| **Linux** | `TI-Toolbox-{version}.AppImage` or `ti-toolbox_{version}_amd64.deb` |

Download, install, and launch — the app talks to Docker directly over its Engine API (no
Docker CLI, no `docker compose` needed on your machine) to pull the image, start the
container, and open the toolbox UI in its own window. Nothing else to configure: there is no
X server to install and no separate FreeSurfer license to obtain for the core workflow.

<br>

## Option 2: Command Line

**Download the required files:**
- **[loader.py](https://github.com/idossha/TI-toolbox/blob/main/loader.py)** - Main launch script
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)** - Docker configuration

<br>

## Option 3: HPC (Apptainer/Singularity)

For high-performance computing clusters where Docker is unavailable. Users build the `.sif`
image from the definition file. The Apptainer path is unchanged by the Docker-image
streamlining described below.

**[Full HPC Deployment Guide]({{ site.baseurl }}/installation/hpc-apptainer/)**

Quick start:
```bash
# 1. Get the definition file
curl -O https://raw.githubusercontent.com/idossha/TI-toolbox/main/container/blueprint/apptainer.def
curl -O https://raw.githubusercontent.com/idossha/TI-toolbox/main/container/blueprint/apptainer_run.sh
chmod +x apptainer_run.sh

# 2. Build the SIF (30-60 min, requires fakeroot or root)
apptainer build ti-toolbox.sif apptainer.def

# 3. Run interactively
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /data/my_study
```

<br>

## Optional: AI Assistant Plugin

If you use an AI coding assistant, install the TI-Toolbox plugin so it can answer questions from the wiki, write correct scripts, and inspect your project folder. In Claude Code:

```text
/plugin marketplace add idossha/TI-Toolbox
/plugin install ti-toolbox@ti-toolbox
```

Codex, Cursor and other MCP clients: see the **[AI Assistant guide]({{ site.baseurl }}/wiki/ai-assistant/)**.

<br>

---

## What's in the image

`idossha/ti-toolbox:<version>` is one image containing:

- **SimNIBS 4.6** (`simnibs_python`, `charm`, `gmsh`) — head modeling and FEM solves
- **FastSurfer**, `--seg_only` mode, with its checkpoints pre-downloaded — fast cortical/
  subcortical segmentation, replacing FreeSurfer `recon-all` (see [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/))
- **Tetravox Embed** — the in-window 3D/volume viewer (see [Viewer]({{ site.baseurl }}/wiki/visualizers/))
- **The TI-Toolbox UI** — served by the container over HTTP, rendered inside the Electron shell

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
| **macOS (Apple Silicon)** | Emulated | The image is `linux/amd64`; Docker Desktop runs it under Rosetta. Measured FastSurfer runtime under this emulation has not yet been benchmarked — see the [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/) page for the native number and status. |
| **macOS (Intel)** | Native | `linux/amd64`, same architecture as the image |

The image is published for `linux/amd64` only; there is no native `arm64` build. On Apple
Silicon and any other non-x86_64 host, Docker Desktop emulates it — expect slower FEM
solves and slower FastSurfer than on native x86_64 hardware.

## Disk size

One image, `idossha/ti-toolbox:<version>` — **~6.7 GB** of actual content, which is what a
fresh `docker pull` on a clean machine downloads. This replaces the previous two-image stack
(`idossha/simnibs`, ~19 GB pulled / ~6.1 GB of content, plus the separate FreeSurfer image,
~67 GB pulled / ~22 GB of content) — dropping FreeSurfer from the core product (see
[Architecture]({{ site.baseurl }}/wiki/desktop-app/)) is what accounts for nearly all of that
reduction, not compression of the SimNIBS layer itself.

`docker images` can report a larger number than 6.7 GB for this same image on a given
machine — that is not a bloated image, it is Docker's own local disk accounting: the column
most Docker Desktop versions print by default is *disk usage*, snapshot layers actually
occupying space on that machine right now, which double-counts base layers this image shares
with any other locally-cached image built from the same SimNIBS base (`docker system df -v`
breaks this into `SHARED SIZE` + `UNIQUE SIZE`, and `SHARED SIZE` goes away the moment nothing
else on that host still references those layers). {% raw %}`docker image inspect
idossha/ti-toolbox:<version> --format '{{.Size}}'`{% endraw %} always reports the 6.7 GB content
size regardless of what else is cached locally.

## Supported container engines

| Engine | Support |
|--------|---------|
| **Docker Desktop** (macOS, Windows, Linux) | Supported |
| **Docker Engine** (Linux) | Supported |
| **Colima / OrbStack** | Best-effort — not actively tested |
| **Podman** | Not supported |

---

## Docker access is a trust boundary

The desktop app's server authenticates with a bearer token, generated fresh per launch and
passed to the container only as an environment variable — nothing writes it to a file on the
host. That token is readable by anything with access to the Docker socket: {% raw %}`docker
inspect <container> --format '{{range .Config.Env}}{{println .}}{{end}}'`{% endraw %}, `docker
exec <container> env`, or reading `/proc/<pid>/environ` for the container's own process all show
it in plain text. On a single-user machine this changes nothing — Docker socket access is already
root-equivalent there. On a **shared multi-user host** (a lab workstation where several
accounts are conventionally added to the `docker` group for convenience), it does: any other
member of that group can read a running TI-Toolbox session's token and, since the server binds
to `127.0.0.1` and is reachable by every local user on that host, use it to read or run jobs
against that session's project data. Do not add mutually-untrusted accounts to the same
`docker` group on a host anyone runs TI-Toolbox on.

---

## Supported Operating Systems

| Operating System | Support Level | Testing Status | Notes |
|------------------|---------------|----------------|--------|
| **Windows** | ✅ Full Support | ✅ Active Testing | Via WSL2 + Docker Desktop |
| **Linux (Ubuntu)** | ✅ Full Support | ✅ Active Testing | Primary development platform |
| **macOS (Apple Silicon)** | ✅ Full Support | ✅ Active Testing | Runs the `linux/amd64` image under emulation — see "Supported platforms" above |
| **macOS (Intel)** | ✅ Built each release | ⚠️ Not actively tested | Intel `.dmg` is still published |

---

## Prerequisites

**Options 1 & 2 (Desktop / CLI):**
- **Docker**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or [Docker Engine](https://docs.docker.com/engine/install/) (Linux)

That's it — no X server, no separate FreeSurfer license for the core workflow.

**Option 3 (HPC):**
- **Apptainer** 1.1+ (or Singularity 3.8+) — typically provided by your cluster's module system
- **FreeSurfer License**: Free from [FreeSurfer registration](https://surfer.nmr.mgh.harvard.edu/registration.html) — the HPC `.sif` still bundles FreeSurfer

---
<br>
⚠️ **Security Notice**: Only run bash scripts and download applications from official sources. 

For detailed, step-by-step instructions for your platform, use the sidebar navigation.
