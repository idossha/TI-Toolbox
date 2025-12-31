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
# Expected format: sim_mode eeg_net output_directory [montage1 [montage2 ...]] [--pairs "montage:pair1-pair2,pair3-pair4"]
sim_mode="$1"         # First argument is the simulation mode (U or M)
eeg_net="$2"          # Second argument is the EEG net name
output_directory="$3" # Third argument is the output directory

# Check if --pairs is provided
pairs_arg=""
selected_montages=()
shift 3  # Remove the first three arguments

while [[ $# -gt 0 ]]; do
    case $1 in
        --pairs)
            pairs_arg="$2"
            shift 2
            ;;
        *)
            selected_montages+=("$1")
            shift
            ;;
    esac
done

# Call the Python script with the parsed arguments
cmd=(simnibs_python "$PYTHON_SCRIPT" \
    --sim-mode "$sim_mode" \
    --eeg-net "$eeg_net" \
    --output-dir "$output_directory" \
    --project-dir-name "$PROJECT_DIR_NAME")

if [[ -n "$pairs_arg" ]]; then
    cmd+=(--pairs "$pairs_arg")
else
    cmd+=("${selected_montages[@]}")
fi

"${cmd[@]}"

# Exit with the same status as the Python script
exit $?
