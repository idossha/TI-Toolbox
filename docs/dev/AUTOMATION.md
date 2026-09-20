# Automation and operations

This page maps automated jobs, operator scripts and recovery. [TESTING.md](TESTING.md) owns
test strategy, [RELEASING.md](RELEASING.md) owns publication, and [ROADMAP.md](ROADMAP.md)
owns unresolved work. Workflow and script source is authoritative for inputs and triggers.

## CI and deployment

| Source | Trigger and responsibility |
|---|---|
| [CircleCI](../../.circleci/config.yml) | Source and desktop checks; full image build selected explicitly with `build_image` |
| [Release build](../../.github/workflows/release-build.yml) | Stable tags, manual dispatch or reusable invocation; export, internal distribution and public release modes |
| [Docs deploy](../../.github/workflows/deploy-docs.yml) | Relevant `main` pushes or manual dispatch; builds MkDocs API then Jekyll, checks assets and deploys Pages |
| [CodeQL](../../.github/workflows/code-ql-analysis.yml) | Configured pushes, PRs and weekly schedule; static analysis |
| [Python security](../../.github/workflows/python-security.yml) | Configured pushes, PRs, weekly schedule or manual dispatch; dependency and source scanning |

A successful source job does not prove a rebuilt image or signed installer. Inspect the result for
the exact candidate SHA. Do not suppress failed checks or repeat a partial publication blindly;
release image tags are immutable. Publication modes and credentials are covered in RELEASING.

## Telemetry service

User consent, payload fields and opt-out controls are documented in the
[telemetry and privacy guide](../wiki/telemetry.md); `tit/telemetry.py` and `tit/constants.py` are
the implementation authority. Operational ownership is separate from the documentation site's
analytics:

### GA4 property and stream

The GA4 property is **`tit-telemetry`**, separate from the documentation site's analytics. Its
Web stream is named **`CLI/GUI Events`**, uses measurement ID `G-2GGJF2D8C7`, the repository URL
only as the stream's website label, and has Enhanced Measurement disabled because events arrive
through Measurement Protocol. The `tit-usage` Measurement Protocol secret in `tit/constants.py`
grants event submission only; GA4, BigQuery and dashboard read access remains controlled by the
maintainer's Google/GCP IAM.

GA4 parameters must be registered under **Admin → Custom definitions** before they are available
as report dimensions. The current implementation uses this event-scoped mapping:

| GA4 display name | Event parameter |
|---|---|
| TIT Version | `tit_version` |
| Host OS | `os_name` |
| Host OS Version | `os_version` |
| Host Architecture | `platform` |
| Interface | `interface` |
| Status | `status` |
| Duration (seconds) | `duration_s` |
| Error Type | `error_type` |
| Error Detail | `error_detail` |
| Error Fingerprint | `error_fingerprint` |
| Run ID | `run_id` |

New definitions can take 24–48 hours to appear in reporting. `report_type` and `n_subjects` from
older dashboard notes are not emitted by the current telemetry implementation and must not be
presented as current payload fields.

### BigQuery export and recovery

GA4 exports a daily batch to the **`tit-telemetry`** GCP project. The dataset is
`analytics_<PROPERTY_ID>`, its tables are `events_YYYYMMDD`, and its location is **US**; BigQuery
dataset location is immutable after creation. GA4's configured event-data retention is 14 months;
exported-table retention is a BigQuery policy and must be checked there rather than inferred from
the GA4 setting. GA4 does not backfill days before a working link.

