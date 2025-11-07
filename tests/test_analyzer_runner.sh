#!/bin/bash

# Integration Test Runner for Analyzer
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

# Find analyzer script
if command -v analyzer >/dev/null 2>&1; then
    ANALYZER_CMD="analyzer"
elif [ -f "/ti-toolbox/ti-toolbox/cli/analyzer.sh" ]; then
    ANALYZER_CMD="/ti-toolbox/ti-toolbox/cli/analyzer.sh"
elif [ -f "ti-toolbox/cli/analyzer.sh" ]; then
    ANALYZER_CMD="./ti-toolbox/cli/analyzer.sh"
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
