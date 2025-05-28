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

**Windows:** Install VcXsrv or Xming

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