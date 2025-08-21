#!/bin/bash
#
# SimNIBS charm (m2m) Creation Script
# Creates SimNIBS m2m head model for a single subject
#
# Usage: ./charm.sh <subject_dir> [--quiet]
#

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/../utils/bash_logging.sh"

# Parse arguments
SUBJECT_DIR=""
QUIET=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quiet)
            QUIET=true
            shift
            ;;
        *)
            if [[ -z "$SUBJECT_DIR" ]]; then
                SUBJECT_DIR="$1"
            else
                echo "Error: Unknown argument: $1"
                echo "Usage: $0 <subject_dir> [--quiet]"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$SUBJECT_DIR" ]]; then
    echo "Error: Subject directory is required"
    echo "Usage: $0 <subject_dir> [--quiet]"
    exit 1
fi

# Validate subject directory
SUBJECT_DIR="$(cd "$SUBJECT_DIR" 2>/dev/null && pwd)"
if [[ ! -d "$SUBJECT_DIR" ]]; then
    echo "Error: Subject directory does not exist: $SUBJECT_DIR"
    exit 1
fi

# Check if charm is available
if ! command -v charm &>/dev/null; then
    echo "Error: charm (SimNIBS) is not installed."
    exit 1
fi

# Set up project structure
PROJECT_NAME=$(basename "$(dirname "$SUBJECT_DIR")")
PROJECT_DIR="/mnt/${PROJECT_NAME}"
SUBJECT_ID=$(basename "$SUBJECT_DIR" | sed 's/^sub-//')
BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"

# Define directories
BIDS_ANAT_DIR="${PROJECT_DIR}/${BIDS_SUBJECT_ID}/anat"
DERIVATIVES_DIR="${PROJECT_DIR}/derivatives"
SIMNIBS_DIR="${DERIVATIVES_DIR}/SimNIBS/${BIDS_SUBJECT_ID}"

# Create SimNIBS directory
mkdir -p "$SIMNIBS_DIR"

# Ensure BIDS dataset_description.json exists for SimNIBS derivative root
ASSETS_DD_DIR="$script_dir/../assets/dataset_descriptions"
if [ ! -f "$DERIVATIVES_DIR/SimNIBS/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/simnibs.dataset_description.json" ]; then
  mkdir -p "$DERIVATIVES_DIR/SimNIBS"
  cp "$ASSETS_DD_DIR/simnibs.dataset_description.json" "$DERIVATIVES_DIR/SimNIBS/dataset_description.json"
  
  # Fill in project-specific information
  CURRENT_DATE=$(date +"%Y-%m-%d")
  sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$PROJECT_NAME@$CURRENT_DATE\"/" "$DERIVATIVES_DIR/SimNIBS/dataset_description.json" && rm -f "$DERIVATIVES_DIR/SimNIBS/dataset_description.json.tmp"
  sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$PROJECT_NAME\": \"..\/..\/\"\n  }/" "$DERIVATIVES_DIR/SimNIBS/dataset_description.json" && rm -f "$DERIVATIVES_DIR/SimNIBS/dataset_description.json.tmp"
fi

# Set up logging
if ! $QUIET; then
    logs_dir="${DERIVATIVES_DIR}/ti-toolbox/logs/${BIDS_SUBJECT_ID}"
    mkdir -p "$logs_dir"
    # Ensure dataset_description.json exists for ti-toolbox derivative
    if [ ! -f "$DERIVATIVES_DIR/ti-toolbox/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/ti-toolbox.dataset_description.json" ]; then
        mkdir -p "$DERIVATIVES_DIR/ti-toolbox"
        cp "$ASSETS_DD_DIR/ti-toolbox.dataset_description.json" "$DERIVATIVES_DIR/ti-toolbox/dataset_description.json"
    fi
    set_logger_name "charm"
    timestamp=$(date +"%Y%m%d_%H%M%S")
    set_log_file "${logs_dir}/charm_${timestamp}.log"
    
    # Configure external loggers for SimNIBS
    configure_external_loggers '["simnibs", "charm"]'
