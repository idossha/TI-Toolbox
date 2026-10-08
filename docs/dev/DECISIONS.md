# Decisions and development history

[ARCHITECTURE.md](ARCHITECTURE.md) defines current behavior; this record explains consequential
choices, reversals and development milestones. [Interface design](ARCHITECTURE.md#11-interface-design) owns UI details, [BENCHMARKS.md](BENCHMARKS.md)
owns performance measurements, and [ROADMAP.md](ROADMAP.md) owns outstanding work.

This combined record was condensed on 2026-09-09. The numbered decisions explain why;
the milestone section records what shipped. Citations that once named `HISTORY.md` point here; detailed
retired program specifications remain in Git history. Git history retains full earlier narratives. Add an entry
for a meaningful decision or milestone, not each fix or test run. Record **Decision / Why / Cost /
Revisit if**; mark reversals explicitly and update the current contract with them.

## The numbered ADR index

“ADR row N” in code refers to these stable identities. Do not renumber them. The compact
rationale below consolidates later amendments without treating superseded designs as current.

| # | Date | Decision | Status |
|---|---|---|---|
| 1 | 2026-08-27 | Bridge is a Python job server (`tit.server`, FastAPI) in the container; Electron is a thin shell | live |
| 2 | 2026-08-27 | UI served by `tit.server`; Electron `loadURL`s `127.0.0.1:<port>`; `?token=` exchanged once for a cookie | live |
| 3 | 2026-08-27 | Freeview and Gmsh stay in the container on X11 for 3.0 | superseded by 15, then 21 |
| 4 | 2026-08-27 | An internal viewer is a separate later track over the same ViewSpec | superseded by 15 |
| 5 | 2026-08-27 | New `desktop/` for v3; legacy `package/` untouched until Phase 6 | Phase 6 done 2026-09-07 |
| 6 | 2026-08-27 | React 18 + Vite + TypeScript strict + Tailwind + react-hook-form/ajv; TanStack Query; Zustand | live |
| 7 | 2026-08-27 | Contract-first: hand-authored OpenAPI, server dump must diff clean, TS types generated | live |
| 8 | 2026-08-27 | Optional panels in 3.0; 3D Visual Exporter and Electrode Placement to 3.1 | placement landed in Simulator; exporter subsequently implemented |
| 9 | 2026-08-27 | `loader.py` shrinks to a wrapper sharing Electron's env computation | live |
| 10 | 2026-08-27 | Windows: unsigned NSIS, no `electron-updater` in 3.0 | live |
| 11 | 2026-08-27 | Per-project compose stacks; docker socket stays mounted; per-subject QSIPrep `-w` | live |
| 12 | 2026-08-27 | X11 hygiene: `xhost` scoped and reverted on exit | moot — X11 removed (21) |
| 13 | 2026-08-27 | Decide PEP 562 lazy imports from the import-timing spike | done: the server imports SimNIBS lazily |
| 14 | 2026-08-27 | Preload bridge budget: no growth without an ADR line. **13** top-level entries at the time; **21** after the native TetraVox surface and FastSurfer API, with the two TI-owned viewer update actions removed and live scene saving added on 2026-09-19; **24** after `onNotificationSound` (2026-09-23) and the `assistant` namespace (2026-10-07; `assistant.start`/`openInTerminal` gained an options argument 2026-10-08, no new entry). `smoke.spec.ts` enforces the exact list | live, amended 2026-10-08 |
| 15 | 2026-09-02 | Tetravox as a service: a released embed bundle in an iframe, no Tetravox source in this repo | supersedes 3–4; viewer half re-decided by 27 then 29 |
| 16 | 2026-09-02 | Freeview/Gmsh/X11 kept only as the no-WebGL2 fallback | superseded by 21 |
| 17 | 2026-09-02 | Workflow-first IA and the density rules; one subject switcher; Panels group dissolved | live |
| 18 | 2026-09-03 | Native bundled Python runtime as the deployment target | parked by 22 |
| 19 | 2026-09-03 | FreeSurfer not required by default (charm + `subject_atlas` + FastSurfer `--seg_only`) | live |
| 20 | 2026-09-03 | Dependency-free typed Docker Engine API client; no dockerode; CLI only for `docker context inspect` | live |
| 21 | 2026-09-03 | X11 removed from the product with the viewers | live |
| 22 | 2026-09-03 | **Docker stays the single runtime**: one image `idossha/ti-toolbox:<ver>`; native runtime parked, not deleted | live |
| 23 | 2026-09-03 | The embed ships inside the image and is drawn on the host GPU; no X11 anywhere | superseded by 27, restored by 29 |
| 24 | 2026-09-03 | Compose remains the stack definition; the app realises it through the Engine API client | live |
| 25 | 2026-09-05 | Landing page = Overview; batch = a scheduler cap; one shared terminal; run-page panes draw a packaged guide; the Viewer loads on command | live |
| 26 | 2026-09-05 | Tetravox updates itself against a protocol range; electrode dots; one selection grammar; a pipeline is a job group | pipeline portion superseded 2026-09-13; native panes replace the embed-specific electrode implementation (27) |
| 27 | 2026-09-06 | Native run-page panes; the viewer is a separate desktop application; jobs tables | pane half live; viewer half superseded by 29 |
| 28 | 2026-09-06 | Managed host install of Tetravox; the pipeline's Subjects node and readiness gating; jobs tables on all three run pages | install half superseded by 29; pipeline portion superseded 2026-09-13; job tables live |
| 29 | 2026-09-06 | **The embed is restored, baked in the image, on the Viewer's own two sub-pages.** Nothing installs Tetravox on the host | superseded by native TetraVox decision, 2026-09-13 |
| 30 | 2026-09-07 | External audit response: the six scientific corrections, the server hardening, one release workflow | live |
| 31 | 2026-09-15 | One TetraVox resolution order (configured, managed, system, PATH) and feed-verified managed updates | amends the install half of 2026-09-13 |
| 32 | 2026-09-17 | A plan's CPUs, threads and duration are the run's: one CPU detector, one budget env var, one estimate model per kind | live |
| 33 | 2026-09-18 | Path validation at the boundary: one name grammar, one lexical join, one physical containment check; CodeQL alerts resolved by shape, not suppression | amends 30 |
| 34 | 2026-09-19 | A job's CPU/RSS are its process tree's, sampled once a second; peak and average persist with the record; the Jobs table drops STAGE | live |
| 35 | 2026-09-19 | The Artifacts tab lists the job's output folder from disk (`GET /api/jobs/{id}/artifacts`); a runner registers where it wrote, not what | live |

## Runtime and distribution

### 2026-09-03 — Docker remains the runtime (ADR 18–24)

**Decision.** Ship Electron with one Docker image containing the server, scientific environment,
UI and viewer embed. Compose is the run specification; Electron realizes it through the typed
Docker Engine API. Native deployment remains parked. FreeSurfer, X11 and the old Qt GUI are not
part of the current product.

**Why.** The native spike worked on Apple Silicon, but distribution and DWI still needed Docker;
a second runtime added platform and packaging ownership without removing that dependency.
**Cost.** Docker remains required; native-platform and licensing questions from the spike remain
unsettled. **Revisit if.** A supported native distribution can cover the whole workflow.

### 2026-09-06 — Viewer embed and native workflow panes (ADR 27–29)

**Superseded 2026-09-13:** the managed native TetraVox decision replaces the embed portion; run-page
WebGL panes remain.

**Decision.** Tetravox is baked into the image and served in the retained Viewer sub-page.
Nothing installs Tetravox on the host. The Menu composes files; appearance belongs to Tetravox.
Workflow panes use the app's own WebGL2 renderer and packaged reference anatomy.

**Why.** The briefly adopted external-app design confused “no display in the container” with
“no browser renderer”; the embed draws on the host GPU. Native panes provide controlled picking
and editing without waiting for another project's release.
**Cost.** Two renderers remain. Guide coordinates cannot silently become subject coordinates;
subject-space placement requires the explicit subject-anatomy mode. **Revisit if.** Their feature
and lifetime requirements converge.

### 2026-09-05/06 — Independent Tetravox delivery

**Superseded 2026-09-13:** native package delivery replaces browser-bundle protocol negotiation.

**Decision.** Pin protocol compatibility and required features, not a Tetravox version. Resolve
published embed assets through the GitHub Releases API; verify digests and archive containment
before atomic installation. Automatic compatible updates default on, with rollback and pinning.
Mounted frames retain their current bundle.

**Why.** A viewer fix should not require a toolbox image release. Reading the manifest before
the archive rejects incompatible releases cheaply. The update baseline is release-install
provenance, so a locally named development version cannot suppress real updates forever.
**Cost.** The installer, update channel and compatibility tests remain product responsibilities;
o network or failed checks must degrade honestly. **Revisit if.** An update breaks compatibility,
or upstream changes its protocol or release index.

### 2026-09-07/09 — One product pipeline and explicit publication

**Decision.** Retire the legacy launcher. Build and validate the current app through the existing
release workflow; verify packaged runtime files and dependencies, then sign/publish only through
explicit release gates. Internal image delivery is distinct from public promotion. Use protected
main, short-lived topic branches and bounded release branches; `release/3.0.0` replaced `develop`.

**Why.** The old release path would have published v2 launchers under a v3 tag. The maintainer
subsequently requested current-product documentation and deferred Docker Hub publication until
manual testing. This supersedes the September 8 preview/teaser documentation decision.
**Cost.** Each distributed source/image/package pairing needs its own acceptance evidence; a
generated installer is insufficient. **Revisit if.** Parallel supported releases need maintenance
branches. Current commands, workflow names and gates live in [RELEASING.md](RELEASING.md).

### 2026-09-08 — Blender has a separate supported environment

**Decision.** Keep SimNIBS's scientific NumPy environment intact; run the official pinned Blender
executable in background mode with prepared geometry/electrode data. Preserve public job/config/
artifact interfaces. A checkpoint-cache fallback needs an explicit archive digest and independent
publisher checksum/size evidence; never bypass TLS.

**Why.** Installing `bpy` downgraded scientific NumPy; permissive wheel metadata did not establish
ABI compatibility. **Cost.** A second runtime and a narrow data boundary; actual export/reopen and
scientific imports need separate verification. **Revisit if.** Upstream supports both in one environment.

### 2026-09-09 — Launch the requested image and checkout

**Decision.** Keep the shared Python/Bash launchers and existing Node dev loop. Argument-free
terminal launch asks only for the remembered project. Explicit image requests must match the
running container. Mounted development verifies the actual checkout bind and import precedence,
reload setting and local renderer; it never silently falls back to baked UI.

**Why.** An obsolete worktree mount made local fixes appear ineffective. Marker environment
variables alone did not prove which source was executing. **Cost.** Python-only browser testing
needs a renderer build; Vite supplies frontend live updates. Incompatible active or uninspectable
jobs prevent automatic replacement. **Revisit if.** Remote Docker makes host-path identity insufficient.

## Interaction and job ownership

### 2026-09-04/06 — Retained state and explicit view lifetime

**Decision.** Retain visited pages for the project session; inactive pages relinquish command,
keyboard and status ownership. Camera resets require explicit intent. Viewer selection is a draft
until Open; failed loads retain the previous scene. An explicit “Open in viewer” deep link carries
open intent. Preview build errors require explicit retry rather than endless polling.

**Why.** Navigation and incidental selector edits destroyed expensive live state. Consumed server
build errors could trigger repeated builds and conceal the original failure.
**Cost.** Retained memory and an explicit recovery action. **Revisit if.** Memory pressure requires
serialization, or the server gains durable build-error identities.

### 2026-09-05/06 — One job table and one scheduler

**Pipeline portion superseded 2026-09-13:** job tables and the shared scheduler remain supported.

**Decision.** Simulator, Optimizer and Analyzer describe one job per row. Shared selection controls
own selection semantics; the plan grid and action digest state the batch. The extra sticky run
receipt was removed on September 6. A batch uses server groups and admission caps; a pipeline is
one existing-job DAG, never a second executor. Subjects nodes and readiness validation prevent
known-invalid edges. Dynamic bindings resolve between producer completion and consumer admission.

**Why.** Subject × montage fan-out could not express independent jobs, and awaited client POSTs
did not enforce concurrency. **Cost.** Caps count jobs, not distinct subjects; mixed-kind UI runs
may use separate groups. No loops, conditionals or retry engine. **Revisit if.** Those semantics
become requirements; they need an explicit scheduler/contract change.

### 2026-09-05/06 — Pipeline canvas and notebook export

**Superseded 2026-09-13:** the graphical pipeline feature was removed; see the removal decision below.

**Decision.** Use controlled React Flow for the canvas and optional `nbformat` support for export.
Export deterministic notebooks calling documented public APIs; retain the pipeline document in
metadata. Do not reconstruct graphs by parsing arbitrary edited Python.

**Why.** Interaction geometry is established library work; notebook execution is a public-API
promise. **Cost.** Dependencies and complete handling of canvas change events; missing export
support returns an honest error. **Revisit if.** Import or richer execution becomes required.

### 2026-09-06/07 — Notebook kernels belong to the container

**Decision.** Use the SimNIBS Jupyter kernel, CodeMirror and kernel completion/inspection. Reserve
kernel capacity before starting; idle time starts after requests finish. Stop/join message pumps
before closing sockets. Revisioned saves cannot clear later edits. Sanitize rich HTML and render
SVG as an image; interactive plots without a safe output scheme remain unsupported.

**Why.** Host kernels reintroduce environment installation; language servers cannot see the live
notebook namespace. Earlier implementations could exceed caps, reap busy kernels, abort the API
on restart, lose edits or execute stored output in the app origin.
**Cost.** Kernels are intentionally unsandboxed; hung work requires explicit recovery. Interactive
plots and external kernels need additional architecture. **Revisit if.** Those capabilities are required.

### 2026-09-07 — Reserve resources and validate at boundaries (ADR 30)

**Decision.** Reserve scheduler locks before runner acquisition. Unknown dependencies are errors,
not satisfied preconditions. Validate subject IDs where they become paths and contain tools,
notebook, scene and job storage paths. Reconnect snapshots are authoritative with protection for
in-flight live updates. Quit policy applies to every owned backend and awaits cancellation.

**Why.** Split check/acquire steps admitted conflicting work; permissive paths escaped the project;
add-only reconnect left stale jobs; backend-specific quit could discard work silently.
**Cost.** Stricter inputs and less aggressive admission. Filesystem containment is not a sandbox
against malicious concurrent local mutation. **Revisit if.** Multi-user trust or storage ownership changes.

### 2026-09-18 — The FreeSurfer license is the user's own, pasted once; FastSurfer needs none

**Superseded 2026-09-20:** the personal-license policy and its redistribution premise below are
reversed by *FreeSurfer licensing is supplied by TI-Toolbox*. The FastSurfer heartbeat fix stands.

**Decision.** The toolbox never bundles, fetches or returns a FreeSurfer license: it is issued per
registered individual and may not be redistributed. The one place a user adds theirs is
**Settings → Pre-processing → FreeSurfer license** (`PUT`/`DELETE
/api/surfer-settings/freesurfer-license`, body `{text}`); the server keeps it as
`<user config dir>/freesurfer-license.txt` (mode 0600), a directory every launcher already
bind-mounts at `/root/.config/ti-toolbox`, and `resolve_fs_license_path()` resolves
`$FS_LICENSE` → that file → `/usr/local/freesurfer/license.txt` (an empty file — the Apptainer
placeholder — does not count). Every job that runs FreeSurfer binaries then receives it the way
it already did: the FreeSurfer worker stages a 0600 copy into the project and binds it at
`/run/license.txt` with `FS_LICENSE`; QSIPrep/QSIRecon get `--fs-license-file`. `GET
/api/surfer-settings` reports `freesurfer_license: {configured, source, email}` — the registered
email so the user recognises it, never the key. Preflight (`tit.pre.preflight.LICENSED_STEPS`)
asks for a license only for `recon-all`, thalamic nuclei and hippocampus/amygdala, and its one
message names exactly the selected stages that need it, the registration URL and where to paste
it; FastSurfer `--seg_only` is never gated.

**Why.** In the v3 app no launcher set `FS_LICENSE` or mounted a license, so the FreeSurfer stages
could never be licensed at all, and the only guidance was "configure the license". Separately,
the report "FastSurfer is blocked" was not the license: a stale
`code/ti-toolbox/native-fastsurfer/availability.json` left by a force-quit desktop app made
every FastSurfer job fail with *Native FastSurfer host is disconnected* before `run_fastsurfer.sh`
started. A stale heartbeat *before* a request now means "no host" (warning, container fallback);
a host that vanishes *mid-run* still fails the job rather than restarting it on CPU.

**Cost.** One new frozen-contract path and one new required property on `SurferSettings`
(`contracts/openapi.yaml`, regenerated). A user who wanted the GPU and submitted with the desktop
app closed now gets a slower CPU run with a warning in the log instead of a refusal.
**Revisit if.** FreeSurfer drops the license requirement for the subregion tools, or a project-
scoped license (per dataset, not per user) is asked for.

### 2026-09-18 — Path validation at the boundary; CodeQL alerts (ADR 33, amends 30)

**Decision.** Every user-supplied value that becomes a path component passes through one of three
functions in `tit/paths.py`, and CodeQL must be able to see it. `validate_subject_id` (existing)
and the new `validate_name` are the allowlists: one grammar for subject ids, one for everything
else (simulation, run, montage, ROI, atlas, EEG net, analysis, stats names — letters, digits,
`._-`, an inner space for v2's legacy names, never a leading dot, never a separator, ≤ 128).
`resolve_under(root, *parts)` is the lexical join every `PathManager` accessor uses
(`normpath` + `startswith(root/)`, no filesystem access, symlinks not followed);
`resolve_within(jail, path)` is the physical check at the I/O boundary (`realpath` +
`startswith(realpath(jail)/)`, returning the resolved path so what is checked is what is opened);
`resolve_leaf_within` is its write/delete form, which resolves the parent and keeps the leaf so an
alias is replaced rather than its target. Request values are validated by pydantic before a route
body runs (`tit.server.schemas.SubjectId` / `EntityName`, as `Annotated[..., Query()]` so FastAPI
keeps the validator; a bare `T = Query(...)` silently drops it): a path-shaped value is a 422
naming the rule, never a 404 from deep inside a listing. Boolean helpers (`is_within`,
`_project_paths_safe`) stay for callers that only ask; anything that then *opens* uses the
returning form. No `# lgtm`, no `# noqa`, no CodeQL path exclusions.

**Why.** 178 open `py/path-injection` alerts and one `py/polynomial-redos`. Every one traced to a
FastAPI request value (subject, simulation, run, name, atlas, net, notebook name, viewer preset
name, a layer path in a body) reaching `open`/`listdir`/`stat` through `PathManager` or
`tit.catalog`. The code already had the checks — `validate_subject_id`, `is_within`,
`Path.resolve().is_relative_to`, `_source_path`'s `resolved == root or resolved.startswith(...)`
— but in shapes CodeQL does not recognise as barriers: a regex allowlist is not one; a boolean
helper's result is not one; `is_relative_to` is not modelled; an `or` around the `startswith`
guard breaks it. The only recognised idiom is *normalise (or realpath), then `startswith` on that
same value in the true branch*, so the sanitizers are written in exactly that shape and return
the guarded value. Two findings were real: `POST /api/view/args` stat'ed every layer `path` and
probed every `attachments` entry from the body before jailing (an existence oracle), and the
mask-upload filename regex backtracked quadratically on a run of dots.

**Cost.** `PathManager.simulation`/`*_run`/`stats_output` now raise `ValueError` for a name with
a separator or a leading dot where they used to return a path that later failed to exist; routes
return 422 rather than 404 for such names (four tests updated). Local CodeQL is the proof:
`codeql database analyze … PathInjection.ql PolynomialReDoS.ql` went 178 + 1 → 0 + 0 on this
checkout. **Revisit if.** A legitimate project name falls outside `NAME_RE` (widen the grammar in
one place and add it to `tests/test_request_name_validation.py`'s Dataset 000 walk), or CodeQL's
Python barrier set gains regex validation.

### 2026-09-06/09 — UI consistency without duplicate state

**Decision.** Keep shared controls, selection and region-toggle models. Terminal Clear uses a
watermark, never deletes logs; pages do not auto-pin completed jobs. Overview replaces Subject
Info. The rail uses digits 0–9, Settings uses its own shortcut, and the preload budget was 13 host
entries including `saveFile`, not a viewer launcher (the 2026-09-13/15 native TetraVox decisions
raised it to 22; ADR row 14). Computational extensions use the common
inputs/plan/terminal layout; controls share a left-aligned label column.

**Why.** Parallel page conventions produced inaccessible controls, mismatched selections and
redundant views. Content-sized labels were tried September 9 and superseded by aligned control
starts the same day. **Cost.** Pages must extend shared components; another host action or rail
row needs a deliberate decision. **Revisit if.** A workflow cannot be represented by the common model.

### 2026-09-06 — Native pane anatomy and labels

**Decision.** Opaque grey matter sits under adjustable skin. Preserve cameras across data changes.
Use atlas colors, aligned TVSC1 labels and majority-labeled provoking vertices without changing
triangle winding. Electrode color encodes state; freehand editing belongs in Simulator.

**Why.** Two translucent surfaces obscured anatomy, arbitrary flat-shading vertices caused border
spikes, and duplicate region models could disagree with submitted ROIs.
**Cost.** Bounded transparency and unresolved idle-marker contrast; real electrode solids need
solver-consistent tangent frames and geometry. **Revisit if.** Measurements require a different renderer
or marker design. Current visual rules and open work live in ARCHITECTURE and ROADMAP.

### 2026-09-07/09 — Viewer composition, scenes and incremental loading

**Decision.** A composition records file choices to re-resolve; a scene preserves the embed's
serialized camera and layers. File basenames remain layer names; surfaces and FEM meshes are
different kinds. Cache full-data statistics by file identity. Dataset concurrency and reuse belong
in Tetravox; the toolbox reconciles progress and preserves successful layers after partial failure.

**Why.** Selection reproducibility and picture reproducibility age differently. Re-reading volumes
and recreating retained datasets made small edits expensive. **Cost.** Concurrent decoding uses
more memory; unchanged URLs may retain overwritten data until explicit Reload.
**Revisit if.** File revisions enable reliable automatic freshness or memory pressure requires a queue.

### 2026-09-09 — Per-job mapping and pinned search destinations

**Decision.** Simulator owns opt-in fsaverage mapping per job; Source exposes forward preparation.
Optimizer resolves an explicit unique folder before preview/submission and refreshes automatic
names after submission. Solver and post-search settings remain directly exposed.

**Why.** Mapping belongs with the simulation, and independently generated timestamps made previews
disagree with runs. **Cost.** An extra path-resolution request; raw API clients without pinned
folders retain timing warnings. **Revisit if.** Additional projection controls are required.

### 2026-09-09 — Project permission and per-run overwrite confirmation

**Decision.** Existing-output replacement requires project `allow_unsafe_overrides` (default false)
and a fresh run choice. Shared dialogs default to Skip; server submission checks groups before
creating jobs. Simulation propagates confirmed overwrite to SimNIBS's supported SESSION option.

**Why.** Dialogs offered replacement without the project setting, and persisted confirmation never
reached SimNIBS. **Cost.** Server/API submissions need project opt-in; direct Python calls retain their own policy.
Prior confirmation cannot authorize rerun.
**Revisit if.** Authenticated per-user roles replace the current project trust model.

### 2026-09-15 — Remove `allow_unsafe_overrides`; "Replace and rerun" is the one replacement control (reverses 2026-09-09)

**Decision.** Dropped the project-scoped `allow_unsafe_overrides` setting and the redundant
"Output safety" settings card. Existing-output replacement is now gated only by the per-run
"Replace and rerun" choice plus its existing confirmation dialog (`overwrite`/
`replace_existing_outputs`); `check_overwrite_permission` no longer 403s for a disabled project
setting, only 409s pending that confirmation. Non-critical `/api/validate` findings were never
server-enforced blockers, so nothing changed there beyond removing the stale settings-page text
claiming otherwise.

**Why.** The setting duplicated the "Replace and rerun" control it gated, and its text also
described a "queue despite non-critical findings" effect that no route ever implemented. Two
controls for one decision confused users without adding real safety.
**Cost.** None measured; a stale `allow_unsafe_overrides` key in an old project's `settings.json`
is now silently ignored rather than read.
**Revisit if.** A real severity-graded validation model (critical vs. warning findings) is added
and needs a queue-time gate again.

## Scientific decisions

### 2026-09-07 — Correct statistics, geometry and exposure (ADR 30)

**Decision.** Preserve separate signed cluster components and tail-oriented comparisons; reject
mismatched voxel grids; use affine geometry and explicit area/volume units; distinguish sampled
from exhaustive permutation p-values; preserve IEEE degeneracy and exclude untestable voxels.
Rationalize weak-modulation arithmetic and compute pooled variance from sums of squared deviations.

**Why.** These defects could produce valid-looking wrong results, including uniformly null maps
for singleton groups. **Cost.** Some old results require reruns or rescaling. The sole user-facing
impact/remediation record is [scientific corrections](../releases/v3.0.0.md#scientific-corrections), SCI-01–09;
do not duplicate its version ranges or correction factors here.
**Revisit if.** New numerical evidence changes an algorithm or its valid input domain.

### 2026-09-07 — Positional carrier model and one pair-count rule

**Decision.** One electrode pair is one current channel/carrier; positional pairing defines TI/mTI.
Valid field/pair counts are even and at least two, stated once in `is_valid_pair_count`. Exposure
is coherent within a carrier and incoherent across carriers; the shipped wiring needs no
`channels=` argument. Quasi-static exposure is a worst case over unknown phases.

**Why.** The v2.5.0 merge removed shared-carrier configuration; retaining a grouping argument would
advertise unsupported wiring. Config and math previously disagreed on odd pair counts.
**Cost.** Shared-carrier montages are inexpressible and need coherent presumming plus a common
configuration contract if restored. No released version shipped the short-lived grouping API.
**Revisit if.** Hardware supports multiple phase-locked pairs on one source, or allowed pair counts change.

## Development milestones

### 2026-08-27 — Electron and the job server

Established `desktop/`, FastAPI routes, the hand-authored OpenAPI contract and the server-owned
queue, dependencies, groups, locks, progress, events and cancellation. Contract-first development
survived later UI redesigns. The early flat navigation and NiiVue evaluation did not.

The spike established why SimNIBS imports must be lazy and why field display percentiles need
a GM mask. GIfTI export must preserve scanner RAS; passing volume geometry can shift surfaces
by `c_ras`. Test telemetry was isolated after tests were found making production network calls.

### 2026-09-02 — Workflow-first navigation and Tetravox

Replaced the flat page collection with workflow navigation, merged optimization interfaces and
an iframe/postMessage viewer. In-process engine vendoring was rejected because it would also
require maintaining viewer chrome. Same-origin fetch and session cookies avoided a custom scheme.

### 2026-09-03 — Native desktop research (parked)

A native Apple Silicon runtime completed real simulation and matched the emulated container;
FastSurfer segmentation and Python replacements for FreeSurfer utilities were also evaluated.
The native deployment path was parked, not certified: no Windows or x86_64 machine was used,
full runtime signing/notarization was not attempted, and DWI still required Docker. Platform wheel
availability and commercial redistribution terms remained questions for any future native effort.

The retained useful outcomes were POSIX process-tree cancellation, labels for cancellation of
QSIPrep/QSIRecon sibling containers, and evidence for removing FreeSurfer as a mandatory runtime.
Measured numerical comparisons and the single-subject FastSurfer limits are in BENCHMARKS.

### 2026-09-03 — One Docker image and a real development loop

Kept Docker, removed X11 and the separate FreeSurfer image, and moved desktop orchestration onto
the typed Docker Engine API. The image owns the scientific package, server, UI, embed and
FastSurfer segmentation. Worktree mounting became an explicit development choice after an
unconditional mount was found replacing packaged source.

Added `dev`, `dev:web`, `dev:down` and a real-job smoke harness. Run pages gained the common
plan/terminal layout and measured layout checks. Production Docker images and ordinary host
launchers share the run specification; development adds checkout/reload/renderer overrides.

### 2026-09-04 — Scene service and retained pages

Built compact scene payloads, shared WebGL2 panes, subject selection and retained page state.
Real picking exposed inward-wound anatomy; outward orientation and a cache-version change fixed
it. Preview build failure handling became explicit instead of hiding errors behind endless retries.
The Tetravox delivery/update machinery shipped; migrating workflow panes into that embed was
subsequently reversed.

### 2026-09-05 — Overview, batch execution and explicit viewing

**Pipeline portion superseded 2026-09-13:** graph execution and its dynamic binding adapter were removed.

The R1–R5 program delivered aggregate Overview, a shared clearable console, scheduler-enforced
batch caps, packaged Ernie guide anatomy and draft-versus-loaded Viewer state. The A–D program
added compatible Tetravox updates, color-coded electrode dots, shared selection controls and the
pipeline canvas with public-API notebook export. These historical requirement labels still appear
in code; current behavior belongs in ARCHITECTURE.

A container restart during FEM exposed the importance of job recovery semantics. The Jobs layer
remains independent of pipeline UI code; dynamic bindings live in the Jobs package.

### 2026-09-06 — Native panes, job rows and notebooks

Restored native workflow panes and interactive atlas selection. Simulator, Analyzer and Optimizer
became per-job tables instead of subject × montage fan-outs. A host-installed external viewer was
adopted briefly, then explicitly reversed the same day: the image ships the embed, with Menu and
Tetravox as retained Viewer sub-pages. ADR rows 27–29 preserve that reversal.

Added container-backed notebooks, CodeMirror and kernel completion. Live testing caught a ZMQ
restart crash, editor command-mode interception and completion-range bugs that mocks missed.
The extra sticky run receipt was removed; report output later became an attachment of its job.

### 2026-09-07 — Scientific audit and v2.5.0 integration

Reproduced and corrected cluster-tail, grid, unit, affine, p-value and degenerate-statistic defects;
exposure conventions and weak-modulation arithmetic were clarified. SCI-01–09 in
[scientific corrections](../releases/v3.0.0.md#scientific-corrections) retain affected outputs and remediation.
Singleton-group pooled variance was a code defect, not evidence of an intrinsically untestable
voxel set. Fixing it does not overcome the inference limits of a tiny cohort.

Merged v2.5.0 and its positional TI/mTI API. Callers, notebooks and generated contracts needed
updates even where Git found no conflict. A second envelope implementation in the accelerated
path required the same numerical correction. Existing project copies of seeded notebooks do not
automatically inherit source-template repairs.

Server hardening added resource reservations, dependency rejection, path containment, revisioned
notebook saves, reconnect reconciliation and rich-output sanitization. Packaging review found the
old release workflow would publish the v2 launcher and that required compose/assets were omitted
from packaged builds. The legacy launcher was retired and artifact inspection became a release gate.

### 2026-09-07 — Viewer composition and documentation consolidation

The Viewer became a subject/space tree distinguishing volumes, tetrahedral meshes and surfaces.
Compositions save choices to re-resolve; scenes save Tetravox's actual camera/layer state. Layer
names use filenames. Persisted full-data statistics and client caching removed repeated volume
reads; meaningful windows and fitted cameras replaced arbitrary defaults. Results and job artifacts
now carry explicit “Open in viewer” intent.

Developer documentation was folded to nine files and per-lane note trees removed. The follow-up
found stale citations, stale test selectors and an order-dependent mock leak; an isolated test pass
had previously hidden a failed full suite. Full-suite failures remain failures until resolved.

### 2026-09-08 — Internal distribution and Blender isolation

Rebuilt the runtime instead of treating a mounted development image as release evidence. `bpy`
had downgraded scientific NumPy; Blender moved to its supported background executable with a
prepared-data boundary. Actual subject export/reopen established the larger montage memory need.
Image-identity checks prevented loaders from silently attaching to an old image, and internal
publication was serialized by resolved tag.

Real validation repaired stale UI selectors, missing fixtures and an obsolete mEx carrier field.
These runtime/planner fixes did not add scientific-formula corrections. Validation used a copied
dataset; individual earlier successes did not certify the rebuilt artifact.

### 2026-09-09 — Security and development closeout

Hosted analysis prompted further concrete path, symlink, WebSocket and search-DOM containment
fixes. Filesystem fixtures were checked in Linux as well as on the host. Kernels remain
unsandboxed; this work does not claim defense against malicious concurrent local filesystem races.
A packaged first launch failed on an external `yaml` dependency, then passed after bundling it.
Earlier failed jobs and inconclusive native-monitor runs remain distinct from later functional passes.

A clean internal image and wheel were retained for local testing. The development branch became
`release/3.0.0` without rewriting ancestry. Documentation now describes the current product;
installation owns actual artifact availability. Main merge and Docker Hub publication were deferred
until manual testing. Current delivery status is in ROADMAP, not inferred from this milestone.

### 2026-09-09 — Workflow polish and progressive viewing

Unified extension inputs/plan/terminal layouts and selection-aware export previews. Moved optional
fsaverage mapping into individual simulation jobs, stabilized participant table actions and CSV/TSV
interchange, pinned automatic optimization folders before submission, and exposed solver settings.
Form controls retain aligned starts. Results reopens its selected preview and passes exact artifact
paths to the Viewer.

Tetravox now adopts completed layers progressively and retains datasets when selections grow;
TI-Toolbox reconciles progress and keeps successful layers visible after partial failure. This was
locally activated through the existing installer, not published as a new toolbox image.

Missing ImageMagick had left copied blank cap templates appearing successful. Restored the runtime
dependency/fonts and made montage rendering atomic with explicit failures. Two confirmed blank
images were repaired from saved configuration without rerunning simulations.

### Retired root plan — 2026-09-09

Removed root `TODO.md`: its August plan mixed completed work, superseded designs and an incorrect
public-release claim. Contributor invitations and unresolved work moved to
[RELEASING.md](RELEASING.md). Historical `TODO §2.x` citations refer to the
[original plan in Git history](https://github.com/idossha/TI-Toolbox/blob/b6304f7fbae6d5ebd4f90881e8383ad728282b7e/TODO.md),
not the current contract. Agent integration gained direct stdio registration and plain-file fallbacks;
protocol process tests do not claim full native-client acceptance.

### 2026-09-09 — Current checkout and overwrite safety

Replaced an idle development container mounting an obsolete secondary checkout. The existing dev
loop now verifies the primary checkout and local frontend instead of trusting environment markers
or baked files. Obsolete runtime containers/images and secondary worktrees were removed after
inspection; dirty source was archived under `~/TI-toolbox-worktree-backups/20260909-023601/`.
Datasets, the retained internal image and unrelated unmerged branches were preserved.

A confirmed replacement job still failed because `JobSpec.overwrite` never reached SimNIBS.
The runner now forwards confirmation to SESSION's supported option. The existing project setting
also gates replacement in dialogs and server submission; old confirmation does not authorize a new
rerun. Tests used temporary fixtures and did not rerun existing user outputs.

### Lessons retained from the migration

- Test the actual boundary: Python 3.11 archive extraction and case-sensitive container paths do
  not behave like the macOS host. A passing mock cannot prove filesystem or numerical behavior.
- Follow deleted APIs/test IDs through callers, generated schemas and seeded examples. A clean
  merge can preserve an obsolete formula or broken example without a conflict.
- Inspect the packaged artifact, not only its build configuration. Ignore rules can hide required
  icons; packaging allowlists can omit compose files; unresolved externals can break first launch.
- A successful request or emitted artifact event does not establish a visible pane or a file on
  disk. Check dimensions/pixels and produced files at the consuming boundary.
- Shared build output, concurrent GUI tests and high machine load corrupt measurements. An
  inconclusive native visibility monitor is not a pass, even when functional assertions pass.
- Global mock assignments can poison later tests. Diagnose scene-guide failures in isolation but
  require the failed full suite to pass after the cause is repaired.
- Electron does not provide browser `prompt` or reliable blob-download behavior automatically;
  file export uses the owned host bridge. Auto-open effects must not recursively depend on the
  draft state they update.

## 2026-09-09 — Documentation ownership

Adopt the roster in [AGENTS.md](../../AGENTS.md#where-things-are-written-down). Contributor setup
lives at the root; architecture includes UI design; testing, release procedure, performance,
roadmap and automation have separate owners. The earlier combined release/roadmap and separate
design pages were superseded to reduce overlap. CHANGELOG moves into this roster while retaining
its public site route. Revise current-state references; append only significant decisions and
release history. Revisit when an additional topic has a distinct reader and owner.

## 2026-09-09 — Explicit loader and development modes

The Bash entry point must not require Python. It uses Docker Compose and the same run spec and
project labels as the Python/Electron launchers, rather than bootstrapping Python. Dev loaders
mount their own checkout/worktree; missing local UI output must not select the baked UI instead.
Keep Docker-backed `pnpm dev` as the reproducible default and add explicit `--host`/`dev:host` for
local API/UI work. Host science dependencies remain the developer's responsibility. This preserves
existing Docker workflows while making container-free development a deliberate choice.

## 2026-09-09 — Custom optimizer masks and stacked panes

**Decision:** Reuse volumetric ROI configuration for explicit Subject/MNI NIfTI masks in Flex
and Ex; use SimNIBS’ subject registration for MNI conversion. Give stacked run panes full width
and viewport-scaled height while preserving the saved desktop width.
**Why:** Conformation alone is not anatomical registration, and a desktop width should not constrain
portrait viewing. **Cost:** MNI targets require the subject’s registration files.
**Revisit if:** Additional mask coordinate spaces or non-SimNIBS registrations are supported.

## 2026-09-09 — FastSurfer selects devices in its own environment

**Decision:** Delegate automatic CPU/CUDA/MPS selection to the pinned FastSurfer runtime,
with an explicit device override and an 8 GB default job reservation. Preserve the bundled
CPU-only image and the separate interpreter override for native FastSurfer installations.
**Why:** Host GPU presence does not imply the container or its PyTorch build can use it.
Replacing the shared SimNIBS environment with FastSurfer’s package environment would risk
incompatible dependencies. **Cost:** GPU acceleration needs a compatible native environment
or custom GPU-enabled image/runtime. **Revisit if:** Supported GPU image variants are added.


## 2026-09-09 — Analyzer imports registered mask targets

**Decision:** Extend Analyzer with the optimizer's NIfTI import and subject-registration path.
Masks select positive voxels with nearest-neighbor sampling; mesh statistics retain surface-area
weights and voxel statistics retain volume weights and tissue selection (§7.2 of ARCHITECTURE.md).
**Why:** A shared picker must produce a runnable target without duplicating nonlinear transforms
or treating subject coordinates as MNI. **Cost:** Group masks require MNI input and each subject's
m2m registration. **Compatibility:** `mask_path` is optional and appended to AnalyzerConfig;
existing sphere and atlas configurations retain their behavior. **Verification:**
`tests/numerical/test_analyzer_masks.py` covers native geometry and real nonlinear registration.

## 2026-09-09 — Read-only volumetric target previews

**Decision:** Use a separate Tetravox viewport for non-surface targets, backed by a cached
subject-space binary volume. Keep cortical picking in the existing surface renderer and make
the form authoritative. **Why:** Reference anatomy cannot accurately show a subject-space mask.
**Cost:** Previews need subject T1 and, for MNI targets, registration; geometric extent is shown
before tissue or mesh filtering. The main Viewer remains mounted for direct file drops.

## 2026-09-09 — Saved montage management

**Decision:** Place confirmed deletion of net montages and subject-specific freehand definitions
in Simulator's Manage montages dialog. Keep job removal separate and preserve simulation outputs.
**Why:** Creation had a visible entry point while definition deletion did not. **Verification:**
Catalog deletion tests cover subject/path boundaries; simulator UI tests cover cancel, confirm
and clearing referencing job selections.

## 2026-09-09 — Compact management and extension navigation

**Decision:** Bound the montage manager's list height, support confirmed multi-selection deletion,
and group enabled extension links beneath Extensions. **Why:** Long catalogs expanded the dialog
beyond a useful size and flat extension links crowded the workflow rail. **Compatibility:** Keep
the existing deletion endpoints and extension routes; partial deletion failures remain selected.

## 2026-09-09 — Overview project context

**Decision:** Load identity, cached file-size totals and retained job activity through a separate
project-summary endpoint. **Why:** Recursive storage scans must not delay the subject matrix.
The calendar counts job submissions by UTC day; filesystem timestamps do not establish project
creation or access history. File-size totals are distinct from System's allocated disk usage.


## 2026-09-09 — Explicit container selection and browser-first terminal launch

**Decision:** Terminal loaders open the browser by default; `--desktop` explicitly delegates to
Electron. Every Docker launcher asks before using a running TI-Toolbox session, including another
project's session. Attach preserves its actual project/image/mounts; Recreate replaces only the
selected session from the requested Compose configuration. Noninteractive calls require an explicit
decision and an unambiguous selection. **Why:** Implicit reconnect and idle configuration replacement
hide consequential session choices. The initially proposed Electron CLI default was reversed because
terminal users can use the same scientific backend through their browser. This supersedes implicit
reuse/recreation in “Explicit loader and development modes”; source mounts and Python-free Bash remain.

**Prompt:** Display image repository/version references with a separate actions section, Recreate as
the Enter default and Attach second. This incorporates the later display refinement from generated
container names to image references. EOF, Ctrl-C and invalid input do not authorize replacement.
A short introduction precedes setup, and the consequence line explains that recreation stops jobs.
Executable coverage is mapped in [TESTING](TESTING.md#launcher-lifecycle-checks).

## 2026-09-09 — Overview owns project selection and desktop lifetime

**Decision:** Welcome Overview contains the editable path, native picker and Open action within the
normal app shell, including the full navigation with disconnected project tools disabled. There is
no separate user-facing launcher or server/token form. Switch project collects and validates the
new path and Compose plan before native confirmation and shutdown; cancellation preserves the
current project. Navigation to the new session clears project state while preserving machine
preferences. **Why:** One application gives users context before opening data and lets them change
projects without an intermediate launcher. This supersedes the earlier separate-launcher and
close-to-launcher proposals and the initial return-home switch flow.

Electron stops/removes the session it started or explicitly adopted when its window closes or Quit
is chosen, then exits on every OS; it does not stop manually connected remote servers. Failed shutdown
keeps the app open with an error. Named volumes and project files remain. Browser sessions remain
persistent until explicitly stopped. Successful CLI desktop completion returns the shell with a
closure message; errors preserve failure status. See [ARCHITECTURE](ARCHITECTURE.md#launch-modes)
for the current contract and [TESTING](TESTING.md#launcher-lifecycle-checks) for its coverage limits.

## 2026-09-09 — Desktop development uses the same welcome flow

**Decision:** `npm run dev` builds and opens welcome Overview without requiring project configuration
or starting Docker. A failed build prevents launch. `dev:web` retains Vite hot reload and
`dev:launcher` remains an alias. **Why:** Developers must be able to test the desktop project workflow
before packaging through the ordinary development command. See [CONTRIBUTING](../../CONTRIBUTING.md)
for commands; real packaged lifecycle acceptance remains in [ROADMAP](ROADMAP.md).

## 2026-09-09 — Consolidate development records by purpose

**Decision:** Accepted requirements live in ARCHITECTURE, rationale in this log, verification and
limits in TESTING, and open work in ROADMAP. **Why:** The maintainer requires
one authoritative home per topic; accumulating dated request files duplicates current behavior and
leaves superseded proposals looking actionable. Dates remain useful within the decision log rather
than as a parallel development-document hierarchy.

## 2026-09-10 — Optional disposable FreeSurfer workers

**Decision:** Retain FastSurfer as default and restore explicit FreeSurfer reconstruction and
T1 subregion operations through on-demand sibling containers. This reverses the earlier
removal of all FreeSurfer execution, while keeping it out of the core image. **Why:** Some
projects need full reconstruction or finer nuclei/subfields. Project bind mounts preserve
results without a persistent service or named volume; job labels and cleanup cover cancellation.
Subregion-only execution requires completed recon-all and must preserve that reconstruction.

## 2026-09-10 — Downloaded launch files and independent development checkouts

**Decision:** Regular users need one launcher and its YAML, without a manual checkout.
Developer wrappers may live elsewhere and select a local source checkout through
`TIT_DEV_REPO_DIR`, independently of the project data directory. Direct CLI starts honor
adjacent YAML or explicit `TIT_COMPOSE_FILE`; invalid explicit paths fail. **Why:** Download
location should not determine which code or data is mounted. Standalone Python uses the
matching v3 launcher rather than silently bootstrapping the older default branch.

## 2026-09-10 — Stable application tag and dated FreeSurfer worker

**Decision:** Publish patch builds to mutable `idossha/ti-toolbox:v3.0.0` and the optional
worker to `idossha/ti-toolbox:freesurfer-20260910`. Replace the internal launcher default.
**Why:** The maintainer distributes small patches under the same application tag; the
rarely changing worker keeps a dated identity. Digests and source commits identify exact
builds. Fresh starts refresh the application image; Attach never replaces a running session.

## 2026-09-10: Optional managed Apple Silicon FastSurfer

Use a consented, user-owned native runtime for local Apple Silicon FastSurfer, with project-scoped file transport and a sandboxed worker. Linux containers cannot expose Metal; copying macOS code into the core image would not provide GPU access. Keep Docker job ownership and standard derivative generation. CPU aggregation avoids the high-resolution Metal buffer limit observed in the maintainer benchmark. FreeSurfer stays an explicit alternative, not an automatic fallback. Pins and checksum sources are recorded in `desktop/src/main/fastsurferInstall.ts`; upstream pinned requirements control the native Python environment. See ARCHITECTURE §12 and the testing guidance in TESTING.md for verification boundaries.

### 2026-09-10 — Prefer accessible GPUs for FastSurfer

Replace CPU-only PyTorch packaging with CUDA 12.6-enabled wheels. A same-image launcher probe checks access before adding Docker GPU requests; FastSurfer validates computation at job time. Native Apple Silicon remains consent-based, and CPU fallback is explicit in logs. This reverses the image-size-driven CPU-only choice because it prevented usable NVIDIA hardware from accelerating segmentation. Host drivers remain outside the image. See ARCHITECTURE §12 and TESTING.md for the verification boundary.

### 2026-09-10 — User-wide reconstruction preferences

Move Apple GPU setup and FastSurfer/FreeSurfer thread controls to Settings → System. Apple GPU approval persists for the desktop user while filesystem permissions remain per active project. New sessions resume an installed runtime without asking again. Shared user configuration owns thread preferences; automatic defaults use 80% of available CPUs. This replaces session-only GPU consent and per-project UI thread inputs to reduce repeated setup and keep Pre-processing focused on pipeline selection.


### 2026-09-10 — Group Settings by workflow

Settings uses horizontal Project, Pre-processing, Extensions, Viewer, and Server tabs. Pre-processing owns user-wide reconstruction operations and resource defaults, including CHARM and QSI. FreeSurfer defaults to reconstruction plus both supported subregion pipelines; its run-page checkbox selects the tool, not its configuration. GPU setup remains discoverable in browser sessions, but native installation consent requires Electron. Mounted tab panels preserve unsaved drafts.

### 2026-09-10 — Persistent QSI and scoped CHARM overrides

QSI processing choices share user preferences between Settings and run-page dialogs; resources
remain separate. Dialogs use stacked labels and a bounded scrolling body to prevent overlap
and keep actions visible. Structural stages are grouped in two columns, with reconstruction
configuration links attached below their owning tools.

CHARM exposes only validated denoising, final segmentation resolution, and scalp facet size.
The runner copies the installed INI and changes explicit values, preserving all other installed
settings. It does not synthesize a new meshing profile or modify the installed file.


### 2026-09-10 — Consolidate v3 development on main

Retire `release/3.0.0` after merging its accepted work into `main`. Development continues on
`main` until the official release; this reverses the active release-branch arrangement above.
Do not create a release tag or change the notification version (`version.py`, 2.5.0) as part of
this consolidation. Resume isolated topic work after the official release.

Apple GPU setup now uses the Settings dialog as its single consent surface, including source,
permissions and third-party notices. Remove the duplicate native dialog while retaining sender
validation, local-project checks and project-change cancellation in the main process.


### 2026-09-11 — Canvas fidelity to existing jobs

**Superseded 2026-09-13:** the graphical pipeline feature was removed; see the removal decision below.

**Decision:** preserve complete node configurations through edits, resolve explicit producer outputs,
and make exported notebooks faithfully execute existing job functions. The canvas remains a visual
composition layer, not a second scientific implementation.

**Why:** the audit reproduced lost scientific settings after loaded-node edits, incomplete notebook
configurations, and validation that hid planner errors. The maintainer authorized correcting these
behaviors with incremental local tests.

**Cost:** configuration round-trip and notebook execution tests must cover the same non-default inputs
as the underlying jobs. Unsupported bindings must report an error rather than guess an output.

**Revisit if:** a new job kind needs a binding the existing job functions cannot represent.


### 2026-09-11 — Plain notebook calls and shared processing forms

**Superseded 2026-09-13:** the graphical pipeline feature was removed; see the removal decision below.

**Decision:** exported notebook cells are ordered calls to existing scientific functions with
explicit configurations. Canvas inspectors reuse the dedicated pages' settings components.

**Why:** the maintainer clarified that notebook readers want the functions and inputs, not an
embedded graph or execution framework, and that nodes need the same options as their pages.
This supersedes the notebook adapter mechanism introduced with the earlier canvas fidelity change;
full configuration preservation and exact producer bindings remain required.

**Cost:** export tests must exercise the emitted direct calls and compare complete inputs. Shared
form tests must prove settings survive page and node edits without duplicate state or submission.

**Revisit if:** an existing scientific function cannot express a supported job configuration;
report that limitation rather than creating notebook-specific science.


### 2026-09-13 — Remove the graphical pipeline feature

**Decision:** remove the Canvas page, graph documents/API, graph execution adapters and graph-to-notebook
export. Architecture §7.3 is retired without renumbering. Standalone Notebooks, dedicated processing
pages, scientific functions and job groups remain supported.

**Why:** the maintainer requested complete removal instead of maintaining the graphical workflow layer.
This reverses the Canvas decisions of September 5–6 and September 11; the shared processing controls
and standalone notebook workflow remain useful independently.

**Alternatives rejected:** hiding the navigation entry would leave an unsupported graph API and
execution path. Retaining graph import/export would preserve the same maintenance surface.

**Compatibility:** existing graph files are not migrated or deleted from user projects. They are no
longer executable by the application. Existing notebooks remain ordinary editable Python notebooks.
React Flow is removed with its only consumer; notebook dependencies remain for standalone notebooks.


### 2026-09-13 — Replace browser embedding with managed native TetraVox

**Amended 2026-09-19:** native-only viewing remains; pinned-version ownership and setup consent are replaced by automatic initial setup and TetraVox-owned updates.

**Decision:** remove the browser viewer transport, bundle installation/update service and iframe
presentation. Full scenes and volume/target previews open native TetraVox explicitly; the run pages'
existing WebGL2 surface renderer remains. The desktop installs the official pinned 0.4.0 platform
package into its per-user runtime directory after SHA256 verification, then opens project scene
paths with a separate viewer profile. TetraVox runs with host-user permissions, without an
additional TI-Toolbox operating-system sandbox. No new live external control channel is introduced.

**Why:** the maintainer requested native-only viewing and removal of the duplicate integration
surface. This reverses the September 4 embed-convergence/protocol-range/update policy and later
iframe viewport decisions. Scene generation, scientific coordinate distinctions and project-native
selection/scene storage remain useful independently. Dedicated embedding code is retired in both
projects; native rendering, scene loading, CLI and batch interfaces remain TetraVox responsibilities.

**Compatibility:** browser sessions can prepare/download scenes but cannot launch host software;
datasets must be reachable from the viewing host. TI-Toolbox saves prepared scene compositions;
TetraVox saves camera and appearance changes made in its own window. The pinned 0.4.0 release
predates TetraVox's new external-manager updater refusal, so that protection is not claimed for
currently downloaded artifacts. An upstream release containing it is needed before relying on it.

### 2026-09-13 — Bounded Viewer workspace and scene reference checks

Viewer uses a scene builder on the left and native launch controls above a saved-scene library on the right. Each panel owns its scrolling so a growing library cannot stretch the page. Scene deletion removes only the saved document and its thumbnail/metadata; filesystem failures remain visible for retry. The scene-list API adds optional reference-health metadata from bounded JSON reads and project-local file checks, without loading scientific datasets or probing arbitrary external paths. External references are explicitly unchecked rather than reported as available. These checks describe file availability, not scientific validity or native rendering success.

### 2026-09-15 — One resolution order for TetraVox, and updates without a TI-Toolbox release

**Superseded 2026-09-19:** initial setup only; TetraVox owns updates and system/PATH installations precede the TI-local copy. See the native lifecycle decision below.

**Decision.** A single rule picks the viewer: a path the user located in Settings, then the managed
copy TI-Toolbox installed, then a compatible system installation, then a compatible executable on
PATH. Identity and version are still checked at every step and no candidate is executed to identify
it. The managed copy is version-addressed under `runtimes/tetravox-<version>-<platform>-<arch>`, so
Settings can check GitHub for the newest release on demand and install it after verifying the
SHA512 the release's own `latest-<os>.yml` update feed publishes for that exact asset; the pinned
baseline 0.4.0 keeps its SHA256 so a first install works without a feed. A release that publishes no
checksum for this platform's asset installs nothing. Downloads run in the main process, stream to a
temporary directory, are verified, moved into place atomically and report progress to the renderer;
older managed versions are pruned after a successful update. Update checks are never automatic.

**Why.** The maintainer asked for detect-or-download with an explicit override, and for TetraVox
updates that do not wait on a TI-Toolbox release. Amends the 2026-09-13 decision below in one
respect: the managed copy now outranks a system installation, because only the managed copy has a
verified update path TI-Toolbox controls — which also removes the "reuse the sole running managed
copy" special case. A user who prefers their own installation says so once with **Locate TetraVox…**.

**Cost.** TI-Toolbox trusts the release's published update feed for non-baseline versions rather
than a digest reviewed in this repository. Windows managed setup still awaits a verified portable
package. **Revisit if.** TetraVox publishes signed checksums, or ships an installer TI-Toolbox
should defer to.

### 2026-09-13 — Reuse installed native viewers and confirm scene replacement

**Amended 2026-09-15:** the managed copy now precedes a system installation in the resolution order.

Compatible system installations take precedence over creating a managed copy; the sole running managed copy is reused instead when applicable. Discovery checks package identity and version in conventional locations without executing candidates. System launches keep the normal profile and updater ownership; managed launches retain their separate profile. This amends the earlier always-managed native installation decision.

TetraVox exposes second-instance file handoff but no public query for unsaved scene state. TI-Toolbox therefore confirms scene replacement whenever the selected application is running or process inspection is unavailable. It serializes requests, freezes the selected executable for consent and launch, and revalidates project access after confirmation. Blank launches only focus/open the application. A successful process handoff is not proof of completed scene rendering; an external application launch racing the final process check remains outside this coordination.

### 2026-09-13 — Evaluated optimizer candidates and explicit replay

**Decision:** retain valid Flex evaluations as scalar CSV records plus full-precision electrode poses,
joined by candidate ID and accompanied by a configuration/metric manifest. Ex uses its existing CSV.
One Results browser shows sortable estimates and the frontier among displayed comparable candidates.
A selection becomes an editable Simulator draft, with provenance and no automatic execution.
New desktop Flex jobs use intensity or threshold-free contrast; legacy threshold-based configurations
are not silently reinterpreted. The durable record and replay scope is ARCHITECTURE §13; verification
and its limits are in TESTING's optimizer candidate section.

**Why:** a single returned optimizer solution hides useful alternatives and a finite objective does
not establish convergence. Threshold selection can produce an uninformative objective landscape.
Recorded alternatives make the limitations and the montage-to-simulation transition inspectable.

**Cost:** streamed geometry and metrics add disk I/O. Background observations for intensity remain
opt-in until real-head time/RSS checks meet the approved budget. No full-field history, surrogate
optimizer, exhaustive-search claim or cross-domain objective comparison is introduced.

**Revisit if:** observed overhead exceeds the budget, the standard Simulator cannot reproduce a
candidate geometry, or scientific validation finds the contrast unsuitable. Such cases must be
reported rather than hidden by approximate replay or permissive success handling.


### 2026-09-13 — Developer Flex uses the checkout integration

**Decision:** resolve the Flex patch relative to the running TI-Toolbox checkout, under a separate
SimNIBS sibling module name. Do not overwrite the container's installed package. Wheel deployments
without the source resource retain the installed-runtime capability guard.

**Why:** the developer loader mounts Python code but cannot refresh dependencies copied during image
build. The new builder guard exposed that mismatch; the earlier custom benchmark loader bypassed it.
Tests now exercise the production resolver and ordinary Flex CLI path. **Cost:** one source-module
load per worker. **Revisit if:** integration packaging moves wholly inside the Python distribution.

## 2026-09-13 — Restore the requested Flex objective definitions

The maintainer corrected the candidate-review objective presentation: Mean TImax, Max TImax
(ROI 99.9th percentile), and Focality. This supersedes the preview labels Target intensity,
Target peak, and Target/background contrast. Focality now uses mean ROI / mean non-ROI, with
the existing ROI exponent `1 + intensity_weight`; weight zero has no absolute-intensity
preference. The earlier p95 denominator is not the requested focality definition. Historical
records and study measurements retain their original definitions; new manifests identify the
mean-denominator score. See §13 of ARCHITECTURE.md and TESTING's Flex objective regression case.

## 2026-09-13 — Link candidate history, trade-off plot and montage

The maintainer requested an intensity–focality scatter plot beside the table with shared selection.
Reuse the existing native WebGL montage renderer rather than add a 2D projection. Plot loading is
independent of the table page; selection navigates to the appropriate row. Missing non-ROI
measurements are not synthesized. Frontier claims remain limited to compatible recorded points.
See ARCHITECTURE §13 and TESTING's optimizer candidate and replay checks.


Cap placement follows the same selected-candidate identity: map that record rather than the run winner, keep the original poses for restoration, and clear poses when cap labels determine placement. Existing one-to-one Euclidean assignment is reused. The preview shows original-to-cap displacement in millimetres; this is not a scalp-geodesic calculation.


## 2026-09-14 — Explicit simulation outputs and optimizer choices

At the maintainer’s request, MNI conversion follows its opt-in flag end to end, with the control
beside fsaverage. Ex preview counts follow the engine enumeration and current splits rather than
assuming symmetry reduction. Flex restores threshold-based choices beside threshold-free focality;
Multi-threshold names the existing `pareto` strategy without claiming a Pareto-front algorithm.
This supersedes the desktop restriction to three goals in the September 13 presentation decision.
Scientific objective definitions remain unchanged. See ARCHITECTURE §8.


## 2026-09-14 — Inspect volume targets in the shared surface viewer

The maintainer requested local volumetric atlas surfaces and access to buried regions. Reuse the
run-page renderer with per-label visibility and picking. Peeling and isolation preserve anatomical
coordinates; exploded displacement was rejected because it adds picking and coordinate ambiguity.
Atlas metadata determines default subcortical visibility; explicit selections remain available.
This replaces the native-only volumetric preview decision in ARCHITECTURE §7.2; native viewer
export remains available independently. Cached meshes are display approximations, not analysis inputs.


## 2026-09-14 — Bundle atlas guides instead of building subject previews

Supersedes the earlier local-volume-surface and peel decision above at the maintainer’s request.
Atlas browsing now reads precomputed Ernie surfaces through the existing guide endpoints, with
synchronized target selection and translucent skin. No peel/isolate controls or request-time atlas
meshing remain. Individualized inspection belongs in native TetraVox; actual Simulator XYZ
placement still requires subject geometry. See ARCHITECTURE §7.2.

## 2026-09-15 — One launch model for users and developers

**Decision:** There is a single launcher implementation. `loader.py` (backed by `tit.cli`) and the
Python-free `loader.sh` each own one code path, and a `--dev [DIR]` flag — equivalently
`TIT_DEV_REPO_DIR`, or `TIT_DEV=1` — switches only the *source* of the server and renderer:
the checkout mounted at `/ti-toolbox`, `TIT_SERVER_RELOAD`, and `TIT_STATIC_DIR` pointing at the
checkout's built renderer. Everything else is identical in both modes: the flag set
(`--desktop`/`--browser`/`--no-open`), browser-by-default UI opening, port selection, the project
hash and container name, attach/recreate prompts and stop semantics. `--print-config` prints the
resolved settings without touching Docker and produces byte-identical output from every front
door. `dev/loader/loader_dev.{sh,py}` are now thin shims that only select a checkout, and
`dev/loader/docker-compose.dev.yml` is deleted — its three overrides are already parameters of the
root `docker-compose.yml` and are now set in one place.

**Why:** the user and developer paths had drifted (Electron-by-default for the Bash dev loader,
browser for the user one; `--build`/`--web`/`--no-mount-repo` living only in a second Python
launcher; a dev compose file that the shims did not even reference, since they looked for
`dev/loader/docker-compose.yml`). Divergent launch behaviour meant developers were not exercising
what users run. **Cost:** `--dev` no longer opens Electron by default; add `--desktop` for the
Apple GPU consent flow. **Revisit if:** a developer-only setting appears that cannot be expressed
as a source override. Supersedes the launcher parts of "Explicit loader and development modes"
(2026-09-09); `loader.py` and `loader.sh` remain the user CLI entry points at the repository root.

## 2026-09-15 — One experience: the loaders bootstrap the desktop app

**Decision:** The desktop (Electron) application is the only user experience. `loader.sh` and
`loader.py` (implementation `tit/cli.py`) are bootstrappers for it: in user mode they resolve
`TIT_ELECTRON_EXECUTABLE`, then a managed install at `<data>/app/<version>/` (`~/Library/Application
Support/TI-Toolbox` on macOS, `${XDG_DATA_HOME:-~/.local/share}/ti-toolbox` on Linux,
`%LOCALAPPDATA%\TI-Toolbox` on Windows), then download the asset for the platform from GitHub
release `v<version>` of `idossha/TI-Toolbox` — the names electron-builder produces
(`TI-Toolbox-<ver>-arm64-mac.zip`, `TI-Toolbox-<ver>-mac.zip`, `TI-Toolbox-<ver>.AppImage`) —
verify its SHA256 against the release's new `SHA256SUMS` asset, install it atomically and prune
older versions. Any failure prints one reason and falls back to the browser; `--desktop` makes it
an error instead, `--browser` and `--no-open` skip the download, and `--print-config` reports the
decision as `desktop_executable` (a path, `download`, or empty) with no network. `--dev` is
unchanged: the checkout is mounted and Electron comes from `desktop/node_modules` via
`dev/launch-electron.sh`. Both loaders keep the resolution in one function named
`resolve_desktop_executable`; `tests/test_desktop_bootstrap.py` asserts the two agree offline.

**Why:** a separately maintained browser edition is a second product with its own defects, and the
features users actually need — native TetraVox viewing, Apple-GPU FastSurfer consent,
reveal-in-file-manager — require the Electron main process and cannot exist in a tab. Making the
loader fetch the app removes the "install the app *or* run the loader" fork: both now end in the
same binary. **Cost:** first run downloads ~120 MB, and the download can only work once a `v<ver>`
release with those assets is published; until then every user-mode run falls back to the browser.
**Revisit if:** a signed release cannot be produced for a supported platform, or a genuinely
browser-only deployment (a shared remote server) becomes a supported product.


## 2026-09-17 — The plan's numbers are the run's numbers (ADR row 32)

**Decision.** Three rules, one each for the three kinds of number the plan panel shows.

1. **CPUs come from the container, not the host.** `tit/cpu.py` is the only answer to "how many
   CPUs may this process use": cgroup v2 `cpu.max`, then cgroup v1 `cpu.cfs_quota_us` /
   `cpu.cfs_period_us`, then the effective cpuset, then `os.sched_getaffinity`, then
   `os.cpu_count()`, smallest wins, never below 1. `tit.jobs.eta`, `tit.jobs.scheduler`,
   `tit.surfer_settings`, `tit.pre.qsi.utils` and `tit.opt.ex.parallel` all call it. Memory is
   unchanged: it already came from the cgroup limit clamped by what is available.
2. **A solver receives what the plan promised.** The runner exports the admitted budget as
   `TIT_JOB_CPUS` beside the `OMP_NUM_THREADS`/`MKL_NUM_THREADS`/`NUMBA_NUM_THREADS` it already
   set, and every "use all the cores" default now reads it: `tit.opt.ex.parallel.resolve_n_jobs`
   (`n_jobs=-1`, the UI default, forked `os.cpu_count() - 1` workers behind a plan that said
   "2 CPU") and `tit.opt.flex` (SimNIBS got `cpus=None` behind the same "2 CPU"). The ex/mEx
   plan cost therefore reports the worker count the run will actually fork, and
   `POST /api/plan/pre` clamps `parallel_subjects` to what the scheduler's budget could admit,
   with a warning, so a plan never multiplies a per-stage cost into cores that do not exist.
3. **One documented estimate model per kind, or no number.** The models stay where they were
   written down (`tit/jobs/eta.py`'s module docstring) — `minutes = (fixed + per_unit × units) ×
   mesh_scale × system.factor / parallel`, with `units` the electrodes in the cap (leadfield),
   electrode pairs (sim), evaluated combinations (ex/mEx), multistart runs × DE budget (flex) or
   the stage list (pre) — and `tests/test_plan_accuracy.py` now checks each one against the
   measured run it was calibrated on, including the two-carrier SESSION of 366.46 s in
   [BENCHMARKS](BENCHMARKS.md#2026-09-13--flex-non-roi-observation-ernie-volume-smoke). Kinds with
   no measured baseline (analyzer, stats, FreeSurfer preprocessing) return `None` and the panel's
   new **Est.** tile shows a dash; where there is a number it is prefixed `≈` and its tooltip names
   the machine it was computed for and the benchmark page it came from.

**Why.** Every one of these numbers was read by a user deciding whether to press Run, and each was
wrong in a different direction: `os.cpu_count()` inside a container reports the Docker VM's cores
regardless of `--cpus`, the exhaustive searches oversubscribed the container by five times what
the plan showed, and a `parallel_subjects` request inflated the previewed cost by a factor the
scheduler would never admit.

**Cost.** An ex/mEx job now declares (truthfully) most of the container's CPUs, so two of them
queue rather than thrash. `tit/cpu.py` is one more module every layer imports.

**Revisit if** the constants drift from the machine they were measured on — the calibration tests
fail rather than the estimates quietly lying — or if per-job CPU limits (cgroups per job, not per
container) ever become real, at which point `TIT_JOB_CPUS` becomes an enforcement point.
## 2026-09-17 — One hidden directory for everything the toolbox can rebuild

**Decision:** Every regenerable file TI-Toolbox writes into a project now lives under one
dot-directory at the project root, `.ti-toolbox/`, created lazily by `tit.paths` and nowhere else:

```
<project>/.ti-toolbox/
    README                     says the tree is regenerable and safe to delete
    cache/scene/sub-<id>/      surface payloads the viewer panes stream (.tvsc/.gii + sidecars)
    cache/masks/sub-<id>/      MNI ROI masks warped into subject space for flex-search
    cache/stats/               per-volume intensity statistics for viewer windowing
    cache/storage/storage.json the project disk-usage scan behind the Overview page
```

`PathManager` is the single source: `dot_dir()`, `cache_root()`, `cache(*parts)`,
`ensure_cache(*parts)`, `scene_cache(sid)`, `mask_cache(sid)`, `viewer_stats_cache()`,
`storage_cache()`, plus the project-dir-taking `scene_cache_dir_for` / `mask_cache_dir_for` for
callers that hold a path rather than a manager. `tit.scene.cache`, `tit.viewspec`, `tit.storage`
and `tit.opt.flex.utils` all resolve their directory through it; none of them joins a cache path by
hand any more. `ensure_cache` is the only creator — it migrates legacy locations, writes the
README, and appends `.ti-toolbox/` to the project's `.bidsignore` so bids-validator ignores the
whole tree (the old per-cache `derivatives/ti-toolbox/scene_cache/` line in existing projects is
harmless and left alone).

What each thing the toolbox writes is, and where it stays:

| Written | Class | Location |
|---|---|---|
| `sub-*/`, `sourcedata/`, `derivatives/{SimNIBS,fastsurfer,freesurfer,qsiprep,qsirecon}` | user output | unchanged |
| `derivatives/ti-toolbox/{reports,stats,tissue_analysis,nilearn_visuals,nifti_average,visual_exports,logs,notes.txt}` | user output | unchanged |
| `code/ti-toolbox/config/` (settings, montages, `project_status.json`, `.initialized`) | project state a user may want to read and copy | unchanged |
| `code/ti-toolbox/jobs/` (spec/status/events/stdout per job) | project state — the run history | unchanged; already `.bidsignore`d, and under `code/`, not a scientific-output tree, so nothing moves and no job history is touched |
| `code/ti-toolbox/notebooks/`, `code/ti-toolbox/viewer/{scenes,presets,compositions,*.tetravox.json}` | user output — a person opens these | unchanged |
| `derivatives/ti-toolbox/scene_cache/` | cache | → `.ti-toolbox/cache/scene/` |
| `m2m_<id>/masks/.prepared/` | cache | → `.ti-toolbox/cache/masks/sub-<id>/` |
| `code/ti-toolbox/viewer/cache/` | cache | → `.ti-toolbox/cache/stats/` |
| `code/ti-toolbox/cache/storage.json` | cache | → `.ti-toolbox/cache/storage/storage.json` |
| `<ex-search run>/masks/` prepared masks, `<atlas>_labels.txt` sidecars beside their volume | cache, but provenance of the run/volume it sits in | left in place; they are part of what a user copies with the result |

**Migration:** on first `ensure_cache` for a project, each legacy location is *moved* — a plain
`os.rename`, so a 60 GB scene cache migrates instantly and nothing is rebuilt — and only when the
destination does not exist. A rename that fails (cross-device, read-only, a race) is ignored: the
legacy directory stays where it is and the new cache is rebuilt, which costs time, never
correctness. Nothing is deleted. Existing projects need no user action.

**Why:** a user opening their project saw six directories of toolbox bookkeeping mixed in with
their data, and one of them (`derivatives/ti-toolbox/scene_cache/`, 61 MB on Dataset 000 and
unbounded on a large one) sat inside the derivatives tree that is supposed to hold scientific
output. A single hidden, self-describing, deletable directory makes "what may I delete" answerable
without documentation, and the disk-usage page now attributes it to its own **Rebuildable cache**
kind. **Cost:** one more path family in `PathManager`, and a hidden directory is easy for a user to
miss when archiving — which is the point, but it does mean a `cp` that skips dotfiles drops the
caches (harmless) along with `.bidsignore` (not). **Revisit if:** a cache must outlive the project
directory (then it belongs in the user config dir), or a second tool needs to read these payloads.
## 2026-09-17 — `--dev` changes the source of the code, never the UI

**Decision:** `--dev [DIR]` (and `TIT_DEV_REPO_DIR` / `TIT_DEV=1`) no longer implies the browser.
`loader.sh` and `tit/cli.py::wants_desktop` resolve `ui=desktop` unless `--browser` or `--no-open`
is explicit, in dev mode exactly as in user mode. A checkout still takes Electron from
`desktop/node_modules` via `dev/launch-electron.sh`; when that is absent the helper now falls back
to the *installed desktop app* with `TIT_DEV_REPO_DIR` and `TIT_STATIC_DIR` set, printing the
`npm --prefix desktop ci && npm --prefix desktop run build` line it would have preferred, rather
than dropping to a browser tab. `--print-config` stays byte-identical between the two loaders in
dev mode, including the `--dev` with no `--project` case (the app opens its own project page).

**Why:** `loader.sh`'s `|| [ -n "$repo" ]` and `wants_desktop`'s `or root is not None` meant every
developer ran a *different product* from every user: no native TetraVox open
(`window.tit.openNativeTetravox`), no container GPU probe (`stack.ts::probeContainerGpu`), no Apple
GPU consent, no native file dialogs. Defects in exactly that surface could not be found by the
people writing it, which contradicts the 2026-09-15 "one experience" decision that this amends.
**Cost:** `bash loader.sh --dev` now needs either a built `desktop/out/main` + `node_modules` or an
installed TI-Toolbox app; a developer who wants the old behaviour types `--browser`. The built
renderer (`desktop/out/renderer`) is still required because the container serves it as
`TIT_STATIC_DIR`. **Revisit if:** Vite HMR inside Electron (`ELECTRON_RENDERER_URL`) becomes the
default dev renderer, at which point the built-renderer precondition can be dropped.

## 2026-09-17 — Detached islands in `labeling.nii.gz` are upstream, and are removed at the ROI

**Diagnosis first.** A user reported Left-Putamen rendering with a detached blob and grey debris
far from the putamen. Measured in the container on the packaged Ernie head model
(`scipy.ndimage.label`, 26-connectivity, per label of `m2m_ernie/segmentation/labeling.nii.gz`):

| region | components | voxels | minor | minor % | farthest minor centroid |
|---|---|---|---|---|---|
| Left-Putamen | 10 | 6109 | 77 | 1.26 % | 38.2 mm |
| Right-Thalamus-Proper | 13 | 7346 | 70 | 0.95 % | 44.3 mm |
| Right-Putamen | 3 | 5727 | 3 | 0.05 % | 13.2 mm |
| Left-Hippocampus | 2 | 4298 | 2 | 0.05 % | 19.4 mm |

Left-Putamen is one 6032-voxel body, one 67-voxel blob 36.9 mm away, and seven specks of one or
two voxels 22–38 mm away — exactly the screenshot. **Verdict: upstream charm labeling, not our
pipeline.** `tit/scene/volume_surfaces.py` was doing its job: it crops to the label's bounding box
and runs marching cubes over every voxel of the label, islands included. The left/right asymmetry
(10 components against 3 for the same structure in the same subject) is what rules out a
systematic bug of ours; a crop or affine defect would not be lateralised.

**Decision:** the cleanup lives in `tit/atlas/islands.py` and is applied to the ROI *mask*, not to
the picture. A connected component is kept when it has at least `max(5 % of the largest component,
50 voxels)` voxels; the ratio distinguishes a genuinely bipartite structure from debris, and the
50-voxel floor keeps a small region (Ernie's Optic-Chiasm is 90 voxels) from collapsing to one
component. Removed voxel counts are logged. `TIT_ROI_KEEP_ISLANDS=1` disables it everywhere.
It is applied in flex (`_subcortical_mask_lists`), ex/mEx (`atlas_roi_entries`), the analyzer's
voxel ROI and `volume_surfaces.surfaces`, so the pane draws the voxels that will be optimised and
measured. A label that is already one body is untouched and no file is written, so the common case
is byte-identical to before.

**Why not leave it:** the islands were never only cosmetic. 77 voxels sitting 37 mm outside the
putamen are averaged into the ROI field and into a focality denominator exactly like the other
6032. **Cost:** a subcortical ROI with islands now differs, by ~1 % of its voxels, from what the
same config produced before; flex and ex write a small derived `.nii` under
`<masks>/.prepared/` for those labels. **Known gap:** the *packaged* reference guide
(`tit/scene/guide/`) was frozen from Ernie before this change, so the bundled subcortical preview
still shows the islands until `python -m tit.scene.guide_build --project <ernie project>` is re-run
and its assets committed. **Revisit if:** a subject's segmentation is legitimately multi-component
at these ratios, or SimNIBS fixes the labeling upstream.

## 2026-09-17 — One space, two controls; the pane draws the subject, or MNI152

**Supersedes the 2026-09-06 native-panes rule "what it draws is the fixed guide, never the selected
subject" (R4).** That rule bought three things — a pane that paints on a project with no head
model, no cache-cold 184 MB extraction on every subject tick, and no subject-RAS coordinate picked
off someone else's anatomy — and cost the one thing the pane exists for: showing *what will
actually be optimised*. charm's islands, an atlas a subject does not have, and an MNI atlas warped
into this particular head are all invisible on a stand-in. The user's decision (2026-09-17) is that
the pane draws the head the row names.

**1. One value, two controls.** Every `RoiValue` mode carries one `space: "subject" | "mni"`;
`SubcorticalRoiValue.atlasSpace` is renamed to it and `CorticalRoiValue` gains it. The Subject | MNI
segmented control appears **twice** — above the scene pane (`TargetPreview`) and inside the ROI
picker's panel — and both are the same `<RoiSpaceControl>` reading and writing that one field, on
the Optimizer and on the Analyzer. *Failure it prevents:* two fields let a user set MNI above the
pane, leave the picker saying Subject, and get a job that ran on whichever one the config builder
happened to read. Switching space clears an atlas and its regions (they are space-specific) and
says so in one sentence; coordinates, radii, mask paths and saved-ROI names are kept, because
reinterpreting them in the new space is exactly what asking for MNI means.

**2. Subject space draws the row's subject.** `<ScenePane subject=…>` already existed for the
Simulator's free-hand placement; the targeting panes now pass it. Three states, each a sentence,
never an error box: *building* (the scene routes' own 202, polled), *no head model yet* (the
packaged guide is drawn and the server's 404 detail is quoted verbatim), *error* (verbatim). The
islands cleanup applies to the drawn subcortical surfaces, so the putamen debris is gone in subject
mode by construction rather than by a second fix.

**3. MNI space draws MNI152.** A second packaged guide, `tit/scene/guide-mni/`, built by the same
`tit.scene.guide_build` from the `mni152` example head, carrying the MNI152 skin and grey matter
and the shipped MNI atlases as pickable label surfaces. `tit.scene.guide` and `/api/guide/*` gain
one `guide` id (`default` | `mni`), checked against a dict the server wrote itself; there is still
no `subject` parameter anywhere in those routes. The manifest answers `guide_id` and `guides[]`, so
the pane offers only the anatomy this installation actually has.

**4. MNI at job start.** Every runner that accepts an MNI ROI (flex, ex/mEx, recip, analyzer)
transforms it into the subject with `mni2subject` *first*, then writes `roi_confirmation.png` (three
orthogonal slices of the subject-space mask on the subject T1 at its centroid) and
`roi_confirmation.json` (centroid in subject RAS, voxel count, GM overlap fraction) into the job's
own output directory, and prints one line. *Failure it prevents:* a silently misplaced ROI is the
one error in this pipeline that no later number can reveal — every metric downstream is
self-consistently wrong.

**Cost:** the targeting panes now issue per-subject scene requests, so ticking a new subject can
cost a cold build (the 202 state is what makes that legible); the installation carries a second
packaged guide. **Revisit if:** the per-subject build cost on a large cohort makes the pane feel
slow enough that a "draw the guide instead" preference is worth having.
## 2026-09-17 — ROI plates: framing rules, two renderers, host-side TetraVox pass *(superseded the same day — see “One scene per target”)*

**Decision:** `tit/figures/roi_plate.py` replaces the MNI-only matplotlib confirmation
(`tit/roi_confirmation.py`, which is now its caller). Three parts:

**1. The ROI is centred in the view and fills it, by a rule that is written down.**
`plan_framing` reads the subject-space mask and returns the cursor and the zoom, recording in the
sidecar which of five rules it used. *single*: one region — cursor at its centroid, **snapped to
the nearest in-mask voxel**, because a C-shaped hippocampus's centroid is in the ventricle beside
it; zoom so the bounding box fills 60 % of the panel with a 4 mm margin, one zoom shared by all
three panels so the scale bar means the same thing in each. *union*: several regions spanning
**≤ 60 mm** (bilateral thalami, an ROI union) — one row, cursor at the union's centroid snapped
into the **largest** region, zoom to the union. *per-region*: several regions spanning more than
60 mm, where one zoom would shrink each to nothing — one A/B/C row per region, largest first, each
with its own cursor and zoom and labelled with its name and voxel count, four rows at most and the
rest counted in `omitted_regions`. *sphere*: the centre and radius the user typed, not the
rasterisation's centroid and bounding box. *empty*: no plate, a JSON naming the reason and one
terminal line. 60 mm is a little over both thalami plus the third ventricle: wider than that is two
targets, not one. Connected components below `max(10 voxels, 2 % of the largest)` are *islands*,
not regions — a real segmentation label carries dozens of single-voxel specks and each would
otherwise be a row — and they are drawn in the largest region's colour and counted.

**2. Two renderers, one framing.** matplotlib in the container (so a headless run still gets a
plate) and TetraVox on the host (so the plate and the viewer the user inspects with cannot
disagree). The job document is written by the **Python** side, once, whoever runs it; Electron only
rewrites its absolute container paths to host paths. The mask TetraVox loads is the plate's own
region map written beside it, not the source file: for a binary mask the plan's region values are
*component* indices, and pointing TetraVox at the original made it colour and reveal labels that
were not in it — the first single-region plate came out with no ROI on it at all.

**3. The pass runs from Electron main.** The container cannot run TetraVox (a host GPU
application), so the job writes the matplotlib plate plus a `*.plate-request.json` and the job
document, and `desktop/src/main/roiPlates.ts`, on the `/ws/jobs` completion event, runs
`Tetravox --job … --quiet` offscreen per request and lets it overwrite the PNG in place. No
TetraVox, an unmapped path, a non-zero exit or a timeout: the matplotlib plate stands and one line
goes to the log.

**`TETRAVOX_VERSION` stays 0.4.0.** Every action these documents use (`figure`, `mmPerPx`,
`labelColors`, `visibleLabels`, `threshold.mode`, `save-scene`) was verified by running the real
plates against the installed **0.5.2**, and the resolution order accepts any 0.4+ install, so the
pass works on both. Bumping the managed-download baseline needs the three per-platform release
SHA256s, which is a release-engineering change with none of this feature's risk; it is left to
whoever next touches the download.

**Cost:** two extra NIfTIs beside each plate (the region map, and the field masked to the ROI) and
one extra GPU process per job on the host. **Revisit if:** a batch of many targets makes the
per-job TetraVox pass (capped at 8 plates) contend with the user's own window, or if TetraVox
gains a `figure` whose panels may each carry their own cursor — a per-region plate is matplotlib
only today for exactly that reason.

## 2026-09-17 — One scene per target: `roi.tetravox.json` and nothing else

**Supersedes “ROI plates: framing rules, two renderers, host-side TetraVox pass”** (above, same
day). That design left, per target, `roi_mask.nii` (125 MB), `roi_plate_roi.nii` (125 MB),
`roi_plate.png`, `roi_plate.json`, `roi_plate.plate-request.json` and `roi_plate.tetravox-job.json`
beside an analysis's own four files. Maintainer, on seeing one such directory: *“We are saving too
much information … only create a simple `.json` scene compatible with Tetravox and TI-Toolbox's
architecture, quick and lightweight, that points to the existing outputs inherent to the operations
themselves.”*

**Decision:** every optimizer and analyzer target leaves **one file**, `roi.tetravox.json` — a
Tetravox `ViewSpec` v2, the same format *File ▸ Save Scene* writes and *Open in Tetravox* reads —
and the analyzer's field target leaves a second, `roi_field.tetravox.json`. Four consequences:

**1. The scene references files that already exist.** The subject's `m2m/T1.nii.gz`; for a
subcortical or mask target the **atlas or mask the user named**, with `visibleLabels` and
`labelColors` selecting and colouring the target's labels; for a cortical target the hemisphere's
`surfaces/<hemi>.central.gii` with the `.annot` attached through `sidecars.fields` and
`annotation.visibleLabels` selecting the region; for the field scene the analysis's **own**
`TI_max` volume with the threshold the ROI's p99.9 sets. Nothing is rasterised, resampled or copied
to make any of it. `_annot_mask` is gone: a cortical cursor comes from the labelled vertices of the
central surface, in memory, and no file is written to get it.

**2. `visibleLabels` on a `.annot` names the packed FreeSurfer id, not the dense index.**
`read_annot` returns an index into the colortable and that is what selects the vertices;
`crates/tvx-mesh-io/src/freesurfer.rs` builds `LabelEntry.id` as `r | g << 8 | b << 16` and
`layers/mesh.ts::buildLabelPalette` matches on **that**. Sending the dense index matches no entry,
every label's alpha goes to zero, and the parcellation renders as nothing at all — which is exactly
what the first cortical scene did.

**3. One legitimate intermediate, and only for MNI.** An MNI target is not the ROI that runs and
exists in no file the user has, so the transformed mask is written once — compressed `uint8` on the
**atlas's** voxel grid, not the subject's 0.5 mm conform grid. CIT168 label 1 into sub-101:
**15.9 KB**, against the 125 MB the same mask cost on the T1 grid.

**4. Paths are relative to the scene.** That is the one addressing correct both in the container
that writes the scene and on the host that opens it, so nothing re-roots anything: `roiPlates.ts`
no longer rewrites a document, and *Open in Tetravox* on the artifact row opens the file directly
(`viewableKind` returns `"scene"` for `*.tetravox.json`; `useOpenInViewer` skips `openView` for one).

**What was deleted.** The matplotlib renderer, `roi_plate.json`, `*.plate-request.json`,
`*.tetravox-job.json`, `roi_plate_roi.nii`, `roi_mask.nii` on the T1 grid and `*_field-in-roi.nii`.
The numbers the sidecar carried — centroid, voxel count, GM overlap, framing rule, per-region counts
— are in the scene's own `meta` block (Tetravox's `parseScene` checks `version`, `datasets` and
`layers` and carries every other key through) and in the one terminal line, which stays.
`plan_framing` stays: it is small, pure and the reason the ROI is centred and fills the view.

**The picture is optional and host-side.** `desktop/src/main/roiPlates.ts` builds a three-line
`--job` document *from the scene, at that moment, never persisted*, runs Tetravox offscreen and
writes `roi.png` / `roi_field.png` beside the scene. No Tetravox, a non-zero exit or a timeout: one
log line, and the scene is still there. The PNG is not in the job's artifact list — the server has
no endpoint to add one after a job ends — but it is in the job's own folder, which *Open folder*
reaches.

**Verified in the container** (`idossha/ti-toolbox:v3.0.0`, Dataset 000, sub-101) for a subcortical
label, a bilateral cortical `.annot`, an MNI CIT168 label, a sphere and a mask analysis with its
field; each directory held the operation's own outputs plus the scene(s), and all five scenes were
then rendered by the installed Tetravox 0.5.2 with `--job`.

**What Tetravox cannot draw yet.** A **sphere** target: `ViewSpec` has no marker or sphere layer
(`sphere` exists only inside a mesh `IsolateSpec`), so a spherical ROI's scene is the T1 with the
crosshair on the centre and the zoom set by the radius, and the smallest addition that would fix it
is a points/sphere layer kind with a centre, a radius and a colour. A cortical target's regions all
take the `.annot`'s **own** colours rather than one palette colour per region, because
`SurfaceLayer.annotation` has no `labelColors`; the smallest addition is that field, mirroring
`VolumeLayer.labelColors`.

**Cost:** a mask analysis writes two small JSON files instead of one picture, so a person who wants
to *see* the ROI without a viewer needs Tetravox installed. **Revisit if:** that turns out to matter
for a headless or CI reader — the answer would be a Tetravox CLI render in the container, not a
second renderer in Python.

## 2026-09-17 — One loader, `--dev` is a bind mount, `loader_dev` is gone

**Decision:** `loader.sh` and `loader.py` are the only entry points. `dev/loader/loader_dev.sh`
and `dev/loader/loader_dev.py` are deleted, and every reference now reads `bash loader.sh --dev`
or `python3 loader.py --dev`. `--dev [DIR]` — default: the checkout the loader file lives in —
bind-mounts that checkout at `/ti-toolbox` exactly as the v2 dev loader did, so `tit/` edits are
live under the server's reloader and the renderer served is the checkout's `desktop/out/renderer`.
When that bundle is missing or older than `desktop/src`, the loader builds it (`npm --prefix
desktop run build`, preceded by `npm ci` when `node_modules` is absent) after printing one line,
instead of telling the developer to; `TIT_DEV_NO_BUILD=1` opts out. No `--dev` is a regular user
run. With no arguments at all, both loaders open the desktop app's own project page and never say
"pass --project"; `--browser` keeps the terminal welcome prompt. On WSL2 a Windows `--project`
path is translated to `/mnt/<drive>/...` in both loaders (`translate_project_path`); macOS and
Linux are unchanged.

**Why:** three scripts implemented one idea. The shims only exported `TIT_DEV_REPO_DIR`, which
`--dev` already means, and every doc had to explain which of the three to type; the loaders had
also drifted apart on `--print-config` with no project (bash demanded one, Python printed an empty
line). The build instruction was the other half: a developer who forgot `npm run build` got an
error telling them to run a command the loader could run itself. **Cost:** a `--dev` start can now
take a minute on its first run while npm builds, and `TIT_DEV_NO_BUILD=1` is a new thing to know
when running `npm run dev` beside it. **Revisit if:** the renderer moves to Vite HMR inside
Electron by default, which would remove the built-bundle precondition altogether.

## 2026-09-17 — An atlas manifest with a kind, one documented MNI transform, and the licence table

**Context.** Two user reports, and one thing behind both: nothing in the repository said what a
shipped MNI atlas *is*. The MNI list was `MNI_ATLAS_FILES`, four filenames in
`tit/atlas/constants.py`, so the ROI picker could not tell a surface parcellation from a label
volume and offered every packaged MNI atlas to whichever mode asked; and flex-search, having no
reason to treat an MNI label specially, passed SimNIBS the whole multi-label atlas with
`mask_space="mni"` and let it warp internally. Every MNI run also printed
`RuntimeWarning: invalid value encountered in dot` from `simnibs/utils/transformations.py:147`,
which was read as a failed registration.

**Decisions.**

1. **`resources/atlas/manifest.json` is the one description of every shipped MNI atlas** — file,
   `kind` (`volume` | `surface`), template space, labels/LUT file, licence, required attribution,
   `redistribution`, citation. `tit/atlas/manifest.py` is the only reader; `MNI_ATLAS_FILES` and
   `DEFAULT_MNI_ATLAS` survive as lazy re-exports resolved from it (lazy because reading a file at
   import time trips `dev/route_import_guard.py`). `GET /api/catalog/atlases` serves the MNI list
   from the manifest with `kind` on every row and filters by the asking mode; subject-space atlases
   carry the same `kind`, still detected from the extension. `kind` describes the **file**, not the
   anatomy: Glasser HCP-MMP1.0 is a cortical parcellation distributed as a label volume, so it is
   `volume` and is targeted through the subcortical/volumetric flow. All four shipped MNI atlases
   are volumes; a surface one would route to the cortical flow without further change.

2. **An MNI atlas label is warped into the subject by TI-Toolbox, once, before anything else.**
   `tit/opt/flex/utils.py::_mni_labels_to_subject` binarises the label, calls
   `tit.opt.masks.prepare_mask` (SimNIBS `mni_mask_to_sub`, nearest-neighbour), cleans islands in
   *subject* space, and hands on a subject-space binary NIfTI with mask value 1 — byte-for-byte the
   shape a subject-space target already produced. The transform is now the only difference between
   an MNI target and a subject one. Before this the island cleanup ran on the atlas in MNI voxels
   and the ROI confirmation plate, which documents itself as making "the same `prepare_mask` call
   the runner makes", transformed a different thing from the search.

3. **The `dot` RuntimeWarning is noise and is suppressed at our one call site.** SimNIBS samples
   the deformation field with `cval=np.inf` (`transformations.volumetric_nonlinear`, SimNIBS 4.6,
   line 142), so every target voxel outside the warp's field of view — the corners of any subject's
   T1 grid — arrives as infinity, is multiplied by a zero off-diagonal term on line 147 and becomes
   NaN, then samples as background, which is correct. `prepare_mask` filters exactly that message
   and checks the *result* (a mask that does not overlap the subject is still an error).

4. **The template mismatch is accepted and measured, not corrected.** SimNIBS's warps target
   `file_finder.Templates().mni_volume` = FSL's `MNI152_T1_1mm.nii.gz` = **MNI152NLin6Asym**;
   `charm` writes `m2m_<id>/toMNI/{MNI2Conform_nonl,Conform2MNI_nonl}.nii.gz` against it, and
   `mni_mask_to_sub` uses `conf2mni_nonl`. CIT168 and Glasser are MNI152NLin2009cAsym and MASSP is
   2009b, about 1.3 mm from NLin6Asym globally. We do **not** ship a TemplateFlow
   2009c→NLin6 resampling step. Measured on `ernie`, warped-label centroid against `charm`'s own
   `labeling.nii.gz` centroid for the same structure: CIT168 putamen **1.05 mm**, CIT168 caudate
   **2.20 mm**, MASSP thalamus left **2.00 mm**, right **1.19 mm**. That is the same order as the
   disagreement between two segmentations of one structure, so a second interpolation would cost
   more than it buys. The ROI plate every job writes is the per-run check that replaces it.
   (MASSP *Striatum*-left against charm's Left-Putamen is 6.75 mm and is not a transform error —
   striatum is putamen **plus** caudate.)

5. **Morel stays shipped and stays flagged.** It is CC BY-NC-SA 4.0, which a GPL-3 project cannot
   redistribute; the manifest carries `"redistribution": "no (CC BY-NC-SA)"`, and the README and
   the wiki say it must move to an optional user-fetched download before the next release. It is
   **not** removed here — removing a shipped atlas changes what existing configurations resolve,
   and that is the maintainer's call. *(Reversed the same day: see the next entry.)*

## 2026-09-17 — Morel is removed; Harvard-Oxford, Cerebellum and Schaefer are added; a NOTICE file

**Context.** The previous entry left the Morel thalamus atlas shipped under a CC BY-NC-SA licence
and named it the maintainer's call. The maintainer made it: remove it now rather than carry a
non-redistributable file into the v3.0.0 image, and fill the gap with atlases whose licences a
GPL-3 project can pass on. The survey in `resources/atlas/README.md` already named the candidates.

**Decisions.**

1. **The Morel atlas is deleted, not moved.** `resources/atlas/MorelMNI152_labeling_1mm.nii.gz`,
   its LUT, and its `parts`/`atlases` entries and files in `tit/scene/guide-mni/` are gone; the guide was
   then rebuilt (`guide_build.py --atlases mni` against the `mni152/headmodel` example part in
   the container) — skin, gm, CIT168, MASSP and every net came out byte-identical, and the
   Harvard-Oxford (cortical and subcortical) and Cerebellum surfaces were added, so the MNI
   pane can draw them; Schaefer's 400 parcels exceed the 256-region surface budget and it is
   picker-only. The manifest gains a `not_shipped` list
   with the sentence a user must read, and `tit.atlas.manifest.not_shipped_message` /
   `check_shipped` are called at every boundary that resolves an MNI atlas name —
   `tit.opt.masks.validate_mask` (so `prepare_mask`, hence flex/ex/mEx and the analyzer's mask
   path), `validate_mask_paths`, `tit.opt.roi_spec.resolve_volume_atlas_path`, and the
   target-preview route — so a configuration that still names it fails with *"The Morel atlas is
   no longer shipped (CC BY-NC-SA); see docs/wiki/atlases.md"* and never with "file not found".
   The name survives only in the not-shipped notes (`resources/atlas/README.md`,
   `manifest.json § not_shipped`, `tit/scene/guide-mni/PROVENANCE.md`);
   `tests/test_atlas_manifest.py::TestNotShipped` greps `tit/` and `resources/` for it. The path
   to reinstating it as an optional download is written in the README's *Not shipped* section.

2. **Four label volumes are added, all on the template's own grid.** Harvard-Oxford cortical
   (48) and subcortical (21) maximum-probability maps at threshold 25, 1 mm, and the
   Cerebellum-MNIfnirt map (28), taken unmodified from the NeuroDebian `fsldata` 5.0.7-2 packages
   (URLs and sha256 in the manifest), CC BY-SA 4.0 by the FSL licence page's own sentence; and
   Schaefer 2018 400 parcels / 7 networks, 1 mm, from ThomasYeoLab/CBIG at commit `35b5664b`
   (MIT, `LICENSE.md` re-read). Each header was checked in the container against the shipped
   `MNI152_T1_1mm.nii.gz`: 182×218×182, 1 mm, identical sform — so they are MNI152NLin6Asym and
   need no template correction; the manifest records that under `grid`, and the test re-derives
   it from the NIfTI headers with no nibabel. The FSL LUTs are generated from FSL's XML with
   ids = XML index + 1 (what a `maxprob` image encodes), names hyphenated, colours ours; the
   Schaefer LUT is CBIG's own, so `roi_spec._find_volume_lut` now asks the manifest for a shipped
   atlas's `labels` file before falling back to the stem rules. Total added: 8 files (4 volumes, 4 LUTs), 680 KB.

3. **A repository-root `NOTICE` carries every third-party data notice.** Copyright holder,
   licence, required attribution (the HCP clause-5a acknowledgement verbatim, the MNI/McGill
   notice verbatim, CBIG's MIT text verbatim) and citation for CIT168, MASSP, Glasser, the
   MNI152 template and the four new files, plus the FreeSurfer colour tables. `LICENSE` points at
   it in one line and the README has a Licence section. `docs/wiki/atlases.md` and
   `resources/atlas/README.md` list the new atlases and the not-shipped note.

**What did not change.** The interactive atlas browser on the wiki page still shows CIT168,
Glasser and MASSP only (`dev/build_atlas_assets.py` was not re-run for the new files); a
follow-up, not a regression.

**Not done.** Harvard-Oxford, Cerebellum-MNIfnirt and Schaefer 2018 were **not** added. Schaefer's
MIT licence was re-verified from `ThomasYeoLab/CBIG/LICENSE.md`; the FSL licence page is a
client-rendered app and could not be re-fetched, so the CC BY-SA 4.0 claim for Harvard-Oxford and
Cerebellum still rests only on the 2026-09-17 survey in `resources/atlas/README.md`. Adding them
also means committing tens of megabytes of binaries to the repository and the image, which needs
the maintainer's decision, not an agent's.

## 2026-09-18 — An analysis folder is data, one histogram and one scene (amends "One scene per target")

**Decision.** An analysis leaves `results.csv`, `analysis.json`, the overlay it computed from
(`roi_overlay.msh` + `.opt`, or `roi_overlay.nii.gz`), **one** `histogram.png`
(`tit.analyzer.visualizer.save_histogram`: the whole-head distribution with bars coloured by
ROI contribution fraction, as the old PDF drew it, area- or volume-weighted, 150 dpi PNG) and **one** `scene.tetravox.json`
(`tit/analyzer/scene.py`) that points at that overlay: the field masked to the ROI over the
anatomy, cursor on the ROI, colour bar on. The analyzer's `roi.tetravox.json` (ROI only, no
field) and `roi_field.tetravox.json` (the whole unmasked field with a threshold, voxel only), the
600-dpi `histogram_histogram.pdf` (replaced by the PNG the same day — the histogram itself is
not optional, a folder without it fails `tests/numerical/test_analyzer_masks.py`) and the second
screenshot are gone; the host pass renders one
`scene.png` and removes Tetravox's `job-result.json` trace after logging it. Optimizers keep their
`roi.tetravox.json`: it is their target confirmation, written before the search.

**Why.** Maintainer: minimalism, one logical picture per operation, scenes that point at the
operation's own outputs. The ROI-only scene repeated what the field scene showed; the field scene
drew the *whole* field volume and hid it with a threshold, which is not "the ROI's field"; a mesh
analysis had no field scene at all, and a bare `roi_overlay.msh` opened as a flat single-colour
surface because Tetravox ignores `View[n].Visible` on open. The intent now travels in the scene:
the overlay's `<field>_ROI` node data (exactly `0` outside the ROI) coloured with the zeros hidden,
over the same mesh once more at 25 % opacity, `peel` transparency, the 3D pane large.

**Cost.** The overlay mesh drops the simulation's own whole-surface view (49 MB from 55; the field is
in the simulation's own file). A mesh `hide` threshold must carry a finite `hi` — Tetravox 0.5.2
floors the ramp at 1e-6 of `hi − lo`, so an open `hi` (3.4e38) hides the whole layer; the scene
writes twice the ROI max. `tit.plotting.plot_whole_head_roi_histogram` is removed with its module; the histogram lives in
the analyzer's own visualizer.

**Revisit if** Tetravox colours 2D mesh contours by field (the mesh scene's slice panes then show
the ROI's field, not only its outline), or Tetravox grows a `stats` result that could replace the
matplotlib PNG.

Verified in the dev container on `ernie` / `L_Insula` / `lh.insula` (DK40), mesh and voxel; both
scenes rendered headless with Tetravox 0.5.2 `--job`.

## 2026-09-19 — A job's CPU and RSS are the process tree's, and a finished job keeps its peak and average (ADR row 34)

**Decision.** `JobStatus` gains `cpu_percent_peak`, `cpu_percent_avg`, `rss_peak` and `rss_avg`
(`contracts/openapi.yaml`); `cpu_percent` and `rss` stay as the latest reading. All six are
read over the job's whole process tree — the runner's root plus `children(recursive=True)` —
by one `tit.jobs.runner.ResourceSampler` per running job, created when the pid appears and
dropped at finalize. The manager's 0.25 s tick still drains events; the sampler reads once a
second (`RESOURCE_SAMPLE_INTERVAL_S`). The average is a simple mean over counted samples, which
at a fixed cadence is time-weighted to within one interval; the peak is the maximum. Both are
persisted in `status.json`, so a finished job still says what it cost after a server restart.
The Jobs table's STAGE column is removed (the run pages' terminals show progress); CPU and RSS
show peak with the average beside it.

**Why.** The previous poll built a fresh `psutil.Process(pid)` every 0.25 s and asked it for
`cpu_percent(interval=None)`, a delta against a baseline that object never had — so every job
reported 0 % CPU for its whole life, and only the runner's own pid was measured, while
SimNIBS/PARDISO/FastSurfer do their work in children. A single latest value also told nobody how
much a run had actually cost. Keeping `cpu_percent`/`rss` avoids breaking `JobDetailPane` and
the stall detector, which now reads the tree's latest CPU.

**Cost.** One `/proc` walk per running job per second; a psutil-primed first sample per process
that is not counted, so a job shorter than two samples reports no CPU average (RSS still).
Re-adoption after a restart restarts the average with the new server life; the persisted peak is
kept.

**Revisit if** the stall detector needs a per-child view, or the UI wants a time series rather
than two numbers (then the samples belong in `events.jsonl`, not in `status.json`).

## 2026-09-19 — The Artifacts tab is the folder on disk; a runner registers where, not what (ADR row 35)

**Decision.** `GET /api/jobs/{id}/artifacts` returns the job's output folder and every file in
it (bounded walk, three levels, jailed to the project, with sizes) — `tit.catalog.output_files`,
the same walk `flex_runs`/`ex_runs` use for Results. The Jobs page's Artifacts tab shows that
list and counts it; `JobStatus.artifacts` stays the runner's *registered* outputs and is used
only to say **where** the folder is (a `dir` artifact first, else the directory of the first
file) and, on the Overview, which run a job was. The simulation runner now registers the
montage's directory (`dir`) before its mesh, as the flex runner already did.

**Why.** A run's tab said "Artifacts (3)" for an ex-search whose folder held ten files and
"Artifacts (2)" for a flex run with thirty-three: each runner remembered to register a
different handful, and a list maintained by hand in six runners can only ever be a subset of
what is on disk. The Results page never had this problem because it reads the folder.

**Cost.** One directory walk per tab open (re-read when the job's state or registered count
changes). A job that registered nothing — failed before writing, or `project_init` — still
shows nothing, because the server does not guess folders. A folder deleted since the run lists
as empty, which is the truth.

**Revisit if** a runner's outputs land in more than one folder (then the registered list
should carry several `dir` entries and the route should union them).

## 2026-09-19 — TI bootstraps TetraVox; TetraVox owns updates

**Decision.** Follow ARCHITECTURE §7.1: discover locally on launch, reuse an existing native app,
otherwise bootstrap
an official verified package automatically under TI user data. Keep updates inside TetraVox. Remove
TI's updater API and controls, release pin, update suppression and executable-hash lock across launches.

**Why.** The prior September 15 rationale said the managed copy won because it had a “verified update
path TI-Toolbox controls”. The maintainer now explicitly chooses one updater owned by TetraVox to avoid
confusion. The September 13 extra setup-consent step is also superseded by the requested automatic setup.
Initial archive verification remains necessary; ownership of subsequent versions does not belong to TI.

**Alternatives rejected.** Reinstating an embed adds an unrelated renderer integration. Disabling the
native updater preserves the duplicate ownership the user rejected. Treating Linux tar notification as
in-app installation, or assuming Windows ZIP/NSIS coexistence, would make unsupported platform claims.
Killing a busy viewer or forcing an X11 display to obtain focus risks user work or adds a dependency.

**Scope and evidence.** This is a staged implementation, not release acceptance. Native handoff reports
only a launch request until upstream provides a load receipt. Upstream packaging/window changes and the
real three-platform install/update/foreground matrix remain in ROADMAP. No new numerical behavior or
scientific dependency is introduced. The preload bridge removes its two native-update entry points;
its exact remaining surface is asserted by the smoke spec. Tests and their limits belong in TESTING.


## 2026-09-19 — Save the live native scene, not the builder recipe

**Decision.** Amend ARCHITECTURE §5 and §7.1 for live native scene saving. Remove Save selection and
Recent, retaining file-list Reset. Keep Save scene in the saved-scene library,
backed by TetraVox's actual serializer and a new `saveNativeTetravoxScene` bridge entry. The bridge count
is 21 (source contract, enforced by `smoke.spec.ts`). Capability is explicit, not inferred from version;
missing support disables the action. New snapshots use the project scene directory and never overwrite.

**Why and alternatives.** Saving the previously prepared recipe loses native camera/layer edits and
falsely claims to preserve the view. A success receipt must identify the requested live session and
saved path before the library refreshes. No TI updater or version pin is reintroduced. On macOS,
explicit bundle reopen follows file delivery because opening a file alone may leave the app minimized;
this requests activation without promising OS foreground authority.

**Delivery boundary.** The upstream serializer/request implementation is a concrete draft at
`dev/upstream/tetravox-live-scene`, not an applied or installed TetraVox change. Existing native builds
remain unable to satisfy live save. Unit fixtures and mocked IPC verify TI behavior; real native
serialization, no-window recovery and foreground acceptance remain release gates in ROADMAP.

### 2026-09-19 — Native scene capability applied upstream

The earlier draft-only delivery boundary is superseded: the request adapter, native controller save,
canonical Save As default and window recreation now live in the TetraVox `fix/ti-native-scenes`
checkout. TI retains capability detection for older installed builds. No viewer update or public
release was performed. The [upstream integration record](../../dev/upstream/tetravox-live-scene/README.md)
identifies the generic API and TI adapter; TESTING owns verification and ROADMAP owns outstanding gates.

### 2026-09-19 — Consume a generic TetraVox scene API

The maintainer rejected the TI-specific upstream protocol and native Save As redirection. TI uses
TetraVox's generic open/save requests with caller-selected paths and an optional expected attached path.
Project directory policy stays here; TetraVox does not know TI's BIDS layout or require a TI session.
This supersedes the upstream-specific session/default claims above.

## 2026-09-20 — Requirements are recorded directly in canonical references

**Decision.** The repository has no `docs/requirements` store. A durable behavior change edits
ARCHITECTURE, its rationale appends here, verification belongs in TESTING, open acceptance stays in
ROADMAP, and user-visible outcomes belong in CHANGELOG or the applicable release page. The
`documentation_policy.py` guard rejects the path itself, including an empty directory, file or symlink.

**Why.** Point-in-time proposals duplicated current truth and left inbound links to scaffolding after
implementation. Keeping one current contract and one append-only rationale makes later maintenance
resolve from canonical sources rather than reconstructing which proposal won.

**Alternatives rejected.** Archiving the files under another intent directory preserves the duplicate
source of truth. Ignoring the directory hides local files but does not prevent them from being forced
into a commit. The structural guard plus its fixture-driven self-test makes the policy executable.

## 2026-09-20 — Save the currently active TetraVox scene into the active project

**Decision.** ARCHITECTURE §7.1 captures the selected running native viewer without a prior TI open
or an `expectedScenePath` constraint. The active BIDS project supplies the destination; the native
viewer supplies the current serialized view. Capability and process readiness are checked afresh,
then project identity is rechecked before dispatch.

**Why.** Requiring a previous TI launch blocked scenes imported directly in TetraVox and could reject
an attachment changed since TI last opened it. The existing generic serializer already supports this
capture. Destination confinement, create-only files and correlated success receipts remain required.
`nativeSceneBridge.test.ts` covers direct capture and canonical destinations;
`nativeSceneSave.test.ts` covers project changes during readiness.

Native snapshots also reopen from their original jailed scene path. Re-exporting them resolved their
scene-relative datasets against the wrong root and could raise "Path escapes the project jail".
Legacy server-URL scenes still use the localizing exporter. This fixes existing native snapshots
without migration or relaxed filesystem confinement.


## 2026-09-20 — Saved-scene previews and inline information

**Decision.** ARCHITECTURE §7.1 uses the existing native `--job` screenshot API in a separate,
offscreen profile to cache a PNG beside each visible saved scene. No live-view replacement or
upstream API change is needed. The preview restores the saved grid and downsizes the render;
it is neither an anatomy substitute nor a decorative placeholder. `previewNativeTetravoxScene`
is one narrow validated IPC entry, bringing the preload surface to 22 entries (smoke test).

The existing bounded scene-health read also returns dataset/layer counts. Modified time comes from
mtime; created time is nullable and only sourced from filesystem birth time. An inline information
popover shows these values without expanding the row. Missing previews and metadata remain optional.


## 2026-09-20 — FreeSurfer licensing is supplied by TI-Toolbox

**Decision.** ARCHITECTURE §1 and §9 require automatic license provisioning for FreeSurfer,
QSIPrep and QSIRecon. Restore the existing v2 license as a Python package resource, so Docker,
Apptainer and package installations can resolve it without user configuration. Remove personal
license entry and registration prompts. Retain existing environment, stored-user and system-file
overrides for compatibility. A missing packaged license is a packaging failure, not a request
for user registration. FastSurfer segmentation needs no license.

**Why.** The maintainer requires the toolbox to supply the license on behalf of its users, as in
v2. This supersedes the 2026-09-18 personal-license decision and its unsupported claim that each
user must register individually. FreeSurfer's [registration page](https://surfer.nmr.mgh.harvard.edu/registration.html)
explicitly supports multi-user installations; preserve the applicable notices from the upstream
[Software License](https://surfer.nmr.mgh.harvard.edu/fswiki/FreeSurferSoftwareLicense), Part B, with the
bundled resource.

**Alternatives rejected.** Mandatory Settings entry moves a toolbox installation responsibility
onto every user and blocks otherwise valid jobs. Optional overrides remain useful for existing
scripts but cannot be a prerequisite. Never fetch a license or contact a registration service at
runtime.

**Verification contract.** With no environment override, saved license or system license, a fresh
installation resolves the packaged resource. FreeSurfer and QSI worker mounts receive that file;
the preprocessing UI contains no personal-license input or registration prompt. See
[TESTING.md](TESTING.md) for the host and container checks; completion requires actual test output.


## 2026-09-20 — Fast daily regression, full local release verification

**Decision.** Keep both existing CircleCI check names and all host Python/desktop unit checks;
remove the scientific test-image pull, combined host/numerical process and browser/Electron E2E
from ordinary pushes. Real numerical tests and full hidden/real workflows run serially before a
release via `dev/verify_release.py`, with explicit image, copied-project and package inputs, logs
and source/image identity. Image build verification remains explicitly requested.

**Why.** The maintainer requested quick daily regression and local long-process release testing.
CircleCI #1052, #1053 and #1057 actually failed Python assertions in approximately nine minutes
[measured: CircleCI v1.1 build records, 2026-09-20], rather than a confirmed one-hour timeout.
Their combined test-image run exposed missing Docker CLI, image SSL paths, scientific/mock state
and CPU quota fixture differences. Desktop #1054/#1056/#1058 were still reported running in the
E2E step at inspection. Moving slow checks does not waive those defects: host/science isolation
restores the documented two-process test model, and remaining platform failures still block their
own gate. New hosted timing must be measured before claiming a speedup.

**Alternatives rejected.** Widening timeouts does not fix assertion failures. Running an arbitrary
small unit subset loses cheap coverage. A new CI framework or automatic publication attestation
service is unnecessary; existing runners plus a fail-fast local wrapper preserve evidence.

**Verification.** CircleCI CLI validates the configuration. `tests/test_release_gate.py` executes
commands that return success, failure, inconclusive and no-tests codes; only success is accepted.
The full local wrapper requires real fixtures and is not claimed executed by these self-tests.
Its receipt is an operator review input, not a publication interlock; platform installer acceptance
and skip review remain required by TESTING and RELEASING.


## 2026-09-20 — Runtime thread defaults are absent from portable schemas

**Decision.** Express the three QSI `omp_threads` dataclass defaults with `default_factory`.
Runtime omission retains `QSI_DEFAULT_OMP_THREADS`; explicit caller values are unchanged. Generated
JSON Schema/OpenAPI omit the host-specific `default`, and generated TypeScript correctly permits
omission. The desktop's explicit resource preferences continue to own submitted thread counts.

**Why.** CircleCI #1070 exposed three generated defaults of 3 on its four-CPU host versus 8 in the
committed schema [measured: exact guard diff]. Byte guards correctly rejected the difference.
Hardcoding a generator CPU count or dropping byte checks would hide a build-host dependency.

**Verification.** `test_qsi_runtime_cpu_defaults_do_not_change_generated_schema` first failed on
unequal schemas, then passed: fresh processes model 1, 4 and 12 host CPUs, assert runtime defaults
1, 3 and 8 respectively, preserve explicit 2, and require identical full generated schemas with
no numeric OpenMP default. Existing packages remain evidence for their original source SHA;
publication artifacts incorporating this change must be rebuilt.


## 2026-09-20 — Manual Docker publication, automated executable releases

**Decision.** Restore the v2 separation: maintainers build, test and push the application image
manually; `release-build.yml` builds and verifies executable artifacts. Remove the image archive,
image-push job, Docker Hub secrets and redundant internal mode. Public executable publication
checks the version image's registry manifest for Linux amd64, then requires verified platform
artifacts and checksums before promoting a draft. Mutable version-line Docker tags remain supported.

**Why.** Run 35537639670 completed image construction and platform validation but failed at
Docker login with `Username and password required` [measured: run logs]. The user explicitly prefers
manual image distribution. Transferring a multi-GB image between hosted jobs and provisioning a
second credential set adds coupling without improving their release workflow. Manifest availability
is deliberately narrower than a runtime test; the manual owner retains scientific/provenance checks.

**Recovery.** Optional `release_tag` dispatch reads candidate metadata and packages the immutable
existing tag SHA while using the repaired workflow's control guards. Uploads target the named draft;
an already-public release is refused. Never retag or silently package newer main source. Apple team
ID is public configuration (v2 team `3BMY24SA43`), not a required secret; actual signing credentials
remain required. Executables are verified before upload and inventory-checked before publication.

**Verification contract.** Build-plan tests reject retired `internal` mode and mismatched release
metadata. Actionlint checks workflow syntax; manifest selection must accept Linux amd64 and reject
wrong/missing platforms. Workflow rehearsal and actual signature/notarization outcomes remain
separate evidence; this decision alone does not certify release completion.

## 2026-09-22 — Windows named pipes are probed; WSL is a Windows host to the loaders

**Decision.** Docker discovery in the desktop app collapses every `npipe:` endpoint to
`//./pipe/<name>`, and on win32 it probes the context-derived pipe and then Docker Desktop's
well-known pipes (`dockerDesktopLinuxEngine`, `docker_engine`) with `GET /_ping` before failing;
`docker.exe` is also looked for in Docker Desktop's install directories, not only on PATH. A named
pipe that does not exist is classified `not-running`, never `not-installed`. Discovery remains the
only CLI use; everything else stays on the Engine API (2026-09-03). Separately, `loader.sh` and
`loader.py` treat WSL2 as a Windows host: browser UI by default, URL opened on the Windows side,
no AppImage download, `--desktop` refused with a reason naming the Windows installer. WSL is
detected from `WSL_DISTRO_NAME`/`WSL_INTEROP` only.

**Why.** On a Windows 11 / Docker Desktop 4.60 / WSL2 machine the active context was
`desktop-linux` with `npipe:////./pipe/dockerDesktopLinuxEngine`; stripping only `npipe:` left a
four-slash path that Node rejects with ENOENT, which the app reported as "Docker was not found"
[measured 2026-09-22: four-slash form ENOENT; `//./pipe/dockerDesktopLinuxEngine` and
`//./pipe/docker_engine` both answer `/_ping` 200]. v2 never hit this because it hard-coded
`//./pipe/docker_engine` and appended Docker Desktop's directories to PATH. A pipe cannot be
`existsSync`-probed, so a one-request ping is the honest liveness check. In WSL the loaders
downloaded the Linux AppImage in full and then failed on missing FUSE, and `webbrowser` handed the
URL to an `xdg-open` with no WSL support while reporting success.

**Verification contract.** `desktop/tests/unit/docker-engine-discover.test.ts` covers slash
collapse, the Windows CLI candidates, the ping fallback order and the not-running/not-installed
split; `tests/test_wsl_host.py` runs both loaders under a WSL environment. Verified live on the
machine above: packaged `TI-Toolbox.exe` attaches to a running container over the pipe, the CUDA
probe passes over npipe with `DeviceRequests` (`nvidia`), and both loaders open the URL through
PowerShell. Fresh container creation from the Windows app was not exercised in that session
because it would have replaced the user's only running container.

## 2026-09-22 — TI-Toolbox launches only the TetraVox it installed

**Decision.** Supersedes the resolution order of 2026-09-19 (located app, system locations, PATH,
then TI's copy) and its "TetraVox owns updates". The desktop app installs its own TetraVox under
`runtimes/tetravox-<platform>-<arch>` on macOS, Linux and Windows, from the official release
archives (`mac-*.zip`, `linux-x64.tar.gz`, `win-x64.zip`), verifies each download against the
SHA-256 digest GitHub publishes for the asset, and launches nothing else. The Locate picker, the
`tetravoxPath` setting, PATH and system-location discovery are removed. TI owns updates through one
**Update** action (download, verify, unpack, swap; refused while the viewer runs) and launches the
viewer with `TETRAVOX_MANAGED_BY` set. The preload budget moves from 22 to 21 entries
(`locateNativeTetravox` and `clearNativeTetravoxPath` out, `updateNativeTetravox` in).

**Why.** The maintainer's instruction: use only the embedded TetraVox, assume none is present on the
machine and ignore one if it is, keep it simple and robust. Under the previous order a stale or
foreign TetraVox anywhere on the machine silently became the viewer, and Windows had no managed
setup at all — the Settings card told a Windows user to install TetraVox themselves and point at
it. The Windows release already ships a plain `win-unpacked` zip and GitHub now publishes a digest
for every asset, which removes the earlier objection that no verifiable portable package existed.
`tar` (bsdtar on Windows 10+) unpacks all non-macOS archives, so no extraction dependency is added.

**Alternatives rejected.** Bundling TetraVox inside the TI-Toolbox installer couples two release
cadences (five TetraVox releases in the week before this decision). Keeping the picker "for experts"
keeps the failure mode. Relying on TetraVox's own updater leaves the Windows zip copy without any
update path and two owners of the installed version.

**Verification contract.** `desktop/src/main/tetravoxNative.test.ts` builds a real platform archive
from a fixture and exercises first setup, digest refusal, byte mismatch, update-and-swap, an
already-current update and rediscovery of earlier directories; `tests/unit/tetravox-card.test.tsx`
pins the card (no Locate, Update once installed); `smoke.spec.ts` pins the 21-entry bridge. Verified
live on Windows 11 the same day: fresh install of TetraVox 0.6.1 from the packaged app and a native
launch. macOS and Linux paths were exercised by the unit fixtures only in that session.

## 2026-09-22 — TI's TetraVox runs in TI's own profile, and scenes never go to the OS

**Decision.** Amends the entry above. Every launch of TI's copy passes
`--user-data-dir=<userData>/tetravox-profile` (created if missing; the directory earlier layouts
used only when it already existed), on macOS through `open -a <bundle> --args` and elsewhere on the
command line. ROI-plate `--job` captures get a throwaway profile, like scene previews already did.
`tit:openPath` refuses `*.tetravox.json`, so a scene is never handed to the OS's file association.
The scene-protocol capability check reads `app.asar` through the asar header like identity does.

**Why.** Without the flag TI's copy used Electron's default profile, `@tetravox` in the OS app-data
directory — the same one a TetraVox the user installed uses. TetraVox takes
`app.requestSingleInstanceLock()` on that profile (`packages/app/src/main/index.ts`), so while the
user's copy was open a scene sent to TI's copy was forwarded to the user's copy and TI's exited, and
the two shared settings and the extension index. Checked on macOS 15.7 the same day: `open -a
<path>` launches that bundle even while another copy with the same bundle id runs, and passes the
caller's environment (so `TETRAVOX_MANAGED_BY` reaches it; TetraVox's `updater.ts` reads exactly that
name). A real first setup and Update of TetraVox 0.6.1 into a temporary user-data directory, followed
by a launch, ran in `tetravox-profile` and left `~/Library/Application Support/@tetravox` untouched.
The asar read: Electron's patched `readFile` keeps the archive open, which on Windows blocks the
directory rename Update performs (the measurement that moved install file operations to
`original-fs`).

**Alternatives rejected.** Keeping the profile only for legacy installs leaves the lock shared on
every new install. `open -n` would start duplicate TI viewers. Routing `openPath` scenes to TI's
copy adds a second launch path for a case with no caller.

**Not changed.** Unpacking and launching the bundle registers it with LaunchServices, and TetraVox
declares `.nii`, `.nii.gz`, `.mgz` and other document types; with one bundle id, macOS may pick
either copy for a double-clicked file. Process detection still counts any TetraVox process as open
(false positives only ask for consent or refuse Update).

**Verification contract.** `tetravoxNative.test.ts` "always runs TI's copy in TI's own profile" and
the macOS `open` cases pin the argument; `roiPlates.test.ts` pins the capture profile;
`settings.test.ts` pins that a stale `tetravoxPath` is ignored and dropped.

## 2026-09-22 — TetraVox's own update popup asks TI to install; "running" means TI's viewer only

**Decision.** Amends the two entries above (§7.1). The maintainer asked that TI's TetraVox be
updatable from TI's Settings *or* from TetraVox's native popup inside TI's copy. TI now also passes
`TETRAVOX_MANAGED_UPDATE_REQUEST=<userData>/tetravox-update-request.json`. A TetraVox with the
handshake (the branch `feat/managed-update-handoff` of idossha/tetravox; first release after 0.6.1)
keeps its launch check and popup in that mode; **Update to X** asks about unsaved edits, writes a
`{protocol: 1, action: "update", id, version, current}` request, waits up to 15 s for TI's receipt
with the same id, and quits. TI polls the path (`fs.watchFile`, 1 s), answers, waits for its viewer
to quit, runs the existing verified update and relaunches with the last scene it opened. The popup is
the consent; **Skip This Version** is TetraVox's per-version skip in TI's viewer profile. Settings ▸
Viewer now shows the newest release (`tit:tetravox:checkUpdate`) and labels its button **Update to X**.
`TETRAVOX_MANAGED_BY` becomes `TI-Toolbox`, the name the popup shows. Process detection now counts only
TI's managed executable or a process in TI's viewer profile — superseding "Not changed … counts any
TetraVox process as open" in the entry above: with separate profiles a user's own TetraVox can no
longer receive TI's scenes, so it has no reason to block TI's Update.

**Why.** TetraVox's electron-updater would write into TI's runtime directory, bypassing TI's
GitHub-digest check, `ready.json` and swap; so TetraVox asks and TI installs. A file in TI's
user-data directory works the same through `open -a` (not a child process) on macOS and a detached
spawn on Linux and Windows, where a pipe, socket, URL scheme or file association would each need a
per-platform mechanism. The request carries no URL or path, only a version string TI validates and
does not trust: TI installs the newest release it verifies itself. The receipt lets TetraVox stay
open with an error instead of quitting into nothing when no TI is listening.

**Alternatives rejected.** TetraVox's in-place updater writing TI's directory (bypasses verification
and TI's identity/ready checks). TI killing the viewer on request (loses unsaved edits; TetraVox asks
first and quits itself). A URL scheme or local HTTP listener (registration per OS; an unauthenticated
listener). Updating to the version TetraVox names (TetraVox read a different feed; TI installs its
own verified newest).

**Compatibility.** TetraVox ≤ 0.6.1 ignores the new variable: updater off, Settings' Update works as
before. A TI without the handshake gives a new TetraVox no request path: its updater stays off and its
dialog says "Updates are managed by …". TI's pinned floor (`compatibleViewerVersion`, 0.4) is
unchanged: the popup appears once the installed copy is a handshake release, and TI's Settings Update
gets it there.

**Verification contract.** `tetravoxNative.test.ts`: the launch env carries both variables; an
accepted request installs the verified release, writes the receipt and relaunches; a failed update
still relaunches and reports; malformed requests install nothing; a viewer that stays open blocks the
install; the watcher answers waiting and new requests; detection ignores another executable/profile.
`tests/unit/tetravox-card.test.tsx`: **Update to X** and **Check for updates**. Real check on macOS
15 arm64, 2026-09-22, scratch user-data: a branch-built TetraVox relabelled 0.6.0 in TI's slot showed
its popup ("ti-toolbox installed this copy and installs its updates …" — the run predates the rename
to `TI-Toolbox`); clicking **Update to 0.6.1** (over CDP) led TI's watcher to install the GitHub 0.6.1
zip (digest-verified, `ready.json` written) and relaunch it in `tetravox-profile` 14 s later.

## 2026-09-22 — TI's TetraVox has its own TetraVox home, too

**Decision.** Amends "TI's TetraVox runs in TI's own profile" (§7.1). Every launch of TI's copy
also sets `TETRAVOX_HOME=<userData>/tetravox-home` (created if missing): the spawn path, both macOS
`open -a … --args` calls (`open` passes the caller's environment to a new instance) and the
`--job` captures (ROI plates and saved-scene previews), which get a `tetravox-home` inside their
throwaway directory. A `TETRAVOX_MODULE_DIR` in TI's own environment is not passed on, because
TetraVox would read extensions from it instead of `<TETRAVOX_HOME>/modules`. The preload bridge is 22 entries since the entry above added
`checkNativeTetravoxUpdate`; `smoke.spec.ts` now pins that.

**Why.** Maintainer rule: TI's managed TetraVox never shares anything with a user's own TetraVox.
`--user-data-dir` moves Electron's profile but not TetraVox's own home, `~/.tetravox`, which holds its
rc file and installed extensions; TetraVox reads `TETRAVOX_HOME` instead when set (`configHome()` in
`packages/app/src/main/module-store.ts`, released 0.6.1 included).

**Alternatives rejected.** Pointing `HOME` at a scratch directory changes every path the viewer
resolves from the user's home, not only TetraVox's own. Leaving captures on `~/.tetravox` lets a headless
render load the user's extensions.

**Not changed.** A TI viewer already running keeps the environment it started with until it is
relaunched; TI's rc and extensions start empty (nothing is copied from `~/.tetravox`).

**Verification contract.** `tetravoxNative.test.ts` (spawn env and directory, macOS `open` env on
both calls, the `--scene-request` spawn and its activation), `roiPlates.test.ts` and
`nativeScenePreview.test.ts` (capture home inside the throwaway directory, present while it runs).

## 2026-09-22 — One global CPU limit, 70 % by default, is the scheduler budget

**Decision.** TI-Toolbox's CPU use is capped by one user-wide setting, **CPU limit**, a percent of
the cores available to the container (`tit.cpu.effective_cpus()`), default **70 %**, resolved as
`max(1, floor(percent × cores / 100))` by `tit.cpu.cpu_limit()`. It is stored in
`<user config>/cpu-limit.json` (the directory every project and container restart shares), set
from Settings → Project → Execution or `PUT /api/cpu-limit` (10–100); that file is the only
source (no environment override). It replaces "all cores minus one" as the default for
every job path: the scheduler budget (`discover_budget`), `n_jobs = -1` for ex/mex/stats (plan cost
and worker count), flex's `cpus=None`, FastSurfer/FreeSurfer/CHARM/QSI automatic threads, and NIfTI
workers. Explicit values stay as API overrides but are clamped to the limit. The exhaustive-search
numba share is `job_cpus() // workers`, not `effective_cpus() // workers`. RAM is unchanged.

**Why.** Maintainer requirement (2026-09-22): "We cannot hijack their container resources by
default … by default use 70 % resources", exposed in general settings. Before this an ex-search on a
10-core container defaulted to 9 workers, and a search admitted with 2 CPUs ran 2 workers × `10 // 2
= 5` numba threads = 10 busy cores [derived: pre-change `tit/opt/ex/parallel.py`]; the scheduler
budget was the whole container, so concurrent jobs together could claim every core.

**Alternatives rejected.** A per-page thread control (Optimizer) cannot bound two concurrent
jobs. Storing the percent in project settings would make it differ per project on one machine.
Rejecting explicit `n_jobs` above the limit would break scripts; clamping keeps them running. An
environment-variable override (maintainer, 2026-09-22) was dropped: a second source would make the
Settings value silently lose to the environment and the slider snap back.

**Verification.** `tests/test_cpu.py` (resolver: default 70, floor, min 1, saved file round-trip, invalid
values), `tests/test_jobs_scheduler.py::test_discover_budget_cpus_are_the_global_limit_not_the_container`,
`tests/test_plan_accuracy.py::test_pool_kinds_claim_the_global_limit_and_clamp_explicit_n_jobs`,
`tests/test_opt_parallel.py::test_workers_times_numba_threads_never_exceed_the_admitted_cpus`,
`tests/test_jobs_manager.py::test_the_global_cpu_limit_is_read_at_admission_and_shrinks_a_larger_claim`,
`tests/test_cpu_limit_route.py`, and `desktop/tests/unit/cpu-limit-ui.test.tsx`.


## 2026-09-22 — One job per product runs at a time; "Subjects in parallel" is retired

**Decision.** The "Subjects in parallel" setting (Settings → Project → Execution, stored in the
renderer's `tit-execution-prefs` localStorage, sent as `JobGroupRequest.parallel_subjects`, mirrored
onto `JobSpec.group_cap` and enforced by the scheduler as a per-group running-job cap; also accepted
by `POST /api/plan/pre` to scale the preview) is removed from the UI, the contract, the server and
the mock. The scheduler instead runs **one job per product**: `PRODUCT_OF` maps `pre` →
preprocessing, `sim` → simulator, `flex`/`flex_adaptive`/`flex_pareto`/`ex`/`mex`/`leadfield` →
optimizer, `analyzer` → analyzer, and a job waits while another job of its product is running.
A multi-subject run is still one group of per-subject jobs (per-stage for Preprocess), run one
after another. The global CPU limit is the only resource setting. A stale `parallel_subjects` in a
request, `group_cap` in a `spec.json` or `parallelSubjects` in localStorage is ignored.

**Why.** Maintainer (2026-09-22): "it should always be 1 job per product, i.e. 1 job per
preprocessing, 1 job per simulator, 1 job per optimizer. Only parallelization that happens is
decided by the architecture of the toolbox." The cap was per group only, so two separate
submissions of one product already ran together, and a cap above 1 ran several FEM-class jobs at
once.

**Alternatives rejected.** Collapsing a multi-subject run into literally one job (one process
looping subjects) would rewrite every group runner, the Jobs table's per-subject rows, per-job ETA,
cancellation and preflight for no change in what runs concurrently; the group of queued jobs run one
at a time already gives that. Keeping `parallel_subjects` as a hidden API override contradicts
"always".

**Verification.** `tests/test_jobs_scheduler.py` (same product waits across groups, optimizer kinds
share one product, other products and non-product kinds run together, stale `group_cap` ignored),
`tests/test_jobs_manager.py::test_a_product_group_runs_one_job_at_a_time`,
`tests/test_jobs_routes.py::test_a_group_runs_one_member_at_a_time` (with and without a stale
`parallel_subjects`), `tests/test_plan_routes.py::test_plan_pre_runs_one_stage_at_a_time_and_ignores_a_stale_parallel_subjects`,
`desktop/tests/unit/job-groups.test.ts`, `desktop/tests/e2e/batch.spec.ts`.


## 2026-09-23 — Every shipped MNI atlas names one hemisphere per label; CIT168 and Harvard-Oxford cortical are lateralized

**Decision.** `CIT168_labeling_MNI152NLin2009cAsym.nii.gz` (16 labels) and
`HarvardOxford-cort-maxprob-thr25-1mm.nii.gz` (48) are no longer shipped. They are replaced by
`CIT168_labeling_lateralized_MNI152NLin2009cAsym.nii.gz` (32: the published map split at world
x = 0 of its own grid, label k -> 2k-1 Left / 2k Right, voxel plane x = 0 -> Right) and FSL's own
`HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz` (96, byte-identical from NeuroDebian
`fsl-harvard-oxford-cortical-lateralized-atlas_5.0.7-2_all.deb`, sha256 `a7c63c12…be51`, odd =
Left, even = Right). `dev/build_lateralized_atlases.py` produces both from sha-pinned inputs,
byte-deterministically. Both old ids are listed under `manifest.json § not_shipped` with a sentence
naming the replacement, so a saved configuration fails instead of label k silently changing meaning.
The MNI guide was rebuilt; the ROI picker, the pane and the selection code are unchanged.

**Why.** Maintainer report (2026-09-23): in MNI mode, picking one region selected both hemispheres.
No code pairs labels: `toggleRegion`/`wireLabelsFor` (`desktop/src/renderer/pages/_shared/scene/model.ts`)
and `selection.ts` toggle one label id. The two atlases themselves gave each structure one value on
both sides of x = 0 [measured: nibabel over the shipped files, >50 voxels at x < -2 and at x > 2:
all 48 HO-cortical and all 16 CIT168 labels; 0 in Glasser and Schaefer; only midline anatomy in
HO-subcortical, MASSP and Cerebellum], so the run config targeted both sides too. Subject mode was
already unilateral (per-hemisphere `.annot` keys, Left-/Right- `labeling.nii.gz` labels).

**Alternatives rejected.** A hemisphere field on `SubcorticalROI` clipped at run time touches flex,
ex, the analyzer, `config_io`, the guide legends and the desktop types — more code than replacing
two files. Splitting labels only in the pane would draw one side and run both. Relabeling in place
under the old file names would re-mean every saved config's label k without an error.

**Verification.** `tests/test_atlas_laterality.py` (red on exactly the two old atlases before the
swap; midline allow-list by LUT name: vermis, brain stem, third/fourth ventricle, fornix),
`tests/test_atlas_manifest.py::TestNotShipped::test_a_bilateral_atlas_names_its_lateralized_replacement`,
`tests/test_atlas_manifest.py::TestGrid` (cortl on the template grid, LUT covers 1..96).

## 2026-09-23 — Job banners can play a TI-Toolbox sound; the preload budget moves from 22 to 23

**Decision.** The notification preference `sound` is one of `none`, `system` or a shipped sound
(`pulse` default, `chime`, `tick`), listed once in `TI_SOUNDS`
(`desktop/src/shared/jobNotifications.ts`); anything else normalizes to the default, and the old
boolean migrates (true → `pulse`, false → `none`); `soft-bell` and `ripple`, offered briefly the
same day and withdrawn, also read as `pulse`. `system` keeps the OS sound (`silent: false`);
a shipped sound shows the banner silent and main sends `tit:notificationSound` to the main window,
which plays the WAV with an `HTMLAudioElement` (a failure: the same file at 0.75× with pitch
following, a fourth lower). This adds one preload entry, `onNotificationSound`. The sound now
plays while the window is focused too (the old "muted while in front" rule is dropped: the user
chose the sound to hear it). An offscreen test window is muted (`setAudioMuted`) and main sends no
sound event in that mode. The WAVs are synthesized by `dev/generate_notification_sounds.py`
(stdlib only, byte-deterministic, −3 dBFS peak, ≤ 0.8 s, 64 KB for three [measured: `du`]) and
imported as Vite assets, so they ship in `out/renderer` for dev, packaged and container-served UIs.

**Alternatives rejected.** Electron's macOS `Notification.sound` only plays sounds inside the app
bundle and does nothing on Windows/Linux. Playing from main needs a shell-out (`afplay`) or a
hidden window. Separate failure files would double the assets for what a playback rate gives.

**Verification.** `desktop/tests/unit/job-notifications.test.ts` (migration, unknown ids,
`soundPlan`, WAV headers read with DataView), `desktop/tests/unit/notifications-card.test.tsx`
(selector, Preview, test banner per choice, failure pitch, unknown id ignored),
`desktop/tests/e2e/smoke.spec.ts` bridge list.

## 2026-09-23 — The run split is sized in pixels: Jobs 640–800 px, Terminal/Scene ≥ 400 px

**Decision.** The run pages' divider (Simulator, Optimizer, Analyzer, Pre-processing, the extension
panels) clamps with `runPaneLimits(bodyWidth)` in `desktop/src/renderer/ui/paneState.ts`: the
work pane stays in [640, 800] px of the split box, the right pane is at least 400 px, and the
handle is 6 px. The same constants reach the stylesheet as custom properties set by `PageLayout`,
where `min-width`/`max-width` re-clamp a stored width on load and window resize without
overwriting it. Below a 1140 px window the run shape stacks (was 1100). The run pane's old window
fractions (36 vw floor, 70 vw ceiling) and the per-page `minWidth`/`maxWidth` knobs are removed;
Results and Jobs say `kind: "preview"` for their 320 px / 70 vw range. Expand, collapse and the
non-wrapping terminal are unchanged.

**Why.** The window fractions let a 70 vw pane leave the Jobs table 162 px at 1440 × 900 and a
36 vw floor stretch it to 959 px at 1920 [measured: offscreen drag on the mock fixture]. The
floor is measured, not chosen: shrinking the work pane in 4 px steps, the first truncation is the
Simulator's SUBJECT header at 628, the Optimizer's goal select at 556 and the Analyzer's "Choose a
simulation" at 632 [measured: offscreen probe, 2026-09-23], so 640. Side by side needs a
1046 px split box, which the icon rail leaves from a 1134 px window, hence the 1139 px breakpoint.

**Alternatives rejected.** Keeping fractions with a larger floor still over-stretches the table
on wide screens. Wrapping the terminal breaks `VirtualList`'s fixed 18 px rows. A JS-only clamp
would leave a stored width drawn at an illegal size until the next drag.

**Cost.** Between 1100 and 1139 px the run pages now stack. The 800 px cap leaves the scene very
wide on 2560 px screens, which is where the scene benefits.

**Verification.** `desktop/tests/unit/pane-state.test.ts` (`runPaneLimits` sweep, CSS agreement),
`desktop/tests/unit/run-pane-controller.test.tsx` (limits from the split box),
`desktop/tests/e2e/layout.spec.ts` (drag extremes at 1140/1280/1440/1920/2560, no Jobs-table
truncation, re-clamp on resize, stacking at 1100).

## 2026-09-27 — DTI via DIPY on QSIPrep output; QSIRecon optional; exact transform chain; SDC mandatory

**Decision.** The SimNIBS tensor is fitted in `tit/pre/qsi/dti_extractor.py` with DIPY
`TensorModel` WLS on b ≤ 1500 from QSIPrep's ACPC DWI and `.b` table, mapped to the m2m T1 with the
exact QSIPrep chain `G = A_lps · inv(A_anat) · inv(X)` (`tensor_math.py`), resampled by
validity-normalised trilinear interpolation with tensor rotation, masked to the brain, and stored in
SimNIBS's `correct_FSL` frame. A QC gate decides whether the file is written. QSIRecon becomes an
optional advanced step. QSIPrep runs with mandatory susceptibility distortion correction (fieldmap
TOPUP, else SyN), data-driven unringing and resolution, explicit eddy/TOPUP/b0 flags, no MNI
normalization unless asked for or SyN needs it, and refuses arm64 hosts. `dipy>=1.12,<2` joins the
image's `simnibs_python` environment.

**Why.** The previous extractor (v2.3.0–v3.0.1) had three defects: a translation-only FFT alignment
where QSIPrep's ACPC space is the T1w rotated about 21° and shifted, no tensor rotation, and order-3
resampling without a mask; `skip_registration` also stored a mirrored tensor. On CHN this placed
tensors 18 mm off on average with a 38° median principal-axis error [measured: dti_eval
chn/chn_eval.txt]. The exact chain recovers a known map to max|G − G_true| ≈ 1e-14 and V1 median
2.3–2.5° against the synthetic truth, equal to the interpolation floor [measured: dti_eval
synth/roundtrip_results.txt]. DIPY WLS b ≤ 1500 agrees with DSI Studio's OLS b ≤ 1750 within 0.54°
median V1 and MD ratio 1.000 on CHN [measured: chn/chn_eval.txt, q1/fit_shells.txt], so QSIRecon adds
nothing to the tensor. CHN's QSIPrep run had no distortion correction because its fieldmaps lacked
`IntendedFor`, which nothing wrote; CHN is partial-Fourier 0.75, where `mrdegibbs` is wrong.

**Alternatives rejected.** NCC registration as the map: it agrees with the chain (0.04 mm on CHN) but
is an optimiser that can fail silently, so it stays a check. FSL `dtifit`/`vecreg`: FSL cannot be
bundled (licence). DSI Studio through QSIRecon: an extra 60-minute container for the same tensor.
A Mac path for QSIPrep: SynthSeg's AVX requirement has no emulated workaround.

**Cost.** One more Python dependency in the image. The NCC check adds about a minute. Subjects whose
m2m was built from a different T1w than QSIPrep's are refused. Published anisotropic results from
v2.3.0–v3.0.1 must be regenerated. Saved QSIPrep preferences keep an explicit `output_resolution` /
`unringing_method` the user saved earlier; only unsaved or reset preferences get the new defaults.

**Verification.** `tests/test_pre_qsi_tensor_math.py`, `tests/test_pre_qsi_sdc.py`,
`tests/test_pre_qsi_dti.py`, `tests/numerical/test_dti_roundtrip.py`, and
`TIT_DTI_REAL=<Dataset 000> tests/numerical/test_dti_real.py` (CHN QC gate passes, V1 vs the
prototype). QSIPrep with the new flags on an x86 host (ernie kit) is still outstanding.

## 2026-09-28 — Reports as QC records: one HTML layer, one rules dict, a lean DTI report

**Decision.** Reports are built from `tit/reporting/html/components.py` + `report.css` (shell, components,
SVG charts, QC-check rows; fonts and images inline, no framework). Every QC value lives in
`tit/reporting/qc_rules.py` with a role (`gate`, `internal`, `advisory`, `report`), citations and plain
text. The DTI QC report is rewritten on it, is written on a failed gate too (then the step raises),
and shows by default only the verdict, the one literature gate (WM median MD, Pierpaoli 1996; Cox 2016),
advisories that need attention, a preprocessing list, one registration flicker, one fibre-orientation
figure and FA/MD by tissue; everything else is collapsed. The QC record gains advisories, measurements
and provenance (`dti_advisories.py`, about 9 s on CHN on an Apple M-series host). `tit.plotting.static_overlay`
and the old DTI figures are removed; `tit/plotting/slices.py` replaces them with one neurological RAS
convention. The report CSP allows `font-src data:`, the Results iframe inherits the app's `color-scheme`,
and the catalog titles `dti_qc_*` reports "DTI QC report".

**Why.** The previous DTI report had no verdict, showed no thresholds, cited nothing specific, mixed
neurological and radiological panels (3 of 14 panels empty), and was never written when the gate
failed, the case that most needs it (survey of 2026-09-27). A literature review (2026-09-28) found one
published DTI cut-off (the b-table flip test has no margin) and one well-referenced range (adult WM MD);
the other five gate checks are TI-Toolbox's own invariants, so they are labelled software checks rather
than presented as quality evidence. The first prototype had ten sections and overwhelmed readers.

**Alternatives rejected.** A template engine or a front-end framework for reports: more dependency than
a few string functions. Keeping the old reportlet path beside the new one for DTI: two ways to render the
same record. Glyph, coverage and conductivity sections: dropped as default content; the `vn` clamp line
stays because it equals SimNIBS 4.6 `cond2elmdata` to 3e-14 (`tests/numerical/test_dti_advisories.py`).
A cached reference-subject analysis: only ernie's WM median FA is shown, computed when the project has
ernie's tensor.

**Cost.** The DTI step takes about 15 s longer (advisories, hashing a 2 GB DWI, report). QC records
written before this change lack advisories; the rebuild command measures them. `generate_static_overlay_images`
is gone from `tit.plotting`.

**Revisit if** a second report type adopts the layer (move its sections into `RULES`), or the published
thresholds change.

## 2026-09-28 — Five report kinds and nothing around them; the DTI verdict counts what the page shows

**Superseded 2026-09-28 (in part)** by "Preprocessing reports are SimNIBS's charm report and the DTI
report" below: the preprocessing report and its recon section are gone.

**Decision.** TI-Toolbox keeps five report kinds: the preprocessing report (home of the
FreeSurfer/FastSurfer recon report), DTI QC, flex-search, ex-search and simulator. `tit.catalog` no
longer titles `m_ex_search_report` (no generator ever wrote one). Reports have no PDF export or print
stylesheet, no metadata or sidecar files, no cross-links and no index page; the shared layer's A4 print
CSS, its print handlers and the legacy templates' `@media print` block are removed. The DTI headline
reads "Quality gate passed", "Quality gate passed · N advisories need attention", or names the failed
checks ("Quality gate failed: White-matter diffusivity — tensor not written"); the masthead shows the
tensor file's write time instead of "written". The DTI generator, its advisories and the HTML layer
lost their unused parameters, tokens and wrappers (labels now live in `RULES`).

**Why.** The maintainer's standing requirement is efficiency without bloat, and PDF export, sidecars,
cross-links and an index page were declined (2026-09-28). "Passed all 6 blocking checks" counted five
software checks the default view does not show, so the headline and the visible table disagreed.

**Alternatives rejected.** Keeping print CSS as harmless: it existed only for the declined PDF path.
Deleting the per-stage preprocessing reports of `tit.pre.structural.run_pipeline`, the unused
`SimulationReportGenerator`, the reports directory's BIDS `dataset_description.json`, and the plain-text
summaries of `tit.stats` and tissue analysis: kept, because they are the home of a needed report or an
analysis output rather than a report of their own; listed for review. Cutting shown DTI content (the
QC-record dump, the motion chart, the `vn` note, the reference-subject FA) to halve the generator: a
change to what the report shows, left to the maintainer.

**Evidence.** CHN (Dataset 000): with the same record and images, the page body is byte-identical
before the two fixes; the re-measured `DTI_coregT1_qc.json` equals the old one apart from timestamps;
every image is byte-identical. Report 1,231,100 → 1,229,144 bytes; rebuild 16.3 → 15.8 s on an Apple
M-series host, 30 → 28 s in `idossha/ti-toolbox:v3.0.1`. `pytest tests/ --ignore=tests/numerical`
5287 passed, 54 skipped; `tests/numerical/test_dti_advisories.py` and `test_dti_roundtrip.py` in the
image with dipy 1.12.1: 16 passed.

## 2026-09-28 — Preprocessing reports are SimNIBS's charm report and the DTI report

**Decision.** Preprocessing has two reports. The charm report is SimNIBS's own `charm_report.html`:
when `charm` exits 0, `tit.pre.charm.copy_charm_report` copies it (never moves it) to
`derivatives/ti-toolbox/reports/sub-<id>/charm_report.html` and records it as a `report` artifact of the
charm job; the catalog titles it "Head model (charm) report". The DTI QC report is unchanged. The
combined preprocessing report is deleted with every section it had (DICOM, atlas, tissue, QSIPrep,
QSIRecon, FreeSurfer/FastSurfer recon): `tit/reporting/generators/preprocessing.py`, `tit/pre/report.py`,
`run_pipeline`'s per-stage reports, `JobManager._attach_pre_report`, and the `report` job kind, which
leaves `JobKind` (`contracts/CHANGES.md`). Reportlets only it used (`ProcessingStepReportlet`,
`MultiViewBrainReportlet`) and the unused `DescriptionReportlet` and `CommandLogReportlet` go too;
simulation and flex-search keep the legacy layer. There is no DICOM report.

**Why.** The maintainer decided only charm and DTI reports matter for preprocessing (2026-09-28). SimNIBS
already writes a reviewed, self-contained charm QC page; re-rendering it in TI-Toolbox duplicated it.

**Alternatives rejected.** Moving the file: SimNIBS and users expect it in m2m. Copying `charm_log.html`
and assets: the report links to neither, and every image is an inline `data:` URI. A timestamped copy:
the report describes one head model, and a replaced m2m makes the old copy wrong. Keeping `report` in
`JobKind` without a runner: a submittable kind that cannot run is the failure the kind was once removed
for; legacy job records with `kind: "report"` still load, like `viewer`'s.

**Evidence.** In `idossha/ti-toolbox:v3.0.1` with this checkout on `PYTHONPATH`, against a scratch copy of
Dataset 000's `m2m_ernie`: the copy is byte-identical (13,925,412 bytes, sha256 equal), the source stays,
`catalog.reports` lists `ernie/charm_report` as "Head model (charm) report", and one `report` artifact
event is written. Rendered headless in Chromium inside `<iframe sandbox="allow-scripts">` with the served
`REPORT_CSP` and `nosniff`: all 6 images decode, the viewer script draws the T1/tissue-label panels, no
CSP violation. `tests/test_pre_charm.py` pins the copy and the catalog entry.

## 2026-09-28 — Simulator, flex-search and ex-search reports on the one report layer; the reportlet layer is gone

**Decision.** The simulator, flex-search and ex-search reports are rebuilt on `tit/reporting/html`
and written by their pipelines from the run's own outputs (ARCHITECTURE.md §14); the reportlet and
assembler layer (`tit/reporting/core`, `reportlets/`, `base_generator.py`) and its tests are deleted,
leaving one report layer. The reference registry moves to `tit/reporting/references.py` as data.
Montage figures reuse the app's EEG-cap overlay (`montage_visualizer.visualize_montage`, as WebP);
`resources/amv/10-10.csv` gains PO9/PO10 (on GSN E114/E159) because the ernie ex-search winner
AF3–PO10 could not be drawn. `RULES["sim"]` and `RULES["opt"]` are the literature review's rules
(2026-09-28): the current checks are advisories, the target field is reported against Rampersad
2019's range, and the rest are software checks.

**Why.** No pipeline called the old simulation generator, so simulations had no report; the flex
report printed "Target ROI" and a bare score and weighed 7.4 MB (a 3.7 MB skin PNG); ex-search had
none. Two report layers meant two stylesheets and two ways to cite. The maintainer asked for a lean
default view, cited thresholds only, the cap overlay the app already shows, and no PDF, sidecars,
cross-links or index (2026-09-28).

**Alternatives rejected.** A new scalp drawing for reports (the prototype's) — a second picture of
the same montage that could disagree with the app's. Porting the reportlets onto the new CSS — they
exist only for the old generators. Pass/fail on target field strength — the published range comes
from optimised montages at deep targets and is context, not a limit. Treating Cassarà 2025's kHz
limits as per channel or as total — the review could not verify which.

**Evidence.** `tests/test_reporting_runs.py` (sections, advisories against `RULES`, current
wording, budgets including a 48,000-montage search); `python -m tit.reporting.generators.<name>` on
Dataset 000 sub-ernie: simulator 0.33 MB, flex-search 0.27 MB (was 7.4 MB), ex-search 0.41 MB.


## 2026-09-28 — Optimiser reports have no checks; a page's references are only what it cites

**Decision.** Ex-search drops its only check, the electrode-current advisory, with its checks table
and section badge, and `RULES["opt"]["electrode_peak_current"]` is deleted (flex-search dropped its
use earlier the same day; the simulator keeps `RULES["sim"]["electrode_peak_current"]`). Methods
paragraphs no longer cite TI-Toolbox itself (Haber 2026) or cite Grossman 2017 for TI as a topic; the
DTI report no longer cites SimNIBS's conductivity mappings (Tuch 2001, Rullmann 2009, Opitz 2011), which
it does not apply. Grossman 2017 stays where the envelope formula behind the shown numbers is named
(simulator, ex-search), the simulator cites only the mapping of the conductivity mode it names
(`vn`/`mc` Opitz 2011, `dir` Tuch 2001 + Rullmann 2009), and Jurcak 2007 only when the named net is a
10-10/10-20 layout. `references.py` keeps only entries some report cites (20 removed).

**Why.** The maintainer asked for ex-search's only check to go, and for a reference to appear only when
a number, threshold, rule or method shown on that page cites it (2026-09-28). The simulator's current
advisories are a separate, pending decision and are unchanged.

**Alternatives rejected.** A fixed reference list per generator — it keeps a reference after its row is
removed. Keeping unused registry entries as a library — nothing reads them.

**Evidence.** `tests/test_reporting_runs.py::test_references_are_exactly_what_the_page_cites`
(all four reports, both directions, from the generators' real output).


## 2026-09-28 — Run reports have no checks; the simulator reports grey matter, not an ROI; only the simulator draws the cap

**Decision.** The simulator report drops its ROI content (newest Analyzer result, ROI mean/max/focality,
the Rampersad 2019 range bar), its electrode-current and brain-current-density advisories and its
software checks (solver, current conservation, field order); `RULES["sim"]`, `common.current_check`,
`rule_check`, `attention_callouts` and the five references only those rules cited (Rampersad 2019,
Huang 2017, Bikson 2016, Antal 2017, Cassarà 2025) are deleted. It leads with the grey-matter envelope's
99.9th percentile and median and the location of its maximum, in MNI through charm's
`Conform2MNI_nonl` read at one voxel (subject-space mm without the warp). Flex-search drops the
nearest-cap overlay and embeds the run's own `roi.png` and `valid_skin_region.png` as WebP;
ex-search drops the cap overlay. The simulator keeps the cap overlay and the dose table.

**Why.** The maintainer asked for these removals and for the grey-matter headline (2026-09-28). The
simulator never sets an ROI, so ROI numbers only appeared after a separate Analyzer run; flex electrodes
are free positions, so a nearest-cap drawing misplaced them.

**Alternatives rejected.** Naming the peak by atlas region — it needs another atlas file read and a
label table per atlas; the MNI coordinate costs one voxel of a warp charm already wrote (0.23 s on
sub-ernie). The centroid of voxels above the 99.9th percentile as the location — on sub-ernie it spreads
22 mm in x and the combined grey/white field puts it in white matter; the maximum is a grey-matter voxel.

**Evidence.** `tests/test_reporting_runs.py` (no checks on any run report, the simulator headline and
peak with and without the warp, flex-search's two embedded figures, no cap on flex/ex);
`python -m tit.reporting.generators.<name>` on Dataset 000 sub-ernie in `idossha/ti-toolbox:v3.0.1`:
simulator 0.32 MB ("0.359 V/m peak envelope in grey matter", maximum 0.485 V/m at MNI (11, 16, -25) mm),
flex-search 0.29 MB, ex-search 0.30 MB.


## 2026-09-28 — PO10 on the 10-10 cap drawing sits on GSN E168, not E159

**Decision.** `resources/amv/10-10.csv` draws PO10 at GSN-256 E168's pixel (1257, 1157), the mirror of
PO9 on E114 (595, 1158) about the midline (Oz x = 925). This supersedes the E159 placement in "Simulator,
flex-search and ex-search reports on the one report layer" above; PO9 on E114 stands.

**Why.** Geometry on the same head: in each subject of Dataset 000 with both nets in
`m2m_<id>/eeg_positions` (CHN, 101, LA; ernie and MNI152 have no GSN-HydroCel-256), SimNIBS's
EEG10-10_UI_Jurak_2007 PO10 is 3.1–3.3 mm from GSN-HydroCel-256 E168 and 22.0–23.1 mm from E159
(6th nearest); PO9 is 6.2–6.4 mm from E114, its nearest.

**Alternatives rejected.** Re-placing the neighbours by the same nearest-electrode rule — the existing
rows follow a mirror-symmetric layout, not nearest electrodes (PO7/PO8 sit on E097/E161, 16.7–20.4 mm
from their nearest E107/E160; P9/P10 on E106/E169, 25–27 mm from E105/E177), and moving them changes
every drawn montage that uses them; that is its own decision.

**Evidence.** A distance script over those `eeg_positions` CSVs (nearest GSN electrode per 10-10 name,
and the rank of the one each drawing row sits on); the ernie simulator report for AF3_PO10_and_AF4_Oz
draws PO10 at the right-hand mirror of the PO9 position.


## 2026-09-30 — Carrier-only (ΔF = 0) controls sum the carriers coherently and record the flag in the run

**Decision.** `SimulationConfig.carrier_only` (default `False`) models a 2-pair montage driven at one
frequency, in phase. `hf_peak`/`hf_sar` then take `coherent=True` (`|E1+E2|`, `|E1+E2|²`), no envelope
field is computed, and `output_fields` may only name `hf_peak`/`hf_sar`. The run writes `carrier_only`
into `documentation/config.json`; the fsaverage projection reads it from there rather than from its own
config. The Simulator exposes it as a per-job checkbox, disabled for mTI rows; the desktop sends the key
only when it is on.

**Why.** Cassarà 2025 Part II p. 8: "coherent field superposition was used for identical frequencies".
The TI worst case `max(|E1+E2|, |E1−E2|)` is reached only because two different frequencies sweep every
relative phase; without a beat it overstates the peak wherever the carriers are more than 90° apart
(|E1| = 1, |E2| = 0.8 at 120°: 1.56 vs 0.92 V/m). "In phase" is the simulation's existing sign
convention (each pair's first electrode +I). Reading the run's own record makes a post-hoc projection
agree with the simulation without the user restating how it was run.

**Alternatives rejected.** An `FsavgMapConfig.carrier_only` flag (the first draft): a post-hoc projection
from the GUI panel or a script that omitted it would silently use the TI formula on a carrier-only run.
Computing `TI_max` as zero: an envelope that does not exist is undefined, not zero, and a zero map would
pass as a result. Allowing mTI: a carrier-only control is defined here for the two-carrier case only.

**Evidence.** `tests/numerical/test_sci07_exposure_channels.py::test_carrier_only_coherent_metrics_match_a_measured_same_frequency_field`
(time-domain reference); `tests/test_fields.py::TestCoherentCarrierOnly`; `tests/test_sim_config.py`,
`tests/test_plan_routes.py::test_validate_sim_reports_carrier_only_errors`, `tests/test_source.py`;
`desktop/tests/unit/simulator-defaults.test.ts`.


## 2026-09-30 — The fsaverage projection is a viewable SimNIBS `.msh`; `.npz` is no longer read

**Decision.** `tit.source.fsaverage` writes each projection as
`<sim>/fsaverage/sub-<id>_sim-<sim>_space-fsaverage<N>_fields.msh` (`PathManager.sim_fsaverage_fields`):
SimNIBS's fsaverage central template (`mesh_io.load_fsaverage_template("central", N)`), lh joined to rh,
one node field per quantity (`TI_max`, `TI_normal`, `hf_peak`, `hf_sar`, float64), plus the Gmsh
`.msh.opt` view — the `join_and_write` layout SimNIBS uses for `fsavg_overlays/<name>_fsavg.msh`.
Provenance (`subject_id`, `simulation`, `carrier_only`, `fields`) goes to a same-stem `.json` sidecar.
`tit.stats.surface` reads the `.msh` with SimNIBS's `mesh_io.read_msh`; the `.npz` cache is neither
written nor read, and old `.npz` files are left on disk. Missing projections are refused by preflight
and by the loader with the re-projection to run. The catalog lists the file as a `fsaverage` mesh,
MNI-space Viewer scenes offer it, and the `fsavg_map` runner reports it as a mesh artifact.

**Why.** The `.npz` was a values-only cache nobody could open; a `.msh` opens in the Viewer and Gmsh
like every other simulation output, and follows SimNIBS's own convention for the same data. The template
shares its face array with the fsaverage sphere `cross_subject_map(..., subsampling_to=N)` resamples
onto, so value `i` is node `i` with no reindexing. Every reader already runs under `simnibs_python`
(`simnibs_python -m tit.stats`, the documented scripting interpreter), so SimNIBS's reader serves
without a hand-written parser.

**Cost.** Disk ~4× (measured [local, SimNIBS 4.6, 4 random float fields]: fsaverage5 2.5 MB vs 0.6 MB
`npz`; fsaverage7 40.6 MB vs 9.9 MB); read 4 ms / 69 ms, negligible beside a permutation run. Projects
with `.npz`-only projections must re-run the fsaverage projection before surface statistics.

**Alternatives rejected.** Keeping a `.npz` fallback in the readers: two formats to test and document
for a cache that re-projects in seconds. Provenance inside the `.msh`: the format has no free metadata
block; extra node fields named after strings would be abuse, and a sidecar is the BIDS idiom. A
hand-written value-only `.msh` reader for SimNIBS-less interpreters: no such reader exists today.

**Revisit if** a reader must run without SimNIBS (e.g. the host server), or projection disk use matters
at fsaverage7 scale.

**Evidence.** `tests/numerical/test_fsaverage_msh.py` (real SimNIBS: morph output index = template vertex
index; lh-then-rh layout; vendored `resources/fsaverage` = template; round trip through
`load_group_surface_data`; Gmsh's own reader sees every field; FreeSurfer's `fsaverage/surf/?h.sphere`
= SimNIBS sphere-7 with sphere-5/6 as its prefix), `tests/test_stats_surface.py::TestLoadGroupSurfaceData`,
`tests/test_jobs_preflight.py::test_stats_fsaverage_space_needs_the_projection`,
`tests/test_viewer_library.py::test_the_fsaverage_projection_is_offered_only_in_mni_scenes`,
`tests/test_catalog_metadata_boundaries.py::test_simulation_detail_lists_the_fsaverage_projection`.


## 2026-09-30 — fsaverage data is `.msh` end to end; surface-stats tables are CSV

**Decision.** A surface cluster-permutation run (`tit/stats/surface.py`) writes `surface_stats.msh`
through the projections' writer (`write_fsaverage_msh`: fsaverage central template, lh then rh) with
node fields `t`, `p`, `sig_mask`, `cluster_id` (0 = none, else the `significant_clusters.csv` id), `r`
for correlation and the mean input field (`mean_field`, or `mean_responders`/`mean_non_responders`),
plus `.msh.opt` and a `surface_stats.json` of the run's settings and subjects. Its non-map data are CSV:
`significant_clusters.csv`, `null_distribution.csv` (one row per permutation) and
`cluster_subject_values.csv` (subject × cluster mean field, long format). `surface_maps.npz` is gone,
old ones are neither read nor deleted, and `render_surface_stats_result` reads the `.msh`. The Results
catalog lists the `.msh` as a mesh and hides its `.opt`; the generic `.npz` kind is removed.

**Why.** Same reason as the projections (entry above): a map people can open beats an archive only
Python reads, and one format for every fsaverage file means one writer, one reader and one test. The
tables go to CSV because their consumers are R and spreadsheets; `cluster_subject_values.csv` is the
export follow-up analyses need, which the `.npz` never carried.

**Cost.** A surface run's map file grows like the projections' (~4×). Old surface runs must be re-run
to get the new files.

**Alternatives rejected.** A per-vertex CSV (the `.msh` is the map; a 20k–330k-row table is neither
viewable nor small). Keeping the null distribution inside the `.msh` (it is not per-vertex).

**Left as is.** `tit/blender/montage_publication.py` hands the scalp geometry to the Blender process
through a temporary `scalp.npz` read by `montage_scene.py` (`allow_pickle=False`). It is an
in-process-pair handoff inside a temp directory, never user data, and Blender's Python has numpy but
not SimNIBS, so `.msh` would need a parser there for no user benefit.

**Evidence.** `tests/numerical/test_fsaverage_msh.py::test_surface_correlation_writes_msh_and_tables_matching_the_inputs`
and `::test_surface_group_comparison_writes_msh_and_tables_matching_the_inputs` (real SimNIBS, scipy,
nilearn: `cluster_id` = CSV ids and sizes, `sig_mask` = `cluster_id > 0`, means and per-subject cluster
means recomputed from the synthetic inputs, null rows = `n_permutations`, two PDFs rendered from the
`.msh`); `tests/test_catalog_group_stats.py::test_detail_of_a_surface_run_lists_the_mesh_and_tables`;
`tests/test_plotting.py::TestRenderFsaverageMap`.

## 2026-10-07 — Users drive jobs from their own agent; jobs record `created_by: "agent"`

**Decision.** The agent plugin gains a second, write-capable MCP server, `ti-toolbox-jobs`
(`agent-plugin/mcp/jobs_server.py`), that submits jobs through the running `tit.server` exactly as
the run pages do (`/api/jobs/groups` per subject, `/api/plan` and `/api/validate` first) and
copies raw scans into `sourcedata/sub-<id>/<modality>/` on the host. Both submit routes accept an
optional `created_by`, restricted to `tit.jobs.spec.CREATED_BY_VALUES`, which gains `agent`;
absent stays `gui`. Contract: `JobSpec.created_by`, `JobGroupRequest.created_by` (additive).

**Why.** Users already have Claude Code or Codex on a subscription login; letting that agent queue
real jobs gives them a natural-language front end without TI-Toolbox handling any AI credential
or shipping an AI service. Going through the job API (not `simnibs_python` in a shell) keeps the
queue, locks, one-job-per-product rule, live job list, outputs and reports identical to app-started
runs. A separate server keeps the read-only knowledge server read-only, so a client can grant one
without the other. Staging is host-side because the raw folder is outside the bind mount.

**Cost.** The job server mirrors the run pages' default configs (Pre-processing, Simulator,
Optimizer flex) by hand; a changed page default must be copied there. Raw-scan modality guesses
are heuristics (DICOM header strings, file names) that the agent must confirm with the user.

**Alternatives rejected.** An embedded agent or server-side LLM route (needs the user's
credentials or our own API keys). Adding write tools to the read-only server (one permission for
two very different risks). A staging route on the server (it cannot see host paths outside the
project).

**Revisit if** page defaults drift from the mirror (move them server-side), or the desktop gains an
"open my agent here" terminal action.

**Evidence.** `tests/test_jobs_routes.py::test_submit_records_who_submitted_defaulting_to_gui`,
`::test_group_records_the_agent_on_every_member`, `::test_submit_rejects_an_unknown_created_by`;
`tests/test_agent_plugin_jobs.py` (fake server per verb, plus
`test_against_the_real_server_jobs_are_recorded_as_agent` over HTTP to the real app);
`agent-plugin/mcp/test_stdio.py::JobsServerStdioTests`.

## 2026-10-07 — Agent jobs need the user's approval; the server runs the approved plan

**Decision.** An agent's direct submission (`created_by: "agent"` on `POST /api/jobs` or
`/api/jobs/groups`) is refused with 403 unless the project setting `agent_auto_submit`
("Agent may submit without approval") is on; it is off by default. The agent proposes instead:
`/api/proposals` stores a plan per project (`code/ti-toolbox/proposals/<id>.json`), plans each
step server-side, and the user approves, edits or rejects it in the app. On approval the server
queues the steps itself: roots at once, dependants when every job of the steps they name has
succeeded, through the same `plan_submission` checks `/api/jobs/groups` makes. A `sim_from_flex`
step is resolved when its flex step has finished, by `resolve_flex_simulation`, which moved from
the agent plugin into `tit.sim.montage_sources` and is served as `GET /api/sim-from-flex`.
Contract (additive): `Settings.agent_auto_submit`, `JobStatus.created_by`, the proposal paths
and schemas, and a `proposal` variant of `JobsWsServerMessage`. Supersedes nothing; extends the
entry above.

**Why.** An agent that queues hours of FEM work, or replaces results, on its own reading of a
request is the failure users fear most; a plan card the user reads (outputs, overwrites, ETA,
the settings in their terms) and approves keeps the user directing the work while the agent does
the typing. The server queues approved steps so the agent need not stay connected for a
multi-hour pipeline. Dependants are deferred, not queued with job-level `after`, because
submission preflight refuses a job whose inputs a predecessor will produce (flex after `pre`)
and a flex result's montage does not exist until the run does. One resolver for flex -> sim
keeps the plugin and the server from choosing different electrodes or currents.

**Cost.** A dependent step's jobs appear in the job list only when they are queued, so the card,
not the list, shows what is still to come. Proposals are never pruned (a few KB each). The
approval is not a security boundary: the agent's MCP server holds the server token, and anything
with the token can call approve or flip the setting; it binds a cooperating agent that uses the
plugin's tools.

**Alternatives rejected.** Agent-side sequencing with `wait_for_job` then `submit_job` (the
agent must stay connected; a closed laptop lid stops the pipeline). Queuing the whole DAG up
front with `after` (refused by preflight; no montage yet). Cookie-only approval routes (an agent
with the token can mint a cookie, so it adds friction, not protection).

**Revisit if** the token ever stops being a single full-access secret (then approve can require
a user session), or proposals need retention.

**Evidence.** `tests/test_proposals_routes.py` (create/plan, reject, edit then approve, approve
with edits, refusal while a step would overwrite, deferred `sim_from_flex` queued by the server
after a fake flex job, error then `run` retry, failed prerequisite skips its dependant,
malformed proposals); `tests/test_jobs_routes.py::test_an_agent_cannot_submit_until_the_user_allows_it`;
`tests/test_flex_simulation_resolver.py`; `tests/test_agent_plugin_jobs.py` (proposal verbs, and
`test_against_the_real_server_jobs_are_recorded_as_agent`: refused submit -> propose -> approve
over HTTP -> queued as `agent`).

## 2026-10-07 — The Assistant pane: the user's own Claude Code or Codex in a host terminal

**Decision.** The desktop app gains an Assistant page (pinned above System) that runs the user's own
`claude` or `codex` CLI in a host pseudo-terminal, in the session's project folder, with the bundled
`agent-plugin/` attached for that session and `TIT_SERVER_URL`/`TIT_SERVER_TOKEN` of the connected
session in its environment (ARCHITECTURE §6). The preload bridge gains one optional namespace,
`assistant` (`detect`, `start`, `write`, `resize`, `kill`, `onEvent`, `openInTerminal`): 23 → 24
top-level entries (ADR row 14). The renderer names only `"claude" | "codex"`; main decides the
executable, arguments, cwd and environment. Two dependencies: **node-pty 1.1.0** (main, shipped
unpacked) and **@xterm/xterm 6.0.0 + @xterm/addon-fit 0.11.0** (renderer, bundled). The packaged app
carries `agent-plugin/` as an extraResource. This closes the "Users drive jobs from their own agent"
entry's "Revisit if the desktop gains an 'open my agent here' terminal action": the env pair also
replaces `docker inspect` discovery for sessions started here, so native runtimes work. A session
started here is an ordinary agent to the server: it proposes plans and the user approves them on the
Jobs page (entry above), unless the project allows direct submission.

**Flags, as verified on 2026-10-07** (Claude Code 2.1.293, codex-cli 0.155.1, this Mac):
- Claude Code: `--plugin-dir <Resources>/agent-plugin`. `claude --plugin-dir … plugin list --json`
  lists it as `ti-toolbox@inline` (scope `session`) beside an installed `ti-toolbox@ti-toolbox`, and
  `claude --plugin-dir … mcp list` registers `plugin:ti-toolbox:ti-toolbox` and
  `…:ti-toolbox-jobs` once each, both connected: no double registration, and the session gets the
  app's own plugin version (the installed marketplace copy here was 0.2.0, without the job server).
  A plugin MCP server inherits the CLI's environment (an env-dumping server saw both variables).
- Codex: `-c mcp_servers.ti-toolbox.command='python3'`, `….args=['…/mcp/server.py']`, the same two
  for `ti-toolbox-jobs`, `-c mcp_servers.ti-toolbox-jobs.env_vars=['TIT_SERVER_URL','TIT_SERVER_TOKEN']`
  and `-c developer_instructions='…read …/skills/ti-run-pipelines/SKILL.md…'`. `codex … mcp get
  ti-toolbox-jobs --json` parses them (re-run by `assistant.test.ts` when codex is installed);
  `codex … debug prompt-input` shows the instruction in the model input; an env-dumping server saw
  the two variables only with `env_vars` (Codex starts MCP servers with a minimal environment).
- Login state: `claude auth status` and `codex login status` exit 0 signed in, 1 signed out (signed
  out reproduced with an empty `CLAUDE_CONFIG_DIR` / `CODEX_HOME`). Only the exit code is read.

**Why.** The "Users drive jobs" entry let a user's agent drive jobs, but only after a manual plugin install,
a Codex config edit and Docker on the agent's PATH; most users never open a terminal. Running the
CLI on the host keeps the user's own login and our no-credentials rule; the container has neither
the CLI nor the login. Session-only flags leave `~/.claude` and `~/.codex` untouched. node-pty is
the PTY VS Code ships: N-API, so its Node-ABI binary loads in Electron 44 without `electron-rebuild`
(`npmRebuild: false` stays), and its single package carries darwin-arm64 **and** darwin-x64 plus
win32-x64 prebuilds, so the release job's one arm64 macOS runner packages both Mac arches. Linux
compiles it during `npm ci` (verified in `node:22-bookworm`, amd64: `build/Release/pty.node`, a PTY
echo). xterm.js is the standard terminal emulator for the web; the renderer had none (the existing
"Terminal" is the job-log console, §6).

**Cost.** A native module in the package: `files`/`asarUnpack` entries, ~1 MB unpacked on macOS,
2.8 MB on Windows (debug symbols and win32-arm64 excluded). node-pty 1.1.0 publishes the macOS
`spawn-helper` without its executable bit (every spawn failed with `posix_spawnp failed` under
Electron 44); `scripts/fix-node-pty.mjs` restores it at `postinstall`, and `verify-package.mjs`
checks it. The MCP servers still need the host's `python3`. The renderer bundle grows by xterm.

**Security.** A served page can already reach the host through Docker's socket in its container,
but the bridge still narrows the new capability: top-frame sender, loopback server origin, an
existing local project folder, a two-value CLI enum, sizes clamped, input capped at 1 MiB per
write. The token reaches only the CLI's environment (and, for **Open in system terminal** on macOS,
a 0700 script in user data that deletes itself on its first line); it is never an argument or a log
line.

**Alternatives rejected.** `@lydell/node-pty` (per-platform optional packages: npm installs only the
runner's arch, so the x64 Mac app would ship without a binary) and
`@homebridge/node-pty-prebuilt-multiarch` (per-ABI prebuilds tied to Electron releases). Running the
CLI in the container's terminal. Writing MCP entries into the user's CLI configuration. Inlining the
6 KB `ti-run-pipelines` skill into Codex's argv (Windows command-line limit, quoting through
`cmd.exe`); a one-line pointer to the bundled file is enough. Probing `claude plugin list --json`
to skip `--plugin-dir` when a plugin is installed (the session copy already supersedes it without
duplication, and its version matches the app).

**Revisit if** node-pty ships `spawn-helper` executable (delete `fix-node-pty.mjs`), Codex gains a
plugin-directory flag, or a Windows/Linux acceptance run disagrees with the unverified paths below.

**Not verified here.** Windows ConPTY sessions and the `.cmd` shim route through `cmd.exe`, the
Windows and Linux **Open in system terminal** routes, and signing/notarisation of the unpacked
`pty.node`/`spawn-helper` (electron-builder signs Mach-O files in `app.asar.unpacked` with the app;
only the release job has the identity). A Linux package was not built on this Mac.

**Evidence.** `desktop/src/main/assistant.test.ts` (login-shell PATH, detection, exact launch per
CLI, env holds the token and no log does, sessions, a real node-pty run, the installed Codex parsing
the overrides); `desktop/tests/unit/assistant-page.test.tsx` (states);
`desktop/tests/e2e/assistant.spec.ts` (offscreen: a stand-in `claude` started from the page in the
project folder with `--plugin-dir`, the server URL and a token in its environment, typed input
reaching it, exit shown, Codex not installed, no token in `main.log`);
`desktop/tests/e2e/packaged-launch.spec.ts` (the packaged main loads node-pty and runs a PTY);
`desktop/tests/unit/package-runtime.test.ts` and `node scripts/verify-package.mjs` against
`--dir` builds for mac-arm64, mac (x64) and win-unpacked.

## 2026-10-08 — The agent's waits run in the background; it asks before guessing

**Decision.** The job server's `wait_for_approval` is replaced by `watch_proposal`, which returns
only on a proposal's next change (decision, a step reaching a final state, all done), with the
finished steps' output folders, files and log tails. Waits default to 1500 s for Claude Code and
45 s for other clients (`initialize`'s `clientInfo.name`), send `notifications/progress` to the
client's token, and stop on `notifications/cancelled`. Each `tools/call` runs on its own thread.
The Assistant page starts Claude Code with `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=5000` unless the
user set it. The `ti-run-pipelines` skill makes the watch the last call of a turn and adds an
ask-first rule for a missing subject, target, run type or goal. Plugin 0.5.0.

**Why.** The frozen chat was Claude Code's automatic backgrounding, not the agent: an MCP call in
the main conversation moves to a background task only after 120 s (`te=120000`, gated by
`tengu_mcp_auto_background`, default on, in the 2.1.294 binary; documented at
code.claude.com/docs/en/mcp), or at once when the user types. `wait_for_approval` returned after
its 50 s default, so the agent re-called it in the foreground indefinitely; the agent's own
`wait_for_job(timeout_s=600)` crossed 120 s and became the "MCP task" that worked. MCP
task-augmented calls (`execution.taskSupport`) exist in the binary but behind `tengu_mcp_tasks`
(default off). A stub server under `claude -p` with `CLAUDE_AUTO_BACKGROUND_TASKS=1` and a 3 s
threshold showed the move after 3 s, a progress token on every call, the turn ending, the result
waking the agent, and the agent's next call arriving while the first still ran — which a
single-threaded server would have held up for the whole wait. codex-cli 0.155.1 ran the same
calls in sequence inside the turn (its per-tool timeout is 60 s), so Codex gets a short wait and
a "say status" turn end.

**Alternatives rejected.** MCP tasks (off behind a flag; a task store for one wait). A
`run_in_background` Bash watcher script (permission prompts, plugin path and token plumbing).
Polling with short waits (a foreground call per poll, the observed freeze). Setting
`CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` globally (outside the app's reach; documented instead).

**Evidence.** `tests/test_agent_plugin_jobs.py` (`watch_proposal` once per change, rejection, the
per-client budget, and over the real stdio entry point: a pending watch does not block
`get_proposal`, progress carries the client's token, cancel ends it);
`desktop/src/main/assistant.test.ts` (the launch environment).

## 2026-10-08 — The Assistant terminal draws with WebGL and fits its card exactly

**Decision.** The Assistant pane loads **@xterm/addon-webgl 0.19.0** (falling back to xterm's DOM
renderer when WebGL is unavailable or its context is lost) and **@xterm/addon-web-links 0.12.0**
(printed http(s) links open through the existing `openExternal`; no bridge entry, still 24). The
terminal's host has no padding (the card has it), the page keeps a fixed height below 1140 px, and
xterm opens only after the mono font has loaded. ANSI colours are GitHub's light and dark terminal
palettes, `minimumContrastRatio` is 4.5, and the terminal follows `<html data-theme>` and the OS
scheme rather than the theme store.

**Why.** Measured on the previous page (e2e stand-in, 2026-10-08): FitAddon reads its host's
computed height, which with `box-sizing: border-box` included the host's 16 px padding, so at
1280×900 it fitted 49 rows (735 px) into 726 px of content and the last row's lower half sat under
the card's clipped edge — the cut-off status line. Below 1140 px `.page-layout { height: auto }`
let the page grow to its content: at 1024×680 the terminal was 128 rows, 2050 px tall, the shell
scrolled 1414 px and the CLI drew its status line under the jobs rail. The DOM renderer draws
block and box characters with the font; the app bundles only Plex Mono's Latin subset, so the
logo's quadrants came from a fallback font with gaps between cells (the broken "▘▘" fragments).
xterm's default white and bright white were invisible on the light theme.

**Alternatives rejected.** The DOM renderer with a font that has block glyphs (cells still do not
join at a line height above 1, and Claude Code's symbols still fall back); the canvas renderer
addon (no release for xterm 6); a link provider for file paths (`openPath` maps server paths; a
host-path open needs a new bridge entry, and the budget is frozen at 24); `screenReaderMode` to make
the text testable (an always-on live region for a full-screen TUI) instead of an e2e-only handle.

**Evidence.** `desktop/tests/e2e/assistant.spec.ts` "the terminal's rows fit the card exactly…".

\n
## 2026-10-08 — The Assistant starts at Low effort, and the user can pick effort and model

**Decision.** `assistant.start` and `assistant.openInTerminal` take an optional second payload,
`{ effort?, model? }`, enums only — a change to a frozen bridge entry, not a new one (the budget
stays 24). Effort is `low` (default, "Low (default)"), `medium`, `high` or `default` ("My CLI
default": no flag); model is `default`, `opus`, `sonnet`, `haiku`, `fable` for Claude Code and only
`default` for Codex. Main validates against an allowlist (anything else is `Untrusted assistant
request.`) and builds the argv: Claude Code `--effort <level>` and `--model <alias>`, Codex
`-c model_reasoning_effort="<level>"`; the system-terminal script gets the same flags because it
runs the same launch. The Claude Code default is `--model sonnet`, Codex keeps its own model. The page remembers the choice per CLI in `localStorage` (like the execution
preferences), applies it on the next Start/Restart and says "Applies on restart" while a running
session differs. The menus stop at High.

**Why.** The maintainer asked for a visible control with Low effort (and Sonnet for Claude Code) as the
default: proposing a job plan does not need the slowest, most plan-limit-hungry setting. Verified 2026-10-08 on
Claude Code 2.1.294 and codex-cli 0.155.1: `claude --effort bogus` only warns ("Valid values: low,
medium, high, xhigh, max") and carries on with the default, so the allowlist is ours; `--model opus|
sonnet|haiku|fable` each started a session on the latest model of that family
(`claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-1`); `codex debug
models` lists `low, medium, high, xhigh, max` as supported reasoning levels (`xhigh` on every
model, `max` not on gpt-5.5) and does not reject an unknown value at parse time.

**Alternatives rejected.** Free-text model or effort (a renderer-chosen argument is exactly what
§6 forbids); a Codex model menu (its models are an account-dependent catalog with no stable
aliases); `xhigh`/`max` in the menu (not on every Codex model; `/effort` reaches them in-session);
writing the setting into `~/.claude/settings.json` or `~/.codex/config.toml` (persistent side
effects outside the app); a new bridge entry (budget).

**Evidence.** `desktop/src/main/assistant.test.ts` "session options" (argv per CLI and option,
defaults, rejected values); `desktop/tests/unit/assistant-page.test.tsx` (persistence, hint);
`desktop/tests/e2e/assistant.spec.ts` (the stand-in receives `--effort low --model sonnet` by default and then
the chosen flags; the header fits at 1024 and 1440).

## 2026-10-08 — The run pages' defaults are one server table; agents send only what they chose

**Decision.** `tit/server/app_defaults.py` `APP_DEFAULTS` holds, per job kind, what the
Pre-processing, Simulator and Optimizer pages start with where it differs from or adds to the
config class's own defaults (`pre`: DICOM conversion, FastSurfer, charm, skip existing,
FreeSurfer subregions; `sim`: `map_to_fsavg` off plus the two `default_factory` values the schema
cannot carry; `flex*`: goal, field, 1 mA, the 8×8 mm ellipse and the solver settings, focality goal
and threshold settings for `flex_adaptive`/`flex_pareto`; `ex`: 0.2 mA steps, 1.6 mA channel
limit). `dev/build_schema.py` writes it into `config.schema.json` as `x-app-defaults`, served by
`GET /api/schema`; the pages render once that document has loaded and build their forms from it.
The server fills it into any config sent with `created_by: "agent"` (validate, plan, preflight,
jobs, groups) and into every proposal step. The agent plugin's `FLEX_UI_DEFAULTS`,
`PRE_UI_DEFAULTS`, `SIM_UI_DEFAULTS` and `_with_app_defaults` are deleted. A frozen-surface change
(`contracts/`): additive, and absent `created_by` or another creator behaves as before.

**Why.** The plugin carried a hand copy of the renderer's literals ("move server-side if they start
drifting"), and the renderer its own; three copies of one fact.

**Alternatives rejected.** A `GET /api/defaults/{kind}` route (the schema document is already
served, cached and mocked, and is where a form's other defaults come from); bundling the generated
JSON into the renderer (a 145 kB import for a few values, and not what the server serves);
keeping a renderer fallback while the schema loads (a second copy); filling defaults for every
creator (a script that omits a field means the dataclass default).

**Evidence.** `desktop/tests/unit/app-defaults.test.ts` (each page's starting values equal the
literals it had at 07ee0ac0); `tests/test_jobs_routes.py::test_an_agents_config_gets_the_run_pages_defaults`;
`tests/test_agent_plugin_jobs.py` (the plugin sends only the agent's fields; against the real app
the job's spec carries the page default).

## 2026-10-08 — Region lookup and its ROIs are served; the picker keeps one shared rule

**Decision.** `GET /api/catalog/regions?subject=&q=` (`tit.catalog.find_regions`) finds the
subject's atlas regions whose names hold every word of the query (side words ignored) and returns,
per atlas, the matches and ready `FlexConfig` ROIs `rois.all|left|right` built by
`tit.catalog.region_roi`. The agent plugin's `find_regions` passes it through (it only remembers
region names for a proposal's "Target: …" note); its own atlas walk, side split and ROI builder are
deleted. The desktop's `roiToConfig` keeps building the picker's ROI in TypeScript, and
`tests/fixtures/region_rois.json` drives both implementations (`tests/test_region_rois.py`,
`desktop/tests/unit/roi-region-table.test.ts`). Additive contract path and schema (`RegionMatch`).

**Why.** The plugin rebuilt the renderer's ROI rule by hand. The picker cannot simply call the
server instead: it builds the ROI from an arbitrary chip selection (not a name query) on every
click for the live plan and cost, synchronously, alongside spherical and mask modes that have no
server counterpart; a request per click would make plan building async for no new truth. The rule
itself is four lines, so one table both must pass is the smaller single source.

**Alternatives rejected.** A server route that builds an ROI from a selection, called by the picker
(async plan building, a round trip per click); generating the TypeScript from Python (a code
generator for four lines).

**Evidence.** `tests/test_region_rois.py` (shared table, search, route 200/404/422);
`desktop/tests/unit/roi-region-table.test.ts`; `tests/test_agent_plugin_jobs.py` (passthrough and
the proposal note).

## 2026-10-08 — One electrode-pairing rule for a flex-search result

**Decision.** Every path that turns a finished flex-search run into a montage pairs its electrodes
with `tit.catalog.pair_by_channel` — the optimiser's `[channel, array]` per electrode
(`_save_optimized_positions` in `resources/map-electrodes/tes_flex_optimization.py`, carried into
`electrode_mapping_<net>.json` by the Hungarian mapping), consecutive only when that record is
absent or unusable — and keeps every channel. `resolve_flex_montage` (used by `/api/plan`'s flex
montage sources and `/api/catalog/flex-runs/{run}/mapping`) reads its pairs through the catalog's
readers (`flex_optimized_pairs`, `read_flex_mapping`); `resolve_flex_simulation` (the agent's
`sim_from_flex` and `GET /api/sim-from-flex`) builds its montage through `resolve_flex_montage`,
which reads a net the run is already mapped to instead of re-mapping it and rewriting the cache.
Wire shapes are unchanged.

**Why.** `resolve_flex_montage` paired the first four electrodes consecutively while the catalog
(what the Simulator page shows) paired by channel, so a record listed out of channel order gave
`/api/plan` and the agent different electrodes than the page, and an mTI run lost its third and
fourth channel there. The optimiser writes channel-major order today, so results produced by
TI-Toolbox's own flex-search do not move; only out-of-order records and mTI runs did.

**Alternatives rejected.** Consecutive pairing everywhere (ignores what the optimiser recorded);
re-mapping on every request (rewrote the cache the catalog reads and repeated the assignment).

**Evidence.** `tests/test_flex_simulation_resolver.py` (an out-of-order fixture: catalog,
`resolve_flex_montage` optimized and mapped, and `resolve_flex_simulation` agree; a cached net is
read with the mapping refused; a new net is mapped once, then read);
`tests/test_montage_sources.py`, `tests/test_montage_source_safety.py`.

## 2026-10-08 — A job may not write outside the project

**Decision.** `tit.server.routes.plan.plan` refuses (422) a plan whose job output folder resolves
outside the project, and `check_overwrite_permission` now plans every submission, `overwrite` or
not, so `/api/jobs`, `/api/jobs/groups`, reruns and approved proposal steps are refused the same
way; a proposal step shows it as a planning error and cannot be approved. Contract: documented
422s, no shape change.

**Why.** An absolute `FlexConfig.output_folder` (or `AnalyzerConfig.output_dir`, a blender
`output_dir`, or a name with `../`) let a job — an agent's in particular — write anywhere the
container can, and `overwrite: true` skipped the only planning step submission made. The plan
already resolves each job's destination for every kind, so one check there covers every field.
The desktop's run pages send only folders the server resolved under the project (the Optimizer
plans with `output_folder: null` and joins the run name to the folder it gets back).

**Alternatives rejected.** Checking each path field per kind (a new field would slip through);
rejecting every absolute folder (the Optimizer's own submissions are absolute paths inside the
project).

**Evidence.** `tests/test_output_jail.py` (plan, both submit routes with `overwrite: true`, a
climbing name, a proposal dry run and approval).

## 2026-10-08 — Region search covers the shipped MNI atlases; their names come from the manifest

**Decision.** `tit.catalog.find_regions` (`GET /api/catalog/regions`, the agent's `find_regions`)
searches the subject's own atlases and then the MNI volume atlases the Optimizer's ROI picker
offers (`atlases(..., space="mni", kind="subcortical")`); each entry carries `space`, and an MNI
entry's ROIs are the `SubcorticalROI` with `atlas_space: "mni"` the picker builds
(`tests/fixtures/region_rois.json` gains that case). `tit.atlas.segstats.resolve_lut_for_atlas`
names a shipped MNI atlas's labels from the table `resources/atlas/manifest.json` lists for it
(`manifest_lut`, the lookup `tit.opt.roi_spec._find_volume_lut` already made), and a region cache
(`<atlas>_labels.txt`) for such an atlas records that table (`# lut <name>`) so one named before is
rebuilt once. Contract: `RegionMatch.space` (additive).

**Why.** An agent could not target what the picker offers in MNI space (CIT168 nuclei, MASSP,
Harvard-Oxford). Searching them exposed a picker bug: the Glasser, Schaefer and MASSP tables are
not `{stem}_LUT.txt`, so their labels were named from FreeSurfer's table (Glasser label 1 read
"Left-Cerebral-Exterior", Schaefer label 10 "Left-Thalamus"); a name search would have handed an
agent a cortical parcel for "thalamus".

**Alternatives rejected.** MNI search behind a flag (the agent cannot know to ask);
deleting stale caches at startup (the image's resources may be read-only, and a cache that names
its table is self-checking).

**Evidence.** `tests/test_region_rois.py` (shared table incl. the MNI case; subject atlases first,
then MNI with `space`); `tests/test_atlas_segstats.py::TestManifestNamedLut` (the manifest table
names a shipped atlas; a cache named from another table is rebuilt once).

## 2026-10-08 — The kind -> config class table is served; the plugin's copy is deleted

**Decision.** `dev/build_schema.py` writes `x-kind-classes` (`SIMPLE_KIND_CLASS` plus
`AMBIGUOUS_KIND_DEFAULT` from `tit.server.routes.validate`) into `config.schema.json`, which
`GET /api/schema` serves; the agent plugin's `get_config_schema` resolves a kind through it and
its `SCHEMA_CLASS` dict is gone. Additive contract key.

**Why.** The plugin's table was a hand copy of the server's (nine of fourteen kinds), the same
drift the run-page defaults had before `x-app-defaults`.

**Alternatives rejected.** `get_config_schema` sending the kind to a new route (the schema
document is already fetched for the `$defs` and the defaults); keeping the copy with a sync test
(two tables and a test instead of one table).

**Evidence.** `tests/test_config_schema.py::TestBuildSchemaScript::test_build_schema_serves_the_servers_kind_to_class_table`;
`tests/test_agent_plugin_jobs.py::test_against_the_real_server_jobs_are_recorded_as_agent`
(`get_config_schema(kind="flex_adaptive")` -> `FlexConfig` over HTTP).
