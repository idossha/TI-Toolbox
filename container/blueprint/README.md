# Container blueprints

Build the v2 images from within the `blueprint` directory; build `Dockerfile.ti-toolbox` via
`./build.sh` (see below — it chooses the context: the repository root, or an empty directory
for a `--ref` clone).

## v3: `idossha/ti-toolbox:<ver>`

One image (D1, `dev/notes/v3-docker-streamline-plan.md`): SimNIBS 4.6 + `tit` + `tit.server`
+ fastapi/uvicorn/pyyaml/psutil baked in (no pip install at container start) + the built
desktop UI at `/opt/ti-toolbox/ui` + the **Tetravox Embed** at `/opt/tetravox/embed` +
FastSurfer `--seg_only` at `/opt/fastsurfer` with checkpoints pre-downloaded. No FreeSurfer
(D2 — dropped from the core image entirely), no X11 (D3 — no display libraries, no
`xhost`/`.Xauthority`, no `DISPLAY`).

**The viewer that ships here is the embed, not an application** (ADR row 29, 2026-09-06;
`docs/ARCHITECTURE.md` §7.1). It is a browser build of the Tetravox engine — HTML, JS and a
WASM module — served by `tit.server` at `/tetravox/` and drawn by the Electron renderer on the
**host's** GPU. Nothing in this image draws anything; D3 still holds. Installing the Tetravox
*desktop application* into the image remains rejected for the same reason: a container with no
display and no GPU has nothing for an Electron app to draw on, and since Chromium 137 there is
no software-WebGL fallback to stand in for one. Installing it on the *host* was tried on
2026-09-06 and reversed by the maintainer the same day: "The Dockerfile should contain Tetravox.
We should not install Tetravox on the host machine — forbidden."

One recipe. `Dockerfile.ti-toolbox.layered` (a fast local build `FROM idossha/simnibs:v2.5.0`)
was deleted, and with it `--layered` / `--from-scratch` / `--skip-ui-build`, which `build.sh`
now accepts and ignores with one line on stderr so an old command line still builds.

| File | What it does |
|---|---|
| `Dockerfile.ti-toolbox` | From-scratch: installs SimNIBS 4.6 itself (Ubuntu 22.04 -> the SimNIBS installer tarball), builds the UI in a Node stage, vendors FastSurfer in its own stage, bakes the embed. Multi-stage. This is what CI and releases publish. **30-60+ minutes even on native hardware**, far longer emulated. |

Build args (all filled in by `build.sh`): `TI_TOOLBOX_SOURCE` (`local` | `clone`),
`TI_TOOLBOX_REF` (the git ref the `clone` variant checks out), `CACHE_BUST` (force a fresh
clone while keeping earlier layers cached), `TI_TOOLBOX_VERSION` / `VCS_REF` / `VCS_SHA` /
`VCS_DIRTY` / `BUILD_DATE` (image labels and `/etc/ti-toolbox-build.json`), and
`TETRAVOX_EMBED_TGZ` + `TETRAVOX_EMBED_SHA256` (the embed tarball and its digest; both are
required — the build fails rather than shipping an image with no viewer).

### Build

```bash
./build.sh                                   # this checkout -> idossha/ti-toolbox:<version>-dev
./build.sh --tag idossha/ti-toolbox:dev      # same, tagged :dev
./build.sh --ref v3.0.0                      # a pushed ref, cloned from GitHub (CI/release)
./build.sh --tetravox-tgz http://host.docker.internal:8798/tetravox-embed-0.3.11.tgz \
           --tetravox-sha256 <hex>           # bake a tarball you built yourself (see below)
```

### Where the source comes from

**Default: the local checkout.** The repository root is the build context and the Dockerfile's
`source-local` stage `COPY`s it. The repo-root `.dockerignore` is an allow-list — `tit/`,
`resources/`, `contracts/`, `container/`, `desktop/` (minus `node_modules`, `out`, `tests`,
dot-directories), `pyproject.toml`, `README.md`, `LICENSE` — which keeps the context at
~140 MB (measured 2026-09-06: 137.5 MB unpacked in the `source` stage) instead of the raw
tree's ~2 GB. The v2 recipes (`Dockerfile.simnibs`, …) use `container/blueprint` itself as
their context and are unaffected. This is what lets an unpushed branch, or a dirty tree, be
built and tried before it is pushed — which is how the v3 image was first built at all
(`../../dev/notes/v3-native-panes-external-viewer/IB.md`).

