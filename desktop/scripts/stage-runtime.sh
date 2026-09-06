#!/usr/bin/env bash
# Copies $TIT_RUNTIME_DIR into .runtime-staging/<platform-arch>, a fixed relative path
# electron-builder.yml's extraResources.from points at.
#
# WHY THIS SCRIPT EXISTS, NOT A ${env.TIT_RUNTIME_DIR} MACRO IN electron-builder.yml DIRECTLY: see
# electron-builder.yml's own comment above the extraResources block. In short — electron-builder
# 26.15.3 resolves an extraResources `from:` path with `path.resolve(projectDir, pattern.from)`
# BEFORE expanding `${env.X}` macros, so a still-relative macro TOKEN gets resolved against the
# project directory first and only THEN has the real (absolute) value substituted into the middle of
# that already-wrong string. Reproduced once during this spike (dev/spikes/native/packaging/REPORT.md):
#   file source doesn't exist  from=.../desktop//private/tmp/.../packaging/runtime
# Staging to a real, fixed, relative path sidesteps the bug entirely and is also just an accurate
# preview of what a real CI runtime-build pipeline will hand this same electron-builder.yml in Stage
# N1 (dev/notes/v3-native-desktop-plan.md §2) — a real pipeline stages its freshly-built runtime tree
# at this same path too, it just does not come from a scratch/ directory.
#
# TARGET_ARCH selects the .runtime-staging/<name> subdirectory (matches nativeRuntime.ts's
# nativePlatformArch() naming: darwin-arm64 / linux-x64 / win32-x64). Defaults to darwin-arm64, the
# only target this spike built and measured.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ARCH="${TIT_NATIVE_TARGET_ARCH:-darwin-arm64}"
DEST="$ROOT/.runtime-staging/$TARGET_ARCH"

if [ -z "${TIT_RUNTIME_DIR:-}" ]; then
  echo "stage-runtime.sh: TIT_RUNTIME_DIR is not set (point it at a python-build-standalone" >&2
  echo "  runtime tree, e.g. the output of dev/spikes/native/packaging/build-runtime.sh)" >&2
  exit 1
fi
if [ ! -d "$TIT_RUNTIME_DIR" ]; then
  echo "stage-runtime.sh: TIT_RUNTIME_DIR does not exist: $TIT_RUNTIME_DIR" >&2
  exit 1
fi

echo "==> staging $TIT_RUNTIME_DIR -> $DEST"
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -R "$TIT_RUNTIME_DIR" "$DEST"
echo "==> staged: $(du -sh "$DEST" | cut -f1)"
