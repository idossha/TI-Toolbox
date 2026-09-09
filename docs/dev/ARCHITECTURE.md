# Architecture

This is the current system contract. [DESIGN.md](DESIGN.md) owns interface behavior,
[CONTRIBUTING.md](CONTRIBUTING.md) owns development and verification procedures, and
[DECISIONS.md](DECISIONS.md) records why the design changed. Results belong in
[BENCHMARKS.md](BENCHMARKS.md); outstanding work belongs in [RELEASE.md](RELEASE.md).
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
Tetravox Embed on the host GPU; focused run previews use the application's WebGL2 renderer (§7).
Dependency versions belong in the package manifests, lockfile and container blueprint, not prose
copies. Replacing these boundaries or adding a dependency is an architecture decision.

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

[`DESIGN.md`](DESIGN.md) owns the shared interaction grammar. Pages use the existing UI primitives,
semantic tokens and schema-driven forms. Scientific scope appears with the work it controls;
commitment belongs to a predictable primary action. Long values, errors and dropdowns must remain
usable inside their pane and viewport. Every interactive node has an accessible name.

Computations return jobs rather than blocking the interface. Output paths and eligibility come from
server planning and validation. A client preview is not authority to bypass server admission checks.

## 5. Verification and frozen interfaces

The verification procedure is [CONTRIBUTING.md](CONTRIBUTING.md). Host tests with mocked heavy
libraries do not prove numerical correctness; science changes require independent assertions against
real libraries. Published-result changes also require [release-specific scientific correction notes](../releases/v3.0.0.md#scientific-corrections).
UI tests run hidden and assess state, geometry and rendering assertions. An unavailable quiet check
is unverified, not passed.

Frozen paths are [`viewer/protocol.ts`](../../desktop/src/renderer/viewer/protocol.ts),
[`tit-bridge.d.ts`](../../desktop/src/shared/tit-bridge.d.ts) and [`contracts/`](../../contracts/).
Changes require this contract and a decision entry. Optional additions preserve prior behavior when
absent. This review requirement does not imply that every platform or runtime gate is automated.

## 6. Project overview, batch execution, the shared terminal, the guide and the Viewer

**Overview is an aggregate, not a client fan-out.** `GET /api/catalog/overview` supplies project-wide
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

The Viewer has Menu and Tetravox subroutes within one retained page. Open resolves the editable
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

### 7.2 The run-page panes are our own WebGL2 renderer

[`scene/`](../../desktop/src/renderer/scene/) renders surfaces, screen-space markers and atlas
selection without an iframe or a second graphics dependency. Guide labels align with their geometry.
A triangle's majority region label controls flat shading and picking; rotating its vertices preserves
winding and prevents the provoking vertex from assigning a minority label. Triple junctions retain
their original ordering.

Electrode color expresses availability and channel membership, with no additional selection ring.
The form, channel legend and preview share one palette and one selection model. Atlas clicks and ROI
chips edit the same region list. Coordinate picking remains constrained by §3.

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

Set selection uses the shared list/picker: plain click, range selection, modifier toggle, filtered
All/None and preserved selection order. Unavailable rows remain visible with their reason and cannot
enter a run through bulk selection. Participant row lists preserve repeats needed by paired studies.
The detailed grammar belongs to [DESIGN.md](DESIGN.md) §4.8.

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
[RELEASE.md](RELEASE.md).

Sources: [`tit/pre/qsi/`](../../tit/pre/qsi/), [`structural.py`](../../tit/pre/structural.py),
[`GQI scalar spec`](../../resources/qsirecon_pipelines/dsi_studio_gqi_scalar.yaml).

## 10. Internal builds and public availability

Internal builds and public releases use the same product and packaging pipeline. An internal cohort
records its source revision and immutable image identity; launchers and installers resolve the same
image. An explicit image request retains mismatch protection. Publishing a container or preparing
an internal build does not create a public release, move `latest` or rewrite stable announcement
metadata. [RELEASE.md](RELEASE.md) owns distribution procedures and current availability.

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
Submission routes enforce project permission before single jobs, groups, pipelines or reruns create
jobs. Simulation overwrite intent reaches the subprocess and native SimNIBS session; ordinary runs
retain native existence protection. Caller environment variables cannot supply permission.

Sources: [`overwrite_policy.py`](../../tit/server/overwrite_policy.py),
[`ExistingOutputsDialog.tsx`](../../desktop/src/renderer/pages/_shared/run/ExistingOutputsDialog.tsx),
[`JobDetailPane.tsx`](../../desktop/src/renderer/app/jobs-rail/JobDetailPane.tsx).
