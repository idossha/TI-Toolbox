# Architecture

This is the current system and interface contract.
[CONTRIBUTING.md](../../CONTRIBUTING.md) owns development; [TESTING.md](TESTING.md) owns verification, and
[DECISIONS.md](DECISIONS.md) records why the design changed. Performance measurements belong in
[BENCHMARKS.md](BENCHMARKS.md); outstanding work belongs in [ROADMAP.md](ROADMAP.md).
Section numbers remain stable because source comments and tests cite them. A contract change
requires a corresponding decision entry in the same change.

## 1. Boundaries and settled stack

TI-Toolbox has three cooperating parts:

| Part | Responsibility | Source |
|---|---|---|
| Python package | Scientific computation, typed configuration, project paths and artifacts | [`tit/`](../../tit/) |
| Container server | FastAPI endpoints, job admission, dependencies, locks, resource budgets, cancellation and events | [`tit/server/`](../../tit/server/), [`tit/jobs/`](../../tit/jobs/) |
| Host application | Electron lifecycle and native integration; React workflow interface | [`desktop/src/main/`](../../desktop/src/main/), [`desktop/src/renderer/`](../../desktop/src/renderer/) |

The desktop, scripts and notebooks use the same Python science implementation. Numerical logic and
project-path rules do not belong in TypeScript. Pipelines expose typed configurations through
[`tit/config_io.py`](../../tit/config_io.py); filesystem locations come from the project's path
manager. [`contracts/openapi.yaml`](../../contracts/openapi.yaml) is the hand-written wire contract;
generated schemas and renderer types are build outputs.

The core container has no Qt GUI, X11 display or FreeSurfer installation. Dedicated viewing uses
Tetravox Embed on the host GPU; surface run previews use the application's WebGL2 renderer and volumetric previews use Tetravox (§7).
Dependency versions belong in the package manifests, lockfile and container blueprint, not prose
copies. Replacing these boundaries or adding a dependency is an architecture decision.

### Launch modes

`loader.py` uses the host Python standard library; `loader.sh` is Python-free and runs Docker
Compose directly. Both consume the root compose specification and share the project hash and
labels with Electron. Their development variants mount the launched checkout/worktree, including
the locally built UI, without replacing scientific dependencies. `pnpm dev` uses that container
with Vite; explicit `--host` runs the Python API locally on loopback and stops it on exit.
Host-only execution depends on locally installed tools and is not an image acceptance test.

## 2. Project and tab lifetime

Visited pages retain their component trees until the project session ends. Navigation hides and
inerts them rather than reconstructing forms, canvases or iframes. Form drafts, section choices,
scrolling, selected rows, camera and loaded data survive a return. Collapsing or expanding a pane
uses the same preservation rule.

Only the active page owns page commands, keyboard shortcuts and subject context. Hidden portals
must not capture focus or cover another page. A new page may inherit the active subject; an explicit
destination link may replace its selection. Project close or switch clears page memory and disposes
retained rendering resources, preventing one dataset's drafts from appearing under another.

Session drafts are distinct from machine preferences such as theme and pane width. Keeping a page
alive does not authorize restoring an unfinished scientific configuration after an application restart.

Sources: [`RetainedPages.tsx`](../../desktop/src/renderer/app/RetainedPages.tsx),
[`pageSession.ts`](../../desktop/src/renderer/app/pageSession.ts),
[`pageActivity.ts`](../../desktop/src/renderer/app/pageActivity.ts).

## 3. Run-page visualization

Run previews select scientific inputs without duplicating the full Viewer. The packaged guide has
coordinate space `guide-ras`; a guide pick may select an electrode name, net channel or atlas region,
but must never become a research subject's coordinate. Optimizer and Analyzer use this fixed guide.
Changing a subject must not rebuild or refetch a guide scene.

The Simulator also supports subject-specific anatomy for placement and recorded montage previews.
Its subject-scoped scene is the coordinate authority for scalp placement; when subject geometry is
unavailable, the guide remains a visual fallback and does not authorize coordinate picking.
Typed subject coordinates remain valid inputs independently of the guide.

