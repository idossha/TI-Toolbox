# Windows GUI Setup Guide for TI-CSC Toolbox

## Overview

The TI-CSC Toolbox GUI on Windows requires an **X11 server** to display Linux-based graphical applications from the Docker container. This guide will help you set up everything needed for GUI functionality.

## Quick Setup (Recommended)

### Step 1: Install VcXsrv (Recommended X11 Server)

1. **Download VcXsrv**
   - Visit: https://sourceforge.net/projects/vcxsrv/
   - Download the latest installer

2. **Install VcXsrv**
   - Run the installer with default settings
   - No special configuration needed during installation

3. **Configure and Launch VcXsrv**
   - Launch "XLaunch" from the Start Menu
   - **Configuration options:**
     - Display settings: Select "Multiple windows"
     - Client startup: Select "Start no client"
     - Extra settings: **CHECK "Disable access control"** (Important!)
   - Click "Finish"
   - XLaunch will start and show an icon in the system tray

### Step 2: Test Your Setup

Run the test script to verify everything is working:

```bash
python test_x11_windows.py
```

This script will check:
- X11 server processes (VcXsrv/Xming)
- Network ports (6000-6010)
- Docker installation
- Overall readiness

### Step 3: Launch TI-CSC

1. Open the TI-CSC Launcher
2. Select your project directory
3. Start Docker containers
4. Click "Launch GUI" - it should now work!

## Alternative X11 Server: Xming

If you prefer Xming over VcXsrv:

1. **Download Xming**
   - Visit: https://xming.en.softonic.com/
   - Or search for "Xming" in your browser

2. **Install and Run**
   - Install with default settings
   - Launch Xming (it will run in the background)

## Troubleshooting

### Problem: "No X11 server detected"

**Solution:**
1. Ensure VcXsrv or Xming is running (check system tray)
2. If using VcXsrv, make sure "Disable access control" was checked
3. Try restarting the X11 server
4. Run the test script to diagnose the issue

### Problem: GUI launches but shows black screen or errors

**Possible causes:**
1. **Access control enabled**: In VcXsrv, ensure "Disable access control" is checked
2. **Firewall blocking**: Temporarily disable Windows Firewall to test
3. **Display settings**: Try different VcXsrv display settings

**Solution:**
1. Restart VcXsrv with correct settings
2. Check Windows Firewall exceptions for VcXsrv
3. Try launching from CLI first: Click "Launch CLI" then type `GUI` in the terminal

### Problem: "Docker not found" or "Docker daemon not running"

**Solution:**
1. Install Docker Desktop: https://www.docker.com/products/docker-desktop/
2. Start Docker Desktop and wait for it to fully initialize
3. Restart the TI-CSC Launcher

### Problem: CLI works but GUI doesn't

This usually indicates an X11 server issue:

1. **Verify X11 server is running:**
   ```cmd
   tasklist | findstr vcxsrv
   tasklist | findstr Xming
   ```

2. **Check network connectivity:**
   ```cmd
   netstat -an | findstr :6000
   ```

3. **Try manual GUI launch:**
   - Click "Launch CLI"
   - In the container terminal, type: `GUI`
   - Look for specific error messages

## Advanced Configuration

### VcXsrv Command Line Launch

For advanced users, you can launch VcXsrv from command line:

```cmd
"C:\Program Files\VcXsrv\vcxsrv.exe" :0 -multiwindow -clipboard -wgl -ac
```

Parameters:
- `:0` - Display number
- `-multiwindow` - Multiple windows mode
- `-clipboard` - Enable clipboard sharing
- `-wgl` - Enable OpenGL
- `-ac` - Disable access control (important!)

### Setting DISPLAY Environment Variable

Normally not needed, but if you want to set it manually:

```cmd
set DISPLAY=localhost:0.0
```

Or in PowerShell:
```powershell
$env:DISPLAY = "localhost:0.0"
```

## Security Considerations

**Important:** The "Disable access control" setting in VcXsrv allows any application to connect to your X11 server. This is necessary for Docker containers but reduces security.

**Recommendations:**
1. Only run VcXsrv when using TI-CSC
2. Use a firewall to limit network access
3. Don't use this setup on public networks

## Performance Tips

1. **Close unnecessary applications** when running GUI-intensive operations
2. **Allocate more RAM to Docker** in Docker Desktop settings
3. **Use SSD storage** for Docker volumes if possible
4. **Enable hardware acceleration** in VcXsrv if supported

## Getting Help

If you continue to have issues:

1. **Run the test script** and save the output
2. **Check the TI-CSC console** for detailed error messages
3. **Try CLI first** to isolate Docker vs X11 issues
4. **Check Docker Desktop logs** for container issues

## File Structure Reference

After setup, your system should have:

```
Windows System:
├── VcXsrv installed in Program Files
├── Docker Desktop running
└── TI-CSC Launcher executable

TI-Toolbox Project Directory:
├── Your BIDS data
├── ti-toolbox/ (created automatically)
│   └── config/ (configuration files)
└── sourcedata/.ti-toolbox-info/ (hidden, system information)
```

## Common VcXsrv Configuration

**Recommended XLaunch settings:**
- Display settings: "Multiple windows"
- Session type: "Start no client"
- Extra settings: 
  - ✅ Clipboard
  - ✅ Primary Selection  
  - ✅ Native opengl
  - ✅ **Disable access control** (Critical!)

Save this configuration for future use by clicking "Save configuration" in XLaunch.

---

**Need more help?** Check the main TI-CSC documentation or run the test script for automated diagnostics. 