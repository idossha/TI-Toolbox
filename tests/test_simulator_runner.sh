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
elif [ -f "/ti-toolbox/ti-toolbox/cli/simulator.sh" ]; then
    SIM_CMD="/ti-toolbox/ti-toolbox/cli/simulator.sh"
elif [ -f "/development/ti-toolbox/cli/simulator.sh" ]; then
    SIM_CMD="/development/ti-toolbox/cli/simulator.sh"
elif [ -f "ti-toolbox/cli/simulator.sh" ]; then
    SIM_CMD="./ti-toolbox/cli/simulator.sh"
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

echo "Running simulator with:"
echo "  Subject: $SUBJECT_CHOICES"
echo "  Sim Mode: $SIM_MODE (U=Unipolar TI)"
echo "  Conductivity: $CONDUCTIVITY"
echo "  Montage: $SELECTED_MONTAGES"

# Run simulator in non-interactive mode
"$SIM_CMD" --run-direct