**`--ref <git-ref>`: a pushed ref.** The `source-clone` stage `git clone --branch`es it from
GitHub (a branch or tag; `git clone --branch` does not take a raw sha) and the context is an
empty staging directory. `build.sh` refuses a ref `git ls-remote` cannot see, with the
reason. This is the CI/release path (`.circleci/config.yml` passes
`--ref "${CIRCLE_TAG:-$CIRCLE_BRANCH}"`).

Either way the image records what it was built from in **`/etc/ti-toolbox-build.json`**:

```json
{"version":"2.4.0","sha":"<40 hex>","short":"<8 hex>","dirty":true,"source":"local","ref":"","date":"2026-09-07T01:08:58Z"}
```

`dirty` is whether tracked files had uncommitted changes in the tree that was copied (a
`--ref` build is never dirty). The same sha is the `org.opencontainers.image.revision` label.
`/api/version` does not report it yet — that route's `Version` model is part of the frozen
contract (`contracts/openapi.v1.yaml`) and adding a field there is a contract change, so the
record stays a file for now.

The UI's Node stage and both `source` stages run on `$BUILDPLATFORM` (natively on Apple
silicon); only the final SimNIBS stage is emulated.

### Which Tetravox gets baked

With no `--tetravox-tgz`, `build.sh` resolves it itself (A5,
`../../dev/notes/v3-tetravox-selection-pipeline-plan.md`): the newest **non-draft,
non-prerelease** release of `idossha/tetravox` that carries all three assets —
`tetravox-embed-<ver>.tgz`, `tetravox-embed-<ver>.tgz.sha256` and
`tetravox-embed-<ver>.manifest.json` — and whose manifest `protocol` is inside the range this
checkout supports. That range is read out of `tit/tetravox/protocol.py`, not copied into the
script, so bumping `SUPPORTED_PROTOCOL_MAX` changes what a build bakes without anyone editing
this directory. The lookup is `curl` plus the Python **standard library** only (no `jq`, no
`pip install`), and it never downloads the tarball to decide — the protocol comes from the
manifest asset. The tarball's sha256 is verified against the `.sha256` sidecar before it is
unpacked; the served layout is the tarball's `dist/` plus `manifest.json`, flat in
`/opt/tetravox/embed`.

This is deliberately the same rule the running server applies at runtime
(`tit/tetravox/updates.py`), so "what a fresh image ships" and "what a running install would
update itself to" can never disagree about which release is incorporable.

Failure is fatal: an unreachable API, a GitHub rate limit (60 requests/hour/IP
unauthenticated), or no release carrying the assets makes `build.sh` exit with one sentence
telling you to pass `--tetravox-tgz` with `--tetravox-sha256`. The baked embed is the offline
floor the runtime falls back to, so an image without one is not worth publishing.

**Until a Tetravox release carries the embed assets (the first will be 0.3.12 or later —
Tetravox PR #35), the resolver finds nothing and says so.** To bake a real embed today, build
the tarball from a Tetravox checkout of that PR's branch and hand it to `build.sh`:

```bash
# in the Tetravox checkout (feat/embed-release)
pnpm install --frozen-lockfile
pnpm --filter @tetravox/embed build && pnpm --filter @tetravox/embed pack:embed
#   -> packages/embed/dist-pkg/tetravox-embed-<v>.tgz
(cd packages/embed/dist-pkg && python3 -m http.server 8798 --bind 0.0.0.0 &)
shasum -a 256 packages/embed/dist-pkg/tetravox-embed-<v>.tgz

# in this repository
./container/blueprint/build.sh --tag idossha/ti-toolbox:dev \
    --tetravox-tgz http://host.docker.internal:8798/tetravox-embed-<v>.tgz \
    --tetravox-sha256 <the digest>
```

`--tetravox-sha256` is **required** with `--tetravox-tgz`: a hand-given URL has no `.sha256`
sidecar for the image to read, and the Dockerfile will not unpack an unverified archive into a
directory it serves to every page. `host.docker.internal` is how a build stage on Docker
Desktop reaches a server on this machine. Check the tarball's `manifest.json` `protocol`
against `tit/tetravox/protocol.py`'s range yourself — the resolver does that only for
release assets.

### Open items in this directory (2026-09-06)

1. **CI's image job is over its time budget.** `.circleci/config.yml`'s `build-and-smoke-image`
   job builds the from-scratch recipe with `--ref`: 30-60+ minutes on the `vm-docker`
   (`machine: ubuntu-2204:current`) executor at best, against a 15 m `no_output_timeout`, and
   nothing in this repo provisions a large or self-hosted executor or a nightly/release-gated
   variant of the job. It is left declared so the gap is visible in CI rather than only here.
   Full reasoning on what a from-scratch-gated job would need is in
   `../../dev/notes/v3-docker-streamline/w6-docs-ci-notes.md`.

### Local build+smoke (2026-09-06, this recipe)

Attempted from this checkout (unpushed `feature/v3-electron-gui`) with a real
`tetravox-embed-0.3.11.tgz` (protocol 2). The recipe's stages up to the SimNIBS install built
(source, UI, FastSurfer clone); the build then died on a full disk (`Docker.raw` at 296 GB,
host free 160 MiB) and Docker Desktop went down with it, so **no image from this recipe has
been verified yet**. What was proved, what was not, and the two real defects found on the way
(a stale `desktop/package-lock.json`, and the FastSurfer stage's checkpoint download needing
torch) are in `../../dev/notes/v3-native-panes-external-viewer/IB.md`. The earlier layered
build's numbers are in `../../dev/notes/v3-docker-streamline/w2-image-notes.md`.

### CI (`.circleci/config.yml`, `build-and-smoke-image` job)

CircleCI's `vm-docker` executor (`machine: ubuntu-2204:current`, x86_64 — this build and its
smoke run *natively* there, unlike on Apple Silicon) builds the image with
`--ref "${CIRCLE_TAG:-$CIRCLE_BRANCH}"` and smoke-tests it. **Its time budget is an open item**
(see above). The job otherwise:

