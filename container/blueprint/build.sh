#!/usr/bin/env bash
# build.sh — build idossha/ti-toolbox:<ver> from container/blueprint/Dockerfile.ti-toolbox.
#
# Usage:
#   ./build.sh [--tag IMAGE:TAG] [--ref GIT-REF]
#              [--fastsurfer-checkpoints-tgz URL --fastsurfer-checkpoints-sha256 HEX]
#              [--blender-archive URL]
#
#   --tag                image:tag to build (default idossha/ti-toolbox:v<version>)
#   --ref                build from `git clone <REF>` of github.com/idossha/TI-Toolbox instead
#                        of the local checkout (the CI/release path; the ref must be pushed).
#                        Default: no ref -- the repository root is the build context and the
#                        image is built from the working tree as it is, committed or not.
#                        `--ti-toolbox-ref` is the same option under its old name.
#                        build stage on Docker Desktop, http://host.docker.internal:<port>/...
#                        reaches a server on this machine). Default: the newest compatible
#                        release, resolved from the GitHub Releases API at build time (see
#                        "Which Tetravox gets baked" below).
#                        release's own .tgz.sha256 asset, but a hand-given URL has no sidecar
#                        to read, so the digest has to be given by hand too.
#   --no-cache           pass --no-cache to docker build
#   --fastsurfer-checkpoints-tgz / --fastsurfer-checkpoints-sha256
#                        optional verified VINN cache (http(s), including a local server).
#                        Archive must contain the three aparc_vinn_*_v2.0.0.pkl files at its
#                        root. Digest is required and checked before extraction. Without it,
#                        FastSurfer downloads its official checkpoints with TLS verification.
#
# There is one recipe. Dockerfile.ti-toolbox.layered (a fast local build FROM
# idossha/simnibs:v2.5.0) was deleted, and with it --layered/--from-scratch/--skip-ui-build:
# the UI is built inside the image's own Node stage from the same source tree, so there is
# nothing for this script to build first. A from-scratch SimNIBS install is 30-60+ minutes
# natively and considerably longer under amd64 emulation on Apple silicon.
#
# ## Where the source comes from
#
# Without --ref, the build CONTEXT is the repository root and the Dockerfile's `source-local`
# stage COPYs it. The repo-root .dockerignore is an allow-list (tit/, resources/, contracts/,
# container/, desktop/ minus node_modules/out/tests, pyproject.toml, README.md, LICENSE), so
# the context is ~150 MB rather than the ~2 GB of the raw tree; `docker build` prints the
# exact figure as "transferring context". The image records what it was built from in
# /etc/ti-toolbox-build.json: the full sha, whether the tree had uncommitted changes to
# tracked files, and the date.
#
# With --ref, the context is an empty staging directory and the `source-clone` stage clones
# the ref from GitHub; the sha is taken from `git ls-remote`.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TAG=""
TI_TOOLBOX_REF=""
FASTSURFER_CHECKPOINTS_TGZ=""
FASTSURFER_CHECKPOINTS_SHA256=""
BLENDER_ARCHIVE_URL=""
NO_CACHE=""
OBSOLETE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --tag) TAG="$2"; shift 2 ;;
        --ref|--ti-toolbox-ref) TI_TOOLBOX_REF="$2"; shift 2 ;;
        --fastsurfer-checkpoints-tgz) FASTSURFER_CHECKPOINTS_TGZ="$2"; shift 2 ;;
        --fastsurfer-checkpoints-sha256) FASTSURFER_CHECKPOINTS_SHA256="$2"; shift 2 ;;
        --blender-archive) BLENDER_ARCHIVE_URL="$2"; shift 2 ;;
        --no-cache) NO_CACHE="--no-cache"; shift ;;
        # Retired flags, accepted so an old command line still builds.
        --layered|--from-scratch|--skip-ui-build) OBSOLETE="$OBSOLETE $1"; shift ;;
        -h|--help)
            sed -n '2,32p' "$0"
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
    TAG="idossha/ti-toolbox:v${VERSION%%-*}"
fi

