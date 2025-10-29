#!/bin/bash

# Set script directory
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
cd "$SCRIPT_DIR"

# Default paths file
DEFAULT_PATHS_FILE="$SCRIPT_DIR/.default_paths.user"

# Function to create hidden files cross-platform
create_hidden_file() {
    local file_path="$1"
    local content="$2"
    
    # Create the file with content
    if [ -n "$content" ]; then
        echo "$content" > "$file_path"
    else
        touch "$file_path"
    fi
    
    # Make it hidden based on OS
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*)
            # Windows
            attrib +h "$file_path" >/dev/null 2>&1
            ;;
        *)
            # Unix-like (macOS/Linux)
            # Files are already hidden if they start with a dot
            ;;
    esac
}

# Function to load default paths
load_default_paths() {
  if [[ -f "$DEFAULT_PATHS_FILE" ]]; then
    source "$DEFAULT_PATHS_FILE"
  fi
}

# Function to save default paths
save_default_paths() {
    create_hidden_file "$DEFAULT_PATHS_FILE" "LOCAL_PROJECT_DIR=\"$LOCAL_PROJECT_DIR\""
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

# Function to set DISPLAY environment variable based on OS and processor type
set_display_env() {

  case "$(uname -s)" in
  Linux)
    # If Linux, use the existing DISPLAY
    export DISPLAY=${DISPLAY:-:0}
    ;;
  Darwin)
    # For macOS, we need IP-based DISPLAY for the container
    get_host_ip # Get the IP address dynamically
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
  echo "Welcome to the TI toolbox from the Center for Sleep and Consciousness"
  echo "Developed by Ido Haber as a wrapper around modified SimNIBS"
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

  # Attach to the simnibs container with an interactive terminal
  docker exec -ti simnibs_container bash

  # Stop and remove all containers when done
  docker compose -f "$SCRIPT_DIR/docker-compose.yml" down >/dev/null 2>&1

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
        cp "$assets_template" "$dataset_file" || { echo "Error: Failed to copy assets template dataset_description.json"; return 1; }
    elif [ -f "$fallback_template" ]; then
        cp "$fallback_template" "$dataset_file" || { echo "Error: Failed to copy fallback template dataset_description.json"; return 1; }
    else
        echo "Error: No dataset_description template found in assets or new_project"; return 1
    fi
    
    # Fill in the Name field in a cross-platform way
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

