#!/bin/bash
#
# TI-Toolbox dev loader (bash).
#
# Equivalent of loader_dev.py for users who do not have Python installed on
# the host. Project scaffolding (BIDS structure, example data) runs inside
# the simnibs container via `tit.project_init`, so no host-side Python is
# required.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OS_TYPE=$(uname -s)
DEFAULT_PATHS_FILE="$SCRIPT_DIR/.default_paths.dev"
DOCKER_COMPOSE_FILE="$SCRIPT_DIR/docker-compose.dev.yml"
FREESURFER_VOLUME_PREFIX="ti-toolbox_freesurfer_data"

# ---------------------------------------------------------------------------
# Docker prerequisites
# ---------------------------------------------------------------------------

check_docker_available() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Error: Docker is not installed or not in PATH."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker daemon is not running. Please start Docker and try again."
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "Error: Docker Compose (v2) is not available."
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Default paths persistence
# ---------------------------------------------------------------------------

load_default_paths() {
  if [[ -f "$DEFAULT_PATHS_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$DEFAULT_PATHS_FILE"
  fi
}

save_default_paths() {
  {
    echo "LOCAL_PROJECT_DIR=\"$LOCAL_PROJECT_DIR\""
    echo "DEV_CODEBASE_DIR=\"$DEV_CODEBASE_DIR\""
  } > "$DEFAULT_PATHS_FILE"
}

# ---------------------------------------------------------------------------
# Interactive directory prompts
# ---------------------------------------------------------------------------

setup_path_completion() {
  bind "set completion-ignore-case on" 2>/dev/null || true
  bind "TAB:menu-complete" 2>/dev/null || true
  bind "set show-all-if-ambiguous on" 2>/dev/null || true
  bind "set menu-complete-display-prefix on" 2>/dev/null || true
}

# Usage: get_directory_path <label> <prompt_message> <current_value_var>
get_directory_path() {
  local label="$1"
  local prompt_msg="$2"
  local current_var="$3"
  local input_path

  while true; do
    if [[ -n "${!current_var:-}" ]]; then
      echo "Current $label: ${!current_var}"
      echo "Press Enter to use this directory or enter a new path:"
      read -e -r input_path
      if [[ -z "$input_path" ]]; then
        break
      fi
    else
      echo "$prompt_msg"
      read -e -r input_path
    fi

    # Expand a leading ~ since read/[[ -d ]] does not do this automatically.
    input_path="${input_path/#\~/$HOME}"
    printf -v "$current_var" '%s' "$input_path"

    if [[ -d "${!current_var:-}" ]]; then
      break
    else
      echo "Invalid directory. Please provide a valid path."
    fi
  done
}

get_project_directory() {
  get_directory_path "project directory" "Give path to local project dir:" LOCAL_PROJECT_DIR
}

get_dev_codebase_directory() {
  get_directory_path "development codebase directory" "Enter path to development codebase:" DEV_CODEBASE_DIR
}

# ---------------------------------------------------------------------------
# macOS X11 / XQuartz
# ---------------------------------------------------------------------------

setup_macos_x11() {
  local xquartz_app="/Applications/Utilities/XQuartz.app"
  if [[ ! -d "$xquartz_app" ]]; then
    echo ""
    echo "WARNING: XQuartz not found. Install it from https://www.xquartz.org/ for GUI support."
    echo ""
    return 0
  fi

  defaults write org.macosforge.xquartz.X11 nolisten_tcp -bool false >/dev/null 2>&1 || true

  if ! pgrep -ix "XQuartz" >/dev/null 2>&1; then
    echo ""
    echo "========================================"
    echo "WARNING: XQuartz is NOT running."
    echo "Start XQuartz if you need GUI support."
    echo "========================================"
    echo ""
  fi
}

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

set_display_env() {
  case "$OS_TYPE" in
  Linux)
    export DISPLAY="${DISPLAY:-:0}"
    ;;
  Darwin|*)
    export DISPLAY="host.docker.internal:0"
    ;;
  esac
}

get_host_timezone() {
  if command -v timedatectl >/dev/null 2>&1; then
    timedatectl show --property=Timezone --value 2>/dev/null || echo "UTC"
  elif [ -L /etc/localtime ]; then
    local timezone_path
    timezone_path=$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')
    echo "${timezone_path:-UTC}"
  elif command -v systemsetup >/dev/null 2>&1; then
    systemsetup -gettimezone 2>/dev/null | sed 's/Time Zone: //' || echo "UTC"
  else
    date +%Z 2>/dev/null || echo "UTC"
  fi
}

