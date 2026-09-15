#!/usr/bin/env bash
# Python-free Docker launcher. Run with --help for options.
set -euo pipefail

die() { printf 'ti-toolbox: %s\n' "$*" >&2; exit 1; }
project="${TIT_PROJECT_DIR:-}"
image="${TIT_IMAGE_TAG:-}"
port=8765 timeout=180 mode=start follow=0 open_browser=1 interactive=0
repo="${TIT_DEV_REPO_DIR:-}"
[ -z "${TIT_DEV:-}" ] || repo="${repo:-$PWD}"
print_config=0
running_action=""; container=""; ui="${TIT_LAUNCH_UI:-}"; explicit_browser=0; explicit_desktop=0
[ "$#" -gt 0 ] || interactive=1
while [ "$#" -gt 0 ]; do
    case "$1" in
        --*=*) set -- "${1%%=*}" "${1#*=}" "${@:2}" ;;
        --help|-h)
            cat <<'HELP'
Usage: bash loader.sh [--project DIR] [options]

Start TI-Toolbox. The desktop app is the UI: it is downloaded, checksum-verified and
cached on first run, and the browser is the fallback. Browser containers persist after
closing the tab. Docker, Compose and curl are required; no host Python is needed.

  --image IMAGE:TAG   image override
  --port PORT        first host port to try (8765)
  --timeout SECONDS  startup wait (180)
  --desktop          require the desktop app; never fall back to the browser
  --browser          use the browser instead of the desktop app
  --no-open          print the session URL without opening a UI
  --existing ACTION  attach or recreate the selected running container
  --container ID     select a running container for either action
  --dev [DIR]        run a source checkout, not the image's code (reload + its built UI)
  --print-config     print the resolved settings and exit; no Docker calls
  --interactive      choose a project interactively
  --status           show this project's container
  --logs [--follow]   print or follow its logs
  --stop             stop and remove its container
HELP
            exit 0 ;;
        --project|--project-dir|--image|--port|--timeout|--existing|--container)
            [ "$#" -ge 2 ] || die "$1 requires a value"
            case "$1" in
                --project|--project-dir) project="$2" ;; --image) image="$2" ;;
                --port) port="$2" ;; --timeout) timeout="$2" ;;
                --existing) running_action="$2" ;; --container) container="$2" ;;
            esac
            shift 2 ;;
        --dev)
            if [ "$#" -ge 2 ] && case "$2" in --*) false ;; *) true ;; esac; then repo="$2"; shift 2
            else repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"; shift; fi ;;
        --print-config) print_config=1; shift ;;
        --no-open) open_browser=0; shift ;;
        --browser) ui=browser; explicit_browser=1; shift ;;
        --desktop) ui=desktop; explicit_desktop=1; shift ;;
        --interactive) interactive=1; shift ;;
        --stop|--status|--logs)
            [ "$mode" = start ] || die 'choose only one of --stop, --status or --logs'
            mode="${1#--}"; shift ;;
        --follow|-f) follow=1; shift ;;
        --no-mount-repo) repo=''; shift ;;
        *) die "unknown argument: $1 (see --help)" ;;
    esac
done
[ "$explicit_desktop" = 0 ] || { [ "$explicit_browser" = 0 ] && [ "$open_browser" = 1 ]; } || die '--desktop cannot be combined with --browser or --no-open'
case "$running_action" in ""|attach|recreate) ;; *) die "--existing must be attach or recreate" ;; esac
config="${XDG_CONFIG_HOME:-$HOME/.config}/ti-toolbox"
if [ "$interactive" = 1 ]; then
    [ -t 0 ] || { printf 'ti-toolbox: interactive setup needs a terminal; pass --project DIR\n' >&2; exit 2; }
    printf '\nWelcome to TI-Toolbox\n'
    printf 'Center for Sleep and Consciousness · UW–Madison\n'
    printf 'Simulate, optimize and analyze temporal interference stimulation.\n'
    printf '\nChoose your project directory to get started.\n\n'
    [ -n "$project" ] || { [ ! -f "$config/last-project.txt" ] || project="$(cat "$config/last-project.txt")"; }
    read -r -p "Project directory${project:+ [$project]}: " answer || exit 2
    project="${answer:-$project}"
