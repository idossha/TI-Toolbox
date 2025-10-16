#!/bin/bash

# TI-Toolbox Loader Test Script
# This script replicates the CircleCI build and test process locally
# It builds Docker images, installs necessary packages, sets up test project directory, and runs tests

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
PROJECT_ROOT=$(dirname "$(dirname "$SCRIPT_DIR")")

# Default parameters (matching CircleCI config)
USE_DOCKERHUB_IMAGES=${USE_DOCKERHUB_IMAGES:-true}
SKIP_COMPONENT_IMAGES=${SKIP_COMPONENT_IMAGES:-false}

# Test results directory
TEST_RESULTS_DIR="/tmp/test-results"
TEST_PROJECT_DIR="/tmp/test_projectdir"

# Test result tracking
declare -A TEST_RESULTS
declare -A TEST_START_TIMES
declare -A TEST_END_TIMES

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}TI-Toolbox Loader Test Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to get current timestamp
get_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Function to print colored output with timestamps
print_status() {
    echo -e "${CYAN}[$(get_timestamp)] [INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[$(get_timestamp)] [SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[$(get_timestamp)] [WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[$(get_timestamp)] [ERROR]${NC} $1"
}

# Function to print step header
print_step() {
    local step_num="$1"
    local step_name="$2"
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Step $step_num: $step_name${NC}"
    echo -e "${BLUE}========================================${NC}"
    print_status "Starting $step_name..."
}

# Function to start test timing
start_test_timing() {
    local test_name="$1"
    TEST_START_TIMES["$test_name"]=$(date +%s)
}

# Function to end test timing and record result
end_test_timing() {
    local test_name="$1"
    local success="$2"
    TEST_END_TIMES["$test_name"]=$(date +%s)
    TEST_RESULTS["$test_name"]="$success"
}

# Function to get test duration
get_test_duration() {
    local test_name="$1"
    local start_time="${TEST_START_TIMES[$test_name]}"
    local end_time="${TEST_END_TIMES[$test_name]}"
    if [[ -n "$start_time" && -n "$end_time" ]]; then
        local duration=$((end_time - start_time))
        printf "%02d:%02d" $((duration / 60)) $((duration % 60))
    else
        echo "00:00"
    fi
}

# Function to parse pytest results from XML
parse_pytest_results() {
    local xml_file="$1"
    local test_name="$2"
    
    if [[ -f "$xml_file" ]]; then
        # Extract test counts from XML (basic parsing)
        local total_tests=$(grep -o 'tests="[0-9]*"' "$xml_file" | grep -o '[0-9]*' | head -1)
        local failures=$(grep -o 'failures="[0-9]*"' "$xml_file" | grep -o '[0-9]*' | head -1)
        local errors=$(grep -o 'errors="[0-9]*"' "$xml_file" | grep -o '[0-9]*' | head -1)
        
        # Set defaults if not found
        total_tests=${total_tests:-0}
        failures=${failures:-0}
        errors=${errors:-0}
        
        local passed=$((total_tests - failures - errors))
        local success_rate=0
        
        if [[ $total_tests -gt 0 ]]; then
            success_rate=$((passed * 100 / total_tests))
        fi
        
        echo "$passed/$total_tests ($success_rate%)"
    else
        echo "No results found"
    fi
}

# Function to check if Docker is running
check_docker() {
    print_status "Checking Docker availability..."
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker is not running or not installed. Please start Docker and try again."
        exit 1
    fi
    print_success "Docker is available"
}

# Function to clean up any existing test containers before starting
cleanup_existing_containers() {
    print_status "Checking for existing test containers..."
    
    # Check for any running containers from previous test runs
    local running_test_containers=$(docker ps -q --filter "label=ti-toolbox-test" 2>/dev/null || true)
    
    if [ -n "$running_test_containers" ]; then
        print_warning "Found running test containers from previous runs. Stopping them..."
        echo "$running_test_containers" | xargs -r docker stop 2>/dev/null || true
        echo "$running_test_containers" | xargs -r docker rm 2>/dev/null || true
        print_success "Existing test containers cleaned up"
    else
        print_status "No existing test containers found"
    fi
    
    # Also check for any ci-runner containers that might be hanging
    local ci_containers=$(docker ps -aq --filter "ancestor=ci-runner:latest" 2>/dev/null || true)
    if [ -n "$ci_containers" ]; then
        print_warning "Found existing ci-runner containers. Cleaning them up..."
        echo "$ci_containers" | xargs -r docker rm -f 2>/dev/null || true
        print_success "Existing ci-runner containers cleaned up"
    fi
}

