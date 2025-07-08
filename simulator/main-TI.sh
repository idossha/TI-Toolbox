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

# Set timestamp for consistent log naming
timestamp=$(date +%Y%m%d_%H%M%S)

# Source the logging utility
source "$utils_dir/bash_logging.sh"

# Initialize logging
set_logger_name "main-TI"

# Gather arguments from the prompter script
subject_id=$1
conductivity=$2
project_dir=$3
simulation_dir=$4
sim_mode=$5
intensity=$6
electrode_shape=$7
dimensions=$8
thickness=$9
shift 9  # Shift past all the fixed arguments
eeg_net=$1  # Get the EEG net parameter
shift 1  # Shift past the EEG net parameter

# Construct BIDS paths
derivatives_dir="$project_dir/derivatives"
simnibs_dir="$derivatives_dir/SimNIBS/sub-$subject_id"
m2m_dir="$simnibs_dir/m2m_$subject_id"

# Update simulation directory to be under the BIDS derivatives structure
simulation_dir="$simnibs_dir/Simulations"

# Initialize arrays for montage parsing
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

# Set up logging in the montage-specific documentation directory
first_montage=${selected_montages[0]}
logs_dir="$derivatives_dir/logs/sub-$subject_id"
mkdir -p "$logs_dir"
log_file="${logs_dir}/simulator_${timestamp}.log"
set_log_file "$log_file"

# Export the log file path for TI.py to use
export TI_LOG_FILE="$log_file"

# Configure external loggers
configure_external_loggers '["simnibs", "charm", "mesh_io"]'

# Debug script location
log_info "Script directory: $script_dir"
log_info "Utils directory: $utils_dir"

# Debug input arguments
log_info "Input Arguments:"
log_info "  - subject_id: $subject_id"
log_info "  - conductivity: $conductivity"
log_info "  - project_dir: $project_dir"
log_info "  - simnibs_dir: $simnibs_dir"
log_info "  - m2m_dir: $m2m_dir"
log_info "  - simulation_dir: $simulation_dir"
log_info "  - sim_mode: $sim_mode"
log_info "  - intensity: $intensity A"
log_info "  - electrode shape: $electrode_shape"
log_info "  - dimensions: $dimensions"
log_info "  - thickness: $thickness"
log_info "  - eeg_net: $eeg_net"

# Set subdirectory paths
sim_dir="$simulation_dir"
log_info "Simulation directory (sim_dir): $sim_dir"

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
    mkdir -p "$montage_dir/TI/surface_overlays"
    mkdir -p "$montage_dir/TI/montage_imgs"
    mkdir -p "$montage_dir/documentation"
    
    log_info "Created directory structure for montage: $montage_name"
}

# Create directories for each montage
for montage in "${selected_montages[@]}"; do
    setup_montage_dirs "$montage"
    montage_dir="$sim_dir/$montage"
    
    # Log simulation parameters
    log_info "Starting simulation for montage: $montage"
    log_info "Simulation parameters:"
    log_info "- Subject ID: $subject_id"
    log_info "- Conductivity: $conductivity"
    log_info "- Simulation Mode: $sim_mode"
    log_info "- Intensity: $intensity A"
    log_info "- Electrode Shape: $electrode_shape"
    log_info "- Electrode Dimensions: $dimensions mm"
    log_info "- Electrode Thickness: $thickness mm"
done

# Function to visualize montages
run_visualize_montages() {
    for montage in "${selected_montages[@]}"; do
        local montage_dir="$sim_dir/$montage"
        local montage_output_dir="$montage_dir/TI/montage_imgs"
        
        log_info "Visualizing montage: $montage"
        visualize_montage_script_path="$utils_dir/visualize-montage.sh"
        if ! bash "$visualize_montage_script_path" "$montage" "$sim_mode" "$eeg_net" "$montage_output_dir" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
            log_error "Failed to visualize montage: $montage"
            exit 1
        fi
        log_info "Montage visualization completed"
    done
}

# Create temporary directory for SimNIBS output
tmp_dir="$sim_dir/tmp"
mkdir -p "$tmp_dir"

# Run the pipeline
run_visualize_montages

# Run TI.py with the selected parameters
for montage in "${selected_montages[@]}"; do
    montage_dir="$sim_dir/$montage"
    log_info "Running SimNIBS simulation for montage: $montage"
done

# Pass all parameters to TI.py
if ! simnibs_python "$script_dir/TI.py" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$intensity" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" "${selected_montages[@]}" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
    log_error "SimNIBS simulation failed"
    exit 1
fi

