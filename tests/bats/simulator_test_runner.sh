#!/bin/bash

# Test runner for simulator.sh that can pass arrays of inputs and run real simulations
# This script runs the actual simulator.sh with provided inputs on existing project directory

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values - use existing project directory
PROJECT_DIR="/mnt/test_projectdir"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIMULATOR_SCRIPT="$SCRIPT_DIR/../../CLI/simulator.sh"

# Ensure simulator script exists
if [ ! -f "$SIMULATOR_SCRIPT" ]; then
    echo -e "${RED}Error: Simulator script not found at: $SIMULATOR_SCRIPT${NC}"
    echo "Please ensure the simulator.sh script exists in the CLI directory"
    exit 1
fi

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -p, --project-dir DIR     Set project directory (default: /mnt/test_projectdir)"
    echo "  -s, --simulator PATH      Path to simulator.sh (default: ../../CLI/simulator.sh)"
    echo "  -i, --inputs ARRAY        Space-separated list of inputs"
    echo "  -e, --env-file FILE       File containing environment variables"
    echo "  -d, --direct-mode         Run in direct mode with environment variables"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Interactive mode with input array (space-separated)"
    echo "  $0 -i '1 1 1 U 0 1 1 rect 50,50 5 2.0 y'"
    echo ""
    echo "  # Direct mode with environment variables"
    echo "  $0 -d -e test_env.conf"
    echo ""
    echo "  # Custom project directory"
    echo "  $0 -p /path/to/project -i '1 1 1 U 0 1 1'"
}

# Function to verify project directory exists
verify_project_directory() {
    echo -e "${CYAN}Verifying project directory exists...${NC}"
    
    if [ ! -d "$PROJECT_DIR" ]; then
        echo -e "${RED}Error: Project directory not found at: $PROJECT_DIR${NC}"
        echo "Please ensure the project directory exists and contains the required structure"
        exit 1
    fi
    
    # Check for basic BIDS structure
    if [ ! -d "$PROJECT_DIR/derivatives" ]; then
        echo -e "${YELLOW}Warning: derivatives directory not found in project${NC}"
    fi
    
    echo -e "${GREEN}Project directory verified: $PROJECT_DIR${NC}"
}

# Function to run interactive mode with input array
run_interactive_mode() {
    local inputs="$1"
    echo -e "${CYAN}Running interactive mode with inputs: $inputs${NC}"
    
    # Convert space-separated inputs to newline-separated
    # This allows comma-separated values like "50,50" to be preserved
    local input_sequence=$(echo "$inputs" | tr ' ' '\n')
    
    # Set environment variable for project directory
    export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")
    
    # Run the simulator with the input sequence
    echo "$input_sequence" | timeout 300s "$SIMULATOR_SCRIPT"
    local exit_code=$?
    
    if [ $exit_code -eq 124 ]; then
        echo -e "${YELLOW}Simulation timed out after 5 minutes${NC}"
        return 1
    elif [ $exit_code -ne 0 ]; then
        echo -e "${RED}Simulation failed with exit code: $exit_code${NC}"
        return 1
    else
        echo -e "${GREEN}Simulation completed successfully${NC}"
        return 0
    fi
}

# Function to run direct mode with environment variables
run_direct_mode() {
    local env_file="$1"
    echo -e "${CYAN}Running direct mode${NC}"
    
    # Load environment variables from file if provided
    if [ -n "$env_file" ] && [ -f "$env_file" ]; then
        echo -e "${CYAN}Loading environment from: $env_file${NC}"
        source "$env_file"
    fi
    
    # Set default environment variables if not set
    export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")
    export SUBJECT_CHOICES="${SUBJECT_CHOICES:-001}"
    export SIM_TYPE="${SIM_TYPE:-1}"
    export SIMULATION_FRAMEWORK="${SIMULATION_FRAMEWORK:-montage}"
    export SIM_MODE="${SIM_MODE:-U}"
    export CONDUCTIVITY="${CONDUCTIVITY:-scalar}"
    export CURRENT="${CURRENT:-0.002,0.002}"
    export ELECTRODE_SHAPE="${ELECTRODE_SHAPE:-rect}"
    export DIMENSIONS="${DIMENSIONS:-50,50}"
    export THICKNESS="${THICKNESS:-5}"
    export SELECTED_MONTAGES="${SELECTED_MONTAGES:-test_montage}"
    export EEG_NETS="${EEG_NETS:-EGI_template.csv}"
    
    # Run the simulator in direct mode
    timeout 300s "$SIMULATOR_SCRIPT" --run-direct
    local exit_code=$?
    
    if [ $exit_code -eq 124 ]; then
        echo -e "${YELLOW}Simulation timed out after 5 minutes${NC}"
        return 1
    elif [ $exit_code -ne 0 ]; then
        echo -e "${RED}Simulation failed with exit code: $exit_code${NC}"
        return 1
    else
        echo -e "${GREEN}Simulation completed successfully${NC}"
        return 0
    fi
}

# Function to create example environment file
create_example_env() {
    local env_file="$1"
    echo -e "${CYAN}Creating example environment file: $env_file${NC}"
    
    cat > "$env_file" << 'EOF'
# Example environment file for simulator testing
export PROJECT_DIR_NAME="test_projectdir"
export SUBJECT_CHOICES="001"
export SIM_TYPE="1"
export SIMULATION_FRAMEWORK="montage"
export SIM_MODE="U"
export CONDUCTIVITY="scalar"
export CURRENT="0.002,0.002"
export ELECTRODE_SHAPE="rect"
export DIMENSIONS="50,50"
export THICKNESS="5"
export SELECTED_MONTAGES="test_montage"
export EEG_NETS="EGI_template.csv"
EOF
    
    echo -e "${GREEN}Example environment file created${NC}"
}


# Parse command line arguments
INPUTS=""
ENV_FILE=""
DIRECT_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--project-dir)
            PROJECT_DIR="$2"
            PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")
            shift 2
            ;;
        -s|--simulator)
            SIMULATOR_SCRIPT="$2"
            shift 2
            ;;
        -i|--inputs)
            INPUTS="$2"
            shift 2
            ;;
        -e|--env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        -d|--direct-mode)
            DIRECT_MODE=true
            shift
            ;;
        --create-example-env)
            create_example_env "${2:-example.env}"
            exit 0
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_usage
            exit 1
            ;;
    esac
done

# Set up environment variables
export PROJECT_DIR_NAME=$(basename "$PROJECT_DIR")
export PROJECT_DIR

# Check if simulator script exists
if [ ! -f "$SIMULATOR_SCRIPT" ]; then
    echo -e "${RED}Error: Simulator script not found at: $SIMULATOR_SCRIPT${NC}"
    exit 1
fi

# Verify project directory exists
verify_project_directory

# Run the appropriate mode
if [ "$DIRECT_MODE" = true ]; then
    run_direct_mode "$ENV_FILE"
    EXIT_CODE=$?
else
    if [ -z "$INPUTS" ]; then
        echo -e "${RED}Error: No inputs provided. Use -i option or -d for direct mode${NC}"
        show_usage
        exit 1
    fi
    run_interactive_mode "$INPUTS"
    EXIT_CODE=$?
fi

exit $EXIT_CODE
