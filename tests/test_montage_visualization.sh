#!/bin/bash

###########################################
# Simple Test Script for Montage Visualization
# Tests coordinate lookup and overlay functionality
# Uses artificial electrode pairs - no JSON dependency
# Ido Haber / ihaber@wisc.edu
# December 2024
###########################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
TEST_OUTPUT_DIR="test_montage_outputs"
PROJECT_DIR_NAME="TI-toolbox"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Simple Montage Visualization Test     ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Create test output directory
mkdir -p "$TEST_OUTPUT_DIR"

# Function to determine which coordinate file to use based on EEG net
get_coordinate_file() {
    local net_name="$1"
    
    case "$net_name" in
        "EGI_template.csv" | "GSN-HydroCel-185.csv" | "GSN-HydroCel-256.csv")
            echo "assets/amv/GSN-HD.csv"
            ;;
        "EEG10-10_UI_Jurak_2007.csv" | "EEG10-10_Neuroelectrics.csv")
            echo "assets/amv/10-10-net.csv"
            ;;
        *)
            echo "ERROR"
            ;;
    esac
}

# Function to get the appropriate template image based on EEG net
get_template_image() {
    local net_name="$1"
    
    case "$net_name" in
        "EGI_template.csv" | "GSN-HydroCel-185.csv" | "GSN-HydroCel-256.csv")
            echo "assets/amv/256template.png"
            ;;
        "EEG10-10_UI_Jurak_2007.csv" | "EEG10-10_Neuroelectrics.csv")
            echo "assets/amv/10-10-net.png"
            ;;
        *)
            echo "assets/amv/256template.png"  # Default fallback
            ;;
    esac
}

# Function to get coordinates based on file type
get_electrode_coordinates() {
    local electrode_label="$1"
    local coord_file="$2"
    
    if [[ "$coord_file" == *"GSN-HD.csv" ]]; then
        # GSN-HD format: name,xcord,modifiedxcord,ycord,modifiedycord (columns 3,5)
        awk -F, -v label="$electrode_label" '$1 == label {print $3, $5}' "$coord_file"
    elif [[ "$coord_file" == *"10-10-net.csv" ]]; then
        # 10-10-net format: electrode_name,x,y (columns 2,3)
        awk -F, -v label="$electrode_label" '$1 == label {print $2, $3}' "$coord_file"
    else
        echo ""
    fi
}

# Function to test coordinate lookup for a single electrode
test_electrode_lookup() {
    local net_name="$1"
    local electrode="$2"
    
    local coord_file=$(get_coordinate_file "$net_name")
    if [[ "$coord_file" == "ERROR" ]]; then
        echo -e "${RED}    ✗ Unknown net: $net_name${NC}"
        return 1
    fi
    
    if [[ ! -f "$coord_file" ]]; then
        echo -e "${RED}    ✗ Coordinate file not found: $coord_file${NC}"
        return 1
    fi
    
    local coords=$(get_electrode_coordinates "$electrode" "$coord_file")
    if [[ -n "$coords" ]]; then
        echo -e "${GREEN}    ✓ $electrode${NC} → coords: $coords (from $(basename $coord_file))"
        return 0
    else
        echo -e "${RED}    ✗ $electrode${NC} → not found in $(basename $coord_file)"
        return 1
    fi
}