# Function to build or pull component images
prepare_component_images() {
    print_status "Preparing component images..."
    
    if [ "$USE_DOCKERHUB_IMAGES" = "true" ]; then
        print_status "Attempting to pull pre-built component images from DockerHub..."
        pulled_any=false
        
        # Try to pull each image, fallback to build if missing
        if docker pull idossha/simnibs:v2.1.2 >/dev/null 2>&1; then 
            docker tag idossha/simnibs:v2.1.2 simnibs:ci
            print_success "Pulled simnibs:v2.1.2"
            pulled_any=true
        else
            print_warning "Failed to pull simnibs:v2.1.2, will build locally"
        fi
        
        if docker pull idossha/ti-toolbox_fsl:v6.0.7.18 >/dev/null 2>&1; then 
            docker tag idossha/ti-toolbox_fsl:v6.0.7.18 fsl:ci
            print_success "Pulled fsl:v6.0.7.18"
            pulled_any=true
        else
            print_warning "Failed to pull fsl:v6.0.7.18, will build locally"
        fi
        
        if docker pull idossha/ti-toolbox_freesurfer:v7.4.1 >/dev/null 2>&1; then 
            docker tag idossha/ti-toolbox_freesurfer:v7.4.1 freesurfer:ci
            print_success "Pulled freesurfer:v7.4.1"
            pulled_any=true
        else
            print_warning "Failed to pull freesurfer:v7.4.1, will build locally"
        fi
        
        if docker pull idossha/matlab:20th >/dev/null 2>&1; then 
            docker tag idossha/matlab:20th matlab-runtime:ci
            print_success "Pulled matlab:20th"
            pulled_any=true
        else
            print_warning "Failed to pull matlab:20th, will build locally"
        fi
        
        if [ "$pulled_any" = "false" ]; then
            print_warning "No pre-built images available; building locally..."
            build_component_images
        fi
    else
        print_status "Building component images locally..."
        build_component_images
    fi
}

# Function to build component images locally
build_component_images() {
    print_status "Building component images locally..."
    
    # Check if Dockerfiles exist
    local dockerfiles=(
        "development/blueprint/Dockerfile.simnibs"
        "development/blueprint/Dockerfile.fsl"
        "development/blueprint/Dockerfile.freesurfer"
        "development/blueprint/Dockerfile.matlab.deprecated"
    )
    
    for dockerfile in "${dockerfiles[@]}"; do
        if [ ! -f "$PROJECT_ROOT/$dockerfile" ]; then
            print_error "Dockerfile not found: $dockerfile"
            exit 1
        fi
    done
    
    # Build images with BuildKit
    print_status "Building simnibs image..."
    DOCKER_BUILDKIT=1 docker build -f "$PROJECT_ROOT/development/blueprint/Dockerfile.simnibs" -t simnibs:ci "$PROJECT_ROOT"
    
    print_status "Building fsl image..."
    DOCKER_BUILDKIT=1 docker build -f "$PROJECT_ROOT/development/blueprint/Dockerfile.fsl" -t fsl:ci "$PROJECT_ROOT"
    
    print_status "Building freesurfer image..."
    DOCKER_BUILDKIT=1 docker build -f "$PROJECT_ROOT/development/blueprint/Dockerfile.freesurfer" -t freesurfer:ci "$PROJECT_ROOT"
    
    print_status "Building matlab-runtime image..."
    DOCKER_BUILDKIT=1 docker build -f "$PROJECT_ROOT/development/blueprint/Dockerfile.matlab.deprecated" -t matlab-runtime:ci "$PROJECT_ROOT"
    
    print_success "All component images built successfully"
}

# Function to build CI runner image
build_ci_runner() {
    print_status "Building CI runner image..."
    
    if [ ! -f "$PROJECT_ROOT/development/blueprint/Dockerfile.ci" ]; then
        print_error "Dockerfile.ci not found at $PROJECT_ROOT/development/blueprint/Dockerfile.ci"
        exit 1
    fi
    
    DOCKER_BUILDKIT=1 docker build -f "$PROJECT_ROOT/development/blueprint/Dockerfile.ci" -t ci-runner:latest "$PROJECT_ROOT"
    print_success "CI runner image built successfully"
}

