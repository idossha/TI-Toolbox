#!/usr/bin/env bash
# The regular loaders delegate container ownership to Electron before touching Docker.
# No dependency installation or renderer rebuild here: that could disturb an active dev session.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
command_args=()
if [ -n "${TIT_ELECTRON_EXECUTABLE:-}" ]; then
    [ -x "$TIT_ELECTRON_EXECUTABLE" ] || { printf 'TI-Toolbox: TIT_ELECTRON_EXECUTABLE must name an executable file.\n' >&2; exit 2; }
    command_args=("$TIT_ELECTRON_EXECUTABLE")
elif [ -x "$repo/desktop/node_modules/.bin/electron" ] && [ -f "$repo/desktop/out/main/index.js" ]; then
    command_args=("$repo/desktop/node_modules/.bin/electron" "$repo/desktop")
elif [ -x /Applications/TI-Toolbox.app/Contents/MacOS/TI-Toolbox ]; then
    command_args=(/Applications/TI-Toolbox.app/Contents/MacOS/TI-Toolbox)
elif [ -x "$HOME/Applications/TI-Toolbox.app/Contents/MacOS/TI-Toolbox" ]; then
    command_args=("$HOME/Applications/TI-Toolbox.app/Contents/MacOS/TI-Toolbox")
elif command -v ti-toolbox >/dev/null 2>&1; then
    command_args=("$(command -v ti-toolbox)")
else
    printf 'TI-Toolbox: Electron is unavailable. Install the desktop app and set TIT_ELECTRON_EXECUTABLE to its executable, or run npm ci and npm run build in desktop/. Use --browser explicitly for browser mode.\n' >&2
    exit 2
fi
if [ "${1:-}" = --check ]; then exit 0; fi
[ "$#" = 0 ] || { printf 'Usage: launch-electron.sh [--check]\n' >&2; exit 2; }
# Node's Electron mode must not leak in from an editor's environment.
unset ELECTRON_RUN_AS_NODE TIT_LAUNCH_CONTAINER_ID TIT_DEV_SERVER_URL TIT_DEV_SERVER_TOKEN TIT_IMAGE_TAG
unset ELECTRON_RENDERER_URL TIT_DEV_REPO_DIR TIT_REPO_DIR TIT_STATIC_DIR TIT_SERVER_RELOAD
"${command_args[@]}"
printf 'TI-Toolbox closed.\n'
