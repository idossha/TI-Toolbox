# TI-CSC - Build Instructions

This guide will help you create cross-platform executables for TI-CSC that your colleagues can simply double-click to run.

## Prerequisites

### All Platforms
- **Python 3.8 or higher** (3.9+ recommended)
- **pip** (usually comes with Python)
- **Docker Desktop** (must be installed on target machines)

### Platform-Specific Requirements

#### macOS
- Xcode Command Line Tools: `xcode-select --install`
- For code signing (optional): Apple Developer account
- XQuartz for GUI functionality: https://www.xquartz.org/

#### Windows
- Microsoft Visual C++ 14.0 or greater (usually comes with Visual Studio)
- Windows 10 or higher recommended
- VcXsrv or similar X server for GUI functionality

#### Linux
- Build tools: `sudo apt-get install build-essential` (Ubuntu/Debian)
- GTK development libraries: `sudo apt-get install libgtk-3-dev`
- X11 usually pre-installed (may need `xhost +local:docker` for GUI)

## Quick Start

### Option 1: Automated Build (Recommended)

1. **Navigate to the project directory:**
   ```bash
   cd launcher/executable/
   ```

2. **Run the build script:**
   ```bash
   python build.py
   ```

The script will:
- Install all required dependencies
- Build the executable using PyInstaller
- Show you where the final executable is located

### Option 2: Manual Build

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. **Build the executable:**
   ```bash
   pyinstaller ti_csc_launcher.spec --clean
   ```

## Output Files

After building, you'll find the executable in the `dist/` folder:

### macOS
- **App Bundle:** `dist/TI-CSC.app` ✅ **RECOMMENDED FOR DISTRIBUTION**
- **Raw Executable:** `dist/TI-CSC` (may show terminal window)

### Windows
- **Executable:** `dist/TI-CSC.exe` ✅ **CLEAN GUI LAUNCH**

### Linux
- **Executable:** `dist/TI-CSC`

## New Features (Latest Version)

### Enhanced User Interface
- **Professional popup dialogs** with system requirements and BIDS structure help
- **Intuitive toggle switch** for Docker containers (green start 🐋, red stop 🛑)
- **Improved layout** with organized button placement
- **System requirements popup** instead of always-visible text
- **Comprehensive help system** for BIDS directory structure

### Updated System Requirements
- **RAM:** 32GB+ minimum for full functionality
- **Storage:** ~30GB for Docker images (updated from 8GB)
- **X11 forwarding** requirements clearly documented for GUI usage
- **Platform-specific X server** instructions (XQuartz, VcXsrv, etc.)

### Improved Functionality
- **Better Docker detection** with enhanced path searching
- **Professional error handling** and user feedback
- **Enhanced CLI and GUI launchers** with anti-double-click protection
- **Cleaner console output** with color-coded messages
- **Toggle-style Docker controls** instead of separate start/stop buttons

## Distribution

### For Colleagues on the Same Platform
Simply share the appropriate file:

**macOS Users:**
- Share: `TI-CSC.app` (the entire app bundle)
- ✅ No terminal window, clean GUI launch
- Recipients: Install Docker Desktop + XQuartz → Double-click app

**Windows Users:**  
- Share: `TI-CSC.exe`
- ✅ No console window, direct GUI launch
- Recipients: Install Docker Desktop + VcXsrv → Double-click exe

**Linux Users:**
- Share: `TI-CSC` (make sure permissions are set)
- Recipients: Install Docker → Run executable

### For Cross-Platform Distribution
Build on each target platform:
1. **Windows:** Build on Windows machine → share `.exe`
2. **macOS:** Build on Mac → share `.app` bundle
3. **Linux:** Build on Linux → share executable

### Automated Packaging
Use the packaging script to create distribution-ready folders:
```bash
python package_for_distribution.py
```

This creates a timestamped folder with:
- The appropriate executable for your platform
- Updated user documentation
- Quick start instructions
- System requirements information

## Advanced Configuration

### Adding an Icon
1. Create icon files:
   - Windows: `.ico` file
   - macOS: `.icns` file
   - Linux: `.png` file

