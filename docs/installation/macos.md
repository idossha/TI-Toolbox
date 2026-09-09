---
layout: installation
title: macOS Installation
permalink: /installation/macos/
---

## Prerequisites

### Docker Desktop
1. **Install Docker Desktop** for Mac from [docker.com](https://www.docker.com/products/docker-desktop/)
2. **Start Docker Desktop** and ensure it's running (green indicator in menu bar)

That's the only prerequisite — no X server to install. The toolbox UI renders inside the
desktop app's own window; 3D/volume viewing happens in the same window too, not in a
separate application.

## Option 1: Desktop App

The desktop preview is unreleased. Use the installer and checksum supplied in the
**[internal testing handoff]({{ site.baseurl }}/installation/#internal-colleague-testing)**.
Public [2.5.0 downloads]({{ site.baseurl }}/releases/v2.5.0/) use the older stack and their
own setup instructions. A tested installer for this platform has not yet been identified here.

<br>

## Option 2: Command Line

Run from the maintainer-supplied tested source checkout; replace the image placeholder with
the reference in the [internal handoff]({{ site.baseurl }}/installation/#internal-colleague-testing).
The public Python package is not a way to obtain this unreleased launcher.

The same interface, in your browser, with no Electron app. Needs Docker and CPython 3.11+
(macOS ships 3.9, so install a newer one first — `brew install python@3.12`, or python.org).

```bash
python3 loader.py --image "<verified-image-reference>" --project ~/datasets/000
```

It starts the container, waits for the server and opens your browser. Add `--status`, `--logs`,
`--stop`, `--port` or `--no-open` as needed. Full reference:
**[Command-line launcher]({{ site.baseurl }}/installation/bash-cli/)**.

With a verified matching image available, the launcher downloads `idossha/ti-toolbox` (**≈ 2.3 GB to download, ≈ 9 GB unpacked on
disk**) — a few minutes on a typical connection.

<br>

## Option 3: Run the latest unreleased version

```bash
git clone https://github.com/idossha/TI-Toolbox.git
cd TI-Toolbox/desktop
cp .env.dev.example .env.dev     # edit TIT_DEV_PROJECT_DIR
npm ci && npm run dev
```

Needs Node 22.12+ (`brew install node`). See
**[Run the latest unreleased version]({{ site.baseurl }}/installation/bash-cli/#run-the-latest-unreleased-version)**
for what the first run builds and how long it takes.

## macOS-Specific Features

### Apple Silicon Compatibility
- The image is built for `linux/amd64`; on Apple Silicon Docker Desktop runs it under Rosetta emulation
- Expect slower FEM solves and FastSurfer segmentation on Apple Silicon than on a comparable x86 machine — see the [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/) page for the measured native-arm64 FastSurfer runtime and its emulated-amd64 status
- Workflow compatibility and packaged launch must be checked on each host architecture

### Signing and first launch

Signing, Apple notarization, Gatekeeper acceptance and clean first launch are **unverified
for the internal installer until recorded in the handoff**. A local package build does not
prove these properties. Report a blocked launch to the maintainer with the installer checksum
and the exact message; this guide does not assert that macOS will accept it without warnings.
