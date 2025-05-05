#!/bin/bash

###########################################
# TI-CSC-2.0 GUI Launcher
# This script launches the TI-CSC-2.0 GUI.
###########################################

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Define colors for output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RESET='\033[0m'

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required to run the GUI.${RESET}"
    exit 1
fi

# Check if PyQt5 is installed, if not prompt to install
python3 -c "import PyQt5" &> /dev/null
if [ $? -ne 0 ]; then
    echo -e "${CYAN}PyQt5 is not installed. Would you like to install it? (y/n)${RESET}"
    read -r answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        echo -e "${CYAN}Installing PyQt5...${RESET}"
        pip3 install PyQt5
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to install PyQt5. Please install it manually with 'pip3 install PyQt5'.${RESET}"
            exit 1
        fi
    else
        echo -e "${RED}PyQt5 is required to run the GUI. Exiting.${RESET}"
        exit 1
    fi
fi

# Launch the GUI
echo -e "${GREEN}Launching TI-CSC-2.0 GUI...${RESET}"
cd "$SCRIPT_DIR/.."
python3 "$SCRIPT_DIR/../GUI/main.py" 