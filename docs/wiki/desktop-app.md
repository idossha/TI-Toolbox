---
layout: wiki
title: Desktop Application
permalink: /wiki/desktop-app/
---

The TI-Toolbox Desktop Application manages the scientific workflow in
`idossha/ti-toolbox:<version>` and renders the toolbox UI on your host. Optional FreeSurfer and
diffusion workflows start their own workers when needed. There is no X11 setup.

Full viewing opens **[TetraVox](https://github.com/idossha/tetravox)** in a separate native window;
the user-facing setup, scenes and updates are on the [Viewer]({{ site.baseurl }}/wiki/visualizers/)
page. What matters for development:

- **Only TI-Toolbox's own copy runs.** On first launch the app downloads the latest TetraVox release
  for the platform (macOS arm64/x64, Linux x64, Windows x64), checks it against the SHA-256 digest
  GitHub publishes for that asset, and unpacks it under the app-data folder in
  `runtimes/tetravox-<platform>-<architecture>`. A TetraVox on the `PATH` or installed by the user
  is never launched. TetraVox's own **Software Update** window hands the install back to
  TI-Toolbox, so its copy is never changed behind its back.
- **Replacing a view asks first.** Opening a scene while TetraVox is running asks before
  replacing its current view; TI-Toolbox cannot see unsaved viewer state.
- **No extra sandbox.** TetraVox runs with the user's permissions. On Linux it is launched with
  `--no-sandbox`, which turns off Chromium's whole sandbox (a user-level install cannot provide
  the setuid helper), not only the setuid part.
- **Browser-only sessions** cannot install or start a host application; they offer the prepared
  scene for download instead. Its dataset paths must exist on the machine running TetraVox.

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

