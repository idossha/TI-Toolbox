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

# Function to enable directory path autocompletion
setup_path_completion() {
  bind "set completion-ignore-case on"
  bind "TAB:menu-complete"
  bind "set show-all-if-ambiguous on"
  bind "set menu-complete-display-prefix on"
}

# Function to validate and prompt for the project directory
get_project_directory() {
  while true; do
    if [[ -n "$LOCAL_PROJECT_DIR" ]]; then
      echo "Current project directory: $LOCAL_PROJECT_DIR"
      echo "Press Enter to use this directory or enter a new path:"
      read -e -r new_path
      if [[ -z "$new_path" ]]; then
        break
      else
        LOCAL_PROJECT_DIR="$new_path"
      fi
    else
      echo "Give path to local project dir:"
      read -e -r LOCAL_PROJECT_DIR
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
      read -e -r new_path
      if [[ -z "$new_path" ]]; then
        break
      else
        DEV_CODEBASE_DIR="$new_path"
      fi
    else
      echo "Enter path to development codebase:"
      read -e -r DEV_CODEBASE_DIR
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

  # Check if xhost command is available
  if ! command -v xhost >/dev/null 2>&1; then
    echo "Warning: xhost command not found. X11 forwarding may not work properly."
    echo "For Windows/WSL users: Make sure you have an X server (like VcXsrv or Xming) running."
    return 0
  fi

  if [[ "$(uname -s)" == "Linux" ]]; then
    # Allow connections for Linux (only if xhost exists)
    if command -v xhost >/dev/null 2>&1; then
      xhost +local:root
    else
      echo "Note: xhost not found; skipping X11 access relaxation"
    fi
  else
    # Use the dynamically obtained IP for macOS xhost
    if command -v xhost >/dev/null 2>&1; then
      xhost + "$HOST_IP"
    else
      echo "Note: xhost not found; skipping X11 access relaxation"
    fi
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
  # Pull images if they don't exist
  echo "Pulling required Docker images..."
  docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" pull

  # Run Docker Compose
  docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" up --build -d

  # Wait for containers to initialize
  echo "Waiting for services to initialize..."
  sleep 3

  # Check if simnibs service is up
  if ! docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" ps | grep -q "simnibs"; then
    echo "Error: simnibs service is not running. Please check your docker-compose.dev.yml and container logs."
    docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" logs
    exit 1
  fi

  # Attach to the simnibs container with an interactive terminal
  echo "Attaching to the simnibs_container..."
  docker exec -ti simnibs_container bash

  # Stop and remove all containers when done
  docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" down

  # Revert X server access permissions (only if xhost is available)
  if command -v xhost >/dev/null 2>&1; then
    xhost -local:root
  fi
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

# Function to initialize BIDS dataset_description.json in the project root
initialize_dataset_description() {
  local dataset_file="$LOCAL_PROJECT_DIR/dataset_description.json"
  local assets_template="$SCRIPT_DIR/../../assets/dataset_descriptions/root.dataset_description.json"
  local fallback_template="$SCRIPT_DIR/../../new_project/dataset_description.json"

  # If it already exists, skip
  if [ -f "$dataset_file" ]; then
    echo "dataset_description.json already exists in the project. Skipping creation."
    return 0
  fi

  # Ensure project directory exists
  if [ ! -d "$LOCAL_PROJECT_DIR" ]; then
    echo "Error: Project directory $LOCAL_PROJECT_DIR does not exist."
    return 1
  fi

  # Determine project name
  local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"

  # Prefer assets template; fallback to new_project template
  if [ -f "$assets_template" ]; then
    cp "$assets_template" "$dataset_file" || { echo "Error: Failed to copy assets template"; return 1; }
  elif [ -f "$fallback_template" ]; then
    cp "$fallback_template" "$dataset_file" || { echo "Error: Failed to copy fallback template"; return 1; }
  else
    echo "Error: No dataset_description template found in assets or new_project"; return 1
  fi
  
  # Fill in the Name field
  sed -i.tmp "s/\"Name\": \"\"/\"Name\": \"$project_name\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"

  # Basic verification
  if [ -f "$dataset_file" ]; then
    echo "Created $dataset_file with project name: $project_name"
    echo ""
    echo "IMPORTANT: To ensure BIDS compliance, please complete the following fields in your dataset_description.json:"
    echo "  - License: Specify the license for your dataset"
    echo "  - Authors: List contributors to the dataset"
    echo "  - Acknowledgements: Credit individuals or institutions"
    echo "  - HowToAcknowledge: Instructions for citing your dataset"
    echo "  - Funding: Grant numbers or funding sources"
    echo "  - EthicsApprovals: Ethics committee approvals"
    echo "  - ReferencesAndLinks: Publications related to the dataset"
    echo "  - DatasetDOI: DOI if available"
    echo ""
    echo "For detailed guidance on BIDS compliance, visit:"
    echo "https://bids-specification.readthedocs.io/en/stable/modality-agnostic-files.html"
    echo ""
    return 0
  else
    echo "Error: Failed to create $dataset_file"
    return 1
  fi
}

# Function to initialize ti-toolbox derivative dataset_description.json
initialize_ti_toolbox_derivative() {
  local derivatives_dir="$LOCAL_PROJECT_DIR/derivatives"
  local ti_toolbox_dir="$derivatives_dir/ti-toolbox"
  local dataset_file="$ti_toolbox_dir/dataset_description.json"
  local assets_template="$SCRIPT_DIR/../../assets/dataset_descriptions/ti-toolbox.dataset_description.json"

  # If it already exists, skip
  if [ -f "$dataset_file" ]; then
    echo "ti-toolbox derivative dataset_description.json already exists. Skipping creation."
    return 0
  fi

  # Ensure derivatives directory exists
  if [ ! -d "$derivatives_dir" ]; then
    mkdir -p "$derivatives_dir" 2>/dev/null || { echo "Error: Failed to create derivatives directory"; return 1; }
  fi

  # Ensure ti-toolbox directory exists
  if [ ! -d "$ti_toolbox_dir" ]; then
    mkdir -p "$ti_toolbox_dir" 2>/dev/null || { echo "Error: Failed to create ti-toolbox directory"; return 1; }
  fi

  # Check if template exists
  if [ ! -f "$assets_template" ]; then
    echo "Error: ti-toolbox.dataset_description.json template not found at $assets_template"
    return 1
  fi

  # Copy template to derivatives/ti-toolbox/
  if cp "$assets_template" "$dataset_file" 2>/dev/null; then
    # Fill in project-specific information
    local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"
    local current_date=$(date +"%Y-%m-%d")
    
    # Update URI field
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$project_name@$current_date\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"
    
    # Update DatasetLinks field
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$project_name\": \"..\/..\/\"\n  }/" "$dataset_file" && rm -f "${dataset_file}.tmp"
    
    echo "Created ti-toolbox derivative dataset_description.json at $dataset_file"
    return 0
  else
    echo "Error: Failed to create ti-toolbox derivative dataset_description.json"
    return 1
  fi
}

# Function to initialize FreeSurfer derivative dataset_description.json
initialize_freesurfer_derivative() {
  local derivatives_dir="$LOCAL_PROJECT_DIR/derivatives"
  local freesurfer_dir="$derivatives_dir/freesurfer"
  local dataset_file="$freesurfer_dir/dataset_description.json"
  local assets_template="$SCRIPT_DIR/../../assets/dataset_descriptions/freesurfer.dataset_description.json"

  # If it already exists, skip
  if [ -f "$dataset_file" ]; then
    echo "FreeSurfer derivative dataset_description.json already exists. Skipping creation."
    return 0
  fi

  # Ensure derivatives directory exists
  if [ ! -d "$derivatives_dir" ]; then
    mkdir -p "$derivatives_dir" 2>/dev/null || { echo "Error: Failed to create derivatives directory"; return 1; }
  fi

  # Ensure freesurfer directory exists
  if [ ! -d "$freesurfer_dir" ]; then
    mkdir -p "$freesurfer_dir" 2>/dev/null || { echo "Error: Failed to create freesurfer directory"; return 1; }
  fi

  # Check if template exists
  if [ ! -f "$assets_template" ]; then
    echo "Error: freesurfer.dataset_description.json template not found at $assets_template"
    return 1
  fi

  # Copy template to derivatives/freesurfer/
  if cp "$assets_template" "$dataset_file" 2>/dev/null; then
    # Fill in project-specific information
    local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"
    local current_date=$(date +"%Y-%m-%d")
    
    # Update URI field
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$project_name@$current_date\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"
    
    # Update DatasetLinks field
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$project_name\": \"..\/..\/\"\n  }/" "$dataset_file" && rm -f "${dataset_file}.tmp"
    
    echo "Created FreeSurfer derivative dataset_description.json at $dataset_file"
    return 0
  else
    echo "Error: Failed to create FreeSurfer derivative dataset_description.json"
    return 1
  fi
}

# Function to initialize SimNIBS derivative dataset_description.json
initialize_simnibs_derivative() {
  local derivatives_dir="$LOCAL_PROJECT_DIR/derivatives"
  local simnibs_dir="$derivatives_dir/SimNIBS"
  local dataset_file="$simnibs_dir/dataset_description.json"
  local assets_template="$SCRIPT_DIR/../../assets/dataset_descriptions/simnibs.dataset_description.json"

  # If it already exists, skip
  if [ -f "$dataset_file" ]; then
    echo "SimNIBS derivative dataset_description.json already exists. Skipping creation."
    return 0
  fi

  # Ensure derivatives directory exists
  if [ ! -d "$derivatives_dir" ]; then
    mkdir -p "$derivatives_dir" 2>/dev/null || { echo "Error: Failed to create derivatives directory"; return 1; }
  fi

  # Ensure SimNIBS directory exists
  if [ ! -d "$simnibs_dir" ]; then
    mkdir -p "$simnibs_dir" 2>/dev/null || { echo "Error: Failed to create SimNIBS directory"; return 1; }
  fi

  # Check if template exists
  if [ ! -f "$assets_template" ]; then
    echo "Error: simnibs.dataset_description.json template not found at $assets_template"
    return 1
  fi

  # Copy template to derivatives/SimNIBS/
  if cp "$assets_template" "$dataset_file" 2>/dev/null; then
    # Fill in project-specific information
    local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"
    local current_date=$(date +"%Y-%m-%d")
    
    # Update URI field
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$project_name@$current_date\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"
    
    # Update DatasetLinks field
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$project_name\": \"..\/..\/\"\n  }/" "$dataset_file" && rm -f "${dataset_file}.tmp"
    
    echo "Created SimNIBS derivative dataset_description.json at $dataset_file"
    return 0
  else
    echo "Error: Failed to create SimNIBS derivative dataset_description.json"
    return 1
  fi
}

# Function to write system info to a hidden folder in the user's project directory
write_system_info() {
  INFO_DIR="$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
  INFO_FILE="$INFO_DIR/system_info.txt"
  
  # Create directory with error checking
  if ! mkdir -p "$INFO_DIR" 2>/dev/null; then
    echo "Error: Could not create directory $INFO_DIR"
    return 1
  fi

  # Create and write to file with error checking
  if ! {
    echo "# TI-Toolbox System Info"
    echo "Date: $(date)"
    echo "User: $(whoami)"
    echo "Host: $(hostname)"
    echo "OS: $(uname -a)"
    echo ""
    echo "## Disk Space (project dir)"
    df -h "$LOCAL_PROJECT_DIR"
    echo ""
    echo "## Docker Version"
    if command -v docker &>/dev/null; then
      docker --version
      echo ""
      echo "## Docker Resource Allocation"
      docker info --format 'CPUs: {{.NCPU}}\nMemory: {{.MemTotal}} bytes'
      echo ""
      echo "## Docker Volumes"
      docker volume ls --format '{{.Name}}'
    else
      echo "Docker not found"
    fi
    echo ""
    echo "## DISPLAY"
    echo "$DISPLAY"
    echo ""
    echo "## Environment Variables (TI-Toolbox relevant)"
    env | grep -Ei '^(FSL|FREESURFER|SIMNIBS|PROJECT_DIR|DEV_CODEBASE|SUBJECTS_DIR|FS_LICENSE|FSFAST|MNI|POSSUM|DISPLAY|USER|PATH|LD_LIBRARY_PATH|XAPPLRESDIR)='
    echo ""
  } > "$INFO_FILE" 2>/dev/null; then
    echo "Error: Could not write to $INFO_FILE"
    return 1
  fi

  echo "System info written to $INFO_FILE"

  # No need to mirror since we're now using the derivatives location directly
  return 0
}

# Function to write project status
write_project_status() {
  # Set info directory to derivatives location
  INFO_DIR="$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
  STATUS_FILE="$INFO_DIR/project_status.json"
  mkdir -p "$INFO_DIR"

  # Check if project is new and initialize configs
  IS_NEW_PROJECT=$(initialize_project_configs)

  # If it's not a new project, just update the last_updated timestamp
  if [ "$IS_NEW_PROJECT" = false ]; then
    if [ -f "$STATUS_FILE" ]; then
      # Validate JSON and update last_updated; if invalid, back up and recreate
      if command -v jq >/dev/null 2>&1; then
        if ! jq empty "$STATUS_FILE" >/dev/null 2>&1; then
          cp "$STATUS_FILE" "${STATUS_FILE}.bak_$(date +%s)"
          cat > "$STATUS_FILE" << EOF
{
  "project_created": "$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")",
  "last_updated": "$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")",
  "config_created": true,
  "user_preferences": { "show_welcome": true },
  "project_metadata": {
    "name": "$(basename "$LOCAL_PROJECT_DIR")",
    "path": "$(printf "%s" "$LOCAL_PROJECT_DIR" | tr -d '\r')",
    "version": "$(get_version)"
  }
}
EOF
        fi
      fi
      # Update last_updated timestamp
      sed -i.tmp "s/\"last_updated\": \".*\"/\"last_updated\": \"$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")\"/" "$STATUS_FILE"
      rm -f "${STATUS_FILE}.tmp"
    fi
  fi

  # No need to mirror since we're now using the derivatives location directly
}

