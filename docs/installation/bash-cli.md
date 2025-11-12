---
layout: installation
title: Bash Entrypoint
permalink: /installation/bash-cli/
---


## Installation Steps

### Step 1: Download Required Files

**Download the required files:**
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)** - Main launch script
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)** - Docker configuration

## Usage

### Basic Launch

```bash
# Run the script
bash loader.sh

# Or if made executable
./loader.sh
```

The script will guide you through:

1. **Environment Detection**
   - Checks Docker availability
   - Verifies system requirements
   - Detects platform (Linux/macOS/Windows)

2. **Configuration Setup**
   - BIDS dataset path selection
   - Output directory configuration
   - Resource allocation

3. **Docker Management**
   - Downloads Docker images (first run)
   - Starts containers
   - Manages environment variables

When loader program completed:

```bash
#Try ebter the core GUI tool
GUI

# Try enter the pre-processing tool
pre-process

# Try start the flex-search tool
flex-search
```

If these manage to load the CLI you are good to go!
