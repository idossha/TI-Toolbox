#!/bin/bash

# Set script directory
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

# Default paths file
DEFAULT_PATHS_FILE="$SCRIPT_DIR/.default_paths.user"

# Function to load default paths
load_default_paths() {
  if [[ -f "$DEFAULT_PATHS_FILE" ]]; then
    source "$DEFAULT_PATHS_FILE"
  fi
}

# Function to save default paths
save_default_paths() {
    echo "LOCAL_PROJECT_DIR=\"$LOCAL_PROJECT_DIR\"" > "$DEFAULT_PATHS_FILE"
}

# Function to validate and prompt for the project directory
get_project_directory() {
  while true; do
    if [[ -n "$LOCAL_PROJECT_DIR" ]]; then
      echo "Current project directory: $LOCAL_PROJECT_DIR"
      echo "Press Enter to use this directory or enter a new path:"
      read -r new_path
      if [[ -z "$new_path" ]]; then
        break
      else
        LOCAL_PROJECT_DIR="$new_path"
      fi
    else
      echo "Give path to local project dir:"
      read -r LOCAL_PROJECT_DIR
    fi

    # Check if directory exists
    if [[ -d "$LOCAL_PROJECT_DIR" ]]; then
      # Check if we have write permissions
      if [[ ! -w "$LOCAL_PROJECT_DIR" ]]; then
        echo "Warning: No write permissions in directory $LOCAL_PROJECT_DIR"
        echo "The container may not function properly without write access."
        echo "Do you want to continue anyway? (y/n)"
        read -r response
        if [[ "$response" != "y" ]]; then
          continue
        fi
      fi
      break
    else
      echo "Directory does not exist: $LOCAL_PROJECT_DIR"
      echo "Please provide an existing directory path."
    fi
  done
}

# Function to check for macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        return 1
    fi
}

# Function to check XQuartz version
check_xquartz_version() {
    XQUARTZ_APP="/Applications/Utilities/XQuartz.app"
    if [ ! -d "$XQUARTZ_APP" ]; then
        return 1
    else
        xquartz_version=$(mdls -name kMDItemVersion "$XQUARTZ_APP" | awk -F'"' '{print $2}')
        if [[ "$xquartz_version" > "2.8.0" ]]; then
            return 1
        fi
    fi
    return 0
}

# Function to allow connections from network clients
allow_network_clients() {
    defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false >/dev/null 2>&1
    
    # Check if XQuartz is already running
    if ! pgrep -x "Xquartz" > /dev/null; then
        open -a XQuartz
        sleep 2
    fi
}

# Function to get the IP address of the host machine
get_host_ip() {
  case "$(uname -s)" in
  Darwin)
    # Get the local IP address on macOS
    HOST_IP=$(ifconfig en0 | grep inet | awk '$1=="inet" {print $2}')
    ;;
  Linux)
    # On Linux, we don't need to calculate HOST_IP for DISPLAY
    HOST_IP=""
    ;;
  MINGW*|MSYS*|CYGWIN*)
    # On Windows, get the host IP from WSL
    HOST_IP=$(powershell.exe -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*' -and $_.InterfaceAlias -notlike '*vEthernet*'} | Select-Object -First 1).IPAddress" | tr -d '\r\n')
    # If that fails, try alternative method
    if [[ -z "$HOST_IP" ]]; then
      HOST_IP=$(hostname -I | awk '{print $1}')
    fi
    # If still empty, use default
    if [[ -z "$HOST_IP" ]]; then
      HOST_IP="host.docker.internal"
    fi
    ;;
  *)
    echo "Unsupported OS. Please use macOS, Linux, or Windows."
    exit 1
    ;;
  esac
}

# Function to set DISPLAY environment variable based on OS
set_display_env() {
  case "$(uname -s)" in
  Linux)
    # If Linux, use the existing DISPLAY
    export DISPLAY=${DISPLAY:-:0}
    ;;
  Darwin)
    # For macOS, we need IP-based DISPLAY for the container
    get_host_ip
    export DISPLAY="$HOST_IP:0"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    # For Windows (Git Bash, MSYS2, Cygwin)
    get_host_ip
    export DISPLAY="$HOST_IP:0.0"
    ;;
  *)
    echo "Unsupported OS for X11 display configuration."
    exit 1
    ;;
  esac
}

