#!/bin/bash

# bash_logging.sh - Bash wrapper for Python logging utility

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default log file location (can be overridden)
LOG_FILE=""
LOGGER_NAME="bash_script"
LOGGER_INITIALIZED=false

# Initialize logging by calling Python logging utility
init_logging() {
    local name="${1:-$LOGGER_NAME}"
    local log_file="${2:-$LOG_FILE}"
    local is_initialized="False"
    if $LOGGER_INITIALIZED; then
        is_initialized="True"
    fi
    
    # Debug information
    echo "Initializing logging:"
    echo "  Script directory: $SCRIPT_DIR"
    echo "  Logger name: $name"
    echo "  Log file: ${log_file:-None}"
    
    # Create Python command to initialize logging
    python3 - "$name" "$log_file" <<EOF
import sys
import os
sys.path.append('$SCRIPT_DIR')
from logging_util import get_logger
name = sys.argv[1]
log_file = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "" else None

# Ensure the directory exists if log_file is specified
if log_file:
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)

# Get or create logger
logger = get_logger(name, log_file, overwrite=not $is_initialized)

# Verify logger setup
print(f"Logger '{name}' initialized with handlers:", file=sys.stderr)
for handler in logger.handlers:
    print(f"  - {handler.__class__.__name__}: {getattr(handler, 'baseFilename', 'N/A')}", file=sys.stderr)
EOF
    
    LOGGER_INITIALIZED=true
}

# Configure external loggers to use our logging setup
configure_external_loggers() {
    local loggers_json="$1"  # JSON array of logger names
    
    python3 - "$LOGGER_NAME" "$LOG_FILE" "$loggers_json" <<EOF
import sys
import os
sys.path.append('$SCRIPT_DIR')
import json
from logging_util import get_logger, configure_external_loggers

name = sys.argv[1]
log_file = sys.argv[2] if sys.argv[2] != "" else None
loggers = json.loads(sys.argv[3])

# First get the parent logger with proper file handler
parent_logger = get_logger(name, log_file, overwrite=False)

# Configure each external logger with the same log file
for logger_name in loggers:
    logger = get_logger(logger_name, log_file, overwrite=False)
    # Copy handlers from parent logger to ensure consistent setup
    for handler in parent_logger.handlers:
        if not any(isinstance(h, handler.__class__) for h in logger.handlers):
            logger.addHandler(handler)
    print(f"Logger '{logger_name}' configured with handlers:", file=sys.stderr)
    for handler in logger.handlers:
        print(f"  - {handler.__class__.__name__}: {getattr(handler, 'baseFilename', 'N/A')}", file=sys.stderr)

# Now configure the external loggers to use the parent logger's settings
configure_external_loggers(loggers, parent_logger)
print(f"Configured external loggers: {loggers}", file=sys.stderr)
EOF
}

# Logging functions for different levels
log_info() {
    local message="$1"
    if ! $LOGGER_INITIALIZED; then
        init_logging
    fi
    python3 - "$LOGGER_NAME" "$LOG_FILE" <<EOF
import sys, os
sys.path.append('$SCRIPT_DIR')
from logging_util import get_logger
name = sys.argv[1]
log_file = sys.argv[2]
logger = get_logger(name, log_file if log_file!="" else None, overwrite=False)
logger.info(r'''$message''')
EOF
}

log_warning() {
    local message="$1"
    if ! $LOGGER_INITIALIZED; then
        init_logging
    fi
    python3 - "$LOGGER_NAME" "$LOG_FILE" <<EOF
import sys, os
sys.path.append('$SCRIPT_DIR')
from logging_util import get_logger
name = sys.argv[1]
log_file = sys.argv[2]
logger = get_logger(name, log_file if log_file!="" else None, overwrite=False)
logger.warning(r'''$message''')
EOF
}