# Function to initialize ti-toolbox derivative dataset_description.json
initialize_ti_toolbox_derivative() {
    local derivatives_dir="$LOCAL_PROJECT_DIR/derivatives"
    local ti_toolbox_dir="$derivatives_dir/ti-toolbox"
    local dataset_file="$ti_toolbox_dir/dataset_description.json"
    local assets_template="$SCRIPT_DIR/../../resources/dataset_descriptions/ti-toolbox.dataset_description.json"

    # If it already exists, skip
    if [ -f "$dataset_file" ]; then
        return 0
    fi

    # Ensure derivatives directory exists
    if [ ! -d "$derivatives_dir" ]; then
        mkdir -p "$derivatives_dir" || { echo "Error: Failed to create derivatives directory"; return 1; }
    fi

    # Ensure ti-toolbox directory exists
    if [ ! -d "$ti_toolbox_dir" ]; then
        mkdir -p "$ti_toolbox_dir" || { echo "Error: Failed to create ti-toolbox directory"; return 1; }
    fi

    # Check if template exists
    if [ ! -f "$assets_template" ]; then
        echo "Error: ti-toolbox.dataset_description.json template not found at $assets_template"
        return 1
    fi

    # Copy template to derivatives/ti-toolbox/
    if cp "$assets_template" "$dataset_file"; then
        # Fill in project-specific information
        local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"
        local current_date=$(date +"%Y-%m-%d")
        
        # Update URI field
        sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$project_name@$current_date\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"
        
        # Update DatasetLinks field
        sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$project_name\": \"..\/..\/\"\n  }/" "$dataset_file" && rm -f "${dataset_file}.tmp"
        
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
    local assets_template="$SCRIPT_DIR/../../resources/dataset_descriptions/freesurfer.dataset_description.json"

    # If it already exists, skip
    if [ -f "$dataset_file" ]; then
        return 0
    fi

    # Ensure derivatives directory exists
    if [ ! -d "$derivatives_dir" ]; then
        mkdir -p "$derivatives_dir" || { echo "Error: Failed to create derivatives directory"; return 1; }
    fi

    # Ensure freesurfer directory exists
    if [ ! -d "$freesurfer_dir" ]; then
        mkdir -p "$freesurfer_dir" || { echo "Error: Failed to create freesurfer directory"; return 1; }
    fi

    # Check if template exists
    if [ ! -f "$assets_template" ]; then
        echo "Error: freesurfer.dataset_description.json template not found at $assets_template"
        return 1
    fi

    # Copy template to derivatives/freesurfer/
    if cp "$assets_template" "$dataset_file"; then
        # Fill in project-specific information
        local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"
        local current_date=$(date +"%Y-%m-%d")
        
        # Update URI field
        sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$project_name@$current_date\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"
        
        # Update DatasetLinks field
        sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$project_name\": \"..\/..\/\"\n  }/" "$dataset_file" && rm -f "${dataset_file}.tmp"
        
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
    local assets_template="$SCRIPT_DIR/../../resources/dataset_descriptions/simnibs.dataset_description.json"

    # If it already exists, skip
    if [ -f "$dataset_file" ]; then
        return 0
    fi

    # Ensure derivatives directory exists
    if [ ! -d "$derivatives_dir" ]; then
        mkdir -p "$derivatives_dir" || { echo "Error: Failed to create derivatives directory"; return 1; }
    fi

    # Ensure SimNIBS directory exists
    if [ ! -d "$simnibs_dir" ]; then
        mkdir -p "$simnibs_dir" || { echo "Error: Failed to create SimNIBS directory"; return 1; }
    fi

    # Check if template exists
    if [ ! -f "$assets_template" ]; then
        echo "Error: simnibs.dataset_description.json template not found at $assets_template"
        return 1
    fi

    # Copy template to derivatives/SimNIBS/
    if cp "$assets_template" "$dataset_file"; then
        # Fill in project-specific information
        local project_name="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"
        local current_date=$(date +"%Y-%m-%d")
        
        # Update URI field
        sed -i.tmp "s/\"URI\": \"\"/\"URI\": \"bids:$project_name@$current_date\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"
        
        # Update DatasetLinks field
        sed -i.tmp "s/\"DatasetLinks\": {}/\"DatasetLinks\": {\n    \"$project_name\": \"..\/..\/\"\n  }/" "$dataset_file" && rm -f "${dataset_file}.tmp"
        
        return 0
    else
        echo "Error: Failed to create SimNIBS derivative dataset_description.json"
        return 1
    fi
}

# Function to setup example data for new projects
setup_example_data_if_new() {
    local toolbox_root="$SCRIPT_DIR/../.."
    local example_data_manager="$toolbox_root/ti-toolbox/new_project/example_data_manager.py"
    
    # Check if the example data manager exists
    if [ ! -f "$example_data_manager" ]; then
        echo "Warning: Example data manager not found at $example_data_manager"
        return 1
    fi
    
    # Check if Python is available in the Docker environment
    if command -v python3 >/dev/null 2>&1; then
        echo "Setting up example data for new project..."
        
        # Run the example data manager
        if python3 "$example_data_manager" "$toolbox_root" "$LOCAL_PROJECT_DIR"; then
            echo "✓ Example data setup completed successfully"
        else
            echo "Warning: Example data setup failed, continuing with project initialization"
        fi
    else
        echo "Warning: Python3 not available, skipping example data setup"
    fi
}

# Function to check if project is new and initialize config files
initialize_project_configs() {
    local project_ti_csc_dir="$LOCAL_PROJECT_DIR/code/ti-toolbox"
    local project_config_dir="$project_ti_csc_dir/config"
    local new_project_configs_dir="$SCRIPT_DIR/../../new_project/configs"
    local is_new_project=false

    # Check if ti-toolbox directory exists
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
                    cp "$config_file" "$target_file"
                    if [ $? -eq 0 ]; then
                        echo "Copied $filename to $project_config_dir"
                        # Make the file hidden
                        create_hidden_file "$target_file"
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

        # Create derivatives/ti-toolbox/.ti-toolbox-info directory and initialize project status
        local info_dir="$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
        mkdir -p "$info_dir"
        
        # Create initial project status file with empty structure
        local status_content='{
  "project_created": "",
  "last_updated": "",
  "config_created": false,
  "example_data_copied": false,
  "user_preferences": {
    "show_welcome": true
  },
  "project_metadata": {
    "name": "",
    "path": "",
    "version": ""
  }
}'
        create_hidden_file "$info_dir/project_status.json" "$status_content"

        # Set proper permissions for the info directory
        chmod -R 755 "$info_dir"
        echo "Project status initialized in $info_dir"
        
        # Initialize BIDS files for new projects
        initialize_dataset_description
        initialize_readme
        
        # Setup example data for new projects
        setup_example_data_if_new
    fi

    # Return the new project status
    echo "$is_new_project"
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

