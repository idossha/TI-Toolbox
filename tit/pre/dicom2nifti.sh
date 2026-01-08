#!/bin/bash
#
# DICOM to NIfTI Conversion Script
# Converts DICOM files to NIfTI format with automatic T1w/T2w detection
#
# Usage: ./dicom2nifti.sh <subject_dir> [--quiet]
#

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_UTIL_CANDIDATES=(
    "$script_dir/../bash_logging.sh"
    "$script_dir/../tools/bash_logging.sh"
)
log_util_path=""
for candidate in "${LOG_UTIL_CANDIDATES[@]}"; do
    if [[ -f "$candidate" ]]; then
        log_util_path="$candidate"
        break
    fi
done
if [[ -n "$log_util_path" ]]; then
    source "$log_util_path"
else
    echo "[WARN] bash_logging.sh not found (looked in: ${LOG_UTIL_CANDIDATES[*]}). Proceeding without enhanced logging." >&2
fi

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
    logs_dir="${DERIVATIVES_DIR}/ti-toolbox/logs/${BIDS_SUBJECT_ID}"
    mkdir -p "$logs_dir"

    # Ensure dataset_description.json exists for tit derivative
    ASSETS_DD_DIR="$script_dir/../resources/dataset_descriptions"
    if [ ! -f "$DERIVATIVES_DIR/tit/dataset_description.json" ] && [ -f "$ASSETS_DD_DIR/tit.dataset_description.json" ]; then
        mkdir -p "$DERIVATIVES_DIR/tit"
        cp "$ASSETS_DD_DIR/tit.dataset_description.json" "$DERIVATIVES_DIR/tit/dataset_description.json"
        
        # Fill in project-specific information
        PROJECT_NAME=$(basename "$PROJECT_DIR")
        CURRENT_DATE=$(date +"%Y-%m-%d")
        sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$PROJECT_NAME@$CURRENT_DATE\"/" "$DERIVATIVES_DIR/tit/dataset_description.json" && rm -f "$DERIVATIVES_DIR/tit/dataset_description.json.tmp"
        sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$PROJECT_NAME\": \"..\/..\/\"\n  }/" "$DERIVATIVES_DIR/tit/dataset_description.json" && rm -f "$DERIVATIVES_DIR/tit/dataset_description.json.tmp"
    fi

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

TI_TOOLBOX_OVERWRITE="${TI_TOOLBOX_OVERWRITE:-false}"
TI_TOOLBOX_PROMPT_OVERWRITE="${TI_TOOLBOX_PROMPT_OVERWRITE:-true}"

confirm_overwrite() {
    local target_path="$1"
    if [ "$TI_TOOLBOX_OVERWRITE" = "true" ] || [ "$TI_TOOLBOX_OVERWRITE" = "1" ]; then
        return 0
    fi
    if [ "$TI_TOOLBOX_PROMPT_OVERWRITE" = "false" ] || [ "$TI_TOOLBOX_PROMPT_OVERWRITE" = "0" ]; then
        return 1
    fi
    # interactive prompt when running in a TTY
    if [ -t 0 ]; then
        read -r -p "Output exists: ${target_path}. Overwrite? [y/N]: " ans
        case "$ans" in
            y|Y|yes|YES) return 0 ;;
            *) return 1 ;;
        esac
    fi
    return 1
}

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

# Function to process DICOM directory
process_dicom_directory() {
    local source_dir="$1"
    local target_dir="$2"
    
    if [ -d "$source_dir" ] && [ "$(ls -A "$source_dir")" ]; then
        log_info "Processing DICOM files in $source_dir..."
        # First convert in place
        dcm2niix -z y -o "$target_dir" "$source_dir"
        
        local wrote_t1w="false"
        local wrote_t2w="false"

		# Process each pair of files
		for json_file in "$target_dir"/*.json; do
			if [ -f "$json_file" ]; then
				# Get the corresponding nii.gz file
				nii_file="${json_file%.json}.nii.gz"
				if [ -f "$nii_file" ]; then
					# Determine scan type (T1w/T2w) preferring directory hint, fallback to SeriesDescription
					scan_suffix=""
					if [[ "$source_dir" == *"/T1w/"* ]]; then
						scan_suffix="T1w"
					elif [[ "$source_dir" == *"/T2w/"* ]]; then
						scan_suffix="T2w"
					else
						series_desc=$(grep -o '"SeriesDescription": *"[^"]*"' "$json_file" | cut -d'"' -f4)
						if [[ -n "$series_desc" && "$series_desc" =~ [Tt]1 ]]; then
							scan_suffix="T1w"
						elif [[ -n "$series_desc" && "$series_desc" =~ [Tt]2 ]]; then
							scan_suffix="T2w"
						fi
					fi
					
					# Build BIDS-compliant base name: sub-XX_T1w or sub-XX_T2w
					if [ -z "$scan_suffix" ]; then
						log_warning "Could not determine scan type for $json_file; leaving in anat with original name."
						base_name="${BIDS_SUBJECT_ID}"
					else
						base_name="${BIDS_SUBJECT_ID}_${scan_suffix}"
					fi

                    # We never auto-create run-XX variants. Instead:
                    # - Write ONE canonical T1w and ONE canonical T2w
                    # - Move any additional series into anat/extra/
                    if [ "$scan_suffix" = "T1w" ] && [ "$wrote_t1w" = "true" ]; then
                        mkdir -p "$BIDS_ANAT_DIR/extra"
                        mv "$json_file" "$BIDS_ANAT_DIR/extra/$(basename "$json_file")"
                        mv "$nii_file" "$BIDS_ANAT_DIR/extra/$(basename "$nii_file")"
                        log_warning "Additional T1w series detected; moved to anat/extra/: $(basename "$nii_file")"
                        continue
                    fi
                    if [ "$scan_suffix" = "T2w" ] && [ "$wrote_t2w" = "true" ]; then
                        mkdir -p "$BIDS_ANAT_DIR/extra"
                        mv "$json_file" "$BIDS_ANAT_DIR/extra/$(basename "$json_file")"
                        mv "$nii_file" "$BIDS_ANAT_DIR/extra/$(basename "$nii_file")"
                        log_warning "Additional T2w series detected; moved to anat/extra/: $(basename "$nii_file")"
                        continue
                    fi

					new_json="${BIDS_ANAT_DIR}/${base_name}.json"
					new_nii="${BIDS_ANAT_DIR}/${base_name}.nii.gz"

                    # If canonical exists, require explicit overwrite confirmation.
                    if [ -e "$new_nii" ] || [ -e "$new_json" ]; then
                        if confirm_overwrite "$new_nii"; then
                            rm -f "$new_nii" "$new_json"
                        else
                            mkdir -p "$BIDS_ANAT_DIR/extra"
                            mv "$json_file" "$BIDS_ANAT_DIR/extra/$(basename "$json_file")"
                            mv "$nii_file" "$BIDS_ANAT_DIR/extra/$(basename "$nii_file")"
                            log_warning "Kept existing canonical file; moved new conversion to anat/extra/: $(basename "$nii_file")"
                            continue
                        fi
                    fi
					
					# Move and rename the files
					mkdir -p "$BIDS_ANAT_DIR"
					mv "$json_file" "$new_json"
					mv "$nii_file" "$new_nii"
					log_info "Renamed files to: $(basename "$new_nii")"

                    if [ "$scan_suffix" = "T1w" ]; then
                        wrote_t1w="true"
                    elif [ "$scan_suffix" = "T2w" ]; then
                        wrote_t2w="true"
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
        log_info "Found T1w DICOM data, processing..."
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