fi

log_info "Starting SimNIBS charm for subject: $SUBJECT_ID"

# Find T1 and T2 images
T1_file=""
T2_file=""

# First try to find files with T1/T1w in the name
for t1_candidate in "$BIDS_ANAT_DIR"/*T1*.nii* "$BIDS_ANAT_DIR"/*t1*.nii*; do
    if [ -f "$t1_candidate" ]; then
        T1_file="$t1_candidate"
        log_info "Found T1 image: $T1_file"
        break
    fi
done

# Look for T2 images
for t2_candidate in "$BIDS_ANAT_DIR"/*T2*.nii* "$BIDS_ANAT_DIR"/*t2*.nii*; do
    if [ -f "$t2_candidate" ]; then
        T2_file="$t2_candidate"
        log_info "Found T2 image: $T2_file"
        break
    fi
done

# Convert to absolute paths if files were found
if [ -f "$T1_file" ]; then
    T1_file="$(cd "$(dirname "$T1_file")" && pwd)/$(basename "$T1_file")"
else
    log_error "No T1 image found in $BIDS_ANAT_DIR"
    log_error "Please ensure anatomical MRI data is available."
    exit 1
fi

if [ -f "$T2_file" ]; then
    T2_file="$(cd "$(dirname "$T2_file")" && pwd)/$(basename "$T2_file")"
    log_info "T2 image found: $T2_file"
else
    log_info "No T2 image found. Proceeding with T1 only."
    T2_file=""
fi

log_info "Creating head model with SimNIBS charm..."

# Check if m2m directory already exists
m2m_dir="$SIMNIBS_DIR/m2m_${SUBJECT_ID}"
forcerun=""
if [ -d "$m2m_dir" ] && [ "$(ls -A "$m2m_dir" 2>/dev/null)" ]; then
    log_warning "Head model directory already contains files. Using --forcerun option."
    forcerun="--forcerun"
fi

# Function to run command with proper error handling
run_command() {
    local cmd="$1"
    local error_msg="$2"
    
    # Run cmd, capture both stdout and stderr,
    # append everything to the log file, and still show on console.
    local temp_output=$(mktemp)
    local exit_code=0
    
    # Execute command and capture output
    if ! eval "$cmd" 2>&1 | tee "$temp_output" | tee -a "$LOG_FILE"; then
        exit_code=1
    fi
    
    # Check for SimNIBS-specific errors
    if grep -q "ERROR\|FAILED\|Fatal\|Error" "$temp_output"; then
        log_error "Command encountered errors: $cmd"
        log_error "$error_msg"
        rm -f "$temp_output"
        return 1
    fi
    
    rm -f "$temp_output"
    
    if [ $exit_code -ne 0 ]; then
        log_error "$error_msg"
        return 1
    fi
    
    return 0
}

# Memory safeguards to prevent PETSC segmentation faults
# Note: We only run one charm process at a time (sequential), but allow each charm 
# to use multiple threads for optimal performance

# Add memory debugging options for PETSC (optional - can help with debugging)
export PETSC_OPTIONS="-malloc_debug -malloc_dump"

# Add a small delay before starting charm to reduce memory contention when multiple subjects
sleep $((RANDOM % 3 + 1))

log_info "Starting charm with memory safeguards (multi-threaded, but sequential execution)..."

# Change to SimNIBS directory and run charm
cd "$SIMNIBS_DIR" || exit 1

if [ -n "$T2_file" ]; then
    log_info "Running charm with T1 and T2 images..."
    if ! run_command "charm $forcerun '$SUBJECT_ID' '$T1_file' '$T2_file'" "SimNIBS charm failed with T1 and T2 images"; then
        exit 1
    fi
else
    log_info "Running charm with T1 image only..."
    if ! run_command "charm $forcerun '$SUBJECT_ID' '$T1_file'" "SimNIBS charm failed with T1 image only"; then
        exit 1
    fi
fi

log_info "SimNIBS charm completed successfully for subject: $SUBJECT_ID" 
