#!/bin/bash

# Unified Tissue Analyzer Script for TI-toolbox
# Wrapper script to run both bone and CSF analysis on segmented tissue data
# Output is organized under derivatives/ti-toolbox/tissue_analysis/sub-*/ structure

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
OUTPUT_DIR="tissue_analysis"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/../utils/tissue_analyzer.py"

# Source shared bash logging utility
UTIL_DIR="$SCRIPT_DIR/../utils"
if [ -f "$UTIL_DIR/bash_logging.sh" ]; then
    # shellcheck disable=SC1090
    source "$UTIL_DIR/bash_logging.sh"
    set_logger_name "tissue_analyzer"
else
    echo "[WARN] bash_logging.sh not found at $UTIL_DIR; proceeding without file logging" >&2
fi

# Print functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage information
show_usage() {
    cat << EOF
Unified Tissue Analyzer for TI-toolbox

Usage: $0 <nifti_file> [options]

Arguments:
    nifti_file              Path to the segmented NIfTI file (e.g., Labeling.nii.gz)

Options:
    -o, --output DIR        Output directory (default: tissue_analysis)
    -h, --help             Show this help message

Description:
    This script runs bone, CSF, and skin analysis on segmented tissue data using the
    unified tissue_analyzer.py Python script. Results are organized under:
    
    output_dir/
    ├── bone_analysis/     # Bone analysis results
    ├── csf_analysis/      # CSF analysis results
    └── skin_analysis/     # Skin analysis results
    
    Each subdirectory contains:
    - Thickness analysis visualizations (PNG)
    - Extraction methodology illustrations (PNG)
    - Combined publication figures (PNG)
    - Analysis summary reports (TXT)
    
    The script automatically:
    1. Validates input files and dependencies
    2. Runs bone analysis (labels 515, 516)
    3. Runs CSF analysis (labels 4, 5, 14, 15, 43, 44, 72, 24, 520)
    4. Runs skin analysis (label 511)
    5. Generates comprehensive logging to /projectdir/derivatives/ti-toolbox/logs/{subject_name}/
    6. Creates organized output structure
    
Examples:
    $0 Labeling.nii.gz
    $0 Labeling.nii.gz -o /path/to/output
    $0 /path/to/Labeling.nii.gz -o tissue_results

Requirements:
    - Python 3 with nibabel, numpy, matplotlib, scipy
    - tissue_analyzer.py script in utils/ directory
    - bash_logging.sh utility (optional, for enhanced logging)

EOF
}

# Validate input file
validate_input() {
    local nifti_file="$1"
    
    if [[ -z "$nifti_file" ]]; then
        print_error "No input file specified"
        show_usage
        exit 1
    fi
    
    if [[ ! -f "$nifti_file" ]]; then
        print_error "Input file not found: $nifti_file"
        exit 1
    fi
    
    if [[ ! "$nifti_file" =~ \.(nii|nii\.gz)$ ]]; then
        print_error "Input file must be a NIfTI file (.nii or .nii.gz): $nifti_file"
        exit 1
    fi
    
    print_info "Input validation passed: $nifti_file"
}

# Check dependencies
check_dependencies() {
    print_info "Checking dependencies..."
    
    # Check Python
    if ! command -v python3 >/dev/null 2>&1; then
        print_error "Python 3 is required but not found"
        exit 1
    fi
    
    # Check Python script
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_error "Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi
    
    # Check Python packages
    if ! python3 -c "import nibabel, numpy, matplotlib, scipy" 2>/dev/null; then
        print_error "Required Python packages not found. Please install: nibabel, numpy, matplotlib, scipy"
        exit 1
    fi
    
    # Test Python script with help
    print_info "Testing Python script..."
    if ! python3 "$PYTHON_SCRIPT" --help >/dev/null 2>&1; then
        print_error "Python script test failed. Testing with verbose output:"
        python3 "$PYTHON_SCRIPT" --help
        exit 1
    fi
    
    print_success "All dependencies satisfied"
    print_success "Python script test passed"
}

