#!/usr/bin/env bash
# Run a local checkout inside Docker; no host Python required.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="${TIT_DEV_REPO_DIR-$HERE/../..}"
case "$REPO" in '~/'*) REPO="$HOME/${REPO#\~/}" ;; esac
if [ ! -f "$REPO/tit/launch.py" ] || [ ! -f "$REPO/loader.sh" ]; then
    printf 'loader_dev.sh: not a TI-Toolbox checkout: %s. Set TIT_DEV_REPO_DIR to your local checkout.\n' "$REPO" >&2
    exit 2
fi
export TIT_DEV_REPO_DIR="$(cd "$REPO" && pwd -P)"
if [ -z "${TIT_COMPOSE_FILE+x}" ] && [ -f "$HERE/docker-compose.yml" ]; then
    export TIT_COMPOSE_FILE="$HERE/docker-compose.yml"
fi
export TIT_LAUNCH_UI="${TIT_LAUNCH_UI:-desktop}"
exec bash "$TIT_DEV_REPO_DIR/loader.sh" "$@"
