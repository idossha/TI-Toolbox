#!/usr/bin/env bash
# Reproduces the N0.3 REPORT.md's LIVE verification from nothing: copies the checked-in
# desktop/src/main/docker/*.ts sources into a scratch build dir alongside this directory's
# live-verify.ts, compiles them to CommonJS with the repo's own pinned TypeScript (via
# `npx --prefix desktop tsc`, so no global/second TypeScript install), and runs the result with
# plain `node` against whatever Docker Engine API endpoint `discover()` finds on this machine.
#
# Requires: a running Docker engine (Docker Desktop, Docker Engine, or anything discover() can
# find) reachable from this host, and node_modules already installed under desktop/ (npm ci).
#
# Also runs a live smoke test of the Python client (tit/jobs/docker_engine.py) against the same
# socket, via DOCKER_HOST, using whatever `python3` is on PATH — no simnibs/venv needed, stdlib
# only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DESKTOP_DIR="$REPO_ROOT/desktop"
BUILD_DIR="$(mktemp -d -t tit-n03-live-verify-XXXXXX)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "== copying desktop/src/main/docker/*.ts into $BUILD_DIR/docker =="
mkdir -p "$BUILD_DIR/docker"
cp "$DESKTOP_DIR/src/main/docker/discover.ts" "$BUILD_DIR/docker/"
cp "$DESKTOP_DIR/src/main/docker/frames.ts" "$BUILD_DIR/docker/"
cp "$DESKTOP_DIR/src/main/docker/engine.ts" "$BUILD_DIR/docker/"
cp "$SCRIPT_DIR/live-verify.ts" "$BUILD_DIR/live-verify.ts"

cat > "$BUILD_DIR/tsconfig.json" <<JSON
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "CommonJS",
    "moduleResolution": "node",
    "esModuleInterop": true,
    "strict": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "typeRoots": ["$DESKTOP_DIR/node_modules/@types"],
    "types": ["node"]
  },
  "include": ["*.ts", "docker/*.ts"]
}
JSON

echo "== compiling with the repo's pinned tsc =="
(cd "$BUILD_DIR" && npx --prefix "$DESKTOP_DIR" tsc -p tsconfig.json)

echo "== running live-verify.js against whatever discover() finds =="
node "$BUILD_DIR/dist/live-verify.js"

echo
echo "== TypeScript client done. Running the Python client's live smoke test =="

DOCKER_CONTEXT_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null || true)"
if [ -z "$DOCKER_CONTEXT_HOST" ]; then
  echo "Could not resolve a Docker context host for the Python smoke test; skipping." >&2
  exit 0
fi

DOCKER_HOST="$DOCKER_CONTEXT_HOST" python3 - "$REPO_ROOT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import os
from tit.jobs.docker_engine import DockerEngineClient, discover, run_job_container

conn = discover(dict(os.environ))
print("conn:", conn)
client = DockerEngineClient(conn, timeout_s=20.0)
v = client.version()
print("version:", v.get("Version"), v.get("ApiVersion"), v.get("Arch"))

cid = run_job_container(
    client,
    image="alpine:3.20",
    cmd=["sh", "-c", "echo pyout; echo pyerr 1>&2; exit 7"],
    job_id="live-verify-py-job",
)
print("created:", cid)
frames = list(client.logs(cid, follow=True))
by_stream = {}
for f in frames:
    by_stream[f.stream] = by_stream.get(f.stream, b"") + f.payload
print("stdout:", by_stream.get("stdout"))
print("stderr:", by_stream.get("stderr"))
code = client.wait_container(cid)
print("exit code:", code)
inspected = client.inspect_container(cid)
print("Labels:", inspected["Config"]["Labels"])
client.remove_container(cid)
print("removed.")
assert code == 7, f"expected exit code 7, got {code}"
PY
