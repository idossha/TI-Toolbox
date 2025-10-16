#!/bin/bash

# Run Tests Inside SimNIBS Docker Environment
# This script is designed to run inside the SimNIBS container
# which already has SimNIBS, FreeSurfer, pytest, BATS, and all dependencies

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse command line arguments
RUN_UNIT_TESTS=true
RUN_INTEGRATION_TESTS=true
VERBOSE=false
SETUP_PROJECT=true
CLEANUP=true

show_help() {
    echo -e "${CYAN}TI-Toolbox Test Runner (SimNIBS Environment)${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  -u, --unit-only         Run only unit tests (skip integration tests)"
    echo "  -i, --integration-only  Run only integration tests (skip unit tests)"
    echo "  -s, --skip-setup        Skip test project setup (assumes already set up)"
    echo "  -v, --verbose           Show verbose output"
    echo "  -n, --no-cleanup        Don't cleanup test directories after completion"
    echo ""
    echo "Examples:"
    echo "  $0                      # Run all tests"
    echo "  $0 --unit-only          # Run only unit tests"
    echo "  $0 --integration-only   # Run only integration tests"
    echo "  $0 --verbose            # Run all tests with verbose output"
    echo ""
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -u|--unit-only)
            RUN_INTEGRATION_TESTS=false
            shift
            ;;
        -i|--integration-only)
            RUN_UNIT_TESTS=false
            shift
            ;;
        -s|--skip-setup)
            SETUP_PROJECT=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -n|--no-cleanup)
            CLEANUP=false
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}TI-Toolbox Test Suite (SimNIBS)${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Check for simnibs_python
if ! command -v simnibs_python &> /dev/null; then
    echo -e "${RED}Error: simnibs_python not found.${NC}"
    echo "This script requires the SimNIBS environment."
    exit 1
fi

echo -e "${GREEN}✓ SimNIBS environment detected${NC}"

# Find the TI-Toolbox directory
# Priority: 1) Current directory if it has tests/, 2) /ti-toolbox
TOOLBOX_DIR=""

if [ -d "tests" ] && [ -f "tests/test_analyzer.py" ]; then
    TOOLBOX_DIR=$(pwd)
    echo -e "${GREEN}✓ Using current directory: ${TOOLBOX_DIR}${NC}"
elif [ -d "/ti-toolbox/tests" ] && [ -f "/ti-toolbox/tests/test_analyzer.py" ]; then
    TOOLBOX_DIR="/ti-toolbox"
    echo -e "${GREEN}✓ Using /ti-toolbox directory${NC}"
else
    echo -e "${RED}Error: TI-Toolbox tests directory not found.${NC}"
    echo ""
    echo "Checked locations:"
    echo "  - $(pwd)/tests"
    echo "  - /ti-toolbox/tests"
    echo ""
    echo "Make sure you're either:"
    echo "  1. Running from TI-Toolbox root directory, or"
    echo "  2. Have mounted your local TI-Toolbox code into the container"
    exit 1
fi

cd "$TOOLBOX_DIR"
echo -e "${GREEN}✓ Working directory: ${TOOLBOX_DIR}${NC}"

# Ensure CLI scripts have execute permissions (important for mounted volumes)
if [ -d "CLI" ]; then
    chmod +x CLI/*.sh 2>/dev/null || true
    echo -e "${GREEN}✓ CLI scripts made executable${NC}"
fi

# Copy TI-Toolbox specific files to SimNIBS directories
if [ -n "$SIMNIBSDIR" ] && [ -d "$SIMNIBSDIR" ]; then
    echo -e "${CYAN}Copying TI-Toolbox extensions to SimNIBS...${NC}"
    
    # Copy EEG caps for CSC
    if [ -d "assets/ElectrodeCaps_MNI" ]; then
        mkdir -p "$SIMNIBSDIR/resources/ElectrodeCaps_MNI/"
        cp assets/ElectrodeCaps_MNI/* "$SIMNIBSDIR/resources/ElectrodeCaps_MNI/" 2>/dev/null || true
        echo -e "${GREEN}✓ ElectrodeCaps_MNI copied${NC}"
    fi
    
    # Copy Flex optimization extension
    if [ -f "assets/map-electrodes/tes_flex_optimization.py" ]; then
        cp assets/map-electrodes/tes_flex_optimization.py \
           "$SIMNIBSDIR/simnibs/optimization/tes_flex_optimization/tes_flex_optimization.py" 2>/dev/null || true
        echo -e "${GREEN}✓ tes_flex_optimization.py copied${NC}"
    fi
fi

echo ""

# Track test results
FAILED_TESTS=()
PASSED_TESTS=()

# Function to run a test suite
run_test() {
    local test_name=$1
    local test_command=$2
    
    echo -e "${CYAN}Running ${test_name}...${NC}"
    
    if [ "$VERBOSE" = true ]; then
        if eval "$test_command"; then
            echo -e "${GREEN}✓ ${test_name} passed${NC}"
            PASSED_TESTS+=("${test_name}")
            return 0
        else
            echo -e "${RED}✗ ${test_name} failed${NC}"
            FAILED_TESTS+=("${test_name}")
            return 1
        fi
    else
        if eval "$test_command" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ ${test_name} passed${NC}"
            PASSED_TESTS+=("${test_name}")
            return 0
        else
            echo -e "${RED}✗ ${test_name} failed${NC}"
            FAILED_TESTS+=("${test_name}")
            return 1
        fi
    fi
}

# Unit Tests
if [ "$RUN_UNIT_TESTS" = true ]; then
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Unit Tests${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    # Analyzer unit tests
    run_test "Analyzer Tests" \
        "simnibs_python -m pytest -q tests/test_analyzer.py tests/test_mesh_analyzer.py tests/test_voxel_analyzer.py tests/test_group_analyzer.py" || true
    
    echo ""
    
    # Simulator unit tests
    run_test "Simulator Tests" \
        "simnibs_python -m pytest -q tests/test_ti_simulator.py tests/test_mti_simulator.py" || true
    
    echo ""
    
    # Flex-search unit tests
    run_test "Flex-Search Tests" \
        "simnibs_python -m pytest -q tests/test_flex_search.py" || true
    
    echo ""
fi

# Integration Tests
if [ "$RUN_INTEGRATION_TESTS" = true ]; then
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Integration Tests${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    # Setup test project directory if needed
    if [ "$SETUP_PROJECT" = true ]; then
        echo -e "${CYAN}Setting up test project directory...${NC}"
        mkdir -p /mnt/test_projectdir
        chmod 777 /mnt/test_projectdir
        
        run_test "Setup Test Project" \
            "bash tests/setup_test_projectdir.sh" || true
        
        echo ""
    else
        echo -e "${YELLOW}Skipping test project setup (using existing)${NC}"
        echo ""
    fi
    
    # Run simulator integration tests
    run_test "Simulator Integration Tests" \
        "bash tests/test_simulator_runner.sh" || true
    
    echo ""
    
    # Run analyzer integration tests
    run_test "Analyzer Integration Tests" \
        "bash tests/test_analyzer_runner.sh" || true
    
    echo ""
    
    # Run BATS tests
    run_test "BATS Output Validation Tests" \
        "bash -lc 'bats tests/test_simulator_outputs.bats && bats tests/test_analyzer_outputs.bats'" || true
    
    echo ""
fi

# Cleanup
if [ "$CLEANUP" = true ] && [ "$RUN_INTEGRATION_TESTS" = true ]; then
    echo -e "${CYAN}Cleaning up test directories...${NC}"
    # Clean contents but not the mount point itself (handled by host)
    if [ -d "/mnt/test_projectdir" ]; then
        rm -rf /mnt/test_projectdir/* 2>/dev/null || true
        echo -e "${GREEN}✓ Test data cleaned${NC}"
    fi
    echo ""
fi

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Test Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ ${#PASSED_TESTS[@]} -gt 0 ]; then
    echo -e "${GREEN}Passed Tests (${#PASSED_TESTS[@]}):${NC}"
    for test in "${PASSED_TESTS[@]}"; do
        echo -e "  ${GREEN}✓${NC} $test"
    done
    echo ""
fi

if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
    echo -e "${RED}Failed Tests (${#FAILED_TESTS[@]}):${NC}"
    for test in "${FAILED_TESTS[@]}"; do
        echo -e "  ${RED}✗${NC} $test"
    done
    echo ""
    echo -e "${RED}Some tests failed. Run with --verbose flag for detailed output.${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed! ✨${NC}"
fi

echo ""

