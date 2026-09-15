---
layout: wiki
title: Desktop Application
permalink: /wiki/desktop-app/
---

The TI-Toolbox Desktop Application manages the scientific workflow in
`idossha/ti-toolbox:<version>` and renders the toolbox UI on your host. Optional FreeSurfer and
diffusion workflows start their own workers when needed. There is no X11 setup.

Full viewing opens **[TetraVox](https://github.com/idossha/tetravox)** in a separate native window.
TI-Toolbox picks one in a fixed order: the application you chose with **Locate TetraVox…**, then the
copy TI-Toolbox installed for you, then a compatible installation in a standard application location,
then a compatible `tetravox` on your `PATH`. Every candidate must identify itself as TetraVox 0.4.0
or later in the 0.x series; none is run to find that out. An installation you maintain keeps its own
profile and its own updater. Settings and the Viewer say which one is in use.

If nothing is found, **Settings → Viewer** offers the official **TetraVox 0.4.0** package. Its
SHA256 is checked before installation. Files live under TI-Toolbox's per-user application-data
folder in `runtimes/tetravox-<version>-<platform>-<architecture>`, with a separate profile. Managed
downloads cover macOS arm64/x64 and Linux x64; Windows can reuse an installed TetraVox, but managed
Windows setup awaits a verified portable release package.

**Check for updates** asks GitHub for the newest TetraVox release and offers to install it into a
new version directory, verifying the SHA512 that release publishes for this platform's package in
its update feed. A release without such a checksum installs nothing. Updates are never automatic,
always ask first, and remove the previous managed version once the new one is in place — so a new
TetraVox does not wait for a TI-Toolbox release.

Opening a scene while TetraVox is running asks before replacing its current view. Cancel leaves
the window untouched. TI-Toolbox cannot inspect unsaved viewer state, so it asks even if the open
window might be empty; save any edits in TetraVox first. **Launch TetraVox** without a scene only
opens or focuses the app. If only the managed copy is running, TI-Toolbox reuses it rather than
starting the system copy alongside it.

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

The loaders are bootstrappers for this same app: they download it (verifying SHA256 against the
release's `SHA256SUMS`), cache it under the user data directory and launch it, exactly as
double-clicking the installed app would. The browser is the fallback when that cannot be done,
and `--browser` asks for it explicitly. Developer browser mode remains convenient for fast iteration.

| Entry point | Interface and lifetime |
|---|---|
| `python3 loader.py` / `bash loader.sh` | The desktop app, downloaded on first run; closing it stops/removes its container. |
| Either loader with `--browser` (or `--no-open`) | Browser session; explicit `--stop` ends it. |
| Either loader with `--desktop` | The desktop app, with an error instead of a browser fallback. |
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
