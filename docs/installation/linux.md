---
layout: installation
title: Linux Installation
permalink: /installation/linux/
---

## Step 1: Download TI Toolbox

1. Go to the [Releases Page]({{ site.baseurl }}/releases/)
2. Download the **Linux AppImage** file
3. Save to a convenient location (e.g., `~/Downloads/`)

## Step 2: Make AppImage Executable

```bash
# Navigate to download location
cd ~/Downloads

# Make AppImage executable
chmod +x TemporalInterferenceToolbox-Linux-x86_64.AppImage
```

## Step 3: First Run

1. Ensure Docker service is running: `sudo systemctl status docker`
2. Launch TI Toolbox
3. **First run will download Docker images (~30GB)**
   - This process may take 30+ minutes
   - Progress will be shown in the application
   - Images are cached for future use

## Distribution-Specific Notes

Currently only tested on Ubuntu distro.
