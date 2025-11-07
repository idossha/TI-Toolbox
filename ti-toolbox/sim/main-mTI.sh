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
tools_dir="$(cd "$script_dir/../tools" && pwd)"

# Set timestamp for consistent log naming
timestamp=$(date +%Y%m%d_%H%M%S)

# Source the logging utility
source "$tools_dir/bash_logging.sh"

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
logs_dir="$derivatives_dir/ti-toolbox/logs/sub-$subject_id"
mkdir -p "$logs_dir"
log_file="${logs_dir}/simulator_${timestamp}.log"
set_log_file "$log_file"

# Export the log file path for mTI.py to use
export TI_LOG_FILE="$log_file"

# Configure external loggers
configure_external_loggers '["simnibs", "charm", "mesh_io"]'

# Global variables for summary timing
SIMULATION_START_TIME=""
# Simplified step tracking - use associative array for better reliability
declare -A STEP_START_TIMES

# Summary logging functions
log_simulation_start() {
    local subject_id=$1
    local montage_count=$2
    
    # Record start time
    SIMULATION_START_TIME=$(date +%s)
    
    # Create description similar to TI format
    local sim_description
    if [ $montage_count -eq 1 ]; then
        sim_description="mTI: 1 montage, intensity: ${intensity}mA"
    else
        sim_description="mTI: $montage_count montages, intensity: ${intensity}mA"
    fi
    
    if [ "$SUMMARY_MODE" = true ]; then
        echo "Beginning simulation for subject: $subject_id ($sim_description)"
    else
        log_info "Beginning simulation for subject: $subject_id ($sim_description)"
    fi
}

log_simulation_complete() {
    local subject_id=$1
    local results_summary=$2
    local output_path=$3
    
    if [ -n "$SIMULATION_START_TIME" ]; then
        local current_time=$(date +%s)
        local total_duration=$((current_time - SIMULATION_START_TIME))
        local duration_str=$(format_duration $total_duration)
        
        if [ "$SUMMARY_MODE" = true ]; then
            if [ -n "$results_summary" ]; then
                echo "└─ Simulation completed successfully for subject: $subject_id ($results_summary, Total: $duration_str)"
            else
                echo "└─ Simulation completed successfully for subject: $subject_id (Total: $duration_str)"
            fi
            if [ -n "$output_path" ]; then
                # Show relative path from /mnt/ for cleaner display
                local display_path=$(echo "$output_path" | sed 's|^/mnt/||')
                echo "   Results saved to: $display_path"
            fi
        else
            log_info "Simulation completed successfully for subject: $subject_id (Total: $duration_str)"
        fi
    fi
}

log_simulation_failed() {
    local subject_id=$1
    local error_msg=$2
    
    if [ -n "$SIMULATION_START_TIME" ]; then
        local current_time=$(date +%s)
        local total_duration=$((current_time - SIMULATION_START_TIME))
        local duration_str=$(format_duration $total_duration)
        
        if [ "$SUMMARY_MODE" = true ]; then
            echo "└─ Simulation failed for subject: $subject_id ($duration_str) - $error_msg"
        else
            log_error "Simulation failed for subject: $subject_id ($duration_str) - $error_msg"
        fi
    fi
}

log_simulation_step_start() {
    local step_name=$1
    local step_key="${subject_id}_${step_name}"
    local step_start_time=$(date +%s)
    
    # Store step start time using associative array
    STEP_START_TIMES["$step_key"]="$step_start_time"
    
    if [ "$SUMMARY_MODE" = true ]; then
        echo "├─ $step_name: Started"
    else
        log_info "$step_name: Started"
    fi
}

log_simulation_step_complete() {
    local step_name=$1
    local step_details=$2
    local step_key="${subject_id}_${step_name}"
    
    # Get step start time from associative array
    local step_start_time="${STEP_START_TIMES[$step_key]}"
    
    # Remove the step from tracking
    unset STEP_START_TIMES["$step_key"]
    
    if [ -n "$step_start_time" ]; then
        local current_time=$(date +%s)
        local duration=$((current_time - step_start_time))
        local duration_str=$(format_duration $duration)
        
        if [ "$SUMMARY_MODE" = true ]; then
            if [ -n "$step_details" ]; then
                echo "├─ $step_name: ✓ Complete ($duration_str) - $step_details"
            else
                echo "├─ $step_name: ✓ Complete ($duration_str)"
            fi
        else
            log_info "$step_name: Complete ($duration_str)"
        fi
    else
        if [ "$SUMMARY_MODE" = true ]; then
            # Show completion even without timing
            if [ -n "$step_details" ]; then
                echo "├─ $step_name: ✓ Complete - $step_details"
            else
                echo "├─ $step_name: ✓ Complete"
            fi
        fi
    fi
}

