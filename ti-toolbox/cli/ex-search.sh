#!/bin/bash

#########################################
# Ido Haber - ihaber@wisc.edu
# June, 2025
#
# This is the main script for the ex-search tool, which collects input from 
# the user and orchestrates the execution of all necessary scripts and executables 
# in the pipeline. It handles ROI creation, leadfield matrix generation, 
# TI optimization, mesh processing, and output file updates.
#########################################

set -e  # Exit immediately if a command exits with a non-zero status

# Get the directory where this script is located
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tools_dir="$(cd "$script_dir/../tools" && pwd)"
ex_search_dir="$script_dir/../opt/ex"

# Set timestamp for consistent log naming
timestamp=$(date +%Y%m%d_%H%M%S)

# Source the logging utility
source "$tools_dir/bash_logging.sh"

# Initialize logging
set_logger_name "ex-search"

# Define color variables
BOLD='\033[1m'
UNDERLINE='\033[4m'
RESET='\033[0m'
RED='\033[0;31m' #Red for errors or important exit messages.
GREEN='\033[0;32m' #Green for successful completions.
CYAN='\033[0;36m' #Cyan for actions being performed.
BOLD_CYAN='\033[1;36m'
YELLOW='\033[0;33m' #Yellow for warnings or important notices

# Check if PROJECT_DIR_NAME is set
if [ -z "$PROJECT_DIR_NAME" ]; then
    log_error "PROJECT_DIR_NAME environment variable is not set"
    exit 1
fi

# Define the new BIDS-compliant directory structure
project_dir="/mnt/$PROJECT_DIR_NAME"
derivatives_dir="$project_dir/derivatives"
simnibs_dir="$derivatives_dir/SimNIBS"

# Set up logging directory and file
logs_dir="$derivatives_dir/logs"
mkdir -p "$logs_dir"
log_file="${logs_dir}/ex_search_${timestamp}.log"
set_log_file "$log_file"

# Configure external loggers
configure_external_loggers '["simnibs", "mesh_io"]'

log_info "Ex-Search Optimization Pipeline"
log_info "==============================="
log_info "Project directory: $project_dir"
log_info "Timestamp: $timestamp"

# Function to list available subjects
list_subjects() {
    subjects=()
    i=1
    # Look for subjects in the new BIDS structure
    for subject_path in "$simnibs_dir"/sub-*/m2m_*; do
        if [ -d "$subject_path" ]; then
            # Extract subject ID from the path (e.g., sub-101 -> 101)
            subject_id=$(basename "$subject_path" | sed 's/m2m_//')
            subjects+=("$subject_id")
            printf "%3d. %s\n" "$i" "$subject_id"
            ((i++))
        fi
    done
}

log_info "Scanning for available subjects..."
echo -e "${BOLD_CYAN}Choose subjects:${RESET}"
list_subjects