# Host-side user config directory (telemetry/prefs), mirrors
# tit.paths.PathManager.user_config_dir() and package/src/backend/env.js.
get_user_config_dir() {
  local base
  case "$OS_TYPE" in
  Darwin)
    base="$HOME/.config"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    base="${APPDATA:-$HOME/AppData/Roaming}"
    ;;
  *)
    base="${XDG_CONFIG_HOME:-$HOME/.config}"
    ;;
  esac
  local config_dir="$base/ti-toolbox"
  mkdir -p "$config_dir"
  echo "$config_dir"
}

# ---------------------------------------------------------------------------
# FreeSurfer volume versioning (see dev/freesurfer-volume-versioning.md)
# ---------------------------------------------------------------------------

get_freesurfer_volume_name() {
  local tag
  tag=$(grep -E '^[[:space:]]*image:[[:space:]]*[^[:space:]]*ti-toolbox_freesurfer:' "$DOCKER_COMPOSE_FILE" \
    | sed -E 's/^[[:space:]]*image:[[:space:]]*[^[:space:]]*ti-toolbox_freesurfer:([^[:space:]]+)[[:space:]]*$/\1/' || true)
  if [[ -n "$tag" ]]; then
    echo "${FREESURFER_VOLUME_PREFIX}_${tag}"
  fi
}

# Remove stale older-version FreeSurfer volumes (best-effort). A blank
# current_name means the active version could not be parsed, so pruning is
# skipped rather than risking deletion of a good volume.
prune_old_freesurfer_volumes() {
  local current_name="$1"
  [[ -z "$current_name" ]] && return 0

  local name
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    if { [[ "$name" == "${FREESURFER_VOLUME_PREFIX}_"* ]] || [[ "$name" == "$FREESURFER_VOLUME_PREFIX" ]]; } \
      && [[ "$name" != "$current_name" ]]; then
      docker volume rm "$name" >/dev/null 2>&1 || true
    fi
  done < <(docker volume ls --format '{{.Name}}')
}

# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

