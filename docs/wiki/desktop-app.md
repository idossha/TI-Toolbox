---
layout: wiki
title: Desktop Application
permalink: /wiki/desktop-app/
---

The TI-Toolbox Desktop Application manages the scientific workflow in
`idossha/ti-toolbox:<version>` and renders the toolbox UI on your host. Optional FreeSurfer and
diffusion workflows start their own workers when needed. There is no X11 setup.

Full viewing opens **[TetraVox](https://github.com/idossha/tetravox)** in a separate native window.
TI-Toolbox installs its own copy of TetraVox and launches only that copy. A TetraVox you installed
yourself, one on your `PATH`, or one you might point at is never used, so the viewer that opens a
scene is always the one TI-Toolbox verified.

**Setup is automatic.** On the first desktop launch TI-Toolbox downloads the newest official
TetraVox package for your platform (macOS arm64/x64, Linux x64, Windows x64), checks it against the
SHA-256 digest GitHub publishes for that file, unpacks it and keeps it under TI-Toolbox's per-user
application-data folder in `runtimes/tetravox-<platform>-<architecture>`. Nothing is installed if
the checksum does not match. **Settings → Viewer** shows the installed version and location, offers
**Retry setup** if the download failed, and **Launch TetraVox** once it is there.

The same card shows the newest TetraVox release next to the installed one; **Update to X** replaces
that copy with it the same verified way. Close TI-Toolbox's TetraVox first; the update is refused
while it is open (a TetraVox you installed yourself does not count). TetraVox can also tell you
itself: when a newer release exists, its own **Software Update** window appears. Choosing **Update
to X** there closes TetraVox, and TI-Toolbox downloads and verifies the release and reopens TetraVox
with the last scene it opened. **Skip This Version** remembers your answer for that version. Either
way TI-Toolbox does the install, so its copy is never changed behind its back. TetraVox releases
before this handshake keep their own updater switched off; use the Settings card for them.

Opening a scene while TetraVox is running asks before replacing its current view. Cancel leaves
the window untouched. TI-Toolbox cannot inspect unsaved viewer state, so it asks even if the open
window might be empty; save any edits in TetraVox first. **Launch TetraVox** without a scene only
opens or focuses the app.

TetraVox is a regular native application launched with the user's host permissions. TI-Toolbox
does not wrap it in an additional operating-system sandbox; on Linux it runs with Chromium's
setuid sandbox disabled, since a user-level install cannot provide one. Its renderer still uses
Chromium's WebGL2 backend; native opening does not introduce a different rendering engine.

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

## Help in the application

<img src="{{ site.baseurl }}/assets/imgs/v3/help.png" alt="Help page with documentation, citation and keyboard shortcuts" style="width: 100%; max-width: 1000px;">
<em>Help links to the documentation and citation and lists the keyboard shortcuts available in the application.</em>

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
