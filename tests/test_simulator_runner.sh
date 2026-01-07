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

# Create montage configuration for the test
CONFIG_DIR="$PROJECT_DIR/code/tit/config"
MONTAGE_FILE="$CONFIG_DIR/montage_list.json"

# Ensure config directory exists
mkdir -p "$CONFIG_DIR"

# Create montage_list.json with central_montage for Okamoto EEG net
# Using standard 10-20 electrodes: Fz-Pz (frontal-parietal pair) and C3-C4 (left-right motor pair)
cat > "$MONTAGE_FILE" << 'EOF'
{
  "nets": {
    "EEG10-20_Okamoto_2004.csv": {
      "uni_polar_montages": {
        "central_montage": [
          ["Fz", "Pz"],
          ["C3", "C4"]
        ]
      },
      "multi_polar_montages": {}
    },
    "EGI_template.csv": {
      "uni_polar_montages": {},
      "multi_polar_montages": {}
    }
  }
}
EOF

chmod 666 "$MONTAGE_FILE"

# Find simulator script
if command -v simulator >/dev/null 2>&1; then
    SIM_CMD="simulator"
    SIM_ARGS=""
elif [ -f "/ti-toolbox/tit/cli/simulator.py" ]; then
    SIM_CMD="simnibs_python"
    SIM_ARGS="/ti-toolbox/tit/cli/simulator.py"
elif [ -f "/development/ti-toolbox/tit/cli/simulator.py" ]; then
    SIM_CMD="simnibs_python"
    SIM_ARGS="/development/ti-toolbox/tit/cli/simulator.py"
elif [ -f "/development/tit/cli/simulator.py" ]; then
    # Backward compatibility (older mounts)
    SIM_CMD="simnibs_python"
    SIM_ARGS="/development/tit/cli/simulator.py"
elif [ -f "tit/cli/simulator.py" ]; then
    SIM_CMD="simnibs_python"
    SIM_ARGS="./tit/cli/simulator.py"
else
    echo "Error: simulator.py not found"
    exit 1
fi

# Set simulation parameters
SUBJECT="ernie_extended"
EEG_NET="EEG10-20_Okamoto_2004.csv"
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

# Clean up any existing simulation directory before running
SIM_DIR="$PROJECT_DIR/derivatives/SimNIBS/sub-$SUBJECT/Simulations"
if [ -d "$SIM_DIR" ]; then
    echo "Cleaning up existing simulations directory: $SIM_DIR"
    rm -rf "$SIM_DIR"
fi

# Run simulator in non-interactive mode with proper arguments
"$SIM_CMD" "$SIM_ARGS" \
    --subject "$SUBJECT" \
    --montages "$MONTAGE" \
    --eeg-net "$EEG_NET" \
    --conductivity "$CONDUCTIVITY" \
    --intensity "$INTENSITY" \
    --electrode-shape "$ELECTRODE_SHAPE" \
    --dimensions "$DIMENSIONS" \
    --thickness "$THICKNESS"
