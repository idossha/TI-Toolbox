#!/bin/bash

# CLI script for collecting user input to execute structural preprocessing
# This script acts as a front-end for structural.sh

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

# Check if running in direct mode from GUI
if [[ "$1" == "--run-direct" ]]; then
    echo "Running in direct execution mode from GUI"
    
    # Check for required environment variables
    if [[ -z "$SUBJECTS" || -z "$PROJECT_DIR" ]]; then
        echo -e "${RED}Error: Missing required environment variables for direct execution.${RESET}"
        echo "Required: SUBJECTS, PROJECT_DIR"
        exit 1
    fi
    
    # Convert comma-separated subjects to array
    IFS=',' read -r -a selected_subjects <<< "$SUBJECTS"
    
    # Set variables from environment
    CONVERT_DICOM=${CONVERT_DICOM:-false}
    RUN_RECON=${RUN_RECON:-false}
    PARALLEL_RECON=${PARALLEL_RECON:-false}
    CREATE_M2M=${CREATE_M2M:-false}
    CREATE_ATLAS=${CREATE_ATLAS:-false}
    RUN_TISSUE_ANALYSIS=${RUN_TISSUE_ANALYSIS:-false}
    
    # Process each subject
    for subject_id in "${selected_subjects[@]}"; do
        echo -e "${CYAN}Processing subject: $subject_id${RESET}"
        
        # Build the command for structural.sh using absolute Docker path
        cmd=("/development/pre-process/structural.sh")
        
        # Add subject directory as first argument - use the main project directory path
        subject_dir="$PROJECT_DIR/sub-$subject_id"
        cmd+=("$subject_dir")
        
        # Create required directories for both T1w and T2w
        mkdir -p "$PROJECT_DIR/sourcedata/sub-$subject_id/T1w/dicom"
        mkdir -p "$PROJECT_DIR/sourcedata/sub-$subject_id/T2w/dicom"
        mkdir -p "$subject_dir/anat"
        mkdir -p "$PROJECT_DIR/derivatives/freesurfer/sub-$subject_id"
        mkdir -p "$PROJECT_DIR/derivatives/SimNIBS/sub-$subject_id"
        
        # Add optional flags based on environment variables
        if [[ "$RUN_RECON" == "true" ]]; then
            cmd+=("recon-all")
        fi
        
        if [[ "$PARALLEL_RECON" == "true" ]]; then
            cmd+=("--parallel")
        fi
        
        if [[ "$CONVERT_DICOM" == "true" ]]; then
            cmd+=("--convert-dicom")
        fi
        
        if [[ "$CREATE_M2M" == "true" ]]; then
            cmd+=("--create-m2m")
        fi
        
        echo -e "${GREEN}Executing: ${cmd[*]}${RESET}"
        
        # No need to export DICOM_TYPE as it's auto-detected now
        
        "${cmd[@]}"
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}Successfully processed subject: $subject_id${RESET}"
        else
            echo -e "${RED}Error processing subject: $subject_id${RESET}"
        fi
    done
    
    exit 0
fi

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
    echo -e "${BOLD_CYAN}║         TI-Toolbox Pre-process Tool       ║${RESET}"
    echo -e "${BOLD_CYAN}╚═══════════════════════════════════════════╝${RESET}"
    echo -e "${CYAN}Version 2.0 - $(date +%Y)${RESET}"
    echo -e "${CYAN}Prepare subject data for TI-Toolbox analysis${RESET}\n"
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
    echo -e "Convert DICOM files to NIfTI:     ${CYAN}$(if $CONVERT_DICOM; then echo "Yes (auto-detects T1w/T2w)"; else echo "No"; fi)${RESET}"
    echo -e "Run FreeSurfer recon-all:         ${CYAN}$(if $RUN_RECON; then echo "Yes"; else echo "No"; fi)${RESET}"
    echo -e "Run in parallel mode:             ${CYAN}$(if $PARALLEL_RECON; then echo "Yes"; else echo "No"; fi)${RESET}"
    echo -e "Create SimNIBS m2m folder:        ${CYAN}$(if $CREATE_M2M; then echo "Yes"; else echo "No"; fi)${RESET}"
    echo -e "Create atlas segmentation:        ${CYAN}$(if $CREATE_ATLAS; then echo "Yes"; else echo "No"; fi)${RESET}"
    echo -e "Run tissue analysis:              ${CYAN}$(if $RUN_TISSUE_ANALYSIS; then echo "Yes (bone + CSF + skin)"; else echo "No"; fi)${RESET}"
    
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

