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
FAILED_SUBJECTS=()

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
  
  # Ensure BIDS dataset_description.json exists for each derivative dataset root
  ASSETS_DD_DIR="$script_dir/../assets/dataset_descriptions"
  
  # Get project name for URI and DatasetLinks
  PROJECT_NAME=$(basename "$PROJECT_DIR")
  CURRENT_DATE=$(date +"%Y-%m-%d")
  
  # FreeSurfer derivative
  if [ ! -f "$PROJECT_DIR/derivatives/freesurfer/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/freesurfer.dataset_description.json" ]; then
    mkdir -p "$PROJECT_DIR/derivatives/freesurfer"
    cp "$ASSETS_DD_DIR/freesurfer.dataset_description.json" "$PROJECT_DIR/derivatives/freesurfer/dataset_description.json"
    
    # Fill in project-specific information
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$PROJECT_NAME@$CURRENT_DATE\"/" "$PROJECT_DIR/derivatives/freesurfer/dataset_description.json" && rm -f "$PROJECT_DIR/derivatives/freesurfer/dataset_description.json.tmp"
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$PROJECT_NAME\": \"..\/..\/\"\n  }/" "$PROJECT_DIR/derivatives/freesurfer/dataset_description.json" && rm -f "$PROJECT_DIR/derivatives/freesurfer/dataset_description.json.tmp"
  fi
  
  # SimNIBS derivative
  if [ ! -f "$PROJECT_DIR/derivatives/SimNIBS/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/simnibs.dataset_description.json" ]; then
    mkdir -p "$PROJECT_DIR/derivatives/SimNIBS"
    cp "$ASSETS_DD_DIR/simnibs.dataset_description.json" "$PROJECT_DIR/derivatives/SimNIBS/dataset_description.json"
    
    # Fill in project-specific information
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$PROJECT_NAME@$CURRENT_DATE\"/" "$PROJECT_DIR/derivatives/SimNIBS/dataset_description.json" && rm -f "$PROJECT_DIR/derivatives/SimNIBS/dataset_description.json.tmp"
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$PROJECT_NAME\": \"..\/..\/\"\n  }/" "$PROJECT_DIR/derivatives/SimNIBS/dataset_description.json" && rm -f "$PROJECT_DIR/derivatives/SimNIBS/dataset_description.json.tmp"
  fi
  
  # TI-Toolbox derivative
  if [ ! -f "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/ti-toolbox.dataset_description.json" ]; then
    mkdir -p "$PROJECT_DIR/derivatives/ti-toolbox"
    cp "$ASSETS_DD_DIR/ti-toolbox.dataset_description.json" "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json"
    
    # Fill in project-specific information
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$PROJECT_NAME@$CURRENT_DATE\"/" "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json" && rm -f "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json.tmp"
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$PROJECT_NAME\": \"..\/..\/\"\n  }/" "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json" && rm -f "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json.tmp"
  fi
  
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
      echo "Usage: $0 <subject_dir_or_id>... [recon-all] [--recon-only] [--parallel] [--quiet] [--convert-dicom] [--create-m2m]"
      echo "       $0 --subjects <subject_id1,subject_id2,...> [options...]"
      echo ""
      echo "Processing Modes:"
      echo "  [default]       Sequential processing - one subject at a time using all cores"
      echo "  --parallel      Parallel processing - multiple subjects with 1 core each"
      echo ""
      echo "Other Flags:"
      echo "  --quiet         Suppress verbose output"
      echo "  --recon-only    Run only FreeSurfer recon-all"
      echo "  --convert-dicom Convert DICOM files"
      echo "  --create-m2m    Create SimNIBS m2m models"
      exit 1
      ;;
  esac
done

echo "DEBUG: Final SUBJECT_DIRS: ${SUBJECT_DIRS[*]}" >&2
echo "DEBUG: RUN_RECON=$RUN_RECON, PARALLEL=$PARALLEL, CONVERT_DICOM=$CONVERT_DICOM" >&2

# Enable summary mode for non-debug preprocessing
if ! $QUIET; then
    set_summary_mode true
else
    set_summary_mode false
fi