2. Update `ti_csc_launcher.spec`:
   ```python
   exe = EXE(
       # ... other parameters ...
       icon='path/to/your/icon.ico',  # or .icns for macOS
   )
   ```

### Code Signing (macOS)
For distribution outside the App Store:
```bash
# Sign the app
codesign --deep --force --verify --verbose --sign "Developer ID Application: Your Name" dist/TI-CSC.app

# Create a notarized DMG (optional)
hdiutil create -volname "TI-CSC" -srcfolder dist/TI-CSC.app -ov -format UDZO TI-CSC.dmg
```

### Windows Code Signing
Use a code signing certificate:
```bash
signtool sign /f your-certificate.p12 /p password dist/TI-CSC.exe
```

## Troubleshooting

### Common Issues

**"Permission denied" on macOS/Linux:**
```bash
chmod +x dist/TI-CSC
```

**Missing Qt plugins:**
If you get Qt-related errors, try:
```bash
pip install --upgrade PyQt6 PyQt6-Qt6
pyinstaller ti_csc_launcher.spec --clean --onefile
```

**Large file size:**
The executable includes Python and all dependencies (~28-35MB). This is normal for PyInstaller builds.

**Antivirus false positives:**
Some antivirus software may flag PyInstaller executables. This is a common false positive.

### Build Optimization

For smaller executables:
```python
# In ti_csc_launcher.spec, add excludes:
excludes=[
    'tkinter',
    'matplotlib',
    'numpy',
    'pandas',
    # Add other unused modules
]
```

## Testing

Before distributing:

1. **Test on clean machine:** Ensure the executable works without Python installed
2. **Test Docker integration:** Verify Docker commands work correctly
3. **Test all features:** CLI launch, GUI launch, container management
4. **Test popup dialogs:** Verify system requirements and help popups display correctly
5. **Test toggle controls:** Ensure Docker start/stop toggle works properly
6. **Test X11 forwarding:** Verify GUI functionality works with X server setup

## Deployment Checklist

- [ ] Executable builds successfully
- [ ] Tested on target platform
- [ ] Docker Desktop requirement documented
- [ ] X11 forwarding requirements documented
- [ ] Icon added (optional)
- [ ] Code signed (optional, for professional distribution)
- [ ] Updated README for end users created
- [ ] Distribution package prepared
- [ ] System requirements popup tested
- [ ] Help dialogs tested

## End User Instructions

The launcher now includes built-in help and system requirements popups, making it much easier for end users to understand what they need. Create a simple instruction file for your colleagues:

```
TI-CSC - Quick Start

Prerequisites:
1. Install Docker Desktop from https://docker.com
2. For GUI functionality, install X server:
   - macOS: XQuartz (https://www.xquartz.org/)
   - Windows: VcXsrv
   - Linux: Usually pre-installed

Usage:
1. Double-click TI-CSC application
2. Click "📋 System Requirements" for detailed system info
3. Select project directory and click "❓ Help" for BIDS structure guide
4. Use the toggle switch to start/stop Docker containers
5. Launch CLI or GUI as needed

The application now includes comprehensive built-in help!
```

## Version History

### Latest Version Features:
- Professional popup dialogs with rich HTML formatting
- Toggle-style Docker controls with visual feedback
- Enhanced system requirements documentation
- Comprehensive BIDS structure help
- Improved error handling and user feedback
- Better Docker detection and path management
- Updated to reflect ~30GB download size
- Clear X11 forwarding requirements documentation

## Summary

✅ **What you built:**
- Clean, terminal-free executables for macOS and Windows
- Self-contained apps with all dependencies included
- Enhanced Docker detection for app bundle compatibility

✅ **What to distribute:**
- **macOS**: `TI-CSC.app` (entire app bundle)
- **Windows**: `TI-CSC.exe`
- **Linux**: `TI-CSC` executable

✅ **What users need:**
- Docker Desktop installed and running
- Just double-click your executable!

---

**Happy building! 🚀** 