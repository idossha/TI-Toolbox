#!/bin/bash

# Set script directory and project root
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
PROJECT_ROOT=$(dirname "$(dirname "$SCRIPT_DIR")")  # This gets three levels up from the script location
cd "$SCRIPT_DIR"

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
    echo "Enter path to your project directory (this will be mounted under /mnt/):"
    read -r LOCAL_PROJECT_DIR

    if [[ -d "$LOCAL_PROJECT_DIR" ]]; then
      echo "Project directory found."
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

# Function to set DISPLAY environment variable based on OS and processor type
set_display_env() {
  echo "Setting DISPLAY environment variable..."

  if [[ "$(uname -s)" == "Linux" ]]; then
    # If Linux, use the existing DISPLAY
    export DISPLAY=$DISPLAY
    echo "Using system's DISPLAY: $DISPLAY"
  else
    # For macOS, dynamically obtain the host IP and set DISPLAY
    get_host_ip # Get the IP address dynamically
    export DISPLAY="$HOST_IP:0"
    echo "DISPLAY set to $DISPLAY"
  fi
}

# Function to allow connections from XQuartz or X11
allow_xhost() {
  echo "Allowing connections from XQuartz or X11..."

  if [[ "$(uname -s)" == "Linux" ]]; then
    # Allow connections for Linux
    xhost +local:root
  else
    # Use the dynamically obtained IP for macOS xhost
    xhost + "$HOST_IP"
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
  # Run Docker Compose
  docker-compose -f "$SCRIPT_DIR/docker-compose.yml" up --build -d

  # Wait for containers to initialize
  sleep 3

  # Check if simnibs service is up
  if ! docker-compose ps | grep -q "simnibs"; then
    echo "Error: simnibs service is not running. Please check your docker-compose.yml and container logs."
    docker-compose logs
    exit 1
  fi

  # Attach to the simnibs container with an interactive terminal
  echo "Attaching to the simnibs_container..."
  docker exec -ti simnibs_container bash

  # Stop and remove all containers when done
  docker-compose -f "$SCRIPT_DIR/docker-compose.yml" down

  # Revert X server access permissions
  xhost -local:root
}

# Main Script Execution

validate_docker_compose
display_welcome
get_project_directory
PROJECT_DIR_NAME=$(basename "$LOCAL_PROJECT_DIR")
check_docker_resources
set_display_env
allow_xhost # Allow X11 connections

# Set up Docker Compose environment variables
export LOCAL_PROJECT_DIR
export PROJECT_DIR_NAME
export PROJECT_ROOT

run_docker_compose
