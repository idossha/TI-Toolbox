#!/bin/bash

##############################################
# Ido Haber - ihaber@wisc.edu
# October 16, 2024
# Optimized for optimizer pipeline
#
# This script orchestrates the full pipeline for Temporal Interference (TI) simulations
# using SimNIBS and other related tools. It handles directory setup, simulation execution,
# mesh processing, field extraction, NIfTI transformation, and other key tasks.
#
# New Features:
# - Automatically creates spherical ROIs and visualizes them based on the user’s input.
# - Extracts both grey matter (GM) and white matter (WM) meshes and saves them in the parcellated_mesh directory.
#
##############################################

set -e # Exit immediately if a command exits with a non-zero status

# Gather arguments from the prompter script
subject_id=$1
conductivity=$2
subject_dir=$3
simulation_dir=$4
sim_mode=$5  # Capture sim_mode
shift 5

# Initialize arrays
selected_montages=()
selected_roi_names=()

# Parse montages until '--' is found
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --)
            shift
            break
            ;;
        *)
            selected_montages+=("$1")
            shift
            ;;
    esac
done

# Remaining arguments are ROI names
selected_roi_names=("$@")

# Set the script directory to the present working directory
script_dir="$(pwd)"

# Set subdirectory paths
sim_dir="$simulation_dir/sim_${subject_id}"
fem_dir="$sim_dir/FEM"
whole_brain_mesh_dir="$sim_dir/Whole-Brain-mesh"
parcellated_mesh_dir="$sim_dir/parcellated_mesh"  # Updated directory name
nifti_dir="$sim_dir/niftis"
output_dir="$sim_dir/ROI_analysis"
screenshots_dir="$sim_dir/screenshots"
visualization_output_dir="$sim_dir/montage_imgs/"

# Ensure directories exist
mkdir -p "$whole_brain_mesh_dir" "$parcellated_mesh_dir" "$nifti_dir" "$output_dir" "$screenshots_dir" "$visualization_output_dir"

# Debugging outputs
echo "Debug: subject_id: $subject_id"
echo "Debug: conductivity: $conductivity"
echo "Debug: subject_dir: $subject_dir"
echo "Debug: simulation_dir: $simulation_dir"
echo "Debug: sim_mode: $sim_mode"
echo "Debug: selected_montages: ${selected_montages[@]}"
echo "Debug: selected_roi_names: ${selected_roi_names[@]}"

# Main script: Run TI.py with the selected parameters
simnibs_python TI.py "$subject_id" "$conductivity" "$subject_dir" "$simulation_dir" "${selected_montages[@]}"

# Function to visualize montages
run_visualize_montages() {
    echo "Visualizing selected montages..."
    echo "Calling visualize-montage.sh with arguments:"
    echo "Montages: ${selected_montages[@]}"
    echo "Sim Mode: $sim_mode"
    echo "Output Directory: $visualization_output_dir"
    visualize_montage_script_path="$script_dir/visualize-montage.sh"
    bash "$visualize_montage_script_path" "${selected_montages[@]}" "$sim_mode" "$visualization_output_dir"
    echo "Montage visualization completed"
}

# Function to extract fields (GM and WM meshes)
extract_fields() {
    local input_file="$1"
    local gm_output_file="$2"
    local wm_output_file="$3"
    echo "Extracting fields (GM and WM) from $input_file..."
    field_extract_script_path="$script_dir/field_extract.py"
    simnibs_python "$field_extract_script_path" "$input_file" --gm_output_file "$gm_output_file" --wm_output_file "$wm_output_file"
    echo "Field extraction (GM and WM) completed"
}

# Function to transform parcellated meshes to NIfTI
transform_parcellated_meshes_to_nifti() {
    echo "Transforming parcellated meshes (GM and WM) to NIfTI in MNI space..."
    mesh2nii_script_path="$script_dir/mesh2nii_loop.sh"
    bash "$mesh2nii_script_path" "$subject_id" "$subject_dir" "$simulation_dir"
    echo "Parcellated meshes to NIfTI transformation completed"
}

# Function to convert T1 to MNI space
convert_t1_to_mni() {
    local t1_file="$subject_dir/m2m_${subject_id}/T1.nii.gz"
    local m2m_dir="$subject_dir/m2m_${subject_id}"
    local output_file="$subject_dir/m2m_${subject_id}/T1_${subject_id}"
    echo "Converting T1 to MNI space..."
    subject2mni -i "$t1_file" -m "$m2m_dir" -o "$output_file"
    echo "T1 conversion to MNI completed: $output_file"
}

# Function to process mesh files
process_mesh_files() {
    echo "Processing mesh files..."
    process_mesh_script_path="$script_dir/field-analysis/run_process_mesh_files.sh"
    bash "$process_mesh_script_path" "$whole_brain_mesh_dir"
    echo "Mesh files processed"
}

# Function to run sphere analysis
run_sphere_analysis() {
    echo "Running sphere analysis..."
    sphere_analysis_script_path="$script_dir/sphere-analysis.sh"
    bash "$sphere_analysis_script_path" "$subject_id" "$simulation_dir" "${selected_roi_names[@]}"
    echo "Sphere analysis completed"
}

# Function to generate screenshots
generate_screenshots() {
    local input_dir="$1"
    local output_dir="$2"
    echo "Generating screenshots..."
    screenshot_script_path="$script_dir/screenshot.sh"
    bash "$screenshot_script_path" "$input_dir" "$output_dir"
    echo "Screenshots generated"
}

# Move and rename TI.msh files
for ti_dir in "$fem_dir"/TI_*; do
    if [ -d "$ti_dir" ]; then
        ti_msh_file="$ti_dir/TI.msh"
        if [ -e "$ti_msh_file" ]; then
            montage_name=$(basename "$ti_dir")
            new_name="${subject_id}_${montage_name}_TI.msh"
            new_path="$whole_brain_mesh_dir/$new_name"
            mv "$ti_msh_file" "$new_path"
            echo "Moved $ti_msh_file to $new_path"
        fi
    fi
done

# Extract fields (GM and WM) from TI.msh and save both in parcellated_mesh directory
for mesh_file in "$whole_brain_mesh_dir"/*.msh; do
    gm_output_file="$parcellated_mesh_dir/grey_$(basename "$mesh_file")"
    wm_output_file="$parcellated_mesh_dir/white_$(basename "$mesh_file")"  # Saving WM mesh in the same directory
    extract_fields "$mesh_file" "$gm_output_file" "$wm_output_file"
done

# Run the processing steps
run_visualize_montages
transform_parcellated_meshes_to_nifti
convert_t1_to_mni
process_mesh_files
run_sphere_analysis  
#generate_screenshots "$nifti_dir" "$screenshots_dir"