fi
case "$project" in \~/*) project="$HOME/${project#\~/}" ;; esac
[ -d "$project" ] || die 'pass --project with an existing directory'
project="$(cd "$project" && pwd -P)"
case "$project" in *$'\n'*|*:*) die 'project path cannot contain newlines or colons' ;; esac
[ "$project" != / ] || die 'choose a project directory, not the filesystem root'
[[ "$port" =~ ^[0-9]+$ ]] && [ "$port" -gt 0 ] && [ "$port" -le 65535 ] || die 'port must be 1–65535'
[[ "$timeout" =~ ^[0-9]+([.][0-9]+)?$ ]] || die 'timeout must be positive seconds'
timeout="$(awk -v t="$timeout" 'BEGIN {print int(t)+(t>int(t))}')"
[ "$timeout" -gt 0 ] || die 'timeout must be positive'
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
# --- desktop bootstrap -------------------------------------------------------------------
# The desktop app is the product; this script only fetches and starts it (docs/dev/DECISIONS.md,
# 2026-09-15). Names come from desktop/electron-builder.yml and dev/update/verify_release_assets.py.
# tit/cli.py::resolve_desktop_executable implements the identical order; --print-config's
# desktop_executable line is what a test compares.
release_base_url="${TIT_RELEASE_BASE_URL:-https://github.com/idossha/TI-Toolbox/releases/download}"
desktop_exe=''; desktop_reason=''
tit_version() {
    # The same value tit.__version__ reports, read the way this script already reads the
    # image tag: the pinned default in the shared compose spec, without its leading "v".
    local spec tag
    spec="${TIT_COMPOSE_FILE:-$script_dir/docker-compose.yml}"
    # shellcheck disable=SC2016
    tag="$(sed -n 's/^[[:space:]]*image: idossha\/ti-toolbox:${TIT_IMAGE_TAG:-\([^}]*\)}.*/\1/p' "$spec" 2>/dev/null | head -1)"
    printf '%s' "${tag#v}"
}
desktop_data_dir() {
    if [ -n "${TIT_DATA_DIR:-}" ]; then printf '%s' "$TIT_DATA_DIR"; return 0; fi
    case "$(uname -s)" in
        Darwin) printf '%s' "$HOME/Library/Application Support/TI-Toolbox" ;;
        *) printf '%s' "${XDG_DATA_HOME:-$HOME/.local/share}/ti-toolbox" ;;
    esac
}
desktop_asset() {
    case "$(uname -s):$(uname -m)" in
        Darwin:arm64) printf 'TI-Toolbox-%s-arm64-mac.zip' "$1" ;;
        Darwin:x86_64) printf 'TI-Toolbox-%s-mac.zip' "$1" ;;
        Linux:x86_64) printf 'TI-Toolbox-%s.AppImage' "$1" ;;
    esac
}
managed_executable() {
    case "$(uname -s)" in
        Darwin) printf '%s' "$1/TI-Toolbox.app/Contents/MacOS/TI-Toolbox" ;;
        Linux) printf '%s' "$1/TI-Toolbox.AppImage" ;;
    esac
}
# Sets desktop_exe to a path, to "download", or to '' (with desktop_reason).
resolve_desktop_executable() {
    local version exe
    desktop_exe=''; desktop_reason=''
    if [ -n "${TIT_ELECTRON_EXECUTABLE:-}" ] && [ -x "$TIT_ELECTRON_EXECUTABLE" ]; then
        desktop_exe="$TIT_ELECTRON_EXECUTABLE"; return 0
    fi
    version="$(tit_version)"
    if [ -z "$version" ]; then desktop_reason='could not determine the TI-Toolbox version'; return 0; fi
    exe="$(managed_executable "$(desktop_data_dir)/app/$version")"
    if [ -n "$exe" ] && [ -x "$exe" ]; then desktop_exe="$exe"; return 0; fi
    if [ -z "$(desktop_asset "$version")" ]; then
        desktop_reason="no desktop build for $(uname -s)/$(uname -m)"; return 0
    fi
    desktop_exe=download
}
sha256_of() {
    if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
    elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
    else printf ''; fi
}
# Downloads, verifies and installs the app; sets desktop_exe or desktop_reason.
install_desktop_executable() {
    local version asset base root work_dir expected actual exe
    version="$(tit_version)"; asset="$(desktop_asset "$version")"
    base="$release_base_url/v$version"
    root="$(desktop_data_dir)/app"
    desktop_exe=''; desktop_reason=''
    mkdir -p "$root" || { desktop_reason="could not create $root"; return 0; }
    work_dir="$(mktemp -d "$root/.staging-XXXXXX")" || { desktop_reason="could not stage the download"; return 0; }
    printf 'Downloading the TI-Toolbox desktop app (%s)\n' "$asset" >&2
    if ! curl -fsSL "$base/SHA256SUMS" -o "$work_dir/SHA256SUMS"; then
        rm -rf "$work_dir"; desktop_reason='could not download SHA256SUMS'; return 0
    fi
    expected="$(awk -v name="$asset" '{sub(/^[*]/, "", $2)} $2 == name {print $1}' "$work_dir/SHA256SUMS" | head -1)"
    if [ -z "$expected" ]; then rm -rf "$work_dir"; desktop_reason="SHA256SUMS does not list $asset"; return 0; fi
    if ! curl -fL --progress-bar "$base/$asset" -o "$work_dir/$asset"; then
        rm -rf "$work_dir"; desktop_reason="could not download $asset"; return 0
    fi
    actual="$(sha256_of "$work_dir/$asset")"
    if [ -z "$actual" ] || [ "$actual" != "$expected" ]; then
        rm -rf "$work_dir"; desktop_reason="checksum mismatch for $asset"; return 0
    fi
    mkdir -p "$work_dir/app"
    case "$asset" in
        *.zip) unzip -q "$work_dir/$asset" -d "$work_dir/app" || { rm -rf "$work_dir"; desktop_reason="could not unpack $asset"; return 0; } ;;
        *) mv "$work_dir/$asset" "$work_dir/app/TI-Toolbox.AppImage" ;;
    esac
    exe="$(managed_executable "$work_dir/app")"
    if [ -z "$exe" ] || [ ! -f "$exe" ]; then
        rm -rf "$work_dir"; desktop_reason="$asset did not contain the expected executable"; return 0
    fi
    chmod +x "$exe"
    rm -rf "${root:?}/$version"
    if ! mv "$work_dir/app" "$root/$version"; then
        rm -rf "$work_dir"; desktop_reason='could not install the desktop app'; return 0
    fi
    rm -rf "$work_dir"
    # One managed install at a time; older versions are never launched again.
    for stale in "$root"/*; do
        [ -d "$stale" ] && [ "$(basename "$stale")" != "$version" ] || continue
        rm -rf "$stale"
    done
    desktop_exe="$(managed_executable "$root/$version")"
}
if [ -z "$ui" ]; then
    # The desktop app is the default UI; --browser, --no-open and a --dev checkout opt out.
    if [ "$explicit_browser" = 1 ] || [ "$open_browser" = 0 ] || [ -n "$repo" ]; then ui=browser; else ui=desktop; fi
fi
# Match the Python/Electron project hash so all entry points can attach and stop.
project_stack() {
    local text="$1" h1 h2 i code hash
    h1=$((0xDEADBEEF ^ ${#text})); h2=$((0x41C6CE57 ^ ${#text}))
    for ((i=0; i<${#text}; i++)); do
        printf -v code '%d' "'${text:i:1}"
        h1=$(( ((h1 ^ code) * 2654435761) & 0xFFFFFFFF ))
        h2=$(( ((h2 ^ code) * 1597334677) & 0xFFFFFFFF ))
    done
    hash=$(( (((h1 ^ (h1 >> 16)) * 2246822507) ^ ((h2 ^ (h2 >> 13)) * 3266489909)) & 0xFFFFFFFF ))
    printf 'ti-toolbox-%08x' "$hash"
}
# --dev changes only the source of the server and renderer; everything else is identical.
if [ -n "$repo" ]; then
    case "$repo" in \~/*) repo="$HOME/${repo#\~/}" ;; esac
    [ -f "$repo/tit/launch.py" ] || die "not a TI-Toolbox checkout: $repo"
    repo="$(cd "$repo" && pwd -P)"
fi
static=''; reload=''
if [ -n "$repo" ]; then
    static=/ti-toolbox/desktop/out/renderer; reload=1
fi
if [ "$print_config" = 1 ]; then
    default_spec="${TIT_COMPOSE_FILE:-$script_dir/docker-compose.yml}"
    # shellcheck disable=SC2016
    resolved_image="${image:-$(sed -n 's/^[[:space:]]*image: idossha\/ti-toolbox:${TIT_IMAGE_TAG:-\([^}]*\)}.*/idossha\/ti-toolbox:\1/p' "$default_spec" 2>/dev/null)}"
    printf 'mode      %s\n' "$([ -n "$repo" ] && printf dev || printf user)"
    printf 'project   %s\n' "$project"
    printf 'port      %s\n' "$port"
    printf 'image     %s\n' "$resolved_image"
    printf 'container %s-tit-1\n' "$(project_stack "$project")"
    printf 'origin    http://127.0.0.1:%s\n' "$port"
    printf 'ui        %s\n' "$ui"
    printf 'repo_dir  %s\n' "$repo"
    printf 'static    %s\n' "$static"
    printf 'reload    %s\n' "$reload"
    desktop_exe=''
    if [ "$ui" = desktop ] && [ -z "$repo" ]; then resolve_desktop_executable; fi
    printf 'desktop_executable %s\n' "$desktop_exe"
    exit 0
