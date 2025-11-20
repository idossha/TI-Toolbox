# TI-Toolbox Desktop Application

A cross-platform desktop application launcher for the Temporal Interference Toolbox. This application provides a user-friendly interface that simplifies the Docker-based workflow, allowing users to launch the TI-Toolbox GUI with just a few clicks.

## Features

- **Cross-Platform**: Works on macOS, Windows, and Linux
- **Simple Interface**: Clean, intuitive GUI for selecting project directories
- **Automatic Setup**: Initializes BIDS-compliant project structure automatically
- **Docker Integration**: Handles all Docker container orchestration behind the scenes
- **Resilient Orchestration**: Uses Docker's API (via `dockerode`) with detailed health checks and retries
- **Built-in Diagnostics**: Real-time activity feed plus one-click log access for support
- **Persistent Configuration**: Remembers your last project directory
- **Platform Detection**: Provides platform-specific setup guidance

## Prerequisites

### All Platforms

1. **Docker Desktop** must be installed and running
   - macOS: [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
   - Windows: [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
   - Linux: [Docker Engine](https://docs.docker.com/engine/install/)

2. **X Server** for GUI display (platform-specific):

### macOS

- **XQuartz** (version 2.8.0 or higher)
  - Download from: https://www.xquartz.org
  - After installation:
    1. Open XQuartz → Preferences → Security
    2. Enable "Allow connections from network clients"
    3. Restart XQuartz

### Windows

- **VcXsrv** or **Xming**
  - VcXsrv: https://sourceforge.net/projects/vcxsrv/
  - Xming: https://sourceforge.net/projects/xming/
  - Launch with:
    - "Multiple windows" mode
    - "Disable access control" checked
    - Configure Windows Firewall to allow X server connections

### Linux

- X11 is typically pre-installed
- Ensure your user has permission to access the X server

## Installation

### Option 1: Download Pre-built Binaries (Recommended)

Download the appropriate installer for your platform from the [Releases](https://github.com/idossha/TI-Toolbox/releases) page:

- **macOS**: `TI-Toolbox-{version}.dmg` or `TI-Toolbox-{version}-mac.zip`
- **Windows**: `TI-Toolbox-Setup-{version}.exe` or `TI-Toolbox-{version}.exe` (portable)
- **Linux**: `TI-Toolbox-{version}.AppImage` or `ti-toolbox_{version}_amd64.deb`

### Option 2: Build from Source

#### 1. Install Node.js

- Download and install Node.js 18+ from: https://nodejs.org/

#### 2. Clone the Repository

```bash
git clone https://github.com/idossha/TI-Toolbox.git
cd TI-Toolbox/package
```

#### 3. Install Dependencies

```bash
npm install
```

#### 4. Build the Application

Build for your current platform:

```bash
npm run build
```

Or build for specific platforms:

```bash
# macOS
npm run build:mac

# Windows
npm run build:win

# Linux
npm run build:linux

# All platforms (requires platform-specific tools)
npm run build:all
```

The built applications will be in the `dist/` directory.

## Usage

### Running the Application

1. **Launch the Desktop App**
   - macOS: Open `TI-Toolbox.app` from Applications
   - Windows: Run `TI-Toolbox.exe`
   - Linux: Run the AppImage or installed application

2. **Select Project Directory**
   - Click "Browse" to select an existing project directory
   - Or create a new directory for a new project
   - The app will remember your selection for next time

3. **Launch TI-Toolbox**
   - Click "Launch TI-Toolbox"
   - The app will:
     - Check Docker availability
     - Initialize project structure (for new projects)
     - Start Docker containers
     - Launch the TI-Toolbox GUI

4. **Work with TI-Toolbox**
   - The GUI will open in a new window
   - You can minimize the launcher window
   - When you close the GUI, Docker containers will shut down automatically

### Diagnostics & Logging

- The launcher now exposes a real-time **Activity** feed so you can monitor each orchestration step (preflight checks, compose status, GUI lifecycle, etc.).
- A dedicated **Stop Session** button is available whenever the GUI is running to gracefully tear down containers.
- The path to the persistent log (`~/Library/Logs/TI-Toolbox/ti-toolbox.log` on macOS) is shown in the UI with a one-click "Show in Finder/Explorer" action for support tickets.

### Development Mode

To run the app in development mode:

```bash
npm start
```

This launches the Electron app without building distributable packages.

## Project Structure

```
package/
├── src/
│   ├── main.js          # Main process (Electron backend)
│   ├── renderer.js      # Renderer process (UI logic)
│   ├── index.html       # Main UI layout
│   └── styles.css       # Application styles
├── assets/
│   ├── icon.png         # Application icon (PNG)
│   ├── icon.icns        # macOS icon (generate from PNG)
│   └── icon.ico         # Windows icon (generate from PNG)
├── build/
│   └── entitlements.mac.plist  # macOS code signing entitlements
├── package.json         # Node.js package configuration
└── README.md           # This file
```

## Building Icons

The application requires platform-specific icon formats. You can generate these from the PNG icon:

### macOS (.icns)

```bash
# Using iconutil (macOS only)
mkdir icon.iconset
sips -z 16 16     assets/icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     assets/icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     assets/icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     assets/icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   assets/icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   assets/icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   assets/icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   assets/icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   assets/icon.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 assets/icon.png --out icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset -o assets/icon.icns
rm -rf icon.iconset
```

### Windows (.ico)

Use online converters or tools like ImageMagick:

```bash
# Using ImageMagick
convert assets/icon.png -define icon:auto-resize=256,128,64,48,32,16 assets/icon.ico
```

Or use online tools:
- https://convertio.co/png-ico/
- https://www.icoconverter.com/

## Troubleshooting

### Docker Not Running

**Error**: "Docker daemon not running. Please start Docker Desktop."

**Solution**:
- Ensure Docker Desktop is installed and running
- On macOS/Windows, check the Docker Desktop icon in the system tray
- On Linux, run `sudo systemctl start docker`

### X Server Connection Issues

**macOS**:
- Ensure XQuartz is running (`ps aux | grep XQuartz`)
- Check XQuartz preferences for "Allow connections from network clients"
- Restart XQuartz after changing settings

**Windows**:
- Ensure VcXsrv or Xming is running
- Launch with "Disable access control" option
- Check Windows Firewall settings

**Linux**:
- Run `xhost +local:docker` before launching
- Check `$DISPLAY` environment variable is set

### Permission Issues

**Linux**: If you get permission errors with Docker:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Build Issues

If you encounter errors during build:

1. Clear the cache and rebuild:
   ```bash
   rm -rf node_modules dist
   npm install
   npm run build
   ```

2. Check Node.js version (requires 18+):
   ```bash
   node --version
   ```

3. For macOS signing issues, you may need to disable code signing temporarily:
   - Remove or comment out the `entitlements` fields in `package.json`

## How It Works

1. **Project Directory Selection**: User selects or creates a project directory
2. **Docker Check**: Verifies Docker is installed and running
3. **Project Initialization**: Creates BIDS-compliant directory structure if needed
4. **Environment Setup**: Configures platform-specific environment variables
5. **Container Launch**: Starts Docker containers using `docker-compose.yml`
6. **GUI Launch**: Executes the TI-Toolbox GUI inside the SimNIBS container
7. **Cleanup**: Stops containers when GUI is closed

## Technical Details

### Technologies Used

- **Electron**: Cross-platform desktop framework
- **Node.js**: JavaScript runtime for backend logic
- **Docker**: Containerization platform
- **HTML/CSS/JavaScript**: User interface

### Docker Integration

The application:
- Reads `docker-compose.yml` from the TI-Toolbox root directory
- In packaged builds, falls back to the bundled `package/docker/docker-compose.yml`, so `TI-Toolbox.app` runs even when the repository is not present
- Respects the optional `TI_TOOLBOX_ROOT` environment variable if you need to point the launcher at a custom checkout
- Sets required environment variables (`LOCAL_PROJECT_DIR`, `PROJECT_DIR_NAME`, `DISPLAY`, etc.)
- Creates necessary Docker volumes (`ti-toolbox_freesurfer_data`)
- Starts containers using `docker compose up`
- Executes GUI using `docker exec` into the SimNIBS container
- Cleans up using `docker compose down` on exit

### Platform-Specific Handling

**macOS**:
- Detects and configures XQuartz
- Sets `DISPLAY=host.docker.internal:0`
- Configures `xhost` permissions

**Windows**:
- Sets `DISPLAY=host.docker.internal:0`
- Converts Windows paths to Docker-compatible format
- Provides guidance for X server setup

**Linux**:
- Uses native `DISPLAY` environment variable
- Configures `xhost +local:docker` permissions

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test on your platform
5. Submit a pull request

## License

See the main TI-Toolbox repository for license information.

## Support

For issues and questions:
- GitHub Issues: https://github.com/idossha/TI-Toolbox/issues
- Documentation: https://idossha.github.io/TI-Toolbox/

## Credits

**Developed by**: Center for Sleep and Consciousness
**Maintainer**: Ido Haber (ihaber@wisc.edu)

Built with Electron for cross-platform desktop deployment.
