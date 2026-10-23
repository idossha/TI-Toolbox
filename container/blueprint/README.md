# Container blueprint

This page owns the local contract for `Dockerfile.ti-toolbox`, `build.sh`, and the Apptainer
recipe built from the image. Release publication belongs in
[RELEASING](../../docs/dev/RELEASING.md); image design decisions belong in
[DECISIONS](../../docs/dev/DECISIONS.md).

## Application image

`Dockerfile.ti-toolbox` builds the single v3 application image. It contains:

- SimNIBS 4.6 and the `tit` package;
- the FastAPI server and the built desktop renderer it serves;
- FastSurfer 2.5.4 `--seg_only`, its verified checkpoints, and CUDA-enabled PyTorch;
- `bpy` for the Blender-backed export job kinds; and
- the Docker CLI used by the current QSIPrep/QSIRecon Docker-out-of-Docker integration.

The final runtime is `linux/amd64`. It runs natively on x86-64 hosts and under Docker's amd64
emulation on Apple Silicon. Host NVIDIA drivers and Docker GPU access are host prerequisites;
the image cannot install them.

TetraVox is installed separately on the host by the desktop app. The application image contains
no viewer bundle. Optional FreeSurfer reconstruction runs through the separately versioned worker
recorded in [RELEASING](../../docs/dev/RELEASING.md), not in this image.

## Build this checkout

Run from `container/blueprint/`:

```bash
./build.sh
./build.sh --tag idossha/ti-toolbox:dev
```

The default source is the local repository checkout. `build.sh` chooses the repository root as
the Docker context, and the root `.dockerignore` limits what enters that context. This mode can
build unpushed or dirty work for local verification.

To build a pushed branch or tag instead:

```bash
./build.sh --ref v3.0.0
./build.sh --ref main --tag idossha/ti-toolbox:dev
```

`--ref` must resolve through `git ls-remote`; the Docker build clones that ref into an otherwise
empty context. A raw commit SHA is not accepted by the underlying `git clone --branch` operation.
Use `./build.sh --help` for the complete current option list. Verified FastSurfer/Blender transport
caches and their required checksum/provenance handling are documented in
[RELEASING](../../docs/dev/RELEASING.md); they do not define a second image recipe.

The script supplies these Docker build arguments:

| Argument | Meaning |
|---|---|
| `TI_TOOLBOX_SOURCE` | `local` or `clone` source stage |
| `TI_TOOLBOX_REF` | Branch/tag used by the clone source stage |
| `CACHE_BUST` | Refresh a moving clone while retaining earlier cached layers |
| `TI_TOOLBOX_VERSION` | Runtime/application version label |
| `VCS_REF`, `VCS_SHA`, `VCS_DIRTY` | Source identity and local tracked-dirty state |
| `BUILD_DATE` | UTC image build timestamp |

Every image records those source facts at `/etc/ti-toolbox-build.json` and in OCI labels. The
record includes the version, full and short commit SHA, dirty flag, source mode, ref, and build
date. Inspect it when verifying an image; a mutable tag alone does not identify the source:

```bash
docker run --rm --entrypoint cat idossha/ti-toolbox:dev /etc/ti-toolbox-build.json
```

The Dockerfile is multi-stage. Source and renderer build stages run on `$BUILDPLATFORM` (the renderer
installs with `npm ci --ignore-scripts`: the native `node-pty` is desktop-only); the final
SimNIBS stage targets `linux/amd64`. A clean from-scratch build is intentionally substantial. CI
and release automation call the same `build.sh`; their triggers and evidence requirements live in
[AUTOMATION](../../docs/dev/AUTOMATION.md) and
[RELEASING](../../docs/dev/RELEASING.md).

## Intentional exclusions

The runtime omits components that do not serve the v3 server/job model:

| Excluded | Reason |
|---|---|
| FreeSurfer `recon-all` | Optional work is isolated in the separate worker image |
| X11, Qt/PyQt5, `simnibs_gui` | The deleted v2 GUI and display forwarding are not part of v3 |
| Gmsh application/library | The runtime writes `.msh`; native TetraVox views outputs |
| Interactive editors, tmux and shell utilities | The container is an application server, not a development workstation |
| Compilers and autotools | Shipped Python dependencies resolve to wheels; the final image does not build extensions |
| JupyterLab language-server packages | Notebook completion uses the live kernel protocol |
| SimNIBS HTML docs and TMS coil models | Documentation is hosted; this toolbox is TES-only |

Do not remove `bpy`, the Docker CLI, or FastSurfer's pinned `torchvision` as apparent cleanup:
they have live runtime callers. Detailed rationale and reversals belong in
[DECISIONS](../../docs/dev/DECISIONS.md), not copied here.

## Apptainer recipe

`apptainer.def` builds a SIF from the published `idossha/ti-toolbox:v<version>` image, the tag
`dev/update/update_version.py` stamps on each release, so the SIF carries exactly the software the
Docker app runs: SimNIBS 4.6 with NumPy 2.3.5 and Blender outside its environment. It installs
nothing. Its `%post` only makes `/root`, where SimNIBS is installed, readable by the non-root user
Apptainer runs as, and its `%test` runs `verify_runtime.py`, the Docker build's last check. Do not
add packages to it: why the SIF must be the image is in [DECISIONS](../../docs/dev/DECISIONS.md).

The SIF is **not validated as a v3 distribution**: the desktop app does not manage a SIF, and the
runscript opens a shell (or runs its arguments) instead of starting `tit.server`. The supported
remote path remains the Docker-backed
[SSH browser launcher](../../docs/wiki/installation-cli.md#over-ssh).

```bash
apptainer build ti-toolbox.sif apptainer.def
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /data/my_study
./apptainer_run.sh --sif ti-toolbox.sif --mode slurm-template > submit.sh
./apptainer_run.sh --help
```

Building requires root or fakeroot; set `APPTAINER_TMPDIR` to cluster scratch when `/tmp` is too
small. The user-facing status and alternatives are in the
[HPC guide](../../docs/wiki/installation-hpc.md).