# Function to initialize project configs with error handling
initialize_project_configs() {
  local project_ti_toolbox_dir="$LOCAL_PROJECT_DIR/code/ti-toolbox"
  local project_config_dir="$project_ti_toolbox_dir/config"
  local new_project_configs_dir="$SCRIPT_DIR/../../new_project/configs"
  local is_new_project=false

  # Create directories with error checking
  if [ ! -d "$project_ti_toolbox_dir" ]; then
    echo "Creating new project structure..."
    if ! mkdir -p "$project_config_dir" 2>/dev/null; then
      echo "Error: Could not create directory $project_config_dir"
      return 1
    fi
    is_new_project=true
  elif [ ! -d "$project_config_dir" ]; then
    echo "Creating config directory..."
    if ! mkdir -p "$project_config_dir" 2>/dev/null; then
      echo "Error: Could not create directory $project_config_dir"
      return 1
    fi
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
    
    # Create .ti-toolbox-info directory with error checking (under derivatives/ti-toolbox)
    local info_dir="$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
    if ! mkdir -p "$info_dir" 2>/dev/null; then
      echo "Error: Could not create directory $info_dir"
      return 1
    fi
    
    # Copy each config file individually and verify, but only if it doesn't exist
    # Exclude entrypoint.json as it's not needed in project configs
    for config_file in "$new_project_configs_dir"/*.json; do
      if [ -f "$config_file" ]; then
        filename=$(basename "$config_file")
        
        # Skip entrypoint.json
        if [ "$filename" = "entrypoint.json" ]; then
          continue
        fi
        
        target_file="$project_config_dir/$filename"
        
        # Only copy if the file doesn't exist
        if [ ! -f "$target_file" ]; then
          if cp "$config_file" "$target_file" 2>/dev/null; then
            echo "Copied $filename to $project_config_dir"
            # Set proper permissions for the config file
            chmod 644 "$target_file" 2>/dev/null || echo "Warning: Could not set permissions for $target_file"
          else
            echo "Error: Failed to copy $filename"
            return 1
          fi
        else
          echo "Config file $filename already exists, skipping..."
        fi
      fi
    done
    
    # Set proper permissions for config directory
    if ! chmod -R 755 "$project_config_dir" 2>/dev/null; then
      echo "Warning: Could not set permissions for $project_config_dir"
    fi

    # Create initial project status file
    local status_file="$info_dir/project_status.json"
    if ! cat > "$status_file" << EOF 2>/dev/null; then
{
  "project_created": "$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")",
  "last_updated": "$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")",
  "config_created": true,
  "user_preferences": {
    "show_welcome": true
  },
  "project_metadata": {
    "name": "$(basename "$LOCAL_PROJECT_DIR")",
    "path": "$LOCAL_PROJECT_DIR",
    "version": "$(get_version)"
  }
}
EOF
      echo "Error: Could not create $status_file"
      return 1
    fi

    # Set proper permissions with error checking
    if ! chmod -R 755 "$info_dir" 2>/dev/null; then
      echo "Warning: Could not set permissions for $info_dir"
    fi
  fi

  echo "$is_new_project"
  return 0
}

# Main Script Execution

validate_docker_compose
display_welcome
load_default_paths
get_project_directory
get_dev_codebase_directory
# Sanitize possible carriage returns from user input paths - prevents creating a "\r" directory
LOCAL_PROJECT_DIR=$(printf "%s" "$LOCAL_PROJECT_DIR" | tr -d '\r')
DEV_CODEBASE_DIR=$(printf "%s" "$DEV_CODEBASE_DIR" | tr -d '\r')
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
export DEV_CODEBASE_NAME="$DEV_CODEBASE_DIR_NAME"  # Add this line to fix the warning

# Save the paths for next time
save_default_paths

# Write system info and project status with error handling
if ! write_system_info; then
  echo "Warning: Failed to write system info"
fi

if ! write_project_status; then
  echo "Warning: Failed to write project status"
fi

# Ensure BIDS dataset description exists in the project root
initialize_dataset_description

# Ensure ti-toolbox derivative dataset description exists
initialize_ti_toolbox_derivative

# Ensure FreeSurfer derivative dataset description exists
initialize_freesurfer_derivative

# Ensure SimNIBS derivative dataset description exists
initialize_simnibs_derivative

run_docker_compose