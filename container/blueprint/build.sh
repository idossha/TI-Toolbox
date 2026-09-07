#!/usr/bin/env bash
# build.sh — build idossha/ti-toolbox:<ver> from container/blueprint/Dockerfile.ti-toolbox.
#
# Usage:
#   ./build.sh [--tag IMAGE:TAG] [--ti-toolbox-ref REF]
#              [--tetravox-tgz URL] [--no-tetravox] [--no-cache]
#
#   --tag                image:tag to build (default idossha/ti-toolbox:<version>-dev)
#   --ti-toolbox-ref     git ref the Dockerfile clones (default main)
#   --tetravox-tgz       bake this exact `tetravox-embed-<ver>.tgz`. Default: the newest
#                        compatible release, resolved from the GitHub Releases API at build
#                        time (see "Which Tetravox gets baked" below). A URL given here is
#                        NOT digest-verified — the digest comes from the release's own
#                        .tgz.sha256 asset, which only the resolver reads.
#   --no-tetravox        bake the placeholder deliberately (an air-gapped build).
#   --no-cache           pass --no-cache to docker build
#
# There is one recipe. Dockerfile.ti-toolbox.layered (a fast local build FROM
# idossha/simnibs:v2.5.0) was deleted, and with it --layered/--from-scratch/--skip-ui-build:
# the UI is built inside the image's own Node stage from the cloned ref, so there is nothing
# for this script to build first. A from-scratch SimNIBS install is 30-60+ minutes natively
# and considerably longer under amd64 emulation on Apple silicon.
#
# ## Which Tetravox gets baked
#
# The image bakes the Tetravox **embed** at /opt/tetravox/embed — the browser build tit.server
# serves at /tetravox/ and the app frames in the Viewer page. Not the desktop app, and not a
# headless CLI: the container has no display, and the embed is the only Tetravox that draws
# inside this app.
#
# With no --tetravox-tgz, `resolve_tetravox_tgz` below asks the GitHub Releases API for the
# newest non-draft, non-prerelease release of idossha/tetravox whose embed manifest declares a
# protocol inside the range THIS checkout supports. So "cut a new image and it ships whatever
# Tetravox is current" needs no edit to this script or to the Dockerfile — and no version
# number lives in either.
#
# The build needs a CONTEXT — never the raw repo root. desktop/node_modules alone is ~700 MB,
# and Docker (even with BuildKit) walks the whole context directory before .dockerignore-style
# filtering can help on a plain COPY; there is also no repo-root .dockerignore this lane may
# add (it isn't owned by this lane, and would affect every other Dockerfile in
# container/blueprint/ too). So this script stages a small, purpose-built context directory
# under mktemp -d instead: {container/blueprint/entrypoint.ti-toolbox.sh} only — the
# Dockerfile itself `git clone`s the TI-Toolbox repo from GitHub (same pattern as
# Dockerfile.simnibs), so the context need only carry the one file it COPYs from local disk.
#
# The staged directory is removed on exit (trap), success or failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TAG=""
TI_TOOLBOX_REF="main"
TETRAVOX_TGZ=""
NO_TETRAVOX=""
NO_CACHE=""
OBSOLETE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --tag) TAG="$2"; shift 2 ;;
        --ti-toolbox-ref) TI_TOOLBOX_REF="$2"; shift 2 ;;
        --tetravox-tgz) TETRAVOX_TGZ="$2"; shift 2 ;;
        --no-tetravox) NO_TETRAVOX=1; shift ;;
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        # Retired flags, accepted so an old command line still builds.
        --layered|--from-scratch|--skip-ui-build) OBSOLETE="$OBSOLETE $1"; shift ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *)
            echo "build.sh: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [ -n "$OBSOLETE" ]; then
    echo "build.sh: obsolete and ignored:$OBSOLETE" >&2
    echo "build.sh:   there is one recipe now (the layered Dockerfile was deleted); the UI is" >&2
    echo "build.sh:   built inside the image's own Node stage. See this script's header." >&2
fi

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

echo "build.sh: tag=$TAG version=$VERSION vcs_ref=$VCS_REF ref=$TI_TOOLBOX_REF stage=$STAGE_DIR"

