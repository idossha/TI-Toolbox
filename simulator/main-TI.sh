#!/bin/bash

##############################################
# Ido Haber - ihaber@wisc.edu
# month, day, year
#
# This script orchestrates the full pipeline for Temporal Interference (TI) simulations
# using SimNIBS and other related tools. It handles directory setup, simulation execution,
# mesh processing, field extraction, NIfTI transformation, and other key tasks.
#
##############################################

set -e # Exit immediately if a command exits with a non-zero status

# Get the directory where this script is located
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
utils_dir="$(cd "$script_dir/../utils" && pwd)"

# Debug script location
echo "DEBUG: Script directory: $script_dir"
echo "DEBUG: Utils directory: $utils_dir"

# Gather arguments from the prompter script
subject_id=$1
conductivity=$2
subject_dir=$3
simulation_dir=$4
sim_mode=$5  
intensity=$6
electrode_shape=$7
dimensions=$8
thickness=$9
shift 9  # Shift past all the fixed arguments

# Debug input arguments
echo "DEBUG: Input Arguments:"
echo "  - subject_id: $subject_id"
echo "  - conductivity: $conductivity"
echo "  - subject_dir: $subject_dir"
echo "  - simulation_dir: $simulation_dir"
echo "  - sim_mode: $sim_mode"
echo "  - intensity: $intensity"
echo "  - electrode shape: $electrode_shape"
echo "  - dimensions: $dimensions"
echo "  - thickness: $thickness"

# Initialize arrays
selected_montages=()

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

echo "DEBUG: Selected montages: ${selected_montages[@]}"

# Set subdirectory paths
sim_dir="$simulation_dir"
echo "DEBUG: Simulation directory (sim_dir): $sim_dir"

# Function to setup directories for a montage
setup_montage_dirs() {
    local montage_name=$1
    local montage_dir="$sim_dir/${montage_name}"
    
    # Create main montage directory structure
    mkdir -p "$montage_dir/high_Frequency/mesh"
    mkdir -p "$montage_dir/high_Frequency/niftis"
    mkdir -p "$montage_dir/high_Frequency/analysis"
    mkdir -p "$montage_dir/TI/mesh"
    mkdir -p "$montage_dir/TI/niftis"
    mkdir -p "$montage_dir/TI/montage_imgs"
    mkdir -p "$montage_dir/documentation"  # Add documentation directory
    
    echo "Created directory structure for montage: $montage_name"
}

# Create directories for each montage
for montage in "${selected_montages[@]}"; do
    setup_montage_dirs "$montage"
done

# Debugging outputs
echo " "
echo "##############################"
echo "subject_id: $subject_id"
echo "conductivity: $conductivity"
echo "subject_dir: $subject_dir"
echo "simulation_dir: $simulation_dir"
echo "sim_mode: $sim_mode"
echo "intensity: $(echo "$intensity * 1000" | bc) mA (${intensity}A)"
echo "electrode shape: $electrode_shape"
echo "electrode dimensions: $dimensions mm"
echo "electrode thickness: $thickness mm"
echo "selected_montages: ${selected_montages[@]}"
echo "##############################"
echo " "

# Function to visualize montages
run_visualize_montages() {
    echo "Visualizing selected montages..."
    for montage in "${selected_montages[@]}"; do
        local montage_output_dir="$sim_dir/${montage}/TI/montage_imgs"
        echo "Calling visualize-montage.sh with arguments:"
        echo "Montage: $montage"
        echo "Sim Mode: $sim_mode"
        echo "Output Directory: $montage_output_dir"
        visualize_montage_script_path="$utils_dir/visualize-montage.sh"
        bash "$visualize_montage_script_path" "$montage" "$sim_mode" "$montage_output_dir"
    done
    echo "Montage visualization completed"
}

run_visualize_montages

# Create temporary directory for SimNIBS output
tmp_dir="$sim_dir/tmp"
mkdir -p "$tmp_dir"

