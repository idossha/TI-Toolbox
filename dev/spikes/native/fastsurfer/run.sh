#!/usr/bin/env bash
# Reproducible spike script: clone FastSurfer, build a native arm64 py3.11
# venv, download the aparc/DKT checkpoints, and run --seg_only on sub-ernie's
# T1w, timing wall-clock and peak RSS. Rebuilds from nothing.
#
# Usage: WORKDIR=/path/to/scratch T1=/path/to/T1.nii.gz bash run.sh
set -euo pipefail

WORKDIR="${WORKDIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
T1="${T1:-/Users/idohaber/datasets/000/sub-ernie/anat/sub-ernie_T1w.nii.gz}"
SID="${SID:-sub-ernie}"
FASTSURFER_TAG="${FASTSURFER_TAG:-v2.5.4}"
THREADS="${THREADS:-8}"   # M2 Max performance-core count; hw.physicalcpu=12 total (8P+4E)

echo "== WORKDIR=$WORKDIR"
echo "== T1=$T1"
echo "== FASTSURFER_TAG=$FASTSURFER_TAG  THREADS=$THREADS"

cd "$WORKDIR"

if [[ ! -d FastSurfer ]]; then
  git clone https://github.com/Deep-MI/FastSurfer.git
fi
cd FastSurfer
git fetch --tags --quiet
git checkout --quiet "$FASTSURFER_TAG"
echo "== FastSurfer commit: $(git rev-parse HEAD)"

# Native arm64 Python 3.11 (uv-managed; falls back to whatever `uv python
# install 3.11` resolves to if not already present).
uv python install 3.11 >/dev/null 2>&1 || true
uv venv --python 3.11 .venv

# requirements.txt is auto-generated for a Linux CUDA container running
# Python 3.12 and pins python>=3.12-only packages (tifffile) -- install from
# pyproject.toml's own (looser, cross-platform) dependency set instead. This
# resolves torch==2.7.1 for macOS arm64 automatically (no separate index/
# extra needed on macOS -- CPU/MPS wheels are the only wheels PyPI ships).
uv pip install --python .venv/bin/python -e .

export FASTSURFER_HOME="$(pwd)"
.venv/bin/python FastSurferCNN/download_checkpoints.py --vinn

OUT="$WORKDIR/out"
mkdir -p "$OUT"

# --seg_only + --no_cereb --no_hypothal: this spike scopes to the one
# output the toolbox actually needs (aparc.DKTatlas+aseg.deep.mgz, see
# r3-parcellation-alternatives.md ranked recommendation #2). CerebNet/
# HypVINN are separate checkpoints/models FastSurfer runs by default under
# plain --seg_only; skipped here to keep the spike inside its time box.
/usr/bin/time -l ./run_fastsurfer.sh \
  --t1 "$T1" \
  --sid "$SID" \
  --sd "$OUT" \
  --seg_only \
  --no_cereb \
  --no_hypothal \
  --device cpu \
  --threads "$THREADS" \
  --py "$(pwd)/.venv/bin/python3" \
  --allow_root

echo "== Output file list =="
find "$OUT/$SID" -type f | sort