# Function to setup test directories
setup_test_directories() {
    print_status "Setting up test directories..."
    
    # Create test results directory
    mkdir -p "$TEST_RESULTS_DIR"
    # Try to set permissions, but don't fail if it doesn't work
    chmod 777 "$TEST_RESULTS_DIR" 2>/dev/null || print_warning "Could not set permissions on $TEST_RESULTS_DIR (this is usually fine)"
    
    # Create test project directory
    mkdir -p "$TEST_PROJECT_DIR"
    # Try to set permissions, but don't fail if it doesn't work
    chmod 777 "$TEST_PROJECT_DIR" 2>/dev/null || print_warning "Could not set permissions on $TEST_PROJECT_DIR (this is usually fine)"
    
    print_success "Test directories created"
}

# Function to run analyzer unit tests
run_analyzer_tests() {
    local test_name="analyzer_unit_tests"
    start_test_timing "$test_name"
    
    print_status "Running analyzer unit tests..."
    
    # Add memory limits and ulimits to prevent bus errors
    if docker run --rm \
        --memory=4g \
        --memory-swap=4g \
        --cpus=2 \
        --ulimit nofile=65536:65536 \
        --ulimit nproc=32768:32768 \
        --label "ti-toolbox-test=analyzer-unit" \
        -v "$TEST_RESULTS_DIR:/tmp/test-results" \
        ci-runner:latest pytest -q \
        --junitxml=/tmp/test-results/analyzer.xml \
        tests/test_analyzer.py tests/test_mesh_analyzer.py tests/test_voxel_analyzer.py tests/test_group_analyzer.py; then
        end_test_timing "$test_name" "success"
        print_success "Analyzer unit tests completed successfully"
    else
        end_test_timing "$test_name" "failed"
        print_error "Analyzer unit tests failed"
        return 1
    fi
}

# Function to run simulator unit tests
run_simulator_tests() {
    local test_name="simulator_unit_tests"
    start_test_timing "$test_name"
    
    print_status "Running simulator unit tests..."
    
    # Add memory limits and ulimits to prevent bus errors
    if docker run --rm \
        --memory=4g \
        --memory-swap=4g \
        --cpus=2 \
        --ulimit nofile=65536:65536 \
        --ulimit nproc=32768:32768 \
        --label "ti-toolbox-test=simulator-unit" \
        -v "$TEST_RESULTS_DIR:/tmp/test-results" \
        ci-runner:latest pytest -q \
        --junitxml=/tmp/test-results/simulator.xml \
        tests/test_ti_simulator.py tests/test_mti_simulator.py; then
        end_test_timing "$test_name" "success"
        print_success "Simulator unit tests completed successfully"
    else
        end_test_timing "$test_name" "failed"
        print_error "Simulator unit tests failed"
        return 1
    fi
}

# Function to run flex-search unit tests
run_flex_search_tests() {
    local test_name="flex_search_unit_tests"
    start_test_timing "$test_name"
    
    print_status "Running flex-search unit tests..."
    
    # Add memory limits and ulimits to prevent bus errors
    if docker run --rm \
        --memory=4g \
        --memory-swap=4g \
        --cpus=2 \
        --ulimit nofile=65536:65536 \
        --ulimit nproc=32768:32768 \
        --label "ti-toolbox-test=flex-search-unit" \
        -v "$TEST_RESULTS_DIR:/tmp/test-results" \
        ci-runner:latest pytest -q \
        --junitxml=/tmp/test-results/flex_search.xml \
        tests/test_flex_search.py; then
        end_test_timing "$test_name" "success"
        print_success "Flex-search unit tests completed successfully"
    else
        end_test_timing "$test_name" "failed"
        print_error "Flex-search unit tests failed"
        return 1
    fi
}

