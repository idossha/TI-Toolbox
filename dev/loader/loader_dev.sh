#!/usr/bin/env bash
# Thin shim for `bash loader.sh --dev <checkout>`; kept so existing muscle memory and
# a wrapper copied outside the checkout keep working. There is one launcher and one
# behaviour: --dev changes only the source of the server and renderer.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="${TIT_DEV_REPO_DIR-$HERE/../..}"
case "$REPO" in '~/'*) REPO="$HOME/${REPO#\~/}" ;; esac
if [ ! -f "$REPO/tit/launch.py" ] || [ ! -f "$REPO/loader.sh" ]; then
    printf 'loader_dev.sh: not a TI-Toolbox checkout: %s. Set TIT_DEV_REPO_DIR to your local checkout.\n' "$REPO" >&2
    exit 2
fi
REPO="$(cd "$REPO" && pwd -P)"
export TIT_DEV_REPO_DIR="$REPO"
if [ -z "${TIT_COMPOSE_FILE+x}" ] && [ -f "$HERE/docker-compose.yml" ]; then
    export TIT_COMPOSE_FILE="$HERE/docker-compose.yml"
fi
# TIT_DEV_REPO_DIR above is the environment spelling of --dev, so an argument-free
# invocation still reaches the interactive project prompt.
exec bash "$REPO/loader.sh" "$@"
