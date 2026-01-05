#!/bin/bash
#
# FreeSurfer recon-all Wrapper Script
# Runs FreeSurfer recon-all on a single subject
#
# Usage: ./recon-all.sh <subject_dir> [--quiet] [--parallel]
#

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_UTIL_CANDIDATES=(
    "$script_dir/../bash_logging.sh"
    "$script_dir/../tools/bash_logging.sh"
)
log_util_path=""
for candidate in "${LOG_UTIL_CANDIDATES[@]}"; do
    if [[ -f "$candidate" ]]; then
        log_util_path="$candidate"
        break
    fi
done
if [[ -n "$log_util_path" ]]; then
    source "$log_util_path"
else
    echo "[WARN] bash_logging.sh not found (looked in: ${LOG_UTIL_CANDIDATES[*]}). Proceeding without enhanced logging." >&2
fi

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

# Function to cleanup incomplete FreeSurfer directories
cleanup_on_failure() {
    local subject_fs_dir="$1"
    local subject_id="$2"
    
    if [ -d "$subject_fs_dir" ]; then
        log_warning "Cleaning up incomplete FreeSurfer directory for subject: $subject_id"
        rm -rf "$subject_fs_dir"
        log_info "Incomplete directory removed: $subject_fs_dir"
    fi
}

# Function to run command with proper error handling and timeout
run_command() {
    local cmd="$1"
    local error_msg="$2"
    
    log_info "Running: $cmd"
    
    # Execute command and capture both exit status and output
    local temp_output=$(mktemp)
    local exit_code=0
    
    # Execute command and capture output with unbuffered output
    if ! eval "$cmd" 2>&1 | stdbuf -oL -eL tee "$temp_output" | stdbuf -oL -eL tee -a "$LOG_FILE"; then
        exit_code=1
    fi
    
    # Check for successful completion message FIRST - this is most important
    if grep -q "finished without error" "$temp_output"; then
        log_info "FreeSurfer completed successfully"
        rm -f "$temp_output"
        return 0
    fi
    
    # Only check for errors if FreeSurfer didn't complete successfully
    # Check for critical system-level errors
    if grep -q "Illegal instruction\|Segmentation fault\|Bus error\|Killed\|Aborted" "$temp_output"; then
        log_error "Command failed with critical system error: $cmd"
        log_error "System error details: $(grep -E "Illegal instruction|Segmentation fault|Bus error|Killed|Aborted" "$temp_output" | head -3)"
        log_error "$error_msg"
        rm -f "$temp_output"
        return 1
    fi
    
    # Check for specific interpreter errors
    if grep -q "bad interpreter\|No such file or directory.*interpreter" "$temp_output"; then
        log_error "Command failed due to missing interpreter (likely tcsh): $cmd"
        log_error "$error_msg"
        rm -f "$temp_output"
        return 1
    fi
    
    # Check for FreeSurfer-specific failure patterns
    if grep -q "recon-all.*exited with ERRORS\|FAILED.*recon-all\|Fatal error in recon-all\|ERROR: must specify a subject" "$temp_output"; then
        log_error "Command encountered FreeSurfer errors: $cmd"
        log_error "FreeSurfer error details: $(grep -E "recon-all.*exited with ERRORS|FAILED.*recon-all|Fatal error in recon-all|ERROR: must specify a subject" "$temp_output" | head -3)"
        log_error "$error_msg"
        rm -f "$temp_output"
        return 1
    fi
    
    rm -f "$temp_output"
    
    # Check exit code if no success/error patterns found
    if [ $exit_code -ne 0 ]; then
        log_error "$error_msg"
        return 1
    fi
    
    return 0
}

# Function to verify FreeSurfer completion by checking log file
verify_freesurfer_completion() {
    local subject_fs_dir="$1"
    local subject_id="$2"
    
    log_info "Checking FreeSurfer completion status for subject: $subject_id"
    
    # Check if recon-all.log exists and contains any completion markers
    local log_file="$subject_fs_dir/scripts/recon-all.log"
    
    if [ -f "$log_file" ]; then
        # Look for any indication of completion
        if grep -q "finished without error\|recon-all.*finished\|Make done\|recon-all.*completed\|recon-all.*done" "$log_file"; then
            log_info "Found completion marker in recon-all.log"
            return 0
        else
            log_warning "No completion marker found in recon-all.log, but continuing anyway"
            return 0
        fi
    else
        log_warning "FreeSurfer log file not found: $log_file, but continuing anyway"
        return 0
    fi
}

