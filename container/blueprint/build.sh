#!/usr/bin/env bash
# build.sh — build idossha/ti-toolbox:<ver> from either recipe.
#
# Usage:
#   ./build.sh [--layered|--from-scratch] [--tag IMAGE:TAG] [--tetravox-tgz URL]
#              [--ti-toolbox-ref REF] [--skip-ui-build] [--no-cache]
#
# --tetravox-tgz is optional: with no URL, the newest Tetravox release this build can host is
# resolved automatically from the GitHub Releases API (A5, dev/notes/v3-tetravox-selection-
# pipeline-plan.md), so a fresh image never ships the placeholder bundle. Pass --tetravox-tgz to
# pin one, or --no-tetravox to bake the placeholder deliberately (an air-gapped build).
#
# Defaults: --layered (fast, FROM idossha/simnibs:v2.5.0 — see Dockerfile.ti-toolbox.layered's
# own header for why this exists), tag idossha/ti-toolbox:<version from tit/__init__.py>-dev.
#
# --from-scratch builds Dockerfile.ti-toolbox (the CI recipe: installs SimNIBS itself,
# 30-60+ minutes even natively — see its own header; not attempted in the Phase-A W2
# session, see dev/notes/v3-docker-streamline/w2-image-notes.md).
#
# Both recipes need a build CONTEXT — never the raw repo root. desktop/node_modules alone
# is ~700 MB, and Docker (even with BuildKit) walks the whole context directory before
# .dockerignore-style filtering can help on a plain COPY; there is also no repo-root
# .dockerignore this lane may add (it isn't owned by this lane, and would affect every
# other Dockerfile in container/blueprint/ too). So this script stages a small, purpose-
# built context directory under mktemp -d instead:
#   --layered:      {ti-toolbox/{tit,resources,pyproject.toml,README.md}, ui/, entrypoint.ti-toolbox.sh}
#                    (Dockerfile.ti-toolbox.layered COPYs tit/resources/pyproject fresh —
#                    the base image's own /ti-toolbox predates tit.server entirely — and
#                    the UI bundle; everything else it needs is already in the base image)
#   --from-scratch: {container/blueprint/entrypoint.ti-toolbox.sh} only (the Dockerfile
#                    itself `git clone`s the TI-Toolbox repo from GitHub — same pattern as
#                    today's Dockerfile.simnibs — so the context need only carry the one
#                    file it COPYs from local disk instead of cloning)
#
# The staged directory is removed on exit (trap), success or failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RECIPE="layered"
TAG=""
TETRAVOX_TGZ=""
NO_TETRAVOX=""
TI_TOOLBOX_REF="main"
SKIP_UI_BUILD=""
NO_CACHE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --layered) RECIPE="layered"; shift ;;
        --from-scratch) RECIPE="from-scratch"; shift ;;
        --tag) TAG="$2"; shift 2 ;;
        --tetravox-tgz) TETRAVOX_TGZ="$2"; shift 2 ;;
        --no-tetravox) NO_TETRAVOX=1; shift ;;
        --ti-toolbox-ref) TI_TOOLBOX_REF="$2"; shift 2 ;;
        --skip-ui-build) SKIP_UI_BUILD=1; shift ;;
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        -h|--help)
            sed -n '2,25p' "$0"
            exit 0
            ;;
        *)
            echo "build.sh: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

# Version: tit/__init__.py's `__version__ = "x.y.z"` (pyproject.toml's `dynamic = ["version"]`
# resolves the same way via setuptools' `attr:` mechanism — read it here instead of
# `simnibs_python -c "import tit"` since neither SimNIBS nor a Python interpreter is
# guaranteed to be on the machine running this script).
VERSION="$(grep -m1 '^__version__' "$REPO_ROOT/tit/__init__.py" | sed -E 's/^__version__[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/')"
if [ -z "$VERSION" ]; then
    echo "build.sh: could not read __version__ from tit/__init__.py" >&2
    exit 1
fi
if [ -z "$TAG" ]; then
    TAG="idossha/ti-toolbox:${VERSION}-dev"
fi

VCS_REF="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"

STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ti-toolbox-build.XXXXXX")"
cleanup() { rm -rf "$STAGE_DIR"; }
trap cleanup EXIT

echo "build.sh: recipe=$RECIPE tag=$TAG version=$VERSION vcs_ref=$VCS_REF stage=$STAGE_DIR"

# --- A5: the same rule as the runtime updater, in bash + python3 stdlib ---------------------
#
# The image's baked bundle is the *floor* the runtime can always fall back to (E2), so baking a
# placeholder means a fresh, offline install has no viewer at all until someone installs one.
# Resolving it here uses exactly the rule tit/tetravox/updates.py uses at runtime: the newest
# non-draft, non-prerelease release of idossha/tetravox carrying tetravox-embed-<ver>.tgz plus
# its .tgz.sha256 and .manifest.json sidecars, whose manifest `protocol` is inside the range this
# checkout supports (read from tit/tetravox/protocol.py -- one source of truth, not a number
# copied into this script). curl + python3 stdlib only: no jq, no pip install, nothing this
# script may assume is on a maintainer's machine.
#
# Failure is never fatal: an unreachable API, a rate limit, or no release carrying the assets all
# print one line and fall through to the placeholder, because a build that cannot reach GitHub is
# still a build.
resolve_tetravox_tgz() {
    local min max
    min="$(grep -m1 '^SUPPORTED_PROTOCOL_MIN' "$REPO_ROOT/tit/tetravox/protocol.py" | sed -E 's/[^0-9]*([0-9]+).*/\1/')"
    max="$(grep -m1 '^SUPPORTED_PROTOCOL_MAX' "$REPO_ROOT/tit/tetravox/protocol.py" | sed -E 's/[^0-9]*([0-9]+).*/\1/')"
    [ -n "$min" ] && [ -n "$max" ] || return 1
    local body
    body="$(curl -fsSL -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/idossha/tetravox/releases" 2>/dev/null)" || return 1
    printf '%s' "$body" | python3 -c '
