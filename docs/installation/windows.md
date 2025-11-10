---
layout: installation
title: Windows Installation
permalink: /installation/windows/
---

## Prerequisites

### Ubuntu from Microsoft Store

1. **Install Ubuntu from Microsoft Store**:
   - Search for "Ubuntu" in the Microsoft Store
   - Install the latest Ubuntu version (this automatically sets up WSL2)
2. **Launch Ubuntu** from Start Menu and complete initial setup
3. **Update Ubuntu** (first time setup):
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

### Docker Desktop Integration
1. **Install Docker Desktop** for Windows
2. **Enable Ubuntu integration**:
   - Open Docker Desktop settings
   - Go to "Resources" > "WSL Integration"
   - Enable integration with your Ubuntu distribution

![Docker Settings on Windows]({{ site.baseurl }}/assets/imgs/installation_docker_windows.png){:style="max-width: 800px;"}

3. **Restart Docker Desktop** after enabling integration

### X Server for GUI
Install [VcXsrv](https://sourceforge.net/projects/vcxsrv/) for GUI display:
- Download and install VcXsrv

---

## Setup Steps

### Step 1: Download Required Files

Download these files to your **Windows filesystem**:
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)**
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)**

**Recommended**: Create a dedicated folder like `C:\TI-Toolbox\` for these files.

### Step 2: Launch from Ubuntu

1. **Open Ubuntu** (search for "Ubuntu" in Windows Start menu)
2. **Navigate to your files** using WSL path format:
   ```bash
   cd /mnt/c/TI-Toolbox/
   ```
   *(Note: Windows `C:\TI-Toolbox\` becomes `/mnt/c/TI-Toolbox/` in WSL)*
3. **Make loader.sh executable**:
   ```bash
   chmod +x loader.sh
   ```
4. **Ensure Docker Desktop is running** on Windows
5. **Launch TI-Toolbox**:
   ```bash
   ./loader.sh
   ```
6. **First run will download Docker images (~30GB)** - this may take 30+ minutes

## File Mounting Considerations

### Accessing Windows Files from Ubuntu
- Windows drives are mounted under `/mnt/` in Ubuntu
- `C:\Users\YourName\Desktop\` → `/mnt/c/Users/YourName/Desktop/`
- Use Ubuntu paths when running commands in the terminal

### Project Data Location
- Store your TI-Toolbox project data in your Windows filesystem
- Access via Ubuntu paths (e.g., `/mnt/c/{project-name}`)
- Docker containers will inherit Ubuntu's access to Windows files

## Troubleshooting

### Docker Integration Issues
- **WSL integration not enabled**: Check Docker Desktop settings under "Resources" > "WSL Integration"
- **Docker daemon not accessible**: Restart Docker Desktop and ensure WSL integration is active

### X Server (VcXsrv) Issues
- **GUI not appearing**: Ensure VcXsrv is running and "Disable access control" is checked
- **Connection refused**: Configure VcXsrv to allow connections from WSL2 (default settings usually work)


---

**Next Steps**:
- [Dependencies](../dependencies/) - If you need to revisit dependency setup
- [Troubleshooting](../troubleshooting/) - For common issues and solutions
- [Quick Start](../) - Return to main installation guide 