log_error() {
    local message="$1"
    if ! $LOGGER_INITIALIZED; then
        init_logging
    fi
    python3 - "$LOGGER_NAME" "$LOG_FILE" <<EOF
import sys, os
sys.path.append('$SCRIPT_DIR')
from logging_util import get_logger
name = sys.argv[1]
log_file = sys.argv[2]
logger = get_logger(name, log_file if log_file!="" else None, overwrite=False)
logger.error(r'''$message''')
EOF
}

log_debug() {
    local message="$1"
    if ! $LOGGER_INITIALIZED; then
        init_logging
    fi
    python3 - "$LOGGER_NAME" "$LOG_FILE" <<EOF
import sys, os
sys.path.append('$SCRIPT_DIR')
from logging_util import get_logger
name = sys.argv[1]
log_file = sys.argv[2]
logger = get_logger(name, log_file if log_file!="" else None, overwrite=False)
logger.debug(r'''$message''')
EOF
}

# Function to set the log file
set_log_file() {
    LOG_FILE="$1"
    echo "Setting log file to: $LOG_FILE" >&2
    init_logging "$LOGGER_NAME" "$LOG_FILE"
}

# Function to set logger name
set_logger_name() {
    LOGGER_NAME="$1"
    echo "Setting logger name to: $LOGGER_NAME" >&2
    init_logging "$LOGGER_NAME" "$LOG_FILE"
}

# =============================================================================
# SUMMARY LOGGING SYSTEM FOR NON-DEBUG MODE
# =============================================================================

# Global variables for tracking processes
declare -A PROCESS_START_TIMES
declare -A PROCESS_NAMES
SUMMARY_ENABLED=true
TOTAL_START_TIME=""

# Function to enable/disable summary mode
set_summary_mode() {
    local enabled="$1"
    if [[ "$enabled" == "true" || "$enabled" == "1" ]]; then
        SUMMARY_ENABLED=true
    else
        SUMMARY_ENABLED=false
    fi
}

# Function to format duration in human-readable format
format_duration() {
    local total_seconds="$1"
    local hours=$((total_seconds / 3600))
    local minutes=$(((total_seconds % 3600) / 60))
    local seconds=$((total_seconds % 60))
    
    if [ $hours -gt 0 ]; then
        printf "%dh %dm %ds" $hours $minutes $seconds
    elif [ $minutes -gt 0 ]; then
        printf "%dm %ds" $minutes $seconds
    else
        printf "%ds" $seconds
    fi
}

# Function to start preprocessing for a subject
log_preprocessing_start() {
    local subject_id="$1"
    TOTAL_START_TIME=$(date +%s)
    
    if $SUMMARY_ENABLED; then
        echo "Beginning pre-processing for subject: $subject_id"
        # In summary mode, only log to file (not console)
        log_info "Beginning pre-processing for subject: $subject_id" >/dev/null 2>&1
    else
        # In debug mode, log normally
        log_info "Beginning pre-processing for subject: $subject_id"
    fi
}

# Function to complete preprocessing for a subject
log_preprocessing_complete() {
    local subject_id="$1"
    local success="${2:-true}"
    
    if [[ -n "$TOTAL_START_TIME" ]]; then
        local end_time=$(date +%s)
        local total_duration=$((end_time - TOTAL_START_TIME))
        local formatted_duration=$(format_duration $total_duration)
        
        if $SUMMARY_ENABLED; then
            if [[ "$success" == "true" ]]; then
                echo "└─ Pre-processing completed successfully for subject: $subject_id (Total: $formatted_duration)"
            else
                echo "└─ Pre-processing failed for subject: $subject_id (Total: $formatted_duration)"
            fi
            # In summary mode, only log to file (not console)
            if [[ "$success" == "true" ]]; then
                log_info "Pre-processing completed successfully for subject: $subject_id (Total: $formatted_duration)" >/dev/null 2>&1
            else
                log_error "Pre-processing failed for subject: $subject_id (Total: $formatted_duration)" >/dev/null 2>&1
            fi
        else
            # In debug mode, log normally
            if [[ "$success" == "true" ]]; then
                log_info "Pre-processing completed successfully for subject: $subject_id (Total: $formatted_duration)"
            else
                log_error "Pre-processing failed for subject: $subject_id (Total: $formatted_duration)"
            fi
        fi
    fi
}