log_simulation_step_failed() {
    local step_name=$1
    local error_msg=$2
    local step_key="${subject_id}_${step_name}"
    
    # Get step start time from associative array
    local step_start_time="${STEP_START_TIMES[$step_key]}"
    
    # Remove the step from tracking
    unset STEP_START_TIMES["$step_key"]
    
    if [ -n "$step_start_time" ]; then
        local current_time=$(date +%s)
        local duration=$((current_time - step_start_time))
        local duration_str=$(format_duration $duration)
        
        if [ "$SUMMARY_MODE" = true ]; then
            echo "├─ $step_name: ✗ Failed ($duration_str) - $error_msg"
        else
            log_error "$step_name: Failed ($duration_str) - $error_msg"
        fi
    else
        if [ "$SUMMARY_MODE" = true ]; then
            echo "├─ $step_name: ✗ Failed (timing unavailable) - $error_msg"
        fi
    fi
}

# When DEBUG_MODE=true, show detailed output (SUMMARY_MODE=false)
# When DEBUG_MODE=false, show summary output (SUMMARY_MODE=true)
if [ "${DEBUG_MODE:-false}" = "true" ]; then
    SUMMARY_MODE=false
else
    SUMMARY_MODE=true
fi

# Debug script location
if [ "$SUMMARY_MODE" != true ]; then
    log_info "Script directory: $script_dir"
    log_info "Tools directory: $tools_dir"
fi

# Debug input arguments
if [ "$SUMMARY_MODE" != true ]; then
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
fi

# Set subdirectory paths
sim_dir="$simulation_dir"
if [ "$SUMMARY_MODE" != true ]; then
    log_info "Simulation directory (sim_dir): $sim_dir"
fi

# Initialize simulation and display summary
montage_count=${#selected_montages[@]}
log_simulation_start "$subject_id" "$montage_count"

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
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Created multipolar directory structure for montage: $montage_name"
    fi
}

# Create directories for each montage
for montage in "${selected_montages[@]}"; do
    setup_montage_dirs "$montage"
    montage_dir="$sim_dir/$montage"
    
    # Log simulation parameters
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Starting simulation for montage: $montage"
        log_info "Simulation parameters:"
        log_info "- Subject ID: $subject_id"
        log_info "- Conductivity: $conductivity"
        log_info "- Simulation Mode: $sim_mode"
        log_info "- Intensity: $intensity A"
        log_info "- Electrode Shape: $electrode_shape"
        log_info "- Electrode Dimensions: $dimensions mm"
        log_info "- Electrode Thickness: $thickness mm"
    fi
done

# Function to visualize montages
run_visualize_montages() {
    for montage in "${selected_montages[@]}"; do
        local montage_dir="$sim_dir/$montage"
        local montage_output_dir="$montage_dir/mTI/montage_imgs"
        
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Visualizing montage: $montage"
        fi
        visualize_montage_script_path="$script_dir/visualize-montage.sh"
        if ! bash "$visualize_montage_script_path" "$montage" "$sim_mode" "$eeg_net" "$montage_output_dir" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
            log_error "Failed to visualize montage: $montage"
            exit 1
        fi
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Montage visualization completed"
        fi
    done
}

# mTI pipeline writes directly to final directories (no temporary directory needed)

# Run the pipeline
run_visualize_montages

# Run mTI.py with the selected parameters
log_simulation_step_start "SimNIBS mTI simulation"

if [ "$SUMMARY_MODE" != true ]; then
    for montage in "${selected_montages[@]}"; do
        montage_dir="$sim_dir/$montage"
        log_info "Running SimNIBS simulation for montage: $montage"
    done
fi