A payload change preserves the camera. Framing occurs on first load or explicit reset. Skin opacity
maps directly to normalized opacity, including both endpoints; grey matter remains opaque. Changing
opacity does not reload geometry or change configured electrodes or targets. Orientation cues remain
visible. Atlas-required previews wait for the atlas, and a failed build stays visible until retry;
old pending responses must not restart endless polling.

Sources: [`ScenePane.tsx`](../../desktop/src/renderer/pages/_shared/scene/ScenePane.tsx),
[`Simulator`](../../desktop/src/renderer/pages/simulator/index.tsx),
[`guide routes`](../../tit/server/routes/guide.py).

## 4. Controls and conventions

Section 11 defines the shared interface grammar. Pages use the existing UI primitives,
semantic tokens and schema-driven forms. Scientific scope appears with the work it controls;
commitment belongs to a predictable primary action. Long values, errors and dropdowns must remain
usable inside their pane and viewport. Every interactive node has an accessible name.

Computations return jobs rather than blocking the interface. Output paths and eligibility come from
server planning and validation. A client preview is not authority to bypass server admission checks.

## 5. Verification and frozen interfaces

The verification procedure is [TESTING.md](TESTING.md). Host tests with mocked heavy
libraries do not prove numerical correctness; science changes require independent assertions against
real libraries. Published-result changes also require [release-specific scientific correction notes](../releases/v3.0.0.md#scientific-corrections).
UI tests run hidden and assess state, geometry and rendering assertions. An unavailable quiet check
is unverified, not passed.

Frozen paths are [`viewer/protocol.ts`](../../desktop/src/renderer/viewer/protocol.ts),
[`tit-bridge.d.ts`](../../desktop/src/shared/tit-bridge.d.ts) and [`contracts/`](../../contracts/).
Changes require this contract and a decision entry. Optional additions preserve prior behavior when
absent. This review requirement does not imply that every platform or runtime gate is automated.

## 6. Project overview, batch execution, the shared terminal, the guide and the Viewer

**Overview is an aggregate, not a client fan-out.**
`GET /api/catalog/project-summary` independently supplies identity, a background file-size scan
cached for five minutes, and retained job activity. Storage never blocks the subject matrix;
calendar days count job submissions in UTC, not file modifications or project visits.
`GET /api/catalog/overview` supplies project-wide
counts and readiness. Disk evidence wins; job state supplies pending or failed status only while the
artifact is absent. The vocabulary is `present`, `absent`, `partial`, `pending`, `failed`. Detailed
output browsing belongs to Results. Sources: [`catalog.py`](../../tit/catalog.py),
[`Overview`](../../desktop/src/renderer/pages/overview/).

**The server schedules batches.** `/api/jobs/groups` accepts a template plus optional per-subject
configs, tags and overwrite intent. The server assigns each generated config its own subject.
`parallel_subjects` caps running jobs in the group; it is not a client POST loop or a distinct-subject
counter. Cohort analyses remain single jobs. Sources: [`jobs routes`](../../tit/server/routes/jobs.py),
[`scheduler.py`](../../tit/jobs/scheduler.py).

**There is one interactive log renderer.** [`logLines.ts`](../../desktop/src/renderer/app/jobs/logLines.ts)
normalizes and merges events; [`JobConsole`](../../desktop/src/renderer/ui/Jobs.tsx) renders them.
Clear hides lines through a local sequence watermark and never deletes server events or log files.
Run terminals retain jobs started by their own page session, including completed output; they do not
adopt unrelated historical jobs simply because a page was opened. Diagnostic excerpts remain excerpts.

**Guide assets are packaged and immutable.** `/api/guide/*` requires neither subject data nor a build.
The manifest enumerates available atlases and nets; responses are content-addressed. The `TVSC1`
surface budget remains 3 MB and 150,000 triangles per packaged surface. Subject eligibility is checked
separately from guide availability.

**Viewer opening is a command.** `POST /api/view/open` resolves once and returns URL-addressed data
for the embed and host-addressed scene data for export. Selection-only links prepare the Menu; explicit Open in viewer actions load the selected artifact. Optional atlas selection retains the server default when absent or unavailable. See §7.1.

## 7. The viewer, the run-page renderer, pipelines and the selection grammar

### 7.1 The viewer is the Tetravox embed, and it ships in the image

Tetravox Embed runs in a same-origin iframe served at `/tetravox/`; no separate host installation is
required. The image's bundle is the offline floor. Runtime-installed bundles and an explicit override
may supersede it; absence is reported as a capability state. The viewer route owns its WASM/worker CSP
exceptions without extending them to the application's top-level page.

Compatibility is a supported protocol range plus named capabilities, not a TI-to-Tetravox version
pair. The server and renderer declarations are checked together. Unsupported surface capabilities
must be reported, never approximated by treating a cortical surface as a tetrahedral mesh.

Downloads are checksum-verified before extraction. Archives cannot escape their destination through
absolute paths, traversal or links; activation is atomic. The update policy is server-owned and
checks outside the rendering path. Pins, including the baked bundle, support rollback. Runtime
capabilities describe the active bundle rather than a build-time assumption.

The Viewer has Menu and Tetravox subroutes within one retained page. Its embed mounts before a
scene is selected, allowing direct local file drops. Open resolves the editable
composition once. Scenes contain one research subject; shared templates and atlases are exempt.
Layer names are file basenames. A composition stores input choices and re-resolves current data;
a saved `.tetravox.json` scene stores the embed's serialized view, including camera and layer state.

Tetravox owns dataset decoding, URL/sidecar reuse and disposal. Cancelled loads cannot adopt stale
layers, and a failed dataset does not discard successful ones. TI owns load/error presentation.
Explicit Reload remounts the iframe, releases workers and re-reads files at unchanged paths.

Sources: [`tit/tetravox/`](../../tit/tetravox/),
[`embedProtocol.ts`](../../desktop/src/renderer/viewer/embedProtocol.ts),
[`static.py`](../../tit/server/static.py), [`viewspec.py`](../../tit/viewspec.py),
[`viewer library`](../../tit/server/routes/viewer_library.py),
[`TetravoxFrame.tsx`](../../desktop/src/renderer/viewer/TetravoxFrame.tsx).

### 7.2 Run-page surface selection and volumetric previews

[`scene/`](../../desktop/src/renderer/scene/) renders surfaces, screen-space markers and atlas
selection without an iframe or a second graphics dependency. Guide labels align with their geometry.
A triangle's majority region label controls flat shading and picking; rotating its vertices preserves
winding and prevents the provoking vertex from assigning a minority label. Triple junctions retain
their original ordering.

Electrode color expresses availability and channel membership, with no additional selection ring.
The form, channel legend and preview share one palette and one selection model. Atlas clicks and ROI
chips edit the same region list. Coordinate picking remains constrained by §3.

Non-surface targets use a private Tetravox channel, separate from the retained Viewer.
`POST /api/scene/target-preview` caches a binary target extent on the subject T1 grid for masks,
subcortical labels, spheres and saved ROI centers. Preview events never change the form;
incomplete requests and errors clear old geometry. Tissue and mesh filtering remain downstream.

Optimizer mask targets explicitly declare Subject or MNI space. Subject masks retain their
coordinates; MNI masks use SimNIBS’ subject registration with nearest-neighbor resampling,
not only the conformation affine. The existing volumetric ROI config carries whole-mask targets
with a null label. In stacked layouts, run panes fill the page width and receive viewport-scaled
height; desktop pane widths remain remembered for the wide layout.

Analyzer reuses that mask registration and picker through additive `analysis_type="mask"`
and `mask_path` fields; absent `mask_path` preserves existing ROI behavior. Positive voxels
select nodes on the subject GM surface (area statistics) or voxels in the subject field grid
(volume statistics, intersected with the selected tissue). Group masks require MNI coordinates
so each subject gets its own registered target. Nearest-neighbor sampling preserves membership;
`tests/numerical/test_analyzer_masks.py` pins transformed landmarks, membership, and units.

### 7.3 Pipelines

A pipeline is a typed DAG of existing job kinds, with a `subjects` source and ports `subjects`,
`montages`, `simulation`, `roi`, `leadfield`. Each processing node owns its configuration; an edge
transfers only its named binding. Readiness checks propagate required and produced capabilities and
name subjects that cannot proceed. Shape validation returns structured issues; malformed documents
are request errors.

One pipeline run uses one job group and the existing scheduler, cancellation and events. Static
bindings resolve during planning. Dynamic bindings use intermediate resolve jobs and are merged into
consumer configuration at admission, when producer files can exist. Pipeline execution introduces
no separate retry, conditional or scheduling engine. Notebook export calls the public scripting API
and preserves the document in metadata.

The UI previews independently resolvable destinations. Partial previews cannot enable replacement;
Skip on a conflicting pipeline queues no jobs because dependencies cannot be partially skipped there.
New dynamic pipelines retain the non-overwrite path. Saved nested destructive flags do not substitute
for the current submission's decision.

Sources: [`pipeline schema`](../../contracts/pipeline.schema.json), [`tit/pipeline/`](../../tit/pipeline/),
[`bindings.py`](../../tit/jobs/bindings.py),
[`Pipeline API`](../../desktop/src/renderer/pages/pipeline/api.ts).

### 7.4 One selection grammar

Set selection uses [`SelectionList`](../../desktop/src/renderer/ui/SelectionList.tsx): plain click
selects one, Shift-click extends a range, modifier-click toggles, modifier-A selects the filtered set
and Escape clears. All/None affect visible rows while preserving hidden selections. Selection order
determines submission order. Unavailable rows remain visible with their reason and cannot enter a
run through bulk selection. Participant row lists preserve repeats needed by paired studies.

A run's grid and action digest derive from one `PlanModel`. They do not maintain separate counts.
Registry order owns navigation and shortcut numbering; subroutes do not create extra page instances.

### 7.5 A run page that submits many jobs describes them as a table

Simulator, Analyzer and Optimizer use explicit job rows. A row owns its subject and all inputs that
differ between jobs; duplicate-and-edit expresses repeated work without implicit cross-products.
Incomplete rows remain editable but are not submitted. A cohort mode uses those same rows and rejects
incompatible shared settings. Submission preserves the table. Mixed job kinds require separate group
submissions, so the UI must not imply atomicity across them.

Flex planning resolves the exact absolute subject output folder before submission and reuses that
configuration. Automatic names refresh after successful submission. Python's literal output-folder
semantics remain unchanged. Simulator rows own `map_to_fsavg`, default false in the UI, including old
saved settings without the key. The Source panel builds forward solutions; standalone Python mapping
remains available.

### 7.6 Notebooks

Notebooks are `.ipynb` files inside the project's notebook directory. The server owns one SimNIBS
kernel per active notebook and the kernel budget/reaper; clients read those limits from the API.
Kernel execution has the container user's project access and is not a sandbox.

Outputs are attributed by parent message ID. Completion waits for both execution reply and idle;
restart joins message pumps before closing sockets and recreates channels. Completion/signature
requests use an existing kernel and never start one on a keystroke. Saves validate nbformat and
preserve unknown fields. The getting-started example is seeded once, so deletion stays deleted.

Navigation preserves the kernel and flushes unsaved edits. Window close releases kernels; the server
reaper and shutdown are backstops. Rich interactive widgets are outside this notebook surface;
static outputs remain supported.

Sources: [`kernels.py`](../../tit/server/kernels.py), [`notebooks.py`](../../tit/server/notebooks.py),
[`notebook session`](../../desktop/src/renderer/pages/notebooks/session.ts).

## 8. The science pipelines, end to end

All entry points use these same Python modules and path-manager output locations:

| Workflow | Computation and outputs | Source |
|---|---|---|
| Simulation | SimNIBS solves each montage channel, then TI metrics are derived; high-frequency and TI field artifacts belong to the simulation | [`tit/sim/`](../../tit/sim/), [`calc.py`](../../tit/calc.py), [`fields.py`](../../tit/fields.py) |
| Flex search | Differential evolution over electrode placement, optional multi-start selection, net mapping and full-resolution simulation | [`tit/opt/flex/`](../../tit/opt/flex/) |
| Ex / mEx search | Exhaustive evaluation within configured electrode buckets and current discretization | [`tit/opt/ex/`](../../tit/opt/ex/), [`tit/opt/mex/`](../../tit/opt/mex/) |
| Analysis and statistics | Subject/cohort metrics over selected fields, spaces and targets | [`tit/analyzer/`](../../tit/analyzer/), [`tit/stats/`](../../tit/stats/) |

Flex-to-simulation uses the electrode mapping as a montage input. A simulation is not an optimizer;
Flex does not promise a global optimum; exhaustive search is exhaustive only within its configured
discretization. Flex's CPU setting does not imply parallel differential-evolution candidates.
Run names and output folders identify real destinations, so replacement rules apply to repeated names.

## 9. DWI preprocessing runs as sibling containers

QSIPrep and QSIRecon run as sibling containers through the Docker socket, not inside the core image.
Bind sources must be host paths resolved using `LOCAL_PROJECT_DIR`. A license needed by a sibling
travels through the shared filesystem and is supplied through its required environment and CLI forms.
Each image has its own version constant. Platform emulation and runtime requirements belong in the
operations documentation, not as timing promises here.

The supported reconstruction path feeds scalar/tensor extraction, registration and SimNIBS tensor
conversion. The custom scalar-only GQI spec avoids unnecessary connectivity and atlas requirements.
Other upstream reconstruction specs are not implicitly validated by this integration. Diffusion
registration and tensor reorientation retain the expert-review limitation recorded in
[RELEASING.md](RELEASING.md).

Sources: [`tit/pre/qsi/`](../../tit/pre/qsi/), [`structural.py`](../../tit/pre/structural.py),
[`GQI scalar spec`](../../resources/qsirecon_pipelines/dsi_studio_gqi_scalar.yaml).

## 10. Internal builds and public availability

Internal builds and public releases use the same product and packaging pipeline. An internal cohort
records its source revision and immutable image identity; launchers and installers resolve the same
image. An explicit image request retains mismatch protection. Publishing a container or preparing
an internal build does not create a public release, move `latest` or rewrite stable announcement
metadata. [RELEASING.md](RELEASING.md) owns distribution procedures and current availability.

### Runtime dependency boundaries

The scientific environment retains SimNIBS's dependency pins. Blender scene creation uses the pinned
Blender distribution's own Python in a cancellable child; prepared geometry crosses the boundary,
not imports of SimNIBS. The parent retains scientific extraction and artifact reporting. Optional
checkpoint caches require verified digests and fixed extraction destinations; download failure never
authorizes disabling TLS verification. Source: [container blueprint](../../container/blueprint/).

### Branch lifecycle

Production and release stabilization follow [root CONTRIBUTING](../../CONTRIBUTING.md). Branch pushes
do not publish releases. Promotion preserves tested ancestry; official publication is a separate
maintainer-controlled action.

### Terminal launcher setup

Python and Bash launchers share [`tit/cli.py`](../../tit/cli.py) setup. Interactive mode asks for the
project; explicit arguments remain scriptable. Missing or cancelled terminal input launches nothing.
Implicit interactive reconnect can resume the project's existing session; an explicit image request
must match. Advanced settings remain flags rather than a questionnaire.

Mounted development uses the launched checkout for Python and UI. Attach verifies the actual Docker
bind and import precedence; mounted UI never falls back to baked assets. Automatic container
replacement requires a verified idle job list. Sources: [`dev.ts`](../../desktop/scripts/dev.ts),
[`stack.ts`](../../desktop/src/main/stack.ts).

### Extension run panes and export selection

Extensions retain returned job IDs and share the live terminal beneath a bounded plan. Export previews
follow their selected subject and configuration; isolated embed channels cannot replace the main
Viewer scene. Preview geometry is context, not proof that export computation completed.
Participant CSV/TSV import validates all rows before replacing any; exports use the existing host
save-file bridge or browser download.

### Overwrite permission

`allow_unsafe_overrides` is project-scoped and default-off. Existing outputs require a fresh UI
choice, including Rerun; old confirmation state and saved config flags confer no authority.
The shared dialog offers Skip, Replace and rerun, or Cancel. Replace stays disabled unless the saved
project setting is true; loading or failed settings checks confer no permission. Skip states whether
new jobs will run; Pipeline Skip and job Rerun Skip queue nothing. Incomplete pipeline previews cannot
enable Replace.
Submission routes enforce project permission before single jobs, groups, pipelines or reruns create
jobs. Simulation overwrite intent reaches the subprocess and native SimNIBS session; ordinary runs
retain native existence protection. Caller environment variables cannot supply permission.

Sources: [`overwrite_policy.py`](../../tit/server/overwrite_policy.py),
[`ExistingOutputsDialog.tsx`](../../desktop/src/renderer/pages/_shared/run/ExistingOutputsDialog.tsx),
[`JobDetailPane.tsx`](../../desktop/src/renderer/app/jobs-rail/JobDetailPane.tsx).

## 11. Interface design

The interface supports configuring scientific work, monitoring expensive computations and reaching
results. Use compact, readable controls, sentence case and consistent action verbs. Numbers, units,
filenames and scientific scope take precedence over decoration. Lifecycle, coordinate authority and
submission rules remain in §§2–3 and §§6–10; this section defines their presentation.

### Layout and navigation

[`PageLayout`](../../desktop/src/renderer/ui/Layout.tsx) supplies three shapes:

| Shape | Work area | Secondary area |
|---|---|---|
| Run | Inputs and a bottom action bar | Bounded plan above Terminal, with Scene where supported |
| Browse | Table, catalog or results tree | Selected item detail or preview |
| Bleed | Canvas or dedicated viewing surface | No additional inspector |

Use the available width. An unselected detail pane is absent; an idle run terminal reserves useful
space for logs. The action bar sits outside the work scroller, with its primary action on the right
and at most one secondary action. Controls cannot scroll beneath it. Wide tables scroll internally;
no page has horizontal overflow. Pane resize supports drag, keyboard, reset, collapse and expansion,
with remembered widths and the retention guarantees in §2.

Sizing and responsive behavior live in [`tokens.css`](../../desktop/src/renderer/ui/tokens.css),
[`pane.css`](../../desktop/src/renderer/ui/pane.css),
[`paneState.ts`](../../desktop/src/renderer/ui/paneState.ts) and
[`shell.css`](../../desktop/src/renderer/app/shell.css). Support the desktop minimum of 1024 × 680;
narrow panes become drawers and forms respond to their own container width.

The context bar owns command search, connection state and running-job count. Scientific scope stays
in the page or palette. The jobs rail remains available throughout the app, with Jobs/Host views,
raw logs and artifacts. There is no separate bottom status bar. System, Settings and Help have page
headers; workflow pages use their navigation context. [`registry.ts`](../../desktop/src/renderer/app/registry.ts)
owns navigation order, gating, palette destinations and shortcuts, including Viewer subroutes.
Enabled extension pages are grouped under a collapsible Extensions item; grouping does not change
their routes or retained page instances.

Simulator's saved-definition manager deletes montage or freehand definitions only. Confirmed
deletion clears matching draft job selections, preserving completed simulation outputs. Freehand
deletion is subject-scoped through `DELETE /api/catalog/freehand/{name}?subject=...`.
The manager uses a fixed-height scroll region. Bulk deletion reports partial success and leaves
failed definitions selected for retry rather than claiming the entire selection was deleted.

### Visual system and controls

[`ui/`](../../desktop/src/renderer/ui/) owns layout, controls, selection, feedback and overlays;
[`pages/_shared/`](../../desktop/src/renderer/pages/_shared/) owns shared domain components. Exported
TypeScript props are the component reference. Use semantic tokens from `tokens.css`, not copied
colors or a page-specific design vocabulary. Panes use thin rules; elevation belongs to overlays.
Accent denotes actions and selection, semantic state colors have accompanying text, and scientific
field colors keep their own meaning. Muted placeholder/disabled ink is not normal body copy.

Use IBM Plex Sans for prose and IBM Plex Mono for values, paths and logs, with tabular numbers.
Normal copy has a 12 px floor; shared tokens own the remaining scale and 4 px spacing grid.
Disabled controls are distinguishable and expose a reason where needed. Loading keeps button labels
and widths stable. Dialogs, dropdowns and tooltips fit the viewport and remain keyboard accessible.

Light is the initial theme. Light, dark and system preferences apply before paint through the
[theme store](../../desktop/src/renderer/app/theme/store.ts). Scientific canvases retain their dark
ground in either theme; authored figures retain their background. Both themes support readable
contrast, visible focus and reduced motion. App shortcuts use Cmd/Ctrl; unmodified keys belong to
the focused editor or canvas. Escape closes the innermost overlay first.

### Forms, tables and feedback

Forms use shared label rows, help popovers and unit suffixes. Wide tables, coordinate editors, paths
and consoles span the row. Flush `FormSection` groups have nonsticky headers; collapsed sections
summarize values and retain changed/error indicators. Essential choices remain exposed, and advanced
non-default settings remain apparent. User-touched disclosure choices outrank automatic layout.
Schema defaults, changed values and field validation use [`forms/`](../../desktop/src/renderer/forms/).
Blocked actions explain their reason; output replacement is decided at commitment (§10).

Tables retain their headers and inline empty state, use shared row density and right-align numbers.
Job rows align identifying fields in columns, with richer pairs, currents and targets on a second
line where needed. Inapplicable cells show a reasoned dash; incomplete rows remain editable (§7.5).

| State | Presentation |
|---|---|
| Initial load | Skeleton or dataset progress sized for expected content |
| Empty | Inline explanation and relevant action, preserving table or console shape |
| Load failure | Persistent local error and retry |
| Refetch | Existing content remains visible with a refresh indication |
| Disconnected | Editable drafts survive; unavailable submission has a reason |

Submission toasts supplement the persistent job record. A rendering failure retains successful
layers where possible. Errors name what failed and a usable next step.

### Workflow presentation

[`RunPanel`](../../desktop/src/renderer/pages/_shared/run/RunPanel.tsx) bounds the plan above live output.
The shared [`PlanModel`](../../desktop/src/renderer/pages/_shared/run/planModel.ts) supplies counts,
paths, waits and representative per-job CPU/memory cost; do not multiply these into an invented batch
budget. Chip precedence is `blocked > wait > overwrite > skip > new`. Blocked-chip detection currently
matches prose warnings because the wire plan lacks structured per-cell blockers; it is a preview
limitation, not server admission authority. The terminal header identifies the actual job and state.

Pipeline cards use shared density and tokens. Named ports supplement color; missing inputs lead to
the node editor. A valid receipt states jobs and dependencies; an invalid receipt groups structured
issues by node and offers Fix. The empty prompt leaves the canvas mounted and sample/import actions
available. Samples still undergo current server validation.

The Viewer Menu's subject/space tree and editable composition share selection. Meshes, surfaces,
volumes and attachments retain server-classified kinds, filenames and size. The embed owns detailed
camera/layer controls; TI provides a slim scene/reload strip and distinguishes missing bundle,
handshake timeout, rendering unavailability and dataset failure. See the
[Viewer page](../../desktop/src/renderer/pages/viewer/index.tsx) and §7.1 for load and retention rules.
Settings reports the active bundle, compatibility, source and verified digest; opening it does not
itself fetch a remote release index. Project overwrite permission is separate from machine preferences.

Notebooks place the file list beside a single cell scroller. Execution controls and kernel state
remain visible, with recovery actions. CodeMirror completion uses the existing kernel; editor
preferences remain separate from document content. Selected cells use an accent rule; stderr and
error outputs have distinct warning/danger treatment. Kernel and save guarantees remain in §7.6.

### Interface verification contract

Hidden tests assert useful occupied space, reachable essential controls, no action-bar occlusion and
no contentless detail pane. Executable thresholds belong to the tests, not copied historical numbers:
[`_metrics.ts`](../../desktop/tests/e2e/_metrics.ts),
[`layout.spec.ts`](../../desktop/tests/e2e/layout.spec.ts) and
[`screens.spec.ts`](../../desktop/tests/e2e/screens.spec.ts). Screenshots supplement assertions.

Preserve work/right-pane test IDs, `data-tier="1"`, user-touched disclosure markers and chosen pane
tab markers. Shell `data-page`/`data-subject` identify active context because MemoryRouter navigation
is not described by the browser URL alone. Tests distinguish active content from hidden retained pages.