# --- the same rule as the runtime updater, in bash + python3 stdlib -------------------------
# The baked bundle is the *floor* the runtime can always fall back to (E2), so baking a
# placeholder means a fresh, offline install has no viewer until someone installs one.
# Resolving it here uses exactly the rule tit/tetravox/updates.py uses at runtime: the newest
# non-draft, non-prerelease release of idossha/tetravox carrying tetravox-embed-<ver>.tgz plus
# its .tgz.sha256 and .manifest.json sidecars, whose manifest `protocol` is inside the range
# this checkout supports (read from tit/tetravox/protocol.py -- one source of truth, not a
# number copied into this script). curl + python3 stdlib only: no jq, no pip install, nothing
# this script may assume is on a maintainer's machine.
#
# It prints "<url> <sha256>": the digest is the release's own .tgz.sha256 asset, and the
# Dockerfile verifies it before opening the archive.
#
# Failure is never fatal: an unreachable API, a rate limit, or no release carrying the assets
# all print one line and fall through to the placeholder, because a build that cannot reach
# GitHub is still a build.
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
    sha_url = assets.get(f"{tgz}.sha256")
    if not manifest_url or not sha_url:
        continue
    try:
        with urllib.request.urlopen(manifest_url, timeout=30) as fh:
            protocol = json.load(fh).get("protocol")
    except Exception:
        continue
    if not (isinstance(protocol, int) and MIN <= protocol <= MAX):
        continue
    try:
        with urllib.request.urlopen(sha_url, timeout=30) as fh:
            # The asset is `sha256sum` output: "<digest>  <filename>".
            digest = fh.read().decode("utf-8", "replace").split()[0]
    except Exception:
        continue
    if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
        continue
    print(assets[tgz], digest)
    sys.exit(0)
sys.exit(1)
' "$min" "$max"
}

TETRAVOX_SHA256=""
if [ -z "$TETRAVOX_TGZ" ] && [ -z "$NO_TETRAVOX" ]; then
    echo "build.sh: resolving the newest compatible Tetravox embed release..."
    if resolved="$(resolve_tetravox_tgz)" && [ -n "$resolved" ]; then
        TETRAVOX_TGZ="${resolved%% *}"
        TETRAVOX_SHA256="${resolved##* }"
        echo "build.sh: baking $TETRAVOX_TGZ (sha256 ${TETRAVOX_SHA256:0:12}...)"
    else
        TETRAVOX_TGZ=""
        echo "build.sh: no compatible Tetravox embed release found (or GitHub unreachable);" \
             "baking the placeholder. The app can still install a bundle at runtime." >&2
    fi
fi
if [ -n "$NO_TETRAVOX" ]; then
    TETRAVOX_TGZ=""
    TETRAVOX_SHA256=""
    echo "build.sh: --no-tetravox: baking the placeholder embed."
fi

build_args=(
    --platform linux/amd64
    --build-arg "TI_TOOLBOX_VERSION=$VERSION"
    --build-arg "VCS_REF=$VCS_REF"
    --build-arg "TI_TOOLBOX_REF=$TI_TOOLBOX_REF"
    --build-arg "CACHE_BUST=$(date +%s)"
    --build-arg "TETRAVOX_EMBED_TGZ=$TETRAVOX_TGZ"
    --build-arg "TETRAVOX_EMBED_SHA256=$TETRAVOX_SHA256"
)
if [ -n "$NO_CACHE" ]; then
    build_args+=("$NO_CACHE")
fi

mkdir -p "$STAGE_DIR/container/blueprint"
cp "$SCRIPT_DIR/entrypoint.ti-toolbox.sh" "$STAGE_DIR/container/blueprint/entrypoint.ti-toolbox.sh"

# NOT `exec` — the EXIT trap above must still fire (staged-context cleanup) once
# `docker build` finishes; `exec` would replace this shell and skip it.
docker build "${build_args[@]}" \
    -f "$SCRIPT_DIR/Dockerfile.ti-toolbox" \
    -t "$TAG" \
    "$STAGE_DIR"
