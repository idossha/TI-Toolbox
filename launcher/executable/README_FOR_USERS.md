# TI-Toolbox - User Guide

## Quick Start

### Prerequisites
1. **Install Docker Desktop** from [https://docker.com](https://docker.com)
2. **Start Docker Desktop** and make sure it's running (whale icon in menu bar/system tray)
3. **For GUI functionality, install X server:**
   - **macOS**: XQuartz from [https://www.xquartz.org/](https://www.xquartz.org/)
   - **Windows**: VcXsrv or similar X server
   - **Linux**: X11 usually pre-installed (may need `xhost +local:docker`)
4. Have the executable file:
   - **macOS**: `TI-Toolbox.app`
- **Windows**: `TI-Toolbox.exe`
- **Linux**: `TI-Toolbox`

### How to Use

1. **Double-click** the TI-Toolbox executable
2. **Click "📋 System Requirements"** to view detailed system information and setup requirements
3. **Select your project directory** using the "Browse" button
4. **Click "❓ Help"** next to the directory field for detailed BIDS structure guide
5. **Use the toggle switch** to start Docker containers (🐋 Start → 🛑 Stop)
6. Choose your interface:
   - **🖥️ Launch CLI**: Opens a terminal with the TI-Toolbox environment (no X server needed)
   - **🖼️ Launch GUI**: Opens the graphical interface (requires X server)

### New Interface Features

#### Built-in Help System
- **System Requirements Popup**: Comprehensive system requirements, performance notes, and setup instructions
- **BIDS Structure Help**: Detailed guide for setting up your project directory structure
- **Color-coded sections**: Easy-to-read information with visual organization

#### Improved Controls
- **Toggle Switch**: Intuitive start/stop control for Docker containers
- **Status Indicator**: Real-time Docker status display (Running/Stopped)
- **Organized Layout**: Cleaner button arrangement with logical grouping
- **Enhanced Console**: Color-coded messages with better readability

#### Desktop Shortcuts 🔗
- **Create Desktop Shortcut button**: Available anytime from the main interface
- **Desktop shortcut**: Creates an icon on your desktop for easy access
- **Cross-platform**: Works on Windows, macOS, and Linux
- **Manual activation**: Click the button when you want to create the shortcut

### What Each Button Does

- **📋 System Requirements**: Opens detailed system requirements and setup information
- **🔗 Create Desktop Shortcut**: Creates a shortcut on your desktop for easy access to TI-Toolbox
- **Browse**: Select your BIDS-compliant project directory
- **❓ Help**: Shows BIDS directory structure guide
- **🐋 Start Docker Containers / 🛑 Stop Docker Containers**: Toggle switch for container management
- **🖥️ Launch CLI**: Opens a terminal window connected to the TI-Toolbox environment
- **🖼️ Launch GUI**: Launches the TI-Toolbox graphical interface
- **🗑️ Clear**: Clears the output messages in the launcher console

### Platform-Specific Notes

#### macOS
- **File**: `TI-Toolbox.app`
- **Launch**: Double-click the app - no terminal window will appear
- **First run**: Right-click → Open → Open (to bypass security warnings)
- **X server**: Install XQuartz for GUI functionality
- **Performance**: Optimized for Apple Silicon and Intel Macs

#### Windows  
- **File**: `TI-Toolbox.exe`
- **Launch**: Double-click the executable - launches directly to GUI
- **Antivirus**: Some antivirus may warn about unknown executable (false positive)
- **X server**: Install VcXsrv or similar for GUI functionality

#### Linux
- **File**: `TI-Toolbox` 
- **Launch**: Double-click or run from terminal
- **Permissions**: May need to make executable: `chmod +x TI-Toolbox`
- **X server**: Usually pre-installed, may need `xhost +local:docker`

### Troubleshooting

**"Docker is not running"**
- Make sure Docker Desktop is installed and running
- Look for the Docker whale icon in your system tray/menu bar
- Wait for Docker to fully start before launching TI-Toolbox

**Permission denied (macOS/Linux)**
- Right-click the executable → Properties → Permissions → Check "Execute"
- Or run in terminal: `chmod +x TI-Toolbox`

**The executable won't open (macOS)**
- Right-click → Open → Open (this bypasses Gatekeeper warnings)
- Or go to System Preferences → Security & Privacy → Allow the app

**Windows Defender/Antivirus warnings**
- This is a false positive common with PyInstaller executables
- Add exception or temporarily disable real-time protection during first run

**GUI won't launch but CLI works**
- Check that you have the X server installed and running:
  - macOS: XQuartz must be installed and running
  - Windows: VcXsrv or similar must be configured
  - Linux: X11 should be available, try `xhost +local:docker`
- Check the console output in the launcher for X11 error messages

**Nothing happens when clicking Launch buttons**
- Check the console output in the launcher for error messages
- Make sure the containers started successfully (toggle shows "Running")
- Try stopping and restarting the containers

**Docker containers won't start**
- Ensure Docker Desktop has finished starting up completely
- Check available disk space (needs ~30GB for images)
- Verify you have sufficient RAM (32GB+ recommended)

### System Requirements

- **Operating System**: Windows 10+, macOS 10.14+, or modern Linux
- **Docker Desktop**: Latest version recommended  
- **RAM**: 32GB+ minimum for full functionality
- **Storage**: At least 30GB free space for Docker images
- **X Server (GUI only)**: 
  - macOS: XQuartz
  - Windows: VcXsrv or similar
  - Linux: X11 (usually pre-installed)

### Project Structure Requirements

TI-Toolbox follows BIDS (Brain Imaging Data Structure) conventions. Use the built-in **❓ Help** button for a comprehensive guide, but in summary:

```
Project Directory/
├── sourcedata/          (Required: Set up by user)
│   └── sub-{subject}/
│       ├── T1w/
│       │   └── dicom/   (Place T1w DICOM files here)
│       └── T2w/         (Optional)
│           └── dicom/   (Place T2w DICOM files here)
├── sub-{subject}/       (Auto-created during preprocessing)
├── derivatives/         (Auto-created during processing)
└── ti-toolbox/             (Auto-created at first launch)
```

### Performance Notes

Based on your hardware:
- **FreeSurfer Processing**: 2-8 hours per subject
- **SimNIBS Mesh Generation**: ~60 minutes per subject  
- **TI Simulations**: ~10 minutes per montage
- **Optimization Algorithms**: Variable (minutes to hours)
- **First-time Setup**: 10-15 minutes to download ~30GB of Docker images
- **Subsequent Launches**: Fast (seconds) startup as images are cached

### Getting Help

The launcher now includes comprehensive built-in help:

1. **Click "📋 System Requirements"** for detailed system and performance information
2. **Click "❓ Help"** for BIDS directory structure guidance
3. **Check console output** for real-time status and error messages

If you still encounter issues:
1. Try stopping and restarting the containers using the toggle switch
2. Restart Docker Desktop and wait for full startup
3. Contact your system administrator with specific error messages from the console

### Advanced Features

- **Enhanced Docker Detection**: Automatically finds Docker in common installation locations
- **Intelligent Error Handling**: Clear error messages with suggested solutions  
- **Color-coded Console**: Visual feedback for different types of messages
- **Anti-double-click Protection**: Prevents accidental multiple launches
- **Comprehensive Logging**: Detailed status information for troubleshooting

---

**Happy computing! 🚀** 

*TI-Toolbox: Temporal Interference Computational Stimulation Consortium* 