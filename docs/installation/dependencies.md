---
layout: installation
title: Dependencies
permalink: /installation/dependencies/
---

**1. Docker** is required for running the TI Toolbox containerized environment.

Windows/macOS: Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)

Linux: Install [Docker Engine](https://docs.docker.com/engine/install/) using your distribution's package manager.

Post-Installation Configuration:
- Open Docker Desktop settings
- Go to "Resources" 
- Allocate at least **32GB RAM** (64GB+ recommended for recon-all and large leadfields)
- Ensure you have at sufficient free disk space

![Docker Settings on Apple]({{ site.baseurl }}/assets/imgs/installation/docker_resource.png){:style="max-width: 350px;"}

---

**2. X Server** Optional, if GUI is desired.

**macOS:** Install **[XQuartz](https://www.xquartz.org/)** and enable *Allow connections from network clients* (the loader does this on first launch). If Gmsh/FreeView show OpenGL rendering problems on a recent XQuartz, the older 2.7.7 release from the [archive](https://www.xquartz.org/releases/archive.html) is a known-good fallback.

**Setup Steps:**
1. Download and install XQuartz 2.7.7
2. Log out and log back in (required for X11 initialization)
3. Launch XQuartz from Applications > Utilities
4. XQuartz will be configured automatically by TI Toolbox

**Windows**: Install **[VcXsrv](https://sourceforge.net/projects/vcxsrv/)**

Start it in *Multiple windows* mode with *Disable access control* checked. VcXsrv is the tested server; Xming is not recommended.

**Configuration:**
1. Launch XLaunch from the Start Menu
2. Select "Multiple windows"
3. Select "Start no client"
4. **Important**: Check "Disable access control"
5. Keep VcXsrv running while using TI Toolbox

**Linux**: X11 is usually pre-installed on most Linux distributions.

**If GUI doesn't appear:**
```bash
xhost +local:docker
```
---

## System Requirements

### Minimum Requirements
- **RAM**: 32GB minimum, 64GB+ recommended
- **Storage**: the two Docker images (`idossha/simnibs`, `idossha/ti-toolbox_freesurfer`) are ~18GB to download and ~85GB once unpacked, plus the FreeSurfer data volume and your project outputs — plan for 100GB+ free
- **Docker Desktop** 4.0+ (or Docker Engine with Compose v2 on Linux); port 8888 free if you use JupyterLab
- **Administrative privileges**: Required for initial setup


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