# Function to run bone analysis
run_bone_analysis() {
    local nifti_file="$1"
    local output_dir="$2"
    
    print_info "Starting bone analysis..."
    print_info "Input file: $nifti_file"
    print_info "Output directory: $output_dir/bone_analysis"
    print_info "Python script: $PYTHON_SCRIPT"
    
    # Check if Python script exists
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_error "Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi
    
    # Create bone analysis output directory
    local bone_output_dir="$output_dir/bone_analysis"
    mkdir -p "$bone_output_dir"
    
    # Run the Python analysis with bone tissue type and capture output
    print_info "Running bone analysis with Python script..."
    if command -v log_info >/dev/null 2>&1; then
        log_info "Starting bone analysis with Python script: $PYTHON_SCRIPT"
        log_info "Command: python3 $PYTHON_SCRIPT $nifti_file -t bone -o $bone_output_dir"
    fi
    
    # Capture Python script output and log it
    if command -v log_info >/dev/null 2>&1; then
        log_info "=== BONE ANALYSIS PYTHON OUTPUT START ==="
        # Run Python script and capture output, passing the log file path
        PYTHON_OUTPUT=$(TI_LOG_LEVEL=DEBUG TI_LOG_FILE="$TIMESTAMPED_LOG_FILE" python3 "$PYTHON_SCRIPT" "$nifti_file" -t bone -o "$bone_output_dir" 2>&1)
        PYTHON_EXIT_CODE=$?
        
        # Log each line of the Python output
        if [[ -n "$PYTHON_OUTPUT" ]]; then
            while IFS= read -r line; do
                if [[ -n "$line" ]]; then
                    log_info "PYTHON: $line"
                fi
            done <<< "$PYTHON_OUTPUT"
        fi
        log_info "=== BONE ANALYSIS PYTHON OUTPUT END ==="
    else
        # Fallback if logging not available
        PYTHON_OUTPUT=$(TI_LOG_LEVEL=DEBUG python3 "$PYTHON_SCRIPT" "$nifti_file" -t bone -o "$bone_output_dir" 2>&1)
        PYTHON_EXIT_CODE=$?
    fi
    
    if [ $PYTHON_EXIT_CODE -eq 0 ]; then
        print_success "Bone analysis completed successfully!"
        print_info "Results saved to: $bone_output_dir"
        
        # Log success to file if logging is available
        if command -v log_info >/dev/null 2>&1; then
            log_info "Bone analysis completed successfully for subject: $(basename "$(dirname "$output_dir")" | sed 's/^sub-//')"
        fi
        
        # List output files
        if [[ -d "$bone_output_dir" ]]; then
            print_info "Generated bone analysis files:"
            ls -la "$bone_output_dir" | grep -E '\.(png|txt)$' | while read -r line; do
                echo "  $line"
            done
        fi
        
        return 0
    else
        print_error "Bone analysis failed!"
        print_error "Python script exit code: $PYTHON_EXIT_CODE"
        print_error "Python script output:"
        echo "$PYTHON_OUTPUT"
        
        if command -v log_error >/dev/null 2>&1; then
            log_error "Bone analysis failed for subject: $(basename "$(dirname "$output_dir")" | sed 's/^sub-//')"
            log_error "Python script exit code: $PYTHON_EXIT_CODE"
            log_error "Python script output: $PYTHON_OUTPUT"
        fi
        return 1
    fi
}

