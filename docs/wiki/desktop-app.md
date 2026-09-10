---
layout: wiki
title: Desktop Application
permalink: /wiki/desktop-app/
---

The TI-Toolbox Desktop Application is an Electron shell around a single Docker container:
`idossha/ti-toolbox:<version>` provides the core workflow (SimNIBS, FastSurfer, the toolbox
UI and the [Tetravox](https://github.com/idossha/tetravox) Embed viewer), the host renders it.
There is no X11 setup. The app manages the core container; optional FreeSurfer and diffusion
workflows start their own workers when needed.

**You install no viewer.** 3-D viewing is the Tetravox Embed: a browser build of the Tetravox
engine that ships inside the image, is served by the container at `/tetravox/`, and runs on your
own machine's GPU inside the app window. It can also update itself without a TI-Toolbox release
(see "Updating the viewer without updating the toolbox").

## Architecture Overview

```
Host                                                          idossha/ti-toolbox:<ver> (amd64)
┌─ Electron shell ───────────────────────────────┐            ┌────────────────────────────────────────────┐
│ main: Engine-API client ─ docker-compose.yml ──────┼─ socket ──▶│ entrypoint → simnibs_python -m tit.server   │
│ renderer (served by the container, :port) ─────┼─ http ────▶│   /            → /opt/ti-toolbox/ui         │
│   ├─ run-page 3-D panes: own WebGL2 renderer   │            │   /tetravox/   → the active embed (own CSP) │
│   └─ Viewer page ▸ Viewer sub-page:            │            │   /api/scene/*  → surfaces, electrodes, atlas│
│        <iframe src=/tetravox/> WebGL2+WASM     │◀─ files ──▶│   /api/files/raw/{path}  (jailed stream)    │
│        on the host GPU, postMessage: load/…    │            │   /api/view/open → the scene, twice over:   │
│                                                │            │     into the iframe, and onto disk at       │
└────────────────────────────────────────────────┘            │     <project>/code/ti-toolbox/viewer/*.tetravox.json │
                                                              │ jobs: charm · subject_atlas · FastSurfer    │
      docker.sock mounted for DWI (QSIPrep/QSIRecon)          │       seg_only · tit.sim/opt/analyzer/stats │
                                                              └────────────────────────────────────────────┘
```

Before a project is open, Electron serves the welcome Overview from its bundled UI; no
container is needed to see the welcome page and full sidebar. Opening a project starts or
attaches to its container, then loads the same application from `http://127.0.0.1:<port>/`.
The connected UI and viewer are HTML/JS rendered on the host, as in a browser. Electron's
main process owns Docker discovery, image pull, project selection, confirmed project
switching, health checks and shutdown.

## What changed from v2

| | v2 | v3 |
|---|---|---|
| **UI** | PyQt5, rendered by the container over X11 forwarding to a host X server | HTML/JS served by the container, rendered by Electron (a normal browser-engine renderer process) — no X server anywhere |
| **Viewer** | Freeview and Gmsh, launched as separate X11 processes inside the container | Tetravox Embed: WebGL2 + WASM, running on the **host** GPU inside an `<iframe>` in the same window, driven by a `postMessage` protocol. The run pages' own small 3-D panes are drawn separately by the app's own WebGL2 renderer |
| **Docker orchestration** | `dockerode` for health checks/log streaming + the `docker compose` CLI shelled out to for starting/stopping services | A dependency-free Docker Engine API client only — no CLI subprocess at all, except `docker context inspect` to discover the active context |
| **Images** | Two: `idossha/simnibs` (~19 GB) + a separate FreeSurfer image (~67 GB) | One core image: `idossha/ti-toolbox:<ver>`, SimNIBS + FastSurfer + the UI + viewer; optional FreeSurfer runs in a temporary worker |
| **X11 host setup** | XQuartz (macOS) / VcXsrv (Windows) / native X11 (Linux), `xhost` permission juggling on every launch | None |
| **Compose's role** | Read by both the app (for its own bookkeeping) and shelled out to via the `docker compose` CLI | Still the stack *definition* (one `tit` service, the root `docker-compose.yml`), but the app parses the YAML itself and realizes it purely through Engine API calls — `docker compose` is never invoked |

## Components

### Electron Application

#### **Renderer Process** (Frontend)

After a project opens, the window's content is the container's own served UI — the renderer process is a normal
web page (HTML/CSS/JS built from the toolbox's TypeScript sources) loaded from
`http://127.0.0.1:<port>/`, exactly like visiting the app in a browser. The run pages' small 3-D
panes are drawn by the app's own WebGL2 renderer. Full viewing is the Viewer page's Viewer
sub-page, which mounts an `<iframe>` pointed at `/tetravox/index.html?embed=1&hostOrigin=<origin>`
— the same container's static Tetravox Embed bundle — and talks to it with `postMessage`
(see "The embed protocol" below).

#### **Main Process** (Backend)

The Node.js process that gets the container running and stays out of the way once it is:

- **Docker discovery** (`desktop/src/main/docker/discover.ts`) — resolves the active Docker
  context (`DOCKER_HOST`, then `docker context inspect`, then well-known socket paths). This
  is the *only* place the app still shells out to the `docker` CLI.
- **Stack orchestration** (`desktop/src/main/stack.ts`) — reads the root `docker-compose.yml`,
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

### Opening a result in the viewer

The **Viewer** entry in the left rail has two indented rows under it, **Menu** and **Tetravox**,
and you move between them by clicking those rows. Clicking Viewer itself opens Menu.

- **Menu** — choose a source (a subject, a simulation, an analysis, a group result or an arbitrary
  file), then edit the **What will open** list: remove a file, add one, reorder it. The list is the
  scene; nothing loads while you are choosing.
- **Tetravox** — press **Open in viewer** and you are moved here, where the scene is drawn
  full-bleed by the embed. A slim strip carries the scene's name and **Reload**, which re-sends the
  scene it is showing. To go back, click **Menu** in the rail; the picture is not thrown away —
  tinker with the list, press Open again, and the new scene replaces the old one in the same frame.

Once a project is open, in a narrow window (below 1440 px) the rail shows icons only and the two sub-rows are not drawn. The welcome Overview keeps the full labeled sidebar visible before project selection.
Reach them from the command palette instead, which lists both by name (`Viewer · Menu`,
`Viewer · Tetravox`).

**One press, one request.** `POST /api/view/open` resolves the scene once and gives back two
addressings of it. One has every dataset as an `/api/files/raw/…` URL and is what goes into the
frame; the other has the same layers as paths on your own machine and is written into your project
at `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`. That file is an ordinary file you keep:
a few kilobytes, `ViewSpec` v2 (Tetravox's own format — TI-Toolbox invents none of its own), and you
can hand it to a Tetravox desktop application later, or archive it with the results it describes.
Both come from a single resolution on purpose, so what the list says, what the file holds and what
you are looking at cannot disagree.

**In a browser**, where the page is served without the desktop shell, everything above still works:
the embed is served by the same container, so viewing needs no desktop application at all.

### Updating the viewer without updating the toolbox

The embed is delivered dynamically, so a Tetravox release does not require a TI-Toolbox release
(`docs/dev/DECISIONS.md § 2026-09-04 (embed convergence)`, decisions E1-E4):

- **The app pins a protocol *range*, not a version.** `tit/tetravox/protocol.py` (and its renderer
  twin `desktop/src/renderer/viewer/embedProtocol.ts`) declare the supported range and a map of
  *named* features — `markers`, `pick`, `camera` — so a page asks "can this embed do markers"
  rather than comparing version numbers. `GET /api/capabilities` reports the active bundle's
  `version`, `protocol`, `source`, `features` and whether it is `compatible`.
- **Two roots, newest compatible wins.** The image bakes a floor version at `/opt/tetravox/embed`,
  so an offline or air-gapped install is unaffected. Bundles installed later live under the user
  config directory (`~/.config/ti-toolbox/tetravox/embed/<version>/`, mounted into the container),
  and `/tetravox/` resolves on **every request**: the `--tetravox-dir` dev override, then the
  pinned or newest compatible installed version, then the baked one. No restart is involved.
- **Installing is verified.** *Settings → Viewer* shows what is running and where it came from,
  checks the release index when asked, and installs a bundle by URL + sha256. The digest is
  verified before the archive is opened, extraction rejects absolute paths, `..` and links, the
  manifest's protocol must be inside the supported range, and activation is a single atomic
  rename — a half-extracted bundle is never served.
- **Automatic updates are a policy you can turn off.** On by default: the server checks the release
  index at startup and once every 24 hours, in the background and never on the path to a render, and
  an offline machine simply keeps the bundle it has. Your setting is stored beside the pin.
- **Rolling back never deletes.** "Use this" on the baked row pins the image's own copy; the
  installed bundle stays on disk, so going forward again is one click.

### The embed protocol

The 3D/volume viewer is not part of the Electron bundle — it is a separate web app (**Tetravox
Embed**) that the container serves at `/tetravox/` and that the Viewer sub-page mounts in an
`<iframe>`. The two talk over `postMessage`: the host sends `load {scene}` (a Tetravox `ViewSpec`
v2 document that `tit.server` builds from the simulation/analysis on disk), `setCursor`, `probe`,
`screenshot`, layer visibility/opacity toggles; the embed answers with `ready`, `loaded`, `status`,
`cursor`, `probe`, `screenshot`, `layers`. Every dataset reference inside the scene the frame
receives is an origin-relative URL — `/api/files/raw/<path>` — so the iframe can `fetch()`
mesh/volume bytes directly from the same container that served it, with no path rewriting on either
side. See [Viewer]({{ site.baseurl }}/wiki/visualizers/) for what this looks like from the UI, and
Tetravox's own `docs/EMBED.md` for the full protocol.

## Launch Workflow

The welcome Overview connects the desktop application to its matching scientific image. See the
[installation guide]({{ site.baseurl }}/installation/) for setup and artifact availability.

1. **Open a project from Overview** — type a project directory or use Browse, then click Open project
2. **Docker discovery** — resolves the active Docker context and confirms the daemon answers
3. **Existing session choice** — if any TI-Toolbox container is running, select it and choose Attach or Replace. Attach retains its actual project and configuration; Replace uses the requested project and YAML.
4. **Image pull** (when the matching image is absent) — `idossha/ti-toolbox:<ver>`, with progress reported in Overview
5. **Container start** — network/volume ensured, container created with the project mounted, the app's env map, and the right labels, then started
6. **Health check** — polled against `/api/health`, raced against "did the container exit" so a crash on boot reports its exit code instead of a generic timeout
7. **Same window connects** to `http://127.0.0.1:<port>/`, the container's own served UI
8. **Active session** — the user interacts with the UI; full 3-D viewing, when needed, is the Viewer page's own Viewer sub-page, drawn by the embed on the host GPU
9. **Switch or quit** — Switch project opens a directory form, then confirms and replaces the current session with the selected project. Closing the window or choosing Quit stops/removes the container and exits Electron. Named volumes are kept.

## Command-line and development launch

The regular CLI opens the browser by default. Use `--desktop` to give Electron ownership of
the selected session. Developer browser mode remains convenient for fast iteration.

| Entry point | Interface and lifetime |
|---|---|
| `python3 loader.py` / `bash loader.sh` | Browser by default; explicit `--stop` ends the session. |
| Either loader with `--desktop` | Electron UI; closing the app stops/removes its container and exits. |
| `dev/loader/loader_dev.py` / `dev/loader/loader_dev.sh` | Browser with checkout mounts for newly created sessions. |
| `npm run dev` in `desktop/` | Builds and opens welcome Overview; select a project in Electron. Closing stops its container. |
| `npm run dev:web` | Browser with Vite; container remains until `npm run dev:down`. |

All Docker starts use the shared root Compose specification (packaged apps carry their copy).
Every route requires an explicit choice before reusing a running session. Attach may select a
session from another project; the displayed project remains that session's actual project.
Replacement affects only the selected container. See the
[launcher reference]({{ site.baseurl }}/installation/bash-cli/) for flags and prerequisites.

In a browser there is no Electron bridge (`window.tit`), so reveal-in-file-manager, native
notifications, the Settings → Docker card and the project picker are absent — each with a
message or a fallback rather than a failure. See
[the command-line launcher]({{ site.baseurl }}/installation/bash-cli/#what-is-different-in-a-browser).

## Job Model

Every long-running operation — pre-processing, a simulation, flex/ex/mex-search, the
analyzer, group statistics — is a **job**: the UI POSTs a JSON config to `tit.server`, which
runs it as a tracked background process inside the container (a job ID
distinguishes concurrent runs; separately launched job containers carry a `tit.job_id` label) and streams status/logs back to the UI over the same HTTP
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
  socket. Initial `stack.start` is restricted to the local welcome page. The connected main
  window may stop its own session; switching to another host directory requires native
  confirmation of the exact destination before the new mount is created.
- **No X11 permissions:** there is nothing to grant or revert on launch/exit — removed
  entirely along with X11 itself.
- **Tetravox Embed's CSP:** the `/tetravox/` route serves its own Content-Security-Policy
  (`script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:`), scoped to that route only —
  the app's own top-level page carries neither `'unsafe-eval'` nor `'wasm-unsafe-eval'`.
- **No program is ever launched for viewing:** the viewer is a same-origin page in an iframe, not
  a process. The desktop shell exposes no bridge method that starts an application.
- **Downloads are verified before they are unpacked:** a viewer bundle installed at runtime is
  checked against its sha256 first, extracted with absolute paths, `..` and links refused, and
  activated by one atomic rename.

## Performance

- **Startup Time:** depends on image availability and host performance. Loading an image
  for the first time takes longer than starting a cached one.
- **Memory Usage:** small for the app itself; the container needs whatever RAM the workload
  needs (16GB+ Docker allocation recommended, 32GB+ for large leadfields/FastSurfer — see
  [Dependencies]({{ site.baseurl }}/installation/dependencies/))
- **Disk Space:** allow space for the image, working data and project outputs; see the
  [installation guide]({{ site.baseurl }}/installation/) for the selected image.

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
