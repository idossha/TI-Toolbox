---
layout: page
title: Installation Guide
permalink: /installation/
---

## Getting the TI Toolbox

The Temporal Interference Toolbox is distributed as compiled executables for Windows, macOS, and Linux. You can download the latest release from:

- **[Releases Page]({{ site.baseurl }}/releases/)** on this website
- **[GitHub Releases](https://github.com/idossha/TI-Toolbox/releases)** for all versions and release notes

## Required Dependencies

Before installing the TI Toolbox, you need to set up the following dependencies:

### Docker Installation
- **Windows/macOS**: Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Linux**: Install [Docker Engine](https://docs.docker.com/engine/install/)

### X Server for GUI
- **macOS**: Install [XQuartz 2.7.7](https://www.xquartz.org/releases/archive.html) (newer versions may cause OpenGL rendering issues)
- **Windows**: Install [VcXsrv](https://sourceforge.net/projects/vcxsrv/) (do not use Xming)
- **Linux**: X11 is usually pre-installed, no additional setup needed

### System Requirements
- **RAM**: 32GB minimum (recommended for full functionality)
- **Storage**: At least 30GB free space for Docker images
- **Administrative privileges** for initial setup

## Understanding the Downloads

You are downloading **compiled executables** - standalone applications that include all necessary components bundled together. These executables:

- Do not require installation or any other dependencies to be installed aside from the above requirements
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

#### Step 1: Install Dependencies
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Install [XQuartz 2.7.7](https://www.xquartz.org/) (newer versions may cause OpenGL rendering issues)
3. After installing XQuartz:
   - Log out and log back in
   - Launch XQuartz from Applications > Utilities
   - XQuartz will be configured automatically by TI Toolbox

#### Step 2: Download and Prepare Application
1. Download the macOS Universal ZIP file from the releases page
2. macOS will likely quarantine the download due to Gatekeeper protection
3. Open Terminal (found in Applications > Utilities)
4. Navigate to your Downloads folder:
   ```bash
   cd ~/Downloads
   ```
5. Remove the quarantine attribute from the ZIP file:
   ```bash
   sudo xattr -r -d com.apple.quarantine TemporalInterferenceToolbox-macOS-universal.zip
   ```
6. Enter your administrator password when prompted

#### Step 3: Extract and Run
1. Double-click the ZIP file to extract it
2. Drag the extracted application to your Applications folder
3. If you get a security warning when opening:
   - Go to System Preferences > Security & Privacy > General
   - Click "Open Anyway" for the TI Toolbox application

### Windows Installation

#### Step 1: Install Dependencies
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Install [VcXsrv](https://sourceforge.net/projects/vcxsrv/) (do not use Xming)
3. Configure VcXsrv:
   - Launch XLaunch from the Start Menu
   - Select "Multiple windows"
   - Select "Start no client"
   - **Important**: Check "Disable access control"
   - Keep VcXsrv running while using TI Toolbox

#### Step 2: Download and Install
1. Download the Windows EXE executable from the releases page
2. If Edge/Chrome blocks the download:
   - Click the "..." menu on the download warning
   - Select "Keep" > "Keep anyway"
3. When running the installer:
   - You may see "Windows protected your PC"
   - Click "More info"
   - Click "Run anyway"

#### Step 3: Run Application
1. Right-click the installer and select "Run as administrator"
2. Follow the installation wizard
3. If Windows Defender blocks execution:
   - Open Windows Security
   - Go to "Virus & threat protection"
   - Click "Protection history"
   - Find the blocked app and click "Actions" > "Allow"

### Linux Installation

Linux installation is more straightforward as most dependencies are pre-installed:

1. Install Docker Engine using your distribution's package manager:
   ```bash
   # For Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install docker-ce docker-ce-cli containerd.io
   ```
   For other distributions, follow the [official Docker installation guide](https://docs.docker.com/engine/install/)

2. Download the AppImage file
3. Make it executable:
   ```bash
   chmod +x TemporalInterferenceToolbox-Linux-x86_64.AppImage
   ```
4. Run the application:
   ```bash
   ./TemporalInterferenceToolbox-Linux-x86_64.AppImage
   ```

## Post-Installation Setup

After successful installation, you'll need to configure Docker:

### Docker Configuration
1. **Start Docker**:
   - **Windows/macOS**: Launch Docker Desktop and wait for it to fully initialize
   - **Linux**: Start the Docker service: `sudo systemctl start docker`

2. **Allocate Resources** (Windows/macOS):
   - Open Docker Desktop settings
   - Go to "Resources"
   - Allocate at least 32GB RAM (recommended)
   - Ensure you have at least 30GB free disk space

3. **First Run**:
   - The application will download required Docker images (~30GB)
   - This may take some time depending on your internet connection
   - Images are cached for subsequent runs

### X Server Configuration
1. **macOS**:
   - XQuartz will be configured automatically by TI Toolbox
   - No manual configuration needed

2. **Windows**:
   - Keep VcXsrv running while using TI Toolbox
   - Ensure "Disable access control" is checked in XLaunch settings

3. **Linux**:
   - X11 should work out of the box
   - If needed: `xhost +local:docker`

## Troubleshooting

### Common Issues

**Docker Issues**
- Ensure Docker is running before starting TI Toolbox
- Check you have allocated sufficient RAM (32GB minimum)
- Verify you have enough free disk space (30GB minimum)

**GUI Display Issues**
- **macOS**: [XQuartz 2.7.7][[memory:3056357008131702354]] is required for proper OpenGL functionality. Higher versions may cause rendering issues.
- **Windows**: Make sure VcXsrv is running with "Disable access control" checked
- **Linux**: Run `xhost +local:docker` if GUI doesn't appear

**"Cannot be opened because the developer cannot be verified" (macOS)**
- Use the Terminal quarantine removal method described above
- Or right-click the app and select "Open" instead of double-clicking

**"This app can't run on your PC" (Windows)**
- Ensure you downloaded the correct version for your system architecture
- Try running as administrator

### Getting Help

If you encounter persistent issues:

1. Check the [GitHub Issues](https://github.com/idossha/TI-Toolbox/issues) for similar problems
2. Post in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)
3. Include your:
   - OS version
   - Docker version
   - X server version (XQuartz/VcXsrv)
   - Error messages
   - Steps to reproduce

## Security Best Practices

- Only download from official sources
- Verify the file hash if provided in release notes
- Re-enable security protections after installation
- Keep your operating system and Docker Desktop updated

## Alternative: Command-Line Bash Script Usage

You do **not** have to use the graphical executables to run the TI Toolbox! The executables simply provide a GUI for the launcher program. If you prefer, or if you are running on a remote server (or just want more control), you can use the bash script directly from the command line.

### When to Use the Bash Script
- Running on a remote server (no GUI)
- Prefer command-line workflows
- Want to automate or customize the launch process
- Troubleshooting or advanced usage

### How to Use the Bash Script

1. **Download** the following two files from the [TI Toolbox GitHub Releases](https://github.com/idossha/TI-Toolbox/releases):
   - `launcher/bash/loader.sh`
   - `launcher/bash/docker-compose.yml`

2. **Place both files in the same directory** on your system or server.

3. **Make the script executable (optional, or use bash directly):**
   ```bash
   chmod +x loader.sh
   ```

4. **Run the script:**
   ```bash
   bash loader.sh
   ```

5. **Follow the prompts** in your terminal to set up and launch the toolbox environment.

This method gives you the same core functionality as the GUI, but in a terminal-based.

---

[Back to Releases]({{ site.baseurl }}/releases/) | [Back to Home]({{ site.baseurl }}/) 
