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

###############################################################################
#                      PARSE ARGUMENTS AND OPTIONS
###############################################################################

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

# Extract subject ID from the subject directory path
SUBJECT_ID=$(basename "$SUBJECT_DIR")

# Validate subject directory
if [[ -z "$SUBJECT_DIR" ]] || [[ ! -d "$SUBJECT_DIR" ]]; then
  echo "Error: <subject_dir> is required and must exist."
  echo "Usage: $0 <subject_dir> [recon-all] [--recon-only] [--parallel] [--quiet] [--convert-dicom] [--create-m2m]"
  exit 1
fi

# If --quiet is set, redirect all output (stdout and stderr) to /dev/null
if $QUIET; then
  exec &>/dev/null
fi

###############################################################################
#                   RECON-ONLY MODE: JUST RUN recon-all
###############################################################################
if $RECON_ONLY; then
  echo "Running in recon-all only mode (skipping DICOM conversion and head model creation)."

  if ! command -v recon-all &>/dev/null; then
    echo "Error: recon-all (FreeSurfer) is not installed." >&2
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
        echo "Error: T1.nii or T1.nii.gz not found in ${nifti_dir}, skipping recon-all."
        return
      fi
    fi
    
    echo "Running FreeSurfer recon-all for subject: $subject"
    recon-all -subject "$subject" -i "$T1_file" -all -sd "$fs_recon_dir"
    echo "Finished FreeSurfer recon-all for subject: $subject"
  }

  if ! $PARALLEL; then
    echo "Running recon-all in SERIAL mode."
    run_recon_only "$SUBJECT_ID" "$NIFTI_DIR" "$FS_RECON_DIR"
  else
    echo "Running recon-all in PARALLEL mode."
    if ! command -v parallel &>/dev/null; then
      echo "Error: GNU Parallel is not installed, but --parallel was requested." >&2
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

  echo "Recon-all only mode completed."
  exit 0
fi

###############################################################################
#                 CHECK REQUIRED COMMANDS AND DIRECTORIES
###############################################################################

if $CONVERT_DICOM; then
  if ! command -v dcm2niix &>/dev/null; then
    echo "Error: dcm2niix is not installed." >&2
    exit 1
  fi
fi

if $CREATE_M2M; then
  if ! command -v charm &>/dev/null; then
    echo "Error: charm (SimNIBS) is not installed." >&2
    exit 1
  fi
fi

if $RUN_RECON; then
  if ! command -v recon-all &>/dev/null; then
    echo "Error: recon-all (FreeSurfer) is not installed." >&2
    exit 1
  fi
fi

if $PARALLEL; then
  if ! command -v parallel &>/dev/null; then
    echo "Error: GNU Parallel is not installed, but --parallel was requested." >&2
    exit 1
  fi
fi

###############################################################################
#                     DEFINE DIRECTORIES AND ENVIRONMENT
###############################################################################

# Adjust directories for BIDS-like structure
SUBJECT_ID=$(basename "$SUBJECT_DIR" | sed 's/^sub-//')  # Remove sub- prefix if it exists
BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"

# Define BIDS directory structure
PROJECT_DIR=$(dirname "$SUBJECT_DIR")  # Get project directory from subject directory
SOURCEDATA_DIR="${PROJECT_DIR}/sourcedata/${BIDS_SUBJECT_ID}"
DERIVATIVES_DIR="${PROJECT_DIR}/derivatives"
BIDS_ANAT_DIR="${PROJECT_DIR}/${BIDS_SUBJECT_ID}/anat"
FREESURFER_DIR="${DERIVATIVES_DIR}/freesurfer/${BIDS_SUBJECT_ID}"
SIMNIBS_DIR="${DERIVATIVES_DIR}/SimNIBS/${BIDS_SUBJECT_ID}"

# Create required directories
mkdir -p "${SOURCEDATA_DIR}/T1w/dicom"
mkdir -p "${SOURCEDATA_DIR}/T2w/dicom"
mkdir -p "$BIDS_ANAT_DIR"
mkdir -p "$FREESURFER_DIR"
mkdir -p "$SIMNIBS_DIR"

###############################################################################
#                         PROCESS SUBJECT
###############################################################################

echo "Processing subject: $SUBJECT_ID"

###############################################################################
#              DICOM TO NIFTI CONVERSION (IF REQUESTED)
###############################################################################