fi
if [ "$mode" = start ] && [ "$open_browser" = 1 ] && [ "$ui" = desktop ]; then
    helper="$script_dir/dev/launch-electron.sh"
    export TIT_LAUNCH_PROJECT_DIR="$project" TIT_LAUNCH_EXISTING="$running_action" TIT_LAUNCH_CONTAINER="$container"
    export TIT_LAUNCH_PORT="$port" TIT_LAUNCH_TIMEOUT="$timeout"
    export TIT_LAUNCH_IMAGE="$image"
    # A checkout keeps the developer path: Electron from desktop/node_modules.
    if [ -n "$repo" ] && [ -f "$helper" ]; then exec bash "$helper"; fi
    resolve_desktop_executable
    [ "$desktop_exe" != download ] || install_desktop_executable
    if [ -n "$desktop_exe" ]; then
        unset ELECTRON_RUN_AS_NODE TIT_LAUNCH_CONTAINER_ID TIT_DEV_SERVER_URL TIT_DEV_SERVER_TOKEN
        unset ELECTRON_RENDERER_URL TIT_DEV_REPO_DIR TIT_REPO_DIR TIT_STATIC_DIR TIT_SERVER_RELOAD
        "$desktop_exe"
        printf 'TI-Toolbox closed.\n'
        exit 0
    fi
    [ "$explicit_desktop" = 0 ] || die "${desktop_reason:-the desktop app is unavailable}"
    printf 'ti-toolbox: %s; opening the browser instead.\n' "${desktop_reason:-the desktop app is unavailable}" >&2
    ui=browser
