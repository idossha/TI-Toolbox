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