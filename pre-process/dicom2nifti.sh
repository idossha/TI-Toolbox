#!/bin/bash
#
# DICOM to NIfTI Conversion Script
# Converts DICOM files to NIfTI format with automatic T1w/T2w detection
#
# Usage: ./dicom2nifti.sh <subject_dir> [--quiet]
#

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/../utils/bash_logging.sh"

# Parse arguments
SUBJECT_DIR=""
QUIET=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --quiet)
            QUIET=true
            shift
            ;;
        *)
            if [[ -z "$SUBJECT_DIR" ]]; then
                SUBJECT_DIR="$1"
            else
                echo "Error: Unknown argument: $1"
                echo "Usage: $0 <subject_dir> [--quiet]"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$SUBJECT_DIR" ]]; then
    echo "Error: Subject directory is required"
    echo "Usage: $0 <subject_dir> [--quiet]"
    exit 1
fi

# Validate subject directory
SUBJECT_DIR="$(cd "$SUBJECT_DIR" 2>/dev/null && pwd)"
if [[ ! -d "$SUBJECT_DIR" ]]; then
    echo "Error: Subject directory does not exist: $SUBJECT_DIR"
    exit 1
fi

# Set up project structure
PROJECT_NAME=$(basename "$(dirname "$SUBJECT_DIR")")
PROJECT_DIR="/mnt/${PROJECT_NAME}"
SUBJECT_ID=$(basename "$SUBJECT_DIR" | sed 's/^sub-//')
BIDS_SUBJECT_ID="sub-${SUBJECT_ID}"

# Define directories
SOURCEDATA_DIR="${PROJECT_DIR}/sourcedata/${BIDS_SUBJECT_ID}"
BIDS_ANAT_DIR="${PROJECT_DIR}/${BIDS_SUBJECT_ID}/anat"

# Set up logging
if ! $QUIET; then
    DERIVATIVES_DIR="${PROJECT_DIR}/derivatives"
    logs_dir="${DERIVATIVES_DIR}/logs/${BIDS_SUBJECT_ID}"
    mkdir -p "$logs_dir"
    set_logger_name "dicom2nifti"
    timestamp=$(date +"%Y%m%d_%H%M%S")
    set_log_file "${logs_dir}/dicom2nifti_${timestamp}.log"
fi

# Check if dcm2niix is available
if ! command -v dcm2niix &>/dev/null; then
    log_error "dcm2niix is not installed."
    exit 1
fi

log_info "Starting DICOM to NIfTI conversion for subject: $SUBJECT_ID"

# Function to handle compressed DICOM files
handle_compressed_dicom() {
    local source_dir="$1"
    local target_dir="$2"
    local scan_type="$3"
    
    # Look for .tgz files in the source directory
    for tgz_file in "$source_dir"/*.tgz; do
        if [ -f "$tgz_file" ]; then
            log_debug "Found compressed DICOM file: $tgz_file"
            
            # Create a temporary directory for extraction
            local temp_dir=$(mktemp -d)
            
            # Extract the .tgz file
            log_debug "Extracting $tgz_file to temporary directory..."
            tar -xzf "$tgz_file" -C "$temp_dir"
            
            # Find all DICOM files in the extracted directory
            local dicom_files=$(find "$temp_dir" -type f -name "*.dcm" -o -name "*.IMA" -o -name "*.dicom")
            
            if [ -n "$dicom_files" ]; then
                log_debug "Found DICOM files in extracted archive"
                
                # Create scan type directory if it doesn't exist
                mkdir -p "$target_dir"
                
                # Move DICOM files to the target directory
                log_debug "Moving DICOM files to $target_dir"
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

# Function to process DICOM directory
process_dicom_directory() {
    local source_dir="$1"
    local target_dir="$2"
    
    if [ -d "$source_dir" ] && [ "$(ls -A "$source_dir")" ]; then
        log_debug "Processing DICOM files in $source_dir..."
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
                        # Clean up series description to be FreeSurfer-friendly
                        # Remove problematic characters and replace spaces with underscores
                        clean_name=$(echo "$series_desc" | \
                            sed 's/[^a-zA-Z0-9._-]/_/g' | \
                            sed 's/__*/_/g' | \
                            sed 's/^_//;s/_$//')
                        
                        # Special handling for T1 and T2 images to ensure consistent naming
                        if [[ "$clean_name" =~ [Tt]1 ]]; then
                            clean_name="anat-T1w_acq-MPRAGE"
                        elif [[ "$clean_name" =~ [Tt]2 ]]; then
                            clean_name="anat-T2w_acq-CUBE"
                        fi
                        
                        # Create new filenames based on cleaned SeriesDescription
                        new_json="${BIDS_ANAT_DIR}/${clean_name}.json"
                        new_nii="${BIDS_ANAT_DIR}/${clean_name}.nii.gz"
                        
                        # Move and rename the files
                        mv "$json_file" "$new_json"
                        mv "$nii_file" "$new_nii"
                        log_debug "Renamed files to: $clean_name (from: $series_desc)"
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

# Handle compressed DICOM files if they exist
handle_compressed_dicom "${SOURCEDATA_DIR}/T1w" "${SOURCEDATA_DIR}/T1w/dicom" "T1w"
handle_compressed_dicom "${SOURCEDATA_DIR}/T2w" "${SOURCEDATA_DIR}/T2w/dicom" "T2w"

# Process T1w and T2w directories
T1_DICOM_DIR="${SOURCEDATA_DIR}/T1w/dicom"
T2_DICOM_DIR="${SOURCEDATA_DIR}/T2w/dicom"

if [ ! -d "$T1_DICOM_DIR" ] && [ ! -d "$T2_DICOM_DIR" ]; then
    log_warning "No DICOM directories found in T1w or T2w. Skipping DICOM conversion."
    exit 0
else
    log_info "Converting DICOM files to NIfTI..."
    
    # Process T1w directory if it exists and has files
    if [ -d "$T1_DICOM_DIR" ] && [ "$(ls -A "$T1_DICOM_DIR")" ]; then
        log_debug "Found T1w DICOM data, processing..."
        process_dicom_directory "$T1_DICOM_DIR" "$T1_DICOM_DIR"
    fi
    
    # Process T2w directory if it exists and has files
    if [ -d "$T2_DICOM_DIR" ] && [ "$(ls -A "$T2_DICOM_DIR")" ]; then
        log_info "Found T2w DICOM data, processing..."
        process_dicom_directory "$T2_DICOM_DIR" "$T2_DICOM_DIR"
    fi
fi

# Verify that NIfTI files were created and moved successfully
if [ ! -d "$BIDS_ANAT_DIR" ] || [ -z "$(ls -A "$BIDS_ANAT_DIR")" ]; then
    log_error "No NIfTI files found in $BIDS_ANAT_DIR"
    log_error "Please ensure anatomical MRI data is available."
    exit 1
fi

log_info "DICOM to NIfTI conversion completed successfully for subject: $SUBJECT_ID" 