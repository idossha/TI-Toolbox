#!/bin/bash
#
# This script creates head model directories for subjects in a project,
# processing subjects either in serial (default) or in parallel (if --parallel is given).
#
# Additionally, it now supports a --recon-only option to run just the FreeSurfer recon-all
# function (which requires that subject-specific T1 images already exist in the anat/niftis/ folder)
# without performing DICOM conversion or head model generation.
#
# Usage:
#   ./structural.sh <subject_dir> [recon-all] [--recon-only] [--parallel] [--quiet] [--convert-dicom] [--create-m2m]
#
#   <subject_dir>    : The subject directory (e.g., /mnt/BIDS_test/101)
#   recon-all        : Optional; if provided (and not in --recon-only mode), FreeSurfer recon-all is run after head model creation.
#   --recon-only     : Optional; if provided, only recon-all is run (all other processing is skipped).
#   --parallel       : Optional; if provided, subjects are processed in parallel (only for recon-all).
#   --quiet          : Optional; if provided, output is suppressed.
#   --convert-dicom  : Optional; if provided, DICOM files will be converted to NIfTI.
#   --create-m2m     : Optional; if provided, SimNIBS m2m folder will be created.
#

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/../utils/bash_logging.sh"

# Default values for optional flags
RUN_RECON=false
RECON_ONLY=false
PARALLEL=false
QUIET=false
CONVERT_DICOM=false
CREATE_M2M=false
SUBJECT_DIR=""

# Loop over all arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --parallel)
      PARALLEL=true
      shift
      ;;
    --quiet)
      QUIET=true
      shift
      ;;
    --recon-only)
      RECON_ONLY=true
      shift
      ;;
    --convert-dicom)
      CONVERT_DICOM=true
      shift
      ;;
    --create-m2m)
      CREATE_M2M=true
      shift
      ;;
    recon-all)
      RUN_RECON=true
      shift
      ;;
    *)
      # Assume first unknown argument is the SUBJECT_DIR
      if [[ -z "$SUBJECT_DIR" ]]; then
        SUBJECT_DIR="$1"
      else
        echo "Unknown argument: $1"
        echo "Usage: $0 <subject_dir> [recon-all] [--recon-only] [--parallel] [--quiet] [--convert-dicom] [--create-m2m]"
        exit 1
      fi
      shift
      ;;
  esac
done

# Validate subject directory
if [[ -z "$SUBJECT_DIR" ]]; then
  echo "Error: <subject_dir> is required."
  echo "Usage: $0 <subject_dir> [recon-all] [--recon-only] [--parallel] [--quiet] [--convert-dicom] [--create-m2m]"
  exit 1
fi

# Get absolute path of subject directory and set up project structure
SUBJECT_DIR="$(realpath "$SUBJECT_DIR")"
PROJECT_NAME=$(basename "$(dirname "$SUBJECT_DIR")")
PROJECT_DIR="/mnt/${PROJECT_NAME}"
DERIVATIVES_DIR="${PROJECT_DIR}/derivatives"
SUBJECT_ID=$(basename "$SUBJECT_DIR" | sed 's/^sub-//')  # Remove sub- prefix if it exists
BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"

# Create logs directory in project derivatives under subject folder
logs_dir="${DERIVATIVES_DIR}/logs/${BIDS_SUBJECT_ID}"
mkdir -p "$logs_dir"
echo "Logs directory: $logs_dir"

# Now that we have the correct paths, set up logging
set_logger_name "pre-process"
timestamp=$(date +"%Y%m%d_%H%M%S")
set_log_file "${logs_dir}/pre-process_${timestamp}.log"

# Configure external loggers for FreeSurfer and SimNIBS
configure_external_loggers '["freesurfer", "simnibs", "charm"]'

# Function to run command with proper error handling
run_command() {
    local cmd="$1"
    local error_msg="$2"
    
    # Run cmd, capture both stdout and stderr,
    # append everything to the log file, and still show on console.
    if ! eval "$cmd" 2>&1 | tee -a "$LOG_FILE"; then
        # tee will forward stderr, so logger.error will also record the final error
        log_error "$error_msg"
        return 1
    fi
    return 0
}

###############################################################################
#                      PARSE ARGUMENTS AND OPTIONS
###############################################################################

# Create subject directory if it doesn't exist
if [[ ! -d "$SUBJECT_DIR" ]]; then
  log_info "Subject directory $SUBJECT_DIR does not exist. Creating it..."
  mkdir -p "$SUBJECT_DIR"
  if [[ ! -d "$SUBJECT_DIR" ]]; then
    log_error "Failed to create subject directory $SUBJECT_DIR"
    exit 1
  fi
