#!/bin/bash
#
# FreeSurfer recon-all Wrapper Script
# Runs FreeSurfer recon-all on a single subject
#
# Usage: ./recon-all.sh <subject_dir> [--quiet] [--parallel]
#

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/../utils/bash_logging.sh"

# Function to validate FreeSurfer environment
validate_freesurfer_env() {
    if [ -z "$FREESURFER_HOME" ]; then
        log_warning "FREESURFER_HOME is not set. FreeSurfer may not work properly."
        return 1
    fi
    
    if [ ! -d "$FREESURFER_HOME" ]; then
        log_error "FREESURFER_HOME directory does not exist: $FREESURFER_HOME"
        return 1
    fi
    
    # Check if tcsh is available (required by FreeSurfer scripts)
    if ! command -v tcsh &>/dev/null; then
        log_error "tcsh (C shell) is not installed. FreeSurfer requires tcsh to run."
        log_error "Please install tcsh using: apt-get update && apt-get install -y tcsh"
        return 1
    fi
    
    # Check if recon-all script exists and is executable
    if [ ! -x "$FREESURFER_HOME/bin/recon-all" ]; then
        log_error "recon-all script not found or not executable at: $FREESURFER_HOME/bin/recon-all"
        return 1
    fi
    
    return 0
}

# Function to run command with proper error handling
run_command() {
    local cmd="$1"
    local error_msg="$2"
    
    # Execute command and capture both exit status and output
    local temp_output=$(mktemp)
    local exit_code=0
    
    # Execute command and capture output
    if ! eval "$cmd" 2>&1 | tee "$temp_output" | tee -a "$LOG_FILE"; then
        exit_code=1
    fi
    
    # Check for specific interpreter errors
    if grep -q "bad interpreter\|No such file or directory.*interpreter" "$temp_output"; then
        log_error "Command failed due to missing interpreter (likely tcsh): $cmd"
        log_error "$error_msg"
        rm -f "$temp_output"
        return 1
    fi
    
    # Check for FreeSurfer-specific failure patterns (not just keywords)
    if grep -q "recon-all.*exited with ERRORS\|FAILED.*recon-all\|Fatal error in recon-all" "$temp_output"; then
        log_error "Command encountered errors: $cmd"
        log_error "$error_msg"
        rm -f "$temp_output"
        return 1
    fi
    
    # Check for successful completion message
    if grep -q "finished without error" "$temp_output"; then
        log_info "FreeSurfer completed successfully"
        rm -f "$temp_output"
        return 0
    fi
    
    rm -f "$temp_output"
    
    # Only fail if the command actually returned a non-zero exit code
    if [ $exit_code -ne 0 ]; then
        log_error "$error_msg"
        return 1
    fi
    
    return 0
}

# Parse arguments
SUBJECT_DIR=""
QUIET=false
PARALLEL=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quiet)
            QUIET=true
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        *)
            if [[ -z "$SUBJECT_DIR" ]]; then
                SUBJECT_DIR="$1"
            else
                echo "Error: Unknown argument: $1"
                echo "Usage: $0 <subject_dir> [--quiet] [--parallel]"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$SUBJECT_DIR" ]]; then
    echo "Error: Subject directory is required"
    echo "Usage: $0 <subject_dir> [--quiet] [--parallel]"
    exit 1
fi

# Validate subject directory
SUBJECT_DIR="$(cd "$SUBJECT_DIR" 2>/dev/null && pwd)"
if [[ ! -d "$SUBJECT_DIR" ]]; then
    echo "Error: Subject directory does not exist: $SUBJECT_DIR"
    exit 1
fi

# Check if recon-all is available
if ! command -v recon-all &>/dev/null; then
    echo "Error: recon-all (FreeSurfer) is not installed."
    exit 1
fi

# Validate FreeSurfer environment
if ! validate_freesurfer_env; then
    echo "Error: FreeSurfer environment validation failed. Cannot proceed with recon-all."
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
SUBJECTS_DIR="${DERIVATIVES_DIR}/freesurfer"

# Create FreeSurfer subjects directory
mkdir -p "$SUBJECTS_DIR"

# Set up logging
if ! $QUIET; then
    logs_dir="${DERIVATIVES_DIR}/logs/${BIDS_SUBJECT_ID}"
    mkdir -p "$logs_dir"
    set_logger_name "recon-all"
    timestamp=$(date +"%Y%m%d_%H%M%S")
    set_log_file "${logs_dir}/recon-all_${timestamp}.log"
    
    # Configure external loggers for FreeSurfer
    configure_external_loggers '["freesurfer"]'
fi

log_info "Starting FreeSurfer recon-all for subject: $SUBJECT_ID"

# Find T1 file
T1_file=""
for t1_candidate in "$BIDS_ANAT_DIR"/*T1*.nii* "$BIDS_ANAT_DIR"/*t1*.nii*; do
    if [ -f "$t1_candidate" ]; then
        T1_file="$t1_candidate"
        log_info "Found T1 image: $T1_file"
        break
    fi
done

# If no T1 found, look for common naming patterns
if [ -z "$T1_file" ]; then
    for t1_candidate in "$BIDS_ANAT_DIR"/T1.nii "$BIDS_ANAT_DIR"/T1.nii.gz; do
        if [ -f "$t1_candidate" ]; then
            T1_file="$t1_candidate"
            log_info "Found T1 image: $T1_file"
            break
        fi
    done
fi

# If still no T1 found, take the first NIfTI file as T1
if [ -z "$T1_file" ]; then
    for nii_file in "$BIDS_ANAT_DIR"/*.nii*; do
        if [ -f "$nii_file" ]; then
            T1_file="$nii_file"
            log_info "Using $T1_file as T1 image"
            break
        fi
    done
fi

if [ -z "$T1_file" ] || [ ! -f "$T1_file" ]; then
    log_error "No T1 image found in ${BIDS_ANAT_DIR}, cannot run recon-all for subject: $SUBJECT_ID"
    exit 1
fi

# Convert to absolute path
T1_file="$(cd "$(dirname "$T1_file")" && pwd)/$(basename "$T1_file")"

# Set thread limits for parallel processing
if $PARALLEL; then
    log_info "Setting thread limits for parallel processing (OMP_NUM_THREADS=1)"
    export OMP_NUM_THREADS=1
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1
else
    log_info "Running in single-process mode (using default thread counts)"
fi

log_info "Running FreeSurfer recon-all..."
log_info "Subject ID: $SUBJECT_ID"
log_info "T1 file: $T1_file"
log_info "FreeSurfer subjects directory: $SUBJECTS_DIR"

# Check if subject already exists and remove it (GUI already confirmed overwrite)
SUBJECT_FS_DIR="$SUBJECTS_DIR/$SUBJECT_ID"
if [ -d "$SUBJECT_FS_DIR" ]; then
    log_info "Removing existing FreeSurfer directory for subject: $SUBJECT_ID (overwrite confirmed)"
    rm -rf "$SUBJECT_FS_DIR"
fi

log_info "Starting new FreeSurfer analysis for subject: $SUBJECT_ID"
# New analysis with -i flag
recon_cmd="recon-all -subject \"$SUBJECT_ID\" -i \"$T1_file\" -all -sd \"$SUBJECTS_DIR\""

if ! run_command "$recon_cmd" "FreeSurfer recon-all failed"; then
    log_error "FreeSurfer recon-all failed for subject: $SUBJECT_ID"
    exit 1
fi

log_info "FreeSurfer recon-all completed successfully for subject: $SUBJECT_ID" 