# Container blueprints

Always build images from within the `blueprint` directory (or, for `Dockerfile.ti-toolbox*`,
via `./build.sh` — see below; it manages its own build context).

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

Build args: `TI_TOOLBOX_VERSION` (image label), `VCS_REF` (image label), `TI_TOOLBOX_REF`
(git ref to clone, default `main`), `CACHE_BUST` (force a fresh clone while keeping earlier
layers cached — the same pattern `Dockerfile.simnibs` uses) and `TETRAVOX_EMBED_TGZ` (an
http(s) URL to a released `tetravox-embed-<ver>.tgz`; empty writes a placeholder
`manifest.json`/`index.html` instead — see "Which Tetravox gets baked", since `build.sh` fills
this in on its own).

### Build

```bash
./build.sh                          # tag idossha/ti-toolbox:<version>-dev
./build.sh --tag idossha/ti-toolbox:dev --tetravox-tgz https://.../tetravox-embed-1.0.0.tgz
./build.sh --no-tetravox            # bake the placeholder deliberately (air-gapped build)
```

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

Failure is never fatal: an unreachable API, a GitHub rate limit (60 requests/hour/IP
unauthenticated), or no release carrying the assets prints one line and falls through to the
placeholder. The image is still usable — the app can install a bundle at runtime through
Settings -> Viewer engine, and `/tetravox/` simply 404s until it does.

**Today this resolves to nothing**, and says so: no `idossha/tetravox` release carries an embed
asset yet (the first will be 0.3.12 or later — Tetravox PR #35). Verified 2026-09-05:
`resolve_tetravox_tgz` exits 1 against the real API, and returns the right URL against a release
payload that does carry the assets.

`build.sh` stages a small, purpose-built build **context** under `mktemp -d` rather than using
the repo root directly — `desktop/node_modules` alone is ~700 MB, there is no repo-root
`.dockerignore` this lane owns (and adding one would affect every other Dockerfile under
`container/blueprint/`, not just this one), and BuildKit still walks the whole context directory
before any per-Dockerfile ignore rule can help on a plain `COPY`. See `build.sh`'s own header
comment for exactly what gets staged. The staged directory is removed on exit, success or
failure.

Or invoke `docker build` directly against an already-staged or hand-built context — see the
Dockerfile's own header comment for the exact `COPY` sources it expects.

### Open items in this directory (2026-09-06)

1. **`build.sh` and `Dockerfile.ti-toolbox` do not yet match this section.** As checked out
   today, `build.sh`'s header documents `--tetravox-version` / `--tetravox-url` for a *headless
   Tetravox CLI* at `/opt/tetravox/current` and treats `--tetravox-tgz` / `--no-tetravox` as
   obsolete-and-ignored, and `Dockerfile.ti-toolbox` mentions the embed only in comments — the
   bake stage that 4ddd3926 removed has not been restored. Until it is, a built image ships no
   bundle and `/tetravox/` 404s until something is installed at runtime.
2. **CI now builds the from-scratch recipe.** `.circleci/config.yml`'s `build-and-smoke-image`
   job passed `--layered --skip-ui-build`; with the layered recipe deleted that reference goes,
   which leaves the job on the from-scratch recipe: 30-60+ minutes on the `vm-docker`
   (`machine: ubuntu-2204:current`) executor at best, and nothing in this repo provisions a
   large or self-hosted executor, nor a nightly/release-gated variant of the job. Its smoke step
   also still asserts that `/tetravox/` is *retired*; with the embed restored that assertion is
   backwards and should check the manifest and the route's own `wasm-unsafe-eval` CSP again.
   Full reasoning on what a from-scratch-gated job would need is in
   `../../dev/notes/v3-docker-streamline/w6-docs-ci-notes.md`.

### Local build+smoke (2026-09-03, on the since-deleted layered recipe)

`idossha/ti-toolbox:dev` was built with `./build.sh --layered --tag idossha/ti-toolbox:dev`
and smoke-tested (health, UI, Tetravox placeholder, FastSurfer `--help`, `import simnibs,
fastapi, torch`). Numbers, exact commands, and what was **not** attempted (a from-scratch
build; `--from-scratch`'s Node/FastSurfer stages; a real FastSurfer run inside the
container) are in `../../dev/notes/v3-docker-streamline/w2-image-notes.md`.

### CI (`.circleci/config.yml`, `build-and-smoke-image` job)

CircleCI's `vm-docker` executor (`machine: ubuntu-2204:current`, x86_64 — this build and its
smoke run *natively* there, unlike on Apple Silicon) builds and smoke-tests the image. It passed
`--layered --skip-ui-build`; with the layered recipe deleted, `--layered` and `--skip-ui-build`
are ignored and the job builds the from-scratch recipe. **That is a real runtime change, and it
is an open item, not a solved one** — see "Open items in this directory" above. The job otherwise:

1. starts the container with the checked-out repo bind-mounted over `/ti-toolbox`
   (`PYTHONPATH=/ti-toolbox`) — the same dev-mount shape `docker-compose.v3.yml`'s optional
   `${TIT_REPO_DIR}:/ti-toolbox` documents, so the smoke test and pytest subset run against the
   commit under test, not whatever was baked in at image-build time
2. waits for the Dockerfile's own `HEALTHCHECK` to report `healthy`
3. smokes `/api/health`, `/`, `/tetravox/manifest.json`, `run_fastsurfer.sh --help`, and
   `import simnibs, fastapi, torch` / `import simnibs.segmentation, brainnet` — the same checks
   `dev/notes/v3-docker-streamline/w2-image-notes.md` ran locally. As checked out today the
   `/tetravox/` step still asserts the route is *retired*; with the embed restored it should
   assert the manifest and the route's own `wasm-unsafe-eval` CSP instead
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
