#!/bin/bash

set -e

PROJECT_DIR="/mnt/test_projectdir"
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")

# Use the guaranteed path from Dockerfile.ci
if command -v analyzer >/dev/null 2>&1; then
    ANALYZER_CMD="analyzer"
    echo "DEBUG: Found analyzer command in PATH"
else
    ANALYZER_CMD="/ti-toolbox/CLI/analyzer.sh"
    echo "DEBUG: Using guaranteed path from Dockerfile.ci: $ANALYZER_CMD"
fi

echo "DEBUG: ANALYZER_CMD = $ANALYZER_CMD"
echo "DEBUG: File exists: $([ -f "$ANALYZER_CMD" ] && echo "YES" || echo "NO")"

# Set environment variables for non-interactive mode
export SUBJECT="ernie"
export SIMULATION_NAME="TI"
export SPACE_TYPE="mesh"
export ANALYSIS_TYPE="spherical"
export FIELD_PATH="$PROJECT_DIR/derivatives/SimNIBS/sub-ernie/Simulations/TI/TI/mesh/ernie_TI.msh"
export COORDINATES="-50 0 0"
export RADIUS="10"
export VISUALIZE="true"

echo "DEBUG: Running analyzer in non-interactive mode with environment variables"
echo "DEBUG: SUBJECT=$SUBJECT"
echo "DEBUG: SIMULATION_NAME=$SIMULATION_NAME"
echo "DEBUG: SPACE_TYPE=$SPACE_TYPE"
echo "DEBUG: ANALYSIS_TYPE=$ANALYSIS_TYPE"
echo "DEBUG: FIELD_PATH=$FIELD_PATH"
echo "DEBUG: COORDINATES=$COORDINATES"
echo "DEBUG: RADIUS=$RADIUS"
echo "DEBUG: VISUALIZE=$VISUALIZE"

# Run analyzer in non-interactive mode
"$ANALYZER_CMD" --run-direct