# Function to start a process
log_process_start() {
    local process_name="$1"
    local subject_id="$2"
    local process_key="${subject_id}_${process_name}"
    
    PROCESS_START_TIMES["$process_key"]=$(date +%s)
    PROCESS_NAMES["$process_key"]="$process_name"
    
    if $SUMMARY_ENABLED; then
        echo "├─ $process_name: Starting..."
        # In summary mode, only log to file (not console)
        log_info "Starting $process_name for subject: $subject_id" >/dev/null 2>&1
    else
        # In debug mode, log normally
        log_info "Starting $process_name for subject: $subject_id"
    fi
}

# Function to complete a process successfully
log_process_complete() {
    local process_name="$1"
    local subject_id="$2"
    local process_key="${subject_id}_${process_name}"
    
    if [[ -n "${PROCESS_START_TIMES[$process_key]}" ]]; then
        local end_time=$(date +%s)
        local duration=$((end_time - PROCESS_START_TIMES[$process_key]))
        local formatted_duration=$(format_duration $duration)
        
        if $SUMMARY_ENABLED; then
            echo "├─ $process_name: ✓ Complete ($formatted_duration)"
            # In summary mode, only log to file (not console)
            log_info "$process_name completed successfully for subject: $subject_id ($formatted_duration)" >/dev/null 2>&1
        else
            # In debug mode, log normally
            log_info "$process_name completed successfully for subject: $subject_id ($formatted_duration)"
        fi
        
        # Clean up
        unset PROCESS_START_TIMES["$process_key"]
        unset PROCESS_NAMES["$process_key"]
    fi
}

# Function to mark a process as failed
log_process_failed() {
    local process_name="$1"
    local subject_id="$2"
    local error_message="$3"
    local process_key="${subject_id}_${process_name}"
    
    local formatted_duration=""
    if [[ -n "${PROCESS_START_TIMES[$process_key]}" ]]; then
        local end_time=$(date +%s)
        local duration=$((end_time - PROCESS_START_TIMES[$process_key]))
        formatted_duration=" ($(format_duration $duration))"
        
        # Clean up
        unset PROCESS_START_TIMES["$process_key"]
        unset PROCESS_NAMES["$process_key"]
    fi
    
    if $SUMMARY_ENABLED; then
        echo "├─ $process_name: ✗ Failed$formatted_duration - $error_message"
        # In summary mode, only log to file (not console)
        log_error "$process_name failed for subject: $subject_id$formatted_duration - $error_message" >/dev/null 2>&1
    else
        # In debug mode, log normally
        log_error "$process_name failed for subject: $subject_id$formatted_duration - $error_message"
    fi
}

