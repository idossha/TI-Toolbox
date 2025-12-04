---
layout: installation
title: macOS Installation
permalink: /installation/macos/
---

## Prerequisites

### Docker Desktop
1. **Install Docker Desktop** for Mac from [docker.com](https://www.docker.com/products/docker-desktop/)
2. **Start Docker Desktop** and ensure it's running (green indicator in menu bar)

### X Server for GUI
Install [XQuartz 2.7.7](https://www.xquartz.org/) for GUI display:
- Download and install XQuartz version 2.7.7 from the official website
- Log out and back in (or restart) after installation

## Setup Steps

### Step 1: Download Required Files

Download these files to your preferred location (e.g., `~/TI-Toolbox/`):
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)**
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)**

### Step 2: Launch TI-Toolbox

1. **Open Terminal** (Applications > Utilities > Terminal)
2. **Navigate to your download location**:
   ```bash
   cd ~/TI-Toolbox/
   ```
3. **Make loader.sh executable**:
   ```bash
   chmod +x loader.sh
   ```
4. **Launch TI-Toolbox**:
   ```bash
   ./loader.sh
   ```
5. **First run will download Docker images (~30GB)** - this may take 30+ minutes

## macOS-Specific Features

### Apple Silicon Compatibility
- Docker Desktop automatically handles architecture differences between Intel and Apple Silicon
- Some performance differences may occur between architectures
- All TI-Toolbox features work on both architectures

## Desktop App Installation

If you're using the desktop application (TI-Toolbox.app), you may encounter a security warning when first opening it:

### Authorizing the Desktop App

When you first download and try to open TI-Toolbox from GitHub releases, macOS will show a warning:

> "TI-Toolbox" is damaged and can't be opened. You should move it to the Trash.

**To authorize the app:**

**Option 1: Right-click to Open**
1. Right-click (or Control-click) the TI-Toolbox.app file
2. Select "Open" from the context menu
3. Click "Open" in the security dialog
4. The app will now open normally

**Option 2: System Settings**
1. Go to System Settings → Privacy & Security
2. Scroll down to find "TI-Toolbox" in the "Security" section
3. Click "Open Anyway"
4. The app will now open normally

**Option 3: Terminal Command (Advanced)**
If the above methods don't work, you can remove the quarantine flag using Terminal:
1. Open Terminal
2. Run: `xattr -d com.apple.quarantine /path/to/TI-Toolbox.dmg`
3. Then double-click the DMG to open it

**Why this happens:**
TI-Toolbox is an open-source application not distributed through the Mac App Store. macOS Gatekeeper protects against potentially harmful software by blocking unsigned applications. This authorization process ensures you can safely run the app.

After authorizing once, the app will open normally in the future.

![Docker Settings on Apple]({{ site.baseurl }}/assets/imgs/installation/docker_apple.png){:style="max-width: 800px;"}
