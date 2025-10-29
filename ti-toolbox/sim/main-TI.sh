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
tools_dir="$(cd "$script_dir/../tools" && pwd)"

# Set timestamp for consistent log naming
timestamp=$(date +%Y%m%d_%H%M%S)

# Source the logging utility
source "$tools_dir/bash_logging.sh"

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

# Set summary mode based on debug mode setting
# When DEBUG_MODE=true, show detailed output (SUMMARY_MODE=false)
# When DEBUG_MODE=false, show summary output (SUMMARY_MODE=true)
if [ "${DEBUG_MODE:-false}" = "true" ]; then
    SUMMARY_MODE=false
else
    SUMMARY_MODE=true
fi

# Parse montages until '--' is found
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --)
            shift
            break
            ;;
        --quiet)
            QUIET=true
            shift
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

# Export the log file path for TI.py to use
export TI_LOG_FILE="$log_file"

# Configure external loggers
configure_external_loggers '["simnibs", "charm", "mesh_io"]'



# Global variables for summary timing
SIMULATION_START_TIME=""
# Simplified step tracking - use associative array for better reliability
declare -A STEP_START_TIMES

# Summary logging functions
format_duration() {
    local total_seconds=$1
    local hours=$((total_seconds / 3600))
    local minutes=$(((total_seconds % 3600) / 60))
    local seconds=$((total_seconds % 60))
    
    if [ $hours -gt 0 ]; then
        echo "${hours}h ${minutes}m ${seconds}s"
    elif [ $minutes -gt 0 ]; then
        echo "${minutes}m ${seconds}s"
    else
        echo "${seconds}s"
    fi
}

log_simulation_start() {
    local subject_id=$1
    local sim_description=$2
    SIMULATION_START_TIME=$(date +%s)
    
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
    
    # Debug: Show what we're storing
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

# Debug output (only in non-summary mode)
if [ "$SUMMARY_MODE" != true ]; then
    log_info "Script directory: $script_dir"
    log_info "Tools directory: $tools_dir"
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
fi

# Set subdirectory paths
sim_dir="$simulation_dir"
if [ "$SUMMARY_MODE" != true ]; then
    log_info "Simulation directory (sim_dir): $sim_dir"
fi

# Create simulation description for summary
sim_type_desc=""
case "$sim_mode" in
    "FLEX_TI")
        sim_type_desc="Flex TI"
        ;;
    "TI")
        sim_type_desc="TI"
        ;;
    "mTI")
        sim_type_desc="mTI"
        ;;
    *)
        sim_type_desc="$sim_mode"
        ;;
esac

montage_count=${#selected_montages[@]}
if [ $montage_count -eq 0 ] && [ "$sim_mode" = "FLEX_TI" ]; then
    sim_description="$sim_type_desc: optimization mode, intensity: ${intensity}mA"
else
    if [ $montage_count -eq 1 ]; then
        sim_description="$sim_type_desc: 1 montage, intensity: ${intensity}mA"
    else
        sim_description="$sim_type_desc: $montage_count montages, intensity: ${intensity}mA"
    fi
fi

# Start simulation summary logging
log_simulation_start "$subject_id" "$sim_description"

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
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Created directory structure for montage: $montage_name"
    fi
}

# Create directories for each montage
for montage in "${selected_montages[@]}"; do
    setup_montage_dirs "$montage"
    montage_dir="$sim_dir/$montage"
    
    # Log simulation parameters
    log_debug "Starting simulation for montage: $montage"
    log_info "Simulation parameters:"
    log_info "- Subject ID: $subject_id"
    log_info "- Conductivity: $conductivity"
    log_info "- Simulation Mode: $sim_mode"
    log_info "- Intensity: $intensity A"
    log_info "- Electrode Shape: $electrode_shape"
    log_info "- Electrode Dimensions: $dimensions mm"
    log_info "- Electrode Thickness: $thickness mm"
    # Log simulation parameters (only in non-summary mode)
    if [ "$SUMMARY_MODE" != true ]; then
        log_debug "Starting simulation for montage: $montage"
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
    local success=true
    for montage in "${selected_montages[@]}"; do
        local montage_dir="$sim_dir/$montage"
        local montage_output_dir="$montage_dir/TI/montage_imgs"
        
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Visualizing montage: $montage"
        fi
        visualize_montage_script_path="$script_dir/visualize-montage.sh"
        if ! bash "$visualize_montage_script_path" "$montage" "$sim_mode" "$eeg_net" "$montage_output_dir" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
            log_error "Failed to visualize montage: $montage"
            success=false
        fi
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Montage visualization completed"
        fi
    done
    return $([ "$success" = true ] && echo 0 || echo 1)
}

