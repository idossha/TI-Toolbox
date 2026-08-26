---
layout: installation
title: macOS Installation
permalink: /installation/macos/
---

## Prerequisites

### Docker Desktop
1. **Install Docker Desktop** for Mac from [docker.com](https://www.docker.com/products/docker-desktop/)
2. **Start Docker Desktop** and ensure it's running (green indicator in menu bar)

### X Server for GUI
Install [XQuartz](https://www.xquartz.org/) for GUI display:
- Download and install XQuartz from the official website
- Log out and back in (or restart) after installation
- On the first launch of a project, the loader enables *Allow connections from network clients* for you (`defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false`); restart XQuartz once afterwards

## Option 1: Desktop App

Download the pre-built desktop application for your Mac from the **[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Architecture | Download |
|--------------|----------|
| **Intel/AMD** | `TI-Toolbox-{version}.dmg` |
| **Apple Silicon** | `TI-Toolbox-{version}-arm64.dmg` |

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
4. **First run will download the two Docker images (~18GB download; they unpack to roughly 85GB on disk)** - this may take 30+ minutes

## macOS-Specific Features

### Apple Silicon Compatibility
- Both images are built for `linux/amd64`; on Apple Silicon Docker Desktop runs them under Rosetta emulation
- Expect slower FEM solves and recon-all on Apple Silicon than on a comparable x86 machine
- All TI-Toolbox features work on both architectures

### Security & Notarization
- **Apple Notarization**: The desktop app is notarized by Apple to ensure it's safe and hasn't been tampered with
- **Gatekeeper Compatibility**: The app passes macOS Gatekeeper checks, so you won't see security warnings when opening it
- **Hardened Runtime**: Uses macOS security features to protect against code injection and other exploits
