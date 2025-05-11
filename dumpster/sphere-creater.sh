#!/bin/bash

##############################################
# Ido Haber - ihaber@wisc.edu
# October 16, 2024
# Optimized for TI-CSC toolbox
#
# This script dynamically creates spherical regions of interest (ROIs) based on the 
# selected subject and ROI input from the user. It generates NIfTI files for these 
# spheres and combines them into a single ROI volume for visualization.
##############################################

# Get the subject ID and simulation directory as arguments
subject_id=$1
simulation_dir=$2
shift 2
selected_roi_names=("$@")

# Check if any ROI names are provided
if [ ${#selected_roi_names[@]} -eq 0 ]; then
    echo "Error: No ROI names provided."
    exit 1
fi

# Set paths for subject-specific T1-weighted MNI file and output directory
subject_dir="/mnt/$PROJECT_DIR_NAME/Subjects/"
t1_file="$subject_dir/m2m_${subject_id}/T1_${subject_id}_MNI.nii.gz"
output_dir="$simulation_dir/sim_${subject_id}/niftis/"

# Check if the T1-weighted MNI file exists
if [[ ! -f "$t1_file" ]]; then
    echo "Error: T1-weighted MNI file for subject $subject_id not found at: $t1_file"
    exit 1
fi

# Ensure the output directory exists
mkdir -p "$output_dir"

# Replace spaces in ROI names with underscores and combine them to form a key
key=$(IFS=_; echo "${selected_roi_names[*]// /_}")  
combined_roi_file="${output_dir}/${key}-sphere.nii.gz"

# Initialize the combined ROI volume with zeros
fslmaths "$t1_file" -mul 0 "$combined_roi_file" -odt float

# Set the radius for the spherical region (in voxels)
radius=3

# Path to ROI list JSON file
roi_file_path="/mnt/$PROJECT_DIR_NAME/utils/roi_list.json"

# Function to get voxel coordinates from ROI name
get_voxel_coordinates() {
    local roi_name="$1"
    local roi_file="$2"
    jq -r ".ROIs.\"$roi_name\"" "$roi_file"
}

# Create spherical ROIs and combine them into the combined ROI volume
for roi_name in "${selected_roi_names[@]}"; do
    echo "Processing ROI: $roi_name"  # Debugging output to ensure correct ROI name

    # Get the voxel coordinates for the selected ROI
    location=$(get_voxel_coordinates "$roi_name" "$roi_file_path")
    
    # Check if the coordinates are valid
    if [[ "$location" == "null" || -z "$location" ]]; then
        echo "Error: Coordinates for ROI '$roi_name' not found in $roi_file_path."
        exit 1
    fi

    echo "Coordinates for ROI '$roi_name': $location"  # Debugging output to verify coordinates

    IFS=' ' read -r vx vy vz <<< "$location"

    # Sanitize the ROI name to remove spaces and special characters
    roi_name_sanitized=$(echo "$roi_name" | tr -s ' ' '_')

    # Create the spherical ROI based on the coordinates
    roi_file="${output_dir}/sphere_${subject_id}_${roi_name_sanitized}.nii.gz"

    # Create the spherical ROI at the specified voxel coordinates
    fslmaths "$t1_file" -mul 0 -add 1 -roi "$vx" 1 "$vy" 1 "$vz" 1 0 1 temp_point.nii.gz -odt float
    fslmaths temp_point.nii.gz -kernel sphere "$radius" -dilM -bin "$roi_file" -odt float

    # Add the spherical ROI to the combined volume
    fslmaths "$combined_roi_file" -add "$roi_file" "$combined_roi_file" -odt float

    # Delete the temporary spherical ROI file
    rm -f "$roi_file"
done

# Delete the temporary point file
rm -f temp_point.nii.gz

echo "Spherical ROI creation completed for subject $subject_id. Output saved to $combined_roi_file."

