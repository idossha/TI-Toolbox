#!/bin/bash

# bash_reporting.sh - Bash wrapper for Python report utility

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default project directory (can be overridden)
PROJECT_DIR=""
REPORT_INITIALIZED=false

# Initialize reporting by setting project directory
init_reporting() {
    local project_dir="${1:-$PROJECT_DIR}"
    
    if [ -z "$project_dir" ]; then
        echo "Error: Project directory must be specified" >&2
        return 1
    fi
    
    PROJECT_DIR="$project_dir"
    REPORT_INITIALIZED=true
    
    # Debug information
    echo "Initializing reporting:"
    echo "  Script directory: $SCRIPT_DIR"
    echo "  Project directory: $PROJECT_DIR"
}

# Set project directory
set_project_dir() {
    PROJECT_DIR="$1"
    echo "Setting project directory to: $PROJECT_DIR" >&2
    init_reporting "$PROJECT_DIR"
}

# Create a preprocessing report
create_preprocessing_report() {
    local subject_id="$1"
    local processing_log_file="$2"  # Optional JSON file with processing log
    local output_path="$3"          # Optional custom output path
    
    if ! $REPORT_INITIALIZED; then
        echo "Error: Reporting not initialized. Call init_reporting first." >&2
        return 1
    fi
    
    if [ -z "$subject_id" ]; then
        echo "Error: Subject ID is required" >&2
        return 1
    fi
    
    echo "Creating preprocessing report for subject: $subject_id"
    
    # Build Python command arguments
    local python_args="'$PROJECT_DIR' '$subject_id'"
    
    if [ -n "$processing_log_file" ] && [ -f "$processing_log_file" ]; then
        python_args="$python_args '$processing_log_file'"
    else
        python_args="$python_args None"
    fi
    
    if [ -n "$output_path" ]; then
        python_args="$python_args '$output_path'"
    else
        python_args="$python_args None"
    fi
    
    # Create Python command to generate report
    simnibs_python - <<EOF
import sys
import os
import json
from tit.tools.report_util import create_preprocessing_report

project_dir = sys.argv[1]
subject_id = sys.argv[2]
processing_log_file = sys.argv[3] if sys.argv[3] != 'None' else None
output_path = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != 'None' else None

# Load processing log if provided
processing_log = None
if processing_log_file and os.path.exists(processing_log_file):
    try:
        with open(processing_log_file, 'r') as f:
            processing_log = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load processing log: {e}", file=sys.stderr)

# Generate report
try:
    report_path = create_preprocessing_report(
        project_dir=project_dir,
        subject_id=subject_id,
        processing_log=processing_log,
        output_path=output_path
    )
    print(f"Preprocessing report generated: {report_path}")
except Exception as e:
    print(f"Error generating preprocessing report: {e}", file=sys.stderr)
    sys.exit(1)
EOF $python_args
}

