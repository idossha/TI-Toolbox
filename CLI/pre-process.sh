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
CYAN='\033[0;36m'
BOLD_CYAN='\033[1;36m'
RESET='\033[0m' # No Color
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

# Function to show welcome message
show_welcome_message() {
    clear  # Clear the screen before starting
    echo -e "${BOLD_CYAN}╔═══════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD_CYAN}║         TI-CSC Pre-process Tool          ║${RESET}"
    echo -e "${BOLD_CYAN}╚═══════════════════════════════════════════╝${RESET}"
    echo -e "${CYAN}Version 2.0 - $(date +%Y)${RESET}"
    echo -e "${CYAN}Prepare subject data for TI-CSC analysis${RESET}\n"
}

# Function to show confirmation dialog
show_confirmation_dialog() {
    echo -e "\n${BOLD_CYAN}Configuration Summary${RESET}"
    echo -e "----------------------------------------"
    echo -e "${BOLD}Selected Parameters:${RESET}"
    
    # Subject Information
    echo -e "\n${BOLD_CYAN}Subject Information:${RESET}"
    echo -e "Selected Subjects (${#selected_subjects[@]}): ${CYAN}${selected_subjects[*]}${RESET}"
    
    # Processing Options
    echo -e "\n${BOLD_CYAN}Processing Options:${RESET}"
    echo -e "Convert DICOM files to NIfTI:     ${CYAN}$(if $CONVERT_DICOM; then echo "Yes"; else echo "No"; fi)${RESET}"
    echo -e "Run FreeSurfer recon-all:         ${CYAN}$(if $RUN_RECON; then echo "Yes"; else echo "No"; fi)${RESET}"
    echo -e "Run in parallel mode:             ${CYAN}$(if $PARALLEL_RECON; then echo "Yes"; else echo "No"; fi)${RESET}"
    echo -e "Create SimNIBS m2m folder:        ${CYAN}$(if $CREATE_M2M; then echo "Yes"; else echo "No"; fi)${RESET}"
    echo -e "Run in quiet mode:                ${CYAN}$(if $QUIET; then echo "Yes"; else echo "No"; fi)${RESET}"
    
    echo -e "\n${BOLD_YELLOW}Please review the configuration above.${RESET}"
    echo -e "${YELLOW}Do you want to proceed with these settings? (y/n)${RESET}"
    read -p " " confirm
    
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        print_message "$YELLOW" "Pre-processing cancelled by user."
        exit 0
    fi
}

# Main script execution starts here
show_welcome_message

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
print_header "SimNIBS Head Model"
if get_yes_no "Create SimNIBS m2m folder?" "y"; then
    CREATE_M2M=true
fi

# Ask for quiet mode
print_header "Output Mode"
if get_yes_no "Run in quiet mode (suppress output)?" "n"; then
    QUIET=true
fi

# Show confirmation dialog before proceeding
show_confirmation_dialog

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

  # If m2m was created, run all three atlases automatically
  if $CREATE_M2M; then
    m2m_folder="$SUBJECT_DIR/SimNIBS/m2m_$SUBJECTID"
    if [ -d "$m2m_folder" ]; then
      for atlas in a2009s DK40 HCP_MMP1; do
        output_dir="$m2m_folder/segmentation"
        mkdir -p "$output_dir"
        print_message "$YELLOW" "[Atlas] $SUBJECT_ID: Running subject_atlas -m $m2m_folder -a $atlas -o $output_dir"
        subject_atlas -m "$m2m_folder" -a "$atlas" -o "$output_dir"
        if [ $? -eq 0 ]; then
          print_message "$GREEN" "[Atlas] $SUBJECT_ID: Atlas $atlas segmentation complete."
        else
          print_message "$RED" "[Atlas] $SUBJECT_ID: Atlas $atlas segmentation failed."
        fi
      done
    else
      print_message "$RED" "[Atlas] $SUBJECT_ID: m2m folder not found, skipping atlas segmentation."
    fi
  fi
  
  print_message "$GREEN" "Completed processing for subject $SUBJECT_ID"
done

# Final message
print_header "Processing Complete"
print_message "$GREEN" "Preprocessing of all selected subjects has been completed." 