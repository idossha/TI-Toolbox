---
layout: installation
title: Dependencies
permalink: /installation/dependencies/
---

Before installing the TI Toolbox, you need to set up the following dependencies:

## Docker Installation

Docker is required for running the TI Toolbox containerized environment.

### Windows/macOS
Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)

**Post-Installation Configuration:**
- Open Docker Desktop settings
- Go to "Resources" 
- Allocate at least **32GB RAM** (recommended)
- Ensure you have at sufficient free disk space

### Linux  
Install [Docker Engine](https://docs.docker.com/engine/install/) using your distribution's package manager.

## X Server for GUI

The TI Toolbox requires an X server for GUI display, especially for visualization tools like freeview, fsleyes, and gmsh.

### macOS
Install **[XQuartz 2.7.7](https://www.xquartz.org/releases/archive.html)**

⚠️ **Important**: XQuartz version 2.7.7 is required for proper OpenGL functionality. Higher versions may cause OpenGL rendering issues with applications like freeview, fsleyes, and gmsh.

**Setup Steps:**
1. Download and install XQuartz 2.7.7
2. Log out and log back in (required for X11 initialization)
3. Launch XQuartz from Applications > Utilities
4. XQuartz will be configured automatically by TI Toolbox

### Windows
Install **[VcXsrv](https://sourceforge.net/projects/vcxsrv/)**

⚠️ **Do not use Xming** - it has compatibility issues with the TI Toolbox.

**Configuration:**
1. Launch XLaunch from the Start Menu
2. Select "Multiple windows"
3. Select "Start no client"
4. **Important**: Check "Disable access control"
5. Keep VcXsrv running while using TI Toolbox

### Linux
X11 is usually pre-installed on most Linux distributions.

**If GUI doesn't appear:**
```bash
xhost +local:docker
```

## System Requirements

### Minimum Requirements
- **RAM**: 32GB minimum (recommended for full functionality)
- **Storage**: At least 30GB free space for Docker images
- **Administrative privileges**: Required for initial setup

### Recommended Specifications
- **RAM**: 64GB+ for large datasets
- **CPU**: Multi-core processor (8+ cores recommended)
- **Storage**: SSD with 50GB+ free space
- **Network**: Stable internet connection for Docker image downloads

## Verification

### Test Docker Installation
```bash
# Check Docker version
docker --version

# Test Docker functionality
docker run hello-world
```

### Test X Server
- **macOS**: Launch XQuartz and verify it runs without errors
- **Windows**: Launch VcXsrv and ensure it's running in system tray
- **Linux**: Run `echo $DISPLAY` to verify X11 is configured

---

**Next Steps**: Once dependencies are installed, proceed to your platform-specific installation guide:
- [Windows Installation](../windows/)
- [macOS Installation](../macos/)
- [Linux Installation](../linux/) 