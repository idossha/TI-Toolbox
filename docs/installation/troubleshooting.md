---
layout: installation
title: Troubleshooting
permalink: /installation/troubleshooting/
---

Comprehensive troubleshooting guide for TI Toolbox installation and usage issues.

## Common Installation Issues

### Security and Permissions

#### macOS: "Cannot be opened because the developer cannot be verified"
**Solution:**
1. Use Terminal quarantine removal method:
   ```bash
   sudo xattr -r -d com.apple.quarantine TemporalInterferenceToolbox-macOS-universal.zip
   ```
2. Or right-click the app and select "Open" (instead of double-clicking)
3. Check System Preferences > Security & Privacy for blocked apps

#### Windows: "Windows protected your PC"
**Solution:**
1. Click "More info" when you see the warning
2. Click "Run anyway"
3. Run installer as administrator (right-click > "Run as administrator")

#### Windows: Antivirus blocking execution
**Solution:**
1. Temporarily disable real-time protection
2. Add TI Toolbox to antivirus exclusions
3. Check Windows Defender quarantine and restore if needed

#### Linux: Permission denied
**Solution:**
```bash
# Make AppImage executable
chmod +x TemporalInterferenceToolbox-Linux-x86_64.AppImage

# Or add user to docker group
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

### Download Issues

#### Browser blocking download
**Solution:**
- **Chrome/Edge**: Click "..." on download warning > "Keep" > "Keep anyway"
- **Firefox**: Click on download arrow > right-click file > "Allow download"
- **Safari**: Download will appear in Downloads folder with quarantine


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
1. Open Docker Desktop settings
2. Go to Resources
3. Allocate:
   - **Memory**: 32GB minimum (64GB recommended)
4. Apply and restart Docker

### Docker images not downloading
**Symptoms:** Stuck at "Pulling image" or network timeouts

**Solution:**
1. Check internet connection
2. Restart Docker Desktop
3. Clear Docker cache:
   ```bash
   docker system prune -a
   ```
4. Try manual pull:
   ```bash
   docker pull idossha/simnibs:latest
   ```

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

### No GUI appears (Windows)
**Solution:**
1. Ensure VcXsrv is running (check system tray)
2. Verify VcXsrv configuration:
   - Multiple windows
   - Start no client
   - **"Disable access control" MUST be checked**
3. Restart VcXsrv if needed
4. Check Windows Firewall isn't blocking VcXsrv

## Application-Specific Issues

### Memory Issues
**Symptoms:** "Out of memory" errors during processing

**Solutions:**
1. Increase Docker memory allocation
2. Close other applications
3. Process smaller datasets

## Network and Connectivity

### Slow Docker image downloads
**Solution:**
1. Use wired internet connection
2. Close other bandwidth-intensive applications
3. Try downloading during off-peak hours

### macOS Apple Silicon Issues
**Symptoms:** Performance issues or compatibility errors

**Solution:**
1. Ensure Docker Desktop supports Apple Silicon
2. Install Rosetta 2 if prompted:
   ```bash
   softwareupdate --install-rosetta
   ```
3. Check Docker Desktop settings for architecture

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