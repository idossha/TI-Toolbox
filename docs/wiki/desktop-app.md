---
layout: wiki
title: Desktop Application
permalink: /wiki/desktop-app/
---

The TI-Toolbox Desktop Application is an Electron shell around a single Docker container:
`idossha/ti-toolbox:<version>` computes and serves everything (SimNIBS, FastSurfer, the
toolbox UI, and the Tetravox Embed viewer), the host renders it. There is no X11 anywhere in
this design, and no second container to manage — one image, one container, driven entirely
through Docker's own Engine API.

## Architecture Overview

```
Host                                                          idossha/ti-toolbox:<ver> (amd64)
┌─ Electron shell ───────────────────────────────┐            ┌────────────────────────────────────────────┐
│ main: Engine-API client ─ compose.v3.yml ──────┼─ socket ──▶│ entrypoint → simnibs_python -m tit.server   │
│ renderer (served by the container, :port) ─────┼─ http ────▶│   /            → /opt/ti-toolbox/ui         │
│   └─ <iframe src=/tetravox/index.html?embed=1> │            │   /tetravox/   → the active embed (CSP)     │
│        WebGL2+WASM on the host GPU  ◀─ files ──┼───────────▶│   /api/files/raw/{path}  (jailed stream)    │
│        postMessage: load/setCursor/screenshot… │            │   /api/view/{kind} → Tetravox ViewSpec v2   │
└────────────────────────────────────────────────┘            │ jobs: charm · subject_atlas · FastSurfer    │
      docker.sock mounted for DWI (QSIPrep/QSIRecon)          │       seg_only · tit.sim/opt/analyzer/stats │
                                                              └────────────────────────────────────────────┘
```

Everything the user sees — the tabbed UI, dialogs, the 3D/volume viewer — is HTML/JS served
by the container over plain HTTP and rendered by Electron's own renderer process, the same
way a browser would. The Electron **main** process's only job is to get that container
running: talk to Docker over its Engine API, pull the image, start the container with the
right volumes/env, wait for it to answer a health check, then point a `BrowserWindow` at
`http://127.0.0.1:<port>/`.

## What changed from v2

| | v2 | v3 |
|---|---|---|
| **UI** | PyQt5, rendered by the container over X11 forwarding to a host X server | HTML/JS served by the container, rendered by Electron (a normal browser-engine renderer process) — no X server anywhere |
| **Viewer** | Freeview and Gmsh, launched as separate X11 processes inside the container | Tetravox Embed: WebGL2 + WASM, running on the **host** GPU inside an `<iframe>` in the same window, driven by a `postMessage` protocol |
| **Docker orchestration** | `dockerode` for health checks/log streaming + the `docker compose` CLI shelled out to for starting/stopping services | A dependency-free Docker Engine API client only — no CLI subprocess at all, except `docker context inspect` to discover the active context |
| **Images** | Two: `idossha/simnibs` (~19 GB) + a separate FreeSurfer image (~67 GB) | One: `idossha/ti-toolbox:<ver>` (~6.7 GB), SimNIBS + FastSurfer + the UI + the viewer baked in |
| **X11 host setup** | XQuartz (macOS) / VcXsrv (Windows) / native X11 (Linux), `xhost` permission juggling on every launch | None |
| **Compose's role** | Read by both the app (for its own bookkeeping) and shelled out to via the `docker compose` CLI | Still the stack *definition* (one `tit` service, `desktop/docker/docker-compose.v3.yml`), but the app parses the YAML itself and realizes it purely through Engine API calls — `docker compose` is never invoked |

## Components

### Electron Application

#### **Renderer Process** (Frontend)

