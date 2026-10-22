#!/usr/bin/env bash
# Run every env-gated real-data test against Dataset 000 inside the toolbox image.
#
# Real-data tests skip with a reason when their variable is unset, so on every ordinary run they
# report "skipped" and prove nothing. This runner sets every gating variable that Dataset 000
# can satisfy, runs the modules that read one, and fails when any test skips except the ones
# check_junit.py's `realdata` allowlist names (variables Dataset 000 cannot satisfy, each with
# its reason) -- so "skipped" can never pass for "checked".
#
#   dev/run_realdata_tests.sh --dataset /path/to/000 [--image idossha/ti-toolbox:vX.Y.Z] [--out DIR]
#
# The dataset is mounted read-only at /mnt/000. Tests that write (scene and dot-directory
# caches) get /tmp/000, a tree of symlinks to it whose directories are writable, so a write to
# a dataset file still fails loudly. The scene builders refuse a source that resolves outside
# the project, so the dot-cache subject's m2m and .bidsignore are real copies there. A
# (path, size, mtime) listing of the dataset, plus the SHA-256 of every file under 16 MB, is
# taken before and after the run and must not change.
# New real-data tests gate on TIT_DATASET_000 (docs/dev/TESTING.md); the runner finds every
# module that reads one of the gating variables (os.environ / getenv, or an ENV_* constant),
# so nothing needs registering here.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/tit/__init__.py")"
IMAGE="idossha/ti-toolbox:v${VERSION}"
DATASET="${TIT_DATASET_000:-}"
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2 ;;
    --dataset) DATASET="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$DATASET" ] || [ ! -d "$DATASET/derivatives/SimNIBS" ]; then
  echo "could not check: pass --dataset (or set TIT_DATASET_000) to a Dataset 000 copy" >&2
  exit 2
fi
DATASET="$(cd "$DATASET" && pwd)"
OUT="${OUT:-$(mktemp -d "${TMPDIR:-/tmp}/tit-realdata.XXXXXX")}"
mkdir -p "$OUT"

# Every variable a real-data test reads, and what the runner gives it.
GATES='TIT_DATASET_000|TIT_SCENE_TESTDATA|TIT_DTI_REAL|TIT_DOTCACHE_PROJECT|TIT_ERNIE_LABELING'
SET_VARS=(
  TIT_DATASET_000=/mnt/000            # read-only; new tests copy what they write to tmp_path
  TIT_SCENE_TESTDATA=/tmp/000         # test_scene_realdata.py mirrors it again under tmp_path
  TIT_SCENE_SUBJECT=101               # Dataset 000's m2m_ernie has no segmentation/ (atlases)
  TIT_SCENE_ATLAS=DK40
  TIT_DOTCACHE_PROJECT=/tmp/000       # writes .ti-toolbox/cache into the project it is given
  TIT_DOTCACHE_SUBJECT=ernie
  TIT_DTI_REAL=/mnt/000               # links sub-CHN into its own tmp project
)
# Read by those modules but deliberately not set here, with the reason.
NOT_SET=(
  "TIT_ERNIE_LABELING: Dataset 000 keeps no m2m_ernie/segmentation/labeling.nii.gz"
  "TIT_DTI_PROTO: the prototype CHN tensor is not part of Dataset 000"
  "TIT_DOTCACHE_CHILD: set by test_dot_cache_layout.py for its own child process"
  "TIT_ROI_KEEP_ISLANDS: set by test_roi_islands.py itself"
  "TIT_EVENTS_FILE: removed by the report tests, so a rebuilt report writes no job events"
)

cd "$ROOT"
MODULES=()  # bash 3.2 (macOS) has no mapfile
while IFS= read -r module; do MODULES+=("$module"); done \
  < <(grep -rlE "(environ\.get\(|environ\[|getenv\(|ENV_[A-Z_]* = )[\"']($GATES)" tests \
       --include='test_*.py' | sort)
if [ "${#MODULES[@]}" -eq 0 ]; then
  echo "could not check: no test module reads a Dataset 000 variable" >&2
  exit 2
fi
# Every quoted TIT_* name is accounted for (an environment variable is named by a string
# literal: in the read itself or in an ENV_* constant); bare identifiers such as the
# caps.TIT_CAPS constant are Python names, not variables.
for var in $(grep -hoE "[\"']TIT_[A-Z0-9_]+[\"']" "${MODULES[@]}" | tr -d "\"'" | sort -u); do
  if ! printf '%s\n' "${SET_VARS[@]%%=*}" "${NOT_SET[@]%%:*}" | grep -qx "$var"; then
    echo "could not check: $var is read by a real-data test but this runner neither sets it" \
      "nor says why not (SET_VARS / NOT_SET in $0)" >&2
    exit 2
  fi
done
echo "real-data modules (${#MODULES[@]}): ${MODULES[*]}"
printf 'not set: %s\n' "${NOT_SET[@]}"

listing() {
  python3 - "$DATASET" <<'PY'
import hashlib, os, sys
root = sys.argv[1]
for base, dirs, files in sorted(os.walk(root)):
    dirs.sort()
    for name in sorted(files):
        path = os.path.join(base, name)
        st = os.lstat(path)
        digest = "-"
        if st.st_size < 16 * 1024 * 1024 and os.path.isfile(path):
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
        print(f"{os.path.relpath(path, root)}\t{st.st_size}\t{st.st_mtime_ns}\t{digest}")
PY
}
listing > "$OUT/dataset_before.tsv"

ENV_ARGS=()
for pair in "${SET_VARS[@]}"; do ENV_ARGS+=(-e "$pair"); done
status=0
docker run --rm --platform linux/amd64 --entrypoint bash \
  -v "$ROOT":/ti-toolbox:ro -v "$DATASET":/mnt/000:ro -v "$OUT":/out -w /ti-toolbox \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTEST_ADDOPTS="-p no:cacheprovider -o log_file=/tmp/pytest.log" \
  "${ENV_ARGS[@]}" "$IMAGE" -lc '
    set -e
    cp -as /mnt/000 /tmp/000
    rm -rf /tmp/000/.ti-toolbox
    cp --remove-destination /mnt/000/.bidsignore /tmp/000/.bidsignore
    m2m=derivatives/SimNIBS/sub-${TIT_DOTCACHE_SUBJECT}/m2m_${TIT_DOTCACHE_SUBJECT}
    rm -rf "/tmp/000/$m2m"
    cp -a "/mnt/000/$m2m" "/tmp/000/$m2m"
    simnibs_python -m pytest "$@" -q -rs --junitxml=/out/realdata.xml
  ' realdata "${MODULES[@]}" || status=$?

listing > "$OUT/dataset_after.tsv"
if ! cmp -s "$OUT/dataset_before.tsv" "$OUT/dataset_after.tsv"; then
  echo "FAIL: the run changed Dataset 000:" >&2
  diff "$OUT/dataset_before.tsv" "$OUT/dataset_after.tsv" | head -20 >&2
  exit 1
fi
echo "Dataset 000 unchanged ($(wc -l < "$OUT/dataset_before.tsv") files listed)"
python3 "$ROOT/dev/check_junit.py" --leg realdata "$OUT/realdata.xml"
echo "pytest exit $status; evidence in $OUT"
exit "$status"
