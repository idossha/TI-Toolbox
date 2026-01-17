#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR"

OS_TYPE=$(uname -s)
DEFAULT_PATHS_FILE="$SCRIPT_DIR/.default_paths.user"

PROJECT_DIR_CREATED="false"
PROJECT_DIR_EMPTY="false"
VERBOSE="false"
AUTO_CREATE="false"
PROJECT_DIR_ARG=""
XHOST_BIN=""

die() {
  echo "$1"
  exit 1
}

load_default_paths() {
  if [[ -f "$DEFAULT_PATHS_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$DEFAULT_PATHS_FILE"
  fi
}

save_default_paths() {
  echo "LOCAL_PROJECT_DIR=\"$LOCAL_PROJECT_DIR\"" > "$DEFAULT_PATHS_FILE"
}

set_xhost_bin() {
  if command -v xhost >/dev/null 2>&1; then
    XHOST_BIN="xhost"
  elif [[ -x /opt/X11/bin/xhost ]]; then
    XHOST_BIN="/opt/X11/bin/xhost"
  else
    XHOST_BIN=""
    return 1
  fi
}

check_docker_available() {
  command -v docker >/dev/null 2>&1 || die "Error: Docker is not installed or not in PATH."
  docker info >/dev/null 2>&1 || die "Error: Docker daemon is not running. Please start Docker and try again."
  docker compose version >/dev/null 2>&1 || die "Error: Docker Compose (v2) is not available."
}

check_x_forwarding() {
  case "$OS_TYPE" in
    Linux)
      export DISPLAY=${DISPLAY:-:0}
      set_xhost_bin >/dev/null 2>&1 || die "Error: xhost is not available. Please install xhost."
      ;;
    Darwin)
      [[ -d "/Applications/Utilities/XQuartz.app" ]] || die "Error: XQuartz is not installed. Please install XQuartz."
      defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false >/dev/null 2>&1 || true
      if ! pgrep -x "XQuartz" >/dev/null 2>&1 && ! pgrep -x "Xquartz" >/dev/null 2>&1; then
        echo ""
        echo "========================================"
        echo "WARNING: XQuartz is NOT running."
        echo "Start XQuartz if you need GUI support."
        echo "========================================"
        echo ""
      fi
      set_xhost_bin >/dev/null 2>&1 || die "Error: xhost is not available. Please ensure XQuartz is installed correctly."
      ;;
    MINGW*|MSYS*|CYGWIN*)
      echo "Windows detected. Please ensure your X server (VcXsrv/Xming) is running with:"
      echo "  - 'Multiple windows' mode"
      echo "  - 'Disable access control' checked"
      echo "  - Firewall configured to allow X server connections"
      echo ""
      read -r -p "Press Enter to continue once X server is configured..."
      ;;
    *)
      die "Unsupported OS for X11 display configuration."
      ;;
  esac
}

set_display_env() {
  case "$OS_TYPE" in
    Linux)
      export DISPLAY=${DISPLAY:-:0}
      ;;
    Darwin|MINGW*|MSYS*|CYGWIN*)
      export DISPLAY="host.docker.internal:0"
      ;;
  esac
}

allow_xhost() {
  [[ -n "$XHOST_BIN" ]] || return 0
  case "$OS_TYPE" in
    Linux)
      "$XHOST_BIN" +local:root >/dev/null 2>&1 || true
      "$XHOST_BIN" +local:docker >/dev/null 2>&1 || true
      ;;
    Darwin|MINGW*|MSYS*|CYGWIN*)
      DISPLAY=":0" "$XHOST_BIN" +localhost >/dev/null 2>&1 || true
      DISPLAY=":0" "$XHOST_BIN" +"$(hostname)" >/dev/null 2>&1 || true
      ;;
  esac
}

revert_xhost() {
  [[ -n "$XHOST_BIN" ]] || return 0
  case "$OS_TYPE" in
    Linux|Darwin)
      "$XHOST_BIN" -local:root >/dev/null 2>&1 || true
      "$XHOST_BIN" -local:docker >/dev/null 2>&1 || true
      ;;
  esac
}

display_welcome() {
  echo "Welcome to the TI-Toolbox from the Center for Sleep and Consciousness"
  echo ""
  echo "#####################################################################"
  echo ""
}

get_host_timezone() {
  if command -v timedatectl >/dev/null 2>&1; then
    timedatectl show --property=Timezone --value 2>/dev/null || echo "UTC"
  elif [ -L /etc/localtime ]; then
    readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||' || echo "UTC"
  elif command -v systemsetup >/dev/null 2>&1; then
    systemsetup -gettimezone 2>/dev/null | sed 's/Time Zone: //' || echo "UTC"
  else
    date +%Z 2>/dev/null || echo "UTC"
  fi
}

