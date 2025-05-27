#!/bin/bash


# Initialize logging
setup_logging() {
    local montage_dir="$1"
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local log_file="$montage_dir/Documentation/Simulator_${timestamp}.log"
    mkdir -p "$(dirname "$log_file")"
    # Clear the log file if it exists
    > "$log_file"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [simulator] [INFO] Starting simulation pipeline" >> "$log_file"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [simulator] [INFO] Script version: 2.0" >> "$log_file"
    echo "----------------------------------------" >> "$log_file"
    # Export the log file path so it can be passed to Python script
    export TI_LOG_FILE="$log_file"
}

# Logging function
log() {
    local level="$1"
    local message="$2"
    local montage_dir="$3"
    local log_file="$TI_LOG_FILE"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Format the message based on level
    case "$level" in
        "INFO")
            echo "[$timestamp] [simulator] [INFO] $message" >> "$log_file"
            echo "$message"  # Clean console output
            ;;
        "DEBUG")
            echo "[$timestamp] [simulator] [DEBUG] $message" >> "$log_file"
            ;;
        "ERROR")
            echo "[$timestamp] [simulator] [ERROR] $message" >> "$log_file"
            echo "ERROR: $message" >&2  # Error messages to stderr
            ;;
        *)
            echo "[$timestamp] [simulator] $message" >> "$log_file"
            ;;
    esac
} 