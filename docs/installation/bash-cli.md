---
layout: installation
title: Bash/CLI Usage
permalink: /installation/bash-cli/
---

Alternative command-line installation and usage guide for the TI Toolbox.

## Overview

You do **not** have to use the graphical executables to run the TI Toolbox! The executables simply provide a GUI for the launcher program. The bash script method gives you the same core functionality in a terminal-based interface.

## When to Use Bash/CLI Method

- **Remote servers** (no GUI available)
- **Command-line workflows** preference
- **Automation** and scripting

## Prerequisites

### Required Dependencies
- **Docker**: [Docker Engine](https://docs.docker.com/engine/install/) (Linux)


## Installation Steps

### Step 1: Download Required Files

Download these two files from the [TI Toolbox GitHub Releases](https://github.com/idossha/TI-Toolbox/releases):

1. `launcher/bash/loader.sh` - Main launcher script
2. `launcher/bash/docker-compose.yml` - Docker configuration

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
# Try enter the pre-processing tool
pre-process

# Try start the flex-search tool
flex-search
```

If these manage to load the CLI you are good to go!
