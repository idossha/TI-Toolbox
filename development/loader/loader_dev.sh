#!/bin/bash

# Set script directory
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

# Default paths file
DEFAULT_PATHS_FILE="$SCRIPT_DIR/.default_paths"

# Function to load default paths
load_default_paths() {
  if [[ -f "$DEFAULT_PATHS_FILE" ]]; then
    source "$DEFAULT_PATHS_FILE"
  fi
}

# Function to save default paths
save_default_paths() {
  echo "LOCAL_PROJECT_DIR=\"$LOCAL_PROJECT_DIR\"" > "$DEFAULT_PATHS_FILE"
  echo "DEV_CODEBASE_DIR=\"$DEV_CODEBASE_DIR\"" >> "$DEFAULT_PATHS_FILE"
}

# Function to initialize required Docker volumes
initialize_volumes() {
  echo "Initializing required Docker volumes..."
  
  # Check and create FSL volume if it doesn't exist
  if ! docker volume inspect ti_csc_fsl_data >/dev/null 2>&1; then
    echo "Creating FSL volume..."
    docker volume create ti_csc_fsl_data
  fi
  
  # Check and create FreeSurfer volume if it doesn't exist
  if ! docker volume inspect ti_csc_freesurfer_data >/dev/null 2>&1; then
    echo "Creating FreeSurfer volume..."
    docker volume create ti_csc_freesurfer_data
  fi
}

# Function to check allocated Docker resources (CPU, memory)
check_docker_resources() {
  echo "Checking Docker resource allocation..."

  if docker info >/dev/null 2>&1; then
    # Get Docker's memory and CPU allocation
    MEMORY=$(docker info --format '{{.MemTotal}}')
    CPU=$(docker info --format '{{.NCPU}}')

    # Convert memory from bytes to GB
    MEMORY_GB=$(echo "scale=2; $MEMORY / (1024^3)" | bc)

    echo "Docker Memory Allocation: ${MEMORY_GB} GB"
    echo "Docker CPU Allocation: $CPU CPUs"
  else
    echo "Docker is not running or not installed. Please start Docker and try again."
    exit 1
  fi
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

# Function to get development codebase directory
get_dev_codebase_directory() {
  while true; do
    if [[ -n "$DEV_CODEBASE_DIR" ]]; then
      echo "Current development codebase directory: $DEV_CODEBASE_DIR"
      echo "Press Enter to use this directory or enter a new path:"
      read -r new_path
      if [[ -z "$new_path" ]]; then
        break
      else
        DEV_CODEBASE_DIR="$new_path"
      fi
    else
      echo "Enter path to development codebase:"
      read -r DEV_CODEBASE_DIR
    fi

    if [[ -d "$DEV_CODEBASE_DIR" ]]; then
      echo "Development codebase directory found."
      break
    else
      echo "Invalid directory. Please provide a valid path."
    fi
  done
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
  *)
    echo "Unsupported OS. Please use macOS or Linux."
    exit 1
    ;;
  esac
  echo "Host IP: $HOST_IP"
}

# Function to check for macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        echo "This script only runs on macOS. Aborting."
        exit 1
    else
        echo "macOS detected. Proceeding..."
    fi
}

# Function to check XQuartz version
check_xquartz_version() {
    XQUARTZ_APP="/Applications/Utilities/XQuartz.app"
    if [ ! -d "$XQUARTZ_APP" ]; then
        echo "XQuartz is not installed. Please install XQuartz 2.7.7."
        exit 1
    else
        xquartz_version=$(mdls -name kMDItemVersion "$XQUARTZ_APP" | awk -F'"' '{print $2}')
        echo "XQuartz version detected: $xquartz_version"
        if [[ "$xquartz_version" > "2.8.0" ]]; then
            echo "Warning: XQuartz version is above 2.8.0. Please downgrade to version 2.7.7 for compatibility."
            exit 1
        else
            echo "XQuartz version is compatible."
        fi
    fi
}

# Function to allow connections from network clients
allow_network_clients() {
    echo "Enabling connections from network clients in XQuartz..."
    defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false
    
    # Check if XQuartz is already running
    if ! pgrep -x "Xquartz" > /dev/null; then
        echo "Starting XQuartz..."
        open -a XQuartz
        sleep 2
    else
        echo "XQuartz is already running."
    fi
}

# Function to set DISPLAY environment variable based on OS and processor type
set_display_env() {
    echo "Setting DISPLAY environment variable..."

    if [[ "$(uname -s)" == "Linux" ]]; then
        # If Linux, use the existing DISPLAY
        export DISPLAY=$DISPLAY
        echo "Using system's DISPLAY: $DISPLAY"
    else
        # For macOS, use the new configuration
        echo "Setting DISPLAY to :0"
        export DISPLAY=:0

        echo "Allowing X11 connections from localhost..."
        xhost +localhost

        echo "Allowing X11 connections from the hostname..."
        xhost +$(hostname)
    fi
}

