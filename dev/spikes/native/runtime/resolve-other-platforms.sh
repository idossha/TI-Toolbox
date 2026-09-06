#!/usr/bin/env bash
# Proves the win_amd64 / manylinux x86_64 wheel sets named in SimNIBS's own
# environment_windows.yml / environment_linux.yml actually resolve (HTTP 200,
# real size) -- does NOT install or run anything (no x86_64 machine here).
# Run from this directory.
set -euo pipefail
curl -sL https://github.com/simnibs/simnibs/releases/download/v4.6.0/environment_windows.yml -o environment_windows.yml
curl -sL https://github.com/simnibs/simnibs/releases/download/v4.6.0/environment_linux.yml -o environment_linux.yml

check() {
  local platform="$1"; shift
  echo "== $platform =="
  for u in "$@"; do
    local code size
    code=$(curl -sIL -o /dev/null -w "%{http_code}" "$u")
    size=$(curl -sIL "$u" | grep -i '^content-length' | tail -1 | tr -d '\r')
    printf '%-4s %-30s %s\n' "$code" "$size" "$u"
  done
}

check win_amd64 \
  "https://github.com/simnibs/simnibs/releases/download/v4.6.0/simnibs-4.6.0-cp311-cp311-win_amd64.whl" \
  "https://github.com/simnibs/petsc4py/releases/download/v3.22.2/petsc4py-3.22.2-cp311-cp311-win_amd64.whl" \
  "https://github.com/simnibs/fmm3dpy/releases/download/v1.0.4/fmm3dpy-1.0.4-cp311-cp311-win_amd64.whl" \
  "https://github.com/simnibs/cortech/releases/download/v0.1/cortech-0.1-cp311-cp311-win_amd64.whl" \
  "https://github.com/oulap/samseg_wheels/releases/download/dev/samseg-0.5a0-cp311-cp311-win_amd64.whl" \
  "https://download.pytorch.org/whl/cpu/torch-2.6.0%2Bcpu-cp311-cp311-win_amd64.whl"

check manylinux_x86_64 \
  "https://github.com/simnibs/simnibs/releases/download/v4.6.0/simnibs-4.6.0-cp311-cp311-linux_x86_64.whl" \
  "https://github.com/simnibs/petsc4py/releases/download/v3.22.2/petsc4py-3.22.2-cp311-cp311-manylinux_2_28_x86_64.whl" \
  "https://github.com/simnibs/fmm3dpy/releases/download/v1.0.4/fmm3dpy-1.0.4-cp311-cp311-manylinux_2_28_x86_64.whl" \
  "https://github.com/simnibs/cortech/releases/download/v0.1/cortech-0.1-cp311-cp311-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl" \
  "https://github.com/oulap/samseg_wheels/releases/download/dev/samseg-0.5a0-cp311-cp311-manylinux_2_28_x86_64.whl" \
  "https://download.pytorch.org/whl/cpu/torch-2.6.0%2Bcpu-cp311-cp311-linux_x86_64.whl"

echo
echo "python-mumps (win-64 / linux-64): conda-forge .conda packages exist for both"
echo "(api.anaconda.org/package/conda-forge/python-mumps lists osx-arm64, osx-64,"
echo "linux-64, linux-aarch64, linux-ppc64le, win-64) -- no PyPI wheel on any of them."
