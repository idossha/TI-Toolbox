---
layout: installation
title: Command-line launcher
permalink: /installation/bash-cli/
---

Regular `python3 loader.py` and `bash loader.sh` open the browser interface.
Use `--desktop` to open Electron instead.
Electron owns the selected Docker session. Closing the app stops/removes its container and
exits Electron. **Switch project** in Overview lets you enter or browse to a different directory,
then confirms the change before stopping the current session and opening the new project.
Use `--no-open` for an SSH/headless session.
Developer loaders continue to use browser mode by default.

## Existing containers

Every Docker launch checks for running TI-Toolbox containers, including other projects.
Choose a numbered container if several exist, then choose **Recreate** (Enter) or **Attach**.
TI-Toolbox image references (repository and version) are shown above a separate Available actions section. Ctrl-C cancels without changing containers.
Attach uses that container's existing project, image and source mounts. Recreate stops/removes
only the selected container (interrupting its jobs), then creates the requested project session
from the Compose YAML. Cancel leaves containers unchanged. A legacy v2 container may be listed
but cannot attach to the v3 HTTP interface; explicitly replace it if you intend to migrate.

For automation, supply `--existing attach|recreate` and `--container NAME` when selection is
ambiguous. These flags are explicit authorization for the selected action; a noninteractive
browser/dev launch without a decision refuses to reuse a running container.

## Requirements

- **Docker Desktop** (macOS/Windows) or **Docker Engine** (Linux), running.
- Bash loader: **Docker Compose and curl**, no host Python.
- Python loader: **CPython 3.11 or newer**.

Neither launcher needs host SimNIBS or numpy. The optional `--desktop` mode needs an installed Electron
executable (`TIT_ELECTRON_EXECUTABLE`) or the checkout's built desktop app (`npm ci` and
`npm run build` in `desktop/`). Explicit browser/developer loaders do not need Node.
The scientific tools run inside the image.

## Setup

