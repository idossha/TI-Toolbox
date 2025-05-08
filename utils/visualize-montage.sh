#!/bin/bash

###########################################
# Aksel W Jackson / awjackson2@wisc.edu
# Ido Haber / ihaber@wisc.edu
# October 16, 2024
# optimized for TI-CSC analyzer
# This script creates a png visualization of the electrode montage from user input
###########################################

# Define paths
project_base="/mnt/$PROJECT_DIR_NAME"
utils_dir="$project_base/utils"
montage_file="$utils_dir/montage_list.json"

# Check if the montage file exists
if [[ ! -f "$montage_file" ]]; then
    echo "Error: Montage file not found at: $montage_file"
    exit 1
fi

# Parse arguments
sim_mode="${@: -3:1}"  # Third-to-last argument is the simulation mode (U or M)
eeg_net="${@: -2:1}"   # Second-to-last argument is the EEG net name
output_directory="${@: -1}"  # The last argument is the output directory
selected_montages=("${@:1:$(($#-3))}")  # All but the last three arguments are the selected montages

# Create output directory if it doesn't exist
mkdir -p "$output_directory"

# Ensure output directory is absolute path
if [[ ! "$output_directory" = /* ]]; then
    output_directory="$project_base/$output_directory"
fi

# Dynamically determine the montage type based on the sim_mode
if [[ "$sim_mode" == "U" ]]; then
    montage_type="uni_polar_montages"
elif [[ "$sim_mode" == "M" ]]; then
    montage_type="multi_polar_montages"
else
    echo "Error: Invalid montage type. Please provide 'U' for Unipolar or 'M' for Multipolar."
    exit 1
fi

# Debugging: Output the simulation mode and montage type
echo "Simulation Mode (sim_mode): $sim_mode"
echo "EEG Net: $eeg_net"
echo "Montage Type: $montage_type"
echo "Selected Montages: ${selected_montages[@]}"
echo "Output Directory: $output_directory"

# Create output directory if it doesn't exist
mkdir -p "$output_directory"

# Initialize the output image for Multipolar mode (M)
if [[ "$sim_mode" == "M" ]]; then
    combined_output_image="$output_directory/combined_montage_visualization.png"
    # Start with a blank template
    cp "/ti-csc/assets/amv/256template.png" "$combined_output_image"
fi

# Ring images for each pair (using distinct ones for multipolar montages)
ring_images=("pair1ring.png" "pair2ring.png" "pair3ring.png" "pair4ring.png")

# Function to generate output filename based on electrode pairs
generate_output_filename() {
    local montage_name=$1
    echo "$output_directory/${montage_name}_highlighted_visualization.png"
}

# Function to overlay the ring for a pair of electrodes using pre-existing images
overlay_rings() {
    local electrode_label=$1
    local ring_image=$2
    echo "Overlaying ring for electrode: $electrode_label using image: $ring_image"

    # Get modified coordinates for the current electrode label from the CSV
    coords=$(awk -F, -v label="$electrode_label" '$1 == label {print $3, $5}' "/ti-csc/assets/amv/electrodes.csv")
    if [ -z "$coords" ]; then
        echo "Warning: Coordinates not found for electrode '$electrode_label'. Skipping overlay."
        return
    fi

    # Read coordinates into variables
    IFS=' ' read -r x_adjusted y_adjusted <<< "$coords"
    echo "Coordinates for electrode '$electrode_label': x=$x_adjusted, y=$y_adjusted"

    # Use the pre-existing ring image to overlay the ring at the specified coordinates
    convert "$output_image" "/ti-csc/assets/amv/$ring_image" -geometry +${x_adjusted}+${y_adjusted} -composite "$output_image" || {
        echo "Error: Failed to overlay ring image '$ring_image' onto output image '$output_image'."
    }
}

# Initialize a global pair index to keep track of all pairs across montages
global_pair_index=0

# Loop through the selected montages and process each
for montage in "${selected_montages[@]}"; do
    # Extract pairs from the JSON file based on the selected montage type and net
    echo "Retrieving pairs for montage '$montage' of type '$montage_type' from net '$eeg_net' in '$montage_file'"
    pairs=$(jq -r --arg net "$eeg_net" --arg type "$montage_type" --arg montage "$montage" '.nets[$net][$type][$montage][] | @csv' "$montage_file" 2>/dev/null)
    if [ $? -ne 0 ]; then
        echo "Error: Failed to parse JSON for montage '$montage'. Please check the format."
        continue
    fi
    echo "Retrieved pairs for montage '$montage':"
    echo "$pairs"

    # Generate the output image filename for the current montage (only for Unipolar)
    if [[ "$sim_mode" == "U" ]]; then
        output_image=$(generate_output_filename "$montage")
        # Initialize output image to the template image (create only once for the montage)
        cp "/ti-csc/assets/amv/256template.png" "$output_image" || {
            echo "Error: Failed to copy template image to '$output_image'."
            continue
        }
    fi

    # Split the pairs and overlay the corresponding rings
    IFS=$'\n' # Set internal field separator to handle multiline input
    for pair in $pairs; do
        echo "Processing pair: $pair"
        # Remove quotes and split by comma
        pair=${pair//\"/}  # Remove quotes
        IFS=',' read -r -a electrodes <<< "$pair"  # Split into individual electrodes
        echo "Electrodes extracted: ${electrodes[@]}"

        # Check if we got exactly 2 electrodes
        if [ ${#electrodes[@]} -ne 2 ]; then
            echo "Warning: Expected 2 electrodes, got ${#electrodes[@]}. Skipping pair: $pair."
            continue
        fi

        # Get the appropriate ring image based on the global pair index
        ring_image=${ring_images[$global_pair_index % ${#ring_images[@]}]}  # Cycle through 4 distinct ring images

        # Overlay rings for each electrode in the current pair
        if [[ "$sim_mode" == "U" ]]; then
            output_image="$output_image"  # For unipolar, separate images
        else
            output_image="$combined_output_image"  # For multipolar, combine on one image
        fi
        overlay_rings "${electrodes[0]}" "$ring_image"
        overlay_rings "${electrodes[1]}" "$ring_image"

        # Increment global pair index for the next pair
        global_pair_index=$((global_pair_index + 1))
    done

    # For unipolar, show output for each montage separately
    if [[ "$sim_mode" == "U" ]]; then
        echo "Ring overlays for montage '$montage' completed. Output saved to $output_image."
    fi
done

# If multipolar, show combined output for all montages
if [[ "$sim_mode" == "M" ]]; then
    echo "Ring overlays for all montages combined. Output saved to $combined_output_image."
fi