1. starts the container with the checked-out repo bind-mounted over `/ti-toolbox`
   (`PYTHONPATH=/ti-toolbox`) — the same dev-mount shape `docker-compose.v3.yml`'s optional
   `${TIT_REPO_DIR}:/ti-toolbox` documents, so the smoke test and pytest subset run against the
   commit under test, not whatever was baked in at image-build time
2. waits for the Dockerfile's own `HEALTHCHECK` to report `healthy`
3. smokes `/api/health`, `/`, `/tetravox/` (200 + the `wasm-unsafe-eval` CSP) and its
   `manifest.json`, `/etc/ti-toolbox-build.json` (a 40-hex sha), `run_fastsurfer.sh --help`, and
   `import simnibs, fastapi, torch` / `import simnibs.segmentation, brainnet`
4. runs a small, stable pytest subset inside the container (server skeleton, viewspec, catalog,
   files routes, the FastSurfer integration test — which only runs here, since `tit-v3-spike`,
   the Phase-A dev container, has no `/opt/fastsurfer`)

Full reasoning and what a from-scratch-gated job would need (a large/self-hosted executor, or a
separate nightly/release-triggered job) is in
`../../dev/notes/v3-docker-streamline/w6-docs-ci-notes.md`.

### Image size

Docker Desktop's containerd store reports "disk usage" (non-deduplicated local snapshots,
inflated by however many times an image was pulled/rebuilt on this machine) and "content
size" (the actual logical image — what a fresh pull/build transfers) separately; they can
disagree a lot for an image with build-up-over-time local history:

