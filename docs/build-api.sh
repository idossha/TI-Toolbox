#!/bin/bash
set -euo pipefail

# Build MkDocs API site into docs/api/ (committed, no CI required)

python3 -m pip install -r "docs/api_mkdocs/requirements.txt"
python3 -m mkdocs build -f "docs/api_mkdocs/mkdocs.yml" --clean

echo ""
echo "✅ Built API site into docs/api/"
echo "   Open: docs/api/index.html"
