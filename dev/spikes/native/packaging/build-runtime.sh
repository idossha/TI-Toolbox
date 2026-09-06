#!/usr/bin/env bash
# Build a minimal python-build-standalone runtime for the N0.4 packaging spike.
# NOT the full SimNIBS runtime (that's lane N0.1) -- headless tit.server deps only,
# so the packaging mechanics (extraResources, signing, spawn/kill) can be proven
# without a multi-hour, multi-GB build.
set -euo pipefail

PBS_TAG="20260901"
PY_VER="3.11.16"
TRIPLE="aarch64-apple-darwin"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOADS="$ROOT/downloads"
RUNTIME_DIR="$ROOT/runtime"
TIT_REPO="${TIT_REPO:-/Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui}"

mkdir -p "$DOWNLOADS"
ARCHIVE="cpython-${PY_VER}+${PBS_TAG}-${TRIPLE}-install_only.tar.gz"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${ARCHIVE}"

if [ ! -f "$DOWNLOADS/$ARCHIVE" ]; then
  echo "==> downloading $URL"
  curl -sL -o "$DOWNLOADS/$ARCHIVE" "$URL"
fi
echo "==> archive size: $(du -h "$DOWNLOADS/$ARCHIVE" | cut -f1)"

rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR"
echo "==> extracting"
tar -xzf "$DOWNLOADS/$ARCHIVE" -C "$RUNTIME_DIR" --strip-components=1

PY="$RUNTIME_DIR/bin/python3.11"
echo "==> interpreter: $("$PY" -c 'import sys; print(sys.version)')"

echo "==> pip install runtime deps"
"$PY" -m pip install --quiet --no-input --disable-pip-version-check \
  fastapi 'uvicorn[standard]' pydantic pyyaml psutil numpy nibabel

echo "==> pip install tit (non-editable, self-contained copy)"
"$PY" -m pip install --quiet --no-input --disable-pip-version-check "$TIT_REPO"

echo "==> smoke: import tit.server.app"
"$PY" -c "import tit.server.app; print('tit.server.app imports OK, tit version', __import__('tit').__version__)"

echo "==> runtime tree size: $(du -sh "$RUNTIME_DIR" | cut -f1)"
echo "==> done"