ensure_images_pulled() {
  local images_needed=()
  local compose_images
  compose_images=$(grep -E '^[[:space:]]+image:' "$DOCKER_COMPOSE_FILE" | awk '{print $2}')

  local image
  while IFS= read -r image; do
    if [ -n "$image" ]; then
      if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -qxF "$image"; then
        images_needed+=("$image")
      fi
    fi
  done <<< "$compose_images"

  if [ ${#images_needed[@]} -gt 0 ]; then
    echo "Pulling required Docker images..."
    docker compose -f "$DOCKER_COMPOSE_FILE" pull
  fi
}

# ---------------------------------------------------------------------------
# Project initialization (runs inside the container — no host Python needed)
# ---------------------------------------------------------------------------

run_project_init_in_container() {
  local project_dir_name="$1"
  local container_project_dir="/mnt/${project_dir_name}"
  local tmp_script
  tmp_script="$(mktemp)"

  cat > "$tmp_script" <<'PY'
import os
from pathlib import Path
from tit.project_init import is_new_project, initialize_project_structure, setup_example_data

project_dir = Path(os.environ["PROJECT_DIR"])
toolbox_root = Path("/ti-toolbox")

if is_new_project(project_dir):
    initialize_project_structure(project_dir)

setup_example_data(toolbox_root, project_dir)
PY

  docker cp "$tmp_script" simnibs_container:/tmp/ti_toolbox_project_init.py >/dev/null 2>&1
  docker exec -e PROJECT_DIR="$container_project_dir" simnibs_container \
    bash -lc "PYTHONPATH=/ti-toolbox simnibs_python /tmp/ti_toolbox_project_init.py" || true
  rm -f "$tmp_script"
}

# ---------------------------------------------------------------------------
# Host-side system info (informational; written before the container starts)
# ---------------------------------------------------------------------------

write_system_info() {
  local info_dir="$LOCAL_PROJECT_DIR/derivatives/ti-toolbox/.ti-toolbox-info"
  local info_file="$info_dir/system_info.txt"

  mkdir -p "$info_dir" 2>/dev/null || return 0

  {
    echo "# TI-Toolbox System Info"
    echo "Date: $(date)"
    echo "User: $(whoami)"
    echo "Host: $(hostname)"
    echo "OS: $(uname -a)"
    echo ""
    echo "## Docker Version"
    if command -v docker &>/dev/null; then
      docker --version
    else
      echo "Docker not found"
    fi
    echo ""
    echo "## DISPLAY"
    echo "$DISPLAY"
    echo ""
  } > "$info_file" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Welcome banner
# ---------------------------------------------------------------------------

display_welcome() {
  echo "Welcome to the TI toolbox from the Center for Sleep and Consciousness"
  echo "Developed by Ido Haber as a wrapper around modified SimNIBS"
  echo ""
  echo "#####################################################################"
  echo ""
}

# ---------------------------------------------------------------------------
# Docker Compose lifecycle
# ---------------------------------------------------------------------------

run_docker_compose() {
  local freesurfer_volume
  freesurfer_volume="$(get_freesurfer_volume_name)"
  if [[ -n "$freesurfer_volume" ]]; then
    export FREESURFER_VOLUME="$freesurfer_volume"
  fi

  # Bring down any containers from a previous (older-image) run first so they
  # release the old FreeSurfer volume; otherwise pruning fails with
  # "volume is in use" and the stale volume lingers.
  docker compose -f "$DOCKER_COMPOSE_FILE" down >/dev/null 2>&1 || true
  prune_old_freesurfer_volumes "$freesurfer_volume"

  ensure_images_pulled

  echo "Starting services..."
  docker compose -f "$DOCKER_COMPOSE_FILE" up -d

  echo "Waiting for services to initialize..."
  sleep 3

  echo "Copying development codebase to container..."
  if [ -d "$DEV_CODEBASE_DIR" ]; then
    docker cp "$DEV_CODEBASE_DIR/." simnibs_container:/ti-toolbox/
    echo "✓ Development codebase copied to container"
  else
    echo "Warning: Development codebase directory $DEV_CODEBASE_DIR not found"
  fi

  if ! docker ps --format '{{.Names}}' | grep -qx "simnibs_container"; then
    echo "Error: simnibs service is not running. Please check your docker-compose.dev.yml and container logs."
    docker compose -f "$DOCKER_COMPOSE_FILE" logs
    exit 1
  fi

  echo "Initializing project (inside container)..."
  run_project_init_in_container "$PROJECT_DIR_NAME"

  echo "Attaching to the simnibs_container..."
  # A non-zero exit from the interactive shell must not skip the teardown below.
  docker exec -ti simnibs_container bash || true

  docker compose -f "$DOCKER_COMPOSE_FILE" down

  if command -v xhost >/dev/null 2>&1; then
    xhost -local:root >/dev/null 2>&1 || true
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  if [[ ! -f "$DOCKER_COMPOSE_FILE" ]]; then
    echo "Error: docker-compose.dev.yml not found in $SCRIPT_DIR. Please make sure the file is present."
    exit 1
  fi

  check_docker_available
  display_welcome
  setup_path_completion

  load_default_paths
  get_project_directory
  get_dev_codebase_directory

  # Sanitize possible carriage returns and a trailing slash from user input
  # paths (tab-completion on a directory typically appends one, which would
  # otherwise make ${VAR##*/} resolve to an empty name).
  LOCAL_PROJECT_DIR=${LOCAL_PROJECT_DIR%$'\r'}
  DEV_CODEBASE_DIR=${DEV_CODEBASE_DIR%$'\r'}
  LOCAL_PROJECT_DIR=${LOCAL_PROJECT_DIR%/}
  DEV_CODEBASE_DIR=${DEV_CODEBASE_DIR%/}
  PROJECT_DIR_NAME="$(basename "$LOCAL_PROJECT_DIR")"
  DEV_CODEBASE_DIR_NAME="$(basename "$DEV_CODEBASE_DIR")"

  save_default_paths

  if [[ "$OS_TYPE" == "Darwin" ]]; then
    setup_macos_x11
  fi
  set_display_env

  export LOCAL_PROJECT_DIR
  export PROJECT_DIR_NAME
  export DEV_CODEBASE_DIR
  export DEV_CODEBASE_NAME="$DEV_CODEBASE_DIR_NAME"
  TZ="$(get_host_timezone)"
  TIT_USER_CONFIG="$(get_user_config_dir)"
  TIT_HOST_OS="$(echo "$OS_TYPE" | tr '[:upper:]' '[:lower:]')"
  TIT_HOST_OS_VERSION="$(uname -r)"
  TIT_HOST_ARCH="$(uname -m)"
  export TZ TIT_USER_CONFIG TIT_HOST_OS TIT_HOST_OS_VERSION TIT_HOST_ARCH

  if [[ "$OS_TYPE" == "Darwin" ]]; then
    # macOS needs these settings for OpenGL to work in Docker.
    export LIBGL_ALWAYS_SOFTWARE="1"
    export LIBGL_ALWAYS_INDIRECT="1"
    export QT_X11_NO_MITSHM="1"
    export QT_OPENGL="desktop"
    export TI_GUI_QGL_FALLBACK="1"
  fi

  write_system_info

  run_docker_compose
}

main "$@"
