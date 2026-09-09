#!/usr/bin/env bash
# Launch the checkout loader, or refresh a cached standalone install.
# Requires Python 3.11+ and Docker. Use --help for options.
# TIT_PYTHON selects Python; TIT_VENV_DIR selects the cache.
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

# Python owns Docker checks, after interactive settings have been collected.
# Keeping those checks here would prevent the no-argument setup from opening.

PYTHON="$(find_python || true)"
[ -n "$PYTHON" ] || die "no CPython >= 3.11 found on PATH. Install one, or set TIT_PYTHON=/path/to/python3."

REPO="$(repo_root || true)"

# 2. this checkout, imported in place — no install, no venv, nothing written anywhere.
# Before the installed-package branch, not after, for two reasons. Running a checkout's
# `./loader.sh` must run *that* checkout's code, not some older `tit` the user pip-installed
# once. And the probe below cannot tell the two apart from in here anyway: `python -c` puts the
# current directory on `sys.path`, so `import tit.launch` succeeds merely by virtue of being run
# from the repository root, and the run would then print `tit launch …` follow-up hints naming a
# command that may not exist on this machine at all.
if [ -n "$REPO" ]; then
    exec "$PYTHON" "$REPO/loader.py" "$@"
fi

# Management operates on existing containers, so a network outage must not block stopping them.
wants_management() {
    local arg
    for arg in "$@"; do
        case "$arg" in --stop|--status|--logs) return 0 ;; esac
    done
    return 1
}
if wants_management "$@" && [ -x "$VENV_DIR/bin/python" ] && \
    "$VENV_DIR/bin/python" -I -c 'from tit.cli import launch_command, launch_parser' >/dev/null 2>&1; then
    exec "$VENV_DIR/bin/python" -I -m tit.cli launch "$@"
fi

# A system installation may be an older release, so it cannot satisfy the main launcher.
# Keep the virtualenv but refresh its source, even when the package version has not changed.
if [ ! -x "$VENV_DIR/bin/python" ]; then
    note "creating launcher environment at $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR" || die "could not create a virtualenv at $VENV_DIR"
fi
note "refreshing launcher from TI-Toolbox main"
"$VENV_DIR/bin/python" -I -m pip install --quiet --upgrade --force-reinstall --no-deps \
    https://github.com/idossha/TI-toolbox/archive/refs/heads/main.zip \
    || die "could not refresh the launcher from main. Check your network, or clone the repository and run ./loader.sh from it."
exec "$VENV_DIR/bin/python" -I -m tit.cli launch "$@"
