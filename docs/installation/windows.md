---
layout: installation
title: Windows Installation
permalink: /installation/windows/
---

## Step 1: Download TI Toolbox

1. Go to the [Releases Page]({{ site.baseurl }}/releases/)
2. Download the Windows `.exe` installer

### Handle Browser Security Warnings
If Edge/Chrome blocks the download:
1. Click the "..." menu on the download warning
2. Select "Keep" > "Keep anyway"

## Step 2: First Run

1. Ensure Docker Desktop is running
2. Start VcXsrv (if not already running)
3. Launch TI Toolbox from Start Menu or desktop shortcut
4. **First run will download Docker images (~30GB)**
   - This process may take 30+ minutes
   - Progress will be shown in the application
   - Images are cached for future use

## Windows-Specific Features

### Path Handling
- TI Toolbox automatically converts Windows backslashes to forward slashes
- Paths with spaces are automatically quoted
- Use forward slashes in configuration files when possible

### X11 Display
- DISPLAY variable is automatically configured
- Host IP is detected automatically for WSL2/Docker communication

## Troubleshooting

### "This app can't run on your PC"
- Ensure you downloaded the correct version for your system architecture
- Try running as administrator
- Check if you have the latest Windows updates

### VcXsrv Issues
- Verify "Disable access control" is checked
- Restart VcXsrv if GUI doesn't appear
- Check Windows Firewall isn't blocking VcXsrv

### Docker Issues
- Ensure Docker Desktop is running before launching TI Toolbox
- Check WSL 2 is enabled and updated
- Verify sufficient disk space and memory allocation

### Permission Errors
- Always run installer as administrator
- Check antivirus software isn't blocking the application
- Temporarily disable real-time protection during installation

## Security Best Practices

1. **Re-enable protections** after installation
2. **Add TI Toolbox to antivirus exclusions** if needed
3. **Only download from official sources**
4. **Keep Windows and Docker Desktop updated**

## BIDS Path Guide

For working with BIDS datasets on Windows, see our comprehensive [Windows BIDS Path Guide](https://github.com/idossha/TI-Toolbox/blob/main/launcher/WINDOWS_BIDS_PATH_GUIDE.md) for handling path formatting and common issues.

---

**Next Steps**: 
- [Dependencies](../dependencies/) - If you need to revisit dependency setup
- [Troubleshooting](../troubleshooting/) - For common issues and solutions
- [Quick Start](../) - Return to main installation guide 