# Function to allow connections from XQuartz or X11
allow_xhost() {
  case "$(uname -s)" in
  Linux)
    # Allow connections for Linux
    if command -v xhost >/dev/null 2>&1; then
      xhost +local:root >/dev/null 2>&1
      xhost +local:docker >/dev/null 2>&1
    fi
    ;;
  Darwin)
    # For macOS, allow both localhost and the specific IP for Docker
    if command -v xhost >/dev/null 2>&1; then
      xhost +localhost >/dev/null 2>&1
      xhost +$(hostname) >/dev/null 2>&1
      
      # Allow the specific IP that Docker will use
      if [ -n "$HOST_IP" ]; then
        xhost + "$HOST_IP" >/dev/null 2>&1
      fi
    fi
    ;;
  MINGW*|MSYS*|CYGWIN*)
    # Windows doesn't have xhost in Git Bash
    ;;
  esac
}

# Function to validate docker-compose.yml existence
validate_docker_compose() {
  if [[ ! -f "$SCRIPT_DIR/docker-compose.yml" ]]; then
    echo "Error: docker-compose.yml not found in $SCRIPT_DIR. Please make sure the file is present."
    exit 1
  fi
}

# Function to display welcome message
display_welcome() {
  echo "Welcome to the TI-Toolbox from the Center for Sleep and Consciousness"
  echo ""
  echo "#####################################################################"
  echo ""
}

# Function to ensure required Docker volumes exist
ensure_docker_volumes() {
  local volumes=( "ti-toolbox_freesurfer_data")
  
  for volume in "${volumes[@]}"; do
    if ! docker volume inspect "$volume" >/dev/null 2>&1; then
      docker volume create "$volume" >/dev/null 2>&1
    fi
  done
}

# Function to prompt for interactive mode
prompt_interactive_mode() {
  echo ""
  echo "Choose mode:"
  echo "  1) Interactive mode (command line access)"
  echo "  2) GUI mode (launch GUI only)"
  echo "  3) Debug/Test mode (run diagnostics)"
  echo ""
  while true; do
    read -p "Enter your choice (1, 2, or 3): " choice
    case $choice in
      1)
        export INTERACTIVE_MODE=true
        export DEBUG_MODE=false
        break
        ;;
      2)
        export INTERACTIVE_MODE=false
        export DEBUG_MODE=false
        break
        ;;
      3)
        export INTERACTIVE_MODE=false
        export DEBUG_MODE=true
        prompt_debug_tests
        break
        ;;
      *)
        echo "Invalid choice. Please enter 1, 2, or 3."
        ;;
    esac
  done
}

# Function to prompt for which debug/test to run
prompt_debug_tests() {
  echo ""
  echo "Available debug/test scripts:"
  echo "  1) Environment diagnostics (debug_env.sh)"
  echo "  2) FreeSurfer setup test (test_entrypoint.sh)"
  echo "  3) Both tests"
  echo ""
  while true; do
    read -p "Enter your choice (1, 2, or 3): " test_choice
    case $test_choice in
      1)
        export DEBUG_TEST_SCRIPT="debug_env.sh"
        break
        ;;
      2)
        export DEBUG_TEST_SCRIPT="test_entrypoint.sh"
        break
        ;;
      3)
        export DEBUG_TEST_SCRIPT="all"
        break
        ;;
      *)
        echo "Invalid choice. Please enter 1, 2, or 3."
        ;;
    esac
  done
}