# Function to setup test project directory
setup_test_project() {
    local test_name="test_project_setup"
    start_test_timing "$test_name"
    
    print_status "Setting up test project directory..."
    
    # Run the setup script inside the CI runner container
    if docker run --rm --user 0:0 --label "ti-toolbox-test=project-setup" -v "$TEST_PROJECT_DIR:/mnt/test_projectdir" ci-runner:latest bash -c '
        set -e
        bash tests/setup_test_projectdir.sh
    '; then
        end_test_timing "$test_name" "success"
        print_success "Test project directory setup completed"
    else
        end_test_timing "$test_name" "failed"
        print_error "Test project directory setup failed"
        return 1
    fi
}

# Function to run simulator integration tests
run_simulator_integration() {
    local test_name="simulator_integration_tests"
    start_test_timing "$test_name"
    
    print_status "Running simulator integration tests..."
    
    if docker run --rm --user 0:0 --label "ti-toolbox-test=simulator-integration" -v "$TEST_PROJECT_DIR:/mnt/test_projectdir" ci-runner:latest bash -c '
        set -e
        bash tests/test_simulator_runner.sh
    '; then
        end_test_timing "$test_name" "success"
        print_success "Simulator integration tests completed successfully"
    else
        end_test_timing "$test_name" "failed"
        print_error "Simulator integration tests failed"
        return 1
    fi
}

# Function to run analyzer integration tests
run_analyzer_integration() {
    local test_name="analyzer_integration_tests"
    start_test_timing "$test_name"
    
    print_status "Running analyzer integration tests..."
    
    if docker run --rm --user 0:0 --label "ti-toolbox-test=analyzer-integration" -v "$TEST_PROJECT_DIR:/mnt/test_projectdir" ci-runner:latest bash -c '
        set -e
        bash tests/test_analyzer_runner.sh
    '; then
        end_test_timing "$test_name" "success"
        print_success "Analyzer integration tests completed successfully"
    else
        end_test_timing "$test_name" "failed"
        print_error "Analyzer integration tests failed"
        return 1
    fi
}

# Function to run BATS integration tests
run_bats_tests() {
    local test_name="bats_integration_tests"
    start_test_timing "$test_name"
    
    print_status "Running BATS integration tests..."
    
    if docker run --rm --user 0:0 --label "ti-toolbox-test=bats-validation" -v "$TEST_PROJECT_DIR:/mnt/test_projectdir" -v "$TEST_RESULTS_DIR:/tmp/test-results" ci-runner:latest bash -lc '
        set -e
        bats tests/test_simulator_outputs.bats | tee /tmp/test-results/bats_simulator.txt
        bats tests/test_analyzer_outputs.bats | tee /tmp/test-results/bats_analyzer.txt
        echo Done > /tmp/test-results/_finished_integration.txt
    '; then
        end_test_timing "$test_name" "success"
        print_success "BATS integration tests completed successfully"
    else
        end_test_timing "$test_name" "failed"
        print_error "BATS integration tests failed"
        return 1
    fi
}