fi

# If --quiet is set, redirect all output (stdout and stderr) to /dev/null
if $QUIET; then
  exec &>/dev/null
fi

###############################################################################
#                   RECON-ONLY MODE: JUST RUN recon-all
###############################################################################
if $RECON_ONLY; then
  log_info "Running in recon-all only mode (skipping DICOM conversion and head model creation)."

  if ! command -v recon-all &>/dev/null; then
    log_error "recon-all (FreeSurfer) is not installed."
    exit 1
  fi

  # Define directories used for recon-all only
  NIFTI_DIR="${SUBJECT_DIR}/anat/niftis"
  FS_RECON_DIR="${SUBJECT_DIR}/anat/freesurfer"   # Directory for FreeSurfer output

  # Ensure the necessary directories exist
  mkdir -p "$NIFTI_DIR" "$FS_RECON_DIR"

  run_recon_only() {
    local subject="$1"
    local nifti_dir="$2"
    local fs_recon_dir="$3"
    
    T1_file="${nifti_dir}/T1.nii"
    if [ ! -f "$T1_file" ]; then
      # Try gzipped version if regular doesn't exist
      T1_file="${nifti_dir}/T1.nii.gz"
      if [ ! -f "$T1_file" ]; then
        log_error "T1.nii or T1.nii.gz not found in ${nifti_dir}, skipping recon-all."
        return
      fi
    fi
    
    log_info "Running FreeSurfer recon-all for subject: $subject"
    if ! run_command "recon-all -subject '$subject' -i '$T1_file' -all -sd '$fs_recon_dir'" "FreeSurfer recon-all failed for subject: $subject"; then
      return 1
    fi
    log_info "Finished FreeSurfer recon-all for subject: $subject"
  }

  if ! $PARALLEL; then
    log_info "Running recon-all in SERIAL mode."
    run_recon_only "$SUBJECT_ID" "$NIFTI_DIR" "$FS_RECON_DIR"
  else
    log_info "Running recon-all in PARALLEL mode."
    if ! command -v parallel &>/dev/null; then
      log_error "GNU Parallel is not installed, but --parallel was requested."
      exit 1
    fi
    
    export -f run_recon_only
    export SUBJECT_ID NIFTI_DIR FS_RECON_DIR
    
    echo "$SUBJECT_ID" | parallel \
      --line-buffer \
      --tagstring '[{}] ' \
      --progress \
      --eta \
      --halt now,fail=1 \
      run_recon_only {} "$NIFTI_DIR" "$FS_RECON_DIR"
  fi

  log_info "Recon-all only mode completed."
  exit 0
fi

###############################################################################
#                 CHECK REQUIRED COMMANDS AND DIRECTORIES
###############################################################################

if $CONVERT_DICOM; then
  if ! command -v dcm2niix &>/dev/null; then
    log_error "dcm2niix is not installed."
    exit 1
  fi
fi

if $CREATE_M2M; then
  if ! command -v charm &>/dev/null; then
    log_error "charm (SimNIBS) is not installed."
    exit 1
  fi
fi

if $RUN_RECON; then
  if ! command -v recon-all &>/dev/null; then
    log_error "recon-all (FreeSurfer) is not installed."
    exit 1
  fi
fi

if $PARALLEL; then
  if ! command -v parallel &>/dev/null; then
    log_error "GNU Parallel is not installed, but --parallel was requested."
    exit 1
  fi
fi

###############################################################################
#                     DEFINE DIRECTORIES AND ENVIRONMENT
###############################################################################

# Define BIDS directory structure
SOURCEDATA_DIR="${PROJECT_DIR}/sourcedata/${BIDS_SUBJECT_ID}"
BIDS_ANAT_DIR="${PROJECT_DIR}/${BIDS_SUBJECT_ID}/anat"
FREESURFER_DIR="${DERIVATIVES_DIR}/freesurfer/${BIDS_SUBJECT_ID}"
SIMNIBS_DIR="${DERIVATIVES_DIR}/SimNIBS/${BIDS_SUBJECT_ID}"

# Create required directories
mkdir -p "${SOURCEDATA_DIR}/T1w"
mkdir -p "${SOURCEDATA_DIR}/T2w"
mkdir -p "$BIDS_ANAT_DIR"
mkdir -p "$FREESURFER_DIR"
mkdir -p "$SIMNIBS_DIR"

###############################################################################
#                         PROCESS SUBJECT
###############################################################################