The window's content is the container's own served UI — the renderer process is a normal
web page (HTML/CSS/JS built from the toolbox's TypeScript sources) loaded from
`http://127.0.0.1:<port>/`, exactly like visiting the app in a browser. The one exception is
the viewer: when a page needs to show a 3D scene or a volume, it mounts an `<iframe>` pointed
at `/tetravox/index.html?embed=1&hostOrigin=<origin>` — the same container's static Tetravox
Embed bundle — and talks to it with `postMessage` (see "The embed protocol" below).

#### **Main Process** (Backend)

The Node.js process that gets the container running and stays out of the way once it is:

- **Docker discovery** (`desktop/src/main/docker/discover.ts`) — resolves the active Docker
  context (`DOCKER_HOST`, then `docker context inspect`, then well-known socket paths). This
  is the *only* place the app still shells out to the `docker` CLI.
- **Stack orchestration** (`desktop/src/main/stack.ts`) — reads `docker-compose.v3.yml`,
  interpolates its `${VAR}` placeholders from the app's own environment map, and drives the
  whole lifecycle (network, volume, image pull with progress, container create/start, health
  check, attach-by-label, stop+remove) through the Engine API client under
  `desktop/src/main/docker/`. There is no `stacks.json` on disk any more: attach-or-start
  works by inspecting the running container's own labels and environment, so it survives a
  cleared `userData` directory.
- **IPC** — the renderer and main processes talk over Electron's IPC exactly as before
  (project selection, launch/stop, log streaming).

### Docker integration

The app's `main` process is a single dependency-free Engine API client (`desktop/src/main/
docker/`) talking to the Docker daemon's own HTTP-over-socket API — no `dockerode`, no
`docker compose` subprocess. Compose stays the **stack definition** (`services.tit.{image,
environment, volumes, ports, labels, healthcheck, command, working_dir, init}`, plus
`networks`/`volumes` — anything else is a startup error naming the key); the app's own parser
reads it and turns it into Engine API calls: pull with progress, create/start the container,
stream logs, health-check, and stop+remove on quit. Named volumes are kept across restarts.

Supported engines: **Docker Desktop** and **Docker Engine**. Colima/OrbStack are best-effort
(same Engine API, not actively tested); Podman is not supported (its `/version` response is
detected and refused by name).

### Updating the viewer without updating the toolbox

The Tetravox embed is delivered dynamically, so a Tetravox release does not require a TI-Toolbox
release (`dev/notes/v3-embed-convergence-plan.md`, decisions E1-E4):

- **The app pins a protocol *range*, not a version.** `tit/tetravox/protocol.py` (and its
  renderer twin `desktop/src/renderer/viewer/embedProtocol.ts`) declare the supported range and a
  map of *named* features — `markers`, `pick`, `camera` — so a page asks "can this embed do
  markers" rather than comparing version numbers. `GET /api/capabilities` reports the active
  bundle's `version`, `protocol`, `source`, `features` and whether it is `compatible`.
- **Two roots, newest compatible wins.** The image still bakes a floor version at
  `/opt/tetravox/embed`, so an offline or air-gapped install is unaffected. Bundles installed
  later live under the user config directory (`~/.config/ti-toolbox/tetravox/embed/<version>/`,
  mounted into the container), and `/tetravox/` resolves on **every request**: the
  `--tetravox-dir` dev override, then the pinned or newest compatible installed version, then the
  baked one. No restart is involved.
- **Installing is explicit and verified.** *Settings → Viewer engine* shows what is running and
  where it came from, checks a release index on request, and installs a bundle by URL + sha256.
  The digest is verified before the archive is opened, extraction rejects absolute paths, `..`
  and links, the manifest's protocol must be inside the supported range, and activation is a
  single atomic rename — a half-extracted bundle is never served. Nothing auto-installs.
- **Rolling back never deletes.** "Use this" on the baked row pins the image's own copy; the
  installed bundle stays on disk, so going forward again is one click.

### The embed protocol

The 3D/volume viewer is not part of the Electron bundle — it is a separate web app
(**Tetravox Embed**) that the container serves at `/tetravox/` and that the toolbox UI mounts
in an `<iframe>` wherever a scene needs to be shown. The two talk over `postMessage`:
the host sends `load {scene}` (a Tetravox `ViewSpec` v2 document that `tit.server` builds
from the simulation/analysis on disk), `setCursor`, `probe`, `screenshot`, layer
visibility/opacity toggles; the embed answers with `ready`, `loaded`, `status`, `cursor`,
`probe`, `screenshot`, `layers`. Every dataset reference inside a scene is an
origin-relative URL — `/api/files/raw/<path>` — so the iframe can `fetch()` mesh/volume bytes
directly from the same container that served it, with no path rewriting on either side. See
[Viewer]({{ site.baseurl }}/wiki/visualizers/) for what this looks like from the UI, and
Tetravox's own `docs/EMBED.md` for the full protocol.

## Launch Workflow

1. **User clicks "Launch TI-Toolbox"**
2. **Docker discovery** — resolves the active Docker context and confirms the daemon answers
3. **Project initialization** — creates the BIDS structure if this is a new project
4. **Image pull** (first launch only) — `idossha/ti-toolbox:<ver>`, with progress reported to the launcher window
5. **Container start** — network/volume ensured, container created with the project mounted, the app's env map, and the right labels, then started
6. **Health check** — polled against `/api/health`, raced against "did the container exit" so a crash on boot reports its exit code instead of a generic timeout
7. **Window opens** on `http://127.0.0.1:<port>/`, the container's own served UI
8. **Active session** — the user interacts with the UI; the viewer, when needed, is an `<iframe>` onto the same container's `/tetravox/`
9. **Cleanup** — on quit, the container is stopped and removed (named volumes are kept)

## Job Model

Every long-running operation — pre-processing, a simulation, flex/ex/mex-search, the
analyzer, group statistics — is a **job**: the UI POSTs a JSON config to `tit.server`, which
runs it as a tracked background process inside the container (a `tit.job_id` label
distinguishes concurrent runs) and streams status/logs back to the UI over the same HTTP
connection the rest of the app already uses. This is unchanged in shape from v2's
subprocess-per-tab pattern (`simnibs_python -m tit.<pipeline> config.json`) — what changed is
*where* it runs: inside the one always-running container, driven over HTTP, rather than a
process the desktop app spawned and monitored itself.

## Building the Application

The desktop app is built with `electron-vite`/`electron-builder`.

**macOS:** `.dmg` installer
**Windows:** `.exe` installer (NSIS)
**Linux:** `.AppImage`, `.deb` package

```bash
cd desktop
npm install
npm run build
```

## Development

```bash
cd desktop
npm install
npm run dev
```

## Dependencies

**Runtime:**
- Docker Desktop or Docker Engine (required)

**Development:**
- Node.js ≥22.12 (electron-vite/electron-builder toolchain)

## Security

- **Docker Access:** the main process holds a direct, unmediated handle to the host's Docker
  socket; `stack.start`/`stack.stop` are reachable only from the launcher window, not from
  every renderer.
- **No X11 permissions:** there is nothing to grant or revert on launch/exit — removed
  entirely along with X11 itself.
- **Tetravox Embed's CSP:** the `/tetravox/` route serves its own Content-Security-Policy
  (`script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:`), scoped to that route only
  — the app's own top-level page does not carry `'wasm-unsafe-eval'`.

## Performance

- **Startup Time:** a few seconds once the image is pulled; the first launch downloads the
  one image (~6.7 GB)
- **Memory Usage:** small for the app itself; the container needs whatever RAM the workload
  needs (16GB+ Docker allocation recommended, 32GB+ for large leadfields/FastSurfer — see
  [Dependencies]({{ site.baseurl }}/installation/dependencies/))
- **Disk Space:** ~6.7 GB for the image plus your project outputs

## Troubleshooting

**Docker not found:**
Ensure Docker Desktop is installed and running.

**Permission errors:**
Check that your user has access to the Docker daemon (usually requires membership in the
`docker` group on Linux).

**Podman:**
Not supported — the app detects and refuses a Podman-flavored `/version` response by name.

## See Also

- [Installation Guide]({{ site.baseurl }}/installation/)
- [Viewer]({{ site.baseurl }}/wiki/visualizers/)
- [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/)