# Function to run CSF analysis
run_csf_analysis() {
    local nifti_file="$1"
    local output_dir="$2"
    
    print_info "Starting CSF analysis..."
    print_info "Input file: $nifti_file"
    print_info "Output directory: $output_dir/csf_analysis"
    print_info "Python script: $PYTHON_SCRIPT"
    
    # Check if Python script exists
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_error "Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi
    
    # Create CSF analysis output directory
    local csf_output_dir="$output_dir/csf_analysis"
    mkdir -p "$csf_output_dir"
    
    # Run the Python analysis with CSF tissue type and capture output
    print_info "Running CSF analysis with Python script..."
    if command -v log_info >/dev/null 2>&1; then
        log_info "Starting CSF analysis with Python script: $PYTHON_SCRIPT"
        log_info "Command: python3 $PYTHON_SCRIPT $nifti_file -t csf -o $csf_output_dir"
    fi
    
    # Capture Python script output and log it
    if command -v log_info >/dev/null 2>&1; then
        log_info "=== CSF ANALYSIS PYTHON OUTPUT START ==="
        # Run Python script and capture output, passing the log file path
        PYTHON_OUTPUT=$(TI_LOG_LEVEL=DEBUG TI_LOG_FILE="$TIMESTAMPED_LOG_FILE" python3 "$PYTHON_SCRIPT" "$nifti_file" -t csf -o "$csf_output_dir" 2>&1)
        PYTHON_EXIT_CODE=$?
        
        # Log each line of the Python output
        if [[ -n "$PYTHON_OUTPUT" ]]; then
            while IFS= read -r line; do
                if [[ -n "$line" ]]; then
                    log_info "PYTHON: $line"
                fi
            done <<< "$PYTHON_OUTPUT"
        fi
        log_info "=== CSF ANALYSIS PYTHON OUTPUT END ==="
    else
        # Fallback if logging not available
        PYTHON_OUTPUT=$(TI_LOG_LEVEL=DEBUG python3 "$PYTHON_SCRIPT" "$nifti_file" -t csf -o "$csf_output_dir" 2>&1)
        PYTHON_EXIT_CODE=$?
    fi
    
    if [ $PYTHON_EXIT_CODE -eq 0 ]; then
        print_success "CSF analysis completed successfully!"
        print_info "Results saved to: $csf_output_dir"
        
        # Log success to file if logging is available
        if command -v log_info >/dev/null 2>&1; then
            log_info "CSF analysis completed successfully for subject: $(basename "$(dirname "$output_dir")" | sed 's/^sub-//')"
        fi
        
        # List output files
        if [[ -d "$csf_output_dir" ]]; then
            print_info "Generated CSF analysis files:"
            ls -la "$csf_output_dir" | grep -E '\.(png|txt)$' | while read -r line; do
                echo "  $line"
            done
        fi
        
        return 0
    else
        print_error "CSF analysis failed!"
        print_error "Python script exit code: $PYTHON_EXIT_CODE"
        print_error "Python script output:"
        echo "$PYTHON_OUTPUT"
        
        if command -v log_error >/dev/null 2>&1; then
            log_error "CSF analysis failed for subject: $(basename "$(dirname "$output_dir")" | sed 's/^sub-//')"
            log_error "Python script exit code: $PYTHON_EXIT_CODE"
            log_error "Python script output: $PYTHON_OUTPUT"
        fi
        return 1
    fi
}