fi
command -v docker >/dev/null || die 'install Docker first'
docker info >/dev/null 2>&1 || die 'start Docker and try again'
ids="$(docker ps -aq --filter label=tit.stack=ti-toolbox-v3 --filter label=tit.service=tit --filter "label=tit.host_project_dir=$project")"
[[ "$ids" != *$'\n'* ]] || die 'multiple containers match this project; inspect Docker before continuing'
if [ "$mode" != start ]; then
    [ -n "$ids" ] || { printf 'No container for this project.\n'; exit 0; }
    case "$mode" in
        stop) docker stop "$ids" >/dev/null; docker rm "$ids" >/dev/null; printf 'Stopped this project.\n' ;;
        status) docker inspect --format '{{.Name}}: {{.State.Status}} ({{.Config.Image}})' "$ids" ;;
        logs) if [ "$follow" = 1 ]; then docker logs --follow "$ids"; else docker logs "$ids"; fi ;;
    esac
    exit 0
fi
command -v curl >/dev/null || die 'install curl first'
spec="${TIT_COMPOSE_FILE-$script_dir/docker-compose.yml}"
if [ "${TIT_COMPOSE_FILE+x}" = x ] && [ ! -f "$spec" ]; then
    die "container specification not found: $spec"
fi
work="$(mktemp -d)"
gpu_probe=''
trap '[ -z "$gpu_probe" ] || docker rm --force "$gpu_probe" >/dev/null 2>&1; rm -rf "$work"' EXIT
if [ ! -f "$spec" ]; then
    curl -fsSL "https://raw.githubusercontent.com/idossha/TI-Toolbox/${TIT_SOURCE_REF:-main}/docker-compose.yml" -o "$work/source.yml" || die 'could not download the container specification'
    spec="$work/source.yml"
