#!/usr/bin/env bash
# Find Python 3.11+ and forward all arguments to loader_dev.py.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

die() { printf 'loader_dev: %s\n' "$*" >&2; exit 1; }

python_ok() { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; }

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

PYTHON="$(find_python || true)"
[ -n "$PYTHON" ] || die "no CPython >= 3.11 found on PATH. Install one, or set TIT_PYTHON=/path/to/python3."

exec "$PYTHON" "$HERE/loader_dev.py" "$@"