# Create a simulation report
create_simulation_report() {
    local simulation_session_id="$1"  # Optional
    local simulation_log_file="$2"    # Optional JSON file with simulation log
    local output_path="$3"            # Optional custom output path
    local subject_id="$4"             # Optional for single-subject reports
    
    if ! $REPORT_INITIALIZED; then
        echo "Error: Reporting not initialized. Call init_reporting first." >&2
        return 1
    fi
    
    echo "Creating simulation report"
    
    # Build Python command arguments
    local python_args="'$PROJECT_DIR'"
    
    if [ -n "$simulation_session_id" ]; then
        python_args="$python_args '$simulation_session_id'"
    else
        python_args="$python_args None"
    fi
    
    if [ -n "$simulation_log_file" ] && [ -f "$simulation_log_file" ]; then
        python_args="$python_args '$simulation_log_file'"
    else
        python_args="$python_args None"
    fi
    
    if [ -n "$output_path" ]; then
        python_args="$python_args '$output_path'"
    else
        python_args="$python_args None"
    fi
    
    if [ -n "$subject_id" ]; then
        python_args="$python_args '$subject_id'"
    else
        python_args="$python_args None"
    fi
    
    # Create Python command to generate report
    simnibs_python - <<EOF
import sys
import os
import json
from tit.tools.report_util import create_simulation_report

project_dir = sys.argv[1]
simulation_session_id = sys.argv[2] if sys.argv[2] != 'None' else None
simulation_log_file = sys.argv[3] if sys.argv[3] != 'None' else None
output_path = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != 'None' else None
subject_id = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != 'None' else None

# Load simulation log if provided
simulation_log = None
if simulation_log_file and os.path.exists(simulation_log_file):
    try:
        with open(simulation_log_file, 'r') as f:
            simulation_log = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load simulation log: {e}", file=sys.stderr)

# Generate report
try:
    report_path = create_simulation_report(
        project_dir=project_dir,
        simulation_session_id=simulation_session_id,
        simulation_log=simulation_log,
        output_path=output_path,
        subject_id=subject_id
    )
    print(f"Simulation report generated: {report_path}")
except Exception as e:
    print(f"Error generating simulation report: {e}", file=sys.stderr)
    sys.exit(1)
EOF $python_args
}

# List existing reports
list_reports() {
    local subject_id="$1"    # Optional
    local report_type="$2"   # Optional: 'preprocessing' or 'simulation'
    
    if ! $REPORT_INITIALIZED; then
        echo "Error: Reporting not initialized. Call init_reporting first." >&2
        return 1
    fi
    
    echo "Listing reports..."
    
    # Build Python command arguments
    local python_args="'$PROJECT_DIR'"
    
    if [ -n "$subject_id" ]; then
        python_args="$python_args '$subject_id'"
    else
        python_args="$python_args None"
    fi
    
    if [ -n "$report_type" ]; then
        python_args="$python_args '$report_type'"
    else
        python_args="$python_args None"
    fi
    
    # Create Python command to list reports
    simnibs_python - <<EOF
import sys
import os
from tit.tools.report_util import list_reports

project_dir = sys.argv[1]
subject_id = sys.argv[2] if sys.argv[2] != 'None' else None
report_type = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != 'None' else None

try:
    reports = list_reports(
        project_dir=project_dir,
        subject_id=subject_id,
        report_type=report_type
    )
    
    if not reports:
        print("No reports found.")
    else:
        print(f"Found {len(reports)} report(s):")
        print("-" * 80)
        for report in reports:
            print(f"Subject: {report['subject_id']}")
            print(f"Type: {report['type']}")
            print(f"File: {report['filename']}")
            print(f"Path: {report['path']}")
            print(f"Modified: {report['modified']}")
            print(f"Size: {report['size']} bytes")
            print("-" * 80)
            
except Exception as e:
    print(f"Error listing reports: {e}", file=sys.stderr)
    sys.exit(1)
EOF $python_args
}

