#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Use the guaranteed path from Dockerfile.ci
if command -v simulator >/dev/null 2>&1; then
    SIM_CMD="simulator"
    echo "DEBUG: Found simulator command in PATH"
else
    SIM_CMD="/ti-toolbox/CLI/simulator.sh"
    echo "DEBUG: Using guaranteed path from Dockerfile.ci: $SIM_CMD"
fi

echo "DEBUG: SIM_CMD = $SIM_CMD"
echo "DEBUG: File exists: $([ -f "$SIM_CMD" ] && echo "YES" || echo "NO")"

# Set environment variables for non-interactive mode
export SUBJECT_CHOICES="ernie"
export SIM_TYPE="isotropic"
export SIMULATION_FRAMEWORK="montage"
export SIM_MODE="U"
export CONDUCTIVITY="0"
export EEG_NETS="EGI_template.csv"
export SELECTED_MONTAGES="4"
export ELECTRODE_SHAPE="rect"
export DIMENSIONS="2,2"
export THICKNESS="2"
export CURRENT="10"

echo "DEBUG: Running simulator in non-interactive mode with environment variables"
echo "DEBUG: SUBJECT_CHOICES=$SUBJECT_CHOICES"
echo "DEBUG: SIM_TYPE=$SIM_TYPE"
echo "DEBUG: SIMULATION_FRAMEWORK=$SIMULATION_FRAMEWORK"
echo "DEBUG: SIM_MODE=$SIM_MODE"
echo "DEBUG: CONDUCTIVITY=$CONDUCTIVITY"
echo "DEBUG: EEG_NETS=$EEG_NETS"
echo "DEBUG: SELECTED_MONTAGES=$SELECTED_MONTAGES"
echo "DEBUG: ELECTRODE_SHAPE=$ELECTRODE_SHAPE"
echo "DEBUG: DIMENSIONS=$DIMENSIONS"
echo "DEBUG: THICKNESS=$THICKNESS"
echo "DEBUG: CURRENT=$CURRENT"

# Run simulator in non-interactive mode
"$SIM_CMD" --run-direct
