---
layout: installation
title: Dependencies
permalink: /installation/dependencies/
---

**Docker** is the only dependency for running TI-Toolbox. There is no X server to install and
no separate FreeSurfer license needed for the core workflow (SimNIBS, pre-processing,
simulation, optimization, analysis, and the built-in viewer) — everything runs and renders
inside the desktop app itself.

Windows/macOS: Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)

Linux: Install [Docker Engine](https://docs.docker.com/engine/install/) using your distribution's package manager.

Post-Installation Configuration:
- Open Docker Desktop settings
- Go to "Resources" 
- Allocate at least **16GB RAM** (32GB+ recommended for large leadfields and FastSurfer segmentation)
- Ensure you have at sufficient free disk space

![Docker Settings on Apple]({{ site.baseurl }}/assets/imgs/installation/docker_resource.png){:style="max-width: 350px;"}

---

## System Requirements

### Minimum Requirements
- **RAM**: 16GB minimum, 32GB+ recommended
- **Storage**: the `idossha/ti-toolbox` image is **~6.7GB** to download, plus your project outputs — plan for 30GB+ free for a comfortable working set
- **Docker Desktop** 4.0+ (or Docker Engine with a daemon exposing the standard Engine API on Linux); port 8888 free if you use JupyterLab
- **Administrative privileges**: Required for initial setup


## Verification

### Test Docker Installation
```bash
# Check Docker version
docker --version

# Test Docker functionality
docker run hello-world
```

---

**Next Steps**: Once dependencies are installed, proceed to your platform-specific installation guide:
- [Windows Installation](../windows/)
- [macOS Installation](../macos/)
- [Linux Installation](../linux/) 
