#!/bin/bash
#
# CLI script for collecting user input to execute structural preprocessing
# This script acts as a front-end for structural.sh
#

# Define script directory and base paths
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color definitions for better user interface
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD_CYAN='\033[1;36m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
  local color=$1
  local message=$2
  echo -e "${color}${message}${NC}"
}

# Function to print section header
print_header() {
  local message=$1
  echo ""
  print_message "${BLUE}===================================================${NC}" ""
  print_message "${BLUE}" "  $message"
  print_message "${BLUE}===================================================${NC}" ""
}

# Function to get yes/no input from user
get_yes_no() {
  local prompt=$1
  local default=$2
  local response

  if [ "$default" = "y" ]; then
    prompt="${prompt} [Y/n]: "
  else
    prompt="${prompt} [y/N]: "
  fi

  while true; do
    read -p "$prompt" response
    response=${response:-$default}
    case "${response,,}" in
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *) echo "Please answer yes or no." ;;
    esac
  done
}

# Function to validate directory exists
validate_dir() {
  local dir=$1
  if [ ! -d "$dir" ]; then
    print_message "$RED" "Error: Directory '$dir' does not exist."
    return 1
  fi
  return 0
}

# Print welcome message
clear
print_header "TI-CSC Preprocessing Tool"
print_message "$GREEN" "This tool will guide you through the structural preprocessing pipeline."

# Automatically detect project directory
print_header "Project Configuration"

