---
layout: installation
title: Installation
permalink: /installation/
---

## Stable public installation (2.5.0)

Use the [2.5.0 downloads]({{ site.baseurl }}/releases/v2.5.0/) and the
[installation documentation frozen at the 2.5.0 tag](https://github.com/idossha/TI-Toolbox/tree/v2.5.0/docs/installation).
Its platform-specific X11 setup and two-image stack still apply. When following that archived
guide, obtain scripts and compose files from the **same `v2.5.0` tag**, even where an old link
says `main`; current `main` may contain the upcoming launcher.

## Upcoming desktop preview

The upcoming desktop preview uses a single Docker image. Docker Desktop (macOS/Windows) or Docker Engine
(Linux) is the only thing you install yourself — SimNIBS, FastSurfer, the TI-Toolbox UI and
the built-in viewer are all baked into the image.

There are three ways to run it, and **they all land on the same interface**. The UI is served
by the container; the desktop application is a shell around it, and the command-line launcher
puts the same page in your browser instead of in a window. Pick the row that describes you:

| | You get | You need | Best for |
|---|---|---|---|
| **[1. Desktop app](#option-1-desktop-app)** | An application in your dock | Docker | Colleagues with a verified preview installer. |
| **[2. Command line](#option-2-command-line-no-electron)** | The UI in a browser tab | Docker, Python 3.11+ | Remote/SSH machines, lab servers, scripted setups |
| **[3. From source](#option-3-run-the-latest-unreleased-version)** | The unreleased code | Docker, Node 22.12+, git | Trying a fix before it ships; contributing |

When a matching image is available, the launcher is designed to download `idossha/ti-toolbox:{version}` — **final candidate download and disk sizes pending measurement**. It is downloaded once and reused by all three options.

<br>

## Internal colleague testing

This is preparation for internal use from `main` and a matching Docker Hub image, **not a
public release**. No public tag, release announcement or updater notification is implied.
Use a copy of a project so preview outputs do not replace the originals.

The maintainer must fill this handoff before asking a colleague to launch:

| Required value | Verification status |
|---|---|
| Tested `main` commit | **Pending — unverified** |
| Intended Docker Hub image | `idossha/ti-toolbox:internal-20260908.1` — publication **pending** |
| Immutable image digest | **Pending — unverified** |
| Internal runtime / app version | `3.0.0-dev.1` — preview identifier, not a public release |
| Tested host OS / architecture and Docker version | **Pending — unverified** |
| Installer location and SHA-256, if using the desktop installer | **Pending — unverified** |
| Signing / notarization and clean first-launch result, per installer | **Pending — unverified** |

1. Install and start Docker Desktop, or Docker Engine on Linux. For the browser route,
   also install Python 3.11+ and make the `docker` CLI available.
2. Obtain the maintainer's tested `main` source revision and matching image reference.
   Check `git rev-parse HEAD` against the supplied commit. Do not substitute `latest`, `dev`,
   or a version-shaped image tag whose digest has not been verified.
3. Run the [command-line route](#option-2-command-line-no-electron) from that checkout,
   with the supplied image and a copy of your project. Alternatively, use the supplied
   installer only after its platform-specific launch check is recorded above.
4. Confirm the project opens, subjects appear, and the intended small example job completes
   with readable outputs. Record the commit, image digest, OS, job type and outcome.
   A successful launch alone does not validate every scientific workflow.
5. Report any failure with the job ID and redacted log; exclude session URLs and tokens.
   Consult [Troubleshooting]({{ site.baseurl }}/wiki/troubleshooting/) for known problems.

The internal tag above is an integration identifier, **not evidence that a pull will work**.
The source must reach `main` before a standalone loader can retrieve it. Both standalone
`loader.py` and `loader.sh` refresh source from `main` into a shared isolated cached environment
on each startup, so starting requires network access. Management commands `--stop`, `--status`
and `--logs` use a working cached launcher offline without refreshing source. A loader run
within a checkout uses that checkout instead.
For a reproducible colleague run, prefer the tested checkout and recorded image digest.
The Tetravox embed used in the internal image is also awaiting public asset publication;
use the supplied complete image rather than assuming a public embed download is available.
These pending values are intentionally not download links or executable image defaults.

## Option 1: Desktop App

The preview is **not available from the public release downloads**. Use only the installer
identified in the [internal testing handoff](#internal-colleague-testing), with its matching
image. Installer format alone does not establish signing, notarization, or successful first
launch on your platform. Those checks are recorded per artifact.

The app is designed to select a project folder, pull the image and start its container.
A packaged first launch must be verified before this is described as a tested install route.

Per-platform notes: **[macOS]({{ site.baseurl }}/installation/macos/)** ·
**[Windows]({{ site.baseurl }}/installation/windows/)** ·
**[Linux]({{ site.baseurl }}/installation/linux/)**.

<br>

## Option 2: Command Line (no Electron)

The same UI, in your browser, driven by a small Python launcher. Useful when the desktop app
is not an option: a machine you reach over SSH, a shared lab server, a container host, or a
setup you want to script.

Do not use `pip install tit` to obtain the unreleased launcher. Replace the placeholder below
with the maintainer-supplied image reference before running.

```bash
# From the tested source checkout, with the supplied matching image:
python3 loader.py --project ~/datasets/000 --image "<verified-image-reference>"
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

## Target platforms (preview)

| Platform | Support | Notes |
|----------|---------|-------|
| **Linux x86_64** | Native | Docker Engine |
| **Windows x64** | Native (via WSL2) | Docker Desktop + WSL2 |
| **macOS (Apple Silicon)** | Emulated | The image is `linux/amd64`; Docker Desktop runs it under emulation. Measured FastSurfer runtime under this emulation has not yet been benchmarked — see the [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/) page for the native number and status. |
| **macOS (Intel)** | Native | `linux/amd64`, same architecture as the image |

The preview image targets `linux/amd64` only; there is no native `arm64` build. On Apple
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

## Container engine targets (preview)

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
