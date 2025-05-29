---
layout: page
title: Installation Guide
permalink: /installation/
---

# Installation Guide

## Getting the TI Toolbox

The Temporal Interference Toolbox is distributed as compiled executables for Windows, macOS, and Linux. You can download the latest release from:

- **[Releases Page]({{ site.baseurl }}/releases/)** on this website
- **[GitHub Releases](https://github.com/idossha/TI-Toolbox/releases)** for all versions and release notes

## Understanding the Downloads

You are downloading **compiled executables** - standalone applications that include all necessary components bundled together. These executables:

- Do not require Python or other dependencies to be installed
- Include the complete TI Toolbox environment
- Are self-contained and portable

## Important Security Notice

Since the TI Toolbox is an independent development effort in its early stages, the executables are not officially signed or notarized by Apple or Microsoft. This means:

- Your operating system will show security warnings when downloading or running the application
- You will need administrative privileges (sudo access) to temporarily bypass these protections
- These protections can be re-enabled after installation

⚠️ **Note**: Only download the TI Toolbox from the official sources listed above to ensure safety.

## Platform-Specific Installation Instructions

### macOS Installation

#### Step 1: Download the Application
1. Download the macOS Universal ZIP file from the releases page
2. macOS will likely quarantine the download due to Gatekeeper protection

#### Step 2: Remove Quarantine (Terminal Method)
1. Open Terminal (found in Applications > Utilities)
2. Navigate to your Downloads folder:
   ```bash
   cd ~/Downloads
   ```
3. Remove the quarantine attribute from the ZIP file:
   ```bash
   sudo xattr -r -d com.apple.quarantine TemporalInterferenceToolbox-macOS-universal.zip
   ```
4. Enter your administrator password when prompted

#### Step 3: Extract and Run
1. Double-click the ZIP file to extract it
2. Drag the extracted application to your Applications folder
3. If you still get a security warning when opening:
   - Go to System Preferences > Security & Privacy > General
   - Click "Open Anyway" for the TI Toolbox application
   - Or in Terminal: `sudo spctl --master-disable` (temporarily disable Gatekeeper)
   - Run the app, then re-enable: `sudo spctl --master-enable`

### Windows Installation

#### Step 1: Download the Installer
1. Download the Windows EXE installer from the releases page
2. Windows Defender SmartScreen may block the download

#### Step 2: Bypass SmartScreen Protection
1. If Edge/Chrome blocks the download:
   - Click the "..." menu on the download warning
   - Select "Keep" > "Keep anyway"
2. When running the installer:
   - You may see "Windows protected your PC"
   - Click "More info"
   - Click "Run anyway"

#### Step 3: Administrator Installation
1. Right-click the installer and select "Run as administrator"
2. Follow the installation wizard
3. If Windows Defender blocks execution:
   - Open Windows Security
   - Go to "Virus & threat protection"
   - Click "Protection history"
   - Find the blocked app and click "Actions" > "Allow"

#### Alternative: Temporarily Disable Protection
If you continue having issues:
1. Open Windows Security
2. Go to "Virus & threat protection" > "Manage settings"
3. Temporarily turn off "Real-time protection"
4. Install the TI Toolbox
5. **Important**: Turn real-time protection back on immediately after installation

### Linux Installation

Linux users typically don't face the same security restrictions:

1. Download the AppImage file
2. Make it executable:
   ```bash
   chmod +x TemporalInterferenceToolbox-Linux-x86_64.AppImage
   ```
3. Run the application:
   ```bash
   ./TemporalInterferenceToolbox-Linux-x86_64.AppImage
   ```

## Post-Installation Setup

After successful installation:

1. **Docker Desktop**: Ensure Docker Desktop is installed and running
2. **System Resources**: Allocate sufficient RAM to Docker (16GB minimum, 32GB recommended)
3. **First Run**: The application will download required Docker images (~30GB) on first use

## Troubleshooting

### Common Issues

**"Cannot be opened because the developer cannot be verified" (macOS)**
- Use the Terminal quarantine removal method above
- Or right-click the app and select "Open" instead of double-clicking

**"This app can't run on your PC" (Windows)**
- Ensure you downloaded the correct version for your system architecture
- Try running as administrator

**Application won't start**
- Check that Docker Desktop is installed and running
- Verify you have sufficient disk space (50GB recommended)
- Review the console output for specific error messages

### Getting Help

If you encounter persistent issues:

1. Check the [GitHub Issues](https://github.com/idossha/TI-Toolbox/issues) for similar problems
2. Post in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)
3. Include your OS version, error messages, and steps to reproduce

## Security Best Practices

- Only download from official sources
- Verify the file hash if provided in release notes
- Re-enable security protections after installation
- Keep your operating system and Docker Desktop updated

---

[Back to Releases]({{ site.baseurl }}/releases/) | [Back to Home]({{ site.baseurl }}/) 