# First check if we're in a docker environment with /mnt mounted
if [ -d "/mnt" ]; then
  # Look for directories under /mnt
  found_project=false
  for dir in /mnt/*/; do
    if [ -d "$dir" ]; then
      PROJECT_DIR="${dir%/}"
      found_project=true
      break
    fi
  done
  
  if ! $found_project; then
    print_message "$RED" "Error: No project directories found under /mnt"
    exit 1
  fi
else
  # If not in docker, check the current directory structure
  # Try to find project directory relative to script location
  for potential_dir in "$script_dir" "$script_dir/.." "$script_dir/../.."; do
    if [ -d "$potential_dir/BIDS_test" ]; then
      PROJECT_DIR="$potential_dir/BIDS_test"
      break
    fi
  done
  
  # If project directory is still not found, prompt user
  if [ -z "$PROJECT_DIR" ] || [ ! -d "$PROJECT_DIR" ]; then
    print_message "$YELLOW" "Could not automatically detect project directory."
    read -p "Enter the project directory path (absolute path): " PROJECT_DIR
    
    if ! validate_dir "$PROJECT_DIR"; then
      print_message "$RED" "Exiting due to invalid project directory."
      exit 1
    fi
  fi
fi

print_message "$GREEN" "Using project directory: $PROJECT_DIR"

# Get list of available subjects
available_subjects=()
print_message "$BOLD_CYAN" "Available Subjects:"
echo "-------------------"
count=0
for subj_dir in "$PROJECT_DIR"/*; do
  if [ -d "$subj_dir" ] && [ "$(basename "$subj_dir")" != "config" ] && [ "$(basename "$subj_dir")" != "utils" ]; then
    subject_id=$(basename "$subj_dir")
    count=$((count+1))
    printf "%3d. %-15s " "$count" "$subject_id"
    available_subjects+=("$subject_id")
    # Print a new line every 3 subjects
    if [ $((count % 3)) -eq 0 ]; then
      echo ""
    fi
  fi
done
echo ""

# Get subject ID(s) from user
print_message "$YELLOW" "You can select multiple subjects by entering comma-separated numbers or IDs."
print_message "$YELLOW" "Enter 'all' to select all available subjects."
read -p "Enter subject number(s) or ID(s) to process: " subject_choice

# Process selection to get array of subject IDs
selected_subjects=()

if [[ "${subject_choice,,}" == "all" ]]; then
  # Select all available subjects
  selected_subjects=("${available_subjects[@]}")
  print_message "$GREEN" "Selected all ${#selected_subjects[@]} subjects."
else
  # Split the comma-separated input
  IFS=',' read -ra selections <<< "$subject_choice"
  
  for selection in "${selections[@]}"; do
    # Trim whitespace
    selection=$(echo "$selection" | xargs)
    
    if [[ $selection =~ ^[0-9]+$ ]] && [ "$selection" -le "${#available_subjects[@]}" ] && [ "$selection" -gt 0 ]; then
      # Selection is a number, convert to ID
      selected_subjects+=("${available_subjects[$((selection-1))]}")
    else
      # Selection is assumed to be a subject ID, check if valid
      if [ -d "$PROJECT_DIR/$selection" ]; then
        selected_subjects+=("$selection")
      else
        print_message "$RED" "Warning: Subject '$selection' not found, skipping."
      fi
    fi
  done
fi

# Validate that we have at least one subject
if [ ${#selected_subjects[@]} -eq 0 ]; then
  print_message "$RED" "Error: No valid subjects selected. Exiting."
  exit 1
fi

print_message "$GREEN" "Selected subjects: ${selected_subjects[*]}"

# Initialize options
CONVERT_DICOM=false
RUN_RECON=false
PARALLEL_RECON=false
CREATE_M2M=false
QUIET=false

# Ask for DICOM conversion
print_header "DICOM Conversion"
if get_yes_no "Do you want to convert DICOM files to NIfTI?" "y"; then
  CONVERT_DICOM=true
fi

# Ask for recon-all
print_header "FreeSurfer Reconstruction"
if get_yes_no "Do you want to run FreeSurfer recon-all?" "y"; then
  RUN_RECON=true
  
  # Ask for parallel processing
  if get_yes_no "Run FreeSurfer reconstruction in parallel (requires GNU Parallel)?" "n"; then
    PARALLEL_RECON=true
  fi
fi

# Ask for SimNIBS m2m folder creation
print_header "SimNIBS Head Model Creation"
if get_yes_no "Create SimNIBS m2m folder (using charm)?" "y"; then
  CREATE_M2M=true
  print_message "$YELLOW" "Note: charm is automatically parallelized."
fi

# Ask for quiet mode
print_header "Output Settings"
if get_yes_no "Run in quiet mode (suppress output)?" "n"; then
  QUIET=true
fi

# Confirm settings
print_header "Confirmation"
echo "Project Directory: $PROJECT_DIR"
echo "Selected Subjects: ${selected_subjects[*]}"
echo "Convert DICOM: $([ "$CONVERT_DICOM" = true ] && echo "Yes" || echo "No")"
echo "Run recon-all: $([ "$RUN_RECON" = true ] && echo "Yes" || echo "No")"
echo "Parallel recon: $([ "$PARALLEL_RECON" = true ] && echo "Yes" || echo "No")"
echo "Create SimNIBS m2m folder: $([ "$CREATE_M2M" = true ] && echo "Yes" || echo "No")"
echo "Quiet mode: $([ "$QUIET" = true ] && echo "Yes" || echo "No")"

if ! get_yes_no "Are these settings correct?" "y"; then
  print_message "$RED" "Operation cancelled by user."
  exit 0
fi

# Process each selected subject
for SUBJECT_ID in "${selected_subjects[@]}"; do
  SUBJECT_DIR="$PROJECT_DIR/$SUBJECT_ID"
  
  print_header "Processing Subject: $SUBJECT_ID"
  
  # Ensure required directories exist
  mkdir -p "$SUBJECT_DIR/anat/niftis"
  mkdir -p "$SUBJECT_DIR/anat/freesurfer"
  
  # Check for raw DICOM directory if converting
  if $CONVERT_DICOM; then
    RAW_DIR="$SUBJECT_DIR/anat/raw"
    if [ ! -d "$RAW_DIR" ]; then
      print_message "$YELLOW" "Warning: Raw DICOM directory not found at $RAW_DIR"
      print_message "$YELLOW" "Creating directory now."
      mkdir -p "$RAW_DIR"
    fi
  fi
  
  # Build the command for structural.sh - use correct path to script in pre-process folder
  CMD="$script_dir/../pre-process/structural.sh $SUBJECT_DIR"

  # Add DICOM conversion flag
  if $CONVERT_DICOM; then
    CMD="$CMD --convert-dicom"
  fi

  if $RUN_RECON; then
    CMD="$CMD recon-all"
  fi

  if $PARALLEL_RECON; then
    CMD="$CMD --parallel"
  fi

  if $CREATE_M2M; then
    CMD="$CMD --create-m2m"
  fi

  if $QUIET; then
    CMD="$CMD --quiet"
  fi

  # Execute the command
  print_message "$GREEN" "Running command: $CMD"
  eval "$CMD"
  
  print_message "$GREEN" "Completed processing for subject $SUBJECT_ID"
done

# Final message
print_header "Processing Complete"
print_message "$GREEN" "Preprocessing of all selected subjects has been completed." 