# Function to run Docker Compose and attach to simnibs container
run_docker_compose() {
  # Ensure volumes exist
  ensure_docker_volumes

  # Set HOME environment variable for .Xauthority access
  export HOME=${HOME:-$USERPROFILE}

  # Check if required images exist, pull only if missing
  local images_needed=()
  
  # Extract image names from docker-compose.yml
  local compose_images=$(grep -E '^\s+image:' "$SCRIPT_DIR/docker-compose.yml" | awk '{print $2}')
  
  # Check each required image
  while IFS= read -r image; do
    if [ -n "$image" ]; then
      if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${image}$"; then
        images_needed+=("$image")
      fi
    fi
  done <<< "$compose_images"
  
  # Pull only if images are missing
  if [ ${#images_needed[@]} -gt 0 ]; then
    echo "Pulling required Docker images..."
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" pull
  fi

  # Set host machine timezone for notes and logging
  export TZ="$(get_host_timezone)"

  # Run Docker Compose
  echo "Starting services..."
  docker compose -f "$SCRIPT_DIR/docker-compose.yml" up --build -d

  # Wait for containers to initialize
  echo "Waiting for services to initialize..."
  sleep 3

  # Check if simnibs service is up
  if ! docker compose ps | grep -q "simnibs"; then
    echo "Error: simnibs service is not running. Please check your docker-compose.yml and container logs."
    docker compose logs
    exit 1
  fi

  # Setup example data if this is a new project
  if [ "${NEEDS_EXAMPLE_DATA:-false}" = "true" ]; then
    setup_example_data_in_container
  fi

  # Handle interactive vs GUI mode vs debug/test mode
  if [ "${DEBUG_MODE:-false}" = true ]; then
    # Copy debug/test scripts to container
    echo "Setting up debug/test scripts..."
    
    if [ "$DEBUG_TEST_SCRIPT" = "debug_env.sh" ] || [ "$DEBUG_TEST_SCRIPT" = "all" ]; then
      if [ -f "$SCRIPT_DIR/debug_env.sh" ]; then
        docker cp "$SCRIPT_DIR/debug_env.sh" simnibs_container:/tmp/debug_env.sh
        docker exec simnibs_container chmod +x /tmp/debug_env.sh
        echo ""
        echo "=== Running Environment Diagnostics ==="
        docker exec simnibs_container bash /tmp/debug_env.sh
      else
        echo "Warning: debug_env.sh not found"
      fi
    fi
    
    if [ "$DEBUG_TEST_SCRIPT" = "test_entrypoint.sh" ] || [ "$DEBUG_TEST_SCRIPT" = "all" ]; then
      if [ -f "$SCRIPT_DIR/test_entrypoint.sh" ]; then
        docker cp "$SCRIPT_DIR/test_entrypoint.sh" simnibs_container:/tmp/test_entrypoint.sh
        docker exec simnibs_container chmod +x /tmp/test_entrypoint.sh
        echo ""
        echo "=== Running FreeSurfer Setup Test ==="
        docker exec simnibs_container bash /tmp/test_entrypoint.sh
      else
        echo "Warning: test_entrypoint.sh not found"
      fi
    fi
    
    # After tests, offer interactive shell
    echo ""
    read -p "Tests complete. Enter interactive shell? (y/n): " shell_choice
    if [ "$shell_choice" = "y" ]; then
      docker exec -ti simnibs_container bash
    fi
  elif [ "$INTERACTIVE_MODE" = true ]; then
    # Attach to the simnibs container with an interactive terminal
    docker exec -ti simnibs_container bash
  else
    # Launch GUI mode
    echo "Launching GUI..."
    docker exec simnibs_container GUI
    
    # Keep the script running and wait for user to press Enter to stop
    echo ""
    echo "GUI is running. Press Enter to stop the container..."
    read -r
  fi

  # Stop and remove all containers when done
  docker compose -f "$SCRIPT_DIR/docker-compose.yml" down >/dev/null 2>&1
  # Stop and remove all containers when done

  # Revert X server access permissions
  case "$(uname -s)" in
  Linux|Darwin)
    if command -v xhost >/dev/null 2>&1; then
      xhost -local:root >/dev/null 2>&1
      xhost -local:docker >/dev/null 2>&1
    fi
    ;;
  esac
}

# Get current timezone from host machine (cross-platform)
get_host_timezone() {
  # Try different methods to get timezone name
  if command -v timedatectl >/dev/null 2>&1; then
    # Linux with systemd
    timedatectl show --property=Timezone --value 2>/dev/null || echo "UTC"
  elif [ -L /etc/localtime ]; then
    # macOS and some Linux systems - localtime is a symlink
    timezone_path=$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')
    echo "${timezone_path:-UTC}"
  elif command -v systemsetup >/dev/null 2>&1; then
    # macOS alternative
    systemsetup -gettimezone 2>/dev/null | sed 's/Time Zone: //' || echo "UTC"
  else
    # Fallback - try to get from date command
    date +%Z 2>/dev/null || echo "UTC"
  fi
}

# Get current timestamp from host machine (cross-platform)
get_host_timestamp() {
  # Use date command which works on all Unix-like systems and Git Bash
  # Format: Thu Oct 30 13:57:36 CDT 2025
  date
}

# ============================================================================
# Host-side project initialization functions
# ============================================================================

# Function to check if project is new and needs initialization
check_if_new_project() {
  local project_config_dir="$LOCAL_PROJECT_DIR/code/ti-toolbox/config"
  
  if [ ! -d "$project_config_dir" ]; then
    return 0  # New project
  else
    return 1  # Existing project
  fi
}

# Function to create hidden files cross-platform
create_hidden_file() {
  local file_path="$1"
  local content="$2"
  
  if [ -n "$content" ]; then
    echo "$content" > "$file_path"
  else
    touch "$file_path"
  fi
  
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      attrib +h "$file_path" >/dev/null 2>&1
      ;;
    *)
      # Unix-like (macOS/Linux) - files are hidden if they start with a dot
      ;;
  esac
}

