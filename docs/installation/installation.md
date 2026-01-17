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

## Prerequisites (Required for Both Options)

- **Docker**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or [Docker Engine](https://docs.docker.com/engine/install/) (Linux)
- **X Server**: XQuartz (macOS), VcXsrv (Windows), or X11 (Linux - usually pre-installed)

---
<br>
⚠️ **Security Notice**: Only run bash scripts and download applications from official sources. 

For detailed, step-by-step instructions for your platform, use the sidebar navigation.