# Get the latest report for a subject
get_latest_report() {
    local subject_id="$1"
    local report_type="$2"  # 'preprocessing' or 'simulation'
    
    if ! $REPORT_INITIALIZED; then
        echo "Error: Reporting not initialized. Call init_reporting first." >&2
        return 1
    fi
    
    if [ -z "$subject_id" ] || [ -z "$report_type" ]; then
        echo "Error: Subject ID and report type are required" >&2
        return 1
    fi
    
    # Create Python command to get latest report
    simnibs_python - "$PROJECT_DIR" "$subject_id" "$report_type" <<EOF
import sys
import os
from tit.tools.report_util import get_latest_report

project_dir = sys.argv[1]
subject_id = sys.argv[2]
report_type = sys.argv[3]

try:
    latest_report = get_latest_report(
        project_dir=project_dir,
        subject_id=subject_id,
        report_type=report_type
    )
    
    if latest_report:
        print(latest_report)
    else:
        print("No reports found for subject $subject_id of type $report_type", file=sys.stderr)
        sys.exit(1)
        
except Exception as e:
    print(f"Error getting latest report: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Function to add a processing step to a JSON log file
add_processing_step_to_log() {
    local log_file="$1"
    local step_name="$2"
    local description="$3"
    local status="$4"
    local duration="$5"
    
    if [ -z "$log_file" ] || [ -z "$step_name" ] || [ -z "$description" ]; then
        echo "Error: log_file, step_name, and description are required" >&2
        return 1
    fi
    
    # Create Python command to add step to log
    simnibs_python - "$log_file" "$step_name" "$description" "$status" "$duration" <<EOF
import sys
import os
import json
import datetime

log_file = sys.argv[1]
step_name = sys.argv[2]
description = sys.argv[3]
status = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else 'completed'
duration = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else None

# Load or create log structure
if os.path.exists(log_file):
    try:
        with open(log_file, 'r') as f:
            log_data = json.load(f)
    except:
        log_data = {'steps': [], 'errors': [], 'warnings': []}
else:
    log_data = {'steps': [], 'errors': [], 'warnings': []}

# Add the processing step
step = {
    'step_name': step_name,
    'description': description,
    'status': status,
    'duration': duration,
    'timestamp': datetime.datetime.now().isoformat()
}

log_data['steps'].append(step)

# Save the log file
try:
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
    with open(log_file, 'w') as f:
        json.dump(log_data, f, indent=2)
    print(f"Added processing step '{step_name}' to {log_file}")
except Exception as e:
    print(f"Error updating log file: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Function to add an error to a JSON log file
add_error_to_log() {
    local log_file="$1"
    local error_message="$2"
    local step="$3"  # Optional
    
    if [ -z "$log_file" ] || [ -z "$error_message" ]; then
        echo "Error: log_file and error_message are required" >&2
        return 1
    fi
    
    # Create Python command to add error to log
    simnibs_python - "$log_file" "$error_message" "$step" <<EOF
import sys
import os
import json
import datetime

log_file = sys.argv[1]
error_message = sys.argv[2]
step = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None

# Load or create log structure
if os.path.exists(log_file):
    try:
        with open(log_file, 'r') as f:
            log_data = json.load(f)
    except:
        log_data = {'steps': [], 'errors': [], 'warnings': []}
else:
    log_data = {'steps': [], 'errors': [], 'warnings': []}

# Add the error
error = {
    'error_message': error_message,
    'step': step,
    'timestamp': datetime.datetime.now().isoformat()
}

log_data['errors'].append(error)

# Save the log file
try:
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
    with open(log_file, 'w') as f:
        json.dump(log_data, f, indent=2)
    print(f"Added error to {log_file}")
except Exception as e:
    print(f"Error updating log file: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Function to add a warning to a JSON log file
add_warning_to_log() {
    local log_file="$1"
    local warning_message="$2"
    local step="$3"  # Optional
    
    if [ -z "$log_file" ] || [ -z "$warning_message" ]; then
        echo "Error: log_file and warning_message are required" >&2
        return 1
    fi
    
    # Create Python command to add warning to log
    simnibs_python - "$log_file" "$warning_message" "$step" <<EOF
import sys
import os
import json
import datetime

log_file = sys.argv[1]
warning_message = sys.argv[2]
step = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None

# Load or create log structure
if os.path.exists(log_file):
    try:
        with open(log_file, 'r') as f:
            log_data = json.load(f)
    except:
        log_data = {'steps': [], 'errors': [], 'warnings': []}
else:
    log_data = {'steps': [], 'errors': [], 'warnings': []}

# Add the warning
warning = {
    'warning_message': warning_message,
    'step': step,
    'timestamp': datetime.datetime.now().isoformat()
}

log_data['warnings'].append(warning)

# Save the log file
try:
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
    with open(log_file, 'w') as f:
        json.dump(log_data, f, indent=2)
    print(f"Added warning to {log_file}")
except Exception as e:
    print(f"Error updating log file: {e}", file=sys.stderr)
    sys.exit(1)
EOF
} 