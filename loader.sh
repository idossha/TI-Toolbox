#!/usr/bin/env bash
# Python-free Docker launcher. Run with --help for options.
set -euo pipefail

die() { printf 'ti-toolbox: %s\n' "$*" >&2; exit 1; }
project="${TIT_PROJECT_DIR:-}"
image="${TIT_IMAGE_TAG:-}"
port=8765 timeout=180 mode=start follow=0 open_browser=1 interactive=0
repo="${TIT_DEV_REPO_DIR:-}"
[ "$#" -gt 0 ] || interactive=1
while [ "$#" -gt 0 ]; do
    case "$1" in
        --*=*) set -- "${1%%=*}" "${1#*=}" "${@:2}" ;;
        --help|-h)
            cat <<'HELP'
Usage: bash loader.sh [--project DIR] [options]

Start the Docker-hosted UI. With no arguments, ask only for the project directory.
Requires Docker with Compose and curl; no host Python or Node is needed.

  --image IMAGE:TAG   image override
  --port PORT        first host port to try (8765)
  --timeout SECONDS  startup wait (180)
  --no-open          print the session URL instead of opening a browser
  --interactive      choose a project interactively
  --status           show this project's container
  --logs [--follow]   print or follow its logs
  --stop             stop and remove its container
HELP
            exit 0 ;;
        --project|--project-dir|--image|--port|--timeout)
            [ "$#" -ge 2 ] || die "$1 requires a value"
            case "$1" in
                --project|--project-dir) project="$2" ;; --image) image="$2" ;;
                --port) port="$2" ;; --timeout) timeout="$2" ;;
            esac
            shift 2 ;;
        --no-open) open_browser=0; shift ;;
        --interactive) interactive=1; shift ;;
        --stop|--status|--logs)
            [ "$mode" = start ] || die 'choose only one of --stop, --status or --logs'
            mode="${1#--}"; shift ;;
        --follow|-f) follow=1; shift ;;
        --no-mount-repo) repo=''; shift ;;
        *) die "unknown argument: $1 (see --help)" ;;
    esac
done
config="${XDG_CONFIG_HOME:-$HOME/.config}/ti-toolbox"
if [ "$interactive" = 1 ]; then
    [ -t 0 ] || die 'interactive setup needs a terminal; pass --project DIR'
    [ -n "$project" ] || { [ ! -f "$config/last-project.txt" ] || project="$(cat "$config/last-project.txt")"; }
    read -r -p "Project directory${project:+ [$project]}: " answer
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
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
spec="$script_dir/docker-compose.yml"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
if [ ! -f "$spec" ]; then
    curl -fsSL "https://raw.githubusercontent.com/idossha/TI-Toolbox/${TIT_SOURCE_REF:-main}/docker-compose.yml" -o "$work/source.yml" || die 'could not download the container specification'
    spec="$work/source.yml"
fi
if [ -z "$image" ] && [ "$interactive" = 1 ] && [ -n "$ids" ]; then
    image="$(docker inspect --format '{{.Config.Image}}' "$ids")"
fi
if [ -z "$image" ]; then
    # Match the literal Compose placeholder.
    # shellcheck disable=SC2016
    image="$(sed -n 's/^[[:space:]]*image: idossha\/ti-toolbox:${TIT_IMAGE_TAG:-\([^}]*\)}.*/idossha\/ti-toolbox:\1/p' "$spec")"
fi
case "$image" in *[!a-zA-Z0-9_./:@-]*|'') die 'invalid image reference' ;; esac
[[ "$image" == */* ]] || image="idossha/ti-toolbox:$image"
if [ -n "$repo" ]; then
    [ -f "$repo/tit/launch.py" ] || die "not a TI-Toolbox checkout: $repo"
    repo="$(cd "$repo" && pwd -P)"
fi
static=''; reload=''
if [ -n "$repo" ]; then
    static=/ti-toolbox/desktop/out/renderer; reload=1
    [ "$open_browser" = 0 ] || [ -f "$repo/desktop/out/renderer/index.html" ] || die 'build the checkout UI with npm --prefix desktop run build, or use pnpm dev:web from desktop/'
fi
read_env() { docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$ids" | sed -n "s/^$1=//p"; }
if [ -n "$ids" ] && [ "$(docker inspect --format '{{.State.Running}}' "$ids")" = true ]; then
    [ "$(docker inspect --format '{{.Config.Image}}' "$ids")" = "$image" ] || die 'container uses another image; let jobs finish, then use --stop and launch again'
    if [ -n "$repo" ]; then
        mounted="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/ti-toolbox"}}{{.Source}}{{end}}{{end}}' "$ids")"
        [ "$mounted" = "$repo" ] && [ "$(read_env TIT_SERVER_RELOAD)" = 1 ] && [ "$(read_env TIT_STATIC_DIR)" = "$static" ] || die 'container uses another checkout or dev configuration; let jobs finish, then use --stop'
    fi
    token="$(read_env TIT_SERVER_TOKEN)"; port="$(read_env TIT_SERVER_PORT)"
    [ -n "$token" ] && [ -n "$port" ] || die 'container has no session credentials; stop and relaunch it'
else
    [ -z "$ids" ] || docker rm "$ids" >/dev/null
    docker compose version >/dev/null 2>&1 || die 'install the Docker Compose plugin'
    docker image inspect "$image" >/dev/null 2>&1 || docker pull --platform linux/amd64 "$image"
    first_port="$port"
    while (: >"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1; do
        port=$((port+1)); [ "$port" -le 65535 ] && [ "$port" -lt $((first_port+64)) ] || die 'no free port found'
    done
    token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    # Match the Python/Electron project hash so all entry points can attach and stop.
    h1=$((0xDEADBEEF ^ ${#project})); h2=$((0x41C6CE57 ^ ${#project}))
    for ((i=0; i<${#project}; i++)); do
        printf -v code '%d' "'${project:i:1}"
        h1=$(( ((h1 ^ code) * 2654435761) & 0xFFFFFFFF ))
        h2=$(( ((h2 ^ code) * 1597334677) & 0xFFFFFFFF ))
    done
    hash=$(( (((h1 ^ (h1 >> 16)) * 2246822507) ^ ((h2 ^ (h2 >> 13)) * 3266489909)) & 0xFFFFFFFF ))
    printf -v stack 'ti-toolbox-%08x' "$hash"
    mkdir -p "$config"
    export LOCAL_PROJECT_DIR="$project" PROJECT_DIR_NAME="${project##*/}" TIT_USER_CONFIG="$config"
    export TIT_SERVER_TOKEN="$token" TIT_SERVER_PORT="$port" TIT_REPO_DIR="$repo" TIT_SERVER_RELOAD="$reload" TIT_STATIC_DIR="$static"
    TIT_HOST_OS="$(uname -s | tr '[:upper:]' '[:lower:]')"; TIT_HOST_OS_VERSION="$(uname -r)"; TIT_HOST_ARCH="$(uname -m)"
    export TIT_HOST_OS TIT_HOST_OS_VERSION TIT_HOST_ARCH
    export DOCKER_DEFAULT_PLATFORM=linux/amd64
    awk -v image="$image" -v mount="$repo" '
        /^[[:space:]]*image:/ {$0="    image: " image}
        /\$\{TIT_REPO_DIR:-\}:\/ti-toolbox/ && mount=="" {next}
        {print}
    ' "$spec" > "$work/compose.yml"
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
