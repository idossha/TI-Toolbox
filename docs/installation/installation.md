---
layout: installation
title: Installation
permalink: /installation/
---

## Option 1: Desktop App

Download the pre-built desktop application for your platform from the **[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Platform | Download |
|----------|----------|
| **macOS (Intel)** | `TI-Toolbox-{version}-x64.dmg` |
| **macOS (Apple Silicon)** | `TI-Toolbox-{version}-arm64.dmg` |
| **Windows** | `TI-Toolbox-Setup-{version}.exe` |
| **Linux** | `TI-Toolbox-{version}.AppImage` or `.deb` |

Simply download, install, and launch — the app handles Docker management for you.

<br>

## Option 2: Command Line (Bash)

**Download the required files:**
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)** - Main launch script
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)** - Docker configuration

<br>

## Option 3: HPC (Apptainer/Singularity)

For high-performance computing clusters where Docker is unavailable. Users build the `.sif` image from the definition file.

**[Full HPC Deployment Guide]({{ site.baseurl }}/installation/hpc-apptainer/)**

Quick start:
```bash
# 1. Get the definition file
curl -O https://raw.githubusercontent.com/idossha/TI-toolbox/main/container/blueprint/apptainer.def
curl -O https://raw.githubusercontent.com/idossha/TI-toolbox/main/container/blueprint/apptainer_run.sh
chmod +x apptainer_run.sh

# 2. Build the SIF (30-60 min, requires fakeroot or root)
apptainer build ti-toolbox.sif apptainer.def

# 3. Run interactively
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /data/my_study
```

<br>

---

## Supported Operating Systems

| Operating System | Support Level | Testing Status | Notes |
|------------------|---------------|----------------|--------|
| **Windows** | ✅ Full Support | ✅ Active Testing | Via WSL2 + Ubuntu |
| **Linux (Ubuntu)** | ✅ Full Support | ✅ Active Testing | Primary development platform |
| **macOS (Apple Silicon)** | ✅ Full Support | ✅ Active Testing | Native ARM64 support |
| **macOS (Intel)** | ✅ Full Support | ⚠️ Stopped Testing | May work but no longer tested |

### Known Issues
- **Latest macOS version 26 (Tahoe)**: Potential compatibility issues with some graphical components


---

## Prerequisites

**Options 1 & 2 (Desktop / CLI):**
- **Docker**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or [Docker Engine](https://docs.docker.com/engine/install/) (Linux)
- **X Server**: XQuartz (macOS), VcXsrv (Windows), or X11 (Linux - usually pre-installed)

**Option 3 (HPC):**
- **Apptainer** 1.1+ (or Singularity 3.8+) — typically provided by your cluster's module system
- **FreeSurfer License**: Free from [FreeSurfer registration](https://surfer.nmr.mgh.harvard.edu/registration.html)

---
<br>
⚠️ **Security Notice**: Only run bash scripts and download applications from official sources. 

For detailed, step-by-step instructions for your platform, use the sidebar navigation.
