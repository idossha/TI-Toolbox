#!/bin/bash

# Inner test runner — executed INSIDE the Docker container.
# Called by tests/test.sh (the host-side wrapper).
#
# Uses simnibs_python (SimNIBS's bundled Python) which has all
# required packages pre-installed (pytest, pytest-cov, etc.)

set -euo pipefail

# ── Parse flags ──────────────────────────────────────────────────────────────
VERBOSE=""
COVERAGE=""
EXTRA_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --verbose|-v) VERBOSE="-v" ;;
        --coverage)   COVERAGE="yes" ;;
        *)            EXTRA_ARGS+=("$arg") ;;
    esac
done

# ── Install tit package in editable mode ─────────────────────────────────────
echo "Installing tit package (editable) into simnibs_python..."
simnibs_python -m pip install -e /ti-toolbox --quiet 2>/dev/null || simnibs_python -m pip install -e /ti-toolbox

# ── Build pytest command ─────────────────────────────────────────────────────
CMD=(simnibs_python -m pytest)

if [ -n "$VERBOSE" ]; then
    CMD+=(-v)
fi

if [ "$COVERAGE" = "yes" ]; then
    CMD+=(
        --cov=tit
        --cov-report=xml:/tmp/coverage/coverage.xml
        --cov-report=term-missing
    )
fi

# JUnit XML for CircleCI test result ingestion
CMD+=(--junitxml=/tmp/test-results/results.xml)

# Append any extra arguments
CMD+=("${EXTRA_ARGS[@]}")

echo "Running: ${CMD[*]}"
echo ""

exec "${CMD[@]}"