# Function to validate input data before processing
validate_input_data() {
    local t1_file="$1"
    local t2_file="$2"
    local subject_id="$3"
    
    log_info "Checking input data for subject: $subject_id"
    
    # Basic check for T1 file existence
    if [ ! -f "$t1_file" ]; then
        log_error "T1 file does not exist: $t1_file"
        return 1
    fi
    
    # Basic check for T1 file readability
    if [ ! -r "$t1_file" ]; then
        log_error "T1 file is not readable: $t1_file"
        return 1
    fi
    
    log_info "T1 file exists and is readable: $(basename "$t1_file")"
    
    # Check T2 file if provided
    if [ -n "$t2_file" ]; then
        if [ ! -f "$t2_file" ]; then
            log_warning "T2 file does not exist: $t2_file, continuing with T1 only"
            return 0
        fi
        
        if [ ! -r "$t2_file" ]; then
            log_warning "T2 file is not readable: $t2_file, continuing with T1 only"
            return 0
        fi
        
        log_info "T2 file exists and is readable: $(basename "$t2_file")"
    fi
    
    return 0
}

# Function to monitor system resources
monitor_resources() {
    local context="$1"
    log_info "Resource monitoring - $context:"
    
    # Memory information
    if command -v free &>/dev/null; then
        log_info "Memory usage: $(free -h | grep '^Mem:' | awk '{print "Used: "$3"/"$2" ("$3/$2*100"%), Available: "$7}')"
    fi
    
    # Load average
    if [ -f /proc/loadavg ]; then
        log_info "Load average: $(cat /proc/loadavg | awk '{print $1" "$2" "$3}')"
    fi
    
    # Available disk space for output directory
    if command -v df &>/dev/null; then
        local disk_usage=$(df -h "$SUBJECTS_DIR" 2>/dev/null | tail -1 | awk '{print "Used: "$3"/"$2" ("$5"), Available: "$4}')
        log_info "Disk usage (FreeSurfer output): $disk_usage"
    fi
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

# Validate that we have a proper subject ID
if [ -z "$SUBJECT_ID" ] || [ "$SUBJECT_ID" = "sub-" ]; then
    echo "Error: Failed to extract subject ID from path: $SUBJECT_DIR"
    echo "Expected format: /path/to/sub-XXX"
    exit 1
fi

# Define directories
BIDS_ANAT_DIR="${PROJECT_DIR}/${BIDS_SUBJECT_ID}/anat"
DERIVATIVES_DIR="${PROJECT_DIR}/derivatives"
SUBJECTS_DIR="${DERIVATIVES_DIR}/freesurfer"

# Create FreeSurfer subjects directory
mkdir -p "$SUBJECTS_DIR"

# Ensure BIDS dataset_description.json exists for FreeSurfer derivative root
ASSETS_DD_DIR="$script_dir/../resources/dataset_descriptions"
if [ ! -f "$DERIVATIVES_DIR/freesurfer/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/freesurfer.dataset_description.json" ]; then
    mkdir -p "$DERIVATIVES_DIR/freesurfer"
    cp "$ASSETS_DD_DIR/freesurfer.dataset_description.json" "$DERIVATIVES_DIR/freesurfer/dataset_description.json"
    
    # Fill in project-specific information
    PROJECT_NAME=$(basename "$PROJECT_DIR")
    CURRENT_DATE=$(date +"%Y-%m-%d")
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$PROJECT_NAME@$CURRENT_DATE\"/" "$DERIVATIVES_DIR/freesurfer/dataset_description.json" && rm -f "$DERIVATIVES_DIR/freesurfer/dataset_description.json.tmp"
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$PROJECT_NAME\": \"..\/..\/\"\n  }/" "$DERIVATIVES_DIR/freesurfer/dataset_description.json" && rm -f "$DERIVATIVES_DIR/freesurfer/dataset_description.json.tmp"
fi

# Set up logging
if ! $QUIET; then
    logs_dir="${DERIVATIVES_DIR}/tit/logs/${BIDS_SUBJECT_ID}"
    mkdir -p "$logs_dir"
    # Ensure dataset_description.json exists for tit derivative
    if [ ! -f "$DERIVATIVES_DIR/tit/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/tit.dataset_description.json" ]; then
        mkdir -p "$DERIVATIVES_DIR/tit"
        cp "$ASSETS_DD_DIR/tit.dataset_description.json" "$DERIVATIVES_DIR/tit/dataset_description.json"
        
        # Fill in project-specific information
        PROJECT_NAME=$(basename "$PROJECT_DIR")
        CURRENT_DATE=$(date +"%Y-%m-%d")
        sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$PROJECT_NAME@$CURRENT_DATE\"/" "$DERIVATIVES_DIR/tit/dataset_description.json" && rm -f "$DERIVATIVES_DIR/tit/dataset_description.json.tmp"
        sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$PROJECT_NAME\": \"..\/..\/\"\n  }/" "$DERIVATIVES_DIR/tit/dataset_description.json" && rm -f "$DERIVATIVES_DIR/tit/dataset_description.json.tmp"
    fi
    set_logger_name "recon-all"
    timestamp=$(date +"%Y%m%d_%H%M%S")
    set_log_file "${logs_dir}/recon-all_${timestamp}.log"
    
    # Configure external loggers for FreeSurfer
    configure_external_loggers '["freesurfer"]'
fi

# Debug logging for subject ID extraction (after logging is set up)
log_debug "Debug info:"
log_debug "  SUBJECT_DIR: $SUBJECT_DIR"
log_debug "  basename result: $(basename "$SUBJECT_DIR")"
log_debug "  SUBJECT_ID: $SUBJECT_ID"
log_debug "  BIDS_SUBJECT_ID: $BIDS_SUBJECT_ID"

log_info "Starting FreeSurfer recon-all for subject: $BIDS_SUBJECT_ID"

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

if [ -z "$T1_file" ] || [ ! -f "$T1_file" ]; then
    log_error "No T1 image found in ${BIDS_ANAT_DIR}, cannot run recon-all for subject: $BIDS_SUBJECT_ID"
    exit 1
fi

# Convert to absolute path
T1_file="$(cd "$(dirname "$T1_file")" && pwd)/$(basename "$T1_file")"

# Find T2 file (optional but improves pial surface reconstruction)
T2_file=""
for t2_candidate in "$BIDS_ANAT_DIR"/*T2*.nii* "$BIDS_ANAT_DIR"/*t2*.nii*; do
    if [ -f "$t2_candidate" ]; then
        T2_file="$t2_candidate"
        log_info "Found T2 image: $T2_file"
        break
    fi
done

# If no T2 found, look for common naming patterns
if [ -z "$T2_file" ]; then
    for t2_candidate in "$BIDS_ANAT_DIR"/T2.nii "$BIDS_ANAT_DIR"/T2.nii.gz; do
        if [ -f "$t2_candidate" ]; then
            T2_file="$t2_candidate"
            log_info "Found T2 image: $T2_file"
            break
        fi
    done
fi

if [ -n "$T2_file" ]; then
    # Convert to absolute path
    T2_file="$(cd "$(dirname "$T2_file")" && pwd)/$(basename "$T2_file")"
    log_info "T2 image will be used for improved pial surface reconstruction"
else
    log_info "No T2 image found - proceeding with T1 only"
fi

# Set threading mode based on processing approach
if $PARALLEL; then
    # APPROACH 1: Sequential processing - use all available cores for this subject
    if command -v nproc &>/dev/null; then
        AVAILABLE_CORES=$(nproc)
    elif command -v sysctl &>/dev/null; then
        AVAILABLE_CORES=$(sysctl -n hw.logicalcpu)
    else
        AVAILABLE_CORES=4  # fallback default
    fi
    
    log_info "SEQUENTIAL MODE: Using all $AVAILABLE_CORES cores for this subject"
    
    # Use all available cores for maximum performance per subject
    export OMP_NUM_THREADS=$AVAILABLE_CORES
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=$AVAILABLE_CORES
    export MKL_NUM_THREADS=$AVAILABLE_CORES
    export NUMBA_NUM_THREADS=$AVAILABLE_CORES
    export VECLIB_MAXIMUM_THREADS=$AVAILABLE_CORES
    export OPENBLAS_NUM_THREADS=$AVAILABLE_CORES
    
    log_info "All threading libraries set to use $AVAILABLE_CORES cores"
else
    # APPROACH 2: Parallel processing - use single core per subject
    log_info "PARALLEL MODE: Using 1 core for this subject (multiple subjects running)"
    
    # Force single-threaded operation to prevent resource conflicts
    export OMP_NUM_THREADS=1
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=1
    export MKL_NUM_THREADS=1
    export NUMBA_NUM_THREADS=1
    export VECLIB_MAXIMUM_THREADS=1
    export OPENBLAS_NUM_THREADS=1
    
    log_info "All threading libraries set to single-threaded mode"
fi

# Additional FreeSurfer-specific optimizations
export SUBJECTS_DIR="$SUBJECTS_DIR"
export FS_FREESURFERENV_NO_OUTPUT=1

# Validate input data before proceeding
if ! validate_input_data "$T1_file" "$T2_file" "$BIDS_SUBJECT_ID"; then
    log_error "Input data validation failed for subject: $BIDS_SUBJECT_ID"
    exit 1
fi

log_info "Running FreeSurfer recon-all..."
log_info "Subject ID: $BIDS_SUBJECT_ID"
log_info "T1 file: $T1_file"
if [ -n "$T2_file" ]; then
    log_info "T2 file: $T2_file"
else
    log_info "T2 file: Not found"
fi
log_info "FreeSurfer subjects directory: $SUBJECTS_DIR"

# Check if subject already exists and require explicit overwrite confirmation
SUBJECT_FS_DIR="$SUBJECTS_DIR/$BIDS_SUBJECT_ID"
if [ -d "$SUBJECT_FS_DIR" ]; then
    if [ "${TI_TOOLBOX_OVERWRITE:-false}" = "true" ] || [ "${TI_TOOLBOX_OVERWRITE:-false}" = "1" ]; then
        log_info "Removing existing FreeSurfer directory for subject: $BIDS_SUBJECT_ID (TI_TOOLBOX_OVERWRITE enabled)"
        rm -rf "$SUBJECT_FS_DIR"
    elif [ "${TI_TOOLBOX_PROMPT_OVERWRITE:-true}" = "false" ] || [ "${TI_TOOLBOX_PROMPT_OVERWRITE:-true}" = "0" ]; then
        log_warning "FreeSurfer output already exists for ${BIDS_SUBJECT_ID}. Skipping recon-all (overwrite not enabled)."
        exit 0
    elif [ -t 0 ]; then
        read -r -p "FreeSurfer output already exists for ${BIDS_SUBJECT_ID}. Delete and re-run recon-all? [y/N]: " ans
        case "$ans" in
            y|Y|yes|YES)
                log_info "User confirmed overwrite. Removing: $SUBJECT_FS_DIR"
                rm -rf "$SUBJECT_FS_DIR"
                ;;
            *)
                log_warning "User declined overwrite. Skipping recon-all for ${BIDS_SUBJECT_ID}."
                exit 0
                ;;
        esac
    else
        log_error "FreeSurfer output already exists for ${BIDS_SUBJECT_ID}. Set TI_TOOLBOX_OVERWRITE=true to overwrite in non-interactive mode."
        exit 1
    fi
fi

log_info "Starting new FreeSurfer analysis for subject: $BIDS_SUBJECT_ID"

# Set up cleanup trap for interruptions
cleanup_and_exit() {
    log_warning "Processing interrupted for subject: $BIDS_SUBJECT_ID"
    cleanup_on_failure "$SUBJECT_FS_DIR" "$BIDS_SUBJECT_ID"
    exit 1
}
trap cleanup_and_exit INT TERM

# Build recon-all command with T2 processing if available
# Monitor resources before starting
monitor_resources "Before FreeSurfer recon-all"

# Run recon-all command directly (avoiding eval for better argument handling)
# Check if we should show detailed output or just log to file
debug_mode="${DEBUG_MODE:-false}"
echo "[DEBUG] recon-all.sh: DEBUG_MODE=$DEBUG_MODE, debug_mode=$debug_mode" >&2

if [ -n "$T2_file" ]; then
    log_info "Using T1 and T2 images with T2pial processing"
    log_info "Running: recon-all -subject $BIDS_SUBJECT_ID -i $T1_file -T2 $T2_file -T2pial -all -sd $SUBJECTS_DIR"
    
    # Execute command with appropriate output handling
    if [ "$debug_mode" = "true" ]; then
        echo "[DEBUG] Running recon-all in DEBUG mode - output will be shown on console" >&2
        # Debug mode: show all output to console AND log file (real-time)
        if ! recon-all -subject "$BIDS_SUBJECT_ID" -i "$T1_file" -T2 "$T2_file" -T2pial -all -sd "$SUBJECTS_DIR" 2>&1 | stdbuf -oL -eL tee -a "$LOG_FILE"; then
            log_error "FreeSurfer recon-all failed for subject: $BIDS_SUBJECT_ID"
            monitor_resources "After FreeSurfer failure"
            exit 1
        fi
    else
        echo "[DEBUG] Running recon-all in SUMMARY mode - output will only go to log file" >&2
        # Summary mode: only log to file (real-time), no console output
        # Use exec to redirect without buffering
        if ! recon-all -subject "$BIDS_SUBJECT_ID" -i "$T1_file" -T2 "$T2_file" -T2pial -all -sd "$SUBJECTS_DIR" 2>&1 | stdbuf -oL -eL cat >> "$LOG_FILE"; then
            log_error "FreeSurfer recon-all failed for subject: $BIDS_SUBJECT_ID"
            monitor_resources "After FreeSurfer failure"
            exit 1
        fi
    fi
else
    log_info "Using T1 image only"
    log_info "Running: recon-all -subject $BIDS_SUBJECT_ID -i $T1_file -all -sd $SUBJECTS_DIR"
    
    # Execute command with appropriate output handling
    if [ "$debug_mode" = "true" ]; then
        echo "[DEBUG] Running recon-all in DEBUG mode - output will be shown on console" >&2
        # Debug mode: show all output to console AND log file (real-time)
        if ! recon-all -subject "$BIDS_SUBJECT_ID" -i "$T1_file" -all -sd "$SUBJECTS_DIR" 2>&1 | stdbuf -oL -eL tee -a "$LOG_FILE"; then
            log_error "FreeSurfer recon-all failed for subject: $BIDS_SUBJECT_ID"
            monitor_resources "After FreeSurfer failure"
            exit 1
        fi
    else
        echo "[DEBUG] Running recon-all in SUMMARY mode - output will only go to log file" >&2
        # Summary mode: only log to file (real-time), no console output
        # Use exec to redirect without buffering
        if ! recon-all -subject "$BIDS_SUBJECT_ID" -i "$T1_file" -all -sd "$SUBJECTS_DIR" 2>&1 | stdbuf -oL -eL cat >> "$LOG_FILE"; then
            log_error "FreeSurfer recon-all failed for subject: $BIDS_SUBJECT_ID"
            monitor_resources "After FreeSurfer failure"
            exit 1
        fi
    fi
fi

# Monitor resources after completion
monitor_resources "After FreeSurfer recon-all"

# Do a basic check for completion but don't fail if not perfect
verify_freesurfer_completion "$SUBJECT_FS_DIR" "$BIDS_SUBJECT_ID"

# Clear the trap since we're done
trap - INT TERM

log_info "FreeSurfer recon-all completed for subject: $BIDS_SUBJECT_ID" 