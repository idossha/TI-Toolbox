#!/bin/bash

###########################################

# Ido Haber / ihaber@wisc.edu
# Optimized for TI-Toolbox analyzer

# This script performs region of interest (ROI) analysis on NIfTI files for a specific subject.
# It uses spherical masks to extract mean and maximum values from the selected ROIs
# and calculates differential mean values between ROIs across different NIfTI volumes.
# The results are saved in a text file within the designated output directory.

# Arguments:
#   1. subject_id        : The ID of the subject.
#   2. simulation_dir    : The base directory where simulation results are stored.
#   3. selected_rois     : A list of ROIs to analyze.

# Output:
#   - A text file containing the voxel coordinates, mean, and max values for the selected ROIs.
#   - Differential mean values between the selected ROIs.

# Note:
#   The script expects the 'roi_list.json' file to be located in the ../utils directory relative to the simulation directory.
#   It uses FSL tools to perform the analysis, so ensure FSL is installed and configured properly in the environment.
###########################################

# Enable error handling and debugging
set -e  # Exit immediately if a command exits with a non-zero status
#set -x  # Uncomment to enable shell command tracing

# Function to clean up temporary files
cleanup() {
    echo "Cleaning up temporary files..."
    rm -rf "$temp_dir"
}

# Trap to call cleanup function on exit or interruption
trap cleanup EXIT

# Create a unique temporary directory for this script's execution
temp_dir=$(mktemp -d -t sphere-analysis-XXXXXXXXXX)
echo "Debug: Created temporary directory $temp_dir"

# Get the subject ID and simulation directory from the command-line arguments
subject_id="$1"
simulation_dir="$2"
shift 2
selected_rois=("$@")

# Debugging outputs
echo "Debug: subject_id: $subject_id"
echo "Debug: simulation_dir: $simulation_dir"
echo "Debug: selected_rois: ${selected_rois[@]}"

# Check if any ROI names are provided
if [ ${#selected_rois[@]} -eq 0 ]; then
    echo "Error: No ROI names provided."
    exit 1
fi

# Set the designated directory for NIfTI files
nifti_dir="$simulation_dir/sim_${subject_id}/niftis"

# Output directory setup
output_dir="$simulation_dir/sim_${subject_id}/ROI_analysis"
mkdir -p "$output_dir"

# Define the correct path for the ROI JSON file
roi_file="${simulation_dir}/../utils/roi_list.json"

# Verify that roi_file exists
if [ ! -f "$roi_file" ]; then
    echo "Error: ROI file not found at $roi_file"
    exit 1
fi

# Radius for the spherical region (in voxels)
radius=3

# Output file setup
output_file="$output_dir/mean_max_values.txt"
echo "Voxel Coordinates and Corresponding Mean and Max Values for Selected ROIs (Sphere Radius: $radius voxels)" > "$output_file"

# Debug: List NIfTI files
echo "Debug: Listing NIfTI files in $nifti_dir"
ls -1 "$nifti_dir"/*.nii* || { echo "No NIfTI files found in $nifti_dir"; exit 1; }

# Initialize an array to keep track of temporary files (no longer needed as we're deleting the temp directory)

# Loop through selected ROIs and volumes
declare -A mean_values

for roi in "${selected_rois[@]}"; do
    echo "Debug: Processing ROI: $roi"

    location=$(jq -r ".ROIs[\"$roi\"]" "$roi_file")
    echo "Debug: Location for ROI '$roi': $location"

    # Check if location is valid
    if [[ "$location" == "null" || -z "$location" ]]; then
        echo "Error: Coordinates for ROI '$roi' not found in $roi_file"
        continue
    fi

    echo "" >> "$output_file"
    echo "Voxel Coordinates: ${location} (${roi})" >> "$output_file"

    IFS=' ' read -r vx vy vz <<< "$location"
    echo "Debug: Voxel coordinates: vx=$vx, vy=$vy, vz=$vz"

    for volume_file in "$nifti_dir"/*.nii*; do
        echo "Debug: Processing volume file: $volume_file"

        volume_name=$(basename "$volume_file")
        volume_name="${volume_name%%.*}"
        echo "Debug: Volume name: $volume_name"

        # Use absolute paths for temporary files in the temp directory
        temp_point="$temp_dir/temp_point_${volume_name}_${roi}.nii.gz"
        temp_sphere="$temp_dir/temp_sphere_${volume_name}_${roi}.nii.gz"
        temp_sphere_masked="$temp_dir/temp_sphere_masked_${volume_name}_${roi}.nii.gz"

        echo "Debug: Temporary files:"
        echo "  temp_point: $temp_point"
        echo "  temp_sphere: $temp_sphere"
        echo "  temp_sphere_masked: $temp_sphere_masked"

        echo "Debug: Creating point image..."
        fslmaths "$volume_file" -mul 0 -add 1 -roi "$vx" 1 "$vy" 1 "$vz" 1 0 1 "$temp_point" -odt float

        echo "Debug: Creating spherical mask..."
        fslmaths "$temp_point" -kernel sphere "$radius" -dilM -bin "$temp_sphere" -odt float

        echo "Debug: Applying mask to volume..."
        fslmaths "$volume_file" -mas "$temp_sphere" "$temp_sphere_masked"

        echo "Debug: Extracting statistics..."
        mean_value=$(fslstats "$temp_sphere_masked" -M -l 0.0001)
        max_value=$(fslstats "$temp_sphere_masked" -R | awk '{print $2}')

        echo "Debug: Mean value: $mean_value"
        echo "Debug: Max value: $max_value"

        if [ -z "$mean_value" ]; then
            echo "Error extracting mean value for ${volume_file} at ${location}" >> "$output_file"
            continue
        fi

        mean_values["${volume_name}_${roi}"]=$mean_value

        echo "${volume_name}: mean=$mean_value , max=$max_value" >> "$output_file"
    done
done

# Calculate and output differential values
echo "" >> "$output_file"
echo "Differential Mean Values between Selected ROIs:" >> "$output_file"

for volume_file in "$nifti_dir"/*.nii*; do
    volume_name=$(basename "$volume_file")
    volume_name="${volume_name%%.*}"
    echo "Debug: Calculating differentials for volume: $volume_name"

    for ((i=0; i<${#selected_rois[@]}; i++)); do
        for ((j=i+1; j<${#selected_rois[@]}; j++)); do
            roi1="${selected_rois[$i]}"
            roi2="${selected_rois[$j]}"

            mean_1=${mean_values["${volume_name}_${roi1}"]}
            mean_2=${mean_values["${volume_name}_${roi2}"]}

            echo "Debug: Mean values for ${volume_name}: ${roi1}=$mean_1, ${roi2}=$mean_2"

            if [ -n "$mean_1" ] && [ -n "$mean_2" ]; then
                differential_value=$(echo "$mean_1 - $mean_2" | bc)
                absolute_differential_value=$(echo "$differential_value" | awk '{if ($1<0) print -1*$1; else print $1}')
                echo "${volume_name} (${roi1} vs ${roi2}) = ${absolute_differential_value}" >> "$output_file"
            else
                echo "Error: Missing mean value for ${volume_name} at ${roi1} or ${roi2}" >> "$output_file"
            fi
        done
    done
done

echo "ROI analysis completed. Results saved to $output_file."