# Main script: Run TI.py with the selected parameters
simnibs_python "$script_dir/TI.py" "$subject_id" "$conductivity" "$subject_dir" "$simulation_dir" "$intensity" "$electrode_shape" "$dimensions" "$thickness" "${selected_montages[@]}"

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
    local input_mesh="$1"
    local output_dir="$2"
    echo "Transforming mesh to NIfTI in subject and MNI space..."
    mesh2nii_script_path="$script_dir/mesh2nii_loop.sh"
    bash "$mesh2nii_script_path" "$subject_id" "$subject_dir" "$input_mesh" "$output_dir"
    echo "Mesh to NIfTI transformation completed"
}

# Convert T1 to MNI space
convert_t1_to_mni() {
    echo "DEBUG: Converting T1 to MNI space..."
    echo "DEBUG: Current directory: $(pwd)"
    echo "DEBUG: Variables for T1 conversion:"
    echo "  - subject_dir: $subject_dir"
    echo "  - subject_id: $subject_id"
    
    local m2m_dir="$subject_dir/${subject_id}/SimNIBS/m2m_${subject_id}"
    local t1_file="$m2m_dir/T1.nii.gz"
    local output_file="$m2m_dir/T1_${subject_id}"
    
    echo "DEBUG: Constructed paths:"
    echo "  - m2m_dir: $m2m_dir"
    echo "  - t1_file: $t1_file"
    echo "  - output_file: $output_file"
    
    # Check if directories and files exist
    echo "DEBUG: Directory/File checks:"
    echo "  - subject_dir exists: $([ -d "$subject_dir" ] && echo "YES" || echo "NO")"
    echo "  - m2m_dir exists: $([ -d "$m2m_dir" ] && echo "YES" || echo "NO")"
    echo "  - t1_file exists: $([ -f "$t1_file" ] && echo "YES" || echo "NO")"
    
    # List contents of relevant directories if they exist
    if [ -d "$subject_dir" ]; then
        echo "DEBUG: Contents of subject_dir ($subject_dir):"
        ls -la "$subject_dir"
    fi
    
    if [ -d "$m2m_dir" ]; then
        echo "DEBUG: Contents of m2m_dir ($m2m_dir):"
        ls -la "$m2m_dir"
    fi
    
    echo "DEBUG: About to run subject2mni command with:"
    echo "  subject2mni -i \"$t1_file\" -m \"$m2m_dir\" -o \"$output_file\""
    
    subject2mni -i "$t1_file" -m "$m2m_dir" -o "$output_file"
    local cmd_status=$?
    echo "DEBUG: subject2mni command exit status: $cmd_status"
    
    if [ $cmd_status -eq 0 ]; then
        echo "T1 conversion to MNI completed: $output_file"
    else
        echo "ERROR: T1 conversion failed with status $cmd_status"
    fi
}

convert_t1_to_mni

