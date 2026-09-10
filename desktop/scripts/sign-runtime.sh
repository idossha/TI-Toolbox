#!/usr/bin/env bash
# Walks a bundled Python runtime tree and ad-hoc-signs every Mach-O binary in it, inside-out
# (dylibs/.so extension modules before plain executables) — the notarization-cost measurement
# r4-python-in-electron.md §8 risk 2 flagged as unmeasured ("nobody has assembled the native
# runtime and [signed it] yet"). Ad-hoc (`-s -`), not a Developer ID: N0.4 does not look for or use
# signing secrets (see electron-builder.yml's own header comment). A real release build with a real
# identity runs the SAME walk, substituting `-s "$IDENTITY"` for `-s -` and dropping `--timestamp=none`
# (a real submission needs a real timestamp authority) — everything else here is unchanged.
#
# WHY THIS IS NEEDED AT ALL, given every Mach-O this spike inspected already carries an *implicit*
# ad-hoc signature (`codesign -dv` on a freshly-extracted python-build-standalone binary or a
# `pip install`-built wheel's .so already shows `flags=0x20002(adhoc,linker-signed)` — Apple Silicon's
# linker (ld64, Xcode 12+/Big Sur+) ad-hoc-signs every Mach-O it produces by default): that default
# signature has NO entitlements and NO `--options runtime` (hardened runtime) flag, and is replaced
# wholesale — not merged — by a real Developer ID signing pass in a production build. This script's
# purpose in Stage N0 is exclusively to MEASURE that pass's cost on a representative tree, not to fix
# anything that is currently broken (this spike's own e2e proves the unsigned/default-signed tree
# already launches and runs fine locally, REPORT.md).
#
# Usage: scripts/sign-runtime.sh <runtime-dir> [codesign-identity, default "-" (ad-hoc)] [entitlements-plist]
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "sign-runtime.sh: macOS only (codesign is not a thing anywhere else)." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${1:?usage: sign-runtime.sh <runtime-dir> [identity] [entitlements-plist]}"
IDENTITY="${2:--}"
ENTITLEMENTS="${3:-$ROOT/build/entitlements.mac.plist}"
if [ ! -d "$RUNTIME_DIR" ]; then
  echo "sign-runtime.sh: not a directory: $RUNTIME_DIR" >&2
  exit 1
fi
if [ ! -f "$ENTITLEMENTS" ]; then
  echo "sign-runtime.sh: entitlements plist not found: $ENTITLEMENTS" >&2
  exit 1
fi

# EMPIRICALLY REQUIRED, not belt-and-braces (found and fixed during this spike, REPORT.md): signing
# WITHOUT `--entitlements` here (an earlier version of this script did exactly that) produces a
# runtime that Electron can still spawn but that then fails on its own first `import numpy` with
#   dlopen(...): tried: '.../_multiarray_umath....so' (code signature ... not valid for use in
#   process: mapping process and mapped file (non-platform) have different Team IDs)
# `--options runtime` (hardened runtime) turns ON library validation for the interpreter, and every
# file here is signed AD HOC (`-s -`) — each with its own distinct, team-less identity — so the
# interpreter (the *loading* process) refuses to `dlopen` any of its own extension modules unless
# ITS OWN signature carries `com.apple.security.cs.disable-library-validation` (this repo's
# `build/entitlements.mac.plist`, same file `electron-builder.yml` signs the outer app with). This
# is r4-python-in-electron.md §3.2's Apple-Forum-sourced claim, now independently reproduced against
# a real interpreter loading its own real extension modules, not merely asserted from a doc search.

# Mach-O detection by content (`file`), not extension: python-build-standalone's own interpreter
# binaries (bin/python3.11) and every SimNIBS sibling binary the real runtime will carry
# (meshfix, mmg3d_O3, dwi2cond — r4 §2.3) have no extension at all, so a `-name "*.dylib" -o -name
# "*.so"` filter alone (as electron-builder.yml's own header comment sketches for illustration)
# would silently skip every one of them.
mapfile -d '' ALL_FILES < <(find "$RUNTIME_DIR" -type f -print0)

echo "==> scanning $(printf '%d' "${#ALL_FILES[@]}") files under $RUNTIME_DIR for Mach-O binaries…"

DYLIBS=()
EXECUTABLES=()
for f in "${ALL_FILES[@]}"; do
  case "$f" in
  *.dylib | *.so) is_dylib=1 ;;
  *) is_dylib=0 ;;
  esac
  # `file -b` output for a Mach-O starts with "Mach-O"; a plain-text/data file never does. One
  # `file` call per candidate is the dominant cost here (see REPORT.md timing) — this is exactly
  # the cost a real multi-GB SimNIBS runtime's walk-and-sign step pays too, just scaled up.
  kind="$(file -b "$f" 2>/dev/null || true)"
  case "$kind" in
  Mach-O*)
    if [ "$is_dylib" -eq 1 ]; then
      DYLIBS+=("$f")
    else
      EXECUTABLES+=("$f")
    fi
    ;;
  esac
done

TOTAL=$((${#DYLIBS[@]} + ${#EXECUTABLES[@]}))
echo "==> found ${#DYLIBS[@]} dylib/.so + ${#EXECUTABLES[@]} other executable Mach-O binaries ($TOTAL total)"

START=$(date +%s)

# Inside-out: every dylib/.so extension module first (nothing else in this tree links against an
# executable), then the plain executables — matches the brief's ordering and r4 §5.3's own
# recommendation ("signing leaves-first… before the interpreter binary itself").
if [ "${#DYLIBS[@]}" -gt 0 ]; then
  echo "==> signing ${#DYLIBS[@]} dylibs/.so extension modules…"
  codesign --force --options runtime --timestamp=none --entitlements "$ENTITLEMENTS" -s "$IDENTITY" "${DYLIBS[@]}"
fi
if [ "${#EXECUTABLES[@]}" -gt 0 ]; then
  echo "==> signing ${#EXECUTABLES[@]} executables…"
  codesign --force --options runtime --timestamp=none --entitlements "$ENTITLEMENTS" -s "$IDENTITY" "${EXECUTABLES[@]}"
fi

END=$(date +%s)
ELAPSED=$((END - START))
if [ "$TOTAL" -gt 0 ]; then
  RATE=$(awk -v t="$TOTAL" -v s="$ELAPSED" 'BEGIN { if (s == 0) s = 1; printf "%.1f", t / s }')
else
  RATE="n/a"
fi
echo "==> signed $TOTAL Mach-O binaries in ${ELAPSED}s ($(awk -v e="$ELAPSED" 'BEGIN{printf "%.2f", e/60}') min, ~${RATE} files/s)"

echo "==> spot-verifying 3 signatures…"
COUNT=0
for f in "${DYLIBS[@]}" "${EXECUTABLES[@]}"; do
  [ "$COUNT" -ge 3 ] && break
  codesign -dv "$f" 2>&1 | grep -E "^(Executable|Signature)="
  COUNT=$((COUNT + 1))
done
