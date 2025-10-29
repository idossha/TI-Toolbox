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

# Function to get system timezone
get_system_timezone() {
  local tz=$(date +%Z)
  
  if [[ -z "$tz" ]] || [[ ${#tz} -le 3 ]]; then
    if [[ -f /etc/timezone ]]; then
      tz=$(cat /etc/timezone)
    elif command -v systemsetup >/dev/null 2>&1; then
      tz=$(systemsetup -gettimezone | awk '{print $NF}')
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

set_display_env >/dev/null 2>&1
allow_xhost >/dev/null 2>&1
set_timezone_env >/dev/null 2>&1

run_docker_compose 