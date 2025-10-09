#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Use the guaranteed path from Dockerfile.ci
if command -v analyzer >/dev/null 2>&1; then
    ANALYZER_CMD="analyzer"
elif [ -f "/development/CLI/analyzer.sh" ]; then
    ANALYZER_CMD="/development/CLI/analyzer.sh"
else
    ANALYZER_CMD="/ti-toolbox/CLI/analyzer.sh"
fi

# Set environment variables for non-interactive mode
export SUBJECT="ernie_extended"
export SIMULATION_NAME="test_montage"
export SPACE_TYPE="mesh"
export ANALYSIS_TYPE="spherical"
export FIELD_PATH="$PROJECT_DIR/derivatives/SimNIBS/sub-ernie_extended/Simulations/test_montage/TI/mesh/grey_test_montage_TI.msh"
export COORDINATES="-50 0 0"
export RADIUS="5"
export VISUALIZE="true"

# Run analyzer in non-interactive mode
export ANALYSIS_MODE="single"
"$ANALYZER_CMD" --run-direct
