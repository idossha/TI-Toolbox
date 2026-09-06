#!/usr/bin/env bash
# Grafts conda-forge's compiled MUMPS solver stack (python-mumps + its native
# dylib closure) into a pip-based python-build-standalone runtime.
#
# WHY: python-mumps has NO PyPI wheel for any platform -- only an sdist that
# needs the MUMPS/SCOTCH/METIS C/Fortran libraries at build time (see
# REPORT.md "MUMPS: the one conda-only dependency"). SimNIBS's own
# environment_macos.yml installs it from conda-forge (`python-mumps=0.0.6`).
# We build it with micromamba (a throwaway env, not touched by pip) and copy
# the compiled artifacts across, relinking with install_name_tool so every
# @rpath reference resolves via @loader_path inside the runtime instead of
# the conda prefix.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_LIB="$HERE/mm/mumbaenv/lib"
CONDA_SITE="$HERE/mm/mumbaenv/lib/python3.11/site-packages"
RUNTIME="$HERE/runtime-macos-arm64"
DEST_SITE="$RUNTIME/lib/python3.11/site-packages"
DYLIBS_DIR="$DEST_SITE/mumps/.dylibs"
EXT="$DEST_SITE/mumps/_mumps.cpython-311-darwin.so"

rm -rf "$DEST_SITE/mumps"
cp -R "$CONDA_SITE/mumps" "$DEST_SITE/mumps"
mkdir -p "$DYLIBS_DIR"

# Resolve the full transitive @rpath closure starting from the extension
# module (otool -L, recursive) instead of hand-maintaining a list -- this is
# what bit us twice during the spike (libquadmath, libgcc_s were missed by
# eye on the first two passes; see REPORT.md).
CLOSURE=$(python3 - "$EXT" "$CONDA_LIB" << 'PYEOF'
import subprocess, os, re, sys
ext, conda_lib = sys.argv[1], sys.argv[2]
seen, queue, closure = set(), [ext], set()
while queue:
    f = queue.pop()
    rf = os.path.realpath(f)
    if rf in seen:
        continue
    seen.add(rf)
    out = subprocess.run(["otool", "-L", f], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        m = re.match(r"\s+(\S+)", line)
        if not m:
            continue
        dep = m.group(1)
        if dep.startswith("@rpath/") or dep.startswith("@loader_path/"):
            base = os.path.basename(dep)
            candidate = os.path.join(conda_lib, base)
            if os.path.exists(candidate):
                closure.add(base)
                queue.append(candidate)
print("\n".join(sorted(closure)))
PYEOF
)

while IFS= read -r base; do
  [ -z "$base" ] && continue
  cp -L "$CONDA_LIB/$base" "$DYLIBS_DIR/$(basename "$(readlink -f "$CONDA_LIB/$base" 2>/dev/null || echo "$CONDA_LIB/$base")")" 2>/dev/null || true
  # also keep the exact @rpath basename as a symlink if it differs from the
  # real (dereferenced) filename, so every alias used in LC_LOAD_DYLIB lines
  # resolves inside this flat directory.
  real_name="$(basename "$(cd "$CONDA_LIB" && readlink -f "$base" 2>/dev/null || echo "$base")")"
  if [ "$real_name" != "$base" ]; then
    ln -sf "$real_name" "$DYLIBS_DIR/$base"
  fi
done <<< "$CLOSURE"

cd "$DYLIBS_DIR"
for f in *.dylib; do
  [ -L "$f" ] && continue
  install_name_tool -id "@loader_path/$f" "$f" 2>/dev/null || true
  for dep in $(otool -L "$f" | tail -n +2 | awk '{print $1}' | grep '^@rpath/'); do
    base="$(basename "$dep")"
    install_name_tool -change "$dep" "@loader_path/$base" "$f" 2>/dev/null || true
  done
done

install_name_tool -add_rpath "@loader_path/.dylibs" "$EXT" 2>/dev/null || true
for dep in $(otool -L "$EXT" | tail -n +2 | awk '{print $1}' | grep '^@rpath/'); do
  base="$(basename "$dep")"
  install_name_tool -change "$dep" "@rpath/$base" "$EXT" 2>/dev/null || true
done
codesign --force --sign - "$EXT" >/dev/null 2>&1 || true
for f in *.dylib; do [ -L "$f" ] || codesign --force --sign - "$f" >/dev/null 2>&1 || true; done

echo "Grafted mumps into $DEST_SITE/mumps ($(du -sh "$DEST_SITE/mumps" | cut -f1)), $(echo "$CLOSURE" | wc -l | tr -d ' ') dylibs in closure"