# Function to initialize BIDS README file in the project root
initialize_readme() {
  local readme_file="$LOCAL_PROJECT_DIR/README"
  
  if [ -f "$readme_file" ]; then
    return 0
  fi

  local project_name="$PROJECT_DIR_NAME"

  cat > "$readme_file" << 'EOF'
# PROJECT_NAME_PLACEHOLDER

This is a BIDS-compliant neuroimaging dataset generated by TI-Toolbox for temporal interference (TI) stimulation modeling and analysis.

## Overview

This project contains structural MRI data and derivatives for simulating and analyzing temporal interference electric field patterns in the brain.

## Dataset Structure

- `sourcedata/` - Raw DICOM source files
- `sub-*/` - Subject-level BIDS-formatted neuroimaging data (NIfTI files)
- `derivatives/` - Processed data and analysis results
  - `freesurfer/` - FreeSurfer anatomical segmentation and surface reconstructions
  - `SimNIBS/` - SimNIBS head models and electric field simulations
  - `ti-toolbox/` - TI-Toolbox simulation results and analyses

## Software

Data processing and simulations were performed using:
- **TI-Toolbox** - Temporal interference modeling pipeline
- **FreeSurfer** - Cortical reconstruction and volumetric segmentation
- **SimNIBS** - Finite element modeling for electric field simulations

## More Information

For more information about TI-Toolbox, visit:
- GitHub: https://github.com/idossha/TI-Toolbox
- Documentation: https://idossha.github.io/TI-toolbox/

## BIDS Compliance

This dataset follows the Brain Imaging Data Structure (BIDS) specification for organizing and describing neuroimaging data. For more information about BIDS, visit: https://bids.neuroimaging.io/
EOF

  # Replace placeholder with actual project name
  if [[ "$(uname -s)" == "Darwin" ]]; then
    sed -i '' "s/PROJECT_NAME_PLACEHOLDER/$project_name/" "$readme_file"
  else
    sed -i "s/PROJECT_NAME_PLACEHOLDER/$project_name/" "$readme_file"
  fi
}

# Function to setup example data for new projects
setup_example_data_if_new() {
  echo "═══════════════════════════════════════════════════════"
  echo "DEBUG: setup_example_data_if_new() called"
  echo "═══════════════════════════════════════════════════════"
  
  local toolbox_root="$SCRIPT_DIR/../.."
  local example_data_manager="$toolbox_root/ti-toolbox/new_project/example_data_manager.py"
  
  echo "DEBUG: SCRIPT_DIR = $SCRIPT_DIR"
  echo "DEBUG: toolbox_root = $toolbox_root"
  echo "DEBUG: example_data_manager = $example_data_manager"
  echo "DEBUG: LOCAL_PROJECT_DIR = $LOCAL_PROJECT_DIR"
  
  # Check if the example data manager exists
  if [ ! -f "$example_data_manager" ]; then
    echo "ERROR: Example data manager not found at $example_data_manager"
    echo "DEBUG: Listing directory contents:"
    ls -la "$toolbox_root/ti-toolbox/new_project/" 2>&1 || echo "Directory does not exist"
    return 1
  fi
  
  echo "DEBUG: ✓ Example data manager file found"
  
  # Check if Python is available (in dev mode, we're on host, not in Docker)
  if command -v python3 >/dev/null 2>&1; then
    echo "DEBUG: ✓ Python3 found at: $(which python3)"
    echo "DEBUG: Python3 version: $(python3 --version)"
    echo "Setting up example data for new project..."
    echo "DEBUG: Running command: python3 $example_data_manager $toolbox_root $LOCAL_PROJECT_DIR"
    
    # Run the example data manager with verbose output
    if python3 "$example_data_manager" "$toolbox_root" "$LOCAL_PROJECT_DIR" 2>&1; then
      echo "✓ Example data setup completed successfully"
    else
      local exit_code=$?
      echo "ERROR: Example data setup failed with exit code: $exit_code"
      echo "Continuing with project initialization..."
    fi
  else
    echo "ERROR: Python3 not available in PATH"
    echo "DEBUG: Current PATH = $PATH"
    echo "Skipping example data setup"
  fi
  
  echo "═══════════════════════════════════════════════════════"
  echo "DEBUG: setup_example_data_if_new() completed"
  echo "═══════════════════════════════════════════════════════"
}




