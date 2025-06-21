#!/bin/bash
#
# Modular Pre-processing Pipeline Orchestrator
# This script orchestrates DICOM conversion, FreeSurfer recon-all, and SimNIBS m2m creation
# by calling individual specialized scripts.
#
# Usage:
#   ./structural.sh <subject_dir>... [recon-all] [--recon-only] [--parallel] [--quiet] [--convert-dicom] [--create-m2m]
#   ./structural.sh --subjects <subject_id1,subject_id2,...> [options...]
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
SUBJECT_DIRS=()

# Enhanced argument parsing to handle GUI command format
# The GUI sends: script.sh /path/sub-101 /path/sub-102 recon-all --parallel --convert-dicom
# We need to create directories first (like CLI does), then process arguments

echo "DEBUG: Received arguments: $*" >&2

# First pass: Extract subject IDs from paths and create directory structure
temp_subject_ids=()
temp_flags=()

for arg in "$@"; do
  if [[ "$arg" == *"/sub-"* ]]; then
    # Extract subject ID from path like /mnt/data_for_Paper/sub-101
    subject_id=$(basename "$arg" | sed 's/^sub-//')
    temp_subject_ids+=("$subject_id")
    echo "DEBUG: Extracted subject ID: $subject_id from path: $arg" >&2
  else
    temp_flags+=("$arg")
    echo "DEBUG: Identified flag: $arg" >&2
  fi
done

# Create directory structure for each subject (like CLI does)
for subject_id in "${temp_subject_ids[@]}"; do
  # Detect project directory from the first subject path
  if [[ -z "$PROJECT_DIR" ]]; then
    for arg in "$@"; do
      if [[ "$arg" == *"/sub-"* ]]; then
        PROJECT_DIR=$(dirname "$arg")
        echo "DEBUG: Detected project directory: $PROJECT_DIR" >&2
        break
      fi
    done
  fi
  
  BIDS_SUBJECT_ID="sub-${subject_id}"
  SUBJECT_DIR="$PROJECT_DIR/$BIDS_SUBJECT_ID"
  
  # Create directory structure (exactly like CLI does)
  echo "DEBUG: Creating directory structure for subject: $subject_id" >&2
  mkdir -p "$PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T1w/dicom"
  mkdir -p "$PROJECT_DIR/sourcedata/$BIDS_SUBJECT_ID/T2w/dicom"
  mkdir -p "$SUBJECT_DIR/anat"
  mkdir -p "$PROJECT_DIR/derivatives/freesurfer/$BIDS_SUBJECT_ID"
  mkdir -p "$PROJECT_DIR/derivatives/SimNIBS/$BIDS_SUBJECT_ID"
  
  SUBJECT_DIRS+=("$SUBJECT_DIR")
  echo "DEBUG: Created and added subject directory: $SUBJECT_DIR" >&2
done

# Process flags
for flag in "${temp_flags[@]}"; do
  case "$flag" in
    --parallel)
      PARALLEL=true
      echo "DEBUG: Set PARALLEL=true" >&2
      ;;
    --quiet)
      QUIET=true
      echo "DEBUG: Set QUIET=true" >&2
      ;;
    --recon-only)
      RECON_ONLY=true
      echo "DEBUG: Set RECON_ONLY=true" >&2
      ;;
    --convert-dicom)
      CONVERT_DICOM=true
      echo "DEBUG: Set CONVERT_DICOM=true" >&2
      ;;
    --create-m2m)
      CREATE_M2M=true
      echo "DEBUG: Set CREATE_M2M=true" >&2
      ;;
    recon-all)
      RUN_RECON=true
      echo "DEBUG: Set RUN_RECON=true" >&2
      ;;
    *)
      echo "Unknown flag: $flag"
      exit 1
      ;;
  esac
done

echo "DEBUG: Final SUBJECT_DIRS: ${SUBJECT_DIRS[*]}" >&2
echo "DEBUG: RUN_RECON=$RUN_RECON, PARALLEL=$PARALLEL, CONVERT_DICOM=$CONVERT_DICOM" >&2

