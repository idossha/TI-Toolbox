#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Find simulator script - prioritize development code
if [ -f "/development/CLI/simulator.sh" ]; then
    SIM_CMD="/development/CLI/simulator.sh"
    echo "Using development simulator: $SIM_CMD"
elif [ -f "CLI/simulator.sh" ]; then
    SIM_CMD="./CLI/simulator.sh"
    echo "Using relative simulator: $SIM_CMD"
elif command -v simulator >/dev/null 2>&1; then
    SIM_CMD="simulator"
    echo "Using installed simulator: $SIM_CMD"
elif [ -f "/ti-toolbox/CLI/simulator.sh" ]; then
    SIM_CMD="/ti-toolbox/CLI/simulator.sh"
    echo "WARNING: Using baked-in simulator (NOT development code): $SIM_CMD"
else
    echo "Error: simulator.sh not found"
    exit 1
fi

# Set environment variables for non-interactive mode
export SUBJECT_CHOICES="ernie_extended"
export SIM_TYPE="isotropic"
export SIMULATION_FRAMEWORK="montage"
export SIM_MODE="U"
export CONDUCTIVITY="scalar"
export EEG_NETS="EEG10-20_extended_SPM12.csv"
export SELECTED_MONTAGES="central_montage"
export ELECTRODE_SHAPE="rect"
export DIMENSIONS="2,2"
export THICKNESS="4"
export CURRENT="2"

# Run simulator in non-interactive mode
"$SIM_CMD" --run-direct
