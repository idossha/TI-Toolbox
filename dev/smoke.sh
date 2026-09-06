#!/usr/bin/env bash
# Run the Level A pipeline smoke harness against the running dev container.
#
# What it does
#   Discovers the dev stack by its labels (never by a hard-coded name or port -- the container
#   name carries a per-project hash, `ti-toolbox-<hash>-tit-1`, so a hard-coded name is wrong on
#   every machine but one), reads the port, the token and the host project directory out of
#   `docker inspect`, and runs `tests/smoke` with those in the environment. No token is ever
#   typed, pasted or written to disk.
#
# Usage
#   dev/smoke.sh                       # the whole matrix
#   dev/smoke.sh sim analyzer_mesh     # only those rows (row id, or a kind -> all its rows)
#   dev/smoke.sh --keep                # keep everything the run created, for inspection
#   dev/smoke.sh --full                # run the long kinds to completion instead of cancelling
#   dev/smoke.sh --list                # print every dev-stack container found and its exact
#                                       # selector, run nothing (exit 0; 2 if none are running)
#
# Exit codes: 0 green, 1 a row failed, 2 could not check (no container / no token / no python3).
# 2 is never a pass -- it means the harness could not tell you anything.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_LABEL="tit.stack=ti-toolbox-v3"
SERVICE_LABEL="tit.service=tit"

die_cannot_check() { echo "smoke: cannot check -- $*" >&2; exit 2; }

# One line of `docker inspect`-derived detail for container id $1, plus the exact env-var
# invocation that selects it when more than one dev stack is running -- copy-pasteable, not a
# pointer to "set one of these two variables and figure out the value yourself".
describe_container() {
  local c="$1" name proj port
  name="$(docker inspect "$c" --format '{{ .Name }}' | sed 's|^/||')"
  proj="$(docker inspect "$c" --format '{{ index .Config.Labels "tit.host_project_dir" }}')"
  [ "$proj" = "<no value>" ] && proj="(no tit.host_project_dir label)"
  # `|| true`: unlike the main flow's own port lookup (which must fail loudly -- the container
  # it picked has to actually be usable), a container listed here only for disambiguation may
  # legitimately publish nothing yet; grep matching nothing exits 1, and pipefail would abort
  # the whole script (found while testing --list against a two-container fixture, 2026-09-04).
  port="$(docker inspect "$c" \
    --format '{{ range $p, $b := .NetworkSettings.Ports }}{{ if $b }}{{ (index $b 0).HostPort }} {{ end }}{{ end }}' \
    | tr " " "\n" | grep -v '^$' | head -1 || true)"
  echo "  ${name}  port=${port:-?}  project=${proj}"
  echo "    -> TIT_SMOKE_CONTAINER=${name} dev/smoke.sh"
}

command -v docker >/dev/null 2>&1 || die_cannot_check "docker is not on PATH"
command -v python3 >/dev/null 2>&1 || die_cannot_check "python3 is not on PATH"

kinds=()
extra_args=()
list_only=0
for arg in "$@"; do
  case "$arg" in
    --keep) extra_args+=("--smoke-keep") ;;
    --full) extra_args+=("--smoke-full") ;;
    --list) list_only=1 ;;
    -*)     extra_args+=("$arg") ;;   # anything else is passed through to pytest
    *)      kinds+=("$arg") ;;
  esac
done

# `mapfile` is bash 4+; macOS still ships bash 3.2 as /bin/bash, so read the ids the portable way.
containers=()
while IFS= read -r line; do
  [ -n "$line" ] && containers+=("$line")
done < <(docker ps --filter "label=${STACK_LABEL}" --filter "label=${SERVICE_LABEL}" --format '{{.ID}}')
if [ "${#containers[@]}" -eq 0 ]; then
  die_cannot_check "no running container labelled ${STACK_LABEL} (start it with: cd desktop && npm run dev)"
fi

if [ "$list_only" -eq 1 ]; then
  echo "smoke: ${#containers[@]} container(s) labelled ${STACK_LABEL},${SERVICE_LABEL}:"
  for c in "${containers[@]}"; do
    describe_container "$c"
  done
  exit 0
fi

