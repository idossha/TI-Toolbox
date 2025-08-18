#!/bin/bash

##############################################
# Ido Haber - ihaber@wisc.edu
# October 16, 2024
# Optimized for optimizer pipeline
#
# This script orchestrates the full pipeline for Multipolar Temporal Interference (mTI) simulations
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
set_logger_name "main-mTI"

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
shift 9
eeg_net=$1
shift 1

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

# Export the log file path for mTI.py to use
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
log_info "  - dimensions: $dimensions mm"
log_info "  - thickness: $thickness mm"
log_info "  - eeg_net: $eeg_net"

# Set subdirectory paths
sim_dir="$simulation_dir"
log_info "Simulation directory (sim_dir): $sim_dir"

# Function to setup directories for a montage
setup_montage_dirs() {
    local montage_name=$1
    local montage_dir="$sim_dir/${montage_name}"
    
    # Create flattened multipolar directory structure
    mkdir -p "$montage_dir/documentation"
    mkdir -p "$montage_dir/high_Frequency/analysis"
    mkdir -p "$montage_dir/high_Frequency/mesh"
    mkdir -p "$montage_dir/TI/mesh"
    mkdir -p "$montage_dir/TI/niftis"
    mkdir -p "$montage_dir/TI/surface_overlays"
    mkdir -p "$montage_dir/mTI/mesh"
    mkdir -p "$montage_dir/mTI/niftis"
    mkdir -p "$montage_dir/mTI/montage_imgs"
    
    log_info "Created multipolar directory structure for montage: $montage_name"
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
        local montage_output_dir="$montage_dir/mTI/montage_imgs"
        
        log_info "Visualizing montage: $montage"
        visualize_montage_script_path="$utils_dir/visualize-montage.sh"
        if ! bash "$visualize_montage_script_path" "$montage" "$sim_mode" "$eeg_net" "$montage_output_dir" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
            log_error "Failed to visualize montage: $montage"
            exit 1
        fi
        log_info "Montage visualization completed"
    done
}

# mTI pipeline writes directly to final directories (no temporary directory needed)

# Run the pipeline
run_visualize_montages

# Run mTI.py with the selected parameters
for montage in "${selected_montages[@]}"; do
    montage_dir="$sim_dir/$montage"
    log_info "Running SimNIBS simulation for montage: $montage"
done