Complete the [installation procedure]({{ site.baseurl }}/installation/#install-from-source)
to select a source ref, set `TIT_IMAGE`, and make that image available locally. Run this
reference's commands from the repository root. `loader.py` and `loader.sh` use the source
in that checkout. Python uses `tit launch`; Bash uses Docker Compose directly. Both share the
root compose specification and container identity, so either can manage the same project.

| Entry point | Use |
|---|---|
| `python3 loader.py` | Python 3.11+ and the Docker CLI are on your PATH. |
| `./loader.sh` | Start Docker directly, without Python. |

Keep the loaders inside the selected checkout so they use that revision.

## Launch

Run either loader without arguments in a terminal to choose a project:

```bash
python3 loader.py
# or
bash loader.sh
```

The prompt asks only for your project directory. The last selected directory is remembered
in your user configuration and shared by the regular and development loaders; press Enter
to accept the displayed path. Advanced settings remain command-line options. To start directly,
pass arguments instead:

```bash
python3 loader.py --project ~/datasets/000 --image "$TIT_IMAGE"
```

With `--desktop`, launch hands control to Electron before any container is created. If Electron is
unavailable it fails with setup instructions; it does not silently switch to browser mode.

In default browser mode, the loader checks Docker, asks how to handle existing sessions,
starts the YAML-defined container when needed, waits for health, then opens its authenticated URL.
The browser container stays running when its tab closes. Use `--stop` to end that project session.
For Electron, closing the app stops/removes its session and exits;
named volumes and project files remain.

## Options

| Flag | Meaning |
|---|---|
| `--project DIR` | The BIDS project directory to open. Supply it with arguments, set `TIT_PROJECT_DIR`, or choose it at the prompt. |
| `--interactive` | Prompt for the project even when arguments are supplied; use the supplied or remembered project as the default. |
| `--port N` | First host port to try. Default 8765; the next free port is used if it is taken, and the launcher says so. |
| `--image IMAGE:TAG` | Run a specific image instead of the default selected by this checkout. |
| `--browser` | Open the browser interface (the default). |
| `--desktop` | Open Electron; closing the app or quitting returns to the terminal. |
| `--no-open` | Start/select a headless session and print its URL (for SSH). |
| `--existing attach\|recreate` | Explicitly attach to or replace a running session. |
| `--container NAME` | Select a running container by name or ID. |
| `--timeout SECONDS` | How long to wait for the server. Default 180. |
| `--status` | Name, state, health, image and URL of this project's container. |
| `--logs` / `--logs --follow` | The container's log, once or streaming. |
| `--stop` | Stop and remove this project's container. |

```bash
python3 loader.py --project ~/datasets/000 --status
python3 loader.py --project ~/datasets/000 --logs --follow
python3 loader.py --project ~/datasets/000 --stop
```

Arguments keep scripted invocations noninteractive unless you add `--interactive`:

```bash
python3 loader.py --interactive --project ~/datasets/000 --image "$TIT_IMAGE"
```

The selected running session is never reused implicitly. Attach deliberately retains its image
and configuration; Recreate uses the requested settings. Use `--status` to inspect a project session
when you need more detail than the prompt's image reference.

The project prompt needs an interactive terminal. A no-argument invocation without one exits with
instructions to pass explicit flags, rather than waiting for input in a script or job.

### Over SSH

The server binds to `127.0.0.1` inside the remote machine on purpose. Forward the port rather
than exposing it:

```bash
# on the remote host
python3 loader.py --project ~/datasets/000 --image "$TIT_IMAGE" --no-open

# on your laptop
ssh -N -L 8765:127.0.0.1:8765 you@remote-host
```

Then open the printed `/auth/session?token=…` URL locally, substituting `127.0.0.1:8765`.

### One project per container

Each project directory gets its own container, named `ti-toolbox-<hash of the directory>-tit-1`
and labelled `tit.project` / `tit.host_project_dir`. That is how `--status` and `--stop` find
the right one, and it is why the desktop app and `tit launch` can hand a session back and forth:
both derive the same name from the same directory. Two projects at once means two containers,
so give the second one a different `--port`.

## What is different in a browser

Everything that talks to the server is identical — jobs, the terminal, notebooks, the pipeline
canvas, results, and the 3D/volume viewer (which is served by the container at `/tetravox/`,
not by Electron). What needs the operating system directly is not there:

| | In a browser |
|---|---|
| **Reveal a file in your file manager** | Not available; the interface says so when you use it. |
| **Open a result in an external application** | Opens in a new browser tab instead. |
| **Save a file** (e.g. exporting a notebook) | A normal browser download. |
| **Native desktop notifications** for finished jobs | In-app notifications only. |
| **Docker controls in Settings** | Not shown — the container belongs to whoever ran `tit launch`. Use `--status` / `--stop`. |
| **Choosing a project folder from the interface** | Not shown — `--project` chose it. |

There is nothing that fails or throws; these are absences with a message or a fallback, and
there is an automated test that loads every main page with no Electron bridge present and
asserts exactly that (`desktop/tests/e2e/browser-mode.spec.ts`).

<a id="run-the-latest-unreleased-version"></a>

## Develop from source

Use the [source setup]({{ site.baseurl }}/installation/#install-from-source) to pair your
checkout and image. In `desktop/`, run:

```bash
npm ci
npm run dev
```

This builds and opens the Electron welcome Overview, with the full sidebar visible and
project tools disabled until you open a project. Type a project path or use **Browse**, then
open it. No `.env.dev` file or running container is needed to see the welcome screen; Docker
is needed when opening the project. Use **Switch project** in Overview to choose another
directory. The current project is retained if you cancel or the destination fails validation;
a confirmed switch stops its container and jobs, then loads the new project's data.

Rerun `npm run dev` after UI changes. It tests the desktop experience without packaging an
installer. `npm run dev:launcher` remains an alias; no separate launcher command is needed.
New desktop development sessions mount this checkout and enable server reload. Attach retains
the existing container's configuration.

Optional defaults can go in `desktop/.env.dev` (copy `.env.dev.example`) or your shell:

| Variable | Default | Meaning |
|---|---|---|
| `TIT_DEV_PROJECT_DIR` | Last project in desktop; required for web mode unless supplied with `--project` | Prefills the desktop project field; selects the browser development project. |
| `TIT_DEV_IMAGE_TAG` | Root Compose image tag | Which `idossha/ti-toolbox:<tag>` to run. |
| `TIT_DEV_PORT` | `8765` | Preferred host port. |
| `TIT_DEV_MOUNT_REPO` | `1` | **Web mode only:** mount the checkout and reload Python changes. Set `0` to test the image's baked Python package. Desktop development always mounts the checkout. |

For live renderer reload in a browser:

```bash
npm run dev:web -- --project /path/to/project  # open http://127.0.0.1:5173/
npm run dev:down -- --project /path/to/project # stop and remove that project's dev container
```

Closing Electron stops/removes its adopted container and exits the app. Browser-only
`dev:web` retains the container after the tab closes or Ctrl-C stops Vite; use `dev:down` to
stop it. The next browser launch asks Recreate or Attach again.

#### Without Node

`dev/loader/loader_dev.py` and `dev/loader/loader_dev.sh` are the developer's equivalents of
the two loaders at the root, and they need no `npm install`. Run either without arguments
for the same project prompt:

```bash
python3 dev/loader/loader_dev.py
# or
bash dev/loader/loader_dev.sh
```

Or pass the settings directly:

```bash
python3 dev/loader/loader_dev.py --project ~/datasets/000 --image "$TIT_IMAGE"
python3 dev/loader/loader_dev.py --build                    # build the image, then exit
python3 dev/loader/loader_dev.py --web                      # hand over to `npm run dev:web`
```

They take every option the user loaders take, including `--interactive`. By default they apply
the three dev overrides collected in `dev/loader/docker-compose.dev.yml` — your checkout
bind-mounted at `/ti-toolbox`, the server run with `--reload`, and your locally built renderer
served instead of the image's. Build `desktop/out/renderer` first or use Vite; a missing
local bundle does not fall back to baked code. That file is *overrides only*; the service itself is defined
once, in the root `docker-compose.yml`, so the two can never describe different containers.
Pass `--no-mount-repo` to test the image's baked Python package and UI instead.

`--web` does not reimplement the dev loop — it runs `npm run dev:web` for you, so there is one
implementation of the browser development server and its container setup.

### Build a development image

The build recipe produces a local Docker image from the selected checkout:

```bash
container/blueprint/build.sh --tag idossha/ti-toolbox:dev
```

Run this command from the repository root. The recipe requires a compatible Tetravox embed;
when building with a supplied asset, pass `--tetravox-tgz` and `--tetravox-sha256` as described
in `container/blueprint/build.sh --help`. Its default resolver uses compatible GitHub release
assets. The [release guide](https://github.com/idossha/TI-toolbox/blob/release/3.0.0/docs/dev/RELEASING.md)
explains the embed and image-build requirements.

Image builds are substantial and take longer under amd64 emulation on Apple Silicon. The
recipe installs SimNIBS 4.6, builds the UI in its own Node stage, and vendors FastSurfer with
its checkpoints. Build once for the source revision you intend to test, then reuse that image.

## Advanced: native, without Docker

If you already have SimNIBS 4.6 installed on the host and `tit` installed into *its*
interpreter, you can run the server directly:

```bash
simnibs_python -m tit.server --project ~/datasets/000 --port 8765
```

It prints a `TIT_SERVER_TOKEN=` line; open `http://127.0.0.1:8765/auth/session?token=<that>`.

Use this for server development, not a first installation. What you lose,
because it comes from the image rather than from `tit`:

- **FastSurfer** segmentation — not installed by SimNIBS, and the pre-processing pipeline will
  say so rather than run it.
- **Blender / `bpy`** rendering for the montage visualiser.
- **The UI bundle and the viewer** — pass `--static-dir desktop/out/renderer` for a renderer build you produced
  yourself, or the server serves a "no UI bundle" page.
- **QSIPrep/QSIRecon** for diffusion, which are spawned as sibling containers and therefore
  need Docker anyway.

Use it for server development and for hosts where Docker is not available at all; for
everything else the container is the supported path.

## Troubleshooting

**The running container uses a different image or project.** Attach deliberately uses that
existing session unchanged. Choose Recreate to stop/remove the selected session and start the
requested YAML configuration. Other running containers are not removed. Enter chooses Recreate;
Ctrl-C cancels without changing containers.

**"Docker was not found on this machine."** Install Docker Desktop or Docker Engine; the
launcher looks for the `docker` executable on your `PATH`.

**"Docker is installed but not running."** Start Docker Desktop, or `sudo systemctl start docker`.

**"Permission denied talking to the Docker socket."** On Linux, `sudo usermod -aG docker $USER`,
then log out and back in. On macOS, restart Docker Desktop.

**"The TI-Toolbox image could not be downloaded."** Either you are offline, or you asked for a
tag that is not published. Check `docker images idossha/ti-toolbox` for what you already have
and pass it with `--image`, or build one (see
[Build a development image](#build-a-development-image)).

**"The container started but its server never answered."** Usually a cold start under emulation
that outran `--timeout`. Raise it (`--timeout 300`) and look at `python3 loader.py --project /path/to/project --logs`.

**Port already in use.** The launcher moves to the next free port on its own and prints which
one it used; pass `--port` to steer it.

More on the [Troubleshooting]({{ site.baseurl }}/installation/troubleshooting/) page.

For a Docker-free local API and frontend, use `npm run dev:host -- --project /path/to/project` from
`desktop/` after the [host setup](https://github.com/idossha/TI-Toolbox/blob/release/3.0.0/CONTRIBUTING.md#development-environment).
Scientific tools must then be available on the host.
