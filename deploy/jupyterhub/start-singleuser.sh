#!/bin/bash
# Seed the user's project volume on first start, then hand over to JupyterHub.
set -euo pipefail

# This checkout's tit/ (baked into the image) must shadow the base image's site-packages copy.
export PYTHONPATH="/ti-toolbox:${PYTHONPATH:-}"

PROJECT="/mnt/${PROJECT_DIR_NAME:-000}"
SEED="/seed"

if [ -d "$SEED" ] && [ ! -e "$PROJECT/dataset_description.json" ]; then
    echo "[tit-hub] seeding $PROJECT from $SEED ..."
    mkdir -p "$PROJECT"
    cp -a "$SEED"/. "$PROJECT"/
    echo "[tit-hub] seed complete"
fi

# The example notebook, ready to open (nbgitpuller keeps it in sync with main).
mkdir -p /mnt/notebooks
if [ -d /opt/tit-hub/notebooks ]; then
    cp -n /opt/tit-hub/notebooks/*.ipynb /mnt/notebooks/ 2>/dev/null || true
fi

exec simnibs_python -m jupyterhub.singleuser \
    --ServerApp.root_dir=/mnt \
    --allow-root \
    "$@"
