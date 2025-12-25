#!/bin/bash

# Integration Test Runner for Simulator
# 
# ⚠️ WARNING: This script is designed to run INSIDE the Docker test container.
# DO NOT run this script directly on your host machine - it will fail!
# 
# Instead, use from your host:
#   ./tests/test.sh              # Run all tests
#   ./tests/test.sh --unit-only  # Run only unit tests
#
# This script is called automatically by test.sh and run_tests.sh

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Find simulator script
if command -v simulator >/dev/null 2>&1; then
    SIM_CMD="simulator"
    SIM_ARGS=""
elif [ -f "/ti-toolbox/ti-toolbox/cli/simulator.py" ]; then
    SIM_CMD="simnibs_python"
    SIM_ARGS="/ti-toolbox/ti-toolbox/cli/simulator.py"
elif [ -f "/development/ti-toolbox/cli/simulator.py" ]; then
    SIM_CMD="simnibs_python"
    SIM_ARGS="/development/ti-toolbox/cli/simulator.py"
elif [ -f "ti-toolbox/cli/simulator.py" ]; then
    SIM_CMD="simnibs_python"
    SIM_ARGS="./ti-toolbox/cli/simulator.py"
else
    echo "Error: simulator.py not found"
    exit 1
fi

# Set simulation parameters
SUBJECT="ernie_extended"
EEG_NET="EEG10-20_extended_SPM12.csv"
MONTAGE="central_montage"
CONDUCTIVITY="scalar"
INTENSITY="2"
ELECTRODE_SHAPE="rect"
DIMENSIONS="2,2"
THICKNESS="4"

echo "Running simulator with:"
echo "  Subject: $SUBJECT"
echo "  EEG Net: $EEG_NET"
echo "  Montage: $MONTAGE"
echo "  Conductivity: $CONDUCTIVITY"
echo "  Intensity: $INTENSITY mA"
echo "  Electrode Shape: $ELECTRODE_SHAPE"
echo "  Dimensions: $DIMENSIONS mm"
echo "  Thickness: $THICKNESS mm"

# Run simulator in non-interactive mode with proper arguments
"$SIM_CMD" "$SIM_ARGS" run \
    --subject "$SUBJECT" \
    --montage "$MONTAGE" \
    --eeg-net "$EEG_NET" \
    --conductivity "$CONDUCTIVITY" \
    --intensity "$INTENSITY" \
    --shape "$ELECTRODE_SHAPE" \
    --dimensions "$DIMENSIONS" \
    --thickness "$THICKNESS"
