#!/bin/bash

###########################################
# TI-Toolbox Desktop App Build Script
###########################################

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

echo -e "${BLUE}"
echo "╔════════════════════════════════════════╗"
echo "║  TI-Toolbox Desktop App Builder       ║"
echo "╚════════════════════════════════════════╝"
echo -e "${RESET}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js is not installed.${RESET}"
    echo "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

echo -e "${GREEN}✓ Node.js version: $(node --version)${RESET}"

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo -e "${RED}Error: npm is not installed.${RESET}"
    exit 1
fi

echo -e "${GREEN}✓ npm version: $(npm --version)${RESET}"
echo ""

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing dependencies...${RESET}"
    npm install
    echo -e "${GREEN}✓ Dependencies installed${RESET}"
    echo ""
else
    echo -e "${GREEN}✓ Dependencies already installed${RESET}"
    echo ""
fi

# Detect platform
PLATFORM=$(uname -s)
case "$PLATFORM" in
    Darwin*)
        DETECTED_PLATFORM="macOS"
        BUILD_CMD="build:mac"
        ;;
    Linux*)
        DETECTED_PLATFORM="Linux"
        BUILD_CMD="build:linux"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        DETECTED_PLATFORM="Windows"
        BUILD_CMD="build:win"
        ;;
    *)
        DETECTED_PLATFORM="Unknown"
        BUILD_CMD="build"
        ;;
esac

echo -e "${BLUE}Detected platform: ${DETECTED_PLATFORM}${RESET}"
echo ""

# Prompt user for build type
echo "What would you like to build?"
echo "1) Current platform only (${DETECTED_PLATFORM})"
echo "2) macOS"
echo "3) Windows"
echo "4) Linux"
echo "5) All platforms"
echo ""
read -p "Enter choice [1-5]: " choice

case $choice in
    1)
        BUILD_CMD=$BUILD_CMD
        ;;
    2)
        BUILD_CMD="build:mac"
        ;;
    3)
        BUILD_CMD="build:win"
        ;;
    4)
        BUILD_CMD="build:linux"
        ;;
    5)
        BUILD_CMD="build:all"
        ;;
    *)
        echo -e "${RED}Invalid choice. Using current platform.${RESET}"
        BUILD_CMD=$BUILD_CMD
        ;;
esac

echo ""
echo -e "${YELLOW}Building application...${RESET}"
echo -e "${BLUE}Running: npm run ${BUILD_CMD}${RESET}"
echo ""

npm run $BUILD_CMD

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}║  Build completed successfully! 🎉     ║${RESET}"
echo -e "${GREEN}╚════════════════════════════════════════╝${RESET}"
echo ""
echo -e "${BLUE}Built files are in: ${RESET}${SCRIPT_DIR}/dist/"
echo ""
echo -e "${YELLOW}Next steps:${RESET}"

case "$PLATFORM" in
    Darwin*)
        echo "  • Open dist/mac/TI-Toolbox.app"
        echo "  • Or install dist/*.dmg"
        ;;
    Linux*)
        echo "  • Run dist/*.AppImage"
        echo "  • Or install dist/*.deb"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        echo "  • Run dist/TI-Toolbox Setup *.exe"
        echo "  • Or run dist/TI-Toolbox *.exe (portable)"
        ;;
esac

echo ""
echo -e "${BLUE}For more information, see README.md${RESET}"