# Function to allow connections from XQuartz or X11
allow_xhost() {
    echo "Allowing connections from XQuartz or X11..."

    if [[ "$(uname -s)" == "Linux" ]]; then
        # Allow connections for Linux
        xhost +local:root
    else
        # For macOS, we've already set up the connections in set_display_env
        return 0
    fi
}

# Function to validate docker-compose.yml existence
validate_docker_compose() {
  if [[ ! -f "$SCRIPT_DIR/docker-compose.dev.yml" ]]; then
    echo "Error: docker-compose.dev.yml not found in $SCRIPT_DIR. Please make sure the file is present."
    exit 1
  fi
}

# Function to display welcome message
display_welcome() {
  echo " "
  echo "#####################################################################"
  echo "Welcome to the TI toolbox from the Center for Sleep and Consciousness"
  echo "Developed by Ido Haber as a wrapper around Modified SimNIBS"
  echo " "
  echo "Make sure you have XQuartz (on macOS), X11 (on Linux), or Xming/VcXsrv (on Windows) running."
  echo "If you wish to use the optimizer, consider allocating more RAM to Docker."
  echo "#####################################################################"
  echo " "
}

# Function to run Docker Compose and attach to simnibs container
run_docker_compose() {
  # Run Docker Compose
  docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" up --build -d

  # Wait for containers to initialize
  sleep 3

  # Check if simnibs service is up
  if ! docker compose ps | grep -q "simnibs"; then
    echo "Error: simnibs service is not running. Please check your docker-compose.dev.yml and container logs."
    docker compose logs
    exit 1
  fi

  # Attach to the simnibs container with an interactive terminal
  echo "Attaching to the simnibs_container..."
  docker exec -ti simnibs_container bash

  # Stop and remove all containers when done
  docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" down

  # Revert X server access permissions
  xhost -local:root
}

# Function to write system info to a hidden folder in the user's project directory
write_system_info() {
  INFO_DIR="$LOCAL_PROJECT_DIR/.ti-csc-info"
  INFO_FILE="$INFO_DIR/system_info.txt"
  
  # Check if we have write permissions before attempting to create directory
  if [[ ! -w "$LOCAL_PROJECT_DIR" ]]; then
    return 0  # Silently exit if no write permissions
  fi
  
  mkdir -p "$INFO_DIR" 2>/dev/null || return 0  # Silently exit if mkdir fails

  {
    echo "# TI-CSC System Info"
    echo "Date: $(date)"
    echo "User: $(whoami)"
    echo "Host: $(hostname)"
    echo "OS: $(uname -a)"
    echo ""
    echo "## Disk Space (project dir)"
    df -h "$LOCAL_PROJECT_DIR" 2>/dev/null || echo "Unable to get disk space information"
    echo ""
    echo "## Docker Version"
    if command -v docker &>/dev/null; then
      docker --version
      echo ""
      echo "## Docker Resource Allocation"
      docker info --format 'CPUs: {{.NCPU}}\nMemory: {{.MemTotal}} bytes' 2>/dev/null || echo "Unable to get Docker resource information"
    else
      echo "Docker not found"
    fi
    echo ""
    echo "## DISPLAY"
    echo "$DISPLAY"
    echo ""
    echo "## Environment Variables (TI-CSC relevant)"
    env | grep -Ei '^(FSL|FREESURFER|SIMNIBS|PROJECT_DIR|DEV_CODEBASE|SUBJECTS_DIR|FS_LICENSE|FSFAST|MNI|POSSUM|DISPLAY|USER|PATH)=' 2>/dev/null || echo "Unable to get environment variables"
  } > "$INFO_FILE" 2>/dev/null || true  # Silently continue if write fails
}

# Main Script Execution

validate_docker_compose
display_welcome

# Check macOS and XQuartz if on macOS
if [[ "$(uname -s)" == "Darwin" ]]; then
    check_macos
    check_xquartz_version
    allow_network_clients
fi

load_default_paths
get_project_directory
get_dev_codebase_directory
PROJECT_DIR_NAME=$(basename "$LOCAL_PROJECT_DIR")
DEV_CODEBASE_NAME=$(basename "$DEV_CODEBASE_DIR")
check_docker_resources
initialize_volumes
set_display_env
allow_xhost # Allow X11 connections

# Set up Docker Compose environment variables
export LOCAL_PROJECT_DIR
export PROJECT_DIR_NAME
export DEV_CODEBASE_DIR
export DEV_CODEBASE_NAME

# Save the paths for next time
save_default_paths

# Write system info to hidden folder in project dir
write_system_info

run_docker_compose