# Validate subject directories
if [[ ${#SUBJECT_DIRS[@]} -eq 0 ]]; then
  echo "Error: At least one subject directory or subject ID is required."
  echo "Usage: $0 <subject_dir_or_id>... [recon-all] [--recon-only] [--parallel] [--quiet] [--convert-dicom] [--create-m2m]"
  echo "       $0 --subjects <subject_id1,subject_id2,...> [options...]"
  echo ""
  echo "Processing Modes:"
  echo "  [default]       Sequential processing - one subject at a time using all cores"
  echo "  --parallel      Parallel processing - multiple subjects with 1 core each"
  echo ""
  echo "Other Flags:"
  echo "  --quiet         Suppress verbose output"
  echo "  --recon-only    Run only FreeSurfer recon-all"
  echo "  --convert-dicom Convert DICOM files"
  echo "  --create-m2m    Create SimNIBS m2m models"
  exit 1
fi

# Print processing plan only in debug mode
if ! $SUMMARY_ENABLED; then
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
    echo ""
    if $PARALLEL; then
        echo "PARALLEL MODE: Multiple subjects will run simultaneously, each using 1 core"
    else
        echo "SEQUENTIAL MODE: One subject at a time, each using all available cores"
    fi
    echo ""
fi

# Function to process a single subject through all non-recon steps
process_subject_non_recon() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    local success=true
    
    echo "Processing non-recon steps for subject: $subject_id"
    
    # DICOM conversion
    if $CONVERT_DICOM; then
        echo "  Running DICOM conversion..."
        local dicom_args=("$subject_dir")
        if $QUIET; then
            dicom_args+=("--quiet")
        fi
        
        if ! "$script_dir/dicom2nifti.sh" "${dicom_args[@]}"; then
            echo "  Warning: DICOM conversion failed for subject: $subject_id"
            success=false
        else
            echo "DICOM conversion completed for subject: $subject_id"
        fi
    fi
    
    if $success; then
        return 0
    else
        FAILED_SUBJECTS+=("$subject_id")
        return 1
    fi
}

# Function to run SimNIBS charm for a single subject (always sequential)
run_charm_single() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    echo "Running SimNIBS charm for subject: $subject_id"
    
    local charm_args=("$subject_dir")
    if $QUIET; then
        charm_args+=("--quiet")
    fi
    
    if ! "$script_dir/charm.sh" "${charm_args[@]}"; then
        echo "Warning: SimNIBS charm failed for subject: $subject_id"
        FAILED_SUBJECTS+=("$subject_id")
        return 1
    fi
    
    echo "SimNIBS charm completed for subject: $subject_id"
    return 0
}

# Function to run recon-all for a single subject
run_recon_single() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    

    
    local recon_args=("$subject_dir")
    if $QUIET; then
        recon_args+=("--quiet")
    fi
    
    # Pass --parallel flag based on processing mode:
    # Sequential mode (--parallel NOT specified): pass --parallel to recon-all (use all cores)
    # Parallel mode (--parallel specified): don't pass --parallel to recon-all (use 1 core)
    if ! $PARALLEL; then
        # Sequential mode: this subject should use all available cores
        recon_args+=("--parallel")
        echo "  Sequential mode: subject will use all available cores"
    else
        # Parallel mode: this subject should use 1 core only
        echo "  Parallel mode: subject will use 1 core"
    fi
    
    if ! "$script_dir/recon-all.sh" "${recon_args[@]}"; then
        echo "Warning: FreeSurfer recon-all failed for subject: $subject_id"
        FAILED_SUBJECTS+=("$subject_id")
        return 1
    fi
    

    return 0
}

# Summary-enabled wrapper functions for individual processes
run_dicom_single_with_summary() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    local dicom_args=("$subject_dir")
    if $QUIET; then
        dicom_args+=("--quiet")
    fi
    
    execute_with_summary "DICOM conversion" "$subject_id" \
        "\"$script_dir/dicom2nifti.sh\" ${dicom_args[*]}" \
        "DICOM conversion failed"
}

run_charm_single_with_summary() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    local charm_args=("$subject_dir")
    if $QUIET; then
        charm_args+=("--quiet")
    fi
    
    execute_with_summary "SimNIBS charm" "$subject_id" \
        "\"$script_dir/charm.sh\" ${charm_args[*]}" \
        "SimNIBS charm failed"
}

run_recon_single_with_summary() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    local recon_args=("$subject_dir")
    if $QUIET; then
        recon_args+=("--quiet")
    fi
    
    # Pass --parallel flag based on processing mode
    if ! $PARALLEL; then
        recon_args+=("--parallel")
    fi
    
    execute_with_summary "FreeSurfer recon-all" "$subject_id" \
        "\"$script_dir/recon-all.sh\" ${recon_args[*]}" \
        "FreeSurfer recon-all failed"
}

