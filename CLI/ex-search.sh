#!/bin/bash

#########################################
# Ido Haber - ihaber@wisc.edu
# October 31, 2024
#
# This is the main script for the optimizer tool, which collects input from 
# the user and orchestrates the execution of all necessary scripts and executables 
# in the pipeline. It handles ROI creation, leadfield matrix generation, 
# TI optimization, mesh processing, and output file updates.
#########################################

set -e  # Exit immediately if a command exits with a non-zero status

# Get the directory where this script is located
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
utils_dir="$(cd "$script_dir/../utils" && pwd)"

# Set timestamp for consistent log naming
timestamp=$(date +%Y%m%d_%H%M%S)

# Source the logging utility
source "$utils_dir/bash_logging.sh"

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

# Get the current script directory and set paths
ex_search_dir="$script_dir/../ex-search"

log_info "Selected subjects for processing: ${selected_subjects[*]}"

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

    # Define leadfield directories
    leadfield_vol_dir="$subject_bids_dir/leadfield_vol_$subject_name"

    # Check if leadfield directory exists
    if [ ! -d "$leadfield_vol_dir" ] ; then
        log_warning "Missing leadfield matrices for subject $subject_name"
        while true; do
            echo -ne "${GREEN}Do you wish to create them? It will take some time (Y/N):${RESET} "
            read -r create_leadfield
            if [[ "$create_leadfield" =~ ^[Yy]$ ]]; then
                log_info "Starting leadfield generation for subject $subject_name"
                if simnibs_python "$ex_search_dir/leadfield.py" "$m2m_dir" "EGI_template.csv"; then
                    log_info "Leadfield generation completed successfully"
                else
                    log_error "Leadfield generation failed"
                    exit 1
                fi
                break
            elif [[ "$create_leadfield" =~ ^[Nn]$ ]]; then
                log_warning "Skipping leadfield creation for subject $subject_name"
                exit 1
            else
                log_error "Invalid input. Please enter Y or N"
            fi
        done
    else
        log_info "Leadfield directories already exist for subject $subject_name"
    fi

    # Set the leadfield_hdf path
    leadfield_hdf="$subject_bids_dir/leadfield_$subject_name/${subject_name}_leadfield_EGI_template.hdf5"
    export LEADFIELD_HDF=$leadfield_hdf
    export PROJECT_DIR=$project_dir
    export SUBJECT_NAME=$subject_name
    export TI_LOG_FILE="$log_file"

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
    if python3 "$ex_search_dir/roi-analyzer.py" "$roi_dir"; then
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

    # Run the Python script to update the output.csv file
    log_info "Starting CSV update process for subject $subject_name"
    if python3 "$ex_search_dir/update_output_csv.py" "$project_dir" "$subject_name"; then
        log_info "CSV update completed successfully for subject $subject_name"
    else
        log_error "CSV update failed for subject $subject_name"
        exit 1
    fi

    log_info "All pipeline steps completed successfully for subject $subject_name"
    log_info "Results saved to: $mesh_dir/analysis"

done

log_info "=========================================="
log_info "Ex-Search pipeline completed successfully!"
log_info "Total subjects processed: ${#selected_subjects[@]}"
log_info "Complete pipeline log: $log_file"
log_info "==========================================" 