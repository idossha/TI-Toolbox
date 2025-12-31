#!/bin/bash

# Set script directory
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

# Cache OS type to avoid multiple uname calls
OS_TYPE=$(uname -s)

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
  # Check and create FSL volume if it doesn't exist
  if ! docker volume inspect ti-toolbox_fsl_data >/dev/null 2>&1; then
    docker volume create ti-toolbox_fsl_data >/dev/null 2>&1
  fi
  
  # Check and create FreeSurfer volume if it doesn't exist
  if ! docker volume inspect ti-toolbox_freesurfer_data >/dev/null 2>&1; then
    docker volume create ti-toolbox_freesurfer_data >/dev/null 2>&1
  fi
}


# Function to enable directory path autocompletion
setup_path_completion() {
  bind "set completion-ignore-case on"
  bind "TAB:menu-complete"
  bind "set show-all-if-ambiguous on"
  bind "set menu-complete-display-prefix on"
}

# Function to prompt for directory path with validation
# Usage: get_directory_path <variable_name> <prompt_message> <current_value_var>
get_directory_path() {
  local var_name="$1"
  local prompt_msg="$2"
  local current_var="$3"

  while true; do
    if [[ -n "${!current_var}" ]]; then
      echo "Current $var_name: ${!current_var}"
      echo "Press Enter to use this directory or enter a new path:"
      read -e -r new_path
      if [[ -z "$new_path" ]]; then
        break
      else
        eval "$current_var=\"$new_path\""
      fi
    else
      echo "$prompt_msg"
      read -e -r input
      eval "$current_var=\"$input\""
    fi

    if [[ -d "${!current_var}" ]]; then
      break
    else
      echo "Invalid directory. Please provide a valid path."
    fi
  done
}

# Function to validate and prompt for the project directory
get_project_directory() {
  get_directory_path "project directory" "Give path to local project dir:" LOCAL_PROJECT_DIR
}

# Function to get development codebase directory
get_dev_codebase_directory() {
  get_directory_path "development codebase directory" "Enter path to development codebase:" DEV_CODEBASE_DIR
}

# Function to check XQuartz version (from config_sys.sh)
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

# Function to allow connections from network clients (from config_sys.sh)
allow_network_clients() {
  defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false >/dev/null 2>&1
  
  # Check if XQuartz is already running
  if ! pgrep -x "Xquartz" > /dev/null; then
    open -a XQuartz
    sleep 2
  fi
}


# Function to set DISPLAY environment variable based on OS
set_display_env() {
  case "$OS_TYPE" in
  Linux)
    # If Linux, use the existing DISPLAY (native X11)
    export DISPLAY=$DISPLAY
    ;;
  Darwin|*)
    # For macOS/Windows with Docker Desktop, use host.docker.internal
    export DISPLAY="host.docker.internal:0"
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


# Function to validate docker-compose.yml existence
validate_docker_compose() {
  if [[ ! -f "$SCRIPT_DIR/docker-compose.dev.yml" ]]; then
    echo "Error: docker-compose.dev.yml not found in $SCRIPT_DIR. Please make sure the file is present."
    exit 1
  fi
}

# Function to display welcome message
display_welcome() {
  echo "Welcome to the TI toolbox from the Center for Sleep and Consciousness"
  echo "Developed by Ido Haber as a wrapper around modified SimNIBS"
  echo ""
  echo "#####################################################################"
  echo ""
}

# Function to run Docker Compose and attach to simnibs container
run_docker_compose() {
  # Check if required images exist, pull only if missing
  local images_needed=()
  
  # Extract image names from docker-compose.dev.yml
  local compose_images=$(grep -E '^\s+image:' "$SCRIPT_DIR/docker-compose.dev.yml" | awk '{print $2}')
  
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
    docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" pull
  fi

  # Set host machine timezone for notes and logging
  export TZ="$(get_host_timezone)"

  # Run Docker Compose
  echo "Starting services..."
  docker compose -f "$SCRIPT_DIR/docker-compose.dev.yml" up -d

  # Wait for containers to initialize
  echo "Waiting for services to initialize..."
  sleep 3

  # Copy development codebase to replace existing ti-toolbox content
  echo "Copying development codebase to container..."
  if [ -d "$DEV_CODEBASE_DIR" ]; then
    # Copy the entire development codebase directory content to replace ti-toolbox
    docker cp "$DEV_CODEBASE_DIR/." simnibs_container:/ti-toolbox/
    echo "✓ Development codebase copied to container"
  else
    echo "Warning: Development codebase directory $DEV_CODEBASE_DIR not found"
  fi

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


  # Revert X server access permissions (if xhost is available)
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
  local assets_template="$SCRIPT_DIR/../../resources/dataset_descriptions/root.dataset_description.json"
  local fallback_template="$SCRIPT_DIR/../../new_project/dataset_description.json"

  # If it already exists, skip
  if [ -f "$dataset_file" ]; then
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
    return 0
  else
    echo "Error: Failed to create $dataset_file"
    return 1
  fi
}

