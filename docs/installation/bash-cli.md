---
layout: installation
title: Command-line launcher
permalink: /installation/bash-cli/
---

`tit launch` runs TI-Toolbox **without the desktop application**. It starts the same container
the app starts and gives you the same interface — in a browser tab instead of a window.

Use it when the desktop app is not the right shape: a machine you reach over SSH, a shared lab
server, a container host, a scripted setup, or simply a preference for the terminal.

> Everything the interface does goes over HTTP to the server in the container, so browser mode
> is not a reduced version of the app. The only differences are the few things that need the
> operating system directly — see [What is different in a browser](#what-is-different-in-a-browser).

## Requirements

- **Docker Desktop** (macOS/Windows) or **Docker Engine** (Linux), running.
- **CPython 3.11 or newer**.

That is the whole list. The launcher uses the Python standard library and the `docker` CLI —
it does **not** need SimNIBS, numpy, or Node on your machine. Everything the toolbox actually
computes with lives inside the image.

## Setup

Complete the [installation procedure]({{ site.baseurl }}/installation/#install-from-source)
to select a source ref, set `TIT_IMAGE`, and make that image available locally. Run this
reference's commands from the repository root. `loader.py` and `loader.sh` use the source
in that checkout; they pass options to the same implementation as `tit launch`.

| Entry point | Use |
|---|---|
| `python3 loader.py` | Python 3.11+ and the Docker CLI are on your PATH. |
| `./loader.sh` | Find a suitable Python interpreter before forwarding the same options. |

Keep the loaders inside the selected checkout so they use that revision.

## Launch

```bash
python3 loader.py --project ~/datasets/000 --image "$TIT_IMAGE"
```

What it does, in order:

1. **Checks Docker** — installed, running, and reachable. Each failure prints its own remedy
   (including the `docker` group fix on Linux).
2. **Attaches** to this project's container if one is already running — the desktop app's, or
   an earlier `tit launch`'s. It is the same container either way.
3. **Pulls the image** if it is not already on the machine (when that image is published).
4. **Starts the container**, publishing the server on `127.0.0.1` only.
5. **Waits for `/api/health`** to answer, up to `--timeout` seconds (180 by default; a cold
   start under emulation on Apple Silicon is slow).
6. **Prints a URL and opens your browser.**

The launcher prints the chosen container and port, followed by a session URL. Open that
URL to authenticate; treat its token as a secret when sharing logs.

Opening that URL trades the token for an `HttpOnly` session cookie and redirects to the app,
so the token does not stay in your address bar or your browser history's query strings.

**The container keeps running after the command exits.** Close the tab, come back tomorrow,
run `tit launch` again — it attaches in a second. `--stop` is what ends it.

## Options

| Flag | Meaning |
|---|---|
| `--project DIR` | The BIDS project directory to open. Required (or set `TIT_PROJECT_DIR`). |
| `--port N` | First host port to try. Default 8765; the next free port is used if it is taken, and the launcher says so. |
| `--image IMAGE:TAG` | Run a specific image instead of the default selected by this checkout. |
| `--no-open` | Print the URL instead of opening a browser. What you want over SSH. |
| `--timeout SECONDS` | How long to wait for the server. Default 180. |
| `--status` | Name, state, health, image and URL of this project's container. |
| `--logs` / `--logs --follow` | The container's log, once or streaming. |
| `--stop` | Stop and remove this project's container. |

```bash
python3 loader.py --project ~/datasets/000 --status
python3 loader.py --project ~/datasets/000 --logs --follow
python3 loader.py --project ~/datasets/000 --stop
```

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
checkout and image, then run `npm run dev` in `desktop/`. It starts the container, Vite,
and Electron. For Python edits, set `TIT_DEV_MOUNT_REPO=1`; for the baked Python package,
set it to `0`.

`.env.dev` has four settings and one of them is required:

| Variable | Default | Meaning |
|---|---|---|
| `TIT_DEV_PROJECT_DIR` | *(none — you must set it)* | The project directory to open. |
| `TIT_DEV_IMAGE_TAG` | `dev` | Which `idossha/ti-toolbox:<tag>` to run. |
| `TIT_DEV_PORT` | `8765` | Host port. A second checkout needs a second port. |
| `TIT_DEV_MOUNT_REPO` | `1` | Mount the checkout at `/ti-toolbox`, so your Python edits are what the container runs, and restart the server on change. Set `0` to test the image's own `tit`. |

Any of them can be overridden for a single run: `TIT_DEV_PORT=8766 npm run dev`.

Other commands:

```bash
npm run dev:web    # the same, without the Electron window — open http://127.0.0.1:5173/
npm run dev:down   # stop and remove this project's dev container
```

Ctrl-C stops the renderer and the app but **leaves the container running**, so the next
`npm run dev` attaches in a second or two.

#### Without Node

`dev/loader/loader_dev.py` and `dev/loader/loader_dev.sh` are the developer's equivalents of
the two loaders at the root, and they need no `npm install`:

```bash
python3 dev/loader/loader_dev.py --project ~/datasets/000 --image "$TIT_IMAGE"
python3 dev/loader/loader_dev.py --build                    # build the image, then exit
python3 dev/loader/loader_dev.py --web                      # hand over to `npm run dev:web`
```

They take every option the user loaders take, and add exactly one thing to what the container
gets: the three dev overrides collected in `dev/loader/docker-compose.dev.yml` — your checkout
bind-mounted at `/ti-toolbox`, the server run with `--reload`, and your locally built renderer
served instead of the image's when `desktop/out/renderer/index.html` exists. Otherwise the
image's baked renderer is used. That file is *overrides only*; the service itself is defined
once, in the root `docker-compose.yml`, so the two can never describe different containers.

`--web` does not reimplement the dev loop — it runs `npm run dev:web` for you, so there is one
implementation of container + Vite + Electron and it is the one `npm run dev` uses.

### Build a development image

The build recipe produces a local Docker image from the selected checkout:

```bash
container/blueprint/build.sh --tag idossha/ti-toolbox:dev
```

Run this command from the repository root. The recipe requires a compatible Tetravox embed;
when building with a supplied asset, pass `--tetravox-tgz` and `--tetravox-sha256` as described
in `container/blueprint/build.sh --help`. Its default resolver uses compatible GitHub release
assets. The [release guide](https://github.com/idossha/TI-toolbox/blob/release/3.0.0/docs/dev/RELEASE.md)
explains the embed and image-build requirements.

Expect **30–60+ minutes** on native x86_64 hardware and considerably longer under amd64
emulation on Apple Silicon: the recipe installs SimNIBS 4.6 from scratch, builds the UI in its
own Node stage, and vendors FastSurfer with its checkpoints. It is a once-per-major-change
cost, not a per-run one.

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
- **The UI bundle and the viewer** — pass `--static-dir` at a renderer build you produced
  yourself (`desktop/out/renderer`), or the server serves a "no UI bundle" page.
- **QSIPrep/QSIRecon** for diffusion, which are spawned as sibling containers and therefore
  need Docker anyway.

Use it for server development and for hosts where Docker is not available at all; for
everything else the container is the supported path.

## Troubleshooting

**The running container uses a different image.** The launcher compares the requested
image reference with the running project's configured image reference and refuses a mismatch.
It leaves the container and its jobs unchanged. Wait for the jobs to finish, then use `--stop`
for that project and launch with the intended image. This avoids silently reusing an older
cohort or killing active work to replace it.

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
