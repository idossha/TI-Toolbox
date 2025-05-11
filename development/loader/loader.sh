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
        echo "This script only runs on macOS. Aborting."
        exit 1
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
        if [[ "$xquartz_version" > "2.8.0" ]]; then
            echo "Warning: XQuartz version is above 2.8.0. Please downgrade to version 2.7.7 for compatibility."
            exit 1
        fi
    fi
}

# Function to allow connections from network clients
allow_network_clients() {
    defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false
    
    # Check if XQuartz is already running
    if ! pgrep -x "Xquartz" > /dev/null; then
        open -a XQuartz
        sleep 2
    fi
}

# Function to set DISPLAY environment variable based on OS and processor type
set_display_env() {
    if [[ "$(uname -s)" == "Linux" ]]; then
        export DISPLAY=$DISPLAY
    else
        export DISPLAY=:0
        xhost +localhost >/dev/null 2>&1
        xhost +$(hostname) >/dev/null 2>&1
    fi
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
  # Run Docker Compose silently
  docker compose -f "$SCRIPT_DIR/docker-compose.yml" up --build -d >/dev/null 2>&1

  # Wait for containers to initialize
  sleep 3

  # Check if simnibs service is up
  if ! docker compose ps | grep -q "simnibs"; then
    echo "Error: simnibs service is not running. Please check your docker-compose.yml and container logs."
    docker compose logs
    exit 1
  fi

  # Attach to the simnibs container with an interactive terminal
  docker exec -ti simnibs_container bash

  # Stop and remove all containers when done
  docker compose -f "$SCRIPT_DIR/docker-compose.yml" down >/dev/null 2>&1

  # Revert X server access permissions
  xhost -local:root >/dev/null 2>&1
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
PROJECT_DIR_NAME=$(basename "$LOCAL_PROJECT_DIR")

# Set up Docker Compose environment variables
export LOCAL_PROJECT_DIR
export PROJECT_DIR_NAME

# Save the paths for next time
save_default_paths

set_display_env

run_docker_compose 