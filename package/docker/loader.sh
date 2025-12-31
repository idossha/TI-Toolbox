#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Error: docker-compose.yml not found next to loader.sh ($COMPOSE_FILE)"
  exit 1
fi

if [ -z "${LOCAL_PROJECT_DIR:-}" ]; then
  echo "LOCAL_PROJECT_DIR is required. Set it before running this script."
  exit 1
fi

PROJECT_DIR_NAME="${PROJECT_DIR_NAME:-$(basename "$LOCAL_PROJECT_DIR")}"
export LOCAL_PROJECT_DIR PROJECT_DIR_NAME

if [ -z "${TZ:-}" ]; then
  export TZ="$(date +%Z)"
fi

echo "Using docker-compose file: $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" up --build -d

echo "Attaching to simnibs_container..."
docker exec -ti simnibs_container bash /ti-toolbox/tit/cli/GUI.sh

echo "Stopping services..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans

