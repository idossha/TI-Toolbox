#!/bin/bash

# TI-Toolbox Voxel-wise Classifier CLI
# Simple wrapper for the Python classifier

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    echo -e "${1}${2}${NC}"
}

# Function to show usage
show_usage() {
    cat << EOF
TI-Toolbox Voxel-wise Classifier

Usage: $(basename "$0") [OPTIONS]

Options:
    --project-dir PATH      Path to TI-Toolbox project directory (required)
    --response-file PATH    Path to CSV file with response data (required)
    --output-dir PATH       Output directory (optional)
    --help                  Show this help message

Example:
    $(basename "$0") --project-dir /path/to/project --response-file responses.csv

Response File Format:
    CSV file with columns:
    - subject_id: Subject identifier (e.g., sub-101 or 101)
    - response: 1 for responder, -1 or 0 for non-responder
    - simulation_name: (optional) Specific simulation for each subject

EOF
}

# Check if no arguments provided
if [ $# -eq 0 ]; then
    show_usage
    exit 1
fi

# Parse arguments
PROJECT_DIR=""
RESPONSE_FILE=""
OUTPUT_DIR=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --project-dir)
            PROJECT_DIR="$2"
            shift 2
            ;;
        --response-file)
            RESPONSE_FILE="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            print_color "$RED" "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$PROJECT_DIR" ]; then
    print_color "$RED" "Error: --project-dir is required"
    show_usage
    exit 1
fi

if [ -z "$RESPONSE_FILE" ]; then
    print_color "$RED" "Error: --response-file is required"
    show_usage
    exit 1
fi

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    print_color "$RED" "Error: Project directory does not exist: $PROJECT_DIR"
    exit 1
fi

# Check if response file exists
if [ ! -f "$RESPONSE_FILE" ]; then
    print_color "$RED" "Error: Response file does not exist: $RESPONSE_FILE"
    exit 1
fi

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TI_TOOLBOX_DIR="$(dirname "$SCRIPT_DIR")"

# Build Python command
PYTHON_CMD="python3 -m classifier.classifier_cli train"
PYTHON_CMD="$PYTHON_CMD --project-dir \"$PROJECT_DIR\""
PYTHON_CMD="$PYTHON_CMD --response-file \"$RESPONSE_FILE\""

if [ ! -z "$OUTPUT_DIR" ]; then
    PYTHON_CMD="$PYTHON_CMD --output-dir \"$OUTPUT_DIR\""
fi

# Print header
print_color "$BLUE" "=========================================="
print_color "$BLUE" "TI-Toolbox Voxel-wise Classifier"
print_color "$BLUE" "=========================================="
echo ""
print_color "$GREEN" "Project: $PROJECT_DIR"
print_color "$GREEN" "Response file: $RESPONSE_FILE"
if [ ! -z "$OUTPUT_DIR" ]; then
    print_color "$GREEN" "Output directory: $OUTPUT_DIR"
fi
echo ""

# Change to TI-Toolbox directory and run
cd "$TI_TOOLBOX_DIR"

# Execute Python classifier
eval $PYTHON_CMD

# Check exit status
if [ $? -eq 0 ]; then
    print_color "$GREEN" ""
    print_color "$GREEN" "✓ Classification completed successfully!"
else
    print_color "$RED" ""
    print_color "$RED" "✗ Classification failed!"
    exit 1
fi