# A cache is an explicit pair, never an unverified replacement for the official weights.
if [ -n "$FASTSURFER_CHECKPOINTS_TGZ" ] || [ -n "$FASTSURFER_CHECKPOINTS_SHA256" ]; then
    if ! printf '%s' "$FASTSURFER_CHECKPOINTS_TGZ" | grep -Eq '^https?://[^[:space:]]+$' \
        || ! printf '%s' "$FASTSURFER_CHECKPOINTS_SHA256" | grep -Eq '^[0-9a-f]{64}$'; then
        echo "build.sh: FastSurfer cache needs an http(s) --fastsurfer-checkpoints-tgz and a 64 lowercase hex --fastsurfer-checkpoints-sha256" >&2
        exit 2
    fi
fi

if [ -n "$BLENDER_ARCHIVE_URL" ] && ! printf '%s' "$BLENDER_ARCHIVE_URL" | grep -Eq '^https?://[^[:space:]]+$'; then
    echo "build.sh: --blender-archive must be an http(s) URL; the recipe still verifies the fixed official checksum" >&2
    exit 2
fi

# --- source: local checkout (default) or a pushed ref -------------------------------------
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ti-toolbox-build.XXXXXX")"
cleanup() { rm -rf "$STAGE_DIR"; }
trap cleanup EXIT

if [ -z "$TI_TOOLBOX_REF" ]; then
    SOURCE=local
    CONTEXT="$REPO_ROOT"
    if [ ! -f "$REPO_ROOT/.dockerignore" ]; then
        echo "build.sh: $REPO_ROOT/.dockerignore is missing; refusing to send the raw tree" >&2
        echo "build.sh:   (desktop/node_modules alone is >1 GB) as the build context" >&2
        exit 1
    fi
    VCS_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    VCS_REF="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    # Tracked files only: an untracked scratch file is not a different build of the code.
    if [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
        VCS_DIRTY=true
    else
        VCS_DIRTY=false
    fi
else
    SOURCE=clone
    CONTEXT="$STAGE_DIR"   # empty: the clone stage needs no file from this machine
    VCS_SHA="$(git ls-remote https://github.com/idossha/TI-Toolbox.git "$TI_TOOLBOX_REF" 2>/dev/null \
        | awk 'NR==1 {print $1}')"
    if [ -z "$VCS_SHA" ]; then
        # A raw commit sha is a valid ref that ls-remote cannot list.
        if printf '%s' "$TI_TOOLBOX_REF" | grep -Eq '^[0-9a-f]{7,40}$'; then
            VCS_SHA="$TI_TOOLBOX_REF"
        else
            echo "build.sh: ref '$TI_TOOLBOX_REF' is not on github.com/idossha/TI-Toolbox (git ls-remote" >&2
            echo "build.sh:   found nothing). Push it, or drop --ref to build from this checkout." >&2
            exit 1
        fi
    fi
    VCS_REF="${VCS_SHA:0:8}"
    VCS_DIRTY=false
fi

echo "build.sh: tag=$TAG version=$VERSION source=$SOURCE ref=${TI_TOOLBOX_REF:-<local>} sha=$VCS_SHA dirty=$VCS_DIRTY"

build_args=(
    --platform linux/amd64
    --build-arg "TI_TOOLBOX_VERSION=$VERSION"
    --build-arg "VCS_REF=$VCS_REF"
    --build-arg "VCS_SHA=$VCS_SHA"
    --build-arg "VCS_DIRTY=$VCS_DIRTY"
    --build-arg "BUILD_DATE=$BUILD_DATE"
    --build-arg "TI_TOOLBOX_SOURCE=$SOURCE"
    --build-arg "TI_TOOLBOX_REF=$TI_TOOLBOX_REF"
    --build-arg "CACHE_BUST=$(date +%s)"
    --build-arg "FASTSURFER_CHECKPOINTS_TGZ=$FASTSURFER_CHECKPOINTS_TGZ"
    --build-arg "FASTSURFER_CHECKPOINTS_SHA256=$FASTSURFER_CHECKPOINTS_SHA256"
)
if [ -n "$BLENDER_ARCHIVE_URL" ]; then
    build_args+=(--build-arg "BLENDER_ARCHIVE_URL=$BLENDER_ARCHIVE_URL")
fi
if [ -n "$NO_CACHE" ]; then
    build_args+=("$NO_CACHE")
fi

# NOT `exec` — the EXIT trap above must still fire (staged-context cleanup) once
# `docker build` finishes; `exec` would replace this shell and skip it.
docker build "${build_args[@]}" \
    -f "$SCRIPT_DIR/Dockerfile.ti-toolbox" \
    -t "$TAG" \
    "$CONTEXT"
