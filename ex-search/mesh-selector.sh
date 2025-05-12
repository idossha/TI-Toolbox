#!/bin/bash

##############################################
# Ido Haber - ihaber@wisc.edu
# September 2, 2024
# Optimized for optimizer pipeline
#
# This script helps the user maintain a clean project directory 
# by allowing selective retention of .msh files and removing unwanted files 
# to reduce clutter.
#
# It prompts the user to select specific .msh files for simulation, 
# and optionally deletes the remaining .msh files and all .opt files.
##############################################

# Check if required environment variables are set
if [ -z "$PROJECT_DIR" ] || [ -z "$SUBJECT_NAME" ]; then
    echo "Error: PROJECT_DIR and SUBJECT_NAME environment variables must be set"
    exit 1
fi

# Get the first ROI file from roi_list.txt
roi_list_file="$PROJECT_DIR/derivatives/SimNIBS/sub-$SUBJECT_NAME/m2m_${SUBJECT_NAME}/ROIs/roi_list.txt"
first_roi=$(head -n1 "$roi_list_file")
if [ ! -f "$first_roi" ]; then
    echo "Error: ROI file not found: $first_roi"
    exit 1
fi

# Read coordinates from the ROI file
IFS=',' read -r x y z <<< $(head -n1 "$first_roi")
# Round coordinates to integers
x_int=$(printf "%.0f" "$x")
y_int=$(printf "%.0f" "$y")
z_int=$(printf "%.0f" "$z")

# Create directory name from coordinates
coord_dir="xyz_${x_int}_${y_int}_${z_int}"
opt_directory="$PROJECT_DIR/derivatives/SimNIBS/sub-$SUBJECT_NAME/ex-search/$coord_dir"

# Get list of mesh files
msh_files=($(ls "$opt_directory"/*.msh))

# Check if any mesh files were found
if [ ${#msh_files[@]} -eq 0 ]; then
    echo "No mesh files found in $opt_directory"
    exit 1
fi

# Print the list of mesh files with indices
echo "Available mesh files:"
for i in "${!msh_files[@]}"; do
    echo "$((i+1)). $(basename "${msh_files[$i]}")"
done

# Get user selection
echo -n "Select a mesh file (1-${#msh_files[@]}): "
read selection

# Validate selection
if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt "${#msh_files[@]}" ]; then
    echo "Invalid selection"
    exit 1
fi

# Get the selected mesh file
selected_mesh="${msh_files[$((selection-1))]}"

# Remove any existing .opt files
rm -f "$opt_directory"/*.opt

# Create a new .opt file with the same name as the selected mesh
opt_file="${selected_mesh%.msh}.opt"
touch "$opt_file"

echo "Created optimization file: $opt_file"

echo "All tasks completed successfully."