# Validate subject directories
if [[ ${#SUBJECT_DIRS[@]} -eq 0 ]]; then
  echo "Error: At least one subject directory or subject ID is required."
  echo "Usage: $0 <subject_dir_or_id>... [recon-all] [--recon-only] [--parallel] [--quiet] [--convert-dicom] [--create-m2m]"
  echo "       $0 --subjects <subject_id1,subject_id2,...> [options...]"
  exit 1
fi

# Print processing plan
echo "Processing plan:"
echo "- Subjects to process: ${#SUBJECT_DIRS[@]}"
for i in "${!SUBJECT_DIRS[@]}"; do
    echo "  $((i+1)). ${SUBJECT_DIRS[i]}"
done
echo "- Parallel processing: $PARALLEL"
echo "- Run recon-all: $RUN_RECON"
echo "- Recon-only mode: $RECON_ONLY"
echo "- Convert DICOM: $CONVERT_DICOM"
echo "- Create m2m: $CREATE_M2M"

# Function to process a single subject through all non-recon steps
process_subject_non_recon() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    echo "Processing non-recon steps for subject: $subject_id"
    
    # DICOM conversion
    if $CONVERT_DICOM; then
        echo "  Running DICOM conversion..."
        local dicom_args=("$subject_dir")
        if $QUIET; then
            dicom_args+=("--quiet")
        fi
        
        if ! "$script_dir/dicom2nifti.sh" "${dicom_args[@]}"; then
            echo "  Error: DICOM conversion failed for subject: $subject_id"
            return 1
        fi
        echo "  DICOM conversion completed for subject: $subject_id"
    fi
    
    # SimNIBS m2m creation
    if $CREATE_M2M; then
        echo "  Running SimNIBS charm..."
        local charm_args=("$subject_dir")
        if $QUIET; then
            charm_args+=("--quiet")
        fi
        
        if ! "$script_dir/charm.sh" "${charm_args[@]}"; then
            echo "  Error: SimNIBS charm failed for subject: $subject_id"
            return 1
        fi
        echo "  SimNIBS charm completed for subject: $subject_id"
    fi
    
    echo "Non-recon processing completed for subject: $subject_id"
    return 0
}

# Function to run recon-all for a single subject
run_recon_single() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    echo "Running FreeSurfer recon-all for subject: $subject_id"
    
    local recon_args=("$subject_dir")
    if $QUIET; then
        recon_args+=("--quiet")
    fi
    if $PARALLEL; then
        recon_args+=("--parallel")
    fi
    
    if ! "$script_dir/recon-all.sh" "${recon_args[@]}"; then
        echo "Error: FreeSurfer recon-all failed for subject: $subject_id"
        return 1
    fi
    
    echo "FreeSurfer recon-all completed for subject: $subject_id"
    return 0
}

# Main processing logic
if $PARALLEL && ($RUN_RECON || $RECON_ONLY) && [[ ${#SUBJECT_DIRS[@]} -gt 1 ]]; then
    echo "Starting parallel processing of ${#SUBJECT_DIRS[@]} subject(s) using GNU Parallel..."
    
    # Check for GNU Parallel
    if ! command -v parallel &>/dev/null; then
        echo "Error: GNU Parallel is not installed, but --parallel was requested."
        echo "Please install GNU Parallel: apt-get install parallel"
        exit 1
    fi
    
    # Process non-recon steps first (sequentially to avoid conflicts)
    if ! $RECON_ONLY; then
        echo "Processing non-recon steps sequentially first..."
        for subject_dir in "${SUBJECT_DIRS[@]}"; do
            if ! process_subject_non_recon "$subject_dir"; then
                echo "Error: Failed to pre-process subject: $subject_dir"
                exit 1
            fi
        done
    fi
    
    # Now run recon-all in parallel
    echo "Running FreeSurfer recon-all in parallel for ${#SUBJECT_DIRS[@]} subjects..."
    
    # Use absolute path to recon-all.sh for parallel execution
    recon_script="$(cd "$script_dir" && pwd)/recon-all.sh"
    
    # Build arguments for parallel execution
    parallel_args=()
    if $QUIET; then
        parallel_args+=("--quiet")
    fi
    if $PARALLEL; then
        parallel_args+=("--parallel")
    fi
    
    # Run recon-all in parallel using the script directly
    if ! printf '%s\n' "${SUBJECT_DIRS[@]}" | parallel \
        --line-buffer \
        --tagstring '[{/}] ' \
        --halt now,fail=1 \
        --jobs 0 \
        "$recon_script" {} "${parallel_args[@]}"; then
        echo "Error: Parallel recon-all processing failed"
        exit 1
    fi
    
    echo "Parallel FreeSurfer recon-all completed successfully!"
    
else
    # Sequential processing
    echo "Starting sequential processing of ${#SUBJECT_DIRS[@]} subject(s)..."
    
    for subject_dir in "${SUBJECT_DIRS[@]}"; do
        subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
        echo "Processing subject: $subject_id"
        
        # Handle recon-only mode
        if $RECON_ONLY; then
            if ! run_recon_single "$subject_dir"; then
                echo "Error: Failed to process subject: $subject_dir"
                exit 1
            fi
        else
            # Process non-recon steps first
            if ! process_subject_non_recon "$subject_dir"; then
                echo "Error: Failed to pre-process subject: $subject_dir"
                exit 1
            fi
            
            # Then run recon-all if requested
            if $RUN_RECON; then
                if ! run_recon_single "$subject_dir"; then
                    echo "Error: Failed to process subject: $subject_dir"
                    exit 1
                fi
            fi
        fi
        
        echo "Successfully processed subject: $subject_id"
    done
    
    echo "Sequential processing completed successfully!"
fi

echo "All subjects processed successfully!" 