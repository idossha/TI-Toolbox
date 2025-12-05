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

### X Server
Most Linux distributions come with X11 pre-installed. If you need to install it:
- **Ubuntu/Debian**: `sudo apt install xorg`
- **Fedora/RHEL**: `sudo dnf install xorg-x11-server-Xorg` (or yum)
- **Arch**: `sudo pacman -S xorg-server`

## Option 1: Desktop App

Download the pre-built desktop application for your Linux distribution from the **[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Format | Download |
|--------|----------|
| **AppImage** | `TI-Toolbox-{version}.AppImage` |
| **Debian/Ubuntu** | `TI-Toolbox-{version}.deb` |

Simply download and run the AppImage, or install the .deb package — the app handles Docker management for you.

<br>

## Option 2: Command Line

## Setup Steps

### Step 1: Download Required Files

Download these files to your preferred location (e.g., `~/TI-Toolbox/`):
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)**
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)**

### Step 2: Launch TI-Toolbox

1. **Open Terminal**
2. **Navigate to your download location**:
   ```bash
   cd ~/TI-Toolbox/
   ```
3. **Make loader.sh executable**:
   ```bash
   chmod +x loader.sh
   ```
4. **Ensure Docker is running**:
   ```bash
   sudo systemctl status docker
   ```
5. **Launch TI-Toolbox**:
   ```bash
   ./loader.sh
   ```
6. **First run will download Docker images (~30GB)** - this may take 30+ minutes

## Distribution-Specific Notes

### Ubuntu/Debian
- Follow standard Docker installation instructions
- X11 is usually pre-installed


*Currently tested primarily on Ubuntu. Please submit an issue if you encounter problems on other distributions.* 
