---
layout: installation
title: macOS Installation
permalink: /installation/macos/
---

## Step 1: Download TI Toolbox

1. Go to the [Releases Page]({{ site.baseurl }}/releases/)
2. Download the **macOS Universal ZIP** file
3. macOS will likely quarantine the download due to Gatekeeper protection

## Step 2: Remove Quarantine (Security Setup)

Since the TI-Toolbox is not officially signed, you need to remove macOS quarantine:

1. Open **Terminal** (Applications > Utilities > Terminal)
2. Navigate to Downloads folder:
   ```bash
   cd ~/Downloads
   ```
3. Remove quarantine attribute:
   ```bash
   sudo xattr -r -d com.apple.quarantine TemporalInterferenceToolbox-macOS-universal.zip
   ```
4. Enter your administrator password when prompted

## Step 3: First Launch

### Handle Security Warnings
If you get a security warning when opening:
1. Go to **System Preferences** > **Security & Privacy** > **General**
2. Click **"Open Anyway"** for the TI Toolbox application


## Step 4: First Run

1. Ensure Docker Desktop is running (green status)
2. Launch TI-Toolbox from Applications
3. **First run will download Docker images (~30GB)**
   - This process may take 30+ minutes
   - Progress will be shown in the application
   - Images are cached for future use

## macOS-Specific Features

### Apple Silicon Compatibility
- TI-Toolbox Universal build works on both Intel and Apple Silicon Macs
- Docker Desktop automatically handles architecture differences
- Some performance differences may occur between architectures

![Docker Settings on Apple]({{ site.baseurl }}/installation/assets/docker_apple.png){:style="max-width: 800px;"}
