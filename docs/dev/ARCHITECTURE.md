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

A request value that names a subject or an on-disk entity is validated by pydantic before a route
runs (`tit.server.schemas.SubjectId` / `EntityName`); `PathManager` joins every user name through
`tit.paths.resolve_under`, and a read, listing or write at a jail boundary goes through
`resolve_within` / `resolve_leaf_within` and uses the path they return. The contract, and the
shapes CodeQL recognises, are in
[`dev/security/SECURITY_MASTER_DOCUMENT.md`](../../dev/security/SECURITY_MASTER_DOCUMENT.md#the-path-sanitizer-contract-v3) (ADR 33).

The core container has no Qt GUI, X11 display or FreeSurfer installation. Dedicated viewing uses
native TetraVox on the host GPU; surface run previews use the application's WebGL2 renderer and volumetric previews open in TetraVox (§7).
Dependency versions belong in the package manifests, lockfile and container blueprint, not prose
copies. Replacing these boundaries or adding a dependency is an architecture decision.

### Optional FreeSurfer preprocessing

FastSurfer remains the default. Explicit FreeSurfer jobs run recon-all and/or T1 thalamic
and hippocampal/amygdala subregions in disposable sibling containers. Subregions require a
completed FreeSurfer reconstruction; FastSurfer segmentation-only output is insufficient.
Workers bind the selected project, retain results under `derivatives/freesurfer`, share the
job resource budget and cancellation lifecycle, and use no named data volume. The image may
remain cached; the worker and temporary license mount are removed after execution.

**TI-Toolbox supplies its bundled FreeSurfer license automatically.** Users must never be asked
to register, bring a personal license or paste a key into Settings. FreeSurfer, QSIPrep and
QSIRecon share the packaged license resolver and stage the resolved file for their runtime.
The fallback resource is `tit/resources/freesurfer/license.txt`, shipped with upstream terms.
Existing environment, stored-user and system-file overrides remain optional compatibility inputs;
the packaged license makes a clean installation usable without them. A missing bundled resource
is an installation error to repair, never a reason to request a user's license. FastSurfer
segmentation remains license-independent. This restores the v2 provisioning policy (DECISIONS,
2026-09-20).

### Launch modes

There is one launch model, and the desktop application is it. `loader.py` (implementation
`tit/cli.py`) and Python-free `loader.sh` bootstrap that app: they resolve
`TIT_ELECTRON_EXECUTABLE`, then a managed install under the per-user data directory, then download
and checksum-verify the release asset for the platform, and start it before Docker. Any failure
prints one reason and falls back to the browser; `--desktop` makes that failure an error instead,
and `--browser` or `--no-open` skips the download. Both loaders keep the resolution in one function
named `resolve_desktop_executable`, and `--print-config` reports the outcome as
`desktop_executable` without touching the network. `--dev [DIR]` (equivalently
`TIT_DEV_REPO_DIR`, or `TIT_DEV=1`) switches only the *source* of the server and renderer: the
checkout — the one the loader itself lives in when no `DIR` is given — is bind-mounted at
`/ti-toolbox`, the server reloads, and its built renderer is served. A missing or stale
`desktop/out` is built by the loader itself (`ensure_dev_bundle`, `npm ci` first when
`desktop/node_modules` is absent; `TIT_DEV_NO_BUILD=1` opts out). It
does **not** change the UI — a checkout opens the same Electron window a user gets, taking
Electron from `desktop/node_modules` and, when that is absent, the installed desktop app with
`TIT_DEV_REPO_DIR` set (`dev/launch-electron.sh` prints the `npm ci && npm run build` line it
would have preferred). Only `--browser` and `--no-open` select the browser.
Flags, port selection, container naming/hash, attach/recreate and stop semantics are identical in
both modes, so every entry point can attach to and stop the same container. `--print-config` output is byte-identical between `loader.sh` and `loader.py`.
Standalone downloads keep the loader and `docker-compose.yml` together. Regular users need no checkout.
There are exactly two entry points, `loader.sh` and `loader.py`; no developer-only wrapper exists
(removed 2026-09-17). Either can live outside the source tree: `--dev DIR` or `TIT_DEV_REPO_DIR`
selects the checkout, independently of the project data path. On WSL2 a Windows `--project` path
(`C:\Users\me\project`) is translated to its `/mnt/c/...` spelling by both loaders
(`tit/launch.py::translate_project_path`); macOS and Linux are untouched. WSL2 is a Windows host
to both loaders (`is_wsl`, decided from `WSL_DISTRO_NAME`/`WSL_INTEROP`, never the kernel string,
which a Docker Desktop container shares): the Linux AppImage cannot run there, so the default UI is
the browser, the session URL is opened on the Windows side (`wslview`, then PowerShell, then
`cmd.exe`) and printed regardless, nothing is downloaded, and `--desktop` is refused with a reason
naming the Windows installer. An adjacent YAML or explicit
`TIT_COMPOSE_FILE` selects the launch specification. Python bootstraps its
launcher in a cache from the matching release branch and forwards the adjacent YAML via
`TIT_COMPOSE_FILE`; an invalid explicit path fails rather than selecting a different configuration.
Explicit browser/headless modes and development wrappers use the same Compose service and
container identity. All Docker launch paths require an explicit Attach or Replace decision when
any TI-Toolbox container is running, including another project's session. Multiple sessions require
selection; only that selected session may be replaced. Attach keeps its actual project and image;
Replace uses the requested project and YAML. This prevents accidental reuse or job interruption.

Electron owns its started or explicitly adopted Docker session. Closing the window or choosing Quit stops/removes that session and exits Electron.
Overview embeds the project path and folder picker when disconnected, served locally without
backend queries. The full labeled navigation is visible, with project tools disabled until connected.
Switch project first collects a new directory inline. Native confirmation grants the new host
mount and warns that jobs stop; the app validates the destination and Compose plan before
shutdown, then starts the new session and reloads its data. Cancel or an invalid destination retains
the current session; a failure after shutdown returns to welcome with a visible error. Named volumes
and project files survive session shutdown. Only running and queued jobs count as active;
shutdown errors cannot silently approve closure. Manually connected remote servers are not adopted
as local Docker sessions. Browser-only development remains persistent until
explicitly stopped. Development mounts the launched checkout; explicit `--host` runs the API
locally and stops it on exit. Host-only execution is not an image acceptance test.

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

Generated configuration schemas omit machine-dependent default values. QSI OpenMP thread fields
remain optional; omitting them resolves the existing host-dependent runtime default, while an
explicit value is preserved. A producer machine's CPU count must not become a wire-contract
constant. Desktop preprocessing continues to send resolved user resource preferences.

The verification procedure is [TESTING.md](TESTING.md). Host tests with mocked heavy
libraries do not prove numerical correctness; science changes require independent assertions against
real libraries. Published-result changes also require [release-specific scientific correction notes](../releases/v3.0.0.md#scientific-corrections).
UI tests run hidden and assess state, geometry and rendering assertions. An unavailable quiet check
is unverified, not passed.

Frozen paths are [`tit-bridge.d.ts`](../../desktop/src/shared/tit-bridge.d.ts) and [`contracts/`](../../contracts/).
The preload bridge has 23 top-level entries, enforced by `desktop/tests/e2e/smoke.spec.ts`;
`saveNativeTetravoxScene` adds native snapshot saving; `onNotificationSound` lets main have the
window play a job banner's TI-Toolbox sound. Changes require this contract and a decision entry. Optional additions preserve prior behavior when
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
**One job per product runs at a time**: `tit.jobs.scheduler.PRODUCT_OF` maps kinds to Preprocessing
(`pre`), Simulator (`sim`), Optimizer (`flex*`, `ex`, `mex`, `leadfield`) and Analyzer (`analyzer`),
and a job of a product waits while another job of that product runs, whether it came from the same
group or a separate submission; other kinds are bounded by locks and the CPU budget only. There is
no concurrency setting: the retired `parallel_subjects` request field and `JobSpec.group_cap` are
ignored if an older client or `spec.json` still carries them. Parallelism inside a job is the job's
own (worker pools under the global CPU limit). Excluded alternative: a user-set per-group cap — it let
several FEM-class jobs of one product contend for the same machine. Cohort analyses remain single
jobs. Sources: [`jobs routes`](../../tit/server/routes/jobs.py),
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
as host-addressed native scene data. Selection-only links prepare the Viewer; explicit Open in viewer actions load the selected artifact. Optional atlas selection retains the server default when absent or unavailable. See §7.1.

Completed job logs use an authoritative final event snapshot after the worker exits and its event
tail is drained. Live subscriptions resume from the next sequence and are reference-counted
across views; a closed terminal view cannot consume delayed replay as new output.

## 7. The viewer, the run-page renderer and the selection grammar

### 7.1 TI-Toolbox's own TetraVox is the only one it launches

TI-Toolbox installs its own TetraVox under its user-data runtime directory
(`runtimes/tetravox-<platform>-<arch>`) and launches nothing else: no application in a system
location, on PATH, or chosen through a picker is ever consulted (decision 2026-09-22). Each ordinary
desktop launch checks that directory without blocking the UI; an existing copy needs no network. When
none exists, setup asks GitHub for the newest TetraVox release, downloads the official package for
this platform — macOS arm64/x64 zip, Linux x64 tarball, Windows x64 zip — verifies it against the
SHA-256 digest GitHub publishes for that asset, unpacks it in a private staging directory (`ditto`
on macOS, `tar` elsewhere; Windows ships bsdtar), confirms the unpacked application's identity and
version, and renames it into place without administrator privileges. Startup, an explicit retry and
a Results open share one in-flight setup. No viewer window opens just because TI started. Errors
remain retryable while TI stays usable. Automated app sessions do not perform ambient downloads.

**TI owns updates.** Settings ▸ Viewer checks the newest release on open (and on **Check for
updates**), shows it beside the installed version, and its **Update to X** replaces the copy with that
release the same way, into a fresh directory swapped over the old one; it is refused while TI's viewer
is open, and a release already installed downloads nothing. "Open" means TI's managed executable or
any process in TI's viewer profile — a TetraVox the user installed neither blocks Update nor counts as
TI's viewer. The viewer is launched with `TETRAVOX_MANAGED_BY=TI-Toolbox` (the name its popup shows) and
`TETRAVOX_MANAGED_UPDATE_REQUEST=<userData>/tetravox-update-request.json` (decision 2026-09-22):
a TetraVox with the handshake keeps its own launch check and native **Software Update** popup, and
the popup is the consent. On **Update to X** it asks about unsaved edits, writes
`{protocol: 1, action: "update", id, version, current}` to that path (temporary file renamed into
place), and waits up to 15 s for `<path>.receipt.json` carrying the same id. TI polls the path with
`fs.watchFile` (1 s; the same on macOS, Linux and Windows, no URL scheme or file association),
consumes the request, answers `{protocol: 1, id, ok}`, waits up to 60 s for TI's viewer to quit (the
viewer quits on the receipt), runs the same verified update as Settings, and relaunches the viewer
with the last scene TI opened when it is still inside the active project — also after a failed
update, whose reason TI shows in a dialog. The request names no URL or path; TI installs the newest
release it verifies itself. No receipt within 15 s (TI not running, or a TI without the handshake)
withdraws the request and TetraVox stays open with an error. "Skip This Version" is TetraVox's
per-version skip, stored in TI's viewer profile. A TetraVox without the handshake ignores the second
variable and keeps its updater off; Settings' Update still works. On Linux the viewer is launched
with `--no-sandbox`, because the tarball's
`chrome-sandbox` cannot be made setuid-root by a user install. Earlier version-addressed
directories and a swap's `.previous` directory still identify as installed, so an upgrade of
TI-Toolbox never loses a working viewer. Version display is informational; minimum scene support
does not reject future majors. TI's copy always runs in its own profile
(`--user-data-dir=<userData>/tetravox-profile`), never Electron's default one, so it shares neither
settings nor the single-instance lock with a TetraVox the user installed, and with its own
TetraVox home (`TETRAVOX_HOME=<userData>/tetravox-home`, created if missing), so it shares neither
the rc file nor installed extensions in the user's `~/.tetravox`; `--user-data-dir` does not move
that directory. Plate captures and saved-scene previews use a throwaway profile with a
`tetravox-home` inside it. Nothing of TI's viewer is shared with a user's own TetraVox. Scenes reach
TetraVox only through TI's copy: `openPath` refuses `.tetravox.json`.

The Viewer page and Results actions build native `.tetravox.json` scenes. Main maps and validates the
scene against the active project's real path before launch and revalidates after confirmation. Dataset
paths are host-addressed; reference assets are staged into the project when needed. Export creates a
native copy without overwriting the saved source. A remote project without local filesystem access
cannot be opened natively; a downloaded scene JSON does not include its referenced datasets.

The TetraVox scene API is caller-independent: TI supplies the canonical project output path and an
optional expected attached scene path. TetraVox imposes no TI directory structure, session nonce, naming
convention, or native Save As default. The project policy remains in TI's main process and server.

TetraVox owns camera, layer editing, dialogs and scene serialization. **Saved scenes ▸ Save scene**
requests the live native serializer, then writes a new `.tetravox.json` under the active project's
`code/ti-toolbox/viewer/scenes/`. It captures the currently active TetraVox scene, including files
opened directly in that app, without requiring a prior TI open or matching its previous attachment.
Saving requires a running TetraVox process before requesting capture.
Visible saved-scene rows may request a cached sibling PNG through a jailed native preview IPC.
TetraVox's isolated offscreen job restores the saved scene's grid; a serial bounded queue avoids
competing capture jobs. Preview failure never prevents saving or opening. Inline scene information
uses actual dataset/layer counts and filesystem modification time; creation is shown only when a
filesystem birth time exists, never inferred from ctime.

Native saved scenes reopen at their original project path so scene-relative datasets retain their
anchor; only legacy server-URL scenes are exported into a localized copy.
Existing files are never overwritten. The builder recipe is not a
fallback: it cannot contain edits made in the native window. The optional `supportsSceneSave` capability
is false when absent; Save stays unavailable until a capable native app is selected. A correlated,
validated native receipt and destination path are required before TI claims a save or refreshes the list.
The builder's Save selection and Recent controls are removed; its file-list Reset remains. Installation under the TI user directory is
not a filesystem sandbox. Existing standalone installations retain their updater ownership and profile.

Scene handoffs serialize and require confirmation when a scene might replace an existing view or
process inspection is unavailable. Cancellation launches nothing. Blank launches only open/focus the
app. macOS scene launches explicitly request reopen/activation through the selected app bundle after
queueing the file; this avoids relying on file-open alone to reveal a minimized window. A successful
legacy request returns `launch-requested`: process handoff does not prove the scene loaded
or the OS granted foreground activation. A capable native app exchanges versioned requests and
receipts through a private per-user temporary directory rather than an unauthenticated listener.
Request IDs correlate replies; stale receipts cannot satisfy a later request, repeated dispatch is
serialized, and cancellation or unknown busy/unsaved state cannot discard user work. A minimized
window is restored and an upstream process with no window recreates one before accepting a request.

The Viewer remains one bounded workspace: independently scrolling builder on the left, launch and
saved-scene library on the right. Deletion removes no dataset; scene health describes reference
availability rather than numerical validity. External references are not probed by the server.

**Release boundary:** verified initial setup is currently wired for macOS archives. Linux tar installs
remain discoverable but are not automatically downloaded because their native updater is notify-only.
Windows automatic setup awaits an updater-compatible per-user package that cannot replace another
installation. Existing installations can still be located on both platforms. These are outstanding
implementation/platform gates, not a reduction of the requested three-platform release scope. Local
unit checks do not prove signing, native updates, scene rendering or OS foreground behavior.

Acknowledged live-scene requests and native no-window recovery are implemented in TetraVox PR #44.
The [upstream integration record](../../dev/upstream/tetravox-live-scene/README.md) identifies that
generic API and TI's adapter boundary; verification evidence is in TESTING and outstanding release
acceptance is in ROADMAP. Installed builds without `sceneApiProtocol: 1` cannot use TI live saving;
the capability becomes available when a compatible TetraVox package is installed.

Official-release acceptance remains a real package matrix: macOS arm64 and x64, Windows x64, and
Linux x64 under Wayland and X11. Each leg covers clean setup, reuse and native-owned update/relaunch;
closed, minimized and no-window handoff; paths with spaces and non-ASCII characters; preservation of
busy/unsaved work; and isolation from a second installation. Linux adds no display server, and OS
foreground restrictions may yield activation/attention feedback rather than unconditional focus.
Sources: [`native setup`](../../desktop/src/main/tetravoxNative.ts),
[`handoff`](../../desktop/src/main/viewerHandoff.ts),
[`native scene bridge`](../../desktop/src/main/nativeSceneBridge.ts),
[`scene export`](../../tit/server/routes/viewers.py), and
[`saved-scene library`](../../tit/server/routes/viewer_library.py).

### 7.2 Run-page surface selection and volumetric previews

[`scene/`](../../desktop/src/renderer/scene/) renders surfaces, screen-space markers and atlas
selection without an iframe or a second graphics dependency. Guide labels align with their geometry.
A triangle's majority region label controls flat shading and picking; rotating its vertices preserves
winding and prevents the provoking vertex from assigning a minority label. Triple junctions retain
their original ordering.

Electrode color expresses availability and channel membership, with no additional selection ring.
The form, channel legend and preview share one palette and one selection model. Atlas clicks and ROI
chips edit the same region list. Coordinate picking remains constrained by §3.

Optimizer and Analyzer select cortical and subcortical atlas regions on precomputed, packaged
Ernie reference anatomy, including translucent skin. The scene atlas selector and target form share
atlas/mode/region state; switching atlas clears incompatible labels. Subcortical targets default to
`labeling.nii.gz`; its build-time label filter excludes background, CSF, ventricles and other
non-subcortical compartments. No subject atlas extraction runs when browsing these guides.
Only the selected atlas surface and skin are fetched. Guide coordinates never become scientific
coordinates. Masks, spheres and saved coordinate targets retain explicit native TetraVox inspection.
Simulator also uses the guide for named montage browsing; actual freehand/XYZ placements and snap
displacements retain subject geometry to preserve their coordinate meaning. Peeling and isolation
controls are omitted. `POST /api/scene/target-preview` remains the explicit native volume path.

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

### 7.3 Pipeline canvas (removed)

The graphical pipeline feature was removed on 2026-09-13. Dedicated processing pages submit
existing jobs and job groups; standalone Notebooks remain available for scripted workflows.
This section number is reserved. See the removal decision in [DECISIONS.md](DECISIONS.md).

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

New Simulator jobs opt into MNI NIfTI export separately from fsaverage mapping, with adjacent
controls. The MNI flag gates both anatomical and field conversion to avoid unwanted registration
work. Ex previews count the engine’s electrode arrangements and valid current splits separately;
total iterations are their product, including one split for fixed balanced currents.
Flex exposes Mean TImax, Max TImax (ROI 99.9th percentile), Threshold-free focality and
Threshold-based focality. The latter retains fixed, adaptive and multi-threshold execution;
“Multi-threshold” is a presentation label for the existing `pareto` strategy, not a new objective.

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

Unsigned builds and public releases use the same executable packaging pipeline. Docker image
construction, scientific acceptance and push are manual; executable CI only checks published image
manifest availability for Linux amd64. That check does not establish exact source provenance or
runtime behavior. Neither executable mode changes Docker tags. Release recovery may use newer
workflow control code but must package the existing immutable release tag's source SHA and attach
assets to that tag. Public releases cannot be overwritten by recovery.

Internal builds and public releases use the same product. An internal cohort
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

Daily CircleCI verifies all host Python and desktop static/unit regressions plus production build;
it does not run scientific-image tests or Electron E2E. Official release acceptance additionally
requires the serial local gate in [TESTING](TESTING.md#daily-ci-and-the-local-release-gate), including
real-library numerical tests, hidden E2E, applicable completed real workflows, the example notebook
and package inspection. Candidate SHA/image identity and per-stage logs must accompany that evidence.
A failed or inconclusive stage cannot be called passed; daily green status alone cannot establish
release readiness. Publication remains a separate operator action, with platform acceptance intact.

### Terminal launcher setup

Terminal setup starts the desktop app; `--browser` selects a browser session, which is also the
fallback when the app cannot be resolved, and which asks for the project. Container discovery
must precede any automatic reuse. Attach/Replace/Cancel is explicit; noninteractive invocation
requires an explicit decision and, when ambiguous, a container identifier. Missing or cancelled
input launches nothing. Selected existing project/image information must remain visible.

Mounted development uses the launched checkout for Python and UI when creating a new session.
Choosing Attach intentionally uses the selected session unchanged; an incompatible legacy server
must fail clearly without replacement. Configuration mismatches no longer authorize automatic idle
recreation. See [TESTING.md](TESTING.md#launcher-lifecycle-checks) for executable lifecycle coverage.

### Extension run panes and export selection

Extensions retain returned job IDs and share the live terminal beneath a bounded plan. Export previews
follow their selected subject and configuration; volume inspection opens explicitly in native TetraVox. Preview geometry is context, not proof that export computation completed.
Participant CSV/TSV import validates all rows before replacing any; exports use the existing host
save-file bridge or browser download.

### Overwrite permission

Existing outputs require a fresh UI choice, including Rerun; old confirmation state and saved
config flags confer no authority. The shared dialog offers Skip, Replace and rerun, or Cancel --
"Replace and rerun" is the one control for replacing outputs, always available (no separate
project setting gates it). Skip states whether new jobs will run; job Rerun Skip queues nothing.
Submission routes still require explicit `overwrite`/`replace_existing_outputs` confirmation
before single jobs, groups or reruns replace existing outputs (409 pending that confirmation).
A run page treats that 409 as the existing-outputs question, not an error, so the dialog opens even
when its cached plan lagged the disk; Skip submits only the jobs a freshly fetched plan calls new.
Simulation overwrite intent reaches the subprocess and native SimNIBS session; ordinary runs
retain native existence protection. Caller environment variables cannot supply permission.

Sources: [`overwrite_policy.py`](../../tit/server/overwrite_policy.py),
[`ExistingOutputsDialog.tsx`](../../desktop/src/renderer/pages/_shared/run/ExistingOutputsDialog.tsx),
[`JobDetailPane.tsx`](../../desktop/src/renderer/app/jobs-rail/JobDetailPane.tsx).

### Missing inputs are refused at submission

A job is never queued when a file it needs is not on disk. `POST /api/jobs` and
`POST /api/jobs/groups` run `tit.jobs.preflight.preflight(kind, config, project_dir)` after the
config-shape check and before any job record exists; a non-empty result is HTTP 422
`{detail: "Missing inputs", missing: [{what, expected_path, how_to_fix}]}`, and
`POST /api/jobs/preflight` returns the same list without submitting. The sweep is one small
checker per kind, filesystem existence and name-correctness only (no SimNIBS import, no mesh or
volume loaded), built on `PathManager` and the runner's own resolution rules so the two cannot
disagree: the analyzer's `select_field_file` and `Analyzer._SURFACE_ATLAS_VOLUMES` (a voxel
analysis of the surface atlas id `DK40` needs FastSurfer's DKT volume; the mesh analysis needs no
parcellation), the flex mapping-net rule, `ExConfig`'s `.csv` suffixing, the stats/nilearn MNI
NIfTI patterns, `tit.pre.preflight` for preprocessing. Each finding names the input, the exact
path it was expected at and what produces it ("run FastSurfer for sub-101", "run the L_Insula
simulation first", "analyze in mesh space instead"). A `pre` group is checked with the whole
group's flags, not per stage, because an early stage supplies what a later one needs. The
desktop turns the body into one persistent notice, one line per input (`notifySubmitError`,
`notify.blocked`); `ApiError.missing` carries the list. Kinds with nothing on disk to check
(`project_init`, `report`, `tools`, whose arguments are jailed separately) return nothing.

Sources: [`preflight.py`](../../tit/jobs/preflight.py), [`jobs.py`](../../tit/server/routes/jobs.py),
[`client.ts`](../../desktop/src/renderer/api/client.ts), [`Toast.tsx`](../../desktop/src/renderer/ui/Toast.tsx).

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

The run shape's split is sized in pixels of its own box, not the window: the work pane (the Jobs
table) stays between 640 px (the measured width at which no Jobs table truncates) and 800 px, the
Terminal/Scene pane gets at least 400 px and the rest, and the 6 px handle sits between them.
`runPaneLimits` in `paneState.ts` owns the numbers; the drag (both the controlled separator and the
controller-less handle) clamps with it, and `PageLayout` exposes the same values as custom
properties that the stylesheet's `min-width`/`max-width` read, so a remembered width is re-clamped
on load and on every window resize while the preference itself is kept. Below a 1140 px window
(`@media (max-width: 1139px)`, pinned to the constants by `tests/unit/pane-state.test.ts`) the
panes stack instead. Expand gives the pane the whole box and hides the work pane until Esc or
restore; collapse hides the pane behind a 16 px rail. The Terminal does not wrap; long lines
scroll sideways. Results' preview and Jobs' detail column keep a 320 px floor and a 70 vw ceiling.

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

Resource and duration figures are the run's own. CPU counts come from
[`tit/cpu.py`](../../tit/cpu.py) — the container's cgroup/cpuset limit, not the host's core count —
and the job runner exports the admitted budget as `TIT_JOB_CPUS` alongside the OpenMP/MKL/Numba
thread variables, which every "use all cores" default reads, so the panel's CPU figure is the
number the solver receives.

**The global CPU limit is the scheduler's CPU budget.** `tit.cpu.cpu_limit()` =
`max(1, floor(percent / 100 × effective_cpus()))`, where the percent is the user-wide
`cpu-limit.json` in `PathManager.user_config_dir()` written by Settings → Project → Execution →
**CPU limit** (`GET/PUT /api/cpu-limit`, 10–100 %), else **70 %**. That file is the only source —
there is no environment override, so the UI and every script always agree.
`scheduler.discover_budget()` takes its CPUs from it, and `JobManager` re-reads it at every admission
pass, so a change applies to the next admitted job while running jobs keep their CPUs; a queued job
costed above a lowered limit has its claim shrunk to the limit instead of waiting forever. Every
"all cores" default resolves to it: `n_jobs < 1` for `ex`/`mex`/`stats` (cost and
`tit.cpu.resolve_n_jobs`), flex's `cpus=None`, pre-processing tool threads
(`surfer_settings.available_threads`) and NIfTI conversion workers; outside a job `job_cpus()` falls
back to it. Explicit per-job values (`n_jobs`, `cpus`, tool threads) remain an API override but are
clamped to the limit, since a claim above the budget could never be admitted. Exhaustive-search
workers share the job's budget with numba: `workers × numba threads ≤ TIT_JOB_CPUS`. RAM is not
limited by it: the budget's memory is the container limit clamped by available memory. Excluded
alternative: only per-page or per-job thread controls — they cannot stop two jobs together from
taking the whole machine. The global CPU limit is the only resource setting. The duration tile is an estimate from the per-kind models documented in
[`tit/jobs/eta.py`](../../tit/jobs/eta.py), calibrated against [BENCHMARKS](BENCHMARKS.md); it is
labelled `≈` with its basis in the tooltip, and a kind with no measured baseline shows no number.

The Viewer Menu's subject/space tree and editable composition share selection. Meshes, surfaces,
volumes and attachments retain server-classified kinds, filenames and size. Native TetraVox owns
camera/layer controls. TI reports installation and launch errors; opening Settings checks the local
managed installation without fetching a release index. Project overwrite permission is separate
from machine preferences. See §7.1 for the native scene handoff boundary.

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


### Terminal container prompt

Interactive terminal prompts list TI-Toolbox image references (repository and version), numbered when selection
is needed. Recreate is the default accepted by Enter; Attach is the second choice. EOF, Ctrl-C and
invalid answers do not authorize replacement. Noninteractive launches still require explicit flags.
A short line states that recreation stops the selected container and its jobs, without exposing
Docker IDs, generated container names or YAML paths in the choice UI.

Default `npm run dev` builds and opens the same welcome Overview as desktop users; it waits for
project selection before starting Docker. `dev:web` retains Vite hot reload. The connected page
may invoke a native project picker, but arbitrary `stack.start` stays restricted to the local
origin; switching destinations requires native confirmation.

## 12. Optional native FastSurfer

An explicitly approved Apple Silicon desktop session can install FastSurfer in the app's user-data `runtimes` directory. The installer pins and verifies the upstream source, bootstrap tool and checkpoints, uses upstream pinned Python requirements, and checks MPS availability before marking the runtime ready. No global Python or administrator installation is used.

The Docker job server remains the owner of scheduling, project locks and derived outputs. A session-specific mailbox within the verified mounted project transports only a subject, relative input and thread count to the host. No executable, environment or output path comes from a request. The host runs the fixed segmentation workflow with MPS inference and CPU aggregation. A macOS sandbox confines data access to the project and runtime/system dependencies, writes to job output/mailbox/temporary paths, and denies networking.

The Settings explanation is the single explicit Apple GPU consent dialog; the main process validates the sender and active local project before installation. Apple GPU consent is a persistent user preference in the desktop user settings. On a verified local connection, an enabled preference resumes an already-installed runtime for that project. Switching or quitting stops the worker without clearing the preference; disabling clears it. Each worker remains scoped to its active project. Missing or broken installations require explicit setup again rather than background downloads. Host and requester heartbeats prevent a crashed client from leaving orphan computation. Auto selection first probes actual CUDA computation in the container, then uses an enabled native mailbox, then logs a CPU fallback. An explicit device override is respected; a stale mailbox fails visibly rather than silently selecting CPU. Remote connections and browser-only launchers do not install or invoke a local runtime.

Verification: [native FastSurfer acceptance](TESTING.md#native-fastsurfer-acceptance).

The image ships CUDA 12.6-enabled PyTorch 2.7.1 and its user-space runtime. Host NVIDIA drivers and Docker GPU integration remain host prerequisites. Launchers probe GPU computation in a temporary, mount-free container before requesting GPUs on the project container. CPU-only hosts can still launch. Verification: [GPU-preferred container acceptance](TESTING.md#gpu-preferred-container-acceptance).

FastSurfer and FreeSurfer thread preferences live in the shared user configuration, not project settings. Automatic defaults use the whole global CPU limit (above), at least one, respecting container limits; explicit values are clamped to it. Plans and new jobs resolve these defaults consistently; explicit scripting overrides remain available. The Pre-processing UI routes users to Settings → Pre-processing and does not keep per-project thread overrides.


Settings groups project preferences, preprocessing defaults, extensions, viewer management, and server details into horizontal tabs. Inactive panels retain unsaved drafts. The preprocessing page selects stages; FreeSurfer operation defaults and reconstruction/QSI resources are edited in Settings and resolved into each submitted configuration.


## 13. Optimizer candidate records and replay

Flex writes valid evaluation metrics to `candidates.csv`, electrode poses to
`candidate_geometry.jsonl`, and configuration/metric definitions to `candidate_manifest.json`.
Restart records survive final-result promotion. New records include a head-mesh content digest and effective solver settings. Replay checks the digest on selection and again at execution; older records explicitly lack this verification. MATLAB export is omitted for callable or ratio goals because it cannot preserve their scoring function. Only finite, field-valid evaluations may become winners or replayable records; an all-invalid history fails rather than promoting a penalty. Scalar and interval mutation settings both reach the installed optimizer in its accepted tuple form. Records carry stable IDs; missing or invalid geometry
cannot become a simulation. Read-only catalog endpoints constrain paths to the project and paginate
results. Raw objectives with different definitions are not compared as a common frontier.

Simulator montages may carry subject-space `electrode_poses` and source `provenance`. Poses preserve
centre, electrode y-direction, signed currents, shape, dimensions and layer thickness with a validated
orthonormal frame; the replayed layout includes configured gel plus the 2 mm rubber layer. Unequal-axis
ellipses are rejected explicitly until true ellipse support exists rather than silently becoming an
average-radius circle. Legacy montages remain valid without replay metadata. The normal simulation
configuration remains authoritative. Changing the montage or subject clears exact-replay metadata;
edits to scientific settings invalidate the source estimates. Native viewer handoff and analysis
continue through their existing project workflows.

Candidate cap placement resolves the selected history record through
`GET /api/catalog/optimization-candidates/{candidate_id}/mapping`, scoped to its subject, run and
project-confined cap data. It does not modify recorded history or substitute the run winner.
Simulator retains the original configuration for reversible placement selection and blocks submission
while mapping is pending; cap mode removes optimized poses so labels determine placement. Preview
annotations use the same ordered pairs and subject-space cap coordinates, never reference-guide
coordinates. Displacement distances are Euclidean millimetres, not travel along the scalp.

Flex jobs resolve the TI-Toolbox integration from `resources/map-electrodes` relative to the
running Python package, once per process. This keeps a developer checkout and its integration in
sync without modifying installed SimNIBS or recreating Docker. Source-load failures remain errors;
only installations without that resource fall back to the image's integration and its capability
check. Ratio postprocessing uses the same resolved module.

Flex exposes Mean TImax (ROI arithmetic mean), Max TImax (ROI 99.9th percentile), and
Focality (mean ROI TImax raised to `1 + intensity_weight`, divided by mean non-ROI TImax),
with `intensity_weight` constrained to [0, 1]. Weight zero is a pure ratio; larger weights favor ROI
intensity while retaining the non-ROI penalty. Candidate manifests distinguish this mean-denominator
definition from historical p95 objectives so old scores cannot silently acquire a new scientific
meaning. Intensity-only runs may opt into target-complement observation metrics over eligible GM;
those measurements record domain, tissue, resolution, weighting and envelope, remain distinct from
explicit avoidance regions, and do not alter the objective, valid-candidate set, chosen current split
or FEM solve count. Empty or nonfinite background observations remain missing with diagnostics.

Candidate review links table rows, scatter points and the existing subject-space montage renderer
through a single selection. Plot history is independent of table pagination; a plot selection
reveals the corresponding row. Responsive columns use the preview pane width. Missing metrics,
incompatible definitions and loading limits stay visible; the frontier is only over recorded
comparable candidates. No new 2D coordinate projection or visualization dependency is introduced.

The candidate plot loads at most 10,000 records in the selected sort order, using abortable
500-record requests and an O(n log n) frontier calculation. The limit is displayed and does
not limit table pagination or recorded files. This bounds client geometry/SVG work without
silently presenting a page-local plot as a complete history.