# Function to create temporary montage entries for flex-search visualization
create_flex_montage_entries() {
    local flex_montages_file="$1"
    local montage_config_file="$project_dir/code/ti-toolbox/config/montage_list.json"
    
    # Backup original montage file
    local backup_file="${montage_config_file}.backup_${timestamp}"
    cp "$montage_config_file" "$backup_file"
    
    # Read flex montages data
    if [[ ! -f "$flex_montages_file" ]]; then
        log_warning "Flex montages file not found: $flex_montages_file"
        return 0
    fi
    
    log_info "Creating temporary montage entries for flex-search visualization"
    
    # Use Python to process the JSON and add temporary entries
    python3 -c "
import json
import sys
import os

# Read flex config (could be individual config or legacy array)
with open('$flex_montages_file', 'r') as f:
    flex_config = json.load(f)

# Handle new individual config format vs old array format
if isinstance(flex_config, list):
    # Old format - array of montages
    flex_montages = flex_config
elif isinstance(flex_config, dict) and 'montage' in flex_config:
    # New format - single config with subject_id, eeg_net, and montage
    flex_montages = [flex_config['montage']]
else:
    print(f'Unrecognized flex config format: {type(flex_config)}')
    flex_montages = []

# Read current montage config
with open('$montage_config_file', 'r') as f:
    montage_config = json.load(f)

# Add temporary entries for mapped flex montages
for flex_montage in flex_montages:
    if flex_montage['type'] == 'flex_mapped':
        montage_name = flex_montage['name']
        eeg_net = flex_montage['eeg_net']
        pairs = flex_montage['pairs']
        
        # Ensure the net exists in config
        if 'nets' not in montage_config:
            montage_config['nets'] = {}
        if eeg_net not in montage_config['nets']:
            montage_config['nets'][eeg_net] = {
                'uni_polar_montages': {},
                'multi_polar_montages': {}
            }
        
        # Add to unipolar montages (TI simulations are always treated as unipolar for visualization)
        montage_config['nets'][eeg_net]['uni_polar_montages'][montage_name] = pairs
        
        print(f'Added temporary montage entry: {montage_name} for net {eeg_net}')

# Write updated config
with open('$montage_config_file', 'w') as f:
    json.dump(montage_config, f, indent=4)
" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"
    
    log_info "Temporary montage entries created successfully"
}

# Function to restore original montage file
restore_montage_file() {
    local backup_file="$project_dir/code/ti-toolbox/config/montage_list.json.backup_${timestamp}"
    local montage_config_file="$project_dir/code/ti-toolbox/config/montage_list.json"
    
    if [[ -f "$backup_file" ]]; then
        mv "$backup_file" "$montage_config_file"
        log_info "Restored original montage configuration file"
    fi
}

