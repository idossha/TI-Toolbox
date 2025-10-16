#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Use the guaranteed path from Dockerfile.ci
if command -v simulator >/dev/null 2>&1; then
    SIM_CMD="simulator"
else
    SIM_CMD="/ti-toolbox/CLI/simulator.sh"
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
