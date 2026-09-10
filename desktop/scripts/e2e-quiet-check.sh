#!/usr/bin/env bash
# Sample native macOS metadata while the command runs in an isolated process session.
# Fail for any sampled test descendant's window/focus, regardless of its app name.
# Unrelated ancestry is noted; missing/ambiguous attribution exits 2, never PASS.
# No window titles, screenshots, process arguments or environments are collected.
# Usage: scripts/e2e-quiet-check.sh [command ...] (default: npm run e2e)
set -uo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
  echo "e2e-quiet-check: ERROR — native attribution requires macOS" >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
if ! clang -fobjc-arc -o "$WORK/snapshot" "$ROOT/scripts/e2e-quiet-snapshot.m" -framework AppKit -framework ApplicationServices; then
  echo "e2e-quiet-check: ERROR — cannot build native metadata sampler" >&2
  exit 2
fi
cd "$ROOT" || exit 2
python3 scripts/e2e_quiet_monitor.py --snapshot "$WORK/snapshot" -- "$@"
