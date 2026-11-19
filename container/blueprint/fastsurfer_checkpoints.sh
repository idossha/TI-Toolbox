#!/bin/sh
# fastsurfer_checkpoints.sh — install FastSurfer's --vinn checkpoints during the image build.
#
# Default: FastSurfer's own downloader from the official host (TLS-verified).
# Optional: a mirror archive, for official-host outages (TLS-chain failure + Zenodo 504,
# 2026-09-09). build.sh passes FASTSURFER_CHECKPOINTS_TGZ and FASTSURFER_CHECKPOINTS_SHA256;
# the archive's bytes are verified before it is read, and only the three named checkpoints
# are extracted to fixed destinations, never to paths the archive chooses.
#
# Needs FASTSURFER_HOME; tests/test_checkpoint_build.py runs this script directly.
set -eu

if [ -n "${FASTSURFER_CHECKPOINTS_TGZ:-}" ]; then
    printf '%s' "${FASTSURFER_CHECKPOINTS_SHA256:-}" | grep -Eq '^[0-9a-f]{64}$'
    curl -fsSL "$FASTSURFER_CHECKPOINTS_TGZ" -o /tmp/fastsurfer-checkpoints.tgz
    echo "$FASTSURFER_CHECKPOINTS_SHA256  /tmp/fastsurfer-checkpoints.tgz" | sha256sum -c -
    mkdir -p "${FASTSURFER_HOME}/checkpoints"
    for plane in axial coronal sagittal; do
        file="aparc_vinn_${plane}_v2.0.0.pkl"
        tar -xzOf /tmp/fastsurfer-checkpoints.tgz "$file" > "${FASTSURFER_HOME}/checkpoints/$file"
        test -s "${FASTSURFER_HOME}/checkpoints/$file"
    done
    printf '%s\n' "$FASTSURFER_CHECKPOINTS_SHA256" > "${FASTSURFER_HOME}/checkpoints/cache-archive.sha256"
    rm /tmp/fastsurfer-checkpoints.tgz
else
    # A digest without an archive is a mistake, not a request for the default.
    test -z "${FASTSURFER_CHECKPOINTS_SHA256:-}"
    simnibs_python "${FASTSURFER_HOME}/FastSurferCNN/download_checkpoints.py" --vinn
fi
