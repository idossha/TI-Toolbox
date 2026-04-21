# Changelog

## Unreleased

### Launcher parity

**Arch telemetry normalized.** Both launchers now emit `x86_64` (Intel) or
`arm64` (Apple Silicon / ARM) as the `platform` event parameter. Previously
the Electron launcher sent Node's `x64` while `loader.py` sent Python's
`x86_64`, splitting the same hardware into two dashboard slices. Historical
`x64` events in BigQuery are absorbed by a CASE in the analytics view.

**Compose project name unified.** `docker-compose.yml` now declares
`name: ti-toolbox` at the top level (Compose spec v1.12+). Both launchers
produce containers on the same `ti-toolbox_ti_network` network regardless
of which one started them. The `COMPOSE_PROJECT_NAME` env var override in
the Electron launcher has been removed (it's now redundant).

> **Upgrade note:** If you previously launched via `loader.py`, a stale
> Docker network from the old project name may remain. Run
> `docker network prune` to clean it up (no data is lost).

### Known issues (accepted divergences on the CLI path)

- **Windows path format:** `loader.py` passes backslash paths to Docker
  Compose substitutions. Docker Desktop on Windows (WSL2 backend) handles
  both `C:\…` and `C:/…` forms. If a Windows user encounters a mount
  failure, the recommended entrypoint is the desktop app.

- **`TZ` abbreviation:** `loader.py` sets `TZ` from `date +%Z` (e.g.
  `PST`) which glibc interprets as a fixed UTC offset (no DST). The
  Electron launcher uses the IANA zone (`America/Los_Angeles`). Container
  log timestamps may disagree with host local time by one hour during DST
  transitions. Workaround: `export TZ=America/Los_Angeles` before
  launching.