# Function to extract meaningful error from log files
extract_log_error() {
    local process_name="$1"
    local subject_id="$2"
    
    # Determine log file pattern based on process
    local log_pattern=""
    case "$process_name" in
        "DICOM conversion")
            log_pattern="dicom2nifti_*.log"
            ;;
        "SimNIBS charm")
            log_pattern="charm_*.log"
            ;;
        "FreeSurfer recon-all")
            log_pattern="recon-all_*.log"
            ;;
        *)
            return 1
            ;;
    esac
    
    # Try to find the most recent log file
    local bids_subject_id="sub-${subject_id}"
    local log_dir="/mnt/*/derivatives/logs/${bids_subject_id}"
    local log_file=""
    
    # Find the most recent log file matching the pattern
    for dir in $log_dir; do
        if [ -d "$dir" ]; then
            log_file=$(find "$dir" -name "$log_pattern" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
            if [ -f "$log_file" ]; then
                break
            fi
        fi
    done
    
    if [ ! -f "$log_file" ]; then
        return 1
    fi
    
    # Extract meaningful error messages based on process type
    local error_msg=""
    case "$process_name" in
        "DICOM conversion")
            # Look for dcm2niix errors, file not found, permission errors
            error_msg=$(grep -E "\[ERROR\]|dcm2niix.*error|No such file|Permission denied|Cannot access" "$log_file" | head -1 | sed 's/.*\[ERROR\] *//' | cut -c1-120)
            ;;
        "SimNIBS charm")
            # Look for SimNIBS-specific errors, segmentation faults, missing files
            error_msg=$(grep -E "\[ERROR\]|ERROR|Fatal|Traceback|No such file|command not found|Segmentation fault|charm.*failed" "$log_file" | head -1 | sed 's/.*ERROR[^:]*: *//' | cut -c1-120)
            ;;
        "FreeSurfer recon-all")
            # Look for FreeSurfer-specific errors - more comprehensive patterns
            error_msg=$(grep -E "\[ERROR\]|ERROR:|FAILED|exited with ERRORS|No such file|recon-all.*failed|terminated with exit status|mri_convert.*failed|mri_nu_correct.*failed|No T1 volumes found" "$log_file" | head -1 | sed 's/.*\[ERROR\][[:space:]]*//' | sed 's/.*ERROR:[[:space:]]*//' | cut -c1-120)
            
            # If no specific error found, look for common FreeSurfer failure patterns
            if [ -z "$error_msg" ]; then
                error_msg=$(grep -E "recon-all -s.*exited|Cannot find|does not exist|Permission denied|Disk full" "$log_file" | head -1 | cut -c1-120)
            fi
            ;;
    esac
    
    if [ -n "$error_msg" ]; then
        echo "$error_msg"
        return 0
    fi
    
    return 1
}

# Function to execute a command with summary tracking
execute_with_summary() {
    local process_name="$1"
    local subject_id="$2"
    local command="$3"
    local error_context="$4"
    
    log_process_start "$process_name" "$subject_id"
    
    # Execute the command and capture output and exit code
    local temp_output=$(mktemp)
    local exit_code=0
    
    # Run command and capture all output to temp file
    # In summary mode, the individual scripts will handle their own logging to files
    # We just capture output to check for errors and success
    if eval "$command" > "$temp_output" 2>&1; then
        exit_code=0
    else
        exit_code=$?
    fi
    
    # Check for success
    if [ $exit_code -eq 0 ]; then
        # Check for ERROR messages in output even if exit code is 0
        if grep -q "\[ERROR\]" "$temp_output"; then
            local first_error=$(grep "\[ERROR\]" "$temp_output" | head -1 | sed 's/.*\[ERROR\] *//')
            log_process_failed "$process_name" "$subject_id" "$first_error"
            rm -f "$temp_output"
            return 1
        else
            log_process_complete "$process_name" "$subject_id"
            rm -f "$temp_output"
            return 0
        fi
    else
        # Command failed - try to get detailed error from log file first
        local error_msg=""
        local detailed_error=$(extract_log_error "$process_name" "$subject_id")
        
        if [ -n "$detailed_error" ]; then
            # Filter out cases where detailed_error is just the subject ID
            if [[ "$detailed_error" != "$subject_id" && "$detailed_error" != "sub-$subject_id" ]]; then
                error_msg="$detailed_error"
            fi
        fi
        
        # If we don't have a good error message yet, try fallback extraction
        if [ -z "$error_msg" ]; then
            # Fallback to extracting from command output
            if grep -q "\[ERROR\]" "$temp_output"; then
                error_msg=$(grep "\[ERROR\]" "$temp_output" | head -1 | sed 's/.*\[ERROR\] *//')
            elif grep -q "ERROR\|Error\|error" "$temp_output"; then
                # For FreeSurfer, look for more specific error patterns
                if [[ "$process_name" == "FreeSurfer recon-all" ]]; then
                    # Look for specific FreeSurfer error patterns in output
                    error_msg=$(grep -E "recon-all.*exited|terminated with exit status|No T1 volumes|Cannot find|does not exist|failed to run" "$temp_output" | head -1 | tr -d '\n' | cut -c1-120)
                    if [ -z "$error_msg" ]; then
                        error_msg=$(grep -i "error" "$temp_output" | head -1 | tr -d '\n' | cut -c1-100)
                    fi
                else
                    error_msg=$(grep -i "error" "$temp_output" | head -1 | tr -d '\n' | cut -c1-100)
                fi
            else
                error_msg="$error_context"
            fi
        fi
        
        log_process_failed "$process_name" "$subject_id" "$error_msg"
        rm -f "$temp_output"
        return $exit_code
    fi
}

