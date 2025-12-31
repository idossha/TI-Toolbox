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
# IMPORTANT:
# If we run `tit/gui/main.py` directly with cwd=.../tit, then `import tit` fails
# because Python will look for a nested `tit/tit` package.
# Run from the repo root and execute as a module so imports resolve cleanly.
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Ensure repo root is on PYTHONPATH even if the caller's cwd is different.
export PYTHONPATH="$REPO_ROOT${PYTHONPATH+:$PYTHONPATH}"

exec simnibs_python -m tit.gui.main
