#!/bin/bash

# Inner test runner — executed INSIDE the Docker container.
# Called by tests/test.sh (the host-side wrapper).
#
# Uses simnibs_python (SimNIBS's bundled Python) for installation and tests,
# so the source checkout's test requirements augment the cached image.

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
echo "Installing tit package and test dependencies into simnibs_python..."
simnibs_python -m pip install -e '/ti-toolbox[test]'

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