The loaders are bootstrappers for this same app: they download it (verifying SHA256 against the
release's `SHA256SUMS`), cache it under the user data directory and launch it, exactly as
double-clicking the installed app would. The browser is the fallback when that cannot be done,
and `--browser` asks for it explicitly. Developer browser mode remains convenient for fast iteration.

| Entry point | Interface and lifetime |
|---|---|
| `python3 loader.py` / `bash loader.sh` | The desktop app, downloaded on first run; closing it stops/removes its container. |
| Either loader with `--browser` (or `--no-open`) | Browser session; explicit `--stop` ends it. |
| Either loader with `--desktop` | The desktop app, with an error instead of a browser fallback. |
| Either loader with `--dev [DIR]` | The desktop app, serving a mounted checkout's code instead of the image's. |
| `npm run dev` in `desktop/` | Builds and opens welcome Overview; select a project in Electron. Closing stops its container. |
| `npm run dev:web` | Browser with Vite; container remains until `npm run dev:down`. |

All Docker starts use the shared root Compose specification (packaged apps carry their copy).
Every route requires an explicit choice before reusing a running session. Attach may select a
session from another project; the displayed project remains that session's actual project.
Replacement affects only the selected container. See the
[launcher reference]({{ site.baseurl }}/installation/bash-cli/) for flags and prerequisites.

In a browser there is no Electron bridge (`window.tit`), so reveal-in-file-manager, native
notifications, the **Settings ▸ Server ▸ Docker** card and the project picker are absent — each with a
message or a fallback rather than a failure. See
[the command-line launcher]({{ site.baseurl }}/installation/bash-cli/#what-is-different-in-a-browser).

## Job Model

Every long-running operation — pre-processing, a simulation, flex/ex/mex-search, the
analyzer, group statistics — is a **job**: the UI POSTs a JSON config to `tit.server`, which
runs it as a tracked background process inside the container (a job ID
distinguishes concurrent runs; separately launched job containers carry a `tit.job_id` label) and streams status and logs back to the UI over the `/ws/jobs`
WebSocket on the same server. This is unchanged in shape from v2's
subprocess-per-tab pattern (`simnibs_python -m tit.<pipeline> config.json`) — what changed is
*where* it runs: inside the one always-running container, driven over HTTP, rather than a
process the desktop app spawned and monitored itself.

## Building the Application

The desktop app is built with `electron-vite`/`electron-builder`. `npm run build` only runs
`electron-vite build` (into `desktop/out/`); the installers come from `npm run package`, which
builds and then runs `electron-builder` with `electron-builder.yml`:

**macOS:** `.dmg` installer
**Windows:** `.exe` installer (NSIS)
**Linux:** `.AppImage`, `.deb` package

```bash
cd desktop
npm install
npm run package
```

The packaged app checks GitHub once per start for a newer TI-Toolbox release and shows it under
**Settings ▸ Updates** (`TIT_UPDATE_CHECK=0` turns the check off). How the system is built and
verified: [ARCHITECTURE](https://github.com/idossha/TI-toolbox/blob/main/docs/dev/ARCHITECTURE.md),
[TESTING](https://github.com/idossha/TI-toolbox/blob/main/docs/dev/TESTING.md) and
[RELEASING](https://github.com/idossha/TI-toolbox/blob/main/docs/dev/RELEASING.md).

## Development

```bash
cd desktop
npm install
npm run dev
```

A checkout (`npm run dev`, or `bash loader.sh --dev --desktop`) runs the Electron.app from
`desktop/node_modules`, which npm installs without a valid code signature, and macOS silently
refuses its notifications. `npm install` re-signs it ad hoc; for an older checkout, quit the app,
run `npm --prefix desktop run sign:dev-electron` once, then allow **Electron** in
**System Settings ▸ Notifications** when asked.

## Dependencies

**Runtime:**
- Docker Desktop or Docker Engine (required)

**Development:**
- Node.js ≥22.12 (electron-vite/electron-builder toolchain)

## Security

- **Docker Access:** the main process holds a direct, unmediated handle to the host's Docker
  socket, and the container mounts the host's `/var/run/docker.sock` (for the QSIPrep/QSIRecon
  sibling containers), so whoever holds the server token effectively has root on the host through
  Docker. The server port is bound to `127.0.0.1` only. Initial `stack.start` is restricted to
  the local welcome page. The connected main window may stop its own session; switching to another
  host directory requires native confirmation of the exact destination before the new mount is
  created.
- **No X11 permissions:** there is nothing to grant or revert on launch/exit — removed
  entirely along with X11 itself.
- **Native viewing:** the desktop launches its managed TetraVox executable with the prepared
  scene path. TetraVox runs with the host user's permissions and no additional TI-Toolbox sandbox.
  It uses its own profile and TetraVox home under TI-Toolbox's app data, so it shares no settings,
  rc file or extensions with a TetraVox you installed yourself.
- **Verified downloads:** nothing is pinned — the app installs the latest compatible TetraVox
  release and checks it against the SHA-256 digest GitHub publishes for that asset. That catches a
  corrupted download, not a compromised release. Scene opening is limited to `.tetravox.json`
  files within the active project.

## Performance

- **Startup Time:** depends on image availability and host performance. Loading an image
  for the first time takes longer than starting a cached one.
- **Memory Usage:** small for the app itself; the container needs whatever the workload needs —
  see [Dependencies]({{ site.baseurl }}/installation/dependencies/) for host RAM and Docker memory.
- **Disk Space:** allow space for the image, working data and project outputs; see the
  [installation guide]({{ site.baseurl }}/installation/) for the selected image.

## Help in the application

The Help page embeds the documentation and has tabs for example data, keyboard shortcuts,
citation and contact.

## Troubleshooting

**Docker not found:**
Ensure Docker Desktop is installed and running. On Windows the app connects over Docker Desktop's
named pipe and does not need WSL Integration or `docker` on PATH; if Docker Desktop is up and the
app still reports it is not running, check the pipe it tried in
`%APPDATA%\ti-toolbox-desktop\logs\main.log` (`Docker endpoint …`).

**Permission errors:**
Check that your user has access to the Docker daemon (usually requires membership in the
`docker` group on Linux).

**Podman:**
Not supported — the app detects and refuses a Podman-flavored `/version` response by name.

## See Also

- [Installation Guide]({{ site.baseurl }}/installation/)
- [Viewer]({{ site.baseurl }}/wiki/visualizers/)
- [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/)
