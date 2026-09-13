---
layout: wiki
title: Desktop Application
permalink: /wiki/desktop-app/
---

The TI-Toolbox Desktop Application manages the scientific workflow in
`idossha/ti-toolbox:<version>` and renders the toolbox UI on your host. Optional FreeSurfer and
diffusion workflows start their own workers when needed. There is no X11 setup.

Full viewing opens **[TetraVox](https://github.com/idossha/tetravox)** in a separate native window.
**Settings → Viewer** installs the supported official release into TI-Toolbox's per-user runtime
directory. The container builds scene files; the desktop opens their host paths in TetraVox.

## Architecture Overview

The container owns scientific computation, job records and project outputs. TI-Toolbox Desktop
owns Docker discovery, project selection and native viewer installation/launch. TetraVox reads the
project's scene and datasets directly from the host filesystem and renders with its WebGL2 engine.
The run pages retain their own small WebGL2 surface panes.

Before a project is open, Electron serves the welcome Overview from its bundled UI. Opening a
project starts or attaches to its container, then loads the application from
`http://127.0.0.1:<port>/`. TetraVox's window is independent of this connection.

## What changed from v2

| | v2 | v3 |
|---|---|---|
| **UI** | PyQt5, rendered by the container over X11 forwarding to a host X server | HTML/JS served by the container, rendered by Electron (a normal browser-engine renderer process) — no X server anywhere |
| **Viewer** | Freeview and Gmsh, launched as separate X11 processes inside the container | Native TetraVox: WebGL2 + WASM in its own host window. Run-page surface panes retain the toolbox's own WebGL2 renderer |
| **Docker orchestration** | `dockerode` for health checks/log streaming + the `docker compose` CLI shelled out to for starting/stopping services | A dependency-free Docker Engine API client only — no CLI subprocess at all, except `docker context inspect` to discover the active context |
| **Images** | Two: `idossha/simnibs` (~19 GB) + a separate FreeSurfer image (~67 GB) | One core image: `idossha/ti-toolbox:<ver>`, SimNIBS + FastSurfer + the UI; optional FreeSurfer runs in a temporary worker |
| **X11 host setup** | XQuartz (macOS) / VcXsrv (Windows) / native X11 (Linux), `xhost` permission juggling on every launch | None |
| **Compose's role** | Read by both the app (for its own bookkeeping) and shelled out to via the `docker compose` CLI | Still the stack *definition* (one `tit` service, the root `docker-compose.yml`), but the app parses the YAML itself and realizes it purely through Engine API calls — `docker compose` is never invoked |

## Components

### Electron Application

#### **Renderer Process** (Frontend)

After a project opens, the window's content is the container's own served UI — the renderer process is a normal
web page (HTML/CSS/JS built from the toolbox's TypeScript sources) loaded from
`http://127.0.0.1:<port>/`, exactly like visiting the app in a browser. The run pages' small 3-D
panes are drawn by the app's own WebGL2 renderer. Volume and target previews offer an explicit
**Open in TetraVox** action; full scenes open in the native viewer window.

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

Use **Viewer → Menu** to choose the subject, space and files, then press **Open in viewer**.
TI-Toolbox prepares a `.tetravox.json` scene and opens it in native TetraVox. The **Tetravox**
sub-page provides installation and reopening controls; it no longer contains a rendered iframe.
Change the selection in Menu and open it again to replace the scene in the native window.

Scene files are written to `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`, with dataset
paths resolved for the host. Keep these ordinary TetraVox files with the results they describe.
Use TetraVox's own controls to adjust layers, camera and appearance, and save those edits there.
TI-Toolbox's **Save scene** saves the prepared composition; it does not read changes back from the
native window. See [Viewer]({{ site.baseurl }}/wiki/visualizers/) for selection and saved-scene details.

### Installing and managing the viewer

**Settings → Viewer** installs the pinned official **TetraVox 0.4.0** release. The download's
SHA256 is checked before installation. Files live under TI-Toolbox's per-user application-data
folder in `runtimes/tetravox-0.4.0-<platform>-<architecture>`; a separate TetraVox profile keeps it
independent of a standalone installation. Supported packages cover macOS arm64/x64 and Linux or
Windows x64. The first installation needs network access; subsequent launches use that copy.

TetraVox is a regular native application launched with the user's host permissions. TI-Toolbox
does not wrap it in an additional operating-system sandbox. Its renderer still uses Chromium's
WebGL2 backend; native opening does not introduce a different rendering engine.

The new TetraVox source supports an external-manager flag that disables its own updater, but the
pinned **0.4.0 release predates that protection**. Keep this managed copy at TI-Toolbox's pinned
version; do not use TetraVox's own updater to replace it. No automatic viewer-bundle updates run
inside the container.

**Browser-only sessions** cannot install or start a host application. They can prepare/download a
scene for manual opening in TetraVox. Its dataset paths must exist on the machine running TetraVox;
a scene made by a remote server does not transfer those datasets.

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
8. **Active session** — the user interacts with the UI; full viewing opens in a separate native TetraVox window
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
- **Native viewing:** the desktop launches its managed TetraVox executable with the prepared
  scene path. TetraVox runs with the host user's permissions and no additional TI-Toolbox sandbox.
- **Verified downloads:** the pinned viewer package is checked against its expected SHA256 before
  installation. Scene opening is limited to `.tetravox.json` files within the active project.

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