# =============================================================================
# ANALYZER SUMMARY LOGGING SYSTEM
# =============================================================================

# Function to log analysis start for a subject
log_analysis_start() {
    local analysis_type="$1"
    local subject_id="$2"
    local roi_description="$3"
    
    local start_time=$(date +%s)
    PROCESS_START_TIMES["analysis_${subject_id}"]=$start_time
    PROCESS_NAMES["analysis_${subject_id}"]="Analysis"
    
    if $SUMMARY_ENABLED; then
        echo "Beginning analysis for subject: $subject_id ($roi_description)"
    fi
    
    # Always log to file
    log_info "Beginning analysis for subject: $subject_id ($roi_description)" > /dev/null 2>&1
}

# Function to log analysis completion for a subject
log_analysis_complete() {
    local analysis_type="$1"
    local subject_id="$2"
    local results_summary="$3"  # Optional: e.g., "1,247 voxels analyzed"
    
    local process_key="analysis_${subject_id}"
    local start_time=${PROCESS_START_TIMES[$process_key]}
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local duration_str=$(format_duration $duration)
    
    if $SUMMARY_ENABLED; then
        if [ -n "$results_summary" ]; then
            echo "└─ Analysis completed successfully for subject: $subject_id ($results_summary, Total: $duration_str)"
        else
            echo "└─ Analysis completed successfully for subject: $subject_id (Total: $duration_str)"
        fi
    fi
    
    # Always log to file
    log_info "Analysis completed successfully for subject: $subject_id (Total: $duration_str)" > /dev/null 2>&1
    
    # Clean up tracking
    unset PROCESS_START_TIMES[$process_key]
    unset PROCESS_NAMES[$process_key]
}

# Function to log analysis failure for a subject
log_analysis_failed() {
    local analysis_type="$1"
    local subject_id="$2"
    local error_msg="$3"
    
    local process_key="analysis_${subject_id}"
    local start_time=${PROCESS_START_TIMES[$process_key]}
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local duration_str=$(format_duration $duration)
    
    if $SUMMARY_ENABLED; then
        echo "└─ Analysis failed for subject: $subject_id ($duration_str) - $error_msg"
    fi
    
    # Always log to file
    log_error "Analysis failed for subject: $subject_id ($duration_str) - $error_msg" > /dev/null 2>&1
    
    # Clean up tracking
    unset PROCESS_START_TIMES[$process_key]
    unset PROCESS_NAMES[$process_key]
}

# Function to log analysis step start (field loading, ROI processing, etc.)
log_analysis_step_start() {
    local step_name="$1"
    local subject_id="$2"
    
    local step_key="step_${subject_id}_$(echo "$step_name" | tr ' ' '_')"
    local start_time=$(date +%s)
    PROCESS_START_TIMES[$step_key]=$start_time
    
    if $SUMMARY_ENABLED; then
        echo "├─ $step_name: Starting..."
    fi
    
    # Always log to file
    log_info "$step_name: Starting..." > /dev/null 2>&1
}

