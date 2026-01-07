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
elif command -v simnibs_python >/dev/null 2>&1; then
    # Preferred: Python Click CLI replacement
    ANALYZER_CMD="simnibs_python -m tit.cli.analyzer"
else
    echo "Error: analyzer CLI not found"
    exit 1
fi

# Run analyzer in non-interactive mode with proper arguments
eval "$ANALYZER_CMD" \
    --sub "ernie_extended" \
    --sim "central_montage" \
    --space "mesh" \
    --analysis-type "spherical" \
    --coordinates -50 0 0 \
    --radius 5 \
    --coordinate-space "subject" \
    --visualize
