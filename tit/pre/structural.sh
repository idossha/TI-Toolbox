#!/bin/bash
#
# Modular Pre-processing Pipeline Orchestrator
# This script orchestrates DICOM conversion, FreeSurfer recon-all, and SimNIBS m2m creation
# by calling individual specialized scripts.
#
# Usage:
#   ./structural.sh <subject_dir>... [recon-all] [--recon-only] [--parallel] [--convert-dicom] [--create-m2m]
#   ./structural.sh --subjects <subject_id1,subject_id2,...> [options...]
#

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "DEBUG: Script directory: $script_dir" >&2
LOG_UTIL_CANDIDATES=(
    "$script_dir/../bash_logging.sh"
    "$script_dir/../tools/bash_logging.sh"
)

log_util_path=""
for candidate in "${LOG_UTIL_CANDIDATES[@]}"; do
    echo "DEBUG: Looking for logging utility at: $candidate" >&2
    if [[ -f "$candidate" ]]; then
        log_util_path="$candidate"
        break
    fi
done

if [[ -n "$log_util_path" ]]; then
    echo "DEBUG: Logging utility file exists, sourcing it..." >&2
    source "$log_util_path"
    echo "DEBUG: Logging utility sourced" >&2
    
    # Check if key functions are available
    if command -v init_logging >/dev/null 2>&1; then
        echo "DEBUG: init_logging function is available" >&2
    else
        echo "DEBUG: init_logging function is NOT available" >&2
    fi
    
    if command -v log_info >/dev/null 2>&1; then
        echo "DEBUG: log_info function is available" >&2
    else
        echo "DEBUG: log_info function is NOT available" >&2
    fi
else
    echo "ERROR: Logging utility file not found. Looked in:" >&2
    for candidate in "${LOG_UTIL_CANDIDATES[@]}"; do
        echo "  - $candidate" >&2
    done
    echo "ERROR: Logging will not be available" >&2
fi

# Simple fallback logging function
simple_log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    if [[ -n "$LOG_FILE" && -f "$LOG_FILE" ]]; then
        echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    fi
    
    # Also output to stderr for immediate visibility
    echo "[$timestamp] [$level] $message" >&2
}

# Default values for optional flags
RUN_RECON=false
RECON_ONLY=false
PARALLEL=false
CONVERT_DICOM=false
CREATE_M2M=false
RUN_TISSUE_ANALYZER=${RUN_TISSUE_ANALYZER:-false}

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
  ASSETS_DD_DIR="$script_dir/../resources/dataset_descriptions"
  
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
  if [ ! -f "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/tit.dataset_description.json" ]; then
    mkdir -p "$PROJECT_DIR/derivatives/ti-toolbox"
    cp "$ASSETS_DD_DIR/tit.dataset_description.json" "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json"

    # Fill in project-specific information
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$PROJECT_NAME@$CURRENT_DATE\"/" "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json" && rm -f "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json.tmp"
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$PROJECT_NAME\": \"..\/..\/\"\n  }/" "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json" && rm -f "$PROJECT_DIR/derivatives/ti-toolbox/dataset_description.json.tmp"
  fi
  
  SUBJECT_DIRS+=("$SUBJECT_DIR")
  echo "DEBUG: Created and added subject directory: $SUBJECT_DIR" >&2
done

