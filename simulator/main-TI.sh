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

# Initialize logging
setup_logging() {
    local montage_dir="$1"
    local log_file="$montage_dir/documentation/sim_pipeline.log"
    mkdir -p "$(dirname "$log_file")"
    # Clear the log file if it exists
    > "$log_file"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting TI simulation pipeline" >> "$log_file"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Script version: 2.0" >> "$log_file"
    echo "----------------------------------------" >> "$log_file"
}

# Logging function
log() {
    local level="$1"
    local message="$2"
    local montage_dir="$3"
    local log_file="$montage_dir/documentation/sim_pipeline.log"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Format the message based on level
    case "$level" in
        "INFO")
            echo "[$timestamp] [INFO] $message" >> "$log_file"
            echo "$message"  # Clean console output
            ;;
        "DEBUG")
            echo "[$timestamp] [DEBUG] $message" >> "$log_file"
            ;;
        "ERROR")
            echo "[$timestamp] [ERROR] $message" >> "$log_file"
            echo "ERROR: $message" >&2  # Error messages to stderr
            ;;
        *)
            echo "[$timestamp] $message" >> "$log_file"
            ;;
    esac
}

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
eeg_net=$1  # Get the EEG net parameter
shift 1  # Shift past the EEG net parameter

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
echo "  - eeg_net: $eeg_net"

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
    mkdir -p "$montage_dir/documentation"
    
    # Initialize logging for this montage
    setup_logging "$montage_dir"
    
    # Log directory creation
    log "DEBUG" "Created directory structure for montage: $montage_name" "$montage_dir"
}

# Create directories for each montage
for montage in "${selected_montages[@]}"; do
    setup_montage_dirs "$montage"
    montage_dir="$sim_dir/$montage"
    
    # Log simulation parameters
    log "INFO" "Starting simulation for montage: $montage" "$montage_dir"
    log "DEBUG" "Simulation parameters:" "$montage_dir"
    log "DEBUG" "- Subject ID: $subject_id" "$montage_dir"
    log "DEBUG" "- Conductivity: $conductivity" "$montage_dir"
    log "DEBUG" "- Simulation Mode: $sim_mode" "$montage_dir"
    log "DEBUG" "- Intensity: $(echo "$intensity * 1000" | bc) mA" "$montage_dir"
    log "DEBUG" "- Electrode Shape: $electrode_shape" "$montage_dir"
    log "DEBUG" "- Electrode Dimensions: $dimensions mm" "$montage_dir"
    log "DEBUG" "- Electrode Thickness: $thickness mm" "$montage_dir"
done