# Function to initialize BIDS README file in the project root
initialize_readme() {
  local readme_file="$LOCAL_PROJECT_DIR/README"
  
  # If it already exists, skip
  if [ -f "$readme_file" ]; then
    return 0
  fi

  # Ensure project directory exists
  if [ ! -d "$LOCAL_PROJECT_DIR" ]; then
    echo "Error: Project directory $LOCAL_PROJECT_DIR does not exist."
    return 1
  fi

  # Determine project name
  local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"

  # Create README content
  cat > "$readme_file" << EOF
# $project_name

This is a BIDS-compliant neuroimaging dataset generated by TI-Toolbox for temporal interference (TI) stimulation modeling and analysis.

## Overview

This project contains structural MRI data and derivatives for simulating and analyzing temporal interference electric field patterns in the brain.

## Dataset Structure

- \`sourcedata/\` - Raw DICOM source files
- \`sub-*/\` - Subject-level BIDS-formatted neuroimaging data (NIfTI files)
- \`derivatives/\` - Processed data and analysis results
  - \`freesurfer/\` - FreeSurfer anatomical segmentation and surface reconstructions
  - \`SimNIBS/\` - SimNIBS head models and electric field simulations
  - \`ti-toolbox/\` - TI-Toolbox simulation results and analyses

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

  # Basic verification
  if [ -f "$readme_file" ]; then
    echo "Created BIDS README file at $readme_file"
    return 0
  else
    echo "Error: Failed to create $readme_file"
    return 1
  fi
}

# Function to initialize derivative dataset_description.json files
# Usage: initialize_derivative_dataset <subdir_name> <template_name> <error_message>
initialize_derivative_dataset() {
  local subdir_name="$1"
  local template_name="$2"
  local error_msg="$3"

  local derivatives_dir="$LOCAL_PROJECT_DIR/derivatives"
  local sub_dir="$derivatives_dir/$subdir_name"
  local dataset_file="$sub_dir/dataset_description.json"
  local assets_template="$SCRIPT_DIR/../../resources/dataset_descriptions/$template_name"

  # If it already exists, skip
  if [ -f "$dataset_file" ]; then
    return 0
  fi

  # Ensure derivatives directory exists
  if [ ! -d "$derivatives_dir" ]; then
    mkdir -p "$derivatives_dir" 2>/dev/null || { echo "Error: Failed to create derivatives directory"; return 1; }
  fi

  # Ensure sub directory exists
  if [ ! -d "$sub_dir" ]; then
    mkdir -p "$sub_dir" 2>/dev/null || { echo "Error: Failed to create $subdir_name directory"; return 1; }
  fi

  # Check if template exists
  if [ ! -f "$assets_template" ]; then
    echo "Error: $template_name template not found at $assets_template"
    return 1
  fi

  # Copy template to derivatives/subdir/
  if cp "$assets_template" "$dataset_file" 2>/dev/null; then
    # Fill in project-specific information
    local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"
    local current_date=$(date +"%Y-%m-%d")

    # Update URI field
    sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$project_name@$current_date\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"

    # Update DatasetLinks field
    sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$project_name\": \"..\/..\/\"\n  }/" "$dataset_file" && rm -f "${dataset_file}.tmp"

    return 0
  else
    echo "Error: Failed to create $error_msg"
    return 1
  fi
}

# Function to initialize ti-toolbox derivative dataset_description.json
initialize_ti_toolbox_derivative() {
  initialize_derivative_dataset "ti-toolbox" "ti-toolbox.dataset_description.json" "ti-toolbox derivative dataset_description.json"
}

# Function to initialize FreeSurfer derivative dataset_description.json
initialize_freesurfer_derivative() {
  initialize_derivative_dataset "freesurfer" "freesurfer.dataset_description.json" "FreeSurfer derivative dataset_description.json"
}

# Function to initialize SimNIBS derivative dataset_description.json
initialize_simnibs_derivative() {
  initialize_derivative_dataset "SimNIBS" "simnibs.dataset_description.json" "SimNIBS derivative dataset_description.json"
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

  # No need to mirror since we're now using the derivatives location directly
  return 0
}

# Function to write project status
write_project_status() {
  echo ""
  echo "Initializing project status..."

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
  echo "✓ Project status updated"
  return 0
}

# Function to setup example data for new projects
setup_example_data_if_new() {
  echo "Setting up example data for new project..."

  local toolbox_root="$SCRIPT_DIR/../.."
  local example_data_manager="$toolbox_root/tit/new_project/example_data_manager.py"
  
  # Check if the example data manager exists
  if [ ! -f "$example_data_manager" ]; then
    echo "ERROR: Example data manager not found at $example_data_manager"
    ls -la "$toolbox_root/tit/new_project/" 2>&1 || echo "Directory does not exist"
    return 1
  fi
  
  # Check if Python is available (in dev mode, we're on host, not in Docker)
  if command -v python3 >/dev/null 2>&1; then
    
    # Run the example data manager with verbose output
    if python3 "$example_data_manager" "$toolbox_root" "$LOCAL_PROJECT_DIR" 2>&1; then
      echo "✓ Example data setup completed successfully"
    else
      local exit_code=$?
      echo "ERROR: Example data setup failed with exit code: $exit_code"
      echo "Continuing with project initialization..."
    fi
  else
    echo "ERROR: Python3 not available in PATH - skipping example data setup"
  fi
}

# Function to initialize project configs with error handling
initialize_project_configs() {
  echo "Checking project configuration..."

  local project_ti_toolbox_dir="$LOCAL_PROJECT_DIR/code/ti-toolbox"
  local project_config_dir="$project_ti_toolbox_dir/config"
  local new_project_configs_dir="$SCRIPT_DIR/../../tit/new_project/configs"
  local is_new_project=false
  
  # Check if project directories exist

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
      echo "ERROR: Default configs directory not found at $new_project_configs_dir"
      ls -la "$(dirname "$new_project_configs_dir")" 2>&1 || echo "Parent directory does not exist"
      return 1
    fi
    
    # Create .ti-toolbox-info directory with error checking (under derivatives/ti-toolbox)
    local info_dir="$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
    if ! mkdir -p "$info_dir" 2>/dev/null; then
      echo "ERROR: Could not create directory $info_dir"
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
  "example_data_copied": false,
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
    
    # Initialize BIDS files for new projects
    initialize_dataset_description
    initialize_readme
    
    # Setup example data for new projects
    setup_example_data_if_new
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
LOCAL_PROJECT_DIR=${LOCAL_PROJECT_DIR%$'\r'}
DEV_CODEBASE_DIR=${DEV_CODEBASE_DIR%$'\r'}
PROJECT_DIR_NAME=${LOCAL_PROJECT_DIR##*/}
DEV_CODEBASE_DIR_NAME=${DEV_CODEBASE_DIR##*/}
initialize_volumes >/dev/null 2>&1

# Setup X11 for macOS (using config_sys.sh approach)
if [[ "$OS_TYPE" == "Darwin" ]]; then
  check_xquartz_version >/dev/null 2>&1
  allow_network_clients >/dev/null 2>&1
fi

set_display_env >/dev/null 2>&1

# Set up Docker Compose environment variables
export LOCAL_PROJECT_DIR
export PROJECT_DIR_NAME
export DEV_CODEBASE_DIR
export DEV_CODEBASE_DIR_NAME
export DEV_CODEBASE_NAME="$DEV_CODEBASE_DIR_NAME"  # Add this line to fix the warning

# Set OpenGL environment variables conditionally based on OS
if [[ "$OS_TYPE" == "Darwin" ]]; then
  # macOS needs these settings for OpenGL to work in Docker
  export LIBGL_ALWAYS_SOFTWARE="1"
  export LIBGL_ALWAYS_INDIRECT="1"
  export QT_X11_NO_MITSHM="1"
  export QT_OPENGL="desktop"
  export TI_GUI_QGL_FALLBACK="1"
fi
# For Windows and Linux, leave OpenGL variables unset (docker-compose will use empty defaults)

# Save the paths for next time
save_default_paths

# Write system info and project status with error handling
write_system_info >/dev/null 2>&1
write_project_status

# Ensure BIDS dataset description exists in the project root
initialize_dataset_description >/dev/null 2>&1

# Ensure ti-toolbox derivative dataset description exists
initialize_ti_toolbox_derivative >/dev/null 2>&1

# Ensure FreeSurfer derivative dataset description exists
initialize_freesurfer_derivative >/dev/null 2>&1

# Ensure SimNIBS derivative dataset description exists
initialize_simnibs_derivative >/dev/null 2>&1

run_docker_compose