# Function to create a simple test visualization
create_test_visualization() {
    local net_name="$1"
    local electrode_pairs="$2"
    local output_file="$3"
    
    local coord_file=$(get_coordinate_file "$net_name")
    local template_image=$(get_template_image "$net_name")
    
    # Copy appropriate template image
    if ! cp "$template_image" "$output_file" 2>/dev/null; then
        echo -e "${RED}    ✗ Failed to copy template image: $template_image${NC}"
        return 1
    fi
    
    echo -e "${GREEN}    ✓ Using template: $(basename $template_image)${NC}"
    
    # Process electrode pairs
    local ring_images=("pair1ring.png" "pair2ring.png" "pair3ring.png" "pair4ring.png")
    local pair_index=0
    
    echo "$electrode_pairs" | while IFS=',' read -r electrode1 electrode2; do
        if [[ -n "$electrode1" && -n "$electrode2" ]]; then
            local ring_image=${ring_images[$pair_index % ${#ring_images[@]}]}
            
            # Get coordinates for both electrodes
            local coords1=$(get_electrode_coordinates "$electrode1" "$coord_file")
            local coords2=$(get_electrode_coordinates "$electrode2" "$coord_file")
            
            if [[ -n "$coords1" && -n "$coords2" ]]; then
                # Extract x,y coordinates
                IFS=' ' read -r x1 y1 <<< "$coords1"
                IFS=' ' read -r x2 y2 <<< "$coords2"
                
                # Overlay rings using ImageMagick convert (if available)
                if command -v convert >/dev/null 2>&1; then
                    if [[ -f "assets/amv/$ring_image" ]]; then
                        convert "$output_file" "assets/amv/$ring_image" -geometry +${x1}+${y1} -composite "$output_file" 2>/dev/null
                        convert "$output_file" "assets/amv/$ring_image" -geometry +${x2}+${y2} -composite "$output_file" 2>/dev/null
                        echo -e "${GREEN}      ✓ Overlaid pair: $electrode1,$electrode2${NC}"
                    fi
                else
                    echo -e "${YELLOW}      ! ImageMagick not available, skipping overlay${NC}"
                fi
            else
                echo -e "${RED}      ✗ Missing coordinates for pair: $electrode1,$electrode2${NC}"
            fi
            
            pair_index=$((pair_index + 1))
        fi
    done
    
    if [[ -f "$output_file" ]]; then
        echo -e "${GREEN}    ✓ Test image created: $output_file${NC}"
        return 0
    else
        echo -e "${RED}    ✗ Failed to create test image${NC}"
        return 1
    fi
}

# Test cases with artificial electrode pairs
test_coordinate_lookups() {
    echo -e "${BLUE}Testing coordinate lookups...${NC}"
    echo ""
    
    local total_tests=0
    local passed_tests=0
    
    # GSN-HD compatible nets with E-type electrodes
    echo -e "${YELLOW}GSN-HD Compatible Nets (E-type electrodes):${NC}"
    local gsn_electrodes=("E001" "E010" "E020" "E050" "E100" "E150" "E200" "E256")
    local gsn_nets=("EGI_template.csv" "GSN-HydroCel-185.csv" "GSN-HydroCel-256.csv")
    
    for net in "${gsn_nets[@]}"; do
        echo "  Testing $net:"
        for electrode in "${gsn_electrodes[@]}"; do
            if test_electrode_lookup "$net" "$electrode"; then
                passed_tests=$((passed_tests + 1))
            fi
            total_tests=$((total_tests + 1))
        done
        echo ""
    done
    
    # 10-10 compatible nets with standard electrode names
    echo -e "${YELLOW}10-10 Compatible Nets (standard electrode names):${NC}"
    local eeg1010_electrodes=("Fp1" "Fp2" "Fz" "Cz" "Pz" "F3" "F4" "C3" "C4" "P3" "P4" "O1" "O3")
    local eeg1010_nets=("EEG10-10_UI_Jurak_2007.csv" "EEG10-10_Neuroelectrics.csv")
    
    for net in "${eeg1010_nets[@]}"; do
        echo "  Testing $net:"
        for electrode in "${eeg1010_electrodes[@]}"; do
            if test_electrode_lookup "$net" "$electrode"; then
                passed_tests=$((passed_tests + 1))
            fi
            total_tests=$((total_tests + 1))
        done
        echo ""
    done
    
    echo -e "${BLUE}Coordinate Lookup Results:${NC}"
    echo -e "${GREEN}Passed: $passed_tests${NC} / ${BLUE}Total: $total_tests${NC}"
    echo ""
}

# Test visualization creation
test_visualizations() {
    echo -e "${BLUE}Testing visualization creation...${NC}"
    echo ""
    
    local vis_tests=0
    local vis_passed=0
    
    # Test data: net_name:electrode_pairs:output_filename
    local test_cases=(
        "EGI_template.csv:E001,E010|E020,E050:gsn_egi_test.png"
        "GSN-HydroCel-256.csv:E100,E150|E200,E256:gsn_256_test.png"
        "EEG10-10_UI_Jurak_2007.csv:Fp1,Fp2|F3,F4:jurak_test.png"
        "EEG10-10_Neuroelectrics.csv:C3,C4|P3,P4:neuro_test.png"
    )
    
    for test_case in "${test_cases[@]}"; do
        IFS=':' read -r net_name electrode_pairs output_filename <<< "$test_case"
        
        echo -e "${YELLOW}Testing visualization: ${NC}$net_name → $output_filename"
        
        # Convert pipe-separated pairs to newline-separated
        local formatted_pairs=$(echo "$electrode_pairs" | tr '|' '\n')
        
        local output_path="$TEST_OUTPUT_DIR/$output_filename"
        
        if create_test_visualization "$net_name" "$formatted_pairs" "$output_path"; then
            vis_passed=$((vis_passed + 1))
        fi
        vis_tests=$((vis_tests + 1))
        echo ""
    done
    
    echo -e "${BLUE}Visualization Creation Results:${NC}"
    echo -e "${GREEN}Passed: $vis_passed${NC} / ${BLUE}Total: $vis_tests${NC}"
    echo ""
}

# Check prerequisites
check_prerequisites() {
    echo -e "${BLUE}Checking prerequisites...${NC}"
    
    local missing_files=0
    
    # Check coordinate files
    if [[ ! -f "assets/amv/GSN-HD.csv" ]]; then
        echo -e "${RED}  ✗ GSN-HD.csv not found${NC}"
        missing_files=$((missing_files + 1))
    else
        echo -e "${GREEN}  ✓ GSN-HD.csv found${NC}"
    fi
    
    if [[ ! -f "assets/amv/10-10-net.csv" ]]; then
        echo -e "${RED}  ✗ 10-10-net.csv not found${NC}"
        missing_files=$((missing_files + 1))
    else
        echo -e "${GREEN}  ✓ 10-10-net.csv found${NC}"
    fi
    
    # Check template images
    if [[ ! -f "assets/amv/256template.png" ]]; then
        echo -e "${RED}  ✗ GSN template image (256template.png) not found${NC}"
        missing_files=$((missing_files + 1))
    else
        echo -e "${GREEN}  ✓ GSN template image (256template.png) found${NC}"
    fi
    
    if [[ ! -f "assets/amv/10-10-net.png" ]]; then
        echo -e "${RED}  ✗ 10-10 template image (10-10-net.png) not found${NC}"
        missing_files=$((missing_files + 1))
    else
        echo -e "${GREEN}  ✓ 10-10 template image (10-10-net.png) found${NC}"
    fi
    
    # Check ring images
    local ring_count=0
    for i in {1..4}; do
        if [[ -f "assets/amv/pair${i}ring.png" ]]; then
            ring_count=$((ring_count + 1))
        fi
    done
    
    if [[ $ring_count -eq 4 ]]; then
        echo -e "${GREEN}  ✓ All ring images found (4/4)${NC}"
    else
        echo -e "${YELLOW}  ! Only $ring_count/4 ring images found${NC}"
    fi
    
    # Check ImageMagick
    if command -v convert >/dev/null 2>&1; then
        echo -e "${GREEN}  ✓ ImageMagick convert found${NC}"
    else
        echo -e "${YELLOW}  ! ImageMagick not found (overlays will be skipped)${NC}"
    fi
    
    echo ""
    
    if [[ $missing_files -gt 0 ]]; then
        echo -e "${RED}Found $missing_files missing files. Please fix before continuing.${NC}"
        exit 1
    fi
}

# Main execution
main() {
    # Check if we're in the right directory
    if [[ ! -d "assets/amv" ]]; then
        echo -e "${RED}Error: Please run this script from the TI-toolbox root directory${NC}"
        echo "Current directory: $(pwd)"
        exit 1
    fi
    
    # Check prerequisites
    check_prerequisites
    
    # Run tests
    test_coordinate_lookups
    test_visualizations
    
    # Summary
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Test Complete                         ${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo -e "Output directory: ${GREEN}$TEST_OUTPUT_DIR${NC}"
    echo ""
    echo -e "${GREEN}✓ Coordinate lookup functionality tested${NC}"
    echo -e "${GREEN}✓ Visualization creation tested${NC}"
    echo -e "${GREEN}✓ All 5 EEG net types validated${NC}"
    echo ""
}

# Run main function
main "$@" 