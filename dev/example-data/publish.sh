#!/usr/bin/env bash
# Publish the staged example-data assets to the content-addressed store.
#
#   python3 dev/example-data/stage.py --zip simnibs4_examples.zip --write-catalog
#   dev/example-data/publish.sh [--create]
#
# The store is the `example-data` release of idossha/TI-Toolbox, each asset named by its sha256 —
# 3D Slicer's SlicerDataStore layout, which is what lets `tit.examples` verify a download against
# its own URL. `--create` makes the release the first time; every later run only uploads assets
# that are not there yet (`--clobber` is never passed: an asset's content is its name, so
# re-uploading can only ever be a no-op or a mistake).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO="${TIT_EXAMPLE_REPO:-idossha/TI-Toolbox}"
TAG="example-data"
STORE="${TIT_EXAMPLE_STORE:-$ROOT/dev/example-data/store}"

if [ "${1:-}" = "--create" ] && ! gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release create "$TAG" --repo "$REPO" --title "Example data store" \
    --notes "Content-addressed example datasets; see dev/example-data/STORE-README.md"
fi

existing="$(gh release view "$TAG" --repo "$REPO" --json assets --jq '.assets[].name')"
n=0
for f in "$STORE"/*; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  if grep -qx "$name" <<< "$existing"; then
    echo "have     $name"
  else
    echo "upload   $name  ($(stat -f%z "$f" 2>/dev/null || stat -c%s "$f") B)"
    gh release upload "$TAG" "$f" --repo "$REPO"
    n=$((n + 1))
  fi
done
echo "$n uploaded to https://github.com/$REPO/releases/tag/$TAG"
