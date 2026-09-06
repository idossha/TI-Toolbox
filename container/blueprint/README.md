# Container blueprints

Always build images from within the `blueprint` directory (or, for `Dockerfile.ti-toolbox*`,
via `./build.sh` — see below; it manages its own build context).

## v3: `idossha/ti-toolbox:<ver>`

One image (D1, `dev/notes/v3-docker-streamline-plan.md`): SimNIBS 4.6 + `tit` + `tit.server`
+ fastapi/uvicorn/pyyaml/psutil baked in (no pip install at container start) + the built
desktop UI at `/opt/ti-toolbox/ui` + FastSurfer `--seg_only` at `/opt/fastsurfer` with
checkpoints pre-downloaded. No FreeSurfer (D2 — dropped from the core image entirely), no X11
(D3 — no display libraries, no `xhost`/`.Xauthority`, no `DISPLAY`).

**No viewer of any kind is baked in** (V4, `../../dev/notes/v3-native-panes-external-viewer-plan.md`).
The Tetravox *embed* that used to live at `/opt/tetravox/embed` is retired; viewing is the
Tetravox **desktop app**, installed on the host, which signs, notarises and updates itself. That
is the honest consequence of D3: a container with no display cannot draw, and an embed baked into
an image is a viewer release tied to a toolbox release.

Two recipes:

| File | What it does | When to use it |
|---|---|---|
| `Dockerfile.ti-toolbox` | From-scratch: installs SimNIBS 4.6 itself (Ubuntu 22.04 → the SimNIBS installer tarball), builds the UI in a Node stage, vendors FastSurfer in its own stage. Multi-stage. | **CI.** This is what gets published. 30-60+ minutes even on native hardware; not attempted in the Phase-A W2 session (see `../../dev/notes/v3-docker-streamline/w2-image-notes.md`). |
| `Dockerfile.ti-toolbox.layered` | The same v3 additions, layered `FROM idossha/simnibs:v2.5.0` (already has SimNIBS, torch, bpy, etc. baked in from `Dockerfile.simnibs`'s own build). | **Local iteration** on a machine that already has (or can pull) `idossha/simnibs:v2.5.0` — minutes, not the better part of an hour. Not what CI publishes. |

Both take the same build args: `TI_TOOLBOX_VERSION` (image label) and `VCS_REF` (image label).
`Dockerfile.ti-toolbox` additionally takes `TI_TOOLBOX_REF` (git ref to clone, default
`main`) and `CACHE_BUST` (force a fresh clone while keeping earlier layers cached — same
pattern `Dockerfile.simnibs` already uses).

### Build

```bash
./build.sh                          # layered, tag idossha/ti-toolbox:<version>-dev
./build.sh --from-scratch           # the real CI recipe (slow)
./build.sh --tag idossha/ti-toolbox:dev
```

`build.sh` stages a small, purpose-built build **context** under `mktemp -d` for each
recipe rather than using the repo root directly — `desktop/node_modules` alone is ~700 MB,
there is no repo-root `.dockerignore` this lane owns (and adding one would affect every
other Dockerfile under `container/blueprint/`, not just these two), and BuildKit still
walks the whole context directory before any per-Dockerfile ignore rule can help on a
plain `COPY`. See `build.sh`'s own header comment for exactly what gets staged for each
recipe. The staged directory is removed on exit, success or failure.

`--layered` builds the desktop UI first (`cd desktop && npm run build`) if
`desktop/out/renderer/index.html` doesn't already exist; pass `--skip-ui-build` to ship
the server's plain status page instead (useful for a build that only needs to smoke
`/api/health` and the FastSurfer/torch checks, not the UI).

Or invoke `docker build` directly against an already-staged or hand-built context — see
each Dockerfile's own header comment for the exact `COPY` sources it expects.

### Local build+smoke, this session (2026-09-03)

`idossha/ti-toolbox:dev` was built with `./build.sh --layered --tag idossha/ti-toolbox:dev`
and smoke-tested (health, UI, Tetravox placeholder, FastSurfer `--help`, `import simnibs,
fastapi, torch`). Numbers, exact commands, and what was **not** attempted (a from-scratch
build; `--from-scratch`'s Node/FastSurfer stages; a real FastSurfer run inside the
container) are in `../../dev/notes/v3-docker-streamline/w2-image-notes.md`.

### CI (`.circleci/config.yml`, `build-and-smoke-image` job)

CircleCI's `vm-docker` executor (`machine: ubuntu-2204:current`, x86_64 — this build and its
smoke run *natively* there, unlike on Apple Silicon) builds and smoke-tests **the layered
recipe**, not the from-scratch one this repo's own convention says CI should eventually
publish from (see "Two recipes" above). A from-scratch SimNIBS install is 30-60+ minutes even
natively — well past what the default `machine` resource class should absorb on every push,
and nothing in this repo provisions a self-hosted/large executor for it yet. The job:

1. `./build.sh --layered --skip-ui-build --tag idossha/ti-toolbox:ci` (`--skip-ui-build` so
   the job doesn't need an `npm ci` for the whole Electron/React toolchain just to smoke the
   container mechanics — the image ships `tit.server`'s plain status page at `/` instead of
   the built UI bundle; that bundle is `desktop`'s own build/vitest/e2e gates' job, not this
   one's)
2. starts the container with the checked-out repo bind-mounted over `/ti-toolbox`
   (`PYTHONPATH=/ti-toolbox`) — the same dev-mount shape `docker-compose.v3.yml`'s optional
   `${TIT_REPO_DIR}:/ti-toolbox` documents, so the smoke test and pytest subset below run
   against the commit under test, not whatever was baked in at image-build time
3. waits for the Dockerfile's own `HEALTHCHECK` to report `healthy`
4. smokes `/api/health`, `/`, that `/tetravox/` is *not* served (V4), `run_fastsurfer.sh --help`, and
   `import simnibs, fastapi, torch` / `import simnibs.segmentation, brainnet` — the same
   checks `dev/notes/v3-docker-streamline/w2-image-notes.md` ran locally
5. runs a small, stable pytest subset inside the container (server skeleton, viewspec,
   catalog, files routes, the FastSurfer integration test — which only runs here, since
   `tit-v3-spike`, the Phase-A dev container, has no `/opt/fastsurfer`)

Full reasoning and what a from-scratch-gated job would need (a large/self-hosted executor, or
a separate nightly/release-triggered job) is in
`../../dev/notes/v3-docker-streamline/w6-docs-ci-notes.md`.

### Image size

Docker Desktop's containerd store reports "disk usage" (non-deduplicated local snapshots,
inflated by however many times an image was pulled/rebuilt on this machine) and "content
size" (the actual logical image — what a fresh pull/build transfers) separately; they can
disagree a lot for an image with build-up-over-time local history:

| Image | Disk usage | Content size |
|---|---|---|
| `idossha/simnibs:v2.5.0` (base for `.layered`) | 19.2 GB | 6.15 GB |
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
