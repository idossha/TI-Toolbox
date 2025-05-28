---
layout: wiki
title: Installation Guide
permalink: /wiki/installation-guide/
---

# Installation Guide

This guide will walk you through installing Temporal Interference Toolbox on your system.

## Prerequisites

Before installing Temporal Interference Toolbox, ensure you have the following:

### 1. Docker Desktop

Docker is required to run Temporal Interference Toolbox's containerized environment.

- **Download**: [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Version**: Latest stable release
- **Resources**: Allocate at least 8GB RAM to Docker

#### Platform-Specific Docker Setup

**macOS:**
1. Download Docker Desktop for Mac
2. Install by dragging to Applications
3. Start Docker Desktop from Applications
4. Increase memory allocation in Preferences > Resources

**Linux:**
1. Install Docker Engine or Docker Desktop
2. Add your user to the docker group: `sudo usermod -aG docker $USER`
3. Log out and back in for group changes to take effect

**Windows:**
1. Enable WSL2 (Windows Subsystem for Linux)
2. Install Docker Desktop with WSL2 backend
3. Ensure virtualization is enabled in BIOS

### 2. Display Server (for GUI)

**macOS:** Install XQuartz
- Download XQuartz 2.7.7 or 2.8.0 (not 2.8.1+)
- Enable "Allow connections from network clients"

**Linux:** X11 is typically pre-installed

**Windows:** Install VcXsrv X11 Server (Required for GUI)

#### Windows VcXsrv Setup (Detailed)

The Temporal Interference Toolbox GUI on Windows requires an X11 server to display Linux-based graphical applications from Docker containers.

**Step 1: Install VcXsrv**
1. Download VcXsrv from: [https://sourceforge.net/projects/vcxsrv/](https://sourceforge.net/projects/vcxsrv/)
2. Run the installer with default settings
3. No special configuration needed during installation

**Step 2: Configure and Launch VcXsrv**
1. Launch "XLaunch" from the Start Menu
2. **Configuration options:**
   - **Display settings**: Select "Multiple windows"
   - **Client startup**: Select "Start no client"
   - **Extra settings**: ✅ **CHECK "Disable access control"** (Critical!)
3. Click "Finish"
4. XLaunch will start and show an icon in the system tray
5. **Keep VcXsrv running** while using the TI-Toolbox GUI

**Step 3: Verify VcXsrv Setup**
- Look for the VcXsrv icon in your system tray (notification area)
- If the GUI fails to launch, restart VcXsrv with correct settings

**Important Notes:**
- VcXsrv must be running **before** launching the TI-Toolbox GUI
- The "Disable access control" setting is required for Docker containers to connect
- You can save your XLaunch configuration for future use

**Alternative:** You can also use Xming as an alternative to VcXsrv, but VcXsrv is recommended for better compatibility.

### 3. System Requirements

- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 50GB free space
- **CPU**: 4+ cores recommended
- **GPU**: Optional, NVIDIA with CUDA support

## Installation Steps

### Step 1: Download Temporal Interference Toolbox

1. Visit the [Releases page](/releases)
2. Select your operating system
3. Download the appropriate installer (version 2.x.x or newer). Note: Versions 1.x.x are no longer supported.

### Step 2: Install the Application

#### macOS Installation

1. Open the downloaded DMG file
2. Drag Temporal Interference Toolbox to your Applications folder
3. Right-click Temporal Interference Toolbox and select "Open" (first time only)
4. If you see a security warning, click "Open" to proceed

#### Linux Installation

1. Make the AppImage executable:
   ```bash
   chmod +x Temporal Interference Toolbox-Linux-x86_64.AppImage
   ```

2. Run the AppImage:
   ```bash
   ./Temporal Interference Toolbox-Linux-x86_64.AppImage
   ```

3. (Optional) Install AppImageLauncher for desktop integration

#### Windows Installation

1. Run the downloaded installer
2. Follow the installation wizard
3. Choose installation directory
4. Create desktop shortcut (optional)

### Step 3: First Launch

1. **Start Docker Desktop** and wait for it to fully initialize
2. **Launch Temporal Interference Toolbox** from your applications or desktop
3. **Select Project Directory** - choose or create a BIDS-compliant folder
4. **Start Docker Containers** - this will download ~30GB on first run

### Step 4: Verify Installation

Once containers are running, verify the installation:

1. Click "Launch CLI"
2. In the terminal, run:
   ```bash
   ti-csc --version
   ```
3. You should see version information

## Troubleshooting

### Docker Issues

**Problem**: "Docker daemon not running"
- **Solution**: Start Docker Desktop and wait for it to fully initialize

**Problem**: "Permission denied while trying to connect to Docker"
- **Solution (Linux)**: Add user to docker group: `sudo usermod -aG docker $USER`

### GUI Issues (macOS)

**Problem**: GUI windows don't appear
- **Solution**: 
  1. Quit XQuartz
  2. Open XQuartz preferences
  3. Under Security, enable "Allow connections from network clients"
  4. Restart XQuartz

### GUI Issues (Windows)

**Problem**: "No X11 server detected" or GUI fails to launch
- **Solution**: 
  1. Ensure VcXsrv is installed and running (check system tray)
  2. Restart VcXsrv with correct settings:
     - Multiple windows → Start no client → ✅ Disable access control
  3. If still failing, try restarting the TI-Toolbox launcher

**Problem**: GUI launches but shows black screen or errors
- **Solution**:
  1. Ensure "Disable access control" was checked in XLaunch
  2. Temporarily disable Windows Firewall to test
  3. Try launching CLI first, then run `GUI` command manually

**Problem**: CLI works but GUI doesn't
- **Solution**: This indicates VcXsrv is not running or configured correctly
  1. Check system tray for VcXsrv icon
  2. Restart XLaunch with proper configuration
  3. Ensure VcXsrv is running before launching GUI

### Memory Issues

**Problem**: "Out of memory" errors
- **Solution**: 
  1. Open Docker Desktop settings
  2. Increase memory allocation to at least 8GB
  3. Restart Docker Desktop

## Next Steps

- Explore the [CLI commands](/documentation#cli-commands)

## Getting Help

If you encounter issues:

1. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
2. Ask in [Discussions](https://github.com/idossha/TI-Toolbox/discussions) 