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
Install [XQuartz 2.7.7](https://www.xquartz.org/) for GUI display:
- Download and install XQuartz version 2.7.7 from the official website
- Log out and back in (or restart) after installation

## Option 1: Desktop App

Download the pre-built desktop application for your Mac from the **[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Architecture | Download |
|--------------|----------|
| **Intel/AMD** | `TI-Toolbox-{version}-x64.dmg` |
| **Apple Silicon** | `TI-Toolbox-{version}-arm64.dmg` |

Simply download, mount the DMG, and drag TI-Toolbox to your Applications folder — the app handles Docker management for you.

<br>

## Option 2: Command Line

## Setup Steps

### Step 1: Download Required Files

Download these files to your preferred location (e.g., `~/TI-Toolbox/`):
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)**
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)**

### Step 2: Launch TI-Toolbox

1. **Open Terminal** (Applications > Utilities > Terminal)
2. **Navigate to your download location**:
   ```bash
   cd ~/TI-Toolbox/
   ```
3. **Make loader.sh executable**:
   ```bash
   chmod +x loader.sh
   ```
4. **Launch TI-Toolbox**:
   ```bash
   ./loader.sh
   ```
5. **First run will download Docker images (~30GB)** - this may take 30+ minutes

## macOS-Specific Features

### Apple Silicon Compatibility
- Docker Desktop automatically handles architecture differences between Intel and Apple Silicon
- Some performance differences may occur between architectures
- All TI-Toolbox features work on both architectures

### Security & Notarization
- **Apple Notarization**: The desktop app is notarized by Apple to ensure it's safe and hasn't been tampered with
- **Gatekeeper Compatibility**: The app passes macOS Gatekeeper checks, so you won't see security warnings when opening it
- **Hardened Runtime**: Uses macOS security features to protect against code injection and other exploits
