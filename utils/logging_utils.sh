#!/bin/bash

##############################################
# Shared logging utilities for TI-CSC tools
# This script provides shell functions for logging that match
# the functionality of the Python logging_utils.py module
##############################################

# Define color variables for console output
BOLD='\033[1m'
UNDERLINE='\033[4m'
RESET='\033[0m'
RED='\033[0;31m'     # Red for errors
GREEN='\033[0;32m'   # Green for success
CYAN='\033[0;36m'    # Cyan for actions
YELLOW='\033[0;33m'  # Yellow for warnings

# Global variables for logging configuration
LOG_FILE=""
LOG_LEVEL="INFO"  # Default log level
DEBUG_ENABLED=false

# Log levels and their numeric values (higher number = more severe)
declare -A LOG_LEVELS=(
    ["DEBUG"]=0
    ["INFO"]=1
    ["WARNING"]=2
    ["ERROR"]=3
)

# Initialize logging
setup_logging() {
    local output_dir="$1"
    local tool_name="$2"
    local debug="${3:-false}"  # Optional debug parameter, defaults to false
    
    # Create output directory if it doesn't exist
    mkdir -p "$output_dir"
    
    # Set log file path
    LOG_FILE="$output_dir/${tool_name}_pipeline.log"
    
    # Set debug mode if requested
    if [[ "$debug" == "true" ]]; then
        DEBUG_ENABLED=true
        LOG_LEVEL="DEBUG"
    else
        DEBUG_ENABLED=false
        LOG_LEVEL="INFO"
    fi
    
    # Create timestamp for log entries
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Clear existing log file and write initial entries
    > "$LOG_FILE"
    echo -e "${CYAN}[${timestamp}] Starting ${tool_name} pipeline${RESET}" >> "$LOG_FILE"
    echo -e "${CYAN}[${timestamp}] Log file created at: ${LOG_FILE}${RESET}" >> "$LOG_FILE"
    
    if [[ "$DEBUG_ENABLED" == "true" ]]; then
        echo -e "${CYAN}[${timestamp}] Debug logging enabled${RESET}" >> "$LOG_FILE"
    fi
    
    # Export variables for use in other functions
    export LOG_FILE
    export LOG_LEVEL
    export DEBUG_ENABLED
}

# Function to check if a message should be logged based on current log level
should_log() {
    local msg_level="$1"
    
    # Get numeric values for comparison
    local current_level=${LOG_LEVELS[$LOG_LEVEL]}
    local msg_level_num=${LOG_LEVELS[$msg_level]}
    
    # Log if message level is higher than or equal to current level
    [[ $msg_level_num -ge $current_level ]]
}

# Log a message with a specific level
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Check if we should log this message
    if ! should_log "$level"; then
        return 0
    fi
    
    # Set color based on level
    local color=""
    case "$level" in
        "ERROR")
            color="$RED"
            ;;
        "WARNING")
            color="$YELLOW"
            ;;
        "SUCCESS")
            color="$GREEN"
            ;;
        "ACTION")
            color="$CYAN"
            ;;
        *)
            color=""
            ;;
    esac
    
    # Format the message
    local formatted_msg="${color}[${timestamp}] ${level}: ${message}${RESET}"
    
    # Write to log file if it exists
    if [[ -n "$LOG_FILE" ]]; then
        echo -e "$formatted_msg" >> "$LOG_FILE"
    fi
    
    # Print to console with colors
    echo -e "$formatted_msg"
}

# Convenience functions for different log levels
log_error() {
    local message="$1"
    log "ERROR" "$message"
}

log_warning() {
    local message="$1"
    log "WARNING" "$message"
}

log_success() {
    local message="$1"
    log "SUCCESS" "$message"
}

log_action() {
    local message="$1"
    log "ACTION" "$message"
}

log_info() {
    local message="$1"
    log "INFO" "$message"
}

log_debug() {
    local message="$1"
    if [[ "$DEBUG_ENABLED" == "true" ]]; then
        log "DEBUG" "$message"
    fi
}

# Function to log command outputs with proper error handling
log_cmd() {
    local cmd="$1"
    local output
    local exit_code
    
    # Log the command being executed
    log_debug "Executing command: $cmd"
    
    # Execute command and capture output and exit code
    if output=$($cmd 2>&1); then
        exit_code=0
    else
        exit_code=$?
    fi
    
    # Log the output based on exit code
    if [[ $exit_code -eq 0 ]]; then
        [[ -n "$output" ]] && log_debug "$output"
    else
        log_error "Command failed with exit code $exit_code"
        [[ -n "$output" ]] && log_error "$output"
        return $exit_code
    fi
}

# Function to log script parameters
log_script_params() {
    log_info "Script Parameters:"
    for param in "$@"; do
        log_debug "  $param"
    done
    log_info "----------------------------------------"
}

# Function to log simulation parameters
log_simulation_params() {
    local subject_id="$1"
    local conductivity="$2"
    local sim_mode="$3"
    local intensity="$4"
    local electrode_shape="$5"
    local dimensions="$6"
    local thickness="$7"
    local montages="$8"
    
    log_info "Simulation Parameters:"
    log_info "- Subject ID: $subject_id"
    log_info "- Conductivity: $conductivity"
    log_info "- Simulation Mode: $sim_mode"
    log_info "- Intensity: $intensity A"
    log_info "- Electrode Shape: $electrode_shape"
    log_info "- Electrode Dimensions: $dimensions mm"
    log_info "- Electrode Thickness: $thickness mm"
    log_info "- Montages: $montages"
    log_info "----------------------------------------"
}

# Function to log section header
log_section() {
    local section_name="$1"
    log_info ""
    log_info "=== $section_name ==="
    log_info ""
}

# Function to log file operations
log_file_operation() {
    local operation="$1"  # e.g., "moved", "created", "deleted"
    local file="$2"
    local details="${3:-}"  # optional additional details
    
    if [[ -n "$details" ]]; then
        log_debug "File $operation: $file ($details)"
    else
        log_debug "File $operation: $file"
    fi
}

# Function to log completion status
log_completion() {
    local status="$1"  # "success" or "error"
    local message="$2"
    
    if [[ "$status" == "success" ]]; then
        log_success "$message"
    else
        log_error "$message"
    fi
    
    log_info "----------------------------------------"
}

# Example usage:
# setup_logging "/path/to/output" "simulator" "true"  # Enable debug logging
# log_info "Starting simulation..."
# log_debug "Debug message (only shown if debug is enabled)"
# log_simulation_params "sub-01" "standard" "U" "2" "rect" "50,50" "4" "montage1 montage2"
# log_cmd "simnibs_python script.py --arg1 value1"
# log_completion "success" "Simulation completed successfully" 