# Initialize logging early to capture any errors from the start
# Create log directory structure
if [[ -n "$PROJECT_DIR" ]]; then
    # Create logs directory structure - logs go directly to derivatives/ti-toolbox/logs/{subject_name}/
    LOGS_DIR="$PROJECT_DIR/derivatives/ti-toolbox/logs"
    mkdir -p "$LOGS_DIR"
    
    # Generate timestamp for this preprocessing run
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    
    # Set up logging for each subject - use BIDS format (sub-xxx)
    for subject_id in "${temp_subject_ids[@]}"; do
        bids_subject_id="sub-${subject_id}"
        mkdir -p "$LOGS_DIR/$bids_subject_id"
    done
    
    # Initialize logging with the first subject's log file
    if [[ ${#temp_subject_ids[@]} -gt 0 ]]; then
        first_subject="${temp_subject_ids[0]}"
        first_bids_subject="sub-${first_subject}"
        LOG_FILE="$LOGS_DIR/$first_bids_subject/preprocessing_${TIMESTAMP}.log"
        
        # Try to initialize logging, but continue if it fails
        if ! init_logging "structural" "$LOG_FILE"; then
            echo "WARNING: Failed to initialize logging, continuing without file logging" >&2
            LOG_FILE=""
        else
            # Update the logger name so all logging functions use "structural" instead of "bash_script"
            LOGGER_NAME="structural"
            # Configure external loggers for each subject - use BIDS format
            # Build JSON array manually for compatibility
            external_loggers_json="["
            for i in "${!temp_subject_ids[@]}"; do
                if [[ $i -gt 0 ]]; then
                    external_loggers_json+=","
                fi
                bids_subject_id="sub-${temp_subject_ids[i]}"
                external_loggers_json+="\"$bids_subject_id\""
            done
            external_loggers_json+="]"
            
            # Try to configure external loggers, but continue if it fails
            if ! configure_external_loggers "$external_loggers_json"; then
                echo "WARNING: Failed to configure external loggers, continuing with basic logging" >&2
            fi
            
            # Create a simple fallback log file to ensure errors are captured
            if [[ -n "$LOG_FILE" ]]; then
                # Create empty log file (no header)
                touch "$LOG_FILE"
            fi
        fi
    fi
    
    # Debug: Show log file locations immediately after creation
    if [[ -n "$LOGS_DIR" ]]; then
        # Silent - no debug output to console
        :
    fi
fi

# Process flags
i=0
while [ $i -lt ${#temp_flags[@]} ]; do
  flag=${temp_flags[$i]}
  case $flag in
    --parallel)
      PARALLEL=true
      echo "DEBUG: Set PARALLEL=true" >&2
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
    --cores)
      i=$((i+1))
      CORES=${temp_flags[$i]}
      if ! [[ $CORES =~ ^[0-9]+$ ]] || [ $CORES -lt 1 ]; then
        echo "Error: --cores must be followed by a positive integer" >&2
        exit 1
      fi
      echo "DEBUG: Set CORES=$CORES" >&2
      ;;
    *)
      echo "Unknown flag: $flag"
      echo "Usage: $0 <subject_dir_or_id>... [recon-all] [--recon-only] [--parallel] [--convert-dicom] [--create-m2m]"
      echo "       $0 --subjects <subject_id1,subject_id2,...> [options...]"
      echo ""
      echo "Processing Modes:"
      echo "  [default]       Sequential processing - one subject at a time using all cores"
      echo "  --parallel      Parallel processing - multiple subjects with 1 core each"
      echo ""
      echo "Other Flags:"
      echo "  --recon-only    Run only FreeSurfer recon-all"
      echo "  --convert-dicom Convert DICOM files"
      echo "  --create-m2m    Create SimNIBS m2m models"
      exit 1
      ;;
  esac
  i=$((i+1))
done

echo "DEBUG: Final SUBJECT_DIRS: ${SUBJECT_DIRS[*]}" >&2
echo "DEBUG: RUN_RECON=$RUN_RECON, PARALLEL=$PARALLEL, CONVERT_DICOM=$CONVERT_DICOM" >&2

# Enable summary mode for non-debug preprocessing
# When DEBUG_MODE=true, show detailed output (SUMMARY_MODE=false)
# When DEBUG_MODE=false, show summary output (SUMMARY_MODE=true)
debug_mode="${DEBUG_MODE:-false}"
if [[ "$debug_mode" == "true" ]]; then
    # Debug mode: show detailed output
    set_summary_mode false
else
    # Non-debug mode: show summary output
    set_summary_mode true
fi

# Validate subject directories
if [[ ${#SUBJECT_DIRS[@]} -eq 0 ]]; then
  echo "Error: At least one subject directory or subject ID is required."
  echo "Usage: $0 <subject_dir_or_id>... [recon-all] [--recon-only] [--parallel] [--convert-dicom] [--create-m2m]"
  echo "       $0 --subjects <subject_id1,subject_id2,...> [options...]"
  echo ""
  echo "Processing Modes:"
  echo "  [default]       Sequential processing - one subject at a time using all cores"
  echo "  --parallel      Parallel processing - multiple subjects with 1 core each"
  echo ""
  echo "Other Flags:"
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
        if ! run_dicom_single_with_summary "$subject_dir"; then
            success=false
        fi
    fi
    
    if $success; then
        echo "Non-recon processing completed successfully for subject: $subject_id"
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
    
    echo "Running FreeSurfer recon-all for subject: $subject_id"
    
    local recon_args=("$subject_dir")
    
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
    
    echo "FreeSurfer recon-all completed for subject: $subject_id"
    return 0
}

# Summary-enabled wrapper functions for individual processes
run_dicom_single_with_summary() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    local dicom_args=("$subject_dir")
    
    execute_with_summary "DICOM conversion" "$subject_id" \
        "\"$script_dir/dicom2nifti.sh\" ${dicom_args[*]}" \
        "DICOM conversion failed"
}

run_charm_single_with_summary() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    local charm_args=("$subject_dir")
    
    execute_with_summary "SimNIBS charm" "$subject_id" \
        "\"$script_dir/charm.sh\" ${charm_args[*]}" \
        "SimNIBS charm failed"
}

run_recon_single_with_summary() {
    local subject_dir="$1"
    local subject_id=$(basename "$subject_dir" | sed 's/^sub-//')
    
    local recon_args=("$subject_dir")
    
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
    
    if [[ -n "$CORES" ]]; then
      PARALLEL_JOBS=$CORES
    else
      PARALLEL_JOBS=$AVAILABLE_CORES
    fi
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
                run_charm_single_with_summary "$subject_dir"
                # Continue even if it fails
            done
        fi
    fi
    
    # Use absolute path to recon-all.sh for parallel execution
    recon_script="$(cd "$script_dir" && pwd)/recon-all.sh"
    
    # Build arguments - NO --parallel flag (single-threaded per subject)
    parallel_args=()
    
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
    # Main processing function
process_subjects() {
    # Log the start of processing
    if command -v log_info >/dev/null 2>&1; then
        log_info "Starting preprocessing pipeline for ${#SUBJECT_DIRS[@]} subject(s)"
        log_info "Processing mode: Sequential (one subject at a time, each using all available cores)"
    fi
    
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
        
        # Note: Tissue analysis logging is now handled by the tissue-analyzer.sh script itself
        # which creates timestamped logs in /projectdir/derivatives/ti-toolbox/logs/{subject_name}/
        
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

        # Run unified tissue analyzer (bone + CSF) if requested
        if $RUN_TISSUE_ANALYZER; then
            # Determine Labeling.nii.gz from SimNIBS segmentation
            bids_subject_id="sub-${subject_id}"
            m2m_dir="$PROJECT_DIR/derivatives/SimNIBS/$bids_subject_id/m2m_${subject_id}"
            label_nii="$m2m_dir/segmentation/Labeling.nii.gz"
            
            # Log tissue analysis start with proper logging
            if command -v log_info >/dev/null 2>&1; then
                log_info "Starting tissue analysis for subject: $subject_id"
                log_info "Looking for Labeling.nii.gz at: $label_nii"
            else
                # Fallback to simple logging
                simple_log "INFO" "Starting tissue analysis for subject: $subject_id"
                simple_log "INFO" "Looking for Labeling.nii.gz at: $label_nii"
            fi
            
            if [ -f "$label_nii" ]; then
                # Unified tissue analysis (bone + CSF)
                tissue_out_dir="$PROJECT_DIR/derivatives/ti-toolbox/tissue_analysis/$bids_subject_id"
                mkdir -p "$tissue_out_dir"
                
                if command -v log_info >/dev/null 2>&1; then
                    log_info "Running tissue analysis for subject: $subject_id"
                    log_info "Output directory: $tissue_out_dir"
                fi
                
                # Execute tissue analysis with detailed logging
                if command -v execute_with_summary >/dev/null 2>&1; then
                    execute_with_summary "Tissue analysis" "$subject_id" \
                        "\"$script_dir/tissue-analyzer.sh\" \"$label_nii\" -o \"$tissue_out_dir\"" \
                        "Tissue analysis failed"
                    tissue_result=$?
                else
                    # Fallback if execute_with_summary is not available
                    if command -v log_info >/dev/null 2>&1; then
                        log_info "execute_with_summary not available, running tissue-analyzer.sh directly"
                    fi
                    "$script_dir/tissue-analyzer.sh" "$label_nii" -o "$tissue_out_dir"
                    tissue_result=$?
                fi
                
                if [ $tissue_result -ne 0 ]; then
                    if command -v log_error >/dev/null 2>&1; then
                        log_error "Tissue analysis failed for subject: $subject_id with exit code: $tissue_result"
                    else
                        simple_log "ERROR" "Tissue analysis failed for subject: $subject_id with exit code: $tissue_result"
                    fi
                    overall_success=false
                else
                    # Log where tissue analysis results were saved
                    if command -v log_info >/dev/null 2>&1; then
                        log_info "Tissue analysis results saved to: $tissue_out_dir"
                    fi
                    # Debug: summarize result files
                    if command -v log_debug >/dev/null 2>&1; then
                        # Count files in bone and CSF subdirectories
                        bone_out_dir="$tissue_out_dir/bone_analysis"
                        csf_out_dir="$tissue_out_dir/csf_analysis"
                        
                        if [ -d "$bone_out_dir" ]; then
                            bone_png_count=$(ls -1 "$bone_out_dir"/*.png 2>/dev/null | wc -l)
                            bone_txt_count=$(ls -1 "$bone_out_dir"/*.txt 2>/dev/null | wc -l)
                            log_debug "Bone analysis generated $bone_png_count PNG(s) and $bone_txt_count TXT report(s) in $bone_out_dir"
                        fi
                        
                        if [ -d "$csf_out_dir" ]; then
                            csf_png_count=$(ls -1 "$csf_out_dir"/*.png 2>/dev/null | wc -l)
                            csf_txt_count=$(ls -1 "$csf_out_dir"/*.txt 2>/dev/null | wc -l)
                            log_debug "CSF analysis generated $csf_png_count PNG(s) and $csf_txt_count TXT report(s) in $csf_out_dir"
                        fi
                        
                        log_debug "Unified tissue analysis completed successfully for $subject_id"
                    fi
                fi
            else
                # Check if m2m directory exists but Labeling.nii.gz is missing
                if [ -d "$m2m_dir" ]; then
                    if command -v log_error >/dev/null 2>&1; then
                        log_error "Tissue analyzer failed for subject: $subject_id - Labeling.nii.gz not found in $m2m_dir/segmentation/"
                    else
                        simple_log "ERROR" "Tissue analyzer failed for subject: $subject_id - Labeling.nii.gz not found in $m2m_dir/segmentation/"
                    fi
                    if command -v log_process_failed >/dev/null 2>&1; then
                        log_process_failed "Tissue analyzer" "$subject_id" "Labeling.nii.gz not found in $m2m_dir/segmentation/"
                    fi
                else
                    if command -v log_error >/dev/null 2>&1; then
                        log_error "Tissue analyzer failed for subject: $subject_id - SimNIBS m2m folder not found at $m2m_dir. Please run m2m creation first."
                    else
                        simple_log "ERROR" "Tissue analyzer failed for subject: $subject_id - SimNIBS m2m folder not found at $m2m_dir. Please run m2m creation first."
                    fi
                    if command -v log_process_failed >/dev/null 2>&1; then
                        log_process_failed "Tissue analyzer" "$subject_id" "SimNIBS m2m folder not found at $m2m_dir. Please run m2m creation first."
                    fi
                fi
                overall_success=false
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

    # Log the completion of processing
    if command -v log_info >/dev/null 2>&1; then
        if [[ ${#FAILED_SUBJECTS[@]} -eq 0 ]]; then
            log_info "Preprocessing pipeline completed successfully for all subjects"
        else
            log_info "Preprocessing pipeline completed with ${#FAILED_SUBJECTS[@]} failed subject(s): ${FAILED_SUBJECTS[*]}"
        fi
    fi
}

# Call the main processing function
process_subjects
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

# Always show log file locations for debugging
if [[ -n "$LOGS_DIR" ]]; then
    echo ""
    echo "=== Log Files Generated ==="
    echo "Detailed logs are available at:"
    for subject_id in "${temp_subject_ids[@]}"; do
        bids_subject_id="sub-${subject_id}"
        log_file="$LOGS_DIR/$bids_subject_id/preprocessing_${TIMESTAMP}.log"
        if [[ -f "$log_file" ]]; then
            echo "  Subject $subject_id ($bids_subject_id): $log_file"
            # Show file size and last modified time
            if command -v stat >/dev/null 2>&1; then
                file_size=$(stat -c%s "$log_file" 2>/dev/null || stat -f%z "$log_file" 2>/dev/null || echo "unknown")
                echo "    Size: ${file_size} bytes"
            fi
        else
            echo "  Subject $subject_id ($bids_subject_id): $log_file (NOT FOUND)"
        fi
    done
    echo ""
    echo "For troubleshooting, check these log files for detailed error information."
    echo "If log files are not found, check the debug output above for logging setup issues."
else
    echo ""
    echo "=== Logging Information ==="
    echo "WARNING: No log directory was created. Logging may not have been initialized properly."
    echo "Check the debug output above for logging setup issues."
fi 