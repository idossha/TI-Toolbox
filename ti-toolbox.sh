#!/usr/bin/env bash
# ti-toolbox.sh — start the TI-Toolbox UI in a browser, without Electron.
#
#   ./ti-toolbox.sh --project ~/datasets/000
#   ./ti-toolbox.sh --project ~/datasets/000 --status | --logs | --stop
#   curl -fsSL https://raw.githubusercontent.com/idossha/TI-Toolbox/main/ti-toolbox.sh | bash -s -- --project ~/datasets/000
#
# This script is a BOOTSTRAP, not a second launcher: every flag is passed straight through to
# `tit launch` (tit/launch.py), which owns the run spec. That is deliberate — a `docker run`
# written out again in bash would drift from the Electron app's container on the first change to
# a label, a mount or an environment variable, and the two would stop being interchangeable.
# All this file does is find a Python that can import `tit`, in this order:
#
#   1. $TIT_PYTHON, if set.
#   2. A CPython >= 3.11 on PATH that can already import `tit` (a pip/pipx install).
#   3. This repository, if the script is running from a checkout (PYTHONPATH=<repo root>).
#   4. A cached virtualenv at ~/.cache/ti-toolbox/venv, created and pip-installed on first use
#      (from the checkout when there is one, otherwise from PyPI).
#
# Requirements on the host: bash, CPython >= 3.11, and the `docker` CLI with a running daemon.
# NOT required: SimNIBS, Node, Electron, or any Python package outside the standard library —
# the toolbox itself lives in the container.

set -euo pipefail

VENV_DIR="${TIT_VENV_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/ti-toolbox/venv}"

die() { printf 'ti-toolbox: %s\n' "$*" >&2; exit 1; }
note() { printf 'ti-toolbox: %s\n' "$*" >&2; }

# The repository root when this file is being run from a checkout; empty when it was piped from
# curl (BASH_SOURCE is then "bash" or a pipe, and pyproject.toml is not next to it).
repo_root() {
    local src="${BASH_SOURCE[0]:-}"
    [ -f "$src" ] || return 0
    local dir
    dir="$(cd "$(dirname "$src")" && pwd)"
    [ -f "$dir/pyproject.toml" ] && [ -d "$dir/tit" ] && printf '%s' "$dir"
}

# True when $1 is a CPython >= 3.11. `tit` declares requires-python >= 3.11 and uses `X | None`
# annotations at import time, so an older interpreter fails with a TypeError rather than a clear
# message — checking here is what turns that into one.
python_ok() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

find_python() {
    local candidate
    if [ -n "${TIT_PYTHON:-}" ]; then
        python_ok "$TIT_PYTHON" || die "TIT_PYTHON=$TIT_PYTHON is not a CPython >= 3.11"
        printf '%s' "$TIT_PYTHON"; return 0
    fi
    for candidate in python3.14 python3.13 python3.12 python3.11 python3 python; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        python_ok "$candidate" && { command -v "$candidate"; return 0; }
    done
    return 1
}

command -v docker >/dev/null 2>&1 || die \
    "Docker was not found. Install Docker Desktop (macOS/Windows) or Docker Engine (Linux) first."
docker version --format '{{.Server.APIVersion}}' >/dev/null 2>&1 || die \
    "Docker is installed but not running. Start Docker Desktop (or your Docker daemon) and retry."

PYTHON="$(find_python || true)"
[ -n "$PYTHON" ] || die "no CPython >= 3.11 found on PATH. Install one, or set TIT_PYTHON=/path/to/python3."

REPO="$(repo_root || true)"

# 2. an installed `tit`
if "$PYTHON" -c 'import tit.launch' >/dev/null 2>&1; then
    exec "$PYTHON" -m tit.cli launch "$@"
fi

# 3. this checkout, imported in place — no install, no venv, nothing written anywhere
if [ -n "$REPO" ]; then
    exec env PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" -m tit.cli launch "$@"
fi

# 4. a cached venv. Only reached when the script was piped from curl on a host with no `tit`
# installed, which is the one case where writing to the user's disk is the only way forward.
if [ ! -x "$VENV_DIR/bin/python" ]; then
    note "installing tit into $VENV_DIR (first run only)"
    "$PYTHON" -m venv "$VENV_DIR" || die "could not create a virtualenv at $VENV_DIR"
    "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
    "$VENV_DIR/bin/python" -m pip install --quiet tit \
        || die "could not install tit from PyPI. Clone the repository and run ./ti-toolbox.sh from it instead."
fi
exec "$VENV_DIR/bin/python" -m tit.cli launch "$@"
