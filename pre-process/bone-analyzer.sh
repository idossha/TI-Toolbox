#!/bin/bash

# Skull Bone Analyzer Script for TI-toolbox
# Wrapper script to run skull bone analysis on segmented tissue data
# Output is organized under derivatives/ti-toolbox/bone_analysis/sub-*/ structure

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
OUTPUT_DIR="bone_analysis"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/bone_analyzer.py"

# Function to print colored output
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

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS] <nifti_file>

Analyze SKULL bone structures from segmented tissue data (excludes jaw/vertebrae).

Arguments:
  nifti_file          Path to the segmented NIfTI file (*.nii or *.nii.gz)

Options:
  -o, --output DIR    Output directory for results (default: bone_analysis_output)
  -h, --help          Show this help message

Examples:
  $0 data/labeling.nii.gz
  $0 -o derivatives/ti-toolbox/bone_analysis/sub-001 data/segmentation.nii
  $0 --output /path/to/derivatives/ti-toolbox/bone_analysis/sub-001 data/segmentation.nii

The tool will analyze:
  - Total volume of skull bone (cortical + cancellous combined)
  - Thickness statistics (max, min, mean, std) for skull region only
  - Generate PNG visualization of thickness distributions
  - Create a comprehensive summary report
  - Spatial filtering to exclude jaw and vertebrae

Input Requirements:
  - NIfTI file should contain segmented tissues with labels:
    * 515: Bone-Cortical
    * 516: Bone-Cancellous
    * 3: Left-Cerebral-Cortex (for skull region reference)
    * 42: Right-Cerebral-Cortex (for skull region reference)
    * 16: Brain-Stem (for skull region reference)
  - File should follow the labeling_LUT.txt convention

Output:
  - skull_bone_thickness_analysis.png (thickness analysis results)
  - skull_extraction_methodology.png (methodology illustration)
  - skull_bone_analysis_summary.txt (detailed report)
  - skull_combined_publication_figure.png (comprehensive visualization)

Note: Output is designed to be placed under derivatives/ti-toolbox/bone_analysis/sub-*/
EOF
}

# Function to check if Python packages are available
check_dependencies() {
    print_info "Checking Python dependencies..."
    
    python3 -c "
import sys
missing_packages = []

try:
    import nibabel
except ImportError:
    missing_packages.append('nibabel')

try:
    import numpy
except ImportError:
    missing_packages.append('numpy')

try:
    import matplotlib
except ImportError:
    missing_packages.append('matplotlib')

try:
    import scipy
except ImportError:
    missing_packages.append('scipy')

if missing_packages:
    print('Missing required packages:', ', '.join(missing_packages))
    print('Please install with: pip install ' + ' '.join(missing_packages))
    sys.exit(1)
else:
    print('All dependencies are available')
    sys.exit(0)
" || {
        print_error "Missing required Python packages. Please install them first."
        print_info "Run: pip install nibabel numpy matplotlib scipy"
        exit 1
    }
}

# Function to validate input file
validate_input() {
    local nifti_file="$1"
    
    if [[ -z "$nifti_file" ]]; then
        print_error "No input file specified"
        show_usage
        exit 1
    fi
    
    if [[ ! -f "$nifti_file" ]]; then
        print_error "Input file does not exist: $nifti_file"
        exit 1
    fi
    
    # Check if it's a NIfTI file
    if [[ ! "$nifti_file" =~ \.(nii|nii\.gz)$ ]]; then
        print_warning "File doesn't have .nii or .nii.gz extension: $nifti_file"
        print_info "Proceeding anyway, but ensure it's a valid NIfTI file"
    fi
    
    print_success "Input file validated: $nifti_file"
}

# Function to run the analysis
run_analysis() {
    local nifti_file="$1"
    local output_dir="$2"
    
    print_info "Starting skull bone analysis..."
    print_info "Input file: $nifti_file"
    print_info "Output directory: $output_dir"
    print_info "Python script: $PYTHON_SCRIPT"
    
    # Check if Python script exists
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_error "Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi
    
    # Run the Python analysis
    if python3 "$PYTHON_SCRIPT" "$nifti_file" -o "$output_dir"; then
        print_success "Skull bone analysis completed successfully!"
        print_info "Results saved to: $output_dir"
        
        # List output files
        if [[ -d "$output_dir" ]]; then
            print_info "Generated files:"
            ls -la "$output_dir" | grep -E '\.(png|txt)$' | while read -r line; do
                echo "  $line"
            done
        fi
    else
        print_error "Skull bone analysis failed!"
        exit 1
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
    
    # Run analysis
    run_analysis "$nifti_file" "$output_dir"
}

# Run main function
main "$@" 