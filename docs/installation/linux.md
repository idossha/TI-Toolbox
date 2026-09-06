---
layout: installation
title: Linux Installation
permalink: /installation/linux/
---

## Prerequisites

### Docker Engine
1. **Install Docker Engine** following the [official installation guide](https://docs.docker.com/engine/install/)
2. **Start Docker service**:
   ```bash
   sudo systemctl start docker
   sudo systemctl enable docker
   ```
3. **Add user to docker group** (optional, avoids using sudo):
   ```bash
   sudo usermod -aG docker $USER
   ```
   *Log out and back in for changes to take effect*

No X server is required. The toolbox UI and 3D/volume viewer both run inside the desktop
app's own window (or, for the CLI route, are served over HTTP and opened in your regular
browser) — there is nothing X11-specific to install.

## Option 1: Desktop App

Download the pre-built desktop application for your Linux distribution from the **[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Format | Download |
|--------|----------|
| **AppImage** | `TI-Toolbox-{version}.AppImage` |
| **Debian/Ubuntu** | `ti-toolbox_{version}_amd64.deb` |

Simply download and run the AppImage, or install the .deb package — the app handles Docker management for you.

<br>

## Option 2: Command Line

### Setup Steps

### Step 1: Download Required Files

Download these files to your preferred location (e.g., `~/TI-Toolbox/`):
- **[loader.py](https://github.com/idossha/TI-toolbox/blob/main/loader.py)**
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)**

### Step 2: Launch TI-Toolbox

1. **Open Terminal**
2. **Navigate to your download location**:
   ```bash
   cd ~/TI-Toolbox/
   ```
3. **Ensure Docker is running**:
   ```bash
   sudo systemctl status docker
   ```
4. **Launch TI-Toolbox**:
   ```bash
   python3 loader.py
   ```
5. **First run will download the single Docker image (`idossha/ti-toolbox`, ~6.7GB)** — a few minutes on a typical connection

## Distribution-Specific Notes

### Ubuntu/Debian
- Follow standard Docker installation instructions — this is the primary tested distribution


*Currently tested primarily on Ubuntu. Please submit an issue if you encounter problems on other distributions.*
