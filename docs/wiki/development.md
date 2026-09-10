---
layout: wiki
title: Development & Testing
permalink: /wiki/development/
---

# Development & testing (v3)

Build and test TI-Toolbox from a source checkout here. For everyday use, follow the
[installation guide]({{ site.baseurl }}/installation/).
The checkout's `CONTRIBUTING.md` owns contributor environment setup and
`docs/dev/TESTING.md` owns the detailed test strategy and release gate.

## Source setup

Install git and Docker. Python loaders need Python 3.11+; desktop/frontend development
needs Node.js 22.12+. Keep the source revision and Docker image paired.

### Select a source revision

Choose the branch or tag paired with your image. The commands work with a release branch,
a release tag, or `main` after the corresponding change is merged:

```bash
TIT_SOURCE_REF=release/3.0.0
git clone --branch "$TIT_SOURCE_REF" git@github.com:idossha/TI-toolbox.git TI-Toolbox
cd TI-Toolbox
git rev-parse HEAD
```

Record the printed commit for reproducibility. Run the following commands inside this checkout;
its root `loader.py` uses the selected source without installing a different package revision.

### Load the matching image

Set the image reference supplied with your selected source revision. For the current pairing:

```bash
TIT_IMAGE=idossha/ti-toolbox:v3.0.0
docker pull "$TIT_IMAGE"
docker image inspect "$TIT_IMAGE" --format {% raw %}'{{json .RepoTags}}'{% endraw %}
```

For offline testing, load a supplied archive with
`docker load --input /path/to/supplied-image.tar`. Keep the checkout paired with its designated
image; similar version numbers do not guarantee matching code.

## Develop from source

Use the [source setup](#source-setup) to pair your checkout and image. In `desktop/`, run:

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

#### Developer CLI and checkout location

Developer mode needs a local TI-Toolbox checkout because it mounts your code over the image's
`/ti-toolbox` directory. **The launcher files do not have to live inside that checkout.**
Keep one developer launcher and `docker-compose.yml` together in any convenient folder:
[loader_dev.py](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/dev/loader/loader_dev.py) or
[loader_dev.sh](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/dev/loader/loader_dev.sh), plus
[the YAML](https://raw.githubusercontent.com/idossha/TI-Toolbox/release/3.0.0/docker-compose.yml).

From that folder, point to the checkout and choose your data project:

```bash
export TIT_DEV_REPO_DIR=/absolute/path/to/TI-Toolbox
python3 loader_dev.py --project /absolute/path/to/dataset
# or
bash loader_dev.sh --project /absolute/path/to/dataset
```

`TIT_DEV_REPO_DIR` selects **source code**; `--project` selects **project data**. They are separate
mounts. Without `--project`, the launcher asks for the data directory. When run inside the
repository without `TIT_DEV_REPO_DIR`, the dev wrappers use their containing checkout.
An explicit invalid checkout path fails instead of silently using another source tree.

Developer sessions enable Python reload and serve the checkout's built renderer. Build it once
with `npm ci` and `npm run build` in the checkout's `desktop/` directory, or use `--web` for Vite
hot reload. Running an already-built renderer needs no Node installation on the launcher host.
**Attach** retains the existing container's mounts; choose **Recreate** to apply a different checkout.

The Python dev loader also supports `--build` (build the image and exit) and `--web`
(run the selected checkout's `npm run dev:web`). Pass `--no-mount-repo` to test the image's own
code and interface. Direct CLI starts use the adjacent YAML; `TIT_COMPOSE_FILE` can explicitly
select a different YAML file. The `--web`/npm development flow uses the YAML inside the selected checkout.

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

## Automation and container configuration

The regular loaders accept `--existing attach|recreate` and `--container NAME` for an
explicit scripted choice. Without one, noninteractive launches refuse to reuse an existing
container. Use `--interactive` to prompt even when arguments are supplied. Attach retains
the selected container's image, project and mounts; Recreate uses the requested Compose
configuration and interrupts that container's jobs.

Each project gets a container named `ti-toolbox-<directory hash>-tit-1`, labelled
`tit.project` / `tit.host_project_dir`. The desktop and CLI derive the same identity;
`--status` and `--stop` locate the project through it. Use `--port` for a preferred host port;
the launcher selects the next free port when necessary. See `python3 loader.py --help`
for the complete option reference.

The regular CLI's optional `--desktop` mode requires `TIT_ELECTRON_EXECUTABLE` pointing to
an installed executable, or a checkout built with `npm ci` and `npm run build` in `desktop/`.
Missing Electron produces setup instructions rather than a browser fallback.

For a Docker-free local API and frontend, run `npm run dev:host -- --project /path/to/project`
from `desktop/` after the host setup in `CONTRIBUTING.md`. Scientific tools must be installed
on the host.

### Windows development

Run Electron development from a Windows checkout with Node.js 22.12+, git and native Windows
project paths. Run browser developer loaders inside WSL2 with Docker integration enabled;
use WSL paths there. Do not mix WSL paths into native Electron configuration.

## Shared-host Docker access

Docker access grants control of the host and exposes container session tokens. On a shared
machine, other Docker users can inspect a TI-Toolbox token and access its local HTTP session
and project data. Do not give mutually untrusted accounts access to the same Docker engine.

## Apptainer and clusters

`container/blueprint/apptainer.def` and `apptainer_run.sh` target an earlier combined
SimNIBS/FreeSurfer environment. They do not reproduce the current Docker image's FastSurfer,
HTTP server and embedded viewer stack. Migration and workload validation are required before
offering this route for v3; Electron's Docker controls cannot launch a SIF image. Use a
consistent source revision and confirm the cluster's container policy before adapting it.

## Choose checks that prove the change

| Check | What it covers |
|---|---|
| Desktop types, lint and unit tests | UI logic, types and code conventions |
| Host Python tests | Server, jobs, configuration and path logic with heavy scientific libraries mocked |
| Container numerical tests | Numerical behavior against real libraries |
| Hidden Electron tests | Actual UI interactions against controlled mock services |
| Real workflow and packaged acceptance | Scientific outputs and the distributed app/image pairing |

From the repository root, after installing the contributor Python environment:

```bash
.venv/bin/python -m pytest tests/ -q
python3 dev/route_import_guard.py
python3 dev/contracts_check.py
```

From `desktop/`:

```bash
npm run typecheck
npm run lint
npx vitest run
```

For real numerical checks, use an existing development/test container with the checkout
mounted at `/ti-toolbox` (replace `<container>` with its actual name):

```bash
docker exec -w /ti-toolbox <container> simnibs_python -m pytest tests/numerical -q
```

Host pytest success does not establish scientific correctness: it mocks SimNIBS and several
other libraries. Numerical test success also does not substitute for a completed end-to-end
simulation on representative data.

## Hidden UI tests and final build

Coordinate exclusive use of `/tmp/tit-e2e.lock` before running Playwright: tests share a mock
server and build output. From `desktop/`, run `TIT_E2E_OFFSCREEN=1 npm run e2e:quiet` under that
lock. The detailed testing guide in the checkout describes real-server credentials, scene
hooks and quiet-monitor limitations. An inconclusive visibility monitor is not a pass.

After tests, run `npm run build` from `desktop/` to restore the normal UI bundle. Release
acceptance additionally checks the actual packaged executable and matching scientific image;
a source build alone does not validate a release artifact.

## Legacy development

The [v2 development archive]({{ site.baseurl }}/wiki/v2-development/) retains the old Qt and
CircleCI instructions. They describe legacy v2 installations and do not apply to the v3 stack.