# TIT_SMOKE_CONTAINER narrows the list *before* the count check, not only when several stacks
# are up: naming a container that is not running must be "cannot check" (exit 2), never a
# silent run against whichever single stack happens to be there (that mistake started a full
# matrix run against the shared container on 2026-09-03).
if [ -n "${TIT_SMOKE_CONTAINER:-}" ]; then
  narrowed=()
  for c in "${containers[@]}"; do
    name="$(docker inspect "$c" --format '{{ .Name }}' | sed 's|^/||')"
    if [ "$c" = "$TIT_SMOKE_CONTAINER" ] || [ "$name" = "$TIT_SMOKE_CONTAINER" ]; then
      narrowed+=("$c")
    fi
  done
  if [ "${#narrowed[@]}" -eq 0 ]; then
    die_cannot_check "TIT_SMOKE_CONTAINER=${TIT_SMOKE_CONTAINER} names no running container labelled ${STACK_LABEL}"
  fi
  containers=("${narrowed[@]}")
fi
if [ "${#containers[@]}" -gt 1 ]; then
  # More than one dev stack is normal on a shared machine (another lane's scratch project).
  # Disambiguate explicitly rather than guessing: TIT_SMOKE_CONTAINER names the container,
  # TIT_SMOKE_PROJECT_HOST names the project directory whose stack we want.
  picked=""
  for c in "${containers[@]}"; do
    name="$(docker inspect "$c" --format '{{ .Name }}' | sed 's|^/||')"
    proj="$(docker inspect "$c" --format '{{ index .Config.Labels "tit.host_project_dir" }}')"
    if [ -n "${TIT_SMOKE_CONTAINER:-}" ] && { [ "$c" = "$TIT_SMOKE_CONTAINER" ] || [ "$name" = "$TIT_SMOKE_CONTAINER" ]; }; then
      picked="$c"
    elif [ -z "${TIT_SMOKE_CONTAINER:-}" ] && [ -n "${TIT_SMOKE_PROJECT_HOST:-}" ] && [ "$proj" = "$TIT_SMOKE_PROJECT_HOST" ]; then
      picked="$c"
    fi
  done
  if [ -z "$picked" ]; then
    {
      echo "smoke: ${#containers[@]} containers labelled ${STACK_LABEL}; pick one with the"
      echo "exact selector printed under it (or TIT_SMOKE_PROJECT_HOST=<project dir>):"
      for c in "${containers[@]}"; do
        describe_container "$c"
      done
    } >&2
    die_cannot_check "more than one dev stack is running (dev/smoke.sh --list shows this any time)"
  fi
  containers=("$picked")
fi
container="${containers[0]}"

# Port: the host side of the published 8765/tcp mapping. Token and project directory: the
# container's own env/labels, which is where `desktop/scripts/dev.ts` put them.
# The container publishes exactly one TCP port (the server); read whichever it is rather than
# assuming 8765 -- desktop/scripts/dev.ts honours TIT_DEV_PORT.
port="$(docker inspect "$container" \
  --format '{{ range $p, $b := .NetworkSettings.Ports }}{{ if $b }}{{ (index $b 0).HostPort }} {{ end }}{{ end }}' \
  | tr " " "\n" | grep -v '^$' | head -1)"
[ -n "$port" ] || die_cannot_check "container $container publishes no host port"

token="$(docker inspect "$container" \
  --format '{{ range .Config.Env }}{{ println . }}{{ end }}' | sed -n 's/^TIT_SERVER_TOKEN=//p' | head -1)"
[ -n "$token" ] || die_cannot_check "container $container has no TIT_SERVER_TOKEN in its environment"

host_project="$(docker inspect "$container" --format '{{ index .Config.Labels "tit.host_project_dir" }}')"
[ "$host_project" = "<no value>" ] && host_project=""
[ -n "$host_project" ] || die_cannot_check \
  "cannot tell where the project directory lives on this host (no tit.host_project_dir label)"

url="http://127.0.0.1:${port}"
echo "smoke: container ${container} -> ${url}, project ${host_project}"

# No -x: the point of a matrix run is the whole table, including which rows failed. Rows are
# sequential (one heavy job at a time, decision P7) and each cleans up after itself.
pytest_args=(-p no:cacheprovider -m smoke "tests/smoke" --no-header -q)
if [ "${#kinds[@]}" -gt 0 ]; then
  pytest_args+=("--smoke-kinds=$(IFS=,; echo "${kinds[*]}")")
fi
if [ "${#extra_args[@]}" -gt 0 ]; then
  pytest_args+=("${extra_args[@]}")
fi

cd "$REPO_ROOT"
TIT_SMOKE_SERVER_URL="$url" \
TIT_SMOKE_TOKEN="$token" \
TIT_SMOKE_PROJECT_HOST="$host_project" \
  python3 -m pytest "${pytest_args[@]}"