# Function to write system info to a hidden folder in the user's project directory
write_system_info() {
    INFO_DIR="$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
    INFO_FILE="$INFO_DIR/system_info.txt"
    mkdir -p "$INFO_DIR"

    # Create the system info file with initial content
    {
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
        else
            echo "Docker not found"
        fi
        echo ""
        echo "## DISPLAY"
        echo "$DISPLAY"
        echo ""
        echo "## Environment Variables (TI-Toolbox relevant)"
        env | grep -Ei '^(FREESURFER|SIMNIBS|PROJECT_DIR|DEV_CODEBASE|SUBJECTS_DIR|FS_LICENSE|FSFAST|MNI|POSSUM|DISPLAY|USER|PATH)='
        echo ""
    } > "$INFO_FILE"

    # Make the file hidden
    create_hidden_file "$INFO_FILE"

    # No need to mirror since we're now using the derivatives location directly
}

# Function to get the system timezone
get_system_timezone() {
  # Try to get timezone using date command
  local tz=$(date +%Z)
  
  # If that returns UTC or similar short code, try to get full timezone name
  if [[ -z "$tz" ]] || [[ ${#tz} -le 3 ]]; then
    # Try to get from /etc/timezone (Linux)
    if [[ -f /etc/timezone ]]; then
      tz=$(cat /etc/timezone)
    # Try to get from system preferences (macOS)
    elif command -v systemsetup >/dev/null 2>&1; then
      tz=$(systemsetup -gettimezone | awk '{print $NF}')
    # Fall back to TZ environment variable or UTC
    else
      tz="${TZ:-UTC}"
    fi
  fi
  
  echo "$tz"
}

# Function to set timezone environment variable
set_timezone_env() {
  local tz=$(get_system_timezone)
  export TZ="$tz"
  echo "System timezone detected: $tz"
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
# Sanitize potential carriage returns from path (prevents creating a "\r" dir under /mnt)
LOCAL_PROJECT_DIR=$(printf "%s" "$LOCAL_PROJECT_DIR" | tr -d '\r')

# Set up Docker Compose environment variables
# Handle Windows paths for Docker
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    # Convert Windows paths to Docker-compatible format
    # C:\Users\name\project -> /c/Users/name/project (Git Bash style)
    # or C:\Users\name\project -> C:/Users/name/project (Docker style)
    if [[ "$LOCAL_PROJECT_DIR" =~ ^[A-Za-z]: ]]; then
      # Convert C:\path to /c/path for Git Bash
      DOCKER_PROJECT_DIR="/$(echo "$LOCAL_PROJECT_DIR" | sed 's/://' | sed 's/\\/\//g' | tr '[:upper:]' '[:lower:]')"
      # Alternative: Keep Windows style but with forward slashes
      # DOCKER_PROJECT_DIR=$(echo "$LOCAL_PROJECT_DIR" | sed 's/\\/\//g')
    else
      DOCKER_PROJECT_DIR="$LOCAL_PROJECT_DIR"
    fi
    export LOCAL_PROJECT_DIR="$DOCKER_PROJECT_DIR"
    ;;
  *)
    export LOCAL_PROJECT_DIR
    ;;
esac
# Compute and sanitize project dir name after any normalization
PROJECT_DIR_NAME=$(basename "$LOCAL_PROJECT_DIR")
PROJECT_DIR_NAME=$(printf "%s" "$PROJECT_DIR_NAME" | tr -d '\r')
export PROJECT_DIR_NAME

# Save the paths for next time
save_default_paths

# Write system info and project status to hidden folder in project dir
write_system_info >/dev/null 2>&1
write_project_status >/dev/null 2>&1

# Ensure BIDS dataset description exists in the project root
initialize_dataset_description >/dev/null 2>&1

# Ensure ti-toolbox derivative dataset description exists
initialize_ti_toolbox_derivative >/dev/null 2>&1

# Ensure FreeSurfer derivative dataset description exists
initialize_freesurfer_derivative >/dev/null 2>&1

# Ensure SimNIBS derivative dataset description exists
initialize_simnibs_derivative >/dev/null 2>&1

set_display_env >/dev/null 2>&1
allow_xhost >/dev/null 2>&1 # Allow X11 connections
set_timezone_env >/dev/null 2>&1

run_docker_compose 