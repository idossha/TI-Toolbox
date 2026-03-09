#!/bin/bash

# Inner test runner — executed INSIDE the Docker container.
# Called by tests/test.sh (the host-side wrapper).

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

# ── Install package in editable mode ─────────────────────────────────────────
echo "Installing tit package (editable)..."
pip install -e /ti-toolbox --quiet 2>/dev/null || pip install -e /ti-toolbox

# ── Build pytest command ─────────────────────────────────────────────────────
CMD=(python -m pytest)

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
