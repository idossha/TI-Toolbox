---
layout: installation
title: Windows Installation
permalink: /installation/windows/
---

## Prerequisites

### Ubuntu from Microsoft Store

1. **Install Ubuntu from Microsoft Store**:
   - Search for "Ubuntu" in the Microsoft Store
   - Install the latest Ubuntu version (this automatically sets up WSL2)
2. **Launch Ubuntu** from Start Menu and complete initial setup
3. **Update Ubuntu** (first time setup):
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

### Docker Desktop Integration
1. **Install Docker Desktop** for Windows
2. **Enable Ubuntu integration**:
   - Open Docker Desktop settings
   - Go to "Resources" > "WSL Integration"
   - Enable integration with your Ubuntu distribution

![Docker Settings on Windows]({{ site.baseurl }}/assets/imgs/installation/docker_windows.png){:style="max-width: 800px;"}

3. **Restart Docker Desktop** after enabling integration

No X server is required — the toolbox UI and viewer both run inside the desktop app's own
window, not a separate X11 client.

## Option 1: Desktop App

Download the pre-built desktop application for Windows from the **[Latest Release](https://github.com/idossha/TI-toolbox/releases/latest)**:

| Platform | Download |
|----------|----------|
| **Windows** | `TI-Toolbox.Setup.{version}.exe` |

Simply download and run the installer — the app handles Docker management and WSL2 setup for you.

<br>

## Option 2: Command Line

The same interface, in your browser, with no Electron app. Run it **from inside Ubuntu/WSL2**,
where the `docker` CLI reaches Docker Desktop through WSL integration:

```bash
pip install tit
tit launch --project /mnt/c/Users/YourName/datasets/000
```

Use the WSL path (`/mnt/c/...`), not the Windows one — that is the path Docker will bind-mount.
The launcher opens your browser at `http://127.0.0.1:<port>/auth/session?token=…`; WSL2
forwards localhost to Windows, so the tab opens in your normal Windows browser.

Add `--status`, `--logs`, `--stop`, `--port` or `--no-open` as needed. Full reference:
**[Command-line launcher]({{ site.baseurl }}/installation/bash-cli/)**.

The first run downloads `idossha/ti-toolbox` (**≈ 2.3 GB to download, ≈ 9 GB unpacked on
disk**) — a few minutes on a typical connection.

<br>

## Option 3: Run the latest unreleased version

From inside Ubuntu/WSL2, with Node 22.12+ installed there:

```bash
git clone https://github.com/idossha/TI-Toolbox.git
cd TI-Toolbox/desktop
cp .env.dev.example .env.dev     # edit TIT_DEV_PROJECT_DIR (a /mnt/c/... path)
npm ci && npm run dev
```

See **[Run the latest unreleased version]({{ site.baseurl }}/installation/bash-cli/#run-the-latest-unreleased-version)**
for what the first run builds and how long it takes.

## File Mounting Considerations

### Accessing Windows Files from Ubuntu
- Windows drives are mounted under `/mnt/` in Ubuntu
- `C:\Users\YourName\Desktop\` → `/mnt/c/Users/YourName/Desktop/`
- Use Ubuntu paths when running commands in the terminal

### Project Data Location
- Store your TI-Toolbox project data in your Windows filesystem
- Access via Ubuntu paths (e.g., `/mnt/c/{project-name}`)
- Docker containers will inherit Ubuntu's access to Windows files

## Troubleshooting

### Docker Integration Issues
- **WSL integration not enabled**: Check Docker Desktop settings under "Resources" > "WSL Integration"
- **Docker daemon not accessible**: Restart Docker Desktop and ensure WSL integration is active
- **Windows named pipe**: the desktop app talks to Docker over its Engine API; if Docker
  Desktop was just installed or updated, restart it once so its named pipe is available
  before launching TI-Toolbox.

---

**Next Steps**:
- [Dependencies](../dependencies/) - If you need to revisit dependency setup
- [Troubleshooting]({{ site.baseurl }}/wiki/troubleshooting/) - For common issues and solutions
- [Quick Start](../) - Return to main installation guide 
