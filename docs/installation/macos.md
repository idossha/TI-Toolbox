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

### Setup Steps

### Step 1: Download Required Files

Download these files to your preferred location (e.g., `~/TI-Toolbox/`):
- **[loader.py](https://github.com/idossha/TI-toolbox/blob/main/loader.py)**
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)**

### Step 2: Launch TI-Toolbox

1. **Open Terminal** (Applications > Utilities > Terminal)
2. **Navigate to your download location**:
   ```bash
   cd ~/TI-Toolbox/
   ```
3. **Launch TI-Toolbox**:
   ```bash
   python3 loader.py
   ```
4. **First run will download the single Docker image (`idossha/ti-toolbox`, ~6.7GB)** — a few minutes on a typical connection

## macOS-Specific Features

### Apple Silicon Compatibility
- The image is built for `linux/amd64`; on Apple Silicon Docker Desktop runs it under Rosetta emulation
- Expect slower FEM solves and FastSurfer segmentation on Apple Silicon than on a comparable x86 machine — see the [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/) page for the measured native-arm64 FastSurfer runtime and its emulated-amd64 status
- All TI-Toolbox features work on both architectures

### Security & Notarization
- **Apple Notarization**: The desktop app is notarized by Apple to ensure it's safe and hasn't been tampered with
- **Gatekeeper Compatibility**: The app passes macOS Gatekeeper checks, so you won't see security warnings when opening it
- **Hardened Runtime**: Uses macOS security features to protect against code injection and other exploits