# Main processing logic
if $PARALLEL && ($RUN_RECON || $RECON_ONLY) && [[ ${#SUBJECT_DIRS[@]} -gt 1 ]]; then
    # APPROACH 2: Simple parallelization - multiple subjects, each with 1 core
    if ! $SUMMARY_ENABLED; then
        echo "Starting PARALLEL processing of ${#SUBJECT_DIRS[@]} subject(s) using GNU Parallel..."
        echo "Each subject will use 1 core, multiple subjects will run simultaneously"
    fi
    
    # Check for GNU Parallel
    if ! command -v parallel &>/dev/null; then
        echo "Error: GNU Parallel is not installed, but --parallel was requested."
        echo "Please install GNU Parallel: apt-get install parallel"
        exit 1
    fi
    
    # Detect number of available cores
    if command -v nproc &>/dev/null; then
        AVAILABLE_CORES=$(nproc)
    elif command -v sysctl &>/dev/null; then
        AVAILABLE_CORES=$(sysctl -n hw.logicalcpu)
    else
        AVAILABLE_CORES=4  # fallback default
    fi
    
    # Set number of parallel jobs to available cores (or number of subjects if fewer)
    PARALLEL_JOBS=$AVAILABLE_CORES
    if [[ $PARALLEL_JOBS -gt ${#SUBJECT_DIRS[@]} ]]; then
        PARALLEL_JOBS=${#SUBJECT_DIRS[@]}
    fi
    
    if ! $SUMMARY_ENABLED; then
        echo "System configuration: $AVAILABLE_CORES cores available"
        echo "Will run $PARALLEL_JOBS subjects simultaneously, each using 1 core"
    fi
    
    # Determine if we need to run non-recon steps
    need_non_recon_steps=false
    if ! $RECON_ONLY && ($CONVERT_DICOM || $CREATE_M2M); then
        need_non_recon_steps=true
    fi
    
    # Process non-recon steps first (sequentially to avoid conflicts)
    if $need_non_recon_steps; then
        echo "Processing non-recon steps (DICOM conversion) first..."
        for subject_dir in "${SUBJECT_DIRS[@]}"; do
            process_subject_non_recon "$subject_dir"
            # Continue even if it fails
        done
        
        # Run SimNIBS charm sequentially to avoid PETSC segmentation faults
        if $CREATE_M2M; then
            echo "Running SimNIBS charm sequentially to prevent memory conflicts..."
            for subject_dir in "${SUBJECT_DIRS[@]}"; do
                run_charm_single "$subject_dir"
                # Continue even if it fails
            done
        fi
    fi
    
    # Use absolute path to recon-all.sh for parallel execution
    recon_script="$(cd "$script_dir" && pwd)/recon-all.sh"
    
    # Build arguments - NO --parallel flag (single-threaded per subject)
    parallel_args=()
    if $QUIET; then
        parallel_args+=("--quiet")
    fi
    
    echo "Running FreeSurfer recon-all in parallel mode (1 core per subject)..."
    
    # Run recon-all in parallel using GNU parallel - each subject gets 1 core
    printf '%s\n' "${SUBJECT_DIRS[@]}" | parallel \
        --line-buffer \
        --tagstring '[{/}] ' \
        --halt never \
        --jobs $PARALLEL_JOBS \
        "$recon_script" {} "${parallel_args[@]}"
    
    # Only show in debug mode
    if ! $SUMMARY_ENABLED; then
        echo "Parallel FreeSurfer recon-all processing completed."
    fi
    
else
    # APPROACH 1: Sequential processing - one subject at a time, each with multiple cores
    if ! $SUMMARY_ENABLED; then
        echo "Starting SEQUENTIAL processing of ${#SUBJECT_DIRS[@]} subject(s)..."
        echo "Each subject will be processed one at a time using all available cores"
    fi
    
    # Detect number of available cores
    if command -v nproc &>/dev/null; then
        AVAILABLE_CORES=$(nproc)
    elif command -v sysctl &>/dev/null; then
        AVAILABLE_CORES=$(sysctl -n hw.logicalcpu)
    else
        AVAILABLE_CORES=4  # fallback default
    fi
    
    if ! $SUMMARY_ENABLED; then
        echo "System configuration: $AVAILABLE_CORES cores available"
        echo "Each subject will use all $AVAILABLE_CORES cores for maximum speed"
    fi
    
    for subject_dir in "${SUBJECT_DIRS[@]}"; do
        subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
        local overall_success=true
        
        # Start preprocessing for this subject
        log_preprocessing_start "$subject_id"
        
        # Handle recon-only mode or when only recon-all is requested
        if $RECON_ONLY || ($RUN_RECON && ! $CONVERT_DICOM && ! $CREATE_M2M); then
            if ! run_recon_single_with_summary "$subject_dir"; then
                overall_success=false
            fi
        else
            # Process non-recon steps first
            if $CONVERT_DICOM; then
                if ! run_dicom_single_with_summary "$subject_dir"; then
                    overall_success=false
                fi
            fi
            
            # Run SimNIBS charm sequentially
            if $CREATE_M2M; then
                if ! run_charm_single_with_summary "$subject_dir"; then
                    overall_success=false
                fi
            fi
            
            # Then run recon-all if requested
            if $RUN_RECON; then
                if ! run_recon_single_with_summary "$subject_dir"; then
                    overall_success=false
                fi
            fi
        fi
        
        # Complete preprocessing for this subject
        log_preprocessing_complete "$subject_id" "$overall_success"
        
        if ! $overall_success; then
            FAILED_SUBJECTS+=("$subject_id")
        fi
    done
    
    # Only show in debug mode
    if ! $SUMMARY_ENABLED; then
        echo "Sequential processing completed."
    fi
fi

# Print final summary only in debug mode
if ! $SUMMARY_ENABLED; then
    echo "Processing completed!"
    if [ ${#FAILED_SUBJECTS[@]} -eq 0 ]; then
        echo "All subjects processed successfully!"
    else
        echo "Warning: The following subjects had failures:"
        printf '%s\n' "${FAILED_SUBJECTS[@]}"
        echo "Please check the logs for more details."
    fi
fi 