# Pass all parameters to mTI.py
if ! simnibs_python "$script_dir/mTI.py" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$intensity" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" "${selected_montages[@]}" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
    log_error "SimNIBS simulation failed"
    exit 1
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
    
    # Convert T1 to MNI space
    convert_t1_to_mni
    
    # Check if simulation results exist in the montage directory (mTI.py writes directly there)
    if [ ! -d "$montage_dir" ]; then
        log_error "No simulation results found for montage: $montage"
        continue
    fi
    
    log_info "Processing simulation results for montage: $montage"
    
    # Move and rename high frequency mesh files to high_Frequency/mesh directory
    for i in {1..4}; do
        hf_letter=$(echo "A B C D" | cut -d' ' -f$i)
        for file in "$montage_dir"/*TDCS_${i}*; do
            if [[ -f "$file" ]]; then
                if [[ "$file" == *".geo" || "$file" == *"scalar.msh" || "$file" == *"scalar.msh.opt" ]]; then
                    filename=$(basename "$file")
                    # Rename from TDCS_1/2/3/4 to TDCS_A/B/C/D
                    new_filename=$(echo "$filename" | sed "s/TDCS_${i}/TDCS_${hf_letter}/g")
                    mv "$file" "$montage_dir/high_Frequency/mesh/$new_filename"
                    log_info "Moved and renamed $(basename "$file") to $new_filename in high frequency mesh directory"
                fi
            fi
        done
    done
    
    # Clean up subject_volumes directory (high frequency niftis not needed in new structure)
    if [ -d "$montage_dir/subject_volumes" ]; then
        rm -rf "$montage_dir/subject_volumes"
        log_info "Cleaned up subject volumes directory"
    fi
    
    # Move fields_summary.txt to analysis directory (similar to regular TI pipeline)
    if [ -f "$montage_dir/fields_summary.txt" ]; then
        mv "$montage_dir/fields_summary.txt" "$montage_dir/high_Frequency/analysis/"
        log_info "Moved fields summary to analysis directory"
    fi
    
    # Move log and mat files to documentation
    for file in "$montage_dir"/simnibs_simulation_*.{log,mat}; do
        if [ -f "$file" ]; then
            mv "$file" "$montage_dir/documentation/"
            log_info "Moved $(basename "$file") to documentation directory"
        fi
    done
    
    # Process TI intermediate meshes (TI_AB and TI_CD) - move directly to TI/mesh
    if [ -f "$montage_dir/TI_AB.msh" ]; then
        log_info "Processing TI_AB mesh"
        mv "$montage_dir/TI_AB.msh" "$montage_dir/TI/mesh/${montage}_TI_AB.msh"
        if [ -f "$montage_dir/TI_AB.msh.opt" ]; then
            mv "$montage_dir/TI_AB.msh.opt" "$montage_dir/TI/mesh/${montage}_TI_AB.msh.opt"
        fi
        log_info "Moved TI_AB mesh files"
        
        # Extract GM and WM fields for TI_AB
        ti_ab_mesh="$montage_dir/TI/mesh/${montage}_TI_AB.msh"
        gm_ti_ab="$montage_dir/TI/mesh/grey_${montage}_TI_AB.msh"
        wm_ti_ab="$montage_dir/TI/mesh/white_${montage}_TI_AB.msh"
        extract_fields "$ti_ab_mesh" "$gm_ti_ab" "$wm_ti_ab"
    fi
    
    if [ -f "$montage_dir/TI_CD.msh" ]; then
        log_info "Processing TI_CD mesh"
        mv "$montage_dir/TI_CD.msh" "$montage_dir/TI/mesh/${montage}_TI_CD.msh"
        if [ -f "$montage_dir/TI_CD.msh.opt" ]; then
            mv "$montage_dir/TI_CD.msh.opt" "$montage_dir/TI/mesh/${montage}_TI_CD.msh.opt"
        fi
        log_info "Moved TI_CD mesh files"
        
        # Extract GM and WM fields for TI_CD
        ti_cd_mesh="$montage_dir/TI/mesh/${montage}_TI_CD.msh"
        gm_ti_cd="$montage_dir/TI/mesh/grey_${montage}_TI_CD.msh"
        wm_ti_cd="$montage_dir/TI/mesh/white_${montage}_TI_CD.msh"
        extract_fields "$ti_cd_mesh" "$gm_ti_cd" "$wm_ti_cd"
    fi

    # Process mTI mesh
    if [ -f "$montage_dir/mTI.msh" ]; then
        log_info "Processing mTI mesh"
        
        # Move and rename mTI mesh and its opt file to mTI/mesh
        mv "$montage_dir/mTI.msh" "$montage_dir/mTI/mesh/${montage}_mTI.msh"
        if [ -f "$montage_dir/mTI.msh.opt" ]; then
            mv "$montage_dir/mTI.msh.opt" "$montage_dir/mTI/mesh/${montage}_mTI.msh.opt"
        fi
        log_info "Moved and renamed mTI mesh files"
        
        # Extract GM and WM fields for mTI
        mti_mesh="$montage_dir/mTI/mesh/${montage}_mTI.msh"
        gm_output="$montage_dir/mTI/mesh/grey_${montage}_mTI.msh"
        wm_output="$montage_dir/mTI/mesh/white_${montage}_mTI.msh"
        extract_fields "$mti_mesh" "$gm_output" "$wm_output"
        
        # Transform TI meshes to NIfTI
        # Create temporary directory for TI NIfTI conversion
        temp_ti_nifti_dir="$sim_dir/${montage}_ti_nifti_conversion"
        mkdir -p "$temp_ti_nifti_dir"
        
        # Copy TI intermediate meshes for NIfTI conversion
        if [ -f "$montage_dir/TI/mesh/${montage}_TI_AB.msh" ]; then
            cp "$montage_dir/TI/mesh/${montage}_TI_AB.msh" "$temp_ti_nifti_dir/"
        fi
        if [ -f "$montage_dir/TI/mesh/grey_${montage}_TI_AB.msh" ]; then
            cp "$montage_dir/TI/mesh/grey_${montage}_TI_AB.msh" "$temp_ti_nifti_dir/"
        fi
        if [ -f "$montage_dir/TI/mesh/white_${montage}_TI_AB.msh" ]; then
            cp "$montage_dir/TI/mesh/white_${montage}_TI_AB.msh" "$temp_ti_nifti_dir/"
        fi
        
        if [ -f "$montage_dir/TI/mesh/${montage}_TI_CD.msh" ]; then
            cp "$montage_dir/TI/mesh/${montage}_TI_CD.msh" "$temp_ti_nifti_dir/"
        fi
        if [ -f "$montage_dir/TI/mesh/grey_${montage}_TI_CD.msh" ]; then
            cp "$montage_dir/TI/mesh/grey_${montage}_TI_CD.msh" "$temp_ti_nifti_dir/"
        fi
        if [ -f "$montage_dir/TI/mesh/white_${montage}_TI_CD.msh" ]; then
            cp "$montage_dir/TI/mesh/white_${montage}_TI_CD.msh" "$temp_ti_nifti_dir/"
        fi
        
        # Convert TI meshes to NIfTI and place in TI/niftis directory
        transform_parcellated_meshes_to_nifti "$temp_ti_nifti_dir" "$montage_dir/TI/niftis"
        rm -rf "$temp_ti_nifti_dir"
        
        # Transform mTI meshes to NIfTI
        # Create temporary directory for mTI NIfTI conversion
        temp_mti_nifti_dir="$sim_dir/${montage}_mti_nifti_conversion"
        mkdir -p "$temp_mti_nifti_dir"
        
        # Copy mTI meshes for NIfTI conversion
        cp "$montage_dir/mTI/mesh/${montage}_mTI.msh" "$temp_mti_nifti_dir/"
        if [ -f "$montage_dir/mTI/mesh/grey_${montage}_mTI.msh" ]; then
            cp "$montage_dir/mTI/mesh/grey_${montage}_mTI.msh" "$temp_mti_nifti_dir/"
        fi
        if [ -f "$montage_dir/mTI/mesh/white_${montage}_mTI.msh" ]; then
            cp "$montage_dir/mTI/mesh/white_${montage}_mTI.msh" "$temp_mti_nifti_dir/"
        fi
        
        # Convert mTI meshes to NIfTI and place in mTI/niftis directory
        transform_parcellated_meshes_to_nifti "$temp_mti_nifti_dir" "$montage_dir/mTI/niftis"
        rm -rf "$temp_mti_nifti_dir"
    fi
done

# Verify all files have been moved correctly
verify_files() {
    local montage_name=$1
    local montage_base_dir="$sim_dir/$montage_name"
    local missing_files=0

    log_info "Verifying files for montage: $montage_name"

    # Check for essential directories
    essential_paths=(
        "$montage_base_dir/high_Frequency/mesh"
        "$montage_base_dir/high_Frequency/analysis"
        "$montage_base_dir/TI/mesh"
        "$montage_base_dir/TI/niftis"
        "$montage_base_dir/TI/surface_overlays"
        "$montage_base_dir/documentation"
        "$montage_base_dir/mTI/mesh"
        "$montage_base_dir/mTI/niftis"
        "$montage_base_dir/mTI/montage_imgs"
    )

    for path in "${essential_paths[@]}"; do
        if [ ! -e "$path" ]; then
            log_error "Missing: $path"
            missing_files=$((missing_files + 1))
        fi
    done

    # Check for essential files
    essential_files=(
        "$montage_base_dir/mTI/mesh/${montage_name}_mTI.msh"
        "$montage_base_dir/TI/mesh/${montage_name}_TI_AB.msh"
        "$montage_base_dir/TI/mesh/${montage_name}_TI_CD.msh"
    )

    for file in "${essential_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_error "Missing essential file: $file"
            missing_files=$((missing_files + 1))
        fi
    done

    # Check if high frequency mesh directory has files with correct naming
    hf_files_missing=0
    for hf_letter in A B C D; do
        if [ ! -f "$montage_base_dir/high_Frequency/mesh/${subject_id}_TDCS_${hf_letter}_scalar.msh" ]; then
            log_error "Missing high frequency file: ${subject_id}_TDCS_${hf_letter}_scalar.msh"
            hf_files_missing=$((hf_files_missing + 1))
        fi
    done
    
    if [ $hf_files_missing -gt 0 ]; then
        missing_files=$((missing_files + hf_files_missing))
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
    for montage in "${selected_montages[@]}"; do
        log_info "Pipeline completed successfully for montage: $montage"
        log_info "Simulation results saved to: $sim_dir/$montage"
        log_info "----------------------------------------"
    done
else
    for montage in "${selected_montages[@]}"; do
        log_error "Some files may be missing for montage: $montage"
        log_error "Check simulation directory: $sim_dir/$montage"
        log_error "----------------------------------------"
    done
fi


