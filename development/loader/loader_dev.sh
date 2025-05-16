#!/bin/bash

# Set script directory
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

# Default paths file
DEFAULT_PATHS_FILE="$SCRIPT_DIR/.default_paths.dev"

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

    if [[ -d "$LOCAL_PROJECT_DIR" ]]; then
      echo "Project directory found."
      break
    else
      echo "Invalid directory. Please provide a valid path."
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

# Function to get version from version.py
get_version() {
    local version_file="$SCRIPT_DIR/../../version.py"
    if [ -f "$version_file" ]; then
        # Extract version using grep and sed
        grep "__version__" "$version_file" | sed 's/.*"\(.*\)".*/\1/'
    else
        echo "Error: version.py not found at $version_file"
        exit 1
    fi
}

# Function to check if project is new and initialize config files
initialize_project_configs() {
  local project_ti_csc_dir="$LOCAL_PROJECT_DIR/ti-csc"
  local project_config_dir="$project_ti_csc_dir/config"
  local new_project_configs_dir="$SCRIPT_DIR/../../new_project/configs"
  local is_new_project=false

  # Check if ti-csc directory exists
  if [ ! -d "$project_ti_csc_dir" ]; then
    echo "Creating new project structure..."
    mkdir -p "$project_config_dir"
    is_new_project=true
  elif [ ! -d "$project_config_dir" ]; then
    echo "Creating config directory..."
    mkdir -p "$project_config_dir"
    is_new_project=true
  fi

  # If it's a new project, copy config files
  if [ "$is_new_project" = true ]; then
    echo "Initializing new project with default configs..."
    # Ensure source directory exists
    if [ ! -d "$new_project_configs_dir" ]; then
      echo "Error: Default configs directory not found at $new_project_configs_dir"
      return 1
    fi
    
    # Copy each config file individually and verify, but only if it doesn't exist
    for config_file in "$new_project_configs_dir"/*.json; do
      if [ -f "$config_file" ]; then
        filename=$(basename "$config_file")
        target_file="$project_config_dir/$filename"
        
        # Only copy if the file doesn't exist
        if [ ! -f "$target_file" ]; then
          cp "$config_file" "$target_file"
          if [ $? -eq 0 ]; then
            echo "Copied $filename to $project_config_dir"
          else
            echo "Error: Failed to copy $filename"
            return 1
          fi
        else
          echo "Config file $filename already exists, skipping..."
        fi
      fi
    done
    
    # Set proper permissions
    chmod -R 755 "$project_config_dir"
    echo "Default config files copied to $project_config_dir"

    # Create .ti-csc-info directory and initialize project status
    local info_dir="$LOCAL_PROJECT_DIR/.ti-csc-info"
    mkdir -p "$info_dir"
    
    # Create initial project status file with empty structure
    cat > "$info_dir/project_status.json" << EOF
{
  "project_created": "",
  "last_updated": "",
  "config_created": false,
  "user_preferences": {
    "show_welcome": true
  },
  "project_metadata": {
    "name": "",
    "path": "",
    "version": ""
  }
}
EOF

    # Set proper permissions for the info directory
    chmod -R 755 "$info_dir"
    echo "Project status initialized in $info_dir"
  fi

  # Return the new project status
  echo "$is_new_project"
}

# Function to write project status
write_project_status() {
  INFO_DIR="$LOCAL_PROJECT_DIR/.ti-csc-info"
  STATUS_FILE="$INFO_DIR/project_status.json"
  mkdir -p "$INFO_DIR"

  # Check if project is new and initialize configs
  IS_NEW_PROJECT=$(initialize_project_configs)

  # If it's not a new project, just update the last_updated timestamp
  if [ "$IS_NEW_PROJECT" = false ]; then
    if [ -f "$STATUS_FILE" ]; then
      # Update last_updated timestamp
      sed -i.tmp "s/\"last_updated\": \".*\"/\"last_updated\": \"$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")\"/" "$STATUS_FILE"
      rm -f "${STATUS_FILE}.tmp"
    fi
  fi
}

# Function to write system info to a hidden folder in the user's project directory
write_system_info() {
  INFO_DIR="$LOCAL_PROJECT_DIR/.ti-csc-info"
  INFO_FILE="$INFO_DIR/system_info.txt"
  mkdir -p "$INFO_DIR"

  echo "# TI-CSC System Info" > "$INFO_FILE"
  echo "Date: $(date)" >> "$INFO_FILE"
  echo "User: $(whoami)" >> "$INFO_FILE"
  echo "Host: $(hostname)" >> "$INFO_FILE"
  echo "OS: $(uname -a)" >> "$INFO_FILE"
  echo "" >> "$INFO_FILE"
  echo "## Disk Space (project dir)" >> "$INFO_FILE"
  df -h "$LOCAL_PROJECT_DIR" >> "$INFO_FILE"
  echo "" >> "$INFO_FILE"
  echo "## Docker Version" >> "$INFO_FILE"
  if command -v docker &>/dev/null; then
    docker --version >> "$INFO_FILE"
    echo "" >> "$INFO_FILE"
    echo "## Docker Resource Allocation" >> "$INFO_FILE"
    docker info --format 'CPUs: {{.NCPU}}\nMemory: {{.MemTotal}} bytes' >> "$INFO_FILE"
  else
    echo "Docker not found" >> "$INFO_FILE"
  fi
  echo "" >> "$INFO_FILE"
  echo "## DISPLAY" >> "$INFO_FILE"
  echo "$DISPLAY" >> "$INFO_FILE"
  echo "" >> "$INFO_FILE"
  echo "## Environment Variables (TI-CSC relevant)" >> "$INFO_FILE"
  env | grep -Ei '^(FSL|FREESURFER|SIMNIBS|PROJECT_DIR|DEV_CODEBASE|SUBJECTS_DIR|FS_LICENSE|FSFAST|MNI|POSSUM|DISPLAY|USER|PATH)=' >> "$INFO_FILE"
  echo "" >> "$INFO_FILE"
  echo "System info written to $INFO_FILE"
}

# Main Script Execution

validate_docker_compose
display_welcome
load_default_paths
get_project_directory
get_dev_codebase_directory
PROJECT_DIR_NAME=$(basename "$LOCAL_PROJECT_DIR")
DEV_CODEBASE_DIR_NAME=$(basename "$DEV_CODEBASE_DIR")
check_docker_resources
initialize_volumes
set_display_env
allow_xhost # Allow X11 connections

# Set up Docker Compose environment variables
export LOCAL_PROJECT_DIR
export PROJECT_DIR_NAME
export DEV_CODEBASE_DIR
export DEV_CODEBASE_DIR_NAME

# Save the paths for next time
save_default_paths

# Write system info and project status to hidden folder in project dir
write_system_info
write_project_status

echo "System info written to $LOCAL_PROJECT_DIR/.ti-csc-info/system_info.txt"
echo "Project status written to $LOCAL_PROJECT_DIR/.ti-csc-info/project_status.json"

run_docker_compose