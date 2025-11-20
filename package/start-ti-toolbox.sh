#!/bin/bash

###########################################
# TI-Toolbox Desktop App Launcher
###########################################

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

echo -e "${BLUE}Starting TI-Toolbox Desktop Application...${RESET}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Platform-specific setup
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}Setting up macOS environment...${RESET}"
    
    # Check if XQuartz is installed
    if [ ! -d "/Applications/Utilities/XQuartz.app" ] && [ ! -d "/Applications/XQuartz.app" ]; then
        echo -e "${RED}XQuartz is not installed!${RESET}"
        echo "Please install XQuartz from: https://www.xquartz.org/"
        echo "After installation, log out and log back in."
        exit 1
    fi
    
    # Start XQuartz if not running
    if ! pgrep -x "XQuartz" > /dev/null; then
        echo "Starting XQuartz..."
        open -a XQuartz
        sleep 3
    fi
    
    # Set DISPLAY if not set
    if [ -z "$DISPLAY" ]; then
        export DISPLAY=:0
        echo "Set DISPLAY=$DISPLAY"
    fi
    
    # Allow localhost connections
    if command -v xhost &> /dev/null; then
        xhost +localhost > /dev/null 2>&1 || true
        xhost +local: > /dev/null 2>&1 || true
        echo "Configured X11 access permissions"
    fi
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker is not running!${RESET}"
    echo "Please start Docker Desktop and try again."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo ""
        echo "Opening Docker Desktop..."
        open -a Docker
        echo "Please wait for Docker to start and run this script again."
    fi
    exit 1
fi

echo -e "${GREEN}✓ Docker is running${RESET}"

# Check if app is built
if [[ "$OSTYPE" == "darwin"* ]]; then
    APP_PATH="$SCRIPT_DIR/dist/mac/TI-Toolbox.app"
    if [ -d "$APP_PATH" ]; then
        echo ""
        echo -e "${GREEN}Launching TI-Toolbox...${RESET}"
        open "$APP_PATH"
    else
        echo -e "${YELLOW}App not found. Building...${RESET}"
        cd "$SCRIPT_DIR"
        npm run build:mac
        echo -e "${GREEN}Build complete. Launching...${RESET}"
        open "$APP_PATH"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    APP_PATH=$(find "$SCRIPT_DIR/dist" -name "*.AppImage" -type f | head -1)
    if [ -f "$APP_PATH" ]; then
        echo ""
        echo -e "${GREEN}Launching TI-Toolbox...${RESET}"
        "$APP_PATH"
    else
        echo -e "${YELLOW}App not found. Building...${RESET}"
        cd "$SCRIPT_DIR"
        npm run build:linux
        APP_PATH=$(find "$SCRIPT_DIR/dist" -name "*.AppImage" -type f | head -1)
        echo -e "${GREEN}Build complete. Launching...${RESET}"
        "$APP_PATH"
    fi
else
    echo -e "${RED}Unsupported platform: $OSTYPE${RESET}"
    exit 1
fi