if $CONVERT_DICOM; then
    # Check if source DICOM directories exist
    T1_DICOM_DIR="${SOURCEDATA_DIR}/T1w/dicom"
    T2_DICOM_DIR="${SOURCEDATA_DIR}/T2w/dicom"
    
    if [ ! -d "$T1_DICOM_DIR" ] && [ ! -d "$T2_DICOM_DIR" ]; then
        echo "Warning: Neither T1w nor T2w DICOM directories exist. Skipping DICOM conversion."
    else
        echo "Converting DICOM files to NIfTI..."
        
        # Process T1w directory
        if [ -d "$T1_DICOM_DIR" ] && [ "$(ls -A "$T1_DICOM_DIR")" ]; then
            echo "Processing T1w DICOM files..."
            # First convert in place
            dcm2niix -z y -o "$T1_DICOM_DIR" "$T1_DICOM_DIR"
            
            # Move all .nii.gz and .json files to the anat directory
            for file in "$T1_DICOM_DIR"/*.nii.gz "$T1_DICOM_DIR"/*.json; do
                if [ -f "$file" ]; then
                    # Get the base filename
                    filename=$(basename "$file")
                    # Rename to BIDS format if not already in it
                    if [[ ! "$filename" =~ ^sub-* ]]; then
                        new_filename="${BIDS_SUBJECT_ID}_T1w${filename#*_}"
                    else
                        new_filename="$filename"
                    fi
                    # Move and rename the file
                    mv "$file" "${BIDS_ANAT_DIR}/${new_filename}"
                fi
            done
        fi
        
        # Process T2w directory
        if [ -d "$T2_DICOM_DIR" ] && [ "$(ls -A "$T2_DICOM_DIR")" ]; then
            echo "Processing T2w DICOM files..."
            # First convert in place
            dcm2niix -z y -o "$T2_DICOM_DIR" "$T2_DICOM_DIR"
            
            # Move all .nii.gz and .json files to the anat directory
            for file in "$T2_DICOM_DIR"/*.nii.gz "$T2_DICOM_DIR"/*.json; do
                if [ -f "$file" ]; then
                    # Get the base filename
                    filename=$(basename "$file")
                    # Rename to BIDS format if not already in it
                    if [[ ! "$filename" =~ ^sub-* ]]; then
                        new_filename="${BIDS_SUBJECT_ID}_T2w${filename#*_}"
                    else
                        new_filename="$filename"
                    fi
                    # Move and rename the file
                    mv "$file" "${BIDS_ANAT_DIR}/${new_filename}"
                fi
            done
        fi
    fi
fi

# Verify that NIfTI files were created and moved successfully
if [ ! -d "$BIDS_ANAT_DIR" ] || [ -z "$(ls -A "$BIDS_ANAT_DIR")" ]; then
    echo "Error: No NIfTI files found in $BIDS_ANAT_DIR"
    echo "Please ensure anatomical MRI data is available."
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
        echo "Found T1 image: $T1_file"
        break
    fi
done

# If no T1 found, take the first NIfTI file as T1
if [ -z "$T1_file" ]; then
    for nii_file in "$BIDS_ANAT_DIR"/*.nii*; do
        if [ -f "$nii_file" ]; then
            T1_file="$nii_file"
            echo "Using $T1_file as T1 image"
            break
        fi
    done
fi

# Look for T2 images
for t2_candidate in "$BIDS_ANAT_DIR"/*T2*.nii* "$BIDS_ANAT_DIR"/*t2*.nii*; do
    if [ -f "$t2_candidate" ]; then
        T2_file="$t2_candidate"
        echo "Found T2 image: $T2_file"
        break
    fi
done

# Convert to absolute paths if files were found
if [ -f "$T1_file" ]; then
    T1_file=$(realpath "$T1_file")
else
    echo "Error: No NIfTI files found in $BIDS_ANAT_DIR"
    echo "Please ensure anatomical MRI data is available."
    exit 1
fi

if [ -f "$T2_file" ]; then
    T2_file=$(realpath "$T2_file")
    echo "T2 image found: $T2_file"
else
    echo "No T2 image found. Proceeding with T1 only."
    T2_file=""
fi

###############################################################################
#                         CREATE HEAD MODEL
###############################################################################

if $CREATE_M2M; then
    # --- Run the charm function to create head model ---
    echo "Creating head model with SimNIBS charm..."
    
    # Check if m2m directory already exists
    m2m_dir="$SIMNIBS_DIR/m2m_${SUBJECT_ID}"
    forcerun=""
    if [ -d "$m2m_dir" ] && [ "$(ls -A "$m2m_dir" 2>/dev/null)" ]; then
        echo "Head model directory already contains files. Using --forcerun option."
        forcerun="--forcerun"
    fi
    
    # Run charm
    if [ -n "$T2_file" ]; then
        echo "Running charm with T1 and T2 images..."
        ( cd "$SIMNIBS_DIR" || exit 1
          charm $forcerun "$SUBJECT_ID" "$T1_file" "$T2_file" )
    else
        echo "Running charm with T1 image only..."
        ( cd "$SIMNIBS_DIR" || exit 1
          charm $forcerun "$SUBJECT_ID" "$T1_file" )
    fi
else
    echo "Skipping head model creation (not requested)."
fi

# --- Optionally run FreeSurfer recon-all ---
if $RUN_RECON; then
    echo "Running FreeSurfer recon-all..."
    recon-all -subject "$SUBJECT_ID" -i "$T1_file" -all -sd "$FREESURFER_DIR"
fi

echo "Finished processing subject: $SUBJECT_ID" 