log_info "Processing subject: $SUBJECT_ID"

###############################################################################
#              DICOM TO NIFTI CONVERSION (IF REQUESTED)
###############################################################################

if $CONVERT_DICOM; then
    log_info "Auto-detecting available DICOM data types..."
    
    # Function to handle compressed DICOM files
    handle_compressed_dicom() {
        local source_dir="$1"
        local target_dir="$2"
        local scan_type="$3"
        
        # Look for .tgz files in the source directory
        for tgz_file in "$source_dir"/*.tgz; do
            if [ -f "$tgz_file" ]; then
                log_info "Found compressed DICOM file: $tgz_file"
                
                # Create a temporary directory for extraction
                local temp_dir=$(mktemp -d)
                
                # Extract the .tgz file
                log_info "Extracting $tgz_file to temporary directory..."
                tar -xzf "$tgz_file" -C "$temp_dir"
                
                # Find all DICOM files in the extracted directory
                local dicom_files=$(find "$temp_dir" -type f -name "*.dcm" -o -name "*.IMA" -o -name "*.dicom")
                
                if [ -n "$dicom_files" ]; then
                    log_info "Found DICOM files in extracted archive"
                    
                    # Create scan type directory if it doesn't exist
                    mkdir -p "$target_dir"
                    
                    # Move DICOM files to the target directory
                    log_info "Moving DICOM files to $target_dir"
                    find "$temp_dir" -type f \( -name "*.dcm" -o -name "*.IMA" -o -name "*.dicom" \) -exec mv {} "$target_dir" \;
                    
                    # Clean up temporary directory
                    rm -rf "$temp_dir"
                else
                    log_warning "Could not find DICOM files in extracted archive"
                    rm -rf "$temp_dir"
                fi
            fi
        done
    }
    
    # Function to find and process DICOM files in a directory
    process_dicom_directory() {
        local source_dir="$1"
        local target_dir="$2"
        
        if [ -d "$source_dir" ] && [ "$(ls -A "$source_dir")" ]; then
            log_info "Processing DICOM files in $source_dir..."
            # First convert in place
            dcm2niix -z y -o "$target_dir" "$source_dir"
            
            # Process each pair of files
            for json_file in "$target_dir"/*.json; do
                if [ -f "$json_file" ]; then
                    # Get the corresponding nii.gz file
                    nii_file="${json_file%.json}.nii.gz"
                    if [ -f "$nii_file" ]; then
                        # Extract SeriesDescription from JSON
                        series_desc=$(grep -o '"SeriesDescription": *"[^"]*"' "$json_file" | cut -d'"' -f4)
                        if [ -n "$series_desc" ]; then
                            # Create new filenames based on SeriesDescription
                            new_json="${BIDS_ANAT_DIR}/${series_desc}.json"
                            new_nii="${BIDS_ANAT_DIR}/${series_desc}.nii.gz"
                            # Move and rename the files
                            mv "$json_file" "$new_json"
                            mv "$nii_file" "$new_nii"
                            log_info "Renamed files to: $series_desc"
                        else
                            # If no SeriesDescription found, move with original names
                            mv "$json_file" "${BIDS_ANAT_DIR}/"
                            mv "$nii_file" "${BIDS_ANAT_DIR}/"
                        fi
                    fi
                fi
            done
        fi
    }
    
    # Create required directories for both T1w and T2w
    mkdir -p "${SOURCEDATA_DIR}/T1w/dicom"
    mkdir -p "${SOURCEDATA_DIR}/T2w/dicom"
    mkdir -p "$BIDS_ANAT_DIR"
    mkdir -p "$FREESURFER_DIR"
    mkdir -p "$SIMNIBS_DIR"
    
    # Handle compressed DICOM files if they exist
    handle_compressed_dicom "${SOURCEDATA_DIR}/T1w" "${SOURCEDATA_DIR}/T1w/dicom" "T1w"
    handle_compressed_dicom "${SOURCEDATA_DIR}/T2w" "${SOURCEDATA_DIR}/T2w/dicom" "T2w"
    
    # Process T1w directory
    T1_DICOM_DIR="${SOURCEDATA_DIR}/T1w/dicom"
    T2_DICOM_DIR="${SOURCEDATA_DIR}/T2w/dicom"
    
    if [ ! -d "$T1_DICOM_DIR" ] && [ ! -d "$T2_DICOM_DIR" ]; then
        log_warning "No DICOM directories found in T1w or T2w. Skipping DICOM conversion."
    else
        log_info "Converting DICOM files to NIfTI..."
        
        # Process T1w directory if it exists and has files
        if [ -d "$T1_DICOM_DIR" ] && [ "$(ls -A "$T1_DICOM_DIR")" ]; then
            log_info "Found T1w DICOM data, processing..."
            process_dicom_directory "$T1_DICOM_DIR" "$T1_DICOM_DIR"
        fi
        
        # Process T2w directory if it exists and has files
        if [ -d "$T2_DICOM_DIR" ] && [ "$(ls -A "$T2_DICOM_DIR")" ]; then
            log_info "Found T2w DICOM data, processing..."
            process_dicom_directory "$T2_DICOM_DIR" "$T2_DICOM_DIR"
        fi
    fi
fi

# Verify that NIfTI files were created and moved successfully
if [ ! -d "$BIDS_ANAT_DIR" ] || [ -z "$(ls -A "$BIDS_ANAT_DIR")" ]; then
    log_error "No NIfTI files found in $BIDS_ANAT_DIR"
    log_error "Please ensure anatomical MRI data is available."
    exit 1
fi

###############################################################################
#                         PREPARE FOR HEAD MODEL
###############################################################################

# Find T1 and T2 images - look for any .nii or .nii.gz files
T1_file=""
T2_file=""

# First try to find files with T1/T1w in the name
for t1_candidate in "$BIDS_ANAT_DIR"/*T1*.nii* "$BIDS_ANAT_DIR"/*t1*.nii*; do
    if [ -f "$t1_candidate" ]; then
        T1_file="$t1_candidate"
        log_info "Found T1 image: $T1_file"
        break
    fi
done

# If no T1 found, take the first NIfTI file as T1
if [ -z "$T1_file" ]; then
    for nii_file in "$BIDS_ANAT_DIR"/*.nii*; do
        if [ -f "$nii_file" ]; then
            T1_file="$nii_file"
            log_info "Using $T1_file as T1 image"
            break
        fi
    done
fi

# Look for T2 images
for t2_candidate in "$BIDS_ANAT_DIR"/*T2*.nii* "$BIDS_ANAT_DIR"/*t2*.nii*; do
    if [ -f "$t2_candidate" ]; then
        T2_file="$t2_candidate"
        log_info "Found T2 image: $T2_file"
        break
    fi
done

# Convert to absolute paths if files were found
if [ -f "$T1_file" ]; then
    T1_file=$(realpath "$T1_file")
else
    log_error "No NIfTI files found in $BIDS_ANAT_DIR"
    log_error "Please ensure anatomical MRI data is available."
    exit 1
fi

if [ -f "$T2_file" ]; then
    T2_file=$(realpath "$T2_file")
    log_info "T2 image found: $T2_file"
else
    log_info "No T2 image found. Proceeding with T1 only."
    T2_file=""
fi

###############################################################################
#                         CREATE HEAD MODEL
###############################################################################

if $CREATE_M2M; then
    # --- Run the charm function to create head model ---
    log_info "Creating head model with SimNIBS charm..."
    
    # Check if m2m directory already exists
    m2m_dir="$SIMNIBS_DIR/m2m_${SUBJECT_ID}"
    forcerun=""
    if [ -d "$m2m_dir" ] && [ "$(ls -A "$m2m_dir" 2>/dev/null)" ]; then
        log_warning "Head model directory already contains files. Using --forcerun option."
        forcerun="--forcerun"
    fi
    
    # Run charm
    if [ -n "$T2_file" ]; then
        log_info "Running charm with T1 and T2 images..."
        ( cd "$SIMNIBS_DIR" || exit 1
          if ! run_command "charm $forcerun '$SUBJECT_ID' '$T1_file' '$T2_file'" "SimNIBS charm failed with T1 and T2 images"; then
              exit 1
          fi
        )
    else
        log_info "Running charm with T1 image only..."
        ( cd "$SIMNIBS_DIR" || exit 1
          if ! run_command "charm $forcerun '$SUBJECT_ID' '$T1_file'" "SimNIBS charm failed with T1 image only"; then
              exit 1
          fi
        )
    fi
else
    log_info "Skipping head model creation (not requested)."
fi

# --- Optionally run FreeSurfer recon-all ---
if $RUN_RECON; then
    log_info "Running FreeSurfer recon-all..."
    if ! run_command "recon-all -subject '$SUBJECT_ID' -i '$T1_file' -all -sd '$FREESURFER_DIR'" "FreeSurfer recon-all failed"; then
        exit 1
    fi
fi

log_info "Finished processing subject: $SUBJECT_ID" 