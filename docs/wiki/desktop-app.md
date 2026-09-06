---
layout: wiki
title: Desktop Application
permalink: /wiki/desktop-app/
---

The TI-Toolbox Desktop Application is an Electron shell around a single Docker container:
`idossha/ti-toolbox:<version>` computes and serves everything (SimNIBS, FastSurfer and the
toolbox UI), the host renders it. There is no X11 anywhere in this design, and no second
container to manage — one image, one container, driven entirely through Docker's own Engine API.

3D viewing is a **separate desktop application**, [Tetravox](https://github.com/idossha/tetravox),
installed on the host. The toolbox writes a scene file and asks the app to open it; the app
updates itself and knows nothing about TI-Toolbox's release cycle.

## Architecture Overview

```
Host                                                          idossha/ti-toolbox:<ver> (amd64)
┌─ Electron shell ───────────────────────────────┐            ┌────────────────────────────────────────────┐
│ main: Engine-API client ─ compose.v3.yml ──────┼─ socket ──▶│ entrypoint → simnibs_python -m tit.server   │
│ renderer (served by the container, :port) ─────┼─ http ────▶│   /            → /opt/ti-toolbox/ui         │
│   └─ run-page 3-D panes: own WebGL2 renderer   │            │   /api/scene/*  → surfaces, electrodes, atlas│
│                                                │            │   /api/files/raw/{path}  (jailed stream)    │
│ ┌─ Tetravox.app (host) ◀─ spawn <scene file> ──┼───────────▶│   /api/view/open → <project>/code/ti-toolbox/│
│ └─ its own window, its own updates             │            │                    viewer/*.tetravox.json   │
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
| **Viewer** | Freeview and Gmsh, launched as separate X11 processes inside the container | The **Tetravox desktop app** on the host, opened with a scene file the server writes. The run pages' own 3-D panes are drawn in-app by a small WebGL2 renderer |
| **Docker orchestration** | `dockerode` for health checks/log streaming + the `docker compose` CLI shelled out to for starting/stopping services | A dependency-free Docker Engine API client only — no CLI subprocess at all, except `docker context inspect` to discover the active context |
| **Images** | Two: `idossha/simnibs` (~19 GB) + a separate FreeSurfer image (~67 GB) | One: `idossha/ti-toolbox:<ver>` (~6.7 GB), SimNIBS + FastSurfer + the UI. No viewer is baked in |
| **X11 host setup** | XQuartz (macOS) / VcXsrv (Windows) / native X11 (Linux), `xhost` permission juggling on every launch | None |
| **Compose's role** | Read by both the app (for its own bookkeeping) and shelled out to via the `docker compose` CLI | Still the stack *definition* (one `tit` service, `desktop/docker/docker-compose.v3.yml`), but the app parses the YAML itself and realizes it purely through Engine API calls — `docker compose` is never invoked |

## Components

### Electron Application

#### **Renderer Process** (Frontend)

The window's content is the container's own served UI — the renderer process is a normal
web page (HTML/CSS/JS built from the toolbox's TypeScript sources) loaded from
`http://127.0.0.1:<port>/`, exactly like visiting the app in a browser. Nothing in it is framed:
the run pages' 3-D panes are drawn by the app's own WebGL2 renderer, and full viewing is the
Tetravox desktop app (see "Opening a scene in Tetravox" below).

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

### Opening a scene in Tetravox

The 3D/volume viewer is not part of this app and is not served by the container — it is
[Tetravox](https://github.com/idossha/tetravox), an ordinary signed, notarised desktop
application. **You do not have to install it.** TI-Toolbox installs and maintains it for you
(`dev/notes/v3-native-panes-external-viewer/TI.md`, decision V6); its part is then one file
(`dev/notes/v3-native-panes-external-viewer-plan.md`, decisions V1-V4):

- **The Viewer page is a selector.** Pick a subject, a simulation, an analysis, a group result or
  an arbitrary file, then press **Open in Tetravox**.
- **The server writes the scene.** `POST /api/view/open` builds the same ViewSpec v2 document
  `GET /api/view/{kind}` returns, rewrites every dataset path from an `/api/files/raw/…` URL to
  the **host's** own absolute path, and writes it to
  `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`. The extension matters: that compound
  extension is what the Tetravox app registers as its scene document, and any other suffix is
  read as a data file instead.
- **The shell opens it.** Electron's main process maps the container path to the host path
  through the same project mount `openPath` uses, then launches the app: on macOS
  `open -a Tetravox <scene>` **followed by a plain `open -a Tetravox`**, elsewhere the resolved
  binary, detached. A second Open is a second launch: Tetravox holds a single-instance lock and
  routes the file into the window already on screen instead of opening another one.
  The second, document-less call is not decoration. A macOS app whose window you closed with ⌘W
  keeps running with no window; in that state Tetravox's `open-file` handler stores the scene and
  creates nothing, `open` still exits 0, and the launch would report success with nothing on
  screen. The extra call is an *activation*, which is what makes the app create a window — and
  that window then picks up the scene the first call handed over.
- **A launch that fails says so.** `open`'s exit code and stderr are the result of the launch
  (they used to be discarded), so a moved bundle or a refused document reaches the Viewer page as
  a failure with a reason, not as "Opened …".
- **The managed install.** The first **Open in Tetravox** on a machine that has no viewer
  downloads one — one click, no dialog, progress while it runs — into
  `<userData>/tetravox/<version>/`, and then opens the scene. TI-Toolbox picks the newest
  non-prerelease GitHub release, takes the single asset for the platform
  (`…-mac-arm64.zip` / `…-mac-x64.zip` / `…-win-x64.exe` / `…-linux-x86_64.AppImage`) and
  **verifies it against the SHA-512 the release's own `latest*.yml` states** before anything is
  moved into place. On macOS the bundle is unpacked with `ditto`, and the quarantine attribute is
  removed *only* if `codesign --verify` passes — an unsigned or damaged download keeps it and
  meets Gatekeeper.
- **Updates never interrupt you.** The release index is checked at most once a day, in the
  background, and never on the path to a launch: an offline machine opens the version it has. A
  newer version is downloaded and verified, then becomes active the *next* time you start
  TI-Toolbox, so nothing is swapped underneath an open window. The last two versions are kept.
- **Discovery, and one override.** Managed install first, then a path you set yourself, then a
  copy already on the machine: `/Applications/Tetravox.app` and `~/Applications` on macOS,
  `%LOCALAPPDATA%\Programs\Tetravox\Tetravox.exe` on Windows, `tetravox` on `PATH` (or
  `~/.local/bin`, `/usr/bin`, `/usr/local/bin`) on Linux. *Settings → Viewer* shows the installed
  version, that TI-Toolbox installed it, when it last checked, and its disk usage, with
  **Check for updates**, **Use a different Tetravox…** (the path override) and **Remove**.
- **In a browser**, where there is no main process to spawn or install anything, the button
  downloads the scene file instead; open it with **File ▸ Open Scene…**. This is unchanged.

Nothing about the viewer is a server capability any more: the container has no display, ships no
viewer, and `GET /api/capabilities` says nothing about one. Putting Tetravox *inside* the image
was considered and rejected for the same reason — a headless container has no display and no GPU,
and since Chromium 137 there is no software-WebGL fallback to stand in for one, so the viewer has
to run on the host's own hardware. Something therefore has to put it there, and that something is
this app rather than the person using it.

## Launch Workflow

1. **User clicks "Launch TI-Toolbox"**
2. **Docker discovery** — resolves the active Docker context and confirms the daemon answers
3. **Project initialization** — creates the BIDS structure if this is a new project
4. **Image pull** (first launch only) — `idossha/ti-toolbox:<ver>`, with progress reported to the launcher window
5. **Container start** — network/volume ensured, container created with the project mounted, the app's env map, and the right labels, then started
6. **Health check** — polled against `/api/health`, raced against "did the container exit" so a crash on boot reports its exit code instead of a generic timeout
7. **Window opens** on `http://127.0.0.1:<port>/`, the container's own served UI
8. **Active session** — the user interacts with the UI; full 3-D viewing, when needed, opens in the host's Tetravox app
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
- **No WASM eval, and nothing framed:** with the embed retired the app's CSP grants neither
  `'unsafe-eval'` nor `'wasm-unsafe-eval'` anywhere, and the only `frame-src` it allows is the
  published documentation site.
- **The launch bridge names no program:** `window.tit.viewer.open` takes a *container* path the
  server just wrote, which main maps through the known project mount and refuses unless it ends
  in `.tetravox.json`. The only executable it can start is the one discovery (or the user's own
  Settings override) says Tetravox is.

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