# Function to visualize montages
run_visualize_montages() {
    for montage in "${selected_montages[@]}"; do
        local montage_dir="$sim_dir/$montage"
        local montage_output_dir="$montage_dir/TI/montage_imgs"
        
        log "INFO" "Visualizing montage: $montage" "$montage_dir"
        visualize_montage_script_path="$utils_dir/visualize-montage.sh"
        if ! bash "$visualize_montage_script_path" "$montage" "$sim_mode" "$eeg_net" "$montage_output_dir"; then
            log "ERROR" "Failed to visualize montage: $montage" "$montage_dir"
            exit 1
        fi
        log "INFO" "Montage visualization completed" "$montage_dir"
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
    log "INFO" "Running SimNIBS simulation for montage: $montage" "$montage_dir"
done

simnibs_python "$script_dir/TI.py" "$subject_id" "$conductivity" "$subject_dir" "$simulation_dir" "$intensity" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" "${selected_montages[@]}"

# Function to extract fields (GM and WM meshes)
extract_fields() {
    local input_file="$1"
    local gm_output_file="$2"
    local wm_output_file="$3"
    local montage_dir="$4"
    
    log "INFO" "Extracting fields from: $(basename "$input_file")" "$montage_dir"
    field_extract_script_path="$script_dir/field_extract.py"
    if ! simnibs_python "$field_extract_script_path" "$input_file" --gm_output_file "$gm_output_file" --wm_output_file "$wm_output_file"; then
        log "ERROR" "Field extraction failed" "$montage_dir"
        return 1
    fi
    log "INFO" "Field extraction completed" "$montage_dir"
}

# Function to transform parcellated meshes to NIfTI
transform_parcellated_meshes_to_nifti() {
    local input_mesh="$1"
    local output_dir="$2"
    local montage_dir="$3"
    
    log "INFO" "Converting meshes to NIfTI format" "$montage_dir"
    mesh2nii_script_path="$script_dir/mesh2nii_loop.sh"
    if ! bash "$mesh2nii_script_path" "$subject_id" "$subject_dir" "$input_mesh" "$output_dir"; then
        log "ERROR" "Mesh to NIfTI conversion failed" "$montage_dir"
        return 1
    fi
    log "INFO" "Mesh to NIfTI conversion completed" "$montage_dir"
}

# Convert T1 to MNI space
convert_t1_to_mni() {
    local montage_dir="$1"
    local m2m_dir="$subject_dir/${subject_id}/SimNIBS/m2m_${subject_id}"
    local t1_file="$m2m_dir/T1.nii.gz"
    local output_file="$m2m_dir/T1_${subject_id}"
    
    log "INFO" "Converting T1 to MNI space" "$montage_dir"
    if ! subject2mni -i "$t1_file" -m "$m2m_dir" -o "$output_file"; then
        log "ERROR" "T1 to MNI conversion failed" "$montage_dir"
        return 1
    fi
    log "INFO" "T1 to MNI conversion completed" "$montage_dir"
}

# Process each montage's simulation results
for montage in "${selected_montages[@]}"; do
    montage_dir="$sim_dir/$montage"
    tmp_montage_dir="$tmp_dir/$montage"
    
    # Convert T1 to MNI space
    convert_t1_to_mni "$montage_dir"
    
    # Skip if temporary directory doesn't exist
    if [ ! -d "$tmp_montage_dir" ]; then
        log "ERROR" "No simulation results found for montage: $montage" "$montage_dir"
        continue
    fi
    
    log "INFO" "Processing simulation results for montage: $montage" "$montage_dir"
    
    # Move high frequency mesh files
    for pattern in "TDCS_1" "TDCS_2"; do
        for file in "$tmp_montage_dir"/*${pattern}*; do
            if [[ -f "$file" ]]; then
                if [[ "$file" == *".geo" || "$file" == *"scalar.msh" || "$file" == *"scalar.msh.opt" ]]; then
                    mv "$file" "$montage_dir/high_Frequency/mesh/"
                    log "DEBUG" "Moved $(basename "$file") to high frequency mesh directory" "$montage_dir"
                fi
            fi
        done
    done
    
    # Handle subject_volumes directory
    if [ -d "$tmp_montage_dir/subject_volumes" ]; then
        mv "$tmp_montage_dir/subject_volumes"/* "$montage_dir/high_Frequency/niftis/"
        rmdir "$tmp_montage_dir/subject_volumes"
        log "DEBUG" "Moved subject volumes to high frequency niftis directory" "$montage_dir"
    fi
    
    # Move fields_summary.txt to analysis
    if [ -f "$tmp_montage_dir/fields_summary.txt" ]; then
        mv "$tmp_montage_dir/fields_summary.txt" "$montage_dir/high_Frequency/analysis/"
        log "DEBUG" "Moved fields summary to analysis directory" "$montage_dir"
    fi
    
    # Move log and mat files to documentation
    for file in "$tmp_montage_dir"/simnibs_simulation_*.{log,mat}; do
        if [ -f "$file" ]; then
            mv "$file" "$montage_dir/documentation/"
            log "DEBUG" "Moved $(basename "$file") to documentation directory" "$montage_dir"
        fi
    done
    
    # Process TI mesh
    if [ -f "$tmp_montage_dir/TI.msh" ]; then
        log "INFO" "Processing TI mesh" "$montage_dir"
        
        # Move and rename TI mesh and its opt file
        mv "$tmp_montage_dir/TI.msh" "$montage_dir/TI/mesh/${subject_id}_${montage}_TI.msh"
        if [ -f "$tmp_montage_dir/TI.msh.opt" ]; then
            mv "$tmp_montage_dir/TI.msh.opt" "$montage_dir/TI/mesh/${subject_id}_${montage}_TI.msh.opt"
        fi
        log "DEBUG" "Moved and renamed TI mesh files" "$montage_dir"
        
        # Extract GM and WM fields
        ti_mesh="$montage_dir/TI/mesh/${subject_id}_${montage}_TI.msh"
        gm_output="$montage_dir/TI/mesh/grey_${subject_id}_${montage}_TI.msh"
        wm_output="$montage_dir/TI/mesh/white_${subject_id}_${montage}_TI.msh"
        extract_fields "$ti_mesh" "$gm_output" "$wm_output" "$montage_dir"
        
        # Transform to NIfTI
        transform_parcellated_meshes_to_nifti "$montage_dir/TI/mesh" "$montage_dir/TI/niftis" "$montage_dir"
    fi
done

# Verify all files have been moved correctly
verify_files() {
    local montage_name=$1
    local montage_base_dir="$sim_dir/$montage_name"
    local missing_files=0

    log "INFO" "Verifying files for montage: $montage_name" "$montage_base_dir"

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
            log "ERROR" "Missing: $path" "$montage_base_dir"
            missing_files=$((missing_files + 1))
        fi
    done

    # Check if high frequency files exist
    if [ ! "$(ls -A "$montage_base_dir/high_Frequency/mesh" 2>/dev/null)" ] || [ ! "$(ls -A "$montage_base_dir/high_Frequency/niftis" 2>/dev/null)" ]; then
        log "ERROR" "High frequency directories are empty" "$montage_base_dir"
        missing_files=$((missing_files + 1))
    fi

    return $missing_files
}

# Verify files for each montage
all_files_present=true
for montage in "${selected_montages[@]}"; do
    montage_dir="$sim_dir/$montage"
    if ! verify_files "$montage"; then
        all_files_present=false
        log "ERROR" "File verification failed for montage: $montage" "$montage_dir"
    fi
done

if [ "$all_files_present" = true ]; then
    # Clean up temporary directory only if all files were moved successfully
    rm -rf "$tmp_dir"
    for montage in "${selected_montages[@]}"; do
        montage_dir="$sim_dir/$montage"
        log "INFO" "Pipeline completed successfully for montage: $montage" "$montage_dir"
        log "INFO" "----------------------------------------" "$montage_dir"
    done
else
    for montage in "${selected_montages[@]}"; do
        montage_dir="$sim_dir/$montage"
        log "ERROR" "Some files may be missing for montage: $montage" "$montage_dir"
        log "ERROR" "Temporary files preserved in: $tmp_dir" "$montage_dir"
        log "ERROR" "----------------------------------------" "$montage_dir"
    done
fi

