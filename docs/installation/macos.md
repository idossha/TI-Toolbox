---
layout: installation
title: macOS Installation
permalink: /installation/macos/
---

## Prerequisites

### Docker Desktop
1. **Install Docker Desktop** for Mac from [docker.com](https://www.docker.com/products/docker-desktop/)
2. **Start Docker Desktop** and ensure it's running (green indicator in menu bar)

### X Server for GUI
Install [XQuartz 2.7.7](https://www.xquartz.org/) for GUI display:
- Download and install XQuartz version 2.7.7 from the official website
- Log out and back in (or restart) after installation

## Setup Steps

### Step 1: Download Required Files

Download these files to your preferred location (e.g., `~/TI-Toolbox/`):
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)**
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)**

### Step 2: Launch TI-Toolbox

1. **Open Terminal** (Applications > Utilities > Terminal)
2. **Navigate to your download location**:
   ```bash
   cd ~/TI-Toolbox/
   ```
3. **Make loader.sh executable**:
   ```bash
   chmod +x loader.sh
   ```
4. **Launch TI-Toolbox**:
   ```bash
   ./loader.sh
   ```
5. **First run will download Docker images (~30GB)** - this may take 30+ minutes

## macOS-Specific Features

### Apple Silicon Compatibility
- Docker Desktop automatically handles architecture differences between Intel and Apple Silicon
- Some performance differences may occur between architectures
- All TI-Toolbox features work on both architectures


![Docker Settings on Apple]({{ site.baseurl }}/assets/imgs/installation/docker_apple.png){:style="max-width: 800px;"}
