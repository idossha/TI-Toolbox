#!/bin/bash
set -euo pipefail

# Build MkDocs API site into docs/api/ (committed, no CI required)
#
# Usage:
#   ./docs/build-api.sh          # Build only
#   ./docs/build-api.sh serve    # Live preview at http://127.0.0.1:8000

cd "$(dirname "$0")/.."

echo "Installing documentation dependencies..."
python3 -m pip install -q -r docs/api_mkdocs/requirements.txt

if [ "${1:-}" = "serve" ]; then
    echo ""
    echo "Starting live preview server..."
    echo "   http://127.0.0.1:8000"
    echo ""
    python3 -m mkdocs serve -f docs/api_mkdocs/mkdocs.yml
else
    echo "Building API documentation..."
    python3 -m mkdocs build -f docs/api_mkdocs/mkdocs.yml --clean

    echo ""
    echo "Built API site into docs/api/"
    echo "   Open: docs/api/index.html"
fi