get_project_directory() {
  while true; do
    if [[ -n "$PROJECT_DIR_ARG" ]]; then
      LOCAL_PROJECT_DIR="$PROJECT_DIR_ARG"
    elif [[ -n "${LOCAL_PROJECT_DIR:-}" ]]; then
      echo "Current project directory: $LOCAL_PROJECT_DIR"
      echo "Press Enter to use this directory or enter a new path:"
      read -r new_path
      if [[ -n "$new_path" ]]; then
        LOCAL_PROJECT_DIR="$new_path"
      fi
    else
      echo "Give path to local project dir:"
      read -r LOCAL_PROJECT_DIR
    fi

    LOCAL_PROJECT_DIR="${LOCAL_PROJECT_DIR/#\~/$HOME}"
    LOCAL_PROJECT_DIR=${LOCAL_PROJECT_DIR%$'\r'}

    if [[ -z "$LOCAL_PROJECT_DIR" ]]; then
      echo "Please provide a valid directory path."
      continue
    fi

    if [[ -d "$LOCAL_PROJECT_DIR" ]]; then
      if [[ ! -w "$LOCAL_PROJECT_DIR" ]]; then
        echo "Warning: No write permissions in directory $LOCAL_PROJECT_DIR"
        echo "Do you want to continue anyway? (y/n)"
        read -r response
        [[ "$response" == "y" ]] || continue
      fi
      if [[ -z "$(ls -A "$LOCAL_PROJECT_DIR" 2>/dev/null)" ]]; then
        PROJECT_DIR_EMPTY="true"
      else
        PROJECT_DIR_EMPTY="false"
      fi
      break
    elif [[ -e "$LOCAL_PROJECT_DIR" ]]; then
      echo "Path exists but is not a directory: $LOCAL_PROJECT_DIR"
      [[ -n "$PROJECT_DIR_ARG" ]] && exit 1
      continue
    else
      echo "Directory does not exist: $LOCAL_PROJECT_DIR"
      if [[ "$AUTO_CREATE" == "true" ]]; then
        response="y"
      else
        read -r -p "Create it? (y/n): " response
      fi
      if [[ "$response" == "y" ]]; then
        mkdir -p "$LOCAL_PROJECT_DIR" || die "Error: Unable to create directory $LOCAL_PROJECT_DIR"
        PROJECT_DIR_CREATED="true"
        PROJECT_DIR_EMPTY="true"
        break
      fi
    fi
  done
}

ensure_docker_volumes() {
  if ! docker volume inspect ti-toolbox_freesurfer_data >/dev/null 2>&1; then
    docker volume create ti-toolbox_freesurfer_data >/dev/null 2>&1 || true
  fi
}

ensure_images_pulled() {
  local images
  images=$(grep -E '^\s*image:' "$SCRIPT_DIR/docker-compose.yml" | awk '{print $2}')
  [[ -n "$images" ]] || return 0
  local missing=()
  while IFS= read -r image; do
    [[ -n "$image" ]] || continue
    if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${image}$"; then
      missing+=("$image")
    fi
  done <<< "$images"

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Pulling required Docker images..."
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" pull
  fi
}

initialize_project_in_container() {
  local container_name="simnibs_container"
  local container_project_dir="/mnt/$PROJECT_DIR_NAME"

  echo "Initializing project (inside container)..."

  if ! docker exec "$container_name" test -d "$container_project_dir"; then
    echo "  ⚠ Project directory not found in container: $container_project_dir"
    return 1
  fi

  # Optionally keep the container-side example data manager in sync with this repo version.
  # This does NOT use host Python; it only copies a file into the running container.
  if [[ -f "$SCRIPT_DIR/tit/project_init/example_data_manager.py" ]]; then
    docker cp "$SCRIPT_DIR/tit/project_init/example_data_manager.py" \
      "$container_name:/ti-toolbox/tit/project_init/example_data_manager.py" >/dev/null 2>&1 || true
  fi

  # Run project init + optional example-data setup entirely in container python.
  # Implemented with a container-side heredoc to avoid host-shell quoting issues.
  docker exec \
    -e PROJECT_DIR="$container_project_dir" \
    "$container_name" \
    bash -lc "cat <<'PY' | PYTHONPATH=/ti-toolbox simnibs_python -
import os
from pathlib import Path

def main() -> int:
    try:
        from tit.project_init import is_new_project, initialize_project_structure, setup_example_data
    except Exception as exc:
        print(f\"  ⚠ Could not import tit.project_init in container: {exc}\")
        return 0

    project_dir = Path(os.environ['PROJECT_DIR'])
    toolbox_root = Path('/ti-toolbox')

    try:
        if is_new_project(project_dir):
            initialize_project_structure(project_dir)

        # Returns False when it is a no-op; that's not an error.
        setup_example_data(toolbox_root, project_dir)
    except Exception as exc:
        print(f\"  ⚠ Project initialization failed: {exc}\")

    return 0

raise SystemExit(main())
PY"
}

run_docker_compose() {
  ensure_docker_volumes
  ensure_images_pulled

  export TZ="$(get_host_timezone)"
  export HOME=${HOME:-$USERPROFILE}

  echo "Starting services..."
  docker compose -f "$SCRIPT_DIR/docker-compose.yml" up --build -d

  echo "Waiting for services to initialize..."
  sleep 3

  if ! docker ps --format "{{.Names}}" | grep -q "simnibs_container"; then
    echo "Error: simnibs service is not running. Please check your docker-compose.yml and container logs."
    docker compose -f "$SCRIPT_DIR/docker-compose.yml" logs
    exit 1
  fi

  initialize_project_in_container || true

  echo "Attaching to the simnibs_container..."
  if [[ -t 0 ]]; then
    docker exec -ti simnibs_container bash
  else
    docker exec -i simnibs_container bash
  fi

  docker compose -f "$SCRIPT_DIR/docker-compose.yml" down
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --project-dir)
        PROJECT_DIR_ARG="$2"
        shift 2
        ;;
      --yes)
        AUTO_CREATE="true"
        shift
        ;;
      --verbose)
        VERBOSE="true"
        shift
        ;;
      *)
        shift
        ;;
    esac
  done
}

parse_args "$@"

[[ -f "$SCRIPT_DIR/docker-compose.yml" ]] || die "Error: docker-compose.yml not found in $SCRIPT_DIR."

check_docker_available
check_x_forwarding
display_welcome

load_default_paths
get_project_directory

PROJECT_DIR_NAME=$(basename "$LOCAL_PROJECT_DIR")
save_default_paths

set_display_env
allow_xhost

trap revert_xhost EXIT

export LOCAL_PROJECT_DIR
export PROJECT_DIR_NAME

run_docker_compose
