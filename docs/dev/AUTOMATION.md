# Automation and operations

This page maps automated jobs, operator scripts and recovery. [TESTING.md](TESTING.md) owns
test strategy, [RELEASING.md](RELEASING.md) owns publication, and [ROADMAP.md](ROADMAP.md)
owns unresolved work. Workflow and script source is authoritative for inputs and triggers.

## CI and deployment

| Source | Trigger and responsibility |
|---|---|
| [CircleCI](../../.circleci/config.yml) | Source and desktop checks; full image build selected explicitly with `build_image` and compatible embed inputs |
| [Release build](../../.github/workflows/release-build.yml) | Stable tags, manual dispatch or reusable invocation; export, internal distribution and public release modes |
| [Docs deploy](../../.github/workflows/deploy-docs.yml) | Relevant `main` pushes or manual dispatch; builds MkDocs API then Jekyll, checks assets and deploys Pages |
| [CodeQL](../../.github/workflows/code-ql-analysis.yml) | Configured pushes, PRs and weekly schedule; static analysis |
| [Python security](../../.github/workflows/python-security.yml) | Configured pushes, PRs, weekly schedule or manual dispatch; dependency and source scanning |

A successful source job does not prove a rebuilt image or signed installer. Inspect the result for
the exact candidate SHA. Do not suppress failed checks or repeat a partial publication blindly;
release image tags are immutable. Publication modes and credentials are covered in RELEASING.

## Operator scripts

| Entry point | Purpose |
|---|---|
| [Version updater](../../dev/update/README.md) | Dry-run/runtime version preparation; authored notes are preserved |
| [Container build](../../container/blueprint/build.sh) | Build source, UI and verified optional tool assets into the runtime image |
| [Development commands](../../CONTRIBUTING.md#development-environment) | Start/attach the project's source-mounted backend and live frontend |
| [Smoke harness](../../dev/smoke.sh) | Discover a stack and execute selected checks with output cleanup manifests |
| [Contract guard](../../dev/contracts_check.py) | Detect generated-schema drift; regenerate through the desktop `gen` script |
| [Import guard](../../dev/route_import_guard.py) | Prevent heavy scientific imports at server route import time |
| [Docs server](../serve.sh) | Local preview; full site/API generation is in [docs README](../README.md) |

## Monitoring and recovery

`/api/health` reports server availability. Jobs and Host panels expose job state, logs and resource
use; [Jobs](../wiki/jobs.md) documents interruption semantics. A health response alone does not
prove that an edited module or a new image is active. Check the actual image, mount and running
version when investigating stale code.

Before restarting or recreating a developer stack, inspect running/queued jobs. Recreation changes
session credentials. Server startup reconciles interrupted jobs; it does not resume scientific
computation. Inspect artifacts and logs before requesting a fresh run. Overwrite requires the
project permission and fresh confirmation, as described in ARCHITECTURE.

For viewer problems, retain logs and manifest identity, then use the supported retry/reload or
rollback controls. Do not clear a user's project or silently replace an active container to repair
an attachment problem. User-visible diagnosed issues belong in [troubleshooting](../wiki/troubleshooting.md).

## Backups

There is no repository-managed scheduled backup service. Operators own project backups, including
`code/ti-toolbox` metadata/notebooks and relevant derivatives. Copy a quiescent project before
migration or destructive testing; container images and Git history do not back up research data.
Keep the image/source identities with a recovery copy. Validate recovery by opening a copied
project and checking required inputs and outputs before running jobs. Test cleanup uses its
manifest and must not be substituted for general-purpose project deletion.

### Managed native FastSurfer

In Electron Settings → System on Apple Silicon, **Enable Apple GPU** explains setup and asks for user-wide consent. The runtime lives under the Electron user-data directory in `runtimes/fastsurfer-2.5.4-arm64`. Downloads and Python setup require network access; computation is offline and sandboxed. Closing the desktop or changing projects ends native access. The browser launcher and remote servers retain container execution.

Installation readiness requires the source, checkpoints and an arm64 Python with working MPS. Failed downloads can be retried. Do not move the managed virtual environment; its interpreter paths are installation-specific. Standard outputs remain under `derivatives/fastsurfer/sub-<id>` and the container creates the NIfTI/labels sidecars.

### FastSurfer GPU selection

The image includes CUDA-enabled PyTorch; NVIDIA drivers must be installed on the host and exposed by Docker (NVIDIA Container Toolkit on Linux, supported Docker Desktop/WSL GPU integration on Windows). Launchers probe the selected image before requesting GPU access. Auto jobs prefer usable container CUDA, then an approved native Apple Silicon worker, then log CPU fallback. Explicit `TIT_FASTSURFER_DEVICE=cpu` remains available; an explicit unavailable GPU fails. Recreate a stopped container through the launcher to change its GPU device requests; restarting an old CPU-only container cannot add them.

Apple GPU is a persistent desktop-user preference. New local project sessions resume the installed worker automatically; disabling it stops the worker and clears the preference. FastSurfer/FreeSurfer thread limits are saved in the shared user configuration, with automatic defaults at 80% of available computation CPUs. See the [user guide](../wiki/fastsurfer.md).
