#!/bin/bash
# entrypoint.ti-toolbox.sh — the v3 image's entrypoint.
#
# Unlike entrypoint.sh (the v2 interactive-shell entrypoint: source FreeSurfer, drop into
# bash, run whatever CMD the compose file gave it), this entrypoint execs `tit.server`
# directly. There is no FreeSurfer to source (D2), no X11/DISPLAY setup (D3), and no
# `pip install` at start — fastapi/uvicorn/pyyaml/psutil are baked into the image
# (Dockerfile.ti-toolbox*, this lane's whole point per D1).
#
# `exec` (not a plain call) so tit.server becomes PID 1's replacement (or `init: true`'s
# child under tini, per docker-compose.v3.yml) and receives SIGTERM directly on
# `docker stop` / `docker compose down` — no wrapper shell left holding the signal.

set -euo pipefail

# Avoid OpenMP affinity crashes SimNIBS/numpy are prone to under emulation (matches
# Dockerfile.simnibs's own ENV; repeated here in case a future base image drops it).
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export KMP_AFFINITY="${KMP_AFFINITY:-disabled}"

# Project directory: TIT_PROJECT_DIR wins outright; otherwise fall back to the
# PROJECT_DIR_NAME convention the v2 compose stack and tit.server.settings both already
# understand (/mnt/<name>, const.DOCKER_MOUNT_PREFIX).
PROJECT_DIR="${TIT_PROJECT_DIR:-/mnt/${PROJECT_DIR_NAME:-}}"

# TIT_STATIC_DIR lets a dev point at a locally built renderer bundle (e.g. a bind-mounted
# /ti-toolbox/desktop/out/renderer) before /opt/ti-toolbox/ui exists in an image, or to
# swap UI bundles without a rebuild. Falls back to the image's baked-in UI.
STATIC_DIR="${TIT_STATIC_DIR:-/opt/ti-toolbox/ui}"

# No explicit `command:` in docker-compose.v3.yml overrides this — if one is ever passed
# (`docker run ... idossha/ti-toolbox:dev bash`), honor it instead of forcing the server.
if [ $# -gt 0 ]; then
    exec "$@"
fi

# TIT_SERVER_RELOAD=1 (set only by `npm run dev`, docker-compose.v3.yml) runs the server under
# uvicorn's reloader so an edit to tit/server/** or tit/jobs/** in the bind-mounted worktree
# restarts it instead of needing `docker restart`. --reload-dir is not optional here: uvicorn's
# default watch root is the working directory, which is the whole mounted repo — including
# desktop/node_modules (~400 directories deep) — and watchfiles walking that makes the container
# unusable. Runner subprocesses under tit/<module> are re-exec'd per job, so they never needed a
# reloader; only the long-lived server process does.
RELOAD_ARGS=()
if [ "${TIT_SERVER_RELOAD:-}" = "1" ]; then
    RELOAD_ARGS=(--reload --reload-dir /ti-toolbox/tit)
fi

exec simnibs_python -m tit.server \
    --project "$PROJECT_DIR" \
    --host 0.0.0.0 \
    --port "${TIT_SERVER_PORT:-8765}" \
    --static-dir "$STATIC_DIR" \
    "${RELOAD_ARGS[@]+"${RELOAD_ARGS[@]}"}"