fi
if [ -z "$image" ]; then
    # Match the literal Compose placeholder.
    # shellcheck disable=SC2016
    image="$(sed -n 's/^[[:space:]]*image: idossha\/ti-toolbox:${TIT_IMAGE_TAG:-\([^}]*\)}.*/idossha\/ti-toolbox:\1/p' "$spec")"
fi
case "$image" in *[!a-zA-Z0-9_./:@-]*|'') die 'invalid image reference' ;; esac
[[ "$image" == */* ]] || image="idossha/ti-toolbox:$image"
if [ -n "$repo" ] && [ "$open_browser" = 1 ]; then
    [ -f "$repo/desktop/out/renderer/index.html" ] || die 'build the checkout UI with npm --prefix desktop run build, or use npm run dev:web from desktop/'
fi
read_env() { docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$ids" | sed -n "s/^$1=//p"; }
# Discover by labels, current and legacy names, and image, including other projects.
running_ids="$(docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Labels}}' | awk -F '|' '$4 ~ /(^|,)tit.service=/ && $4 !~ /(^|,)tit.service=tit(,|$)/ {next} tolower($2) ~ /^ti[-_]toolbox([-_]|$)/ || tolower($3) ~ /(^|\/)ti[-_]toolbox(:|@|$)/ || $4 ~ /(^|,)tit.stack=ti-toolbox(-v3)?(,|$)/ {print $1}')"
if [ -n "$running_ids" ]; then
    printf '\nRunning TI-Toolbox containers:\n'
    number=0
    while IFS= read -r candidate; do
        number=$((number + 1))
        display_image="$(docker inspect --format '{{.Config.Image}}' "$candidate")"
        printf '  %s. %s\n' "$number" "$display_image"
    done <<< "$running_ids"
    if [ -z "$container" ]; then
        if [[ "$running_ids" == *$'\n'* ]]; then
            [ -t 0 ] || die 'multiple running containers: pass --container ID'
            read -r -p 'Select container number: ' answer || exit 2
            [[ "$answer" =~ ^[1-9][0-9]*$ ]] || die 'invalid container number; containers unchanged'
            container="$(printf '%s\n' "$running_ids" | sed -n "${answer}p")"
            [ -n "$container" ] || die 'invalid container number; containers unchanged'
        else container="$running_ids"; fi
    fi
    selected=''
    while IFS= read -r candidate; do
        full_id="$(docker inspect --format '{{.Id}}' "$candidate")"
        name="$(docker inspect --format '{{.Name}}' "$candidate")"
        if [ "$container" = "$candidate" ] || [ "$container" = "$full_id" ] || [ "$container" = "${name#/}" ]; then selected="$candidate"; fi
    done <<< "$running_ids"
    [ -n "$selected" ] || die 'selected container is not a running TI-Toolbox container'
    if [ -z "$running_action" ]; then
        [ -t 0 ] || die 'running containers require --existing attach or --existing recreate'
        printf '\nAvailable actions\n-----------------\n  1. Recreate (default)\n  2. Attach\n\nRecreate stops this container and its jobs.\n'
        read -r -p 'Choose [1]: ' answer || exit 2
        case "$answer" in
            ''|1|recreate|r) running_action=recreate ;;
            2|attach|a) running_action=attach ;;
            *) die 'invalid choice; containers unchanged' ;;
        esac
    fi
    [ "$explicit_desktop" = 0 ] || { [ "$explicit_browser" = 0 ] && [ "$open_browser" = 1 ]; } || die '--desktop cannot be combined with --browser or --no-open'
case "$running_action" in
        attach)
            ids="$selected"
            attached_project="$(docker inspect --format '{{index .Config.Labels "tit.host_project_dir"}}' "$ids")"
            [ -z "$attached_project" ] || [ "$attached_project" = '<no value>' ] || project="$attached_project"
            ;;
        recreate)
            if [ -n "$ids" ] && [ "$ids" != "$selected" ] && [ "$(docker inspect --format '{{.State.Running}}' "$ids")" = true ]; then
                die 'requested project already has another running container; select that container to recreate'
            fi
            ;;
        *) die 'launch cancelled; containers unchanged' ;;
    esac
elif [ "$running_action" = attach ] || [ -n "$container" ]; then
    die 'no running TI-Toolbox container matches the requested selection'
fi
if [ -n "$running_ids" ] && [ "$running_action" = attach ]; then
    token="$(read_env TIT_SERVER_TOKEN)"; port="$(read_env TIT_SERVER_PORT)"
    [ -n "$token" ] && [ -n "$port" ] || die 'container has no session credentials; stop and relaunch it'
else
    docker compose version >/dev/null 2>&1 || die 'install the Docker Compose plugin'
    cached=0
    docker image inspect "$image" >/dev/null 2>&1 && cached=1
    if [ "$cached" = 0 ] || { [ "$image" = idossha/ti-toolbox:v3.0.0 ] && [ -z "$repo" ]; }; then
        if ! docker pull --platform linux/amd64 "$image"; then
            [ "$cached" = 1 ] || die "could not download $image"
            printf 'Warning: could not refresh %s; using the cached image.\n' "$image" >&2
        fi
    fi
    gpu=0
    gpu_probe="ti-gpu-probe-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
    cuda_probe="import torch; assert torch.cuda.is_available(); x=torch.ones((32,32),device='cuda'); y=x@x; torch.cuda.synchronize(); assert y[0,0].item()==32"
    if docker run --detach --name "$gpu_probe" --network none --platform linux/amd64 --gpus all --env NVIDIA_DRIVER_CAPABILITIES=compute,utility --entrypoint simnibs_python "$image" -c "$cuda_probe" >"$work/gpu.out" 2>"$work/gpu.err"; then
        gpu_deadline=$((SECONDS+60))
        while [ "$(docker inspect --format '{{.State.Running}}' "$gpu_probe" 2>/dev/null)" = true ] && [ "$SECONDS" -lt "$gpu_deadline" ]; do sleep 1; done
        gpu_state="$(docker inspect --format '{{.State.Status}}:{{.State.ExitCode}}' "$gpu_probe" 2>/dev/null || true)"
        [ "$gpu_state" != exited:0 ] || gpu=1
    fi
    if [ "$gpu" = 0 ] && [ ! -s "$work/gpu.err" ]; then docker logs --tail 4 "$gpu_probe" >"$work/gpu.err" 2>&1 || true; fi
    docker rm --force "$gpu_probe" >/dev/null 2>&1 || true
    gpu_probe=''
    if [ "$gpu" = 1 ]; then
        printf 'CUDA GPU verified; GPU access enabled for FastSurfer.\n'
    else
        printf 'Container GPU unavailable. CPU remains available; Apple Silicon users can enable native Apple GPU in Pre-processing.\n'
        cat "$work/gpu.err" >&2
    fi
    first_port="$port"
    while (: >"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1; do
        port=$((port+1)); [ "$port" -le 65535 ] && [ "$port" -lt $((first_port+64)) ] || die 'no free port found'
    done
    token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    stack="$(project_stack "$project")"
    mkdir -p "$config"
    export LOCAL_PROJECT_DIR="$project" PROJECT_DIR_NAME="${project##*/}" TIT_USER_CONFIG="$config"
    export TIT_SERVER_TOKEN="$token" TIT_SERVER_PORT="$port" TIT_REPO_DIR="$repo" TIT_SERVER_RELOAD="$reload" TIT_STATIC_DIR="$static"
    TIT_HOST_OS="$(uname -s | tr '[:upper:]' '[:lower:]')"; TIT_HOST_OS_VERSION="$(uname -r)"; TIT_HOST_ARCH="$(uname -m)"
    export TIT_HOST_OS TIT_HOST_OS_VERSION TIT_HOST_ARCH
    export DOCKER_DEFAULT_PLATFORM=linux/amd64
    awk -v image="$image" -v mount="$repo" -v gpu="$gpu" '
        /^[[:space:]]*image:/ {
            $0="    image: " image
            if (gpu==1) $0=$0 "\n    deploy:\n      resources:\n        reservations:\n          devices:\n            - driver: nvidia\n              count: all\n              capabilities: [gpu]"
        }
        /\$\{TIT_REPO_DIR:-\}:\/ti-toolbox/ && mount=="" {next}
        {print}
    ' "$spec" > "$work/compose.yml"
    docker compose --project-name "$stack" --project-directory "$script_dir" -f "$work/compose.yml" config --quiet || die 'invalid container specification; existing container unchanged'
    if [ -n "$running_ids" ] && [ "$running_action" = recreate ]; then
        docker stop "$selected" >/dev/null
        docker rm "$selected" >/dev/null
        [ "$ids" != "$selected" ] || ids=''
    fi
    [ -z "$ids" ] || docker rm "$ids" >/dev/null
    ids="$(docker compose --project-name "$stack" --project-directory "$script_dir" -f "$work/compose.yml" run --detach --no-deps --service-ports --name "$stack-tit-1" --label "tit.project=$stack" --label tit.stack=ti-toolbox-v3 --label tit.service=tit --label "tit.host_project_dir=$project" tit)"
fi
origin="http://127.0.0.1:$port"
deadline=$((SECONDS+timeout))
until curl -fsS "$origin/api/health" >/dev/null 2>&1; do
    [ "$SECONDS" -lt "$deadline" ] || die "startup timed out; inspect with --logs ($origin)"
    sleep 1
done
mkdir -p "$config"; printf '%s\n' "$project" > "$config/last-project.txt"
url="$origin/auth/session?token=$token"
if [ "$open_browser" = 1 ] && command -v open >/dev/null; then open "$url"
elif [ "$open_browser" = 1 ] && command -v xdg-open >/dev/null; then xdg-open "$url"
else printf '%s\n' "$url"
fi