# Function to run skin analysis
run_skin_analysis() {
    local nifti_file="$1"
    local output_dir="$2"
    
    print_info "Starting skin analysis..."
    print_info "Input file: $nifti_file"
    print_info "Output directory: $output_dir/skin_analysis"
    print_info "Python script: $PYTHON_SCRIPT"
    
    # Check if Python script exists
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_error "Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi
    
    # Create skin analysis output directory
    local skin_output_dir="$output_dir/skin_analysis"
    mkdir -p "$skin_output_dir"
    
    # Run the Python analysis with skin tissue type and capture output
    print_info "Running skin analysis with Python script..."
    if command -v log_info >/dev/null 2>&1; then
        log_info "Starting skin analysis with Python script: $PYTHON_SCRIPT"
        log_info "Command: python3 $PYTHON_SCRIPT $nifti_file -t skin -o $skin_output_dir"
    fi
    
    # Capture Python script output and log it
    if command -v log_info >/dev/null 2>&1; then
        log_info "=== SKIN ANALYSIS PYTHON OUTPUT START ==="
        # Run Python script and capture output, passing the log file path
        PYTHON_OUTPUT=$(TI_LOG_LEVEL=DEBUG TI_LOG_FILE="$TIMESTAMPED_LOG_FILE" python3 "$PYTHON_SCRIPT" "$nifti_file" -t skin -o "$skin_output_dir" 2>&1)
        PYTHON_EXIT_CODE=$?
        
        # Log each line of the Python output
        if [[ -n "$PYTHON_OUTPUT" ]]; then
            while IFS= read -r line; do
                if [[ -n "$line" ]]; then
                    log_info "PYTHON: $line"
                fi
            done <<< "$PYTHON_OUTPUT"
        fi
        log_info "=== SKIN ANALYSIS PYTHON OUTPUT END ==="
    else
        # Fallback if logging not available
        PYTHON_OUTPUT=$(TI_LOG_LEVEL=DEBUG python3 "$PYTHON_SCRIPT" "$nifti_file" -t skin -o "$skin_output_dir" 2>&1)
        PYTHON_EXIT_CODE=$?
    fi
    
    if [ $PYTHON_EXIT_CODE -eq 0 ]; then
        print_success "Skin analysis completed successfully!"
        print_info "Results saved to: $skin_output_dir"
        
        # Log success to file if logging is available
        if command -v log_info >/dev/null 2>&1; then
            log_info "Skin analysis completed successfully for subject: $(basename "$(dirname "$output_dir")" | sed 's/^sub-//')"
        fi
        
        # List output files
        if [[ -d "$skin_output_dir" ]]; then
            print_info "Generated skin analysis files:"
            ls -la "$skin_output_dir" | grep -E '\.(png|txt)$' | while read -r line; do
                echo "  $line"
            done
        fi
        
        return 0
    else
        print_error "Skin analysis failed!"
        print_error "Python script exit code: $PYTHON_EXIT_CODE"
        print_error "Python script output:"
        echo "$PYTHON_OUTPUT"
        
        if command -v log_error >/dev/null 2>&1; then
            log_error "Skin analysis failed for subject: $(basename "$(dirname "$output_dir")" | sed 's/^sub-//')"
            log_error "Python script exit code: $PYTHON_EXIT_CODE"
            log_error "Python script output: $PYTHON_OUTPUT"
        fi
        return 1
    fi
}

