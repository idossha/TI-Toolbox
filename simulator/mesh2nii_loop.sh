#!/bin/bash

##############################################
# Ido Haber - ihaber@wisc.edu
# October 16, 2024
# Optimized for optimizer pipeline
#
# This script is designed to convert parcellated mesh files (e.g., GM and WM meshes) to NIfTI format 
# using a subject's T1-weighted MRI as a reference. It ensures the anatomical accuracy 
# of simulations by aligning the mesh with the subject's brain anatomy in MNI space.
#
# Key Features:
# - Converts parcellated mesh files to NIfTI format using the subject2mni tool.
# - Validates input directories and files to ensure smooth execution.
# - Automatically creates an output directory for the resulting NIfTI files.
# - Provides detailed error handling for common issues like missing files or directories.
##############################################

# Get the subject ID, subject directory, input mesh directory, and output directory from the command-line arguments
subject_id="$1"
subject_dir="$2"
input_mesh_dir="$3"
output_dir="$4"

# Define the path to the reference directory
FN_REFERENCE="$subject_dir/m2m_${subject_id}"

# Check if input_mesh_dir exists and is a directory
if [ ! -d "$input_mesh_dir" ]; then
  echo "Error: Directory $input_mesh_dir does not exist."
  exit 1
fi

# Check if FN_REFERENCE exists and is a directory
if [ ! -d "$FN_REFERENCE" ]; then
  echo "Error: Reference directory $FN_REFERENCE does not exist."
  exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$output_dir"

# Loop through all .msh files in the directory
for FN_MESH in "$input_mesh_dir"/*.msh; do
  # Check if any .msh files are found
  if [ ! -f "$FN_MESH" ]; then
    echo "Error: No .msh files found in $input_mesh_dir."
    exit 1
  fi
  
  # Get the base name of the .msh file (without directory and extension)
  BASE_NAME=$(basename "$FN_MESH" .msh)
  
  # Define the output file names for both subject space and MNI space
  FN_OUT="$output_dir/${BASE_NAME}"
  
  # Run the subject2mni command for MNI space
  subject2mni -i "$FN_MESH" -m "$FN_REFERENCE" -o "${FN_OUT}_MNI"
  if [ $? -ne 0 ]; then
    echo "Error: subject2mni command failed for $FN_MESH."
    exit 1
  fi
  
  # Run msh2nii for subject space
  msh2nii "$FN_MESH" "$FN_REFERENCE" "${FN_OUT}"
  if [ $? -ne 0 ]; then
    echo "Error: msh2nii command failed for $FN_MESH."
    exit 1
  fi
done

echo "Processing complete!"