# Process each montage's simulation results
for montage in "${selected_montages[@]}"; do
    tmp_montage_dir="$tmp_dir/$montage"
    montage_dir="$sim_dir/$montage"
    
    # Skip if temporary directory doesn't exist
    if [ ! -d "$tmp_montage_dir" ]; then
        echo "Warning: No simulation results found for montage $montage"
        continue
    fi
    
    # Create all necessary directories
    mkdir -p "$montage_dir/high_Frequency/mesh"
    mkdir -p "$montage_dir/high_Frequency/niftis"
    mkdir -p "$montage_dir/high_Frequency/analysis"
    mkdir -p "$montage_dir/TI/mesh"
    mkdir -p "$montage_dir/TI/niftis"
    mkdir -p "$montage_dir/TI/montage_imgs"
    mkdir -p "$montage_dir/documentation"
    
    # Move high frequency mesh files
    for pattern in "TDCS_1" "TDCS_2"; do
        for file in "$tmp_montage_dir"/*${pattern}*; do
            if [[ -f "$file" ]]; then
                if [[ "$file" == *".geo" || "$file" == *"scalar.msh" || "$file" == *"scalar.msh.opt" ]]; then
                    mv "$file" "$montage_dir/high_Frequency/mesh/"
                fi
            fi
        done
    done
    
    # Handle subject_volumes directory
    if [ -d "$tmp_montage_dir/subject_volumes" ]; then
        mv "$tmp_montage_dir/subject_volumes"/* "$montage_dir/high_Frequency/niftis/"
        rmdir "$tmp_montage_dir/subject_volumes"
    fi
    
    # Move fields_summary.txt to analysis
    if [ -f "$tmp_montage_dir/fields_summary.txt" ]; then
        mv "$tmp_montage_dir/fields_summary.txt" "$montage_dir/high_Frequency/analysis/"
    fi
    
    # Move log and mat files to documentation
    for file in "$tmp_montage_dir"/simnibs_simulation_*.{log,mat}; do
        if [ -f "$file" ]; then
            mv "$file" "$montage_dir/documentation/"
        fi
    done
    
    # Process TI mesh
    if [ -f "$tmp_montage_dir/TI.msh" ]; then
        # Move and rename TI mesh and its opt file
        mv "$tmp_montage_dir/TI.msh" "$montage_dir/TI/mesh/${subject_id}_${montage}_TI.msh"
        if [ -f "$tmp_montage_dir/TI.msh.opt" ]; then
            mv "$tmp_montage_dir/TI.msh.opt" "$montage_dir/TI/mesh/${subject_id}_${montage}_TI.msh.opt"
        fi
        
        # Extract GM and WM fields
        ti_mesh="$montage_dir/TI/mesh/${subject_id}_${montage}_TI.msh"
        gm_output="$montage_dir/TI/mesh/grey_${subject_id}_${montage}_TI.msh"
        wm_output="$montage_dir/TI/mesh/white_${subject_id}_${montage}_TI.msh"
        extract_fields "$ti_mesh" "$gm_output" "$wm_output"
        
        # Transform to NIfTI
        transform_parcellated_meshes_to_nifti "$montage_dir/TI/mesh" "$montage_dir/TI/niftis"
    fi
done

# Verify all files have been moved correctly
verify_files() {
    local montage_name=$1
    local montage_base_dir="$sim_dir/$montage_name"
    local missing_files=0

    # Check for essential files and directories
    essential_paths=(
        "$montage_base_dir/high_Frequency/mesh"
        "$montage_base_dir/high_Frequency/niftis"
        "$montage_base_dir/high_Frequency/analysis/fields_summary.txt"
        "$montage_base_dir/documentation"
        "$montage_base_dir/TI/mesh/${subject_id}_${montage_name}_TI.msh"
        "$montage_base_dir/TI/mesh/${subject_id}_${montage_name}_TI.msh.opt"
    )

    for path in "${essential_paths[@]}"; do
        if [ ! -e "$path" ]; then
            echo "Warning: Missing expected file or directory: $path"
            missing_files=$((missing_files + 1))
        fi
    done

    # Check if high frequency files exist
    if [ ! "$(ls -A "$montage_base_dir/high_Frequency/mesh" 2>/dev/null)" ] || [ ! "$(ls -A "$montage_base_dir/high_Frequency/niftis" 2>/dev/null)" ]; then
        echo "Warning: High frequency mesh or nifti directories are empty"
        missing_files=$((missing_files + 1))
    fi

    return $missing_files
}

# Verify files for each montage
all_files_present=true
for montage in "${selected_montages[@]}"; do
    if ! verify_files "$montage"; then
        all_files_present=false
        echo "Warning: Some files may not have been moved correctly for montage $montage"
    fi
done

if [ "$all_files_present" = true ]; then
    # Clean up temporary directory only if all files were moved successfully
    rm -rf "$tmp_dir"
    echo "Pipeline completed successfully!"
else
    echo "Warning: Some files may be missing. Please check the output directories."
    echo "Temporary files preserved in: $tmp_dir"
fi

