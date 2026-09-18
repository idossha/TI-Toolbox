#!/usr/bin/env bash
# Sequential, resumable runner for the flex-search mini study on subject ernie.
#
# Usage:
#   export TIT_PROJECT_DIR=/path/to/your/bids/project
#   ./run_all.sh              # run configs/*.json (the real study)
#   ./run_all.sh configs_smoke  # run a different config dir (e.g. the smoke pass)
#
# - Runs one docker container at a time (never two FEM jobs in parallel).
# - Each run's stdout+stderr goes to logs/<name>.log (never piped through tail/head).
# - Start/end epoch seconds + exit code are appended to logs/timing.tsv.
# - Resumable: a config whose timing.tsv line already shows exit 0 is skipped.
#
# Docker command per config (entrypoint execs the given command directly):
#   docker run --rm \
#     -v "${TIT_PROJECT_DIR}:/mnt/000" \
#     -v <study_dir>:/study \
#     idossha/ti-toolbox:v3.0.0 simnibs_python -m tit.opt.flex /study/<config_dir>/<name>.json
#
# The container reads project_dir out of the config JSON itself
# (tit.opt.flex.__main__ pops "project_dir" and calls get_path_manager(...)), so
# nothing besides the /mnt/000 bind mount is required for path resolution.

set -uo pipefail

STUDY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${TIT_PROJECT_DIR:?set TIT_PROJECT_DIR to your BIDS project dir before running}"
IMAGE="idossha/ti-toolbox:v3.0.0"

CONFIG_DIR="${1:-configs}"
CONFIG_PATH="${STUDY_DIR}/${CONFIG_DIR}"
LOG_DIR="${STUDY_DIR}/logs"
TIMING_TSV="${LOG_DIR}/timing.tsv"

mkdir -p "${LOG_DIR}"
touch "${TIMING_TSV}"

# Fixed order: thalamus arms 1-6, then lhippo arms 1-6; the two "mean" arms first
# within each target block so an early result is available quickly.
ORDER=(
  thalamus_mean
  thalamus_tf_w0
  thalamus_tf_w1
  thalamus_roc_fixed
  thalamus_roc_adapt
  thalamus_mean_ratio
  lhippo_mean
  lhippo_tf_w0
  lhippo_tf_w1
  lhippo_roc_fixed
  lhippo_roc_adapt
  lhippo_mean_ratio
)

already_succeeded() {
  local name="$1"
  # timing.tsv columns: name, start_epoch, end_epoch, exit_code
  awk -F'\t' -v n="$name" '$1==n && $4==0 {found=1} END{exit !found}' "${TIMING_TSV}"
}

for name in "${ORDER[@]}"; do
  cfg_file="${CONFIG_PATH}/${name}.json"
  if [[ ! -f "${cfg_file}" ]]; then
    echo "SKIP (missing config): ${name} -> ${cfg_file}"
    continue
  fi

  if already_succeeded "${name}"; then
    echo "SKIP (already exit 0): ${name}"
    continue
  fi

  log_file="${LOG_DIR}/${name}.log"
  echo "RUN: ${name}"
  start_ts=$(date +%s)

  docker run --rm \
    -v "${PROJECT_DIR}:/mnt/000" \
    -v "${STUDY_DIR}:/study" \
    "${IMAGE}" simnibs_python -m tit.opt.flex "/study/${CONFIG_DIR}/${name}.json" \
    > "${log_file}" 2>&1
  exit_code=$?

  end_ts=$(date +%s)
  printf '%s\t%s\t%s\t%s\n' "${name}" "${start_ts}" "${end_ts}" "${exit_code}" >> "${TIMING_TSV}"

  elapsed=$((end_ts - start_ts))
  echo "DONE: ${name} exit=${exit_code} elapsed=${elapsed}s log=${log_file}"
done
