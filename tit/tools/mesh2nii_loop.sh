#!/bin/bash

# Get the subject ID, m2m directory, input mesh directory, and output directory from the command-line arguments
subject_id="$1"
m2m_dir="$2"  # This is now the full path to the m2m directory
input_mesh_dir="$3"
output_dir="$4"

# Check if input_mesh_dir exists and is a directory
if [ ! -d "$input_mesh_dir" ]; then
  echo "Error: Directory $input_mesh_dir does not exist."
  exit 1
fi

# Check if m2m_dir exists and is a directory
if [ ! -d "$m2m_dir" ]; then
  echo "Error: Reference directory $m2m_dir does not exist."
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
  
  # Skip surface meshes (e.g., *_normal.msh) as they don't have volume elements
  # and cannot be transformed to MNI space using volume-based methods
  if [[ "$BASE_NAME" == *"normal"* ]]; then
    echo "Skipping surface mesh (no volume elements): $BASE_NAME"
    continue
  fi
  
  # Define the output file names with the desired naming convention
  FN_OUT="$output_dir/${BASE_NAME}_MNI.nii.gz"
  
  # Run the subject2mni command for MNI space
  subject2mni -i "$FN_MESH" -m "$m2m_dir" -o "$FN_OUT"
  if [ $? -ne 0 ]; then
    echo "Error: subject2mni command failed for $FN_MESH."
    exit 1
  fi
  
  # Run msh2nii for subject space
  FN_OUT_SUBJECT="$output_dir/${BASE_NAME}_subject.nii.gz"
  msh2nii "$FN_MESH" "$m2m_dir" "$FN_OUT_SUBJECT"
  if [ $? -ne 0 ]; then
    echo "Error: msh2nii command failed for $FN_MESH."
    exit 1
  fi
done

echo "Processing complete!"

