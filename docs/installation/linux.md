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

The same interface, in your browser, with no Electron app. Needs Docker and CPython 3.11+
(`sudo apt install python3` on a current Ubuntu already gives you 3.11+).

```bash
pip install tit
tit launch --project ~/datasets/000
```

It starts the container, waits for the server and opens your browser. Add `--status`, `--logs`,
`--stop`, `--port` or `--no-open` as needed. Full reference:
**[Command-line launcher]({{ site.baseurl }}/installation/bash-cli/)**.

The first run downloads `idossha/ti-toolbox` (**≈ 2.3 GB to download, ≈ 9 GB unpacked on
disk**) — a few minutes on a typical connection.

<br>

## Option 3: Run the latest unreleased version

```bash
git clone https://github.com/idossha/TI-Toolbox.git
cd TI-Toolbox/desktop
cp .env.dev.example .env.dev     # edit TIT_DEV_PROJECT_DIR
npm ci && npm run dev
```

Needs Node 22.12+ (nodejs.org, or `nvm install 22`). See
**[Run the latest unreleased version]({{ site.baseurl }}/installation/bash-cli/#run-the-latest-unreleased-version)**
for what the first run builds and how long it takes.

## Distribution-Specific Notes

### Ubuntu/Debian
- Follow standard Docker installation instructions — this is the primary tested distribution


*Currently tested primarily on Ubuntu. Please submit an issue if you encounter problems on other distributions.*