# Pass all parameters to mTI.py
if ! simnibs_python "$script_dir/mTI.py" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$intensity" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" "${selected_montages[@]}" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
    log_simulation_step_failed "SimNIBS mTI simulation" "mTI.py execution failed"
    log_simulation_failed "$subject_id" "SimNIBS simulation failed"
    exit 1
fi

log_simulation_step_complete "SimNIBS mTI simulation" "${montage_count} montage(s)"

# Function to extract fields (GM and WM meshes)
extract_fields() {
    local input_file="$1"
    local gm_output_file="$2"
    local wm_output_file="$3"
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Extracting fields from: $(basename "$input_file")"
    fi
    field_extract_script_path="$script_dir/../tools/field_extract.py"
    if ! simnibs_python "$field_extract_script_path" "$input_file" --gm_output_file "$gm_output_file" --wm_output_file "$wm_output_file" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
        log_error "Field extraction failed"
        return 1
    fi
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Field extraction completed"
    fi
}

# Function to transform parcellated meshes to NIfTI
transform_parcellated_meshes_to_nifti() {
    local input_mesh="$1"
    local output_dir="$2"
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Converting meshes to NIfTI format"
    fi
    mesh2nii_script_path="$script_dir/../tools/mesh2nii_loop.sh"
    if ! bash "$mesh2nii_script_path" "$subject_id" "$m2m_dir" "$input_mesh" "$output_dir" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
        log_error "Mesh to NIfTI conversion failed"
        return 1
    fi
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Mesh to NIfTI conversion completed"
    fi
}

# Convert T1 to MNI space
convert_t1_to_mni() {
    local t1_file="$m2m_dir/T1.nii.gz"
    local output_file="$m2m_dir/T1_${subject_id}"
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Converting T1 to MNI space"
    fi
    if ! subject2mni -i "$t1_file" -m "$m2m_dir" -o "$output_file" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
        log_error "T1 to MNI conversion failed"
        return 1
    fi
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "T1 to MNI conversion completed"
    fi
}

# Process each montage's simulation results
log_simulation_step_start "Results processing"