# Function to display comprehensive test results summary
display_results_summary() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}COMPREHENSIVE TEST RESULTS SUMMARY${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    # Overall execution time
    local total_start_time="${TEST_START_TIMES[analyzer_unit_tests]}"
    local total_end_time="${TEST_END_TIMES[bats_integration_tests]}"
    if [[ -n "$total_start_time" && -n "$total_end_time" ]]; then
        local total_duration=$((total_end_time - total_start_time))
        print_status "Total execution time: $(printf "%02d:%02d" $((total_duration / 60)) $((total_duration % 60)))"
    fi
    echo ""
    
    # Unit Tests Summary
    echo -e "${CYAN}UNIT TESTS SUMMARY${NC}"
    echo -e "${CYAN}==================${NC}"
    
    local unit_tests_passed=0
    local unit_tests_total=0
    local unit_tests_failed=0
    
    # Analyzer unit tests
    if [[ "${TEST_RESULTS[analyzer_unit_tests]}" == "success" ]]; then
        local analyzer_results=$(parse_pytest_results "$TEST_RESULTS_DIR/analyzer.xml" "analyzer")
        echo -e "${GREEN}✓ Analyzer Unit Tests${NC}     [$(get_test_duration "analyzer_unit_tests")] - $analyzer_results"
        unit_tests_passed=$((unit_tests_passed + 1))
    else
        echo -e "${RED}✗ Analyzer Unit Tests${NC}     [$(get_test_duration "analyzer_unit_tests")] - FAILED"
        unit_tests_failed=$((unit_tests_failed + 1))
    fi
    unit_tests_total=$((unit_tests_total + 1))
    
    # Simulator unit tests
    if [[ "${TEST_RESULTS[simulator_unit_tests]}" == "success" ]]; then
        local simulator_results=$(parse_pytest_results "$TEST_RESULTS_DIR/simulator.xml" "simulator")
        echo -e "${GREEN}✓ Simulator Unit Tests${NC}    [$(get_test_duration "simulator_unit_tests")] - $simulator_results"
        unit_tests_passed=$((unit_tests_passed + 1))
    else
        echo -e "${RED}✗ Simulator Unit Tests${NC}    [$(get_test_duration "simulator_unit_tests")] - FAILED"
        unit_tests_failed=$((unit_tests_failed + 1))
    fi
    unit_tests_total=$((unit_tests_total + 1))
    
    # Flex-search unit tests
    if [[ "${TEST_RESULTS[flex_search_unit_tests]}" == "success" ]]; then
        local flex_results=$(parse_pytest_results "$TEST_RESULTS_DIR/flex_search.xml" "flex_search")
        echo -e "${GREEN}✓ Flex-Search Unit Tests${NC}  [$(get_test_duration "flex_search_unit_tests")] - $flex_results"
        unit_tests_passed=$((unit_tests_passed + 1))
    else
        echo -e "${RED}✗ Flex-Search Unit Tests${NC}  [$(get_test_duration "flex_search_unit_tests")] - FAILED"
        unit_tests_failed=$((unit_tests_failed + 1))
    fi
    unit_tests_total=$((unit_tests_total + 1))
    
    # Unit tests overall
    local unit_success_rate=0
    if [[ $unit_tests_total -gt 0 ]]; then
        unit_success_rate=$((unit_tests_passed * 100 / unit_tests_total))
    fi
    
    echo ""
    if [[ $unit_tests_failed -eq 0 ]]; then
        echo -e "${GREEN}UNIT TESTS: ALL PASSED ($unit_tests_passed/$unit_tests_total - 100%)${NC}"
    else
        echo -e "${YELLOW}UNIT TESTS: $unit_tests_passed/$unit_tests_total PASSED ($unit_success_rate%) - $unit_tests_failed FAILED${NC}"
    fi
    echo ""
    
    # Integration Tests Summary
    echo -e "${CYAN}INTEGRATION TESTS SUMMARY${NC}"
    echo -e "${CYAN}============================${NC}"
    
    local integration_tests_passed=0
    local integration_tests_total=0
    local integration_tests_failed=0
    
    # Test project setup
    if [[ "${TEST_RESULTS[test_project_setup]}" == "success" ]]; then
        echo -e "${GREEN}✓ Test Project Setup${NC}      [$(get_test_duration "test_project_setup")] - SUCCESS"
        integration_tests_passed=$((integration_tests_passed + 1))
    else
        echo -e "${RED}✗ Test Project Setup${NC}      [$(get_test_duration "test_project_setup")] - FAILED"
        integration_tests_failed=$((integration_tests_failed + 1))
    fi
    integration_tests_total=$((integration_tests_total + 1))
    
    # Simulator integration tests
    if [[ "${TEST_RESULTS[simulator_integration_tests]}" == "success" ]]; then
        echo -e "${GREEN}✓ Simulator Integration${NC}   [$(get_test_duration "simulator_integration_tests")] - SUCCESS"
        integration_tests_passed=$((integration_tests_passed + 1))
    else
        echo -e "${RED}✗ Simulator Integration${NC}   [$(get_test_duration "simulator_integration_tests")] - FAILED"
        integration_tests_failed=$((integration_tests_failed + 1))
    fi
    integration_tests_total=$((integration_tests_total + 1))
    
    # Analyzer integration tests
    if [[ "${TEST_RESULTS[analyzer_integration_tests]}" == "success" ]]; then
        echo -e "${GREEN}✓ Analyzer Integration${NC}    [$(get_test_duration "analyzer_integration_tests")] - SUCCESS"
        integration_tests_passed=$((integration_tests_passed + 1))
    else
        echo -e "${RED}✗ Analyzer Integration${NC}    [$(get_test_duration "analyzer_integration_tests")] - FAILED"
        integration_tests_failed=$((integration_tests_failed + 1))
    fi
    integration_tests_total=$((integration_tests_total + 1))
    
    # BATS integration tests
    if [[ "${TEST_RESULTS[bats_integration_tests]}" == "success" ]]; then
        echo -e "${GREEN}✓ BATS Validation Tests${NC}   [$(get_test_duration "bats_integration_tests")] - SUCCESS"
        integration_tests_passed=$((integration_tests_passed + 1))
    else
        echo -e "${RED}✗ BATS Validation Tests${NC}   [$(get_test_duration "bats_integration_tests")] - FAILED"
        integration_tests_failed=$((integration_tests_failed + 1))
    fi
    integration_tests_total=$((integration_tests_total + 1))
    
    # Integration tests overall
    local integration_success_rate=0
    if [[ $integration_tests_total -gt 0 ]]; then
        integration_success_rate=$((integration_tests_passed * 100 / integration_tests_total))
    fi
    
    echo ""
    if [[ $integration_tests_failed -eq 0 ]]; then
        echo -e "${GREEN}INTEGRATION TESTS: ALL PASSED ($integration_tests_passed/$integration_tests_total - 100%)${NC}"
    else
        echo -e "${YELLOW}INTEGRATION TESTS: $integration_tests_passed/$integration_tests_total PASSED ($integration_success_rate%) - $integration_tests_failed FAILED${NC}"
    fi
    echo ""
    
    # Overall Summary
    local total_tests_passed=$((unit_tests_passed + integration_tests_passed))
    local total_tests=$((unit_tests_total + integration_tests_total))
    local total_failed=$((unit_tests_failed + integration_tests_failed))
    local overall_success_rate=0
    
    if [[ $total_tests -gt 0 ]]; then
        overall_success_rate=$((total_tests_passed * 100 / total_tests))
    fi
    
    echo -e "${BLUE}OVERALL SUMMARY${NC}"
    echo -e "${BLUE}=================${NC}"
    if [[ $total_failed -eq 0 ]]; then
        echo -e "${GREEN}ALL TESTS PASSED! ($total_tests_passed/$total_tests - 100%)${NC}"
        echo -e "${GREEN}TI-Toolbox is ready for use!${NC}"
    else
        echo -e "${YELLOW}$total_tests_passed/$total_tests TESTS PASSED ($overall_success_rate%) - $total_failed FAILED${NC}"
        echo -e "${YELLOW}Please review failed tests and fix issues before proceeding.${NC}"
    fi
    echo ""
    
    # Test artifacts information
    if [ -d "$TEST_RESULTS_DIR" ]; then
        echo -e "${CYAN}Test Artifacts:${NC}"
        echo -e "${CYAN}   Results Directory: $TEST_RESULTS_DIR${NC}"
        echo -e "${CYAN}   Project Directory: $TEST_PROJECT_DIR${NC}"
        echo ""
        
        # List available artifacts
        if ls "$TEST_RESULTS_DIR"/*.xml >/dev/null 2>&1; then
            echo -e "${GREEN}   Unit Test Reports:${NC}"
            for xml_file in "$TEST_RESULTS_DIR"/*.xml; do
                echo -e "${GREEN}     - $(basename "$xml_file")${NC}"
            done
        fi
        
        if ls "$TEST_RESULTS_DIR"/*.txt >/dev/null 2>&1; then
            echo -e "${GREEN}   Integration Test Reports:${NC}"
            for txt_file in "$TEST_RESULTS_DIR"/*.txt; do
                echo -e "${GREEN}     - $(basename "$txt_file")${NC}"
            done
        fi
    fi
    echo ""
}

# Function to cleanup Docker containers and temporary files
cleanup() {
    print_status "Cleaning up Docker containers and temporary files..."
    
    # Stop and remove any running containers from this script
    print_status "Stopping and removing test containers..."
    
    # Get list of running containers that might be from our tests
    local running_containers=$(docker ps -q --filter "ancestor=ci-runner:latest" 2>/dev/null || true)
    
    if [ -n "$running_containers" ]; then
        print_status "Stopping running test containers..."
        echo "$running_containers" | xargs -r docker stop 2>/dev/null || true
        print_status "Removing test containers..."
        echo "$running_containers" | xargs -r docker rm 2>/dev/null || true
    fi
    
    # Clean up any dangling containers
    local dangling_containers=$(docker ps -aq --filter "ancestor=ci-runner:latest" 2>/dev/null || true)
    if [ -n "$dangling_containers" ]; then
        print_status "Removing dangling test containers..."
        echo "$dangling_containers" | xargs -r docker rm 2>/dev/null || true
    fi
    
    # Clean up any containers that might have been created during testing
    # Look for containers with test-related names or created recently
    local test_containers=$(docker ps -aq --filter "label=ti-toolbox-test" 2>/dev/null || true)
    if [ -n "$test_containers" ]; then
        print_status "Removing test-labeled containers..."
        echo "$test_containers" | xargs -r docker rm -f 2>/dev/null || true
    fi
    
    # Remove test directories if they exist
    if [ -d "$TEST_RESULTS_DIR" ]; then
        print_status "Removing test results directory..."
        rm -rf "$TEST_RESULTS_DIR"
    fi
    
    if [ -d "$TEST_PROJECT_DIR" ]; then
        print_status "Removing test project directory..."
        rm -rf "$TEST_PROJECT_DIR"
    fi
    
    # Optional: Clean up Docker system (uncomment if you want aggressive cleanup)
    # print_status "Cleaning up Docker system..."
    # docker system prune -f 2>/dev/null || true
    
    print_success "Cleanup completed - all test containers stopped and removed"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --use-dockerhub-images    Use pre-built images from DockerHub (default: true)"
    echo "  --build-local            Build all images locally instead of pulling from DockerHub"
    echo "  --skip-component-images  Skip building/pulling component images (unused now)"
    echo "  --cleanup                Clean up test directories and exit"
    echo "  --help                   Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  USE_DOCKERHUB_IMAGES     Set to 'false' to build images locally (default: true)"
    echo "  SKIP_COMPONENT_IMAGES    Set to 'true' to skip component images (default: false)"
    echo ""
    echo "Container Management:"
    echo "  - All test containers are automatically labeled for easy identification"
    echo "  - Containers are automatically cleaned up when the script ends"
    echo "  - Use --cleanup to manually clean up containers and test files"
    echo "  - Script handles cleanup on interruption (Ctrl+C)"
}

# Main execution
main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --use-dockerhub-images)
                USE_DOCKERHUB_IMAGES=true
                shift
                ;;
            --build-local)
                USE_DOCKERHUB_IMAGES=false
                shift
                ;;
            --skip-component-images)
                SKIP_COMPONENT_IMAGES=true
                shift
                ;;
            --cleanup)
                cleanup
                exit 0
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    print_status "Starting TI-Toolbox loader test process..."
    print_status "Project root: $PROJECT_ROOT"
    print_status "Use DockerHub images: $USE_DOCKERHUB_IMAGES"
    echo ""
    
    # Step 1: Check Docker
    print_step "1" "Docker Environment Check"
    check_docker
    
    # Step 1.5: Clean up any existing test containers
    cleanup_existing_containers
    
    # Step 2: Prepare component images
    print_step "2" "Component Images Preparation"
    if [ "$SKIP_COMPONENT_IMAGES" = "false" ]; then
        prepare_component_images
    else
        print_warning "Skipping component images preparation"
    fi
    
    # Step 3: Build CI runner
    print_step "3" "CI Runner Image Build"
    build_ci_runner
    
    # Step 4: Setup test directories
    print_step "4" "Test Environment Setup"
    setup_test_directories
    
    # Step 5: Run unit tests
    print_step "5" "Unit Tests Execution"
    run_analyzer_tests
    run_simulator_tests
    run_flex_search_tests
    
    # Step 6: Setup test project directory
    print_step "6" "Test Project Setup"
    setup_test_project
    
    # Step 7: Run integration tests
    print_step "7" "Integration Tests Execution"
    run_simulator_integration
    run_analyzer_integration
    run_bats_tests
    
    # Step 8: Display results
    print_step "8" "Results Summary"
    display_results_summary
    
    print_success "All tests completed successfully!"
    echo ""
    print_status "Test artifacts are available in: $TEST_RESULTS_DIR"
    print_status "Test project directory: $TEST_PROJECT_DIR"
    
    # Clean up containers and temporary files
    cleanup
}

# Trap to handle script interruption
trap 'print_error "Script interrupted. Cleaning up..."; cleanup; exit 1' INT TERM

# Run main function
main "$@"