The maintained Cloud Run dashboard and daily `daily_metrics` aggregation live in
[idossha/TI-toolbox-stats](https://github.com/idossha/TI-toolbox-stats). Monitor GA4 Realtime for
recent delivery, the dashboard for operation/error trends, and BigQuery for a fresh daily table.
If export stops, first verify billing at the
[`tit-telemetry` linked-account page](https://console.cloud.google.com/billing/linkedaccount?project=tit-telemetry),
the BigQuery API, the GA4 BigQuery Link, and the auto-provisioned
`firebase-measurement@system.gserviceaccount.com` service account (`BigQuery User` and
`Logs Writer`).

To recreate the link:

1. Sign in to [Google Cloud](https://console.cloud.google.com) with the Google account that owns
   the GA4 property and select the existing `tit-telemetry` project.
2. Enable the BigQuery API and attach a billing account **before** creating the link. A link can
   appear valid without billing while producing no dataset.
3. In [Google Analytics](https://analytics.google.com), open the `tit-telemetry` property, then
   **Admin → Product links → BigQuery Links → Link**.
4. Select the `tit-telemetry` project, choose location **US** and export type **Daily**, and leave
   **Include advertising identifiers** unchecked.
5. Submit, then allow the next daily cycle (normally about 24 hours) for the dataset/table to
   appear. If a pre-billing link remains inert after that cycle, unlink and repeat these steps.

Google's [BigQuery Export guide](https://support.google.com/analytics/answer/9358801) covers service
recovery. Do not rotate the send-only client constant as though it were a dashboard credential.

## Operator scripts

| Entry point | Purpose |
|---|---|
| [Version updater](../../dev/update/README.md) | Dry-run/runtime version preparation; authored notes are preserved |
| [Container build](../../container/blueprint/build.sh) | Build source, UI and verified optional tool assets into the runtime image |
| [Launcher](../../loader.sh) | One launch model: `loader.sh`/`loader.py`, `--dev [DIR]` for a source-mounted checkout, `--print-config` for the resolved settings |
| [Development commands](../../CONTRIBUTING.md#development-environment) | Start/attach the project's source-mounted backend and live frontend |
| [Smoke harness](../../dev/smoke.sh) | Discover a stack and execute selected checks with output cleanup manifests |
| [Contract guard](../../dev/contracts_check.py) | Detect generated-schema drift; regenerate through the desktop `gen` script |
| [Import guard](../../dev/route_import_guard.py) | Prevent heavy scientific imports at server route import time |
| [Example notebook](../../dev/run_example_notebook.sh) | Execute the seeded example notebook in the image against a fresh project; `dev/render_example_notebook.py` regenerates its wiki page |
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

In Electron Settings → System on Apple Silicon, **Enable Apple GPU** explains setup and asks for user-wide consent. The runtime lives under the Electron user-data directory in `runtimes/fastsurfer-2.5.4-arm64`. Downloads and Python setup require network access; computation is offline and sandboxed. Closing the desktop or changing projects ends native access. Browser fallback sessions and remote servers retain container execution; the Apple GPU path is one reason the desktop app, not the browser, is the product.

Installation readiness requires the source, checkpoints and an arm64 Python with working MPS. Failed downloads can be retried. Do not move the managed virtual environment; its interpreter paths are installation-specific. Standard outputs remain under `derivatives/fastsurfer/sub-<id>` and the container creates the NIfTI/labels sidecars.

### FastSurfer GPU selection

The image includes CUDA-enabled PyTorch; NVIDIA drivers must be installed on the host and exposed by Docker (NVIDIA Container Toolkit on Linux, supported Docker Desktop/WSL GPU integration on Windows). Launchers probe the selected image before requesting GPU access. Auto jobs prefer usable container CUDA, then an approved native Apple Silicon worker, then log CPU fallback. Explicit `TIT_FASTSURFER_DEVICE=cpu` remains available; an explicit unavailable GPU fails. Recreate a stopped container through the launcher to change its GPU device requests; restarting an old CPU-only container cannot add them.

Apple GPU is a persistent desktop-user preference. New local project sessions resume the installed worker automatically; disabling it stops the worker and clears the preference. FastSurfer/FreeSurfer thread limits are saved in the shared user configuration, with automatic defaults at 80% of available computation CPUs. See the [user guide](../wiki/fastsurfer.md).