# For flex-search mode, discover the montages that were created by TI.py
if [ "$sim_mode" = "FLEX_TI" ] && [ ${#selected_montages[@]} -eq 0 ]; then
    log_info "Flex-search mode detected - discovering created montages"
    flex_montages=()
    if [ -d "$sim_dir" ]; then
        for montage_dir in "$sim_dir"/*/; do
            if [ -d "$montage_dir" ]; then
                montage_name=$(basename "$montage_dir")
                # Skip the tmp directory
                if [ "$montage_name" != "tmp" ]; then
                    flex_montages+=("$montage_name")
                    log_info "Found flex montage: $montage_name"
                fi
            fi
        done
    fi
    # Use flex montages for post-processing
    selected_montages=("${flex_montages[@]}")
    log_info "Will process ${#selected_montages[@]} flex montages"
fi

# Function to extract fields (GM and WM meshes)
extract_fields() {
    local input_file="$1"
    local gm_output_file="$2"
    local wm_output_file="$3"
    
    log_info "Extracting fields from: $(basename "$input_file")"
    field_extract_script_path="$script_dir/field_extract.py"
    if ! simnibs_python "$field_extract_script_path" "$input_file" --gm_output_file "$gm_output_file" --wm_output_file "$wm_output_file" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
        log_error "Field extraction failed"
        return 1
    fi
    log_info "Field extraction completed"
}

# Function to transform parcellated meshes to NIfTI
transform_parcellated_meshes_to_nifti() {
    local input_mesh="$1"
    local output_dir="$2"
    
    log_info "Converting meshes to NIfTI format"
    mesh2nii_script_path="$script_dir/mesh2nii_loop.sh"
    if ! bash "$mesh2nii_script_path" "$subject_id" "$m2m_dir" "$input_mesh" "$output_dir" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
        log_error "Mesh to NIfTI conversion failed"
        return 1
    fi
    log_info "Mesh to NIfTI conversion completed"
}

# Convert T1 to MNI space
convert_t1_to_mni() {
    local t1_file="$m2m_dir/T1.nii.gz"
    local output_file="$m2m_dir/T1_${subject_id}"
    
    log_info "Converting T1 to MNI space"
    if ! subject2mni -i "$t1_file" -m "$m2m_dir" -o "$output_file" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
        log_error "T1 to MNI conversion failed"
        return 1
    fi
    log_info "T1 to MNI conversion completed"
}

# Process each montage's simulation results
for montage in "${selected_montages[@]}"; do
    montage_dir="$sim_dir/$montage"
    tmp_montage_dir="$tmp_dir/$montage"
    
    # Convert T1 to MNI space
    convert_t1_to_mni
    
    # Skip if temporary directory doesn't exist
    if [ ! -d "$tmp_montage_dir" ]; then
        log_error "No simulation results found for montage: $montage"
        continue
    fi
    
    log_info "Processing simulation results for montage: $montage"
    
    # Move high frequency mesh files
    for pattern in "TDCS_1" "TDCS_2"; do
        for file in "$tmp_montage_dir"/*${pattern}*; do
            if [[ -f "$file" ]]; then
                if [[ "$file" == *".geo" || "$file" == *"scalar.msh" || "$file" == *"scalar.msh.opt" ]]; then
                    mv "$file" "$montage_dir/high_Frequency/mesh/"
                    log_info "Moved $(basename "$file") to high frequency mesh directory"
                fi
            fi
        done
    done
    
    # Handle subject_volumes directory
    if [ -d "$tmp_montage_dir/subject_volumes" ]; then
        mv "$tmp_montage_dir/subject_volumes"/* "$montage_dir/high_Frequency/niftis/"
        rmdir "$tmp_montage_dir/subject_volumes"
        log_info "Moved subject volumes to high frequency niftis directory"
    fi
    
    # Handle subject_overlays directory (surface files)
    if [ -d "$tmp_montage_dir/subject_overlays" ]; then
        mv "$tmp_montage_dir/subject_overlays"/* "$montage_dir/TI/surface_overlays/"
        rmdir "$tmp_montage_dir/subject_overlays"
        log_info "Moved subject overlays to TI surface overlays directory"
    fi
    
    # Move fields_summary.txt to analysis
    if [ -f "$tmp_montage_dir/fields_summary.txt" ]; then
        mv "$tmp_montage_dir/fields_summary.txt" "$montage_dir/high_Frequency/analysis/"
        log_info "Moved fields summary to analysis directory"
    fi
    
    # Move log and mat files to documentation
    for file in "$tmp_montage_dir"/simnibs_simulation_*.{log,mat}; do
        if [ -f "$file" ]; then
            mv "$file" "$montage_dir/documentation/"
            log_info "Moved $(basename "$file") to documentation directory"
        fi
    done
    
    # Process TI mesh
    if [ -f "$tmp_montage_dir/TI.msh" ]; then
        log_info "Processing TI mesh"
        
        # Move and rename TI mesh and its opt file (without subject ID)
        mv "$tmp_montage_dir/TI.msh" "$montage_dir/TI/mesh/${montage}_TI.msh"
        if [ -f "$tmp_montage_dir/TI.msh.opt" ]; then
            mv "$tmp_montage_dir/TI.msh.opt" "$montage_dir/TI/mesh/${montage}_TI.msh.opt"
        fi
        log_info "Moved and renamed TI mesh files"
        
        # Extract GM and WM fields (without subject ID)
        ti_mesh="$montage_dir/TI/mesh/${montage}_TI.msh"
        gm_output="$montage_dir/TI/mesh/grey_${montage}_TI.msh"
        wm_output="$montage_dir/TI/mesh/white_${montage}_TI.msh"
        extract_fields "$ti_mesh" "$gm_output" "$wm_output"
        
        # Transform volume meshes to NIfTI (excluding central surface meshes)
        # Create temporary directory with only volume meshes for NIfTI conversion
        temp_nifti_dir="$tmp_dir/${montage}_nifti_conversion"
        mkdir -p "$temp_nifti_dir"
        
        # Copy only volume mesh files (exclude TI_central files)
        cp "$montage_dir/TI/mesh/${montage}_TI.msh" "$temp_nifti_dir/"
        if [ -f "$montage_dir/TI/mesh/grey_${montage}_TI.msh" ]; then
            cp "$montage_dir/TI/mesh/grey_${montage}_TI.msh" "$temp_nifti_dir/"
        fi
        if [ -f "$montage_dir/TI/mesh/white_${montage}_TI.msh" ]; then
            cp "$montage_dir/TI/mesh/white_${montage}_TI.msh" "$temp_nifti_dir/"
        fi
        
        # Convert only volume meshes to NIfTI
        transform_parcellated_meshes_to_nifti "$temp_nifti_dir" "$montage_dir/TI/niftis"
        
        # Clean up temporary directory
        rm -rf "$temp_nifti_dir"
    fi
    
    # Process TI central surface mesh (middle cortical layer) - AFTER NIfTI conversion
    if [ -f "$tmp_montage_dir/TI_central.msh" ]; then
        log_info "Processing TI central surface mesh (surface-only, no NIfTI conversion)"
        
        # Move and rename TI central mesh and its opt file
        mv "$tmp_montage_dir/TI_central.msh" "$montage_dir/TI/mesh/${montage}_TI_central.msh"
        if [ -f "$tmp_montage_dir/TI_central.msh.opt" ]; then
            mv "$tmp_montage_dir/TI_central.msh.opt" "$montage_dir/TI/mesh/${montage}_TI_central.msh.opt"
        fi
        log_info "Moved and renamed TI central surface mesh files (surface format preserved)"
    fi
done

# Verify all files have been moved correctly
verify_files() {
    local montage_name=$1
    local montage_base_dir="$sim_dir/$montage_name"
    local missing_files=0

    log_info "Verifying files for montage: $montage_name"

    # Check for essential files and directories
    essential_paths=(
        "$montage_base_dir/high_Frequency/mesh"
        "$montage_base_dir/high_Frequency/niftis"
        "$montage_base_dir/high_Frequency/analysis/fields_summary.txt"
        "$montage_base_dir/documentation"
        "$montage_base_dir/TI/mesh/${montage_name}_TI.msh"
        "$montage_base_dir/TI/mesh/${montage_name}_TI.msh.opt"
        "$montage_base_dir/TI/mesh/${montage_name}_TI_central.msh"
        "$montage_base_dir/TI/surface_overlays"
    )

    for path in "${essential_paths[@]}"; do
        if [ ! -e "$path" ]; then
            log_error "Missing: $path"
            missing_files=$((missing_files + 1))
        fi
    done

    # Check if high frequency files exist
    if [ ! "$(ls -A "$montage_base_dir/high_Frequency/mesh" 2>/dev/null)" ] || [ ! "$(ls -A "$montage_base_dir/high_Frequency/niftis" 2>/dev/null)" ]; then
        log_error "High frequency directories are empty"
        missing_files=$((missing_files + 1))
    fi

    return $missing_files
}

# Verify files for each montage
all_files_present=true
for montage in "${selected_montages[@]}"; do
    if ! verify_files "$montage"; then
        all_files_present=false
        log_error "File verification failed for montage: $montage"
    fi
done

if [ "$all_files_present" = true ]; then
    # Clean up temporary directory only if all files were moved successfully
    rm -rf "$tmp_dir"
    for montage in "${selected_montages[@]}"; do
        log_info "Pipeline completed successfully for montage: $montage"
        log_info "----------------------------------------"
    done
else
    for montage in "${selected_montages[@]}"; do
        log_error "Some files may be missing for montage: $montage"
        log_error "Temporary files preserved in: $tmp_dir"
        log_error "----------------------------------------"
    done
fi
