#!/bin/bash

###########################################
# TI-Toolbox GUI Launcher
###########################################

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Define colors for output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RESET='\033[0m'

# Launch the GUI
echo -e "${GREEN}Launching TI-Toolbox GUI...${RESET}"
cd "$SCRIPT_DIR/.."
simnibs_python "$SCRIPT_DIR/../gui/main.py" 