| Image | Disk usage | Content size |
|---|---|---|
| `idossha/simnibs:v2.5.0` (base for the since-deleted layered recipe) | 19.2 GB | 6.15 GB |
| `idossha/ti-toolbox_freesurfer:v7.4.1` (dropped entirely by D2) | 67.5 GB | 21.9 GB |
| `idossha/ti-toolbox:dev` (this session's layered build, fresh — both numbers agree) | **6.66 GB** | **6.66 GB** |

**The SimNIBS-based image itself grew slightly** (6.15 → 6.66 GB content size: FastSurfer's
CPU-only torch/torchvision + its other deps + 67 MB of checkpoints + the UI bundle + the
Tetravox placeholder — the `.layered` build inherits the base image's X11/Qt5/GTK packages
unchanged, so D3's trim isn't reflected here; see `w2-image-notes.md`). **The real space win
is D2**: a v2 stack pulls two images (SimNIBS + a separate 67.5 GB/21.9 GB FreeSurfer image);
a v3 stack pulls one, at 6.66 GB. Full commands, smoke-test output, and four real bugs found
and fixed while producing these numbers are in
`../../dev/notes/v3-docker-streamline/w2-image-notes.md`.

The from-scratch `Dockerfile.ti-toolbox` was not built this session (see that file's own
header and `w2-image-notes.md`'s "Not attempted" section for what that leaves unverified,
including one real bug — a Node version mismatch — caught by inspection rather than a build).

## v2 (existing, unchanged by this program)

```bash
docker build -f <file> -t <image_name> .
```

Where `<file>` is `Dockerfile.simnibs`, `Dockerfile.freesurfer`, etc. and `<image_name>` is
`idossha/simnibs:vX.X.X` or `idossha/freesurfer:vX.X.X`.

Use `--no-cache` to ensure no previous build layers are reused:

```bash
docker build --no-cache -f Dockerfile.simnibs -t idossha/simnibs:vX.X.X .
```

Then push:

```bash
docker push <image_name>
```

On ARM processors (Apple Silicon), add `--platform linux/amd64`:

```bash
docker build --no-cache --platform linux/amd64 \
  -f Dockerfile.simnibs \
  -t idossha/simnibs:vX.X.X .
```

---

## Apptainer (HPC)

The `apptainer.def` file builds a combined image with SimNIBS 4.5 + FreeSurfer 7.4.1 + TI-Toolbox for HPC clusters.

### Build from definition file

```bash
apptainer build ti-toolbox.sif apptainer.def
```

This requires `fakeroot` capability or root access. Build time is ~30-60 minutes. The resulting `.sif` file is ~8-12 GB.

Set a custom temp directory if `/tmp` is too small:

```bash
export APPTAINER_TMPDIR=/scratch/tmp
apptainer build ti-toolbox.sif apptainer.def
```

### Convert from Docker Hub

```bash
apptainer build ti-toolbox.sif docker://idossha/simnibs:v2.3.1
```

### Run with the wrapper script

```bash
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /data/my_study
./apptainer_run.sh --sif ti-toolbox.sif --mode slurm-template > submit.sh
```

See `./apptainer_run.sh --help` for all options.

Full documentation: [HPC Deployment Guide](../../docs/wiki/installation/hpc-apptainer.md)


## What the image deliberately does not contain

`Dockerfile.ti-toolbox` is a server image, so nothing in it exists for a human at a terminal
and nothing in it draws on a screen. Removed on 2026-09-06 and the reasons, so they are not
re-added by habit:

- **Interactive tooling** — neovim (plus its `~/.config` symlink and `+LAZY! sync` step), tmux
  and its config symlink, vim, tree, bats, GNU parallel, jq, bc, execstack, imagemagick. Nothing
  under `tit/` invokes any of them; a server image has no interactive session to serve them.
- **`python-lsp-server` / `jupyterlab-lsp` and the JupyterLab `overrides.json`** — completion in
  the app's notebooks comes from the live kernel over `/ws/kernels/{id}` (`op: "complete"`,
  `tit/server/routes/kernels.py`), not from a language server, and this image publishes no
  JupyterLab to apply settings to.
- **Compilers and autotools** — `build-essential`, `gcc`/`g++`(`-10`), `cmake`, `ninja-build`,
  `libtool`, `autoconf`, `automake`, `pkg-config`, `libopenblas-dev`. Verified by building: every
  pip requirement here resolves to a manylinux wheel, and SimNIBS ships its own interpreter and
  BLAS.
- **`gmsh`** — the 92 MB `libgmsh.so.4.14`, the `gmsh.py` ctypes wrapper, the `bin/gmsh`
  launcher and the gmsh share/doc trees are deleted right after the SimNIBS install. The only
  importer of the `gmsh` module in the whole environment is `simnibs/cli/gmsh_cli.py`, the GUI
  launcher D3 retired; nothing else in `simnibs_env` links `libgmsh`. `simnibs/mesh_tools/
  gmsh_view.py` — which `simnibs/simulation/sim_struct.py` and `tes_flex_optimization.py` *do*
  import at module load — only writes `.opt` files and never imports the module, so simulation
  and flex optimisation import and run without it.
- **SimNIBS's HTML documentation** (38 MB) — read on the web, not in a container.
- **`mesa-utils` / `mesa-va-drivers`, `gettext`, `locales`, `dos2unix`, `unzip`, `bzip2`** — no
  caller. The remaining Mesa/EGL packages and the `libX*`/`libICE`/`libSM`/`libxkbcommon`
  shared objects stay because they are `ldd` dependencies of `bpy`'s own `.so`; `import bpy`
  fails without them. That is a linkage, not a display — there is still no X11 server here.

Kept, with the reason, so these are not "cleaned up" next time:

- **`bpy`** (821 MB) — `blender` is a live job kind (`tit/jobs/kinds.py`), and the montage,
  region, vector and subcortical exporters under `tit/blender/` are the v3 visual pipeline.
- **`docker-ce-cli`** — `tit/pre/qsi/utils.py` and `docker_builder.py` still shell out to the
  `docker` CLI for QSIPrep/QSIRecon (Docker-out-of-Docker). It goes when that migrates onto
  `tit/jobs/docker_engine.py`'s Engine-API client.
- **`torchvision`** (8.9 MB) — FastSurfer's own pin; small enough not to be worth the fight.

### Size, measured 2026-09-06

| | Disk usage | Content size |
|---|---|---|
| before this pass | 19.5 GB | 5.88 GB |
| after | 9.27 GB | 2.41 GB |
