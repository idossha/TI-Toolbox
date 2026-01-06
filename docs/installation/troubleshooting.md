---
layout: installation
title: Troubleshooting
permalink: /installation/troubleshooting/
---
---

## Docker Issues

### Docker not running
**Symptoms:** "Docker daemon not running" or "Cannot connect to Docker"

**Solution:**
- **Windows/macOS**: Start Docker Desktop and wait for green status
- **Linux**: 
  ```bash
  sudo systemctl start docker
  sudo systemctl enable docker
  ```

### Insufficient resources
**Symptoms:** Slow performance, out of memory errors, failed simulations

**Solution:**
1. Open Docker Desktop settings -> Go to Resources
2. Allocate: **Memory**: 32GB minimum
3. Apply and restart Docker

### Docker images not downloading
**Symptoms:** Stuck at "Pulling image" or network timeouts

**Solution:**
1. Check internet connection
2. Restart Docker Desktop
3. Try manual pull:
   ```bash
   docker pull idossha/simnibs:{version}
   ```

### New version image pulling
Every time a new version of TI-Toolbox is released, the updated Docker image needs to be pulled from Docker Hub. This is a normal process that occurs automatically when you first run a new version.

![New Version Image Pulling]({{ site.baseurl }}/assets/imgs/installation/new_version_pulling.png)
*Figure: Docker Desktop showing the image pulling process for a new TI-Toolbox version*

**What happens:**
- Docker downloads the latest container image from Docker Hub
- This may take several minutes depending on your internet connection speed
- Progress is shown in Docker Desktop or the application logs
- The image size is typically 5-10GB depending on the version

**Subsequent runs:**
- Once downloaded, the image is cached locally
- Future runs of the same version will start much faster
- You only need to download each version once

**To manually pull the latest image:**
```bash
docker pull idossha/simnibs:latest
```

**If the download seems slow:**
1. Check your internet connection speed
2. Use a wired connection if possible
3. Try during off-peak hours
4. Ensure you have at least 20GB of free disk space

---

## GUI Display Issues

### No GUI appears (Linux)
**Solution:**
```bash
# Allow Docker to access X11
xhost +local:docker

# Check DISPLAY variable
echo $DISPLAY

# If empty, set manually
export DISPLAY=:0
```

### No GUI appears (macOS)
**Solution:**
1. Ensure [XQuartz 2.7.7] is installed (not newer versions)
2. Log out and back in after XQuartz installation
3. Launch XQuartz from Applications > Utilities
4. Check XQuartz preferences: Allow connections from network clients

If still running into issues, download the **[config_sys.sh](https://github.com/idossha/TI-toolbox/blob/main/dev/bash_dev/config_sys.sh)** place it next to your loader.sh, and run it:

```bash
bash config_sys.sh
```

### No GUI appears (Windows)
**Solution:**
1. Ensure VcXsrv is running (check system tray)
2. Verify VcXsrv configuration:
   - Multiple windows
   - Start no client
   - **"Disable access control" MUST be checked**
3. Restart VcXsrv if needed
4. Check Windows Firewall isn't blocking VcXsrv  

<br>

---

## Getting Help

### Information to Include
When reporting issues, include:

1. **System Information:**
   - OS version
   - Docker version
   - Available RAM/storage
   - X server version (XQuartz/VcXsrv)

2. **Error Details:**
   - Exact error messages
   - Steps to reproduce
   - When the error occurs
   - Screenshot if applicable

3. **Log Files:**
   - Docker logs: `docker logs [container_name]`
   - Application logs from output directory
   - System logs if relevant

### Where to Get Help

1. **[GitHub Issues](https://github.com/idossha/TI-Toolbox/issues)** - Search existing issues first
2. **[GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)** - Community support
3. **Documentation** - Check other installation guides for platform-specific help

### Diagnostic Commands

Run these commands to gather system information:

```bash
# System information
uname -a
docker --version
docker info

# Docker status
docker ps
docker images

# Display information
echo $DISPLAY
xhost  # Linux/macOS only

# Resource usage
free -h  # Linux
top      # All platforms
```