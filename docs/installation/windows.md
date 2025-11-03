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

## Troubleshooting

### VcXsrv Issues
- Verify "Disable access control" is checked
- Restart VcXsrv if GUI doesn't appear

### Docker Issues
- Ensure Docker Desktop is running before launching TI Toolbox
- Check WSL 2 is enabled and updated
- Verify sufficient disk space and memory allocation

![Docker Settings on Windows]({{ site.baseurl }}/assets/imgs/installation_docker_windows.png){:style="max-width: 800px;"}


---

**Next Steps**: 
- [Dependencies](../dependencies/) - If you need to revisit dependency setup
- [Troubleshooting](../troubleshooting/) - For common issues and solutions
- [Quick Start](../) - Return to main installation guide 