#!/usr/bin/env bash
# Reproducible from nothing: builds a native SimNIBS 4.6.0 + tit runtime out
# of a python-build-standalone CPython 3.11, following SimNIBS's own
# environment_macos.yml exactly (fetched live from the v4.6.0 release), with
# two upstream packaging gaps worked around (see graft_mumps.sh,
# graft_cgal_libs.sh, and REPORT.md "What this proves / does not prove").
#
# Scope of this spike: macOS arm64 only (this Mac). Windows x64 / Linux
# x86_64 are proven only at the "every wheel URL in their environment_*.yml
# resolves with a real size" level -- see wheels-win_amd64/manifest.json and
# wheels-manylinux_x86_64/manifest.json, produced by resolve-other-platforms.sh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PBS_TAG="20260901"
PBS_ASSET="cpython-3.11.16+20260901-aarch64-apple-darwin-install_only.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$PBS_ASSET")"
PBS_SHA256="50424fa409e8ae84b82a3052522f64695b47dff2158b70bb7358e0ebd6c085c9"

REPO_ROOT="${TIT_REPO_ROOT:-$(cd "$HERE/../../../../../.." && pwd)}"
if [ ! -f "$REPO_ROOT/pyproject.toml" ] && [ ! -f "$REPO_ROOT/setup.py" ]; then
  echo "Set TIT_REPO_ROOT to the TI-Toolbox repo checkout (tit package)." >&2
  exit 1
fi

echo "== 1. python-build-standalone CPython 3.11 (aarch64-apple-darwin) =="
mkdir -p downloads
if [ ! -f "downloads/$(basename "$PBS_ASSET")" ]; then
  curl -sL -o "downloads/cpython-3.11.16-aarch64-apple-darwin-install_only.tar.gz" "$PBS_URL"
fi
echo "$PBS_SHA256  downloads/cpython-3.11.16-aarch64-apple-darwin-install_only.tar.gz" | shasum -a 256 -c -
rm -rf runtime-macos-arm64
tar xzf downloads/cpython-3.11.16-aarch64-apple-darwin-install_only.tar.gz -C .
mv python runtime-macos-arm64
PY=./runtime-macos-arm64/bin/python3
"$PY" -m pip install --upgrade pip -q

echo "== 2. environment_macos.yml -- fetch live, install exactly what it pins =="
curl -sL https://github.com/simnibs/simnibs/releases/download/v4.6.0/environment_macos.yml -o environment_macos.yml

# 2a. numpy/scipy first (mumps and simnibs's own extensions link against them).
"$PY" -m pip install -q "numpy==2.3.0" "scipy==1.17.1"

# 2b. GitHub-release wheels named in the yml (--no-deps to keep upstream's pins
# exact; simnibs's own declared deps are satisfied explicitly below instead of
# letting pip's resolver reorder/upgrade anything).
mkdir -p downloads/wheels
declare -A GH_WHEELS=(
  [simnibs]="https://github.com/simnibs/simnibs/releases/download/v4.6.0/simnibs-4.6.0-cp311-cp311-macosx_11_0_arm64.whl"
  [petsc4py]="https://github.com/simnibs/petsc4py/releases/download/v3.22.2/petsc4py-3.22.2-cp311-cp311-macosx_14_0_arm64.whl"
  [fmm3dpy]="https://github.com/simnibs/fmm3dpy/releases/download/v1.0.4/fmm3dpy-1.0.4-cp311-cp311-macosx_14_0_arm64.whl"
  [cortech]="https://github.com/simnibs/cortech/releases/download/v0.1/cortech-0.1-cp311-cp311-macosx_11_0_arm64.whl"
  [samseg]="https://github.com/oulap/samseg_wheels/releases/download/dev/samseg-0.5a0-cp311-cp311-macosx_14_0_arm64.whl"
)
for name in "${!GH_WHEELS[@]}"; do
  url="${GH_WHEELS[$name]}"
  f="downloads/wheels/$(basename "$url")"
  [ -f "$f" ] || curl -sL -o "$f" "$url"
done
"$PY" -m pip install -q --no-deps downloads/wheels/*.whl

# 2c. brainnet/brainsynth built from git source at install time (per the yml).
"$PY" -m pip install -q \
  "brainnet@git+https://github.com/simnibs/brainnet@v0.2" \
  "brainsynth@git+https://github.com/simnibs/brainsynth@v0.1"

# 2d. remaining pins from the yml's `pip:` block + `[project]dependencies`
# that aren't covered above.
"$PY" -m pip install -q \
  "gmsh==4.14.0" "h5py==3.15.1" "nibabel==5.3.3" "numba==0.64.0" \
  "pygpc==0.4.4" "pyqt5==5.15.11" "torch==2.6.0" \
  "jsonschema==4.26.0" "pillow==12.1.1" "requests==2.32.5" "mock==5.2.0" \
  "pyopengl==3.1.10" "matplotlib==3.10.8"

# 2e. samseg's own transitive deps -- NOT listed in environment_macos.yml
# (upstream's yml uses --no-deps implicitly via its own pinned-everything
# design; samseg's wheel metadata declares these two, uncovered above).
"$PY" -m pip install -q \
  "ml-dtypes==0.4.1" \
  "surfa @ git+https://github.com/freesurfer/surfa.git@ec5ddb193fd1caf22ec654c457b5678f6bd8e460"

echo "== 3. python-mumps: conda-only, no PyPI wheel -- graft via micromamba =="
if [ ! -x mm/bin/micromamba ]; then
  mkdir -p mm
  curl -Ls https://micro.mamba.pm/api/micromamba/osx-arm64/latest -o mm/micromamba.tar.bz2
  tar xjf mm/micromamba.tar.bz2 -C mm bin/micromamba
fi
export MAMBA_ROOT_PREFIX="$HERE/mm/root"
if [ ! -d mm/mumbaenv ]; then
  mm/bin/micromamba create -y -p "$HERE/mm/mumbaenv" -c conda-forge python=3.11 python-mumps mpfr=4.2.1
else
  mm/bin/micromamba install -y -p "$HERE/mm/mumbaenv" -c conda-forge mpfr=4.2.1
fi
./graft_mumps.sh

echo "== 4. simnibs wheel's CGAL extensions: non-relocatable rpath -- graft libmpfr/libgmp =="
./graft_cgal_libs.sh

echo "== 5. pip check =="
"$PY" -m pip check

echo "== 6. tit + pure-Python deps =="
"$PY" -m pip install -q --no-deps -e "$REPO_ROOT"
"$PY" -m pip install -q \
  nibabel mne nilearn pandas joblib matplotlib fastapi uvicorn pydantic pyyaml psutil
# bpy intentionally NOT installed (size; see REPORT.md).

"$PY" -m pip check
echo "== done: $(du -sh runtime-macos-arm64 | cut -f1) at $HERE/runtime-macos-arm64 =="