# Function to run the complete tissue analysis
run_tissue_analysis() {
    local nifti_file="$1"
    local output_dir="$2"
    
    print_info "Starting comprehensive tissue analysis (bone + CSF + skin)..."
    print_info "Input file: $nifti_file"
    print_info "Output directory: $output_dir"
    print_info "Python script: $PYTHON_SCRIPT"
    
    # Check if Python script exists
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_error "Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi
    
    # Create main output directory
    mkdir -p "$output_dir"
    
    # Track analysis results
    local bone_success=false
    local csf_success=false
    local skin_success=false
    local overall_success=true
    
    # Run bone analysis
    print_info "=== PHASE 1: BONE ANALYSIS ==="
    if run_bone_analysis "$nifti_file" "$output_dir"; then
        bone_success=true
        print_success "✓ Bone analysis completed successfully"
    else
        print_error "✗ Bone analysis failed"
        overall_success=false
    fi
    
    # Run CSF analysis
    print_info "=== PHASE 2: CSF ANALYSIS ==="
    if run_csf_analysis "$nifti_file" "$output_dir"; then
        csf_success=true
        print_success "✓ CSF analysis completed successfully"
    else
        print_error "✗ CSF analysis failed"
        overall_success=false
    fi
    
    # Run skin analysis
    print_info "=== PHASE 3: SKIN ANALYSIS ==="
    if run_skin_analysis "$nifti_file" "$output_dir"; then
        skin_success=true
        print_success "✓ Skin analysis completed successfully"
    else
        print_error "✗ Skin analysis failed"
        overall_success=false
    fi
    
    # Summary and final status
    print_info "=== TISSUE ANALYSIS SUMMARY ==="
    if [[ "$bone_success" == true ]]; then
        print_success "Bone analysis: ✓ Complete"
    else
        print_error "Bone analysis: ✗ Failed"
    fi
    
    if [[ "$csf_success" == true ]]; then
        print_success "CSF analysis: ✓ Complete"
    else
        print_error "CSF analysis: ✗ Failed"
    fi
    
    if [[ "$skin_success" == true ]]; then
        print_success "Skin analysis: ✓ Complete"
    else
        print_error "Skin analysis: ✗ Failed"
    fi
    
    if [[ "$overall_success" == true ]]; then
        print_success "Overall tissue analysis: ✓ COMPLETE"
        print_info "All analyses completed successfully!"
        
        # Log overall success
        if command -v log_info >/dev/null 2>&1; then
            log_info "Complete tissue analysis (bone + CSF + skin) completed successfully for subject: $(basename "$(dirname "$output_dir")" | sed 's/^sub-//')"
            
            # Log detailed results summary
            log_info "=== TISSUE ANALYSIS RESULTS SUMMARY ==="
            
            # Count files in bone, CSF, and skin subdirectories
            bone_out_dir="$output_dir/bone_analysis"
            csf_out_dir="$output_dir/csf_analysis"
            skin_out_dir="$output_dir/skin_analysis"
            
            if [ -d "$bone_out_dir" ]; then
                bone_png_count=$(ls -1 "$bone_out_dir"/*.png 2>/dev/null | wc -l)
                bone_txt_count=$(ls -1 "$bone_out_dir"/*.txt 2>/dev/null | wc -l)
                log_info "Bone analysis generated $bone_png_count PNG(s) and $bone_txt_count TXT report(s)"
                log_info "Bone analysis output directory: $bone_out_dir"
                
                # List specific files generated
                if [ $bone_png_count -gt 0 ]; then
                    log_info "Bone analysis PNG files:"
                    ls -1 "$bone_out_dir"/*.png 2>/dev/null | while read -r file; do
                        log_info "  - $(basename "$file")"
                    done
                fi
                
                if [ $bone_txt_count -gt 0 ]; then
                    log_info "Bone analysis TXT files:"
                    ls -1 "$bone_out_dir"/*.txt 2>/dev/null | while read -r file; do
                        log_info "  - $(basename "$file")"
                    done
                fi
            fi
            
            if [ -d "$csf_out_dir" ]; then
                csf_png_count=$(ls -1 "$csf_out_dir"/*.png 2>/dev/null | wc -l)
                csf_txt_count=$(ls -1 "$csf_out_dir"/*.txt 2>/dev/null | wc -l)
                log_info "CSF analysis generated $csf_png_count PNG(s) and $csf_txt_count TXT report(s)"
                log_info "CSF analysis output directory: $csf_out_dir"
                
                # List specific files generated
                if [ $csf_png_count -gt 0 ]; then
                    log_info "CSF analysis PNG files:"
                    ls -1 "$csf_out_dir"/*.png 2>/dev/null | while read -r file; do
                        log_info "  - $(basename "$file")"
                    done
                fi
                
                if [ $csf_txt_count -gt 0 ]; then
                    log_info "CSF analysis TXT files:"
                    ls -1 "$csf_out_dir"/*.txt 2>/dev/null | while read -r file; do
                        log_info "  - $(basename "$file")"
                    done
                fi
            fi
            
            if [ -d "$skin_out_dir" ]; then
                skin_png_count=$(ls -1 "$skin_out_dir"/*.png 2>/dev/null | wc -l)
                skin_txt_count=$(ls -1 "$skin_out_dir"/*.txt 2>/dev/null | wc -l)
                log_info "Skin analysis generated $skin_png_count PNG(s) and $skin_txt_count TXT report(s)"
                log_info "Skin analysis output directory: $skin_out_dir"
                
                # List specific files generated
                if [ $skin_png_count -gt 0 ]; then
                    log_info "Skin analysis PNG files:"
                    ls -1 "$skin_out_dir"/*.png 2>/dev/null | while read -r file; do
                        log_info "  - $(basename "$file")"
                    done
                fi
                
                if [ $skin_txt_count -gt 0 ]; then
                    log_info "Skin analysis TXT files:"
                    ls -1 "$skin_out_dir"/*.txt 2>/dev/null | while read -r file; do
                        log_info "  - $(basename "$file")"
                    done
                fi
            fi
            
            log_info "=== END TISSUE ANALYSIS RESULTS SUMMARY ==="
            log_info "=== Tissue Analyzer Completed Successfully at $(date) ==="
        fi
        
        
        # Show final output structure
        print_info "Final output structure:"
        print_info "  $output_dir/"
        print_info "  ├── bone_analysis/"
        print_info "  │   ├── bone_thickness_analysis.png"
        print_info "  │   ├── bone_extraction_methodology.png"
        print_info "  │   ├── bone_analysis_summary.txt"
        print_info "  │   └── bone_combined_publication_figure.png"
        print_info "  ├── csf_analysis/"
        print_info "  │   ├── csf_thickness_analysis.png"
        print_info "  │   ├── csf_extraction_methodology.png"
        print_info "  │   ├── csf_analysis_summary.txt"
        print_info "  │   └── csf_combined_publication_figure.png"
        print_info "  ├── skin_analysis/"
        print_info "  │   ├── skin_thickness_analysis.png"
        print_info "  │   ├── skin_extraction_methodology.png"
        print_info "  │   ├── skin_analysis_summary.txt"
        print_info "  │   └── skin_combined_publication_figure.png"
        
        return 0
    else
        print_error "Overall tissue analysis: ✗ FAILED"
        print_warning "Some analyses failed. Check the output above for details."
        
        # Log overall failure
        if command -v log_error >/dev/null 2>&1; then
            log_error "Tissue analysis had failures for subject: $(basename "$(dirname "$output_dir")" | sed 's/^sub-//')"
            log_error "=== Tissue Analyzer Completed with Failures at $(date) ==="
        fi
        
        return 1
    fi
}

# Main script logic
main() {
    local nifti_file=""
    local output_dir="$OUTPUT_DIR"
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -o|--output)
                output_dir="$2"
                shift 2
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                if [[ -z "$nifti_file" ]]; then
                    nifti_file="$1"
                else
                    print_error "Multiple input files specified"
                    show_usage
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # Validate inputs
    validate_input "$nifti_file"
    
    # Check dependencies
    check_dependencies
    
    # Set up timestamped logging if bash_logging.sh is available
    if command -v set_log_file >/dev/null 2>&1; then
        TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
        
        # Extract subject name from output directory path
        # Expected path format: /projectdir/derivatives/ti-toolbox/tissue_analysis/sub-001/
        # We want to extract "sub-001" or similar
        SUBJECT_NAME=$(basename "$output_dir" 2>/dev/null || echo "unknown")
        
        # Create logs directory structure: /projectdir/derivatives/ti-toolbox/logs/{subject_name}/
        # Go up 2 levels from tissue_analysis to get to ti-toolbox, then into logs
        PROJECT_ROOT=$(dirname "$(dirname "$output_dir")")
        LOGS_DIR="$PROJECT_ROOT/logs/$SUBJECT_NAME"
        mkdir -p "$LOGS_DIR"
        
        TIMESTAMPED_LOG_FILE="$LOGS_DIR/tissue_analyzer_${TIMESTAMP}.log"
        set_log_file "$TIMESTAMPED_LOG_FILE"
        log_info "=== Tissue Analyzer Started at $(date) ==="
        log_info "Input file: $nifti_file"
        log_info "Output directory: $output_dir"
        log_info "Log file: $TIMESTAMPED_LOG_FILE"
        log_info "Subject: $SUBJECT_NAME"
    fi
    
    # Run complete tissue analysis
    print_info "Starting tissue analysis pipeline..."
    if ! run_tissue_analysis "$nifti_file" "$output_dir"; then
        print_error "Tissue analysis pipeline failed!"
        if command -v log_error >/dev/null 2>&1; then
            log_error "Tissue analysis pipeline failed for input: $nifti_file"
            log_error "Check the log file for detailed error information: $TIMESTAMPED_LOG_FILE"
        fi
        exit 1
    fi
    
    print_success "Tissue analysis pipeline completed successfully!"
    if command -v log_info >/dev/null 2>&1; then
        log_info "Tissue analysis pipeline completed successfully for input: $nifti_file"
        log_info "Results available in: $output_dir"
        log_info "Log file: $TIMESTAMPED_LOG_FILE"
    fi
}

# Run main function
main "$@"
