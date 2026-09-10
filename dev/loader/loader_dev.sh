#!/usr/bin/env bash
# Run this checkout inside Docker; no host Python required.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
export TIT_DEV_REPO_DIR="$REPO"
export TIT_LAUNCH_UI=browser
exec bash "$REPO/loader.sh" "$@"
