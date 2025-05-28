---
layout: page
title: Downloads
permalink: /downloads/
---

# Download Temporal Interference Toolbox

Get the latest version of Temporal Interference Toolbox for your operating system. All downloads include the complete Docker-based environment.

<div class="download-section">
  <h2>Latest Release: Version 2.2.3
  <p>Released: May 2025
  
  <div class="download-grid">
    <div class="download-card">
      <div class="os-icon">🍎</div>
      <h4>macOS</h4>
      <p>For macOS 10.14 and later</p>
      <p>Intel and Apple Silicon</p>
      <a href="https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/Temporal Interference Toolbox-macOS-universal.dmg" class="download-btn">Download DMG</a>
      <p class="file-info">~150 MB</p>
    </div>
    
    <div class="download-card">
      <div class="os-icon">🐧</div>
      <h4>Linux</h4>
      <p>For Ubuntu 18.04+ and compatible distros</p>
      <p>x86_64 architecture</p>
      <a href="https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/Temporal Interference Toolbox-Linux-x86_64.AppImage" class="download-btn">Download AppImage</a>
      <p class="file-info">~180 MB</p>
    </div>
    
    <div class="download-card">
      <div class="os-icon">🪟</div>
      <h4>Windows</h4>
      <p>For Windows 10 and later</p>
      <p>64-bit only</p>
      <a href="https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/Temporal Interference Toolbox-Windows-x64.exe" class="download-btn">Download EXE</a>
      <p class="file-info">~140 MB</p>
    </div>
  </div>
</div>

## System Requirements

### Minimum Requirements
- **OS**: macOS 10.14+, Ubuntu 18.04+, Windows 10+ (64-bit)
- **RAM**: 16 GB
- **Storage**: 50 GB free space
- **Docker Desktop**: Latest version
- **Internet**: Required for initial Docker image download (~30 GB)

### Recommended Requirements
- **RAM**: 32 GB or more
- **Storage**: 100 GB free space
- **GPU**: NVIDIA GPU with CUDA support
- **CPU**: 8+ cores

## Installation Instructions

### macOS
1. Download the DMG file
2. Open the DMG and drag Temporal Interference Toolbox to Applications
3. Right-click and select "Open" for first launch (security)
4. Follow the setup wizard

### Linux
1. Download the AppImage file
2. Make it executable: `chmod +x Temporal Interference Toolbox-Linux-x86_64.AppImage`
3. Run: `./Temporal Interference Toolbox-Linux-x86_64.AppImage`
4. Optional: Use AppImageLauncher for desktop integration

### Windows
1. Download the EXE installer
2. Run the installer (may require administrator privileges)
3. Follow the installation wizard
4. Launch from Start Menu or Desktop shortcut

## Docker Images

Temporal Interference Toolbox requires Docker Desktop to be installed and running. On first launch, the application will automatically download the required Docker images (~30 GB). This process may take 15-30 minutes depending on your internet connection.

### Pre-downloaded Images

For environments with limited internet access, you can download the Docker images separately:

- [Temporal Interference Toolbox Docker Images Bundle](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/ti-csc-docker-images.tar.gz) (~30 GB)

To load pre-downloaded images:
```bash
docker load < ti-csc-docker-images.tar.gz
```

## Previous Versions

Need an older version? Check our [releases page](https://github.com/idossha/TI-Toolbox/releases) for all available versions.

## Checksums

Verify your download integrity:

```
# macOS
SHA256: abc123def456...

# Linux  
SHA256: 789ghi012jkl...

# Windows
SHA256: 345mno678pqr...
```

## Troubleshooting

### macOS Security Warning
If you see "Temporal Interference Toolbox can't be opened because it is from an unidentified developer":
1. Right-click the application
2. Select "Open" from the context menu
3. Click "Open" in the dialog

### Linux Permissions
If the AppImage won't run:
```bash
chmod +x Temporal Interference Toolbox-Linux-x86_64.AppImage
```

### Windows SmartScreen
If Windows SmartScreen blocks the installer:
1. Click "More info"
2. Click "Run anyway"

## Need Help?

- Check our [Documentation](/documentation)
- Visit the [Wiki](/wiki)
- Open an [Issue](https://github.com/idossha/TI-Toolbox/issues)
- Join the [Discussions](https://github.com/idossha/TI-Toolbox/discussions) 