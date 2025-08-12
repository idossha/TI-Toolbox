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
  echo "Host IP: $HOST_IP"
}

# Function to set DISPLAY environment variable based on OS and processor type
set_display_env() {
  echo "Setting DISPLAY environment variable..."

  case "$(uname -s)" in
  Linux)
    # If Linux, use the existing DISPLAY
    export DISPLAY=${DISPLAY:-:0}
    echo "Using system's DISPLAY: $DISPLAY"
    ;;
  Darwin)
    # For macOS, dynamically obtain the host IP and set DISPLAY
    get_host_ip # Get the IP address dynamically
    export DISPLAY="$HOST_IP:0"
    echo "DISPLAY set to $DISPLAY"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    # For Windows (Git Bash, MSYS2, Cygwin)
    get_host_ip
    export DISPLAY="$HOST_IP:0.0"
    echo "DISPLAY set to $DISPLAY"
    ;;
  *)
    echo "Unsupported OS for X11 display configuration."
    exit 1
    ;;
  esac
}

# Function to allow connections from XQuartz or X11
allow_xhost() {
  echo "Allowing connections from XQuartz or X11..."

  case "$(uname -s)" in
  Linux)
    # Allow connections for Linux
    if command -v xhost >/dev/null 2>&1; then
      xhost +local:root >/dev/null 2>&1
      xhost +local:docker >/dev/null 2>&1
    fi
    ;;
  Darwin)
    # Use the dynamically obtained IP for macOS xhost
    if command -v xhost >/dev/null 2>&1; then
      xhost + "$HOST_IP" >/dev/null 2>&1
      xhost +localhost >/dev/null 2>&1
    fi
    ;;
  MINGW*|MSYS*|CYGWIN*)
    # Windows doesn't have xhost in Git Bash
    echo "Note: Make sure your X server (VcXsrv/Xming) is configured to accept connections."
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
  echo " "
  echo "#####################################################################"
  echo "Welcome to the TI toolbox from the Center for Sleep and Consciousness"
  echo "Developed by Ido Haber as a wrapper around Modified SimNIBS"
  echo " "
  echo "Make sure you have:"
  echo "  - XQuartz (on macOS) - [version 2.7.7 recommended for OpenGL support][[memory:3056357008131702354]]"
  echo "  - X11 (on Linux)"
  echo "  - VcXsrv or Xming (on Windows) - with 'Disable access control' checked"
  echo ""
  echo "If you wish to use the optimizer, consider allocating more RAM to Docker."
  echo "#####################################################################"
  echo " "
}

# Function to ensure required Docker volumes exist
ensure_docker_volumes() {
  echo "Ensuring required Docker volumes exist..."
  local volumes=("ti_csc_fsl_data" "ti_csc_freesurfer_data")
  
  for volume in "${volumes[@]}"; do
    if ! docker volume inspect "$volume" >/dev/null 2>&1; then
      echo "Creating Docker volume: $volume"
      docker volume create "$volume"
    fi
  done
}

# Function to run Docker Compose and attach to simnibs container
run_docker_compose() {
  # Ensure volumes exist
  ensure_docker_volumes

  # Set HOME environment variable for .Xauthority access
  export HOME=${HOME:-$USERPROFILE}

  # Pull images if they don't exist
  echo "Pulling required Docker images..."
  docker compose -f "$SCRIPT_DIR/docker-compose.yml" pull

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
    local template_file="$SCRIPT_DIR/../../new_project/dataset_description.json"

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

    # Create from template if available, else generate minimal file
    if [ -f "$template_file" ];
    then
        cp "$template_file" "$dataset_file" || {
            echo "Error: Failed to copy template dataset_description.json";
            return 1;
        }
        # Fill in the Name field in a cross-platform way
        sed -i.tmp "s/\"Name\": \"\"/\"Name\": \"$project_name\"/" "$dataset_file" && rm -f "${dataset_file}.tmp"
    else
        cat > "$dataset_file" << EOF
{
    "Name": "$project_name",
    "BIDSVersion": "1.10.0",
    "HEDVersion": "8.2.0",
    "DatasetType": "raw",
    "License": "",
    "Authors": [
        "",
        "",
        ""
    ],
    "Acknowledgements": "",
    "HowToAcknowledge": "",
    "Funding": [
        "",
        "",
        ""
    ],
    "EthicsApprovals": [
        ""
    ],
    "ReferencesAndLinks": [
        "",
        "",
        ""
    ],
    "DatasetDOI": "doi:"
}
EOF
    fi

    # Basic verification
    if [ -f "$dataset_file" ]; then
        echo "Created $dataset_file"
        return 0
    else
        echo "Error: Failed to create $dataset_file"
        return 1
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

        # Create .ti-csc-info directory and initialize project status
        local info_dir="$LOCAL_PROJECT_DIR/.ti-csc-info"
        mkdir -p "$info_dir"
        
        # Create initial project status file with empty structure
        local status_content='{
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
}'
        create_hidden_file "$info_dir/project_status.json" "$status_content"

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

    # Create the system info file with initial content
    {
        echo "# TI-CSC System Info"
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
        echo "## Environment Variables (TI-CSC relevant)"
        env | grep -Ei '^(FSL|FREESURFER|SIMNIBS|PROJECT_DIR|DEV_CODEBASE|SUBJECTS_DIR|FS_LICENSE|FSFAST|MNI|POSSUM|DISPLAY|USER|PATH)='
        echo ""
    } > "$INFO_FILE"

    # Make the file hidden
    create_hidden_file "$INFO_FILE"
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
PROJECT_DIR_NAME=$(basename "$LOCAL_PROJECT_DIR")

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
export PROJECT_DIR_NAME

# Save the paths for next time
save_default_paths

# Write system info and project status to hidden folder in project dir
write_system_info
write_project_status

# Ensure BIDS dataset description exists in the project root
initialize_dataset_description

echo "System info written to $LOCAL_PROJECT_DIR/.ti-csc-info/system_info.txt"
echo "Project status written to $LOCAL_PROJECT_DIR/.ti-csc-info/project_status.json"

set_display_env
allow_xhost # Allow X11 connections

run_docker_compose 