# Function to initialize root dataset_description.json
initialize_dataset_description() {
  local dataset_file="$LOCAL_PROJECT_DIR/dataset_description.json"
  
  if [ -f "$dataset_file" ]; then
    return 0
  fi

  local project_name="$PROJECT_DIR_NAME"
  
  cat > "$dataset_file" << EOF
{
  "Name": "$project_name",
  "BIDSVersion": "1.6.0",
  "DatasetType": "raw",
  "License": "",
  "Authors": [],
  "Acknowledgements": "",
  "HowToAcknowledge": "",
  "Funding": [],
  "ReferencesAndLinks": [
    "https://github.com/idossha/TI-Toolbox"
  ],
  "DatasetDOI": ""
}
EOF
}

# Function to initialize derivative dataset_description.json files
initialize_derivative_dataset_description() {
  local derivative_name="$1"
  local derivative_dir="$LOCAL_PROJECT_DIR/derivatives/$derivative_name"
  local dataset_file="$derivative_dir/dataset_description.json"
  
  if [ -f "$dataset_file" ]; then
    return 0
  fi

  mkdir -p "$derivative_dir"

  local project_name="$PROJECT_DIR_NAME"
  local current_date=$(date +"%Y-%m-%d")
  
  cat > "$dataset_file" << EOF
{
  "Name": "$derivative_name derivatives",
  "BIDSVersion": "1.6.0",
  "DatasetType": "derivative",
  "GeneratedBy": [
    {
      "Name": "$derivative_name"
    }
  ],
  "SourceDatasets": [
    {
      "URI": "bids:$project_name@$current_date",
      "Version": "1.0.0"
    }
  ],
  "DatasetLinks": {
    "$project_name": "../../"
  }
}
EOF
}

# Function to initialize project status JSON
initialize_project_status() {
  local info_dir="$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
  local status_file="$info_dir/project_status.json"
  
  mkdir -p "$info_dir"
  
  local current_time=$(date -u +"%Y-%m-%dT%H:%M:%S")
  
  cat > "$status_file" << EOF
{
  "project_created": "$current_time",
  "last_updated": "$current_time",
  "config_created": true,
  "example_data_copied": false,
  "user_preferences": {
    "show_welcome": true
  },
  "project_metadata": {
    "name": "$PROJECT_DIR_NAME",
    "path": "$LOCAL_PROJECT_DIR",
    "version": "unknown"
  }
}
EOF

  create_hidden_file "$status_file"
}

# Function to setup example data using Docker container
setup_example_data_in_container() {
  local container_name="simnibs_container"
  local container_project_dir="/mnt/$PROJECT_DIR_NAME"
  
  echo "Setting up example data..."
  
  # Wait for container to be ready
  local max_wait=30
  local wait_count=0
  while ! docker ps | grep -q "$container_name"; do
    sleep 1
    wait_count=$((wait_count + 1))
    if [ $wait_count -ge $max_wait ]; then
      echo "  ⚠ Container not ready, skipping example data setup"
      return 1
    fi
  done
  
  # Check if example_data_manager.py exists in container
  if docker exec "$container_name" test -f "/ti-toolbox/new_project/example_data_manager.py"; then
    # Run the example data manager inside the container
    if docker exec "$container_name" python3 /ti-toolbox/new_project/example_data_manager.py /ti-toolbox/../.. "$container_project_dir" >/dev/null 2>&1; then
      echo "  ✓ Example data copied successfully"
      return 0
    else
      echo "  ⚠ Example data setup failed (continuing anyway)"
      return 1
    fi
  else
    # Fallback: Direct copy if example_data_manager doesn't exist
    if docker exec "$container_name" test -d "/ti-toolbox/assets/example_data"; then
      docker exec "$container_name" cp -r /ti-toolbox/assets/example_data/* "$container_project_dir/sourcedata/" >/dev/null 2>&1
      echo "  ✓ Example data copied successfully"
      return 0
    else
      echo "  ⚠ Example data not found (skipping)"
      return 1
    fi
  fi
}

# Main initialization function that orchestrates everything
initialize_project_structure() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  New project detected: $PROJECT_DIR_NAME"
  echo "  Initializing BIDS-compliant structure..."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  
  # Create main BIDS directories
  echo "Creating directory structure..."
  mkdir -p "$LOCAL_PROJECT_DIR/code/ti-toolbox/config"
  mkdir -p "$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
  mkdir -p "$LOCAL_PROJECT_DIR/derivatives/freesurfer"
  mkdir -p "$LOCAL_PROJECT_DIR/derivatives/SimNIBS"
  mkdir -p "$LOCAL_PROJECT_DIR/sourcedata"
  echo "  ✓ Directories created"
  
  # Initialize BIDS files
  echo "Creating BIDS metadata files..."
  initialize_readme
  echo "  ✓ README created"
  
  initialize_dataset_description
  echo "  ✓ Root dataset_description.json created"
  
  initialize_derivative_dataset_description "ti-toolbox"
  echo "  ✓ ti-toolbox dataset_description.json created"
  
  initialize_derivative_dataset_description "freesurfer"
  echo "  ✓ freesurfer dataset_description.json created"
  
  initialize_derivative_dataset_description "SimNIBS"
  echo "  ✓ SimNIBS dataset_description.json created"
  
  # Initialize project status
  echo "Creating project configuration..."
  initialize_project_status
  echo "  ✓ Project status file created"
  
  # Create a marker file to indicate initialization was done
  touch "$LOCAL_PROJECT_DIR/code/ti-toolbox/config/.initialized"
  echo "  ✓ Initialization marker created"
  
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  ✓ Project initialization complete!"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  
  # Mark that example data needs to be copied after container starts
  export NEEDS_EXAMPLE_DATA="true"
}

# Main Script Execution
validate_docker_compose
display_welcome

# Check macOS and XQuartz if on macOS
if [[ "$(uname -s)" == "Darwin" ]]; then
    check_xquartz_version >/dev/null 2>&1
    allow_network_clients >/dev/null 2>&1
fi

# Check Windows X server
if [[ "$(uname -s)" =~ ^(MINGW|MSYS|CYGWIN) ]]; then
    echo "Windows detected. Please ensure your X server (VcXsrv/Xming) is running with:"
    echo "  - 'Multiple windows' mode"
    echo "  - 'Disable access control' checked"
    echo "  - Firewall configured to allow X server connections"
    echo ""
    read -p "Press Enter to continue once X server is configured..."
fi

load_default_paths
get_project_directory

# Prompt for interactive mode
prompt_interactive_mode

# Sanitize potential carriage returns from path
LOCAL_PROJECT_DIR=$(printf "%s" "$LOCAL_PROJECT_DIR" | tr -d '\r')

# Set up Docker Compose environment variables
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    # Convert Windows paths to Docker-compatible format
    if [[ "$LOCAL_PROJECT_DIR" =~ ^[A-Za-z]: ]]; then
      DOCKER_PROJECT_DIR="/$(echo "$LOCAL_PROJECT_DIR" | sed 's/://' | sed 's/\\/\//g' | tr '[:upper:]' '[:lower:]')"
    else
      DOCKER_PROJECT_DIR="$LOCAL_PROJECT_DIR"
    fi
    export LOCAL_PROJECT_DIR="$DOCKER_PROJECT_DIR"
    ;;
  *)
    export LOCAL_PROJECT_DIR
    ;;
esac

# Compute and sanitize project dir name
PROJECT_DIR_NAME=$(basename "$LOCAL_PROJECT_DIR")
PROJECT_DIR_NAME=$(printf "%s" "$PROJECT_DIR_NAME" | tr -d '\r')
export PROJECT_DIR_NAME

# Save the paths for next time
save_default_paths

# Check and initialize project if new
if check_if_new_project; then
  initialize_project_structure
fi

set_display_env >/dev/null 2>&1
allow_xhost >/dev/null 2>&1

run_docker_compose 