if [ ${#subjects[@]} -eq 0 ]; then
    log_error "No subjects found in BIDS directory structure"
    exit 1
fi

log_info "Found ${#subjects[@]} available subjects"

# Prompt user to select subjects
while true; do
    echo -ne "${GREEN}Enter the numbers of the subjects to analyze (comma-separated):${RESET} "
    read -r subject_choices
    if [[ "$subject_choices" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        IFS=',' read -r -a selected_subjects <<< "$subject_choices"
        valid_input=true
        for num in "${selected_subjects[@]}"; do
            if (( num < 1 || num >= i )); then
                log_error "Invalid subject number: $num"
                valid_input=false
                break
            fi
        done
        if $valid_input; then
            break
        fi
    else
        log_error "Invalid input format. Please enter numbers separated by commas"
    fi
done

log_info "Selected subjects for processing: ${selected_subjects[*]}"

# Function to list and select EEG nets
select_eeg_net() {
    local subject_name=$1
    local m2m_dir=$2
    local eeg_positions_dir="$m2m_dir/eeg_positions"
    
    log_info "Scanning available EEG nets for subject $subject_name..."
    
    if [ ! -d "$eeg_positions_dir" ]; then
        log_error "EEG positions directory not found: $eeg_positions_dir"
        exit 1
    fi
    
    # Get available CSV files (EEG nets)
    eeg_nets=()
    default_net=""
    i=1
    
    # Scan for CSV files
    for net_file in "$eeg_positions_dir"/*.csv; do
        if [ -f "$net_file" ]; then
            net_name=$(basename "$net_file")
            eeg_nets+=("$net_name")
            
            # Set default to GSN-HydroCel-185.csv if available
            if [[ "$net_name" == "GSN-HydroCel-185.csv" ]]; then
                default_net="$net_name"
                default_index=$i
            fi
            
            printf "%3d. %s\n" "$i" "$net_name"
            ((i++))
        fi
    done
    
    if [ ${#eeg_nets[@]} -eq 0 ]; then
        log_error "No EEG net CSV files found in: $eeg_positions_dir"
        exit 1
    fi
    
    log_info "Found ${#eeg_nets[@]} available EEG nets"
    if [ -n "$default_net" ]; then
        log_info "Default net: $default_net (option $default_index)"
    fi
    
    # Prompt user to select EEG net
    while true; do
        if [ -n "$default_net" ]; then
            echo -ne "${GREEN}Select EEG net [Press Enter for default: $default_net]: ${RESET}"
        else
            echo -ne "${GREEN}Select EEG net (enter number): ${RESET}"
        fi
        read -r net_choice
        
        if [[ -z "$net_choice" && -n "$default_net" ]]; then
            # Use default
            selected_net="$default_net"
            log_info "Using default EEG net: $selected_net"
            break
        elif [[ "$net_choice" =~ ^[0-9]+$ ]] && (( net_choice >= 1 && net_choice <= ${#eeg_nets[@]} )); then
            selected_net="${eeg_nets[$((net_choice-1))]}"
            log_info "Selected EEG net: $selected_net"
            break
        else
            log_error "Invalid selection. Please enter a number between 1 and ${#eeg_nets[@]}"
        fi
    done
    
    echo "$selected_net"
}

# Function to list available leadfields for a subject
list_available_leadfields() {
    local subject_name=$1
    local subject_bids_dir=$2
    
    log_info "Scanning for existing leadfields for subject $subject_name..."
    
    leadfield_dirs=()
    i=1
    
    # Look for leadfield directories in ex-search subdirectory with pattern: leadfield_vol_*
    local ex_search_dir="$subject_bids_dir/leadfields"
    
    if [ -d "$ex_search_dir" ]; then
        for leadfield_path in "$ex_search_dir"/leadfield_vol_*; do
            if [ -d "$leadfield_path" ]; then
                # Extract net name from directory
                dir_name=$(basename "$leadfield_path")
                net_name=${dir_name#leadfield_vol_}
                
                # Check if leadfield.hdf5 exists
                hdf5_file="$leadfield_path/leadfield.hdf5"
                if [ -f "$hdf5_file" ]; then
                    leadfield_dirs+=("$net_name:$hdf5_file")
                    printf "%3d. %s (leadfield.hdf5)\n" "$i" "$net_name"
                    ((i++))
                fi
            fi
        done
    fi
    
    if [ ${#leadfield_dirs[@]} -eq 0 ]; then
        log_warning "No existing leadfields found for subject $subject_name"
        return 1
    else
        log_info "Found ${#leadfield_dirs[@]} existing leadfield(s)"
        return 0
    fi
}

# Function to select leadfield for simulation
select_leadfield() {
    local subject_name=$1
    local subject_bids_dir=$2
    
    if ! list_available_leadfields "$subject_name" "$subject_bids_dir"; then
        log_error "No leadfields available for simulation"
        return 1
    fi
    
    # Prompt user to select leadfield
    while true; do
        echo -ne "${GREEN}Select leadfield for simulation (enter number): ${RESET}"
        read -r leadfield_choice
        
        if [[ "$leadfield_choice" =~ ^[0-9]+$ ]] && (( leadfield_choice >= 1 && leadfield_choice <= ${#leadfield_dirs[@]} )); then
            selected_leadfield_info="${leadfield_dirs[$((leadfield_choice-1))]}"
            selected_net_name="${selected_leadfield_info%%:*}"
            selected_hdf5_path="${selected_leadfield_info##*:}"
            
            log_info "Selected leadfield: $selected_net_name"
            log_info "HDF5 file: $selected_hdf5_path"
            
            echo "$selected_net_name:$selected_hdf5_path"
            return 0
        else
            log_error "Invalid selection. Please enter a number between 1 and ${#leadfield_dirs[@]}"
        fi
    done
}

# Function to check/create leadfields
manage_leadfields() {
    local subject_name=$1
    local subject_bids_dir=$2
    local m2m_dir=$3
    
    log_info "=========================================="
    log_info "Leadfield Management for subject $subject_name"
    log_info "=========================================="
    
    # Check for existing leadfields
    if list_available_leadfields "$subject_name" "$subject_bids_dir"; then
        echo ""
        while true; do
            echo -ne "${GREEN}Do you want to (C)reate new leadfield, (U)se existing, or (B)oth? [U/C/B]: ${RESET}"
            read -r leadfield_action
            
            case "${leadfield_action^^}" in
                U|"")
                    log_info "Using existing leadfield"
                    if selected_info=$(select_leadfield "$subject_name" "$subject_bids_dir"); then
                        echo "$selected_info"
                        return 0
                    else
                        return 1
                    fi
                    ;;
                C)
                    log_info "Creating new leadfield"
                    create_new_leadfield "$subject_name" "$subject_bids_dir" "$m2m_dir"
                    # After creation, let user select from available leadfields
                    if selected_info=$(select_leadfield "$subject_name" "$subject_bids_dir"); then
                        echo "$selected_info"
                        return 0
                    else
                        return 1
                    fi
                    ;;
                B)
                    log_info "Creating new leadfield, then selecting for simulation"
                    create_new_leadfield "$subject_name" "$subject_bids_dir" "$m2m_dir"
                    # After creation, let user select from available leadfields
                    if selected_info=$(select_leadfield "$subject_name" "$subject_bids_dir"); then
                        echo "$selected_info"
                        return 0
                    else
                        return 1
                    fi
                    ;;
                *)
                    log_error "Invalid input. Please enter U, C, or B"
                    ;;
            esac
        done
    else
        log_warning "No existing leadfields found. Creating new leadfield..."
        create_new_leadfield "$subject_name" "$subject_bids_dir" "$m2m_dir"
        # After creation, automatically use the newly created leadfield
        if list_available_leadfields "$subject_name" "$subject_bids_dir"; then
            # If only one leadfield exists, use it automatically
            if [ ${#leadfield_dirs[@]} -eq 1 ]; then
                selected_leadfield_info="${leadfield_dirs[0]}"
                selected_net_name="${selected_leadfield_info%%:*}"
                selected_hdf5_path="${selected_leadfield_info##*:}"
                log_info "Automatically using newly created leadfield: $selected_net_name"
                echo "$selected_net_name:$selected_hdf5_path"
                return 0
            else
                # Multiple leadfields available, let user choose
                if selected_info=$(select_leadfield "$subject_name" "$subject_bids_dir"); then
                    echo "$selected_info"
                    return 0
                else
                    return 1
                fi
            fi
        else
            log_error "Leadfield creation failed"
            return 1
        fi
    fi
}

# Function to create new leadfield
create_new_leadfield() {
    local subject_name=$1
    local subject_bids_dir=$2
    local m2m_dir=$3
    
    # Select EEG net for new leadfield
    selected_net=$(select_eeg_net "$subject_name" "$m2m_dir")
    
    # Extract net name without .csv extension for directory naming
    net_name_clean="${selected_net%.csv}"
    
    # Construct paths with new naming scheme - leadfields go in ex-search subdirectory
    leadfield_dir="$subject_bids_dir/leadfields/leadfield_vol_$net_name_clean"
    eeg_cap_path="$m2m_dir/eeg_positions/$selected_net"
    
    log_info "Creating leadfield for EEG net: $selected_net"
    log_info "Output directory: $leadfield_dir"
    
    # Create leadfield
    if simnibs_python "$ex_search_dir/leadfield.py" "$m2m_dir" "$eeg_cap_path" "$net_name_clean"; then
        log_info "Leadfield creation completed successfully"
        
        # Verify the leadfield file was created
        expected_hdf5="$leadfield_dir/leadfield.hdf5"
        if [ -f "$expected_hdf5" ]; then
            log_info "Leadfield file verified: $expected_hdf5"
        else
            log_error "Leadfield file not found: $expected_hdf5"
            return 1
        fi
    else
        log_error "Leadfield creation failed"
        return 1
    fi
}

# Loop through selected subjects and run the pipeline
for subject_index in "${selected_subjects[@]}"; do
    subject_name="${subjects[$((subject_index-1))]}"
    subject_bids_dir="$simnibs_dir/sub-$subject_name"
    m2m_dir="$subject_bids_dir/m2m_$subject_name"
    roi_dir="$m2m_dir/ROIs"
    ex_search_output_dir="$subject_bids_dir/ex-search"

    # Create ex-search output directory if it doesn't exist
    mkdir -p "$ex_search_output_dir"

    log_info "=========================================="
    log_info "Processing subject: $subject_name"
    log_info "Subject directory: $subject_bids_dir"
    log_info "M2M directory: $m2m_dir"
    log_info "ROI directory: $roi_dir"
    log_info "=========================================="

    # Call the ROI creator script to handle ROI creation or selection
    log_info "Starting ROI creation/selection process"
    if python3 "$ex_search_dir/roi-creator.py" "$roi_dir"; then
        log_info "ROI creation completed successfully for subject $subject_name"
    else
        log_error "ROI creation failed for subject $subject_name"
        exit 1
    fi

    # Manage leadfields (check existing, create new, or select)
    log_info "Managing leadfields for subject $subject_name"
    if leadfield_info=$(manage_leadfields "$subject_name" "$subject_bids_dir" "$m2m_dir"); then
        # Parse the returned information
        selected_net_name="${leadfield_info%%:*}"
        selected_hdf5_path="${leadfield_info##*:}"
        
        log_info "Using leadfield: $selected_net_name"
        log_info "HDF5 path: $selected_hdf5_path"
    else
        log_error "Leadfield management failed for subject $subject_name"
        exit 1
    fi

    # Set environment variables for TI simulation
    export LEADFIELD_HDF="$selected_hdf5_path"
    export SELECTED_EEG_NET="$selected_net_name"
    export PROJECT_DIR="$project_dir"
    export SUBJECT_NAME="$subject_name"
    export TI_LOG_FILE="$log_file"
    
    # Check for existing output directories (coordinate-based naming)
    # Note: For CLI, the directory will be created as xyz_X_Y_Z format
    # We'll check and handle this after the TI simulation creates it
    
    # Call the TI optimizer script (sequential processing for SimNIBS compatibility)
    log_info "Starting TI simulation for subject $subject_name"
    if simnibs_python "$ex_search_dir/ti_sim.py"; then
        log_info "TI optimization completed successfully for subject $subject_name"
    else
        log_error "TI optimization failed for subject $subject_name"
        exit 1
    fi

    # Call the ROI analyzer script
    log_info "Starting ROI analysis for subject $subject_name"
    if python3 "$ex_search_dir/ex_analyzer.py" "$roi_dir"; then
        log_info "ROI analysis completed successfully for subject $subject_name"
    else
        log_error "ROI analysis failed for subject $subject_name"
        exit 1
    fi

    # Define and check roi_list_file
    roi_list_file="$roi_dir/roi_list.txt"
    if [ ! -f "$roi_list_file" ]; then
        log_error "ROI list file not found: $roi_list_file"
        exit 1
    fi

    # Get ROI coordinates from the first ROI file
    first_roi=$(head -n1 "$roi_list_file" || echo "")
    if [ -z "$first_roi" ]; then
        log_error "ROI list file is empty: $roi_list_file"
        exit 1
    fi
    
    # Construct full path to ROI file
    roi_file="$roi_dir/$first_roi"
    if [ ! -f "$roi_file" ]; then
        log_error "ROI file not found: $roi_file"
        exit 1
    fi

    # Read coordinates from the ROI file and handle Windows line endings
    coordinates=$(head -n1 "$roi_file" | tr -d '\r')
    IFS=',' read -r x y z <<< "$coordinates"
    
    # Remove any whitespace and validate coordinates
    x=$(echo "$x" | tr -d ' ')
    y=$(echo "$y" | tr -d ' ')
    z=$(echo "$z" | tr -d ' ')
    
    log_info "Processing ROI coordinates: $x, $y, $z"
    
    # Round coordinates to integers using awk for better decimal and negative number handling
    x_int=$(echo "$x" | awk '{printf "%.0f", $1}')
    y_int=$(echo "$y" | awk '{printf "%.0f", $1}')
    z_int=$(echo "$z" | awk '{printf "%.0f", $1}')
    
    # Validate that we got all coordinates
    if [ -z "$x_int" ] || [ -z "$y_int" ] || [ -z "$z_int" ]; then
        log_error "Failed to parse coordinates from ROI file: $roi_file"
        log_error "Raw coordinates: $coordinates"
        exit 1
    fi
    
    # Create directory name from coordinates
    coord_dir="xyz_${x_int}_${y_int}_${z_int}"
    log_info "Creating analysis directory: $coord_dir"
    mesh_dir="$ex_search_output_dir/$coord_dir"

    # Create output directory if it doesn't exist
    mkdir -p "$mesh_dir"

    # Run the Python mesh analysis script
    log_info "Starting mesh field analysis for subject $subject_name"
    if python3 "$ex_search_dir/mesh_field_analyzer.py" "$mesh_dir"; then
        log_info "Mesh field analysis completed successfully for subject $subject_name"
    else
        log_error "Mesh field analysis failed for subject $subject_name"
        exit 1
    fi

    # Note: Final output CSV is now created directly by the mesh field analyzer
    # No separate CSV update step needed

    log_info "All pipeline steps completed successfully for subject $subject_name"
    log_info "Results saved to: $mesh_dir/analysis"

done

log_info "=========================================="
log_info "Ex-Search pipeline completed successfully!"
log_info "Total subjects processed: ${#selected_subjects[@]}"
log_info "Complete pipeline log: $log_file"
log_info "==========================================" 