# Function to visualize flex montages with mapped electrodes
run_visualize_flex_montages() {
    # Only run if we have a flex montages file
    local flex_montages_file="${FLEX_MONTAGES_FILE:-}"
    
    if [[ -z "$flex_montages_file" ]] || [[ ! -f "$flex_montages_file" ]]; then
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "No flex montages file found, skipping flex visualization"
        fi
        return 0
    fi
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Starting visualization for flex-search montages with mapped electrodes"
    fi
    
    # Create temporary montage entries
    create_flex_montage_entries "$flex_montages_file"
    
    # Extract flex montage information and visualize mapped ones
    python3 -c "
import json
import subprocess
import sys
import os

# Read flex config (could be individual config or legacy array)
with open('$flex_montages_file', 'r') as f:
    flex_config = json.load(f)

# Handle new individual config format vs old array format
if isinstance(flex_config, list):
    # Old format - array of montages
    flex_montages = flex_config
elif isinstance(flex_config, dict) and 'montage' in flex_config:
    # New format - single config with subject_id, eeg_net, and montage
    flex_montages = [flex_config['montage']]
else:
    print(f'Unrecognized flex config format: {type(flex_config)}')
    flex_montages = []

# Process each flex montage
for flex_montage in flex_montages:
    if flex_montage['type'] == 'flex_mapped':
        montage_name = flex_montage['name']
        eeg_net = flex_montage['eeg_net']
        
        # Create montage directory
        montage_dir = os.path.join('$sim_dir', montage_name)
        montage_output_dir = os.path.join(montage_dir, 'TI', 'montage_imgs')
        os.makedirs(montage_output_dir, exist_ok=True)
        
        print(f'Visualizing flex montage: {montage_name} with EEG net: {eeg_net}')
        
        # Call visualize-montage.sh for this specific montage
        cmd = [
            'bash', '$script_dir/visualize-montage.sh',
            montage_name, 'U', eeg_net, montage_output_dir
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                print(f'Successfully visualized flex montage: {montage_name}')
            else:
                print(f'Failed to visualize flex montage: {montage_name}')
                print(f'Error: {result.stderr}')
        except subprocess.TimeoutExpired:
            print(f'Timeout while visualizing flex montage: {montage_name}')
        except Exception as e:
            print(f'Exception while visualizing flex montage {montage_name}: {e}')
    else:
        print(f'Skipping visualization for optimized montage: {flex_montage[\"name\"]} (coordinates-based)')
" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"
    
    # Restore original montage file
    restore_montage_file
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Flex-search montage visualization completed"
    fi
}

# Function to visualize a single discovered flex montage after simulation
# DISABLED: This function was causing electrode mapping confusion
# Initial visualization is sufficient and more accurate
visualize_flex_montage_post_simulation_DISABLED() {
    local montage_name="$1"
    local montage_dir="$sim_dir/$montage_name"
    local montage_output_dir="$montage_dir/TI/montage_imgs"
    
    # Try to reconstruct the montage data from the simulation results
    # Look for the original flex-search data that created this montage
    log_info "Attempting to visualize discovered flex montage: $montage_name"
    
    # Try to find the corresponding flex-search directory to get the electrode mapping
    local subject_flex_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/flex-search"
    
    if [[ -d "$subject_flex_dir" ]]; then
        # Extract the search name from the montage name (remove flex_ prefix and _mapped/_optimized suffix)
        local search_name_pattern="${montage_name#flex_*}"  # Remove flex_ prefix
        search_name_pattern="${search_name_pattern%_mapped}"  # Remove _mapped suffix
        search_name_pattern="${search_name_pattern%_optimized}"  # Remove _optimized suffix
        
        # Find matching flex-search directory using exact match
        for search_dir in "$subject_flex_dir"/*; do
            if [[ -d "$search_dir" ]]; then
                local search_basename=$(basename "$search_dir")
                # Try exact match first (most reliable)
                if [[ "$search_basename" == "$search_name_pattern" ]]; then
                    local mapping_file="$search_dir/electrode_mapping.json"
                    if [[ -f "$mapping_file" ]]; then
                        log_info "Found mapping file for $montage_name: $mapping_file"
                        
                        # Extract electrode data and create temporary montage entry
                        python3 -c "
import json
import subprocess
import os

mapping_file = '$mapping_file'
montage_name = '$montage_name'
montage_config_file = '$project_dir/code/ti-toolbox/config/montage_list.json'
montage_output_dir = '$montage_output_dir'
tools_dir = '$tools_dir'

try:
    # Read the electrode mapping
    with open(mapping_file, 'r') as f:
        mapping_data = json.load(f)
    
    mapped_labels = mapping_data.get('mapped_labels', [])
    eeg_net = mapping_data.get('eeg_net', 'EGI_template.csv')
    
    if len(mapped_labels) >= 4:
        # Create electrode pairs (first 4 electrodes)
        pairs = [[mapped_labels[0], mapped_labels[1]], [mapped_labels[2], mapped_labels[3]]]
        
        # Read current montage config
        try:
            with open(montage_config_file, 'r') as f:
                montage_config = json.load(f)
        except:
            montage_config = {'nets': {}}
        
        # Add temporary entry
        if 'nets' not in montage_config:
            montage_config['nets'] = {}
        if eeg_net not in montage_config['nets']:
            montage_config['nets'][eeg_net] = {'uni_polar_montages': {}, 'multi_polar_montages': {}}
        
        montage_config['nets'][eeg_net]['uni_polar_montages'][montage_name] = pairs
        
        # Write updated config
        with open(montage_config_file, 'w') as f:
            json.dump(montage_config, f, indent=4)
        
        print(f'Created temporary montage entry for {montage_name}')
        
        # Ensure output directory exists
        os.makedirs(montage_output_dir, exist_ok=True)
        
        # Call visualization script
        cmd = ['bash', f'{script_dir}/visualize-montage.sh', montage_name, 'U', eeg_net, montage_output_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print(f'Successfully visualized flex montage: {montage_name}')
        else:
            print(f'Failed to visualize flex montage: {montage_name}')
            print(f'Error: {result.stderr}')
        
        # Clean up temporary entry
        del montage_config['nets'][eeg_net]['uni_polar_montages'][montage_name]
        with open(montage_config_file, 'w') as f:
            json.dump(montage_config, f, indent=4)
    else:
        print(f'Not enough mapped electrodes for visualization: {len(mapped_labels)}')

except Exception as e:
    print(f'Error visualizing {montage_name}: {e}')
" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"
                        return 0
                    fi
                fi
            fi
        done
    fi
    
    log_warning "Could not find electrode mapping data for flex montage: $montage_name"
    return 1
}

# No temporary directory needed - files written directly to final locations

# Montage visualization step
log_simulation_step_start "Montage visualization"

# Run the visualization pipeline
if [ "$sim_mode" = "FLEX_TI" ]; then
    # For flex mode, first try to visualize any mapped montages if we have the file
    if run_visualize_flex_montages; then
        log_simulation_step_complete "Montage visualization"
    else
        log_simulation_step_failed "Montage visualization" "Flex montage visualization failed"
        log_simulation_failed "$subject_id" "Montage visualization failed"
        exit 1
    fi
else
    # For regular montage mode, use the standard visualization
    if run_visualize_montages; then
        log_simulation_step_complete "Montage visualization"
    else
        log_simulation_step_failed "Montage visualization" "Montage visualization failed"
        log_simulation_failed "$subject_id" "Montage visualization failed"
        exit 1
    fi
fi

# SimNIBS simulation step
log_simulation_step_start "SimNIBS simulation"

# Run TI.py with the selected parameters
if [ "$SUMMARY_MODE" != true ]; then
    for montage in "${selected_montages[@]}"; do
        montage_dir="$sim_dir/$montage"
        log_info "Running SimNIBS simulation for montage: $montage"
    done
fi

# Pass all parameters to TI.py
if ! simnibs_python "$script_dir/TI.py" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$intensity" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" "${selected_montages[@]}" 2>&1 | tee -a "${logs_dir}/simulator_${timestamp}.log"; then
    log_simulation_step_failed "SimNIBS simulation" "SimNIBS simulation failed"
    log_simulation_failed "$subject_id" "SimNIBS simulation failed"
    exit 1
fi

# Update montage count for summary after simulation (for flex mode)
original_montage_count=$montage_count

# For flex-search mode, discover the montages that were created by TI.py
# Only process montages that have simulation results in the tmp directory
if [ "$sim_mode" = "FLEX_TI" ] && [ ${#selected_montages[@]} -eq 0 ]; then
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Flex-search mode detected - discovering created montages from tmp directory"
    fi
    flex_montages=()
    if [ -d "$tmp_dir" ]; then
        for tmp_montage_dir in "$tmp_dir"/*/; do
            if [ -d "$tmp_montage_dir" ]; then
                montage_name=$(basename "$tmp_montage_dir")
                # Check if this montage has actual simulation results (TI.msh file)
                if [ -f "$tmp_montage_dir/TI.msh" ]; then
                    flex_montages+=("$montage_name")
                    if [ "$SUMMARY_MODE" != true ]; then
                        log_info "Found flex montage with simulation results: $montage_name"
                    fi
                    # Ensure the permanent directory structure exists for this montage
                    setup_montage_dirs "$montage_name"
                else
                    if [ "$SUMMARY_MODE" != true ]; then
                        log_warning "Found directory $montage_name in tmp but no TI.msh file - skipping"
                    fi
                fi
            fi
        done
    fi
    # Use flex montages for post-processing
    selected_montages=("${flex_montages[@]}")
    montage_count=${#selected_montages[@]}
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Will process ${#selected_montages[@]} flex montages with valid simulation results"
        log_info "Skipping post-simulation visualization (initial visualization already completed successfully)"
    fi
fi

# Complete SimNIBS simulation step
if [ "$sim_mode" = "FLEX_TI" ] && [ $original_montage_count -eq 0 ]; then
    log_simulation_step_complete "SimNIBS simulation" "$montage_count montages generated"
else
    log_simulation_step_complete "SimNIBS simulation" "$montage_count montages processed"
fi

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

# Field extraction and processing step
log_simulation_step_start "Field extraction"

# NIfTI transformation step
log_simulation_step_start "NIfTI transformation"

# Process each montage's simulation results
for montage in "${selected_montages[@]}"; do
    montage_dir="$sim_dir/$montage"
    
    # Convert T1 to MNI space
    convert_t1_to_mni
    
    # Skip if high_Frequency directory doesn't exist (means simulation didn't run)
    if [ ! -d "$montage_dir/high_Frequency" ]; then
        log_error "No simulation results found for montage: $montage"
        continue
    fi
    
    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Processing simulation results for montage: $montage"
    fi
    
    # High frequency files are already in place (TI.py writes directly to high_Frequency/)
    hf_dir="$montage_dir/high_Frequency"
    
    # Move high frequency mesh files to proper location
    for pattern in "TDCS_1" "TDCS_2"; do
        for file in "$hf_dir"/*${pattern}*; do
            if [[ -f "$file" ]]; then
                if [[ "$file" == *".geo" || "$file" == *"scalar.msh" || "$file" == *"scalar.msh.opt" ]]; then
                    mv "$file" "$montage_dir/high_Frequency/mesh/"
                    if [ "$SUMMARY_MODE" != true ]; then
                        log_info "Moved $(basename "$file") to high frequency mesh directory"
                    fi
                fi
            fi
        done
    done
    
    # Handle subject_volumes directory
    if [ -d "$hf_dir/subject_volumes" ]; then
        mv "$hf_dir/subject_volumes"/* "$montage_dir/high_Frequency/niftis/"
        rmdir "$hf_dir/subject_volumes"
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Moved subject volumes to high frequency niftis directory"
        fi
    fi
    
    # Handle subject_overlays directory (surface files)
    if [ -d "$hf_dir/subject_overlays" ]; then
        mv "$hf_dir/subject_overlays"/* "$montage_dir/TI/surface_overlays/"
        rmdir "$hf_dir/subject_overlays"
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Moved subject overlays to TI surface overlays directory"
        fi
    fi
    
    # Move fields_summary.txt to analysis
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
    
    # Process TI mesh (TI.py now writes directly to final location)
    ti_mesh="$montage_dir/TI/mesh/${montage}_TI.msh"
    if [ -f "$ti_mesh" ]; then
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "Processing TI mesh"
        fi
        
        # Extract GM and WM fields
        gm_output="$montage_dir/TI/mesh/grey_${montage}_TI.msh"
        wm_output="$montage_dir/TI/mesh/white_${montage}_TI.msh"
        extract_fields "$ti_mesh" "$gm_output" "$wm_output"
        
        # Transform volume meshes to NIfTI (directly from TI/mesh to TI/niftis)
        transform_parcellated_meshes_to_nifti "$montage_dir/TI/mesh" "$montage_dir/TI/niftis"
        
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "TI mesh processing completed"
        fi
    fi
    
    # TI normal mesh is already in place (written by TI.py)
    if [ -f "$montage_dir/TI/mesh/${montage}_normal.msh" ]; then
        if [ "$SUMMARY_MODE" != true ]; then
            log_info "TI normal surface mesh found (${montage}_normal.msh)"
        fi
    fi
done

# Field extraction step completion (field extraction happens within the processing loop)
log_simulation_step_complete "Field extraction" "GM/WM meshes extracted"

# NIfTI transformation step completion (NIfTI transformation happens within the processing loop)
log_simulation_step_complete "NIfTI transformation"

# Results processing step
log_simulation_step_start "Results processing"

# Verify all files have been moved correctly
verify_files() {
    local montage_name=$1
    local montage_base_dir="$sim_dir/$montage_name"
    local missing_files=0

    if [ "$SUMMARY_MODE" != true ]; then
        log_info "Verifying files for montage: $montage_name"
    fi

    # Check for essential files and directories
    essential_paths=(
        "$montage_base_dir/high_Frequency/mesh"
        "$montage_base_dir/high_Frequency/niftis"
        "$montage_base_dir/high_Frequency/analysis/fields_summary.txt"
        "$montage_base_dir/documentation"
        "$montage_base_dir/TI/mesh/${montage_name}_TI.msh"
        "$montage_base_dir/TI/mesh/${montage_name}_TI.msh.opt"
        "$montage_base_dir/TI/mesh/${montage_name}_normal.msh"
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
        log_info "Simulation results saved to: $sim_dir/$montage"
        log_info "----------------------------------------"
    done
    
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
            log_error "Temporary files preserved in: $tmp_dir"
            log_error "----------------------------------------"
        done
    fi
    exit 1
fi