for montage in "${selected_montages[@]}"; do
    montage_dir="$sim_dir/$montage"
    
    # Convert T1 to MNI space
    convert_t1_to_mni
    
    # Check if high_Frequency directory exists (mTI.py writes directly there)
    if [ ! -d "$montage_dir/high_Frequency" ]; then
        log_error "No simulation results found for montage: $montage"
        continue
    fi
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Processing simulation results for montage: $montage"
    fi
    
    # Move and rename high frequency mesh files (mTI.py writes to high_Frequency/)
    hf_dir="$montage_dir/high_Frequency"
    for i in {1..4}; do
        hf_letter=$(echo "A B C D" | cut -d' ' -f$i)
        for file in "$hf_dir"/*TDCS_${i}*; do
            if [[ -f "$file" ]]; then
                if [[ "$file" == *".geo" || "$file" == *"scalar.msh" || "$file" == *"scalar.msh.opt" ]]; then
                    filename=$(basename "$file")
                    new_filename=$(echo "$filename" | sed "s/TDCS_${i}/TDCS_${hf_letter}/g")
                    mv "$file" "$montage_dir/high_Frequency/mesh/$new_filename"
                    if [ "$SUMMARY_MODE" != true ]; then
                        log_info "Moved and renamed $(basename "$file") to $new_filename"
                    fi
                fi
            fi
        done
    done
    
    # Clean up subject_volumes directory (high frequency niftis not needed in new structure)
    if [ -d "$montage_dir/subject_volumes" ]; then
        rm -rf "$montage_dir/subject_volumes"
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Cleaned up subject volumes directory"
        fi
    fi
    
    # Move fields_summary.txt to analysis directory
    if [ -f "$hf_dir/fields_summary.txt" ]; then
        mv "$hf_dir/fields_summary.txt" "$montage_dir/high_Frequency/analysis/"
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Moved fields summary to analysis directory"
        fi
    fi
    
    # Move log and mat files to documentation
    for file in "$hf_dir"/simnibs_simulation_*.{log,mat}; do
        if [ -f "$file" ]; then
            mv "$file" "$montage_dir/documentation/"
            if [ "$SUMMARY_MODE" != true ]; then
                log_info "Moved $(basename "$file") to documentation directory"
            fi
        fi
    done
    
    # Process TI intermediate meshes (TI_AB and TI_CD) - already in place from mTI.py
    ti_ab_mesh="$montage_dir/TI/mesh/${montage}_TI_AB.msh"
    ti_cd_mesh="$montage_dir/TI/mesh/${montage}_TI_CD.msh"
    
    if [ -f "$ti_ab_mesh" ]; then
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Processing TI_AB mesh"
        fi
        gm_ti_ab="$montage_dir/TI/mesh/grey_${montage}_TI_AB.msh"
        wm_ti_ab="$montage_dir/TI/mesh/white_${montage}_TI_AB.msh"
        extract_fields "$ti_ab_mesh" "$gm_ti_ab" "$wm_ti_ab"
    fi
    
    if [ -f "$ti_cd_mesh" ]; then
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Processing TI_CD mesh"
        fi
        gm_ti_cd="$montage_dir/TI/mesh/grey_${montage}_TI_CD.msh"
        wm_ti_cd="$montage_dir/TI/mesh/white_${montage}_TI_CD.msh"
        extract_fields "$ti_cd_mesh" "$gm_ti_cd" "$wm_ti_cd"
    fi

    # Process mTI mesh (already in mTI/mesh/ from mTI.py)
    mti_mesh="$montage_dir/mTI/mesh/${montage}_mTI.msh"
    if [ -f "$mti_mesh" ]; then
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Processing mTI mesh"
        fi
        
        # Extract GM and WM fields for mTI (save to mTI/mesh/)
        gm_output="$montage_dir/mTI/mesh/grey_${montage}_mTI.msh"
        wm_output="$montage_dir/mTI/mesh/white_${montage}_mTI.msh"
        extract_fields "$mti_mesh" "$gm_output" "$wm_output"
        
        # Transform only mTI meshes to NIfTI (mTI/mesh/ → mTI/niftis/)
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Converting mTI meshes to NIfTI format (final results only)"
        fi
        transform_parcellated_meshes_to_nifti "$montage_dir/mTI/mesh" "$montage_dir/mTI/niftis"
        
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "mTI mesh processing completed"
        fi
    fi
done

# Verify all files have been moved correctly
verify_files() {
    local montage_name=$1
    local montage_base_dir="$sim_dir/$montage_name"
    local missing_files=0

    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Verifying files for montage: $montage_name"
    fi

    # Check for essential directories
    essential_paths=(
        "$montage_base_dir/high_Frequency/mesh"
        "$montage_base_dir/high_Frequency/analysis"
        "$montage_base_dir/TI/mesh"
        "$montage_base_dir/TI/niftis"
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

    # Check for essential files (TI_AB/TI_CD in TI/mesh, final mTI in mTI/mesh)
    essential_files=(
        "$montage_base_dir/TI/mesh/${montage_name}_TI_AB.msh"
        "$montage_base_dir/TI/mesh/${montage_name}_TI_CD.msh"
        "$montage_base_dir/mTI/mesh/${montage_name}_mTI.msh"
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
    # Complete results processing step
    log_simulation_step_complete "Results processing" "saved to ${sim_dir}"
    
    # Create results summary
    if [ $montage_count -eq 1 ]; then
        results_summary="1 montage"
    else
        results_summary="$montage_count montages"
    fi
    
    # Complete overall simulation
    log_simulation_complete "$subject_id" "$results_summary" "$sim_dir"
    
    # Verbose completion messages (only in non-summary mode)
    if [ "$SUMMARY_MODE" != true ]; then
        for montage in "${selected_montages[@]}"; do
            log_info "Pipeline completed successfully for montage: $montage"
            log_info "Simulation results saved to: $sim_dir/$montage"
            log_info "----------------------------------------"
        done
    fi
else
    # Results processing failed
    log_simulation_step_failed "Results processing" "File verification failed"
    log_simulation_failed "$subject_id" "File verification failed - some files may be missing"
    
    # Verbose error messages (only in non-summary mode)
    if [ "$SUMMARY_MODE" != true ]; then
        for montage in "${selected_montages[@]}"; do
            log_error "Some files may be missing for montage: $montage"
            log_error "Check simulation directory: $sim_dir/$montage"
            log_error "----------------------------------------"
        done
    fi
    exit 1
fi


