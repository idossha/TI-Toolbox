#!/bin/bash

# subject_atlas.sh - Apply atlas segmentation to selected subjects

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/../utils/bash_logging.sh"

# Initialize logging
set_logger_name "subject_atlas"
set_log_file "${script_dir}/subject_atlas.log"

# Function to validate directory exists
validate_dir() {
  local dir=$1
  if [ ! -d "$dir" ]; then
    log_error "Directory '$dir' does not exist."
    return 1
  fi
  return 0
}

# Detect project directory (like in pre-process.sh)
log_info "Starting Atlas Segmentation Tool"
PROJECT_DIR=""
if [ -d "/mnt" ]; then
  for dir in /mnt/*/; do
    if [ -d "$dir" ]; then
      PROJECT_DIR="${dir%/}"
      break
    fi
  done
else
  for potential_dir in "$script_dir" "$script_dir/.." "$script_dir/../.."; do
    if [ -d "$potential_dir/BIDS_test" ]; then
      PROJECT_DIR="$potential_dir/BIDS_test"
      break
    fi
  done
  if [ -z "$PROJECT_DIR" ] || [ ! -d "$PROJECT_DIR" ]; then
    log_warning "Could not automatically detect project directory."
    read -p "Enter the project directory path (absolute path): " PROJECT_DIR
    if ! validate_dir "$PROJECT_DIR"; then
      log_error "Exiting due to invalid project directory."
      exit 1
    fi
  fi
fi
log_info "Using project directory: $PROJECT_DIR"

# List available subjects
available_subjects=()
log_info "Available Subjects:"
echo "-------------------"
count=0
for subj_dir in "$PROJECT_DIR"/*; do
  if [ -d "$subj_dir" ] && [ "$(basename "$subj_dir")" != "config" ] && [ "$(basename "$subj_dir")" != "utils" ]; then
    subject_id=$(basename "$subj_dir")
    count=$((count+1))
    printf "%3d. %-15s " "$count" "$subject_id"
    available_subjects+=("$subject_id")
    if [ $((count % 3)) -eq 0 ]; then
      echo ""
    fi
  fi
done
echo ""

# Prompt for subject selection
log_info "You can select multiple subjects by entering comma-separated numbers or IDs."
log_info "Enter 'all' to select all available subjects."
read -p "Enter subject number(s) or ID(s) to process: " subject_choice
selected_subjects=()
if [[ "${subject_choice,,}" == "all" ]]; then
  selected_subjects=("${available_subjects[@]}")
  log_info "Selected all ${#selected_subjects[@]} subjects."
else
  IFS=',' read -ra selections <<< "$subject_choice"
  for selection in "${selections[@]}"; do
    selection=$(echo "$selection" | xargs)
    if [[ $selection =~ ^[0-9]+$ ]] && [ "$selection" -le "${#available_subjects[@]}" ] && [ "$selection" -gt 0 ]; then
      selected_subjects+=("${available_subjects[$((selection-1))]}")
    else
      if [ -d "$PROJECT_DIR/$selection" ]; then
        selected_subjects+=("$selection")
      else
        log_warning "Subject '$selection' not found, skipping."
      fi
    fi
  done
fi
if [ ${#selected_subjects[@]} -eq 0 ]; then
  log_error "No valid subjects selected. Exiting."
  exit 1
fi
log_info "Selected subjects: ${selected_subjects[*]}"

# Prompt for atlas selection
log_info "Atlas Selection"
log_info "Available Atlases:"
echo "  1. a2009s"
echo "  2. DK40"
echo "  3. HCP_MMP1"
read -p "Enter atlas name or number: " atlas_choice
case "$atlas_choice" in
  1|a2009s|A2009S) atlas="a2009s" ;;
  2|dk40|DK40) atlas="DK40" ;;
  3|hcp_mmp1|HCP_MMP1|hcp-mmp1) atlas="HCP_MMP1" ;;
  *)
    log_error "Invalid atlas selection. Exiting."
    exit 1
    ;;
esac
log_info "Selected atlas: $atlas"

# Iterate through subjects and run subject_atlas
log_info "Running Atlas Segmentation"
for subject in "${selected_subjects[@]}"; do
  m2m_folder="$PROJECT_DIR/$subject/SimNIBS/m2m_$subject"
  output_dir="$m2m_folder/segmentation"
  mkdir -p "$output_dir"
  if [ ! -d "$m2m_folder" ]; then
    log_error "[SKIP] $subject: m2m folder not found at $m2m_folder"
    continue
  fi
  log_info "Processing $subject with atlas $atlas..."
  subject_atlas -m "$m2m_folder" -a "$atlas" -o "$output_dir"
  if [ $? -eq 0 ]; then
    log_info "[DONE] $subject: Atlas segmentation complete."
  else
    log_error "[FAIL] $subject: Atlas segmentation failed."
  fi
done

log_info "Atlas Segmentation Complete"
log_info "All selected subjects processed." 