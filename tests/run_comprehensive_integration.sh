#!/bin/bash
# Run the heavy release-gate integration pipeline in the same Docker image used
# by CircleCI (container/blueprint/Dockerfile.test).
#
# This is intentionally separate from the default pytest suite. It runs real
# computational stages and can take a long time:
#   DICOM conversion -> CHARM -> simulation -> flex focality -> leadfield ->
#   ex-search (pool of 6 electrodes) -> mesh + voxel analysis.
#
# Example:
#   tests/run_comprehensive_integration.sh --keep-work
#
# The default run uses only data available inside the Dockerfile.test
# environment. You can optionally override the DICOM fixture with
# --dicom-source for debugging, but release-gate runs should not need it.

set -euo pipefail

TEST_IMAGE="${TEST_IMAGE:-idossha/ti-toolbox-test:latest}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"
HOST_TEST_PROJECT="${HOST_TEST_PROJECT:-/tmp/test_projectdir}"
HOST_WORK_DIR="${TIT_COMPREHENSIVE_HOST_WORK_DIR:-/tmp/tit_comprehensive_integration}"
CONTAINER_WORK_DIR="/tmp/tit_comprehensive_integration"
DICOM_SOURCE=""
PASSTHROUGH=()

usage() {
  cat <<'EOF'
Usage: tests/run_comprehensive_integration.sh [options]

Options:
  --dicom-source PATH       Optional host path to a DICOM directory or archive.
                            Defaults to the DICOM fixture inside Dockerfile.test.
  --work-dir PATH           Host work directory for comprehensive outputs
                            (default: /tmp/tit_comprehensive_integration).
  --keep-work               Keep the container work project after completion.
  --skip-dicom              Skip DICOM conversion phase.
  --skip-charm              Skip CHARM phase.
  --skip-flex               Skip flex-search focality phase.
  --skip-leadfield-ex       Skip leadfield + ex-search phase.
  --subject ID              Fixture subject to use for simulation/optimization
                            (default: ernie_extended).
  -h, --help                Show this help.

Environment:
  TEST_IMAGE                         Docker image (default: idossha/ti-toolbox-test:latest)
  HOST_TEST_PROJECT                  Host mount for /mnt/test_projectdir
  TIT_COMPREHENSIVE_HOST_WORK_DIR    Host directory mounted as /tmp/tit_comprehensive_integration

Notes:
  - The image is built from container/blueprint/Dockerfile.test.
  - The script sets TIT_RUN_COMPREHENSIVE=1 inside the container.
  - This is a release-gate test, not a default PR smoke test.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dicom-source)
      DICOM_SOURCE="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
      PASSTHROUGH+=(--dicom-source /dicom_source)
      shift 2
      ;;
    --work-dir)
      HOST_WORK_DIR="$2"
      shift 2
      ;;
    --keep-work|--skip-dicom|--skip-charm|--skip-flex|--skip-leadfield-ex)
      PASSTHROUGH+=("$1")
      shift
      ;;
    --subject|--dicom-subject)
      PASSTHROUGH+=("$1" "$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is not running." >&2
  exit 1
fi

if ! docker image inspect "$TEST_IMAGE" >/dev/null 2>&1; then
  echo "Pulling test image: $TEST_IMAGE"
  docker pull "$TEST_IMAGE"
fi

mkdir -p "$HOST_TEST_PROJECT" "$HOST_WORK_DIR" /tmp/test-results
chmod 777 "$HOST_TEST_PROJECT" "$HOST_WORK_DIR" /tmp/test-results 2>/dev/null || true

DOCKER_ARGS=(
  run --rm
  -e TIT_RUN_COMPREHENSIVE=1
  -e PYTHONPATH=/ti-toolbox
  -v "${REPO_ROOT}:/ti-toolbox"
  -v "${HOST_TEST_PROJECT}:/mnt/test_projectdir"
  -v "${HOST_WORK_DIR}:${CONTAINER_WORK_DIR}"
  -v /tmp/test-results:/tmp/test-results
  -w /ti-toolbox
)

if [[ -n "$DICOM_SOURCE" ]]; then
  if [[ ! -e "$DICOM_SOURCE" ]]; then
    echo "DICOM source does not exist: $DICOM_SOURCE" >&2
    exit 2
  fi
  DOCKER_ARGS+=( -v "${DICOM_SOURCE}:/dicom_source:ro" )
fi

set -x
docker "${DOCKER_ARGS[@]}" "$TEST_IMAGE" \
  simnibs_python /ti-toolbox/tests/comprehensive_integration.py \
  --fixture-project /mnt/test_projectdir \
  --work-dir "$CONTAINER_WORK_DIR" \
  "${PASSTHROUGH[@]}"
