#!/bin/bash
#
# Fix T2 Filenames Script
# Renames problematic T2 filenames to be FreeSurfer-compatible
#
# Usage: ./fix_t2_filenames.sh <project_dir>
#

# Source the logging utility
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/../tools/bash_logging.sh"

# Parse arguments
PROJECT_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        *)
            if [[ -z "$PROJECT_DIR" ]]; then
                PROJECT_DIR="$1"
            else
                echo "Error: Unknown argument: $1"
                echo "Usage: $0 <project_dir>"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$PROJECT_DIR" ]]; then
    echo "Error: Project directory is required"
    echo "Usage: $0 <project_dir>"
    exit 1
fi

# Validate project directory
if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "Error: Project directory does not exist: $PROJECT_DIR"
    exit 1
fi

# Set up logging
set_logger_name "fix_t2_filenames"
timestamp=$(date +"%Y%m%d_%H%M%S")
set_log_file "${PROJECT_DIR}/fix_t2_filenames_${timestamp}.log"

log_info "Starting T2 filename fixing for project: $PROJECT_DIR"

# Function to fix filenames in a directory
fix_filenames_in_dir() {
    local anat_dir="$1"
    local subject_id="$2"
    
    if [[ ! -d "$anat_dir" ]]; then
        log_warning "Anatomy directory not found: $anat_dir"
        return 0
    fi
    
    log_info "Processing subject: $subject_id"
    
    # Find files with problematic names (containing spaces or "T2" in the middle)
    for file in "$anat_dir"/*; do
        if [[ -f "$file" ]]; then
            filename=$(basename "$file")
            
            # Check if filename contains spaces or problematic patterns
            if [[ "$filename" =~ [[:space:]] ]] || [[ "$filename" =~ .*T2.*[[:space:]] ]]; then
                log_info "Found problematic filename: $filename"
                
                # Determine file extension
                if [[ "$filename" == *.nii.gz ]]; then
                    extension=".nii.gz"
                    base_name="${filename%.nii.gz}"
                elif [[ "$filename" == *.json ]]; then
                    extension=".json"
                    base_name="${filename%.json}"
                else
                    extension="${filename##*.}"
                    base_name="${filename%.*}"
                fi
                
                # Generate clean filename
                clean_name=$(echo "$base_name" | \
                    sed 's/[^a-zA-Z0-9._-]/_/g' | \
                    sed 's/__*/_/g' | \
                    sed 's/^_//;s/_$//')
                
                # Special handling for T1 and T2 images
                if [[ "$clean_name" =~ [Tt]1 ]]; then
                    clean_name="anat-T1w_acq-MPRAGE"
                elif [[ "$clean_name" =~ [Tt]2 ]]; then
                    clean_name="anat-T2w_acq-CUBE"
                fi
                
                new_filename="${clean_name}${extension}"
                new_filepath="$anat_dir/$new_filename"
                
                # Check if target file already exists
                if [[ -f "$new_filepath" ]]; then
                    log_warning "Target file already exists: $new_filename, adding timestamp"
                    timestamp_suffix="_$(date +%H%M%S)"
                    new_filename="${clean_name}${timestamp_suffix}${extension}"
                    new_filepath="$anat_dir/$new_filename"
                fi
                
                # Rename the file
                if mv "$file" "$new_filepath"; then
                    log_info "Renamed: $filename -> $new_filename"
                else
                    log_error "Failed to rename: $filename"
                fi
            fi
        fi
    done
}

# Process all subject directories
processed_count=0
for subject_path in "$PROJECT_DIR"/sub-*; do
    if [[ -d "$subject_path" ]]; then
        subject_id=$(basename "$subject_path")
        anat_dir="$subject_path/anat"
        
        fix_filenames_in_dir "$anat_dir" "$subject_id"
        ((processed_count++))
    fi
done

log_info "Completed T2 filename fixing for $processed_count subjects"
log_info "You can now re-run the preprocessing pipeline"

echo "T2 filename fixing completed!"
echo "Log file: ${PROJECT_DIR}/fix_t2_filenames_${timestamp}.log"
echo ""
echo "Next steps:"
echo "1. Re-run your preprocessing command"
echo "2. The problematic filenames have been fixed to be FreeSurfer-compatible" 