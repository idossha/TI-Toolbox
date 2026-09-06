#!/usr/bin/env bash
# Fixes a real upstream packaging defect in the simnibs-4.6.0 macOS arm64
# wheel: its 3 CGAL Cython extensions (mesh_tools/cgal/*.so) were built with
# an absolute, non-relocatable LC_RPATH baked in --
# `/Users/axelt/miniforge3/envs/simnibs_dev/lib` (the SimNIBS developer's own
# machine) -- so `import simnibs` fails everywhere else with
# "Library not loaded: @rpath/libmpfr.6.dylib" (see REPORT.md).
#
# Fix: obtain libmpfr/libgmp from conda-forge (same mpfr=4.2.1 pin
# environment_macos.yml lists) via micromamba, copy them into the runtime,
# and add a *working* rpath to the three affected extensions with
# install_name_tool (their existing bad rpath is left in place --
# dyld tries every LC_RPATH entry in order, so an extra one is enough; it
# does not need to be removed). libc++.1.dylib and libz.1.dylib are also
# @rpath-referenced but resolve via dyld's fallback search of /usr/lib, so
# they need no action.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_LIB="$HERE/mm/mumbaenv/lib"
RUNTIME="$HERE/runtime-macos-arm64"
SP="$RUNTIME/lib/python3.11/site-packages"
DEST="$SP/simnibs/mesh_tools/cgal/.dylibs"

mkdir -p "$DEST"
cp -L "$CONDA_LIB/libmpfr.6.dylib" "$DEST/libmpfr.6.dylib"
cp -L "$CONDA_LIB/libgmp.10.dylib" "$DEST/libgmp.10.dylib"
cd "$DEST"
install_name_tool -id "@loader_path/libmpfr.6.dylib" libmpfr.6.dylib
install_name_tool -id "@loader_path/libgmp.10.dylib" libgmp.10.dylib
# libmpfr itself links libgmp -- repoint that too.
for dep in $(otool -L libmpfr.6.dylib | tail -n +2 | awk '{print $1}' | grep '^@rpath/'); do
  install_name_tool -change "$dep" "@loader_path/$(basename "$dep")" libmpfr.6.dylib
done
codesign --force --sign - libmpfr.6.dylib libgmp.10.dylib >/dev/null 2>&1 || true

for ext in create_mesh_surf create_mesh_vol cgal_misc; do
  f="$SP/simnibs/mesh_tools/cgal/${ext}.cpython-311-darwin.so"
  install_name_tool -add_rpath "@loader_path/.dylibs" "$f" 2>/dev/null || true
  # libc++.1.dylib / libz.1.dylib are also @rpath-referenced but are *system*
  # libraries (always at /usr/lib on macOS) -- @rpath lookups do NOT fall
  # back to /usr/lib automatically (that only happens for bare, non-@rpath
  # library names), so add it explicitly.
  install_name_tool -add_rpath "/usr/lib" "$f" 2>/dev/null || true
  codesign --force --sign - "$f" >/dev/null 2>&1 || true
done

echo "Grafted libmpfr/libgmp into $DEST"
