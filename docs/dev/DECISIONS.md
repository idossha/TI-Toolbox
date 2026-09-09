# Architecture decisions

[ARCHITECTURE.md](ARCHITECTURE.md) defines current behavior; this record explains consequential
choices and reversals. [DESIGN.md](DESIGN.md) owns UI details, [BENCHMARKS.md](BENCHMARKS.md)
owns retained measurements, and [RELEASE.md](RELEASE.md) owns outstanding work.

This log was condensed on 2026-09-09. Git history retains full earlier narratives. Add an entry
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
| 14 | 2026-08-27 | Preload bridge budget, **13** top-level entries, no growth without an ADR line | live |
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
| 26 | 2026-09-05 | Tetravox updates itself against a protocol range; electrode dots; one selection grammar; a pipeline is a job group | live; native panes replace the embed-specific electrode implementation (27) |
| 27 | 2026-09-06 | Native run-page panes; the viewer is a separate desktop application; jobs tables | pane half live; viewer half superseded by 29 |
| 28 | 2026-09-06 | Managed host install of Tetravox; the pipeline's Subjects node and readiness gating; jobs tables on all three run pages | install half superseded by 29; the rest live |
| 29 | 2026-09-06 | **The embed is restored, baked in the image, on the Viewer's own two sub-pages.** Nothing installs Tetravox on the host | live |
| 30 | 2026-09-07 | External audit response: the six scientific corrections, the server hardening, one release workflow | live |

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
branches. Current commands, workflow names and gates live in [RELEASE.md](RELEASE.md).

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

### 2026-09-06/09 — UI consistency without duplicate state

**Decision.** Keep shared controls, selection and region-toggle models. Terminal Clear uses a
watermark, never deletes logs; pages do not auto-pin completed jobs. Overview replaces Subject
Info. The rail uses digits 0–9, Settings uses its own shortcut, and the preload budget is 13 host
entries including `saveFile`, not a viewer launcher. Computational extensions use the common
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
or marker design. Current visual rules and open work live in DESIGN and RELEASE.

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
