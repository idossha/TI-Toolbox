#!/usr/bin/env bash
# Execute the packaged example notebook end to end inside the TI-Toolbox image.
#
# What it does
#   Runs `tit/server/examples/example_workflow.ipynb` with `jupyter nbconvert --execute` in a
#   fresh container of the release image, with this checkout mounted read-only as the `tit`
#   that runs (PYTHONPATH=/ti-toolbox) and an empty project directory substituted for the
#   notebook's `/path/to/your/project` placeholder. That
#   is exactly the situation of a user who just installed the toolbox and opened the seeded
#   example: cell 1 downloads ernie (~630 MB, once -- pass a --project that already has it to
#   skip the download), the flex cell runs its reduced search, the simulator runs one TI FEM
#   simulation and the analyzer reads it back. The executed notebook, with outputs, is written
#   next to the log so a failure shows the traceback in the cell that raised it.
#
#   The static API check is `python3 -m pytest -q tests/test_example_notebook_api.py`; this
#   script is the run that proves the notebook really works, and it is not a CI step because it
#   needs a real FEM solve (~10-40 min on this Mac under emulation; less native).
#
# Usage
#   dev/run_example_notebook.sh                       # fresh project under a temp dir
#   dev/run_example_notebook.sh --project ~/nb-proj   # reuse a project (skips the download)
#   dev/run_example_notebook.sh --image idossha/ti-toolbox:v3.0.0
#
# Exit codes: 0 every cell ran, 1 a cell raised (see the .ipynb in the output dir), 2 could
# not run (no docker / image missing).
#
# Never run this while another FEM simulation is running under emulation on the same machine.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="idossha/ti-toolbox:${TIT_IMAGE_TAG:-v3.0.0}"
PROJECT=""
OUT_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --image)   IMAGE="$2"; shift 2 ;;
    --out)     OUT_DIR="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null 2>&1 || { echo "cannot run: docker is not on PATH" >&2; exit 2; }
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "cannot run: image $IMAGE not present" >&2; exit 2; }

[ -n "$PROJECT" ] || PROJECT="$(mktemp -d "${TMPDIR:-/tmp}/tit-example-nb-project.XXXXXX")"
[ -n "$OUT_DIR" ] || OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tit-example-nb-out.XXXXXX")"
mkdir -p "$PROJECT" "$OUT_DIR"
# The notebook's one edited line is a literal path; the runner edits it the way a user would.
sed 's#/path/to/your/project#/mnt/project#' "$REPO_ROOT/tit/server/examples/example_workflow.ipynb" > "$OUT_DIR/example_workflow.ipynb"

echo "image:   $IMAGE"
echo "project: $PROJECT"
echo "output:  $OUT_DIR/example_workflow.executed.ipynb (log: $OUT_DIR/nbconvert.log)"

start=$(date +%s)
set +e
docker run --rm --entrypoint bash \
  -v "$REPO_ROOT:/ti-toolbox:ro" \
  -v "$PROJECT:/mnt/project" \
  -v "$OUT_DIR:/mnt/out" \
  -e PYTHONPATH=/ti-toolbox \
  -w /mnt/out \
  "$IMAGE" -c 'simnibs_python -m jupyter nbconvert --to notebook --execute \
      --ExecutePreprocessor.timeout=-1 --ExecutePreprocessor.kernel_name=python3 \
      example_workflow.ipynb --output example_workflow.executed.ipynb' \
  > "$OUT_DIR/nbconvert.log" 2>&1
rc=$?
set -e
echo "nbconvert exit $rc, wall $(( $(date +%s) - start )) s"
if [ "$rc" -ne 0 ]; then
  tail -40 "$OUT_DIR/nbconvert.log"
  exit 1
fi
