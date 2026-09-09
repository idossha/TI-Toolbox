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

## Install

The browser launcher described here is **unreleased**. Do not assume `pip install tit`
or a public release download contains it. Obtain the tested source revision and image from
the [internal testing handoff]({{ site.baseurl }}/installation/#internal-colleague-testing).
From that checkout, with Python 3.11+, replace the placeholder and run:

```bash
python3 loader.py --project ~/datasets/000 --image "<verified-image-reference>"
```

The `tit launch` examples below describe the same interface when the matching source package
has been installed in your environment. Keep the verified `--image` override on subsequent
launch commands; the package version's default tag is not evidence of a published image.

Two entry points sit at the root of the checkout, and they take the same options:

| | |
|---|---|
| `loader.py` | For a host where you already know which Python to use. Standard library only. |
| `loader.sh` | For one where finding it is the hard part: it locates a CPython ≥ 3.11 — one you installed, the checkout it is sitting in, or a virtualenv it creates in `~/.cache/ti-toolbox/venv` — and hands your arguments on. |

Both also support standalone downloads: `python3 loader.py` when Python 3.11+ is available,
or `./loader.sh` for Python discovery. Outside a checkout, each refreshes the `main` source
archive into the shared isolated cache on startup; starting needs network access. The management
options `--stop`, `--status` and `--logs` can use a working cached launcher offline, without a
source refresh. Inside a checkout, both use the local source. Use the tested image reference
from the [internal handoff]({{ site.baseurl }}/installation/#internal-colleague-testing).

Both are bootstraps, not second launchers: every option is the option `tit launch` defines,
and the work is done by the same code. There is one implementation of the container's run
specification — the single `docker-compose.yml` at the root of the repository, which the
desktop app, `tit launch` and both loaders all read — so the container you get here is exactly
the container the desktop app creates.

## Launch

```bash
tit launch --project ~/datasets/000
```

What it does, in order:

1. **Checks Docker** — installed, running, and reachable. Each failure prints its own remedy
   (including the `docker` group fix on Linux).
2. **Attaches** to this project's container if one is already running — the desktop app's, or
   an earlier `tit launch`'s. It is the same container either way.
3. **Pulls the image** if it is not already on the machine (final candidate size and download time are not yet measured).
4. **Starts the container**, publishing the server on `127.0.0.1` only.
5. **Waits for `/api/health`** to answer, up to `--timeout` seconds (180 by default; a cold
   start under emulation on Apple Silicon is slow).
6. **Prints a URL and opens your browser.**

```text
image idossha/ti-toolbox:3.0.0 is already present
starting ti-toolbox-e37166cb-tit-1 on port 8765…
waiting for the server to answer…

TI-Toolbox is running at http://127.0.0.1:8765
Open this URL to sign in (it is single-use per session):
  http://127.0.0.1:8765/auth/session?token=8k-cp8kIpJGbLaGRGAWSQFRuUgMNNtVuFWPTZU_0IPg

The container keeps running after this command exits.
```

Opening that URL trades the token for an `HttpOnly` session cookie and redirects to the app,
so the token does not stay in your address bar or your browser history's query strings.

**The container keeps running after the command exits.** Close the tab, come back tomorrow,
run `tit launch` again — it attaches in a second. `--stop` is what ends it.

## Options

| Flag | Meaning |
|---|---|
| `--project DIR` | The BIDS project directory to open. Required (or set `TIT_PROJECT_DIR`). |
| `--port N` | First host port to try. Default 8765; the next free port is used if it is taken, and the launcher says so. |
| `--image IMAGE:TAG` | Run a specific image instead of the one matching this package's version. |
| `--no-open` | Print the URL instead of opening a browser. What you want over SSH. |
| `--timeout SECONDS` | How long to wait for the server. Default 180. |
| `--status` | Name, state, health, image and URL of this project's container. |
| `--logs` / `--logs --follow` | The container's log, once or streaming. |
| `--stop` | Stop and remove this project's container. |

```bash
tit launch --project ~/datasets/000 --status
tit launch --project ~/datasets/000 --logs --follow
tit launch --project ~/datasets/000 --stop
```

### Over SSH

The server binds to `127.0.0.1` inside the remote machine on purpose. Forward the port rather
than exposing it:

```bash
# on the remote host
tit launch --project ~/datasets/000 --no-open

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

## Run the latest unreleased version

To try code that has not been released yet, run the app from a checkout. `npm run dev` brings
up the **whole system** — container, renderer dev server, and the app window already connected
to it. You never see or type a token.

**Requirements:** Docker, **Node 22.12+**, and git.

```bash
git clone https://github.com/idossha/TI-Toolbox.git
cd TI-Toolbox/desktop
cp .env.dev.example .env.dev     # then edit TIT_DEV_PROJECT_DIR
npm ci
npm run dev
```

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
python dev/loader/loader_dev.py --project ~/datasets/000   # container only, no Node
python dev/loader/loader_dev.py --build                    # build the image, then exit
python dev/loader/loader_dev.py --web                      # hand over to `npm run dev:web`
```

They take every option the user loaders take, and add exactly one thing to what the container
gets: the three dev overrides collected in `dev/loader/docker-compose.dev.yml` — your checkout
bind-mounted at `/ti-toolbox`, the server run with `--reload`, and your locally built renderer
served instead of the image's. That file is *overrides only*; the service itself is defined
once, in the root `docker-compose.yml`, so the two can never describe different containers.

`--web` does not reimplement the dev loop — it runs `npm run dev:web` for you, so there is one
implementation of container + Vite + Electron and it is the one `npm run dev` uses.

### First run: the image

`npm run dev` runs `idossha/ti-toolbox:dev`, which is a **locally built** tag — it is not
published on Docker Hub. On a machine that has never built it, the launcher says so and gives
you the command:

```bash
container/blueprint/build.sh --tag idossha/ti-toolbox:dev
```

Expect **30–60+ minutes** on native x86_64 hardware and considerably longer under amd64
emulation on Apple Silicon: the recipe installs SimNIBS 4.6 from scratch, builds the UI in its
own Node stage, and vendors FastSurfer with its checkpoints. It is a once-per-major-change
cost, not a per-run one.

For internal testing, use only the maintainer-verified source and image pairing in the
[handoff]({{ site.baseurl }}/installation/#internal-colleague-testing). The `dev` tag is a
local development convention; `3.0.0` is not a verified public image download.

## Advanced: native, without Docker

If you already have SimNIBS 4.6 installed on the host and `tit` installed into *its*
interpreter, you can run the server directly:

```bash
simnibs_python -m tit.server --project ~/datasets/000 --port 8765
```

It prints a `TIT_SERVER_TOKEN=` line; open `http://127.0.0.1:8765/auth/session?token=<that>`.

This is genuinely advanced and deliberately unsupported as a first install. What you lose,
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

**The running container uses a different image.** The preview launcher compares the requested
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
[above](#first-run-the-image)).

**"The container started but its server never answered."** Usually a cold start under emulation
that outran `--timeout`. Raise it (`--timeout 300`) and look at `tit launch --logs`.

**Port already in use.** The launcher moves to the next free port on its own and prints which
one it used; pass `--port` to steer it.

More on the [Troubleshooting]({{ site.baseurl }}/installation/troubleshooting/) page.