import json, re, sys, urllib.request

MIN, MAX = int(sys.argv[1]), int(sys.argv[2])
TGZ = re.compile(r"^tetravox-embed-(.+)\.tgz$")
try:
    releases = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
for release in releases if isinstance(releases, list) else []:
    if release.get("draft") or release.get("prerelease"):
        continue
    assets = {a.get("name"): a.get("browser_download_url") for a in release.get("assets") or []}
    tgz = next((n for n in assets if TGZ.match(n or "")), None)
    if not tgz:
        continue
    version = TGZ.match(tgz).group(1)
    manifest_url = assets.get(f"tetravox-embed-{version}.manifest.json")
    if not manifest_url or f"{tgz}.sha256" not in assets:
        continue
    try:
        with urllib.request.urlopen(manifest_url, timeout=30) as fh:
            protocol = json.load(fh).get("protocol")
    except Exception:
        continue
    if isinstance(protocol, int) and MIN <= protocol <= MAX:
        print(assets[tgz])
        sys.exit(0)
sys.exit(1)
' "$min" "$max"
}

if [ -z "$TETRAVOX_TGZ" ] && [ -z "$NO_TETRAVOX" ]; then
    echo "build.sh: resolving the newest compatible Tetravox embed release..."
    if TETRAVOX_TGZ="$(resolve_tetravox_tgz)" && [ -n "$TETRAVOX_TGZ" ]; then
        echo "build.sh: baking $TETRAVOX_TGZ"
    else
        TETRAVOX_TGZ=""
        echo "build.sh: no compatible Tetravox embed release found (or GitHub unreachable);" \
             "baking the placeholder. The app can still install a bundle at runtime." >&2
    fi
fi

build_args=(--platform linux/amd64 --build-arg "TI_TOOLBOX_VERSION=$VERSION" --build-arg "VCS_REF=$VCS_REF")
if [ -n "$TETRAVOX_TGZ" ]; then
    build_args+=(--build-arg "TETRAVOX_EMBED_TGZ=$TETRAVOX_TGZ")
fi
if [ -n "$NO_CACHE" ]; then
    build_args+=("$NO_CACHE")
fi

if [ "$RECIPE" = "layered" ]; then
    # --- stage the curated context ---
    mkdir -p "$STAGE_DIR/ti-toolbox"
    for item in tit resources pyproject.toml README.md; do
        cp -R "$REPO_ROOT/$item" "$STAGE_DIR/ti-toolbox/$item"
    done
    # Drop bytecode caches that may exist in a dev worktree — never wanted in an image.
    find "$STAGE_DIR/ti-toolbox" -name "__pycache__" -type d -prune -exec rm -rf {} +

    RENDERER_DIR="$REPO_ROOT/desktop/out/renderer"
    if [ -z "$SKIP_UI_BUILD" ] && [ ! -f "$RENDERER_DIR/index.html" ]; then
        echo "build.sh: desktop/out/renderer missing — building the UI bundle first"
        (cd "$REPO_ROOT/desktop" && npm run build)
    fi
    if [ ! -f "$RENDERER_DIR/index.html" ]; then
        echo "build.sh: $RENDERER_DIR has no index.html — build the desktop UI first" \
             "(cd desktop && npm run build) or pass --skip-ui-build to ship the status page instead" >&2
        exit 1
    fi
    cp -R "$RENDERER_DIR" "$STAGE_DIR/ui"

    cp "$SCRIPT_DIR/entrypoint.ti-toolbox.sh" "$STAGE_DIR/entrypoint.ti-toolbox.sh"

    # NOT `exec` — the EXIT trap above must still fire (staged-context cleanup) once
    # `docker build` finishes; `exec` would replace this shell and skip it.
    docker build "${build_args[@]}" \
        -f "$SCRIPT_DIR/Dockerfile.ti-toolbox.layered" \
        -t "$TAG" \
        "$STAGE_DIR"
else
    mkdir -p "$STAGE_DIR/container/blueprint"
    cp "$SCRIPT_DIR/entrypoint.ti-toolbox.sh" "$STAGE_DIR/container/blueprint/entrypoint.ti-toolbox.sh"

    docker build "${build_args[@]}" \
        --build-arg "TI_TOOLBOX_REF=$TI_TOOLBOX_REF" \
        --build-arg "CACHE_BUST=$(date +%s)" \
        -f "$SCRIPT_DIR/Dockerfile.ti-toolbox" \
        -t "$TAG" \
        "$STAGE_DIR"
fi
