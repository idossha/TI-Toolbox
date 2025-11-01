#!/bin/bash

###########################################
# Aksel W Jackson / awjackson2@wisc.edu
# Ido Haber / ihaber@wisc.edu
# optimized for TI-Toolbox analyzer
# This script creates a png visualization of the electrode montage from user input
#
# This is a wrapper script that calls the Python implementation
###########################################

# Determine the location of the Python script
# The Python script is in the tools directory (one level up from sim)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$SCRIPT_DIR/../tools"
PYTHON_SCRIPT="$TOOLS_DIR/montage_visualizer.py"

# Check if Python script exists
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "Error: Could not find montage_visualizer.py at: $PYTHON_SCRIPT"
    exit 1
fi

# Parse arguments (maintaining backward compatibility)
# Expected format: montage1 [montage2 ...] sim_mode eeg_net output_directory
sim_mode="${@: -3:1}"  # Third-to-last argument is the simulation mode (U or M)
eeg_net="${@: -2:1}"   # Second-to-last argument is the EEG net name
output_directory="${@: -1}"  # The last argument is the output directory
selected_montages=("${@:1:$(($#-3))}")  # All but the last three arguments are the selected montages

# Call the Python script with the parsed arguments
simnibs_python "$PYTHON_SCRIPT" \
    "${selected_montages[@]}" \
    --sim-mode "$sim_mode" \
    --eeg-net "$eeg_net" \
    --output-dir "$output_directory" \
    --project-dir-name "$PROJECT_DIR_NAME"

# Exit with the same status as the Python script
exit $?
