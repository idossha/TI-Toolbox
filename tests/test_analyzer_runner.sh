#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Find analyzer script - prioritize development code
if [ -f "/development/CLI/analyzer.sh" ]; then
    ANALYZER_CMD="/development/CLI/analyzer.sh"
    echo "Using development analyzer: $ANALYZER_CMD"
elif [ -f "CLI/analyzer.sh" ]; then
    ANALYZER_CMD="./CLI/analyzer.sh"
    echo "Using relative analyzer: $ANALYZER_CMD"
elif command -v analyzer >/dev/null 2>&1; then
    ANALYZER_CMD="analyzer"
    echo "Using installed analyzer: $ANALYZER_CMD"
elif [ -f "/ti-toolbox/CLI/analyzer.sh" ]; then
    ANALYZER_CMD="/ti-toolbox/CLI/analyzer.sh"
    echo "WARNING: Using baked-in analyzer (NOT development code): $ANALYZER_CMD"
else
    echo "Error: analyzer.sh not found"
    exit 1
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