# First check sourcedata directory for new subjects
for subj_dir in "$PROJECT_DIR/sourcedata/sub-"*; do
  if [ -d "$subj_dir" ]; then
    # Check for both BIDS structure and compressed format
    if [ -d "$subj_dir/T1w" ] || [ -f "$subj_dir"/*.tgz ]; then
      subject_id=$(basename "$subj_dir" | sed 's/^sub-//')
      count=$((count+1))
      printf "%3d. %-15s " "$count" "$subject_id"
      available_subjects+=("$subject_id")
      # Print a new line every 3 subjects
      if [ $((count % 3)) -eq 0 ]; then
        echo ""
      fi
    fi
  fi
done

# If no subjects found in sourcedata, check root directory for legacy structure
if [ ${#available_subjects[@]} -eq 0 ]; then
  for subj_dir in "$PROJECT_DIR/sub-"*; do
    if [ -d "$subj_dir" ]; then
      subject_id=$(basename "$subj_dir" | sed 's/^sub-//')
      count=$((count+1))
      printf "%3d. %-15s " "$count" "$subject_id"
      available_subjects+=("$subject_id")
      # Print a new line every 3 subjects
      if [ $((count % 3)) -eq 0 ]; then
        echo ""
      fi
    fi
  done
fi

echo ""

if [ ${#available_subjects[@]} -eq 0 ]; then
  print_message "$RED" "No subjects found in $PROJECT_DIR/sourcedata/ or $PROJECT_DIR/"
  print_message "$YELLOW" "Please ensure your subjects follow one of these structures:"
  print_message "$YELLOW" "  BIDS: $PROJECT_DIR/sourcedata/sub-{subjectID}/T1w/{any_subdirectory}"
  print_message "$YELLOW" "  Compressed: $PROJECT_DIR/sourcedata/sub-{subjectID}/*.tgz"
  exit 1
fi

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
            if [ -d "$PROJECT_DIR/sub-$selection" ]; then
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
CREATE_ATLAS=false
RUN_TISSUE_ANALYSIS=false

# Ask for DICOM conversion
print_header "DICOM Conversion"
if get_yes_no "Do you want to convert DICOM files to NIfTI (auto-detects T1w/T2w)?" "y"; then
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

# Ask for atlas creation
print_header "Atlas Segmentation"
if get_yes_no "Create atlas segmentation (requires m2m folder)?" "y"; then
    CREATE_ATLAS=true
else
    CREATE_ATLAS=false
fi

# Ask for tissue analysis
print_header "Tissue Analysis"
if get_yes_no "Run tissue analysis (bone, CSF, skin - requires m2m folder)?" "y"; then
    RUN_TISSUE_ANALYSIS=true
fi

# Validate atlas creation requirements
if $CREATE_ATLAS && ! $CREATE_M2M; then
    print_message "$YELLOW" "Atlas creation requires m2m folders. Checking if they exist for selected subjects..."
    missing_m2m_subjects=()
    for SUBJECT_ID in "${selected_subjects[@]}"; do
        BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"
        m2m_dir="$PROJECT_DIR/derivatives/SimNIBS/$BIDS_SUBJECT_ID/m2m_$SUBJECT_ID"
        if [ ! -d "$m2m_dir" ]; then
            missing_m2m_subjects+=("$SUBJECT_ID")
        fi
    done
    
    if [ ${#missing_m2m_subjects[@]} -gt 0 ]; then
        print_message "$RED" "Error: Atlas creation requires m2m folders, but the following subjects don't have them:"
        print_message "$RED" "${missing_m2m_subjects[*]}"
        print_message "$YELLOW" "Please either:"
        print_message "$YELLOW" "1. Enable 'Create SimNIBS m2m folder' option, or"
        print_message "$YELLOW" "2. Run m2m creation for these subjects first, or"
        print_message "$YELLOW" "3. Disable atlas creation"
        exit 1
    else
        print_message "$GREEN" "All selected subjects have existing m2m folders."
    fi
fi

# Validate tissue analysis requirements
if $RUN_TISSUE_ANALYSIS && ! $CREATE_M2M; then
    print_message "$YELLOW" "Tissue analysis requires m2m folders. Checking if they exist for selected subjects..."
    missing_m2m_subjects=()
    for SUBJECT_ID in "${selected_subjects[@]}"; do
        BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"
        m2m_dir="$PROJECT_DIR/derivatives/SimNIBS/$BIDS_SUBJECT_ID/m2m_$SUBJECT_ID"
        labeling_file="$m2m_dir/Labeling.nii.gz"
        if [ ! -f "$labeling_file" ]; then
            missing_m2m_subjects+=("$SUBJECT_ID")
        fi
    done
    
    if [ ${#missing_m2m_subjects[@]} -gt 0 ]; then
        print_message "$RED" "Error: Tissue analysis requires m2m folders with Labeling.nii.gz, but the following subjects don't have them:"
        print_message "$RED" "${missing_m2m_subjects[*]}"
        print_message "$YELLOW" "Please make sure all subjects have m2m folder by running charm first."
        exit 1
    else
        print_message "$GREEN" "All selected subjects have existing m2m folders with Labeling.nii.gz."
    fi
fi

# Show confirmation dialog before proceeding
show_confirmation_dialog

# Check if parallel processing is enabled and we have multiple subjects
if $PARALLEL_RECON && $RUN_RECON && [ ${#selected_subjects[@]} -gt 1 ]; then
    print_header "Processing All Subjects in Parallel"
    
    # Create required directories for all subjects
    for SUBJECT_ID in "${selected_subjects[@]}"; do
        BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"
        mkdir -p "$PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T1w/dicom"
        mkdir -p "$PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T2w/dicom"
        mkdir -p "$PROJECT_DIR/$BIDS_SUBJECT_ID/anat"
        mkdir -p "$PROJECT_DIR/derivatives/freesurfer/$BIDS_SUBJECT_ID"
        mkdir -p "$PROJECT_DIR/derivatives/SimNIBS/$BIDS_SUBJECT_ID"
        
        if $CONVERT_DICOM; then
            print_message "$YELLOW" "Please place T1w DICOM files in: $PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T1w/dicom"
            print_message "$YELLOW" "Please place T2w DICOM files in: $PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T2w/dicom (optional)"
        fi
    done
    
    if $CONVERT_DICOM; then
        print_message "$CYAN" "The script will automatically detect and process available data types."
    fi
    
    # Build the command for structural.sh with all subjects
    CMD="$script_dir/../pre-process/structural.sh"
    
    # Add all subject directories
    for SUBJECT_ID in "${selected_subjects[@]}"; do
        BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"
        SUBJECT_DIR="$PROJECT_DIR/$BIDS_SUBJECT_ID"
        CMD="$CMD $SUBJECT_DIR"
    done
    
    # Add flags
    if $RUN_RECON; then
        CMD="$CMD recon-all"
    fi
    
    if $PARALLEL_RECON; then
        CMD="$CMD --parallel"
    fi
    
    if $CONVERT_DICOM; then
        CMD="$CMD --convert-dicom"
    fi
    
    if $CREATE_M2M; then
        CMD="$CMD --create-m2m"
    fi
    
    # Execute the command once for all subjects
    print_message "$GREEN" "Running parallel command: $CMD"
    eval "$CMD"
    
    # Store result for later atlas processing
    PARALLEL_RESULT=$?
    
else
    # Process each selected subject sequentially
    for SUBJECT_ID in "${selected_subjects[@]}"; do
        BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"
        SUBJECT_DIR="$PROJECT_DIR/$BIDS_SUBJECT_ID"
        
        print_header "Processing Subject: $SUBJECT_ID"
        
        # Create required directories
        mkdir -p "$PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T1w/dicom"
        mkdir -p "$PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T2w/dicom"
        mkdir -p "$PROJECT_DIR/$BIDS_SUBJECT_ID/anat"
        mkdir -p "$PROJECT_DIR/derivatives/freesurfer/$BIDS_SUBJECT_ID"
        mkdir -p "$PROJECT_DIR/derivatives/SimNIBS/$BIDS_SUBJECT_ID"
        
        if $CONVERT_DICOM; then
            print_message "$YELLOW" "Please place T1w DICOM files in: $PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T1w/dicom"
            print_message "$YELLOW" "Please place T2w DICOM files in: $PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T2w/dicom (optional)"
            print_message "$CYAN" "The script will automatically detect and process available data types."
        fi
        
        # Build the command for structural.sh
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
        
        # Execute the command
        print_message "$GREEN" "Running command: $CMD"
        eval "$CMD"
    
        # If atlas creation is requested, run all three atlases
        if $CREATE_ATLAS; then
            m2m_folder="$PROJECT_DIR/derivatives/SimNIBS/$BIDS_SUBJECT_ID/m2m_$SUBJECT_ID"
            if [ -d "$m2m_folder" ]; then
                output_dir="$m2m_folder/segmentation"
                mkdir -p "$output_dir"
                
                # Check if output_dir is actually a directory and not a file
                if [ -e "$output_dir" ] && [ ! -d "$output_dir" ]; then
                    print_message "$RED" "[Atlas] $SUBJECT_ID: Error - segmentation path exists but is not a directory: $output_dir"
                else
                    for atlas in a2009s DK40 HCP_MMP1; do
                        # Check for potential file conflicts before running
                        lh_file="$output_dir/lh.${SUBJECT_ID}_${atlas}.annot"
                        rh_file="$output_dir/rh.${SUBJECT_ID}_${atlas}.annot"
                        
                        # Check if any expected file exists as a directory (conflict)
                        conflict_found=false
                        if [ -e "$lh_file" ] && [ -d "$lh_file" ]; then
                            print_message "$RED" "[Atlas] $SUBJECT_ID: Error - expected file path is a directory: $lh_file"
                            conflict_found=true
                        fi
                        if [ -e "$rh_file" ] && [ -d "$rh_file" ]; then
                            print_message "$RED" "[Atlas] $SUBJECT_ID: Error - expected file path is a directory: $rh_file"
                            conflict_found=true
                        fi
                        
                        if [ "$conflict_found" = true ]; then
                            continue
                        fi
                        
                        print_message "$YELLOW" "[Atlas] $SUBJECT_ID: Running subject_atlas -m $m2m_folder -a $atlas -o $output_dir"
                        subject_atlas -m "$m2m_folder" -a "$atlas" -o "$output_dir"
                        if [ $? -eq 0 ]; then
                            # Verify that the expected .annot files were actually created
                            created_files=""
                            if [ -f "$lh_file" ]; then
                                created_files="lh.${SUBJECT_ID}_${atlas}.annot"
                            fi
                            if [ -f "$rh_file" ]; then
                                if [ -n "$created_files" ]; then
                                    created_files="$created_files, rh.${SUBJECT_ID}_${atlas}.annot"
                                else
                                    created_files="rh.${SUBJECT_ID}_${atlas}.annot"
                                fi
                            fi
                            
                            if [ -f "$lh_file" ] && [ -f "$rh_file" ]; then
                                print_message "$GREEN" "[Atlas] $SUBJECT_ID: Atlas $atlas segmentation complete. Created: $created_files"
                            else
                                print_message "$YELLOW" "[Atlas] $SUBJECT_ID: Atlas $atlas segmentation completed but some files missing. Created: $created_files"
                            fi
                        else
                            print_message "$RED" "[Atlas] $SUBJECT_ID: Atlas $atlas segmentation failed."
                        fi
                    done
                fi
            else
                print_message "$RED" "[Atlas] $SUBJECT_ID: m2m folder not found, skipping atlas segmentation."
            fi
        fi
        
        print_message "$GREEN" "Completed processing for subject $SUBJECT_ID"
    done
fi

# Post-processing: Tissue analysis, atlas creation and report generation for all subjects
for SUBJECT_ID in "${selected_subjects[@]}"; do
    BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"
    
    # Run tissue analysis if requested
    if $RUN_TISSUE_ANALYSIS; then
        print_message "$CYAN" "[Tissue Analysis] $SUBJECT_ID: Starting tissue analysis..."
        
        # Check if m2m folder and Labeling.nii.gz exist
        m2m_folder="$PROJECT_DIR/derivatives/SimNIBS/$BIDS_SUBJECT_ID/m2m_$SUBJECT_ID"
        labeling_file="$m2m_folder/Labeling.nii.gz"
        
        if [ -f "$labeling_file" ]; then
            # Set up tissue analysis output directory
            tissue_output_dir="$PROJECT_DIR/derivatives/ti-toolbox/tissue_analysis/$BIDS_SUBJECT_ID"
            mkdir -p "$tissue_output_dir"
            
            # Run the tissue analyzer script
            tissue_analyzer_script="$script_dir/../pre-process/tissue-analyzer.sh"
            
            if [ -f "$tissue_analyzer_script" ]; then
                print_message "$YELLOW" "[Tissue Analysis] $SUBJECT_ID: Running tissue analyzer on $labeling_file"
                
                # Execute tissue analyzer
                if bash "$tissue_analyzer_script" "$labeling_file" -o "$tissue_output_dir"; then
                    print_message "$GREEN" "[Tissue Analysis] $SUBJECT_ID: Tissue analysis completed successfully!"
                    print_message "$CYAN" "[Tissue Analysis] $SUBJECT_ID: Results saved to: $tissue_output_dir"
                    
                    # Show summary of generated files
                    if [ -d "$tissue_output_dir" ]; then
                        bone_count=$(find "$tissue_output_dir/bone_analysis" -name "*.png" 2>/dev/null | wc -l)
                        csf_count=$(find "$tissue_output_dir/csf_analysis" -name "*.png" 2>/dev/null | wc -l)
                        skin_count=$(find "$tissue_output_dir/skin_analysis" -name "*.png" 2>/dev/null | wc -l)
                        print_message "$CYAN" "[Tissue Analysis] $SUBJECT_ID: Generated $bone_count bone, $csf_count CSF, and $skin_count skin analysis visualizations"
                    fi
                else
                    print_message "$RED" "[Tissue Analysis] $SUBJECT_ID: Tissue analysis failed!"
                fi
            else
                print_message "$RED" "[Tissue Analysis] $SUBJECT_ID: tissue-analyzer.sh not found at $tissue_analyzer_script"
            fi
        else
            print_message "$YELLOW" "[Tissue Analysis] $SUBJECT_ID: Labeling.nii.gz not found in m2m folder, skipping tissue analysis"
            print_message "$YELLOW" "[Tissue Analysis] $SUBJECT_ID: Expected location: $labeling_file"
        fi
    fi
    
    # Generate preprocessing report automatically
    print_message "$CYAN" "[Report] $SUBJECT_ID: Generating preprocessing report..."
    
    # Try to generate report using Python directly
    if command -v simnibs_python >/dev/null 2>&1; then
        # Try to generate report using the report generator
        simnibs_python -c "
import sys
import os
sys.path.insert(0, '$script_dir/../tools')
try:
    from report_util import create_preprocessing_report
    report_path = create_preprocessing_report('$PROJECT_DIR', '$SUBJECT_ID')
    print(f'Report generated: {os.path.basename(report_path)}')
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
" 2>/dev/null
        
        if [ $? -eq 0 ]; then
            print_message "$GREEN" "[Report] $SUBJECT_ID: Preprocessing report generated successfully."
        else
            print_message "$YELLOW" "[Report] $SUBJECT_ID: Could not generate preprocessing report."
        fi
    else
        print_message "$YELLOW" "[Report] $SUBJECT_ID: Python not available, skipping report generation."
    fi
done

# Final message
print_header "Processing Complete"
print_message "$GREEN" "Preprocessing of all selected subjects has been completed."

# Summary of generated reports
reports_dir="$PROJECT_DIR/derivatives/ti-toolbox/reports"
if [ -d "$reports_dir" ]; then
    report_count=$(find "$reports_dir" -name "*pre_processing_report*.html" 2>/dev/null | wc -l)
    if [ "$report_count" -gt 0 ]; then
        print_message "$CYAN" "📊 Generated $report_count preprocessing report(s)"
        print_message "$CYAN" "📁 Reports location: $reports_dir/sub-{subjectID}/"
        print_message "$CYAN" "💡 Open the HTML files in your web browser to view detailed preprocessing reports."
    fi
fi 