# Function to log analysis step completion
log_analysis_step_complete() {
    local step_name="$1"
    local subject_id="$2"
    local step_details="$3"  # Optional: e.g., "1,247 voxels"
    
    local step_key="step_${subject_id}_$(echo "$step_name" | tr ' ' '_')"
    local start_time=${PROCESS_START_TIMES[$step_key]}
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local duration_str=$(format_duration $duration)
    
    if $SUMMARY_ENABLED; then
        if [ -n "$step_details" ]; then
            echo "├─ $step_name: ✓ Complete (${duration_str}) - $step_details"
        else
            echo "├─ $step_name: ✓ Complete (${duration_str})"
        fi
    fi
    
    # Always log to file
    log_info "$step_name: Complete (${duration_str})" > /dev/null 2>&1
    
    # Clean up tracking
    unset PROCESS_START_TIMES[$step_key]
}

# Function to log analysis step failure
log_analysis_step_failed() {
    local step_name="$1"
    local subject_id="$2"
    local error_msg="$3"
    
    local step_key="step_${subject_id}_$(echo "$step_name" | tr ' ' '_')"
    local start_time=${PROCESS_START_TIMES[$step_key]}
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local duration_str=$(format_duration $duration)
    
    if $SUMMARY_ENABLED; then
        echo "├─ $step_name: ✗ Failed (${duration_str}) - $error_msg"
    fi
    
    # Always log to file
    log_error "$step_name: Failed (${duration_str}) - $error_msg" > /dev/null 2>&1
    
    # Clean up tracking
    unset PROCESS_START_TIMES[$step_key]
}

# Function to log group analysis start
log_group_analysis_start() {
    local num_subjects="$1"
    local analysis_description="$2"
    
    local start_time=$(date +%s)
    PROCESS_START_TIMES["group_analysis"]=$start_time
    
    if $SUMMARY_ENABLED; then
        echo ""
        echo "Beginning group analysis for $num_subjects subjects ($analysis_description)"
    fi
    
    # Always log to file
    log_info "Beginning group analysis for $num_subjects subjects ($analysis_description)" > /dev/null 2>&1
}

# Function to log group analysis completion
log_group_analysis_complete() {
    local num_successful="$1"
    local num_total="$2"
    local output_path="$3"
    
    local start_time=${PROCESS_START_TIMES["group_analysis"]}
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local duration_str=$(format_duration $duration)
    
    if $SUMMARY_ENABLED; then
        if [ "$num_successful" -eq "$num_total" ]; then
            echo "└─ Group analysis completed ($num_successful/$num_total subjects successful, Total: $duration_str)"
        else
            echo "└─ Group analysis completed with failures ($num_successful/$num_total subjects successful, Total: $duration_str)"
        fi
        if [ -n "$output_path" ]; then
            echo "   Results saved to: $output_path"
        fi
    fi
    
    # Always log to file
    log_info "Group analysis completed ($num_successful/$num_total subjects successful, Total: $duration_str)" > /dev/null 2>&1
    
    # Clean up tracking
    unset PROCESS_START_TIMES["group_analysis"]
}

# Function to log group subject status (for group analysis progress)
log_group_subject_status() {
    local subject_id="$1"
    local status="$2"  # "complete" or "failed"
    local duration_str="$3"
    local error_msg="$4"  # Only for failed subjects
    
    if $SUMMARY_ENABLED; then
        if [ "$status" = "complete" ]; then
            echo "├─ Subject $subject_id: ✓ Complete (${duration_str})"
        else
            echo "├─ Subject $subject_id: ✗ Failed (${duration_str}) - $error_msg"
        fi
    fi
    
    # Always log to file
    if [ "$status" = "complete" ]; then
        log_info "Subject $subject_id: Complete (${duration_str})" > /dev/null 2>&1
    else
        log_error "Subject $subject_id: Failed (${duration_str}) - $error_msg" > /dev/null 2>&1
    fi
} 