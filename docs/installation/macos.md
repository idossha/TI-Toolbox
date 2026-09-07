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

Download the pre-built desktop application for your Mac from the **[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Architecture | Download |
|--------------|----------|
| **Apple Silicon** | `TI-Toolbox-{version}-arm64.dmg` |
| **Intel/AMD** | `TI-Toolbox-{version}.dmg` |

Simply download, mount the DMG, and drag TI-Toolbox to your Applications folder — the app handles Docker management for you.

<br>

## Option 2: Command Line

The same interface, in your browser, with no Electron app. Needs Docker and CPython 3.11+
(macOS ships 3.9, so install a newer one first — `brew install python@3.12`, or python.org).

```bash
pip install tit
tit launch --project ~/datasets/000
```

It starts the container, waits for the server and opens your browser. Add `--status`, `--logs`,
`--stop`, `--port` or `--no-open` as needed. Full reference:
**[Command-line launcher]({{ site.baseurl }}/installation/bash-cli/)**.

The first run downloads `idossha/ti-toolbox` (**≈ 2.3 GB to download, ≈ 9 GB unpacked on
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
- All TI-Toolbox features work on both architectures

### Security & Notarization
- **Apple Notarization**: The desktop app is notarized by Apple to ensure it's safe and hasn't been tampered with
- **Gatekeeper Compatibility**: The app passes macOS Gatekeeper checks, so you won't see security warnings when opening it
- **Hardened Runtime**: Uses macOS security features to protect against code injection and other exploits
