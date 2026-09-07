# v3 program history

> Historical. This is the record of how v3 was built; the living description is
> `docs/dev/ARCHITECTURE.md`, the reasoning is `docs/dev/DECISIONS.md`, the measured
> numbers are `docs/dev/BENCHMARKS.md`, and the UI contract is `docs/dev/DESIGN.md`.
> Where this file and those disagree, they win.

One chronological record of the v3 (Electron desktop) development programs on
`feature/v3-electron-gui`, 2026-08-27 → 2026-09-07. It replaces ~120 per-program
plan files and per-lane evidence notes that used to live under `dev/notes/`.

**This file is not a contract.** The durable records are:

- `docs/dev/ARCHITECTURE.md` — what the system is.
- `docs/dev/DECISIONS.md` and the ADR table in `docs/dev/ADR.md` —
  what was decided and why.
- `docs/dev/DESIGN.md` — the UI design contract and its acceptance numbers.
- `docs/dev/requirements/*` — the dated requirement documents.
- `docs/dev/ROADMAP.md` — the gate table.
- `docs/dev/v3-implementation-plan.md` — the live plan-of-record index.

What is kept here is only what those do not carry: for each program, the
maintainer's ask, what shipped, which decisions survived and where they are now
recorded, which plans were reversed (several were reversed the same day they
were written), and the **gotchas** that were paid for once and would otherwise
be lost.

Measured numbers live in `docs/dev/BENCHMARKS.md`, once, with the conditions they
were measured under. This file does not restate them.

Still-live companion files under `dev/notes/`:

- `v3-pipelines/RUNBOOK.md` — live smoke-run runbook, still cited by e2e specs.
- `v3-ui-program/u0-design-notes.md` — the verbatim TypeScript contract
  signatures `docs/dev/DESIGN.md` §5 defers to.
- `v3-ui-program/wireframes.md` — per-page ASCII layouts and empty-state copy.
- `flex-search-multicore-analysis.md` — unrelated 2026-04 backend analysis.
- `../spikes/README.md` — the merged native-desktop spike verdicts.

`README.md` in this directory maps every retired file path to its section here.

---

## 2026-08-27 — v3 build program + spikes

**Ask:** build every screen of the v3 Electron GUI in parallel against a frozen
v1 contract, backed by real `tit.server` endpoints, ending in a real E2E run on
Dataset 000.

**Shipped:**
- `tit/server/routes/` with `catalog_v1.py`, `files.py`, `viewers.py`, `plan.py`,
  `validate.py`, `schema.py`, `settings.py`, `capabilities.py`, `jobs.py`,
  `ws_jobs.py`.
- `contracts/openapi.v1.yaml`, still the live contract.
- One directory per screen under `desktop/src/renderer/pages/`.
- The job model — queue/group/progress/liveness/cancel/rerun/force,
  `events.jsonl`, `WS /ws/jobs`. Every later redesign judged it the strongest
  part of v3 and left it untouched.

**Decisions that survived:** contract-first development (the mock server is
built from `openapi.v1.json`; the backend implements the same contract) —
`docs/dev/ADR.md`. Lane ownership discipline carried into every
later program.

**Reversed / superseded:** the flat per-page IA this plan produced (19 nav rows,
7 separate subject pickers) was replaced by the workflow-first IA on 2026-09-02.
NiiVue-as-engine (spike c) was superseded by Tetravox.

**Lessons and gotchas:**
- NiiVue: four 256×256×208 volumes load in 1.1–1.5 s; GM mesh (169 k verts)
  renders in 144–272 ms, central surface (491 k verts) in 379 ms; ~190 MB JS
  heap. `elm_data2node_data()` interpolation costs 38 s once and must be cached;
  per-surface export afterwards is 0.2–0.6 s.
- NiiVue traps: cannot read Gmsh `.msh` (needs server-side `mesh_io`
  conversion); a `name:` without an extension throws; `.curv` scalars do not
  colour meshes (use GIfTI `.func.gii`); volume clip planes do not cut meshes.
- `TI_max` percentiles must be computed GM-masked, not whole-volume — scalp
  p99 = 0.81 V/m vs GM p99 = 0.17 V/m.
- `write_gifti_surface(msh, fn, geometry=None)` keeps mesh mm in T1 scanner RAS
  (bbox verified). Never pass a volume `geometry` or the surface shifts by
  `c_ras`.
- fastapi/uvicorn install into `idossha/simnibs:v2.4.0` with zero numpy
  conflicts; a server bound to `0.0.0.0` is reachable from the macOS host at
  `127.0.0.1:8765` for both REST and WS; cookie + Bearer auth, TrustedHost and
  Origin-checked WS handshakes all verified.
- Import cost: `tit.sim` / `tit.opt` each ~3.1–3.3 s and 388 MB RSS, almost
  entirely `import simnibs` (3.4 s / 387 MB on its own). `tit.analyzer`,
  `tit.stats`, `tit.pre` do not pull SimNIBS (0.4–0.9 s). Hence: the server
  imports SimNIBS lazily so `/api/health` answers immediately.
- Host pytest regressed 30 s → 87 s because `test_telemetry.py` joined *every*
  alive daemon thread (2 s timeout × 6 call sites) once another test left a live
  `JobManager` poll thread running. Fixed with a named `"tit-telemetry"` thread,
  join-only-telemetry-threads, `TIT_NO_TELEMETRY=1` by default and JobManager
  teardown fixtures — back to ~26 s. The same audit found `GA4_MEASUREMENT_ID` /
  `GA4_API_SECRET` in `tit.constants` were live production credentials being
  POSTed to from tests; now a session-wide `_send_ga4` no-op patch.

---

## 2026-09-02 — UX redesign, workflow-first IA

**Ask:** three independent design proposals (density-first, viewer-centric,
workflow-first) judged on feasibility, risk and testability, plus research
spikes on embedding Tetravox as the internal viewer and on the server-side
deltas that needs.

**Shipped:**
- `pages/overview` (workflow-first's Project/Workbench merge) and a single
  merged `optimizer` page (flex + ex + mEx).
- `tit/server/routes/tetravox.py` and `scene.py` — the raw-file route and the
  scene-document delta.
- The iframe-embed client (`desktop/src/renderer/viewer/`).

**Decisions that survived:** Tetravox as a released, versioned embed service
rather than vendored source, and same-origin HTTP via
`/api/files/raw/{path}` rather than a custom Electron scheme — ADR rows 15–17.
The workflow-first IA (one subject switcher; nav = Project / Prepare / Simulate /
Optimize / Analyze / Results / Viewer / Jobs) became the plan of record over
`docs/dev/DESIGN.md` §2–§5.

**Reversed / superseded:** in-process `@tetravox/engine` vendoring under
`desktop/vendor/**` was built and measured, then rejected by the maintainer
("wrap around it as a microservice") and replaced by the iframe/postMessage
embed the same day. The `TitScene` JSON shape was retired for Tetravox's own
ViewSpec v2 with URL dataset refs. Viewer-centric and density-first lost to
workflow-first (35 vs 33 vs 27).

**Lessons and gotchas:**
- `@tetravox/engine` ships zero React; the app chrome (layers, histogram,
  regions, info, coordinate, measure panels) is 9,345 LOC of React that an
  in-process route would have had to rebuild and a whole-app iframe gets free.
  That single fact reordered the three proposals.
- `packages/wasm/pkg` (848 KB `tvx_wasm_bg.wasm`) is git-ignored and `npm pack`
  silently drops it — Tetravox was not installable until an upstream one-liner
  (`rm -f packages/wasm/pkg/.gitignore` after `wasm-pack`).
- Vite config needed to embed the engine directly: `optimizeDeps.exclude` the
  three `@tetravox/*` packages, `worker.format: 'es'` (the engine uses
  `new Worker(url, {type:'module'})`; Vite's default IIFE worker format cannot
  be a module worker), `assetsInlineLimit: 0`, `target: 'chrome138'`.
- No custom Electron scheme is needed: the dataset worker does a plain
  same-origin `fetch(url)` and the session cookie rides along.
- CSP needs `script-src 'self' 'wasm-unsafe-eval'` for WASM instantiation.
- The raw-file route reuses Starlette's `FileResponse` for Range/206/ETag (only
  304 and HEAD needed hand-writing) and deliberately does **not** emit
  `*.tetravox.json` server-side: `DatasetRef.fingerprint` is defined over
  post-gunzip bytes (which would force inflating every `.nii.gz` per request)
  and its `path` is relative to the scene file, meaningless over HTTP.
- Duplication found, and later the compaction target: `getSimulationsFor`
  declared 7×, two ROI pickers (327 + 271 LOC), two `PlanSummary`
  implementations (120 + 95 LOC) behind five near-identical `PlanPanel` shells,
  Freeview/Gmsh launch logic implemented independently on three pages.
- Density-first had the best evidence (a 674 px work column at 1280 px, 94 px of
  per-section chrome, each cited to a CSS line) and still lost: workflow-first
  was the only proposal that answered the maintainer's actual complaint — the
  old IA had no notion of *where a subject is*.

---

## 2026-09-03 — Native desktop research (parked)

**Ask:** could TI-Toolbox drop X11, FreeSurfer and Gmsh and ship as a single
native Electron executable, with no Docker, on Linux/Windows/macOS?

**Outcome:** judged "realistic, with three precise corrections", then **parked**
in favour of the shipped Electron + one-Docker-image v3.

- Only Linux x86_64, Windows x64 and macOS Apple Silicon are natively viable.
  No Intel Mac (bpy ≥ 5, torch 2.6 and SimNIBS's petsc4py fork ship no
  x86_64-macOS wheels; SimNIBS itself dropped Intel Mac at 4.5), no ARM64 Linux
  or Windows.
- Installed size ~2.5–3.5 GB (SimNIBS wheel 185 MB + atlases 220 MB + torch-cpu
  715 MB + bpy 200–400 MB) against Tetravox's ~100 MB — auto-update would have
  to be component-wise.
- DWI preprocessing (QSIPrep/QSIRecon) has no native path on any OS, so Docker
  can only become optional for the core app, never removed.

**Decisions that survived** (ADR rows 18–21): native bundled runtime as the
deployment target with Docker optional for DWI and legacy FreeSurfer and Intel
Mac staying on Docker; FreeSurfer not required by default (charm +
`subject_atlas` + FastSurfer `--seg_only` covers the default pipeline, with
thalamic/hippocampal subfields only via optional Docker FreeSurfer); Docker
integration through a typed Engine API client over the socket/npipe rather than
dockerode, with CLI shell-out kept only for `docker context inspect`; Tetravox
replacing Freeview/Gmsh with X11 removed from the product. Two licence flags
were raised for any commercial distribution: ADMlib (GPLv2, non-commercial,
unused by our code) inside the SimNIBS wheel, and Intel MKL's EULA on Linux and
Windows.

**Lessons and gotchas:** the six spike lanes' verdicts and numbers are in
`docs/dev/SPIKES.md` — a native runtime reproducing the container's TI result
to 13–14 significant figures, FastSurfer's Dice 0.922/0.914 against `recon-all`,
exact `mri_convert`/`mri_segstats` replacements, and the packaging and
job-control findings. Gate for the program: host pytest 3122 passed / 17
skipped; desktop typecheck clean, lint 0 errors, vitest 43 files / 418 tests;
e2e quiet-check PASS. What it did **not** prove: any x86_64 or Windows
execution, a full `charm` run natively, the real 2–3.5 GB runtime through
electron-builder plus Developer ID notarization, FastSurfer beyond one subject,
Podman/Colima, or the Windows named pipe.

---

## 2026-09-03 — Docker streamline (one image, `tit.server`)

**Ask:** keep Docker, streamline everything else — one centralised image with
FastSurfer and Tetravox baked in, driven by compose plus the Docker Engine API;
park native mode.

**Shipped:**
- One image `idossha/ti-toolbox:<ver>` (amd64): SimNIBS 4.6 + `tit` +
  `tit.server` + fastapi/uvicorn/pyyaml/psutil, the built desktop UI at
  `/opt/ti-toolbox/ui`, the Tetravox embed at `/opt/tetravox/embed`, and
  FastSurfer `--seg_only` at `/opt/fastsurfer` with checkpoints pre-downloaded.
- The FreeSurfer image dropped entirely: `recon-all`, thalamic-nuclei and
  hippocampal-subfield stages and the MATLAB Runtime are gone, replaced by
  `tit/pre/fastsurfer.py`. Legacy `derivatives/freesurfer` stays readable
  (search order FastSurfer → legacy FreeSurfer → `labeling.nii.gz` → `masks/`).
- X11 removed everywhere: no `/tmp/.X11-unix`, `DISPLAY` or `xhost`; `x11.ts`,
  the Freeview/Gmsh routes and their launchers deleted.
- The desktop stack moved onto the Docker Engine API: reworked `stack.ts`, new
  `desktop/src/shared/composeFile.ts` (compose-subset parser with
  `${VAR}` / `${VAR:-default}` interpolation) and `docker/stackApi.ts`;
  `dockerCli.ts` and the `stacks.json` token file deleted — attach is by label.
- `to_tetravox_viewspec` emits a real ViewSpec v2 document
  (`contracts/tetravox-viewspec-v2.schema.json`).
- `Capabilities` drops `freesurfer` / `x11_display` / `gmsh` / `freeview` and
  adds `tetravox_embed{available,version,protocol}` and `fastsurfer`.

**Decisions that survived:** ADR rows 22–26 — one image; FreeSurfer dropped;
X11 removed; compose stays the definition while the Engine API drives it;
native mode parked untouched; the N0 cross-platform fixes kept. Also: the viewer
iframe's `sandbox="allow-scripts allow-same-origin"` is correct and is not to be
tightened (same-origin access is required for WASM and workers; the real
confinement is server-side CSP plus the absence of top-navigation, download and
popup flags), and the container port is always `TIT_SERVER_PORT` with ports
bound explicitly to `127.0.0.1`.

**Reversed / superseded:**
- Syncing `docs/releases/changelog.md` to main's v2.5.0 was reverted mid-lane —
  it broke `test_changelog_and_version`, since this branch's `tit/__init__.py`
  is still 2.4.0.
- `PreprocessConfig`'s `run_recon` / `parallel_recon` / `parallel_cores` /
  `run_subcortical_segmentations` became `run_fastsurfer` /
  `fastsurfer_threads`; legacy keys are aliased by `migrate_legacy_keys` with
  warnings surfaced in the HTTP response.
- Layout and Screenshot blocks were removed from the app's viewer inspector
  after QA found duplicated chrome. Ownership rule: the embed toolbar owns image
  chrome, the app inspector owns data only.
- `Dockerfile.ti-toolbox.layered` (the fast `FROM idossha/simnibs:v2.5.0`
  recipe) was later deleted by the maintainer. Only the from-scratch
  `Dockerfile.ti-toolbox` remains; `--layered`, `--from-scratch` and
  `--skip-ui-build` are accepted and ignored so old command lines still work.

**Lessons and gotchas:**
- Image size: `idossha/ti-toolbox:dev` **6.66–6.67 GB content size**, against
  the old two-image stack (`simnibs:v2.5.0` 6.15 GB content / 19.2 GB disk plus
  `ti-toolbox_freesurfer:v7.4.1` 21.9 GB content / 67.5 GB disk). `docker
  images` prints non-deduplicated *disk usage* (which later read 21.3 GB once
  `simnibs:v2.5.0` was cached alongside); always cite content size, which is the
  fresh-pull cost.
- `pip install -e /opt/fastsurfer` defaults to CUDA torch (~2 GB of
  `nvidia-cu12*` wheels) on a machine with no GPU. Pinning `torch==2.7.1` /
  `torchvision==0.22.1` from the CPU wheel index before the FastSurfer install
  cut that step from ~140 s to ~49 s.
- `COPY <dir> <existing-dir>` **merges**, it does not replace — `rm -rf
  /ti-toolbox/tit /ti-toolbox/resources` is needed before re-copying.
- `build.sh`'s version `sed` used `\s`, which is GNU-only and a silent no-op
  under macOS BSD sed; use `[[:space:]]`.
- FastSurfer on sub-ernie, native arm64: 4.84 GiB peak RSS, ~5 min wall.
  Emulated amd64 on Apple Silicon is expected to be slower and was never
  measured. `--no_cc` is passed unconditionally — the corpus-callosum module
  downloads 81 MB it never uses and crashes after segmentation.
- The thalamic-nuclei atlas: sorting label ids into `.volumes.txt` name order is
  provably wrong (verified against three subjects). Fixed by vendoring the
  thalamus section of FreeSurfer's `FreeSurferColorLUT.txt` as
  `resources/atlas/ThalamicNuclei_LUT.txt` (Iglesias 2018,
  DOI 10.1016/j.neuroimage.2018.08.012).
- **Real blocker:** stack start unconditionally bind-mounted a host worktree
  over `/ti-toolbox`, silently replacing the packaged image's `tit`. Fixed by
  `resolveRepoDir(env, isPackaged)` (opt-in only via `TIT_DEV_REPO_DIR`),
  `buildStackEnv` always emitting `TIT_REPO_DIR` even when empty, and
  `composeFile.ts` dropping a volume whose interpolated source is empty.
- FastAPI's `APIRoute` does not infer `HEAD` from `GET`: `HEAD /` and
  `HEAD /tetravox/*` returned 405 until explicit `@router.head(...)` handlers
  were added.
- The e2e fake embed's inline `<script>` violated its own
  `script-src 'self' 'wasm-unsafe-eval'` CSP; externalised to `fake-embed.js`.
- Compose-parser contract: `services.<name>.{image, environment, volumes, ports,
  labels, healthcheck, command, working_dir, init, platform, restart, networks}`
  plus the healthcheck/networks/volumes subkeys. Anything else — `depends_on`,
  `tty`, `env_file`, long-form volumes — is a named startup error. `platform`
  goes on the container-create `?platform=` query string, not in the body.
- Security: the bearer token is plaintext-readable via `docker inspect` and
  `docker exec env`. Acceptable for a single user, flagged for shared
  multi-user hosts; per-attach rotation is unfixed. Path traversal on
  `/api/files/raw` is blocked (403, `O_NOFOLLOW`) — an apparent bypass turned
  out to be curl's own client-side `..` normalisation.
- CI: `build-and-smoke-image` runs natively on `ubuntu-2204:current` (x86_64, no
  QEMU). A from-scratch SimNIBS install is 30–60+ minutes natively and far
  longer emulated, well past what a default `machine` resource class should
  absorb on every push — which is why the job's original `--layered` reference
  matters and why no nightly/release-gated variant exists yet. The
  `desktop-checks` job needs `vm-docker` plus Xvfb, because Electron's Chromium
  needs a real X display even offscreen; `npm run e2e:quiet` stays macOS-only
  and CI runs `npm run e2e` under `xvfb-run`.
- Gate: host pytest 3159 passed / 18 skipped; desktop vitest 46 files / 499
  passed; `npm run e2e` 51 passed / 1 skipped (`viewer-real`, gated on
  `TIT_TETRAVOX_EMBED_DIR`); quiet-check PASS throughout.

---

## 2026-09-03 — Pipelines program (dev mode, jobs, smoke harness)

**Ask:** bring every pipeline to a real working state under `npm run dev` with
no token in hand, and prove accept/start/complete on Dataset 000.

**Shipped:**
- `npm run dev` / `dev:web` / `dev:down` — attach-or-start the dev container,
  Vite HMR, Electron pre-connected, bearer token injected by the proxy and never
  surfaced to the developer (`desktop/scripts/dev.ts`, `devProxy.ts`).
- A two-level smoke harness over one shared payload. Level A is
  `tests/smoke/` (pytest, `smoke` marker, gated on `TIT_SMOKE_SERVER_URL` /
  `TIT_SMOKE_TOKEN`, deselected by default) driving HTTP; Level B is
  `desktop/tests/e2e/real/*.spec.ts` (Playwright `real` project) driving the UI
  and recording payloads into `tests/smoke/payloads/`.
- `dev/smoke.sh` — discovers dev containers by label and runs Level A;
  `--list`, `--keep`, `--full`, per-kind selection.
- Both known-broken job kinds fixed: flex accepts list-form (ROI-union)
  `atlas_path`, and the trailing `report` job of a `pre` group runs
  `tit.pre.report` instead of failing with `unknown job kind`.
- Workflow-2 fix lanes: optimizer ex/mEx electrode buckets, page-owned subject
  sets, `/api/project.host_path`, `/api/openapi.json`, PETSc cancel-noise
  silencing, report-job locks, missing artifacts for stats/blender/tools/
  analyzer-group, catalog scanning any `output_dir`, a data-driven nilearn
  cutoff, four mne-compat faults in the EEG forward, sourcedata-only subject
  onboarding.

**Decisions that survived:** the dev-mode contract (`npm run dev` is the whole
system, no token in hand, live-mounted repo with `--reload`), cited live from
`desktop/.env.dev.example`, `docs/dev/DESIGN.md` §138, `dev.ts` and `devProxy.ts`;
the harness contract (the accepted/started/completed vocabulary, namespaced and
cleaned outputs, one heavy job at a time, a results table of numbers rather than
impressions), cited from `tests/smoke/__init__.py`, `tests/smoke/matrix.py`,
`tests/smoke/README.md` and `pytest.ini`; and the one-FEM-at-a-time rule, cited
from `desktop/tests/e2e/batch.spec.ts` and `real/pipeline.spec.ts`.

**Reversed / superseded:** `VITE_INCLUDE_GALLERY=1` no longer gates scene test
hooks — it was split into its own `VITE_SCENE_HOOKS=1` flag on 2026-09-04 after
costing three lanes time.

**Lessons and gotchas:**
- Bare matrix run: **21/21 passed in 280.7 s** with zero paths left on disk; an
  independent second run six minutes later also went 21/21.
- Per kind: `blender` did 12.1 s of work after a 32.5 s bpy-import start (the
  slowest start); `ex` at 44.2 s and `mex` at 40.2 s were the slowest completed
  jobs; cancel latency was **0.0 s** for every long kind against a 15 s budget;
  the runner banner was reached in 2.0–7.1 s except for blender; the `accepted`
  leg was under 10 s on every row.
- A full (not cancelled) `sim` completion took 16 min under emulation.
- 9 of the 21 rows replayed the UI's own recorded payload, proving the UI and
  the runner agree on the request body.
- `--project=real`, never `--project real` — Playwright 1.62.1's variadic
  `--project` swallows the spec path otherwise.
- Never use `npm run e2e` for a real-server run: `pree2e` force-rebuilds `out/`
  and races other lanes' builds.
- Scene specs need `VITE_SCENE_HOOKS=1 npx electron-vite build`, and then a
  plain `npm run build` again before leaving `out/` for anyone else — a plain
  build strips `window.__scene` / `__scenePane`, because `import.meta.env.DEV`
  is false regardless of `--mode`.
- Restart rule: check that `GET /api/jobs` is empty before `docker restart`. A
  plain restart keeps the token and is healthy again in 2–5 s; only a *recreate*
  mints a new one.
- Never run two FEM-class jobs at once — the harness enforces it itself with a
  `GET /api/jobs` block before any `completed` or `heavy` row.
- nilearn's default `min_cutoff` of 0.3 V/m is above real TI data (ernie
  L_Insula peaks at 0.138 V/m) — still an open UI default.
- Known non-blocking gaps at the end of the program: `.blend` / `.glb` / `.stl`
  are reported as artifact kind `txt`; `GET
  /api/catalog/analyses/{name}/summary` cannot address a name containing `/`;
  there is no Level A row for stats correlation mode; the `source` row is
  once-per-project.

---

## 2026-09-03 — UI program (shell, run pages, results, system pages)

**Ask:** the app was replicating PyQt too closely. Stop capping width, add a
real run panel, and prove every layout claim with a measured DOM metric rather
than a screenshot — "judge numbers, not pictures".

**Shipped:**
- A flat, workflow-ordered nav rail: no subject-id group header, no separate
  Optimizer Flex/Ex entries (one merged Optimizer page with a Method segment),
  icons below 1440 px and labels at ≥1440 px (`NavRail.tsx`'s
  `LABEL_RAIL_QUERY`).
- A right-hand `RunPanel` on every run page — `PlanGrid` (stat tiles over a
  subject × stage chip matrix of `new` / `skip` / `overwrite` / `blocked` /
  `wait`) above a `JobTerminal`. `PageLayout`'s 880 px `max-width` cap was
  removed entirely.
- Results rebuilt subject-centric: subject list → outputs tree
  (`outputsTreeFor`) → preview pane, replacing the v2 tab strip and dropdown.
- Subjects became the data/readiness home (presence matrix, coverage strip,
  four-stage readiness board). Viewer lost its Layers/Cursor/Scene inspector,
  becoming a source bar over a full-width iframe.
- The status bar became a per-page registry (`useStatusCells`), ending the
  placeholder `RAS — Space — Renderer —` on pages with no canvas.
- A DOM metrics instrument (`tests/e2e/_metrics.ts`: `deadSpaceRatio`,
  `paneWidths`, `firstScreenControls`) replaced a pixel-occupancy proxy; every
  lane ran at least two build → screenshot → measure → fix rounds with numbers.

**Decisions that survived:** the responsive rail rule (icons under 1440 px,
labels at or above, no special case for the Viewer); the dead-space target,
renegotiated from ≤25% to ≤45% for run pages specifically (unreachable for any
label-left form) — `docs/dev/DESIGN.md` §12.3 is now the acceptance table of
record; the RunPanel's lower half being tabbed Plan / Terminal-Scene rather than
Terminal alone (`docs/dev/DESIGN.md` §4.5, §4.6, `RunPaneTabs.tsx`); and the
contract signatures for `PlanModel`, `RunPanel`, `PlanGrid`, `JobTerminal`,
`useStatusCells`, `PageLayout` v3, the outputs tree and the metrics helpers —
`docs/dev/DESIGN.md` §5 defers to `v3-ui-program/u0-design-notes.md` §3 as the
verbatim source rather than restating them, which is why that one file is kept.

**Reversed / superseded:** presence chips and "+ Add subjects" were removed from
the context bar and moved into the subject switcher; the `optimizer-flex` and
`optimizer-ex` pages were deleted into one `optimizer` page; and the original
per-page dead-space ceilings in `wireframes.md` §9 were superseded by DESIGN.md
§12.3's renegotiated numbers.

**Lessons and gotchas:**
- The DOM `deadSpaceRatio` (a topmost-element-is-content test) is *stricter*,
  not more lenient, than the pixel-occupancy proxy it replaced: the proxy called
  preprocess 74% dead, the DOM metric 75–83% even after every removable element
  was removed. Limits set from the proxy were unreachable and had to be
  renegotiated.
- The shared `out/` build directory races: screenshots taken without an
  immediately preceding rebuild pick up another lane's in-flight build.
- `.page-layout-panel { align-self: flex-start; max-height: 100% }` sized the
  run/preview pane to its content, collapsing report `<iframe>`s to their 150 px
  intrinsic height. Fixed per pane shape (`stretch` for run and browse panes).
- `direction: rtl` for left-truncating a mono path bidi-reorders the leading `/`
  to the end, producing a fake trailing slash. Use `truncatePathLeft()`.
- Light-theme-only WCAG AA contrast failures, found by hand-computing from
  `ui/tokens.css` because `tokenContrast.test.ts` only covered filled-button
  pairs and not soft-chip pairs: `--field` on `--field-soft` = 3.11:1 and
  `--warning` on `--warning-soft` = 4.42:1, both real in shipping
  Results/Analyzer/Subjects chips.
- An unrelated `npm run dev` in another terminal intermittently trips the
  offscreen quiet-check's "window reached the screen" detector — diagnose with
  `ps`/`tty` before suspecting the lane's own tests.
- Exact selectors: `data-testid="page-work"` and `"page-right-pane"` (absent
  from the DOM, not merely hidden, when there is no pane); `data-status-cell`
  for status-bar cell ids; `[data-pane-kind="run"|"preview"]` for the CSS
  geometry rules.
- Real bugs the process surfaced: the Viewer's `no-embed` handshake guard
  checked `status === "idle"` and so never re-fired once a scene started loading
  (rekeyed on `embedReady`); `DataTable` body cells had no background, making
  populated tables read as ~40% dead space to the metric.

---

## 2026-09-04 — Scene service, subject-selection grammar, layout pass

**Ask:** "a slim scene management" loading exactly what Simulator, Optimizer and
Analyzer need, one consistent subject-selection UI across tabs, and sensible
UI/UX positioning.

**Shipped:** a slim `tit/scene/` service
(`GET /api/scene/{manifest,surface,electrodes,regions,volume-legend}`); the
`TVSC1` binary wire format (32-byte header, float32 positions, uint32 indices,
optional uint16 labels, budgeted at ≤3 MB and ≤150 k triangles per surface); a
~700-line WebGL2 renderer under `desktop/src/renderer/scene/`; a shared
`<ScenePane mode="montage"|"target"|"inspect">`; one `SubjectsField` component
replacing four divergent subject pickers; and a shared run-page layout skeleton
(Subjects → tier-1 decisions → collapsible detail → action bar, with the right
pane showing Plan over a tabbed Terminal/Scene).

**Decisions that survived:** the scene service is a **form control, not a
viewer** — cited from `docs/dev/DESIGN.md`, `tit/scene/build.py`,
`tit/server/routes/scene.py` and `tests/test_scene_{tvsc,routes,realdata}.py`.
The `SubjectsField` grammar (one summary line, a disclosure, a table with a
per-row eligibility reason) still governs Pre-processing, Simulator, Optimizer
and Analyzer, and the layout skeleton with its 45% dead-space limit is still
enforced by `desktop/tests/e2e/layout.spec.ts`.

**Reversed / superseded:** nothing within the program. Its renderer was
structurally replaced during the embed-convergence fallout and then restored on
2026-09-06; the scene *service* underneath has been load-bearing throughout.

**Lessons and gotchas:**
- `ernie.msh` is 184 MB — 847,165 nodes, 5,899,838 elements, 1.7 s to read
  in-container. It is never sent to the browser.
- Skin (tag 1005) is 77,032 triangles / 38,952 vertices, 1.33 MiB; grey matter
  (tag 1002) is 335,930 raw triangles simplified into the 150 k budget (145,402
  measured for DK40 gm on ernie).
- A cold atlas build (ernie, HCP_MMP1, 362 regions) takes 173 ms. First paint is
  258 ms fresh and 19 ms warm; orbiting measured 121.2 fps against a floor of 30.
- **Never restart uvicorn `--reload` blind.** An import-time assert in an
  auto-discovered route module took the shared dev container down for ~4 min.
  Rule adopted: a route module does no work at import time, and every save under
  `tit/` is followed by a health check.
- `curl /api/health` returning 200 right after a save does not prove the reload
  landed — the pre-reload process can still answer. Wait 3–5 s and probe
  something that reflects the actual change.
- Pick-culling bug: on real anatomy the culled pick named a surface *behind* the
  visible one at 399 of 400 sampled pixels (median 17.6 mm off, max 154.4 mm),
  because the served `gm` was wound inward everywhere (−1,316,329 mm³). Fixed by
  drawing both faces in the pick pass and orienting every surface outward in
  `tit/scene/build.py`, with a `BUILDER_VERSION` cache salt. Post-fix, the
  picked world point lands within 1.086 mm of an independently solved
  intersection and sphere-centre placement error is 0.093–0.164 mm.
- `focus_bbox` (cropping above the lowest GM vertex) removes 34.2% of neck
  height on ernie and 7.2 mm of jaw on MNI152.
- Never repeat a hand-rolled `<div style="display:grid">` row idiom per page —
  four divergent ones collapsed into `SubjectsField`.
- Gate: host pytest 3519 passed, vitest 909 passed, lint 0 errors, offscreen
  e2e 5 passed; `panel-source` at 44.8% dead space, 0.2 points inside the 45%
  limit — treat that as reached, not as headroom.

---

## 2026-09-04 — Embed convergence and runtime-installable Tetravox

**Ask:** (a) make the run-page 3-D panes drive the Tetravox embed instead of the
bespoke scene renderer, the way the Viewer already did; (b) decouple TI-Toolbox
releases from Tetravox updates via a runtime-installable embed.

**Shipped:** the dynamic-delivery half, in full — `tit/tetravox/{protocol,store,
install}.py`, five `/api/tetravox/*` routes, a Settings "Viewer engine" card,
protocol-range and named-feature gating (`SUPPORTED_EMBED_PROTOCOL {min:1,
max:2}`), traversal-safe install with sha256 verified before unpacking, an
https allowlist with redirect re-validation, and a certifi TLS fallback. The
scene service also gained a `format=gii` (GIfTI) output alongside `TVSC1`, still
live today. The pane-migration half — embed protocol 2 in the Tetravox repo,
switching the three panes onto it, deleting `desktop/src/renderer/scene/**` —
was left unfinished.

**Decisions that survived:** the dynamic-delivery machinery
(`SUPPORTED_PROTOCOL_MIN`/`MAX`, dual install roots, explicit verified install,
same-origin-only serving) in `tit/server/routes/tetravox.py`,
`tit/tetravox/updates.py` and `pages/settings/TetravoxCard.tsx`; and the
`format=gii` scene export, which the current native-pane rendering path uses.

**Reversed / superseded:** the convergence goal itself — panes driving a
Tetravox embed iframe — was retired on 2026-09-06. The panes reverted to native
WebGL2 rendering (the scene renderer above, restored from a `~/.treehouse`
copy) and the Viewer became "Open in Tetravox app" against `*.tetravox.json`
files rather than an embedded iframe. `desktop/src/renderer/viewer/protocol.ts`
was left pinned at `tvx === 1` and never widened, because the embed path was
abandoned first.

**Lessons and gotchas:**
- The baked embed floor is `/opt/tetravox/embed`, version 0.3.4, protocol 1,
  sha `c56c3c84…`. Release layout is
  `tetravox-embed-<ver>/{manifest.json,dist/index.html,dist/assets/…}`, and only
  `dist/` plus `manifest.json` are served.
- Per-request resolution costs 21.6 µs with nothing installed and 95.1 µs with
  three installs plus a pin (2000 iterations) — no cache is needed.
- **`TarFile.extractall()` is not safe even with default filters.** On the
  container's Python 3.11.14 it wrote `../escape.txt` outside the destination
  (host Python 3.14 refused it). Traversal-safe extraction is hand-rolled.
- A certifi fallback is required in-container: `simnibs_python`'s OpenSSL
  default verify paths point at absent conda build-time paths, so TLS fails with
  `CERTIFICATE_VERIFY_FAILED` until certifi's `cacert.pem` is loaded explicitly.
- A live install loop takes 0.14 s wall for a 5.6 MB bundle; the 848,311-byte
  wasm chunk is served with `content-type: application/wasm`, and rolling back
  to the baked embed reproduces a byte-identical ETag.
- `pkill -f 'http.server 8919'` kills its own invoking shell when it is run in
  the same `sh -lc` string as its own cleanup; use a self-excluding regex like
  `http[.]server 8919`.
- Consolidation recovery in the same window (2026-09-04/05): an interrupted
  Codex session was recovered and verified byte-identical by SHA-256 against a
  parallel `.treehouse` checkout, excluding generated `artifacts`,
  `test-results` and `.cache`. A fresh sandboxed `pnpm test` then showed 34
  failures, all `listen EPERM` from a unix-socket fixture the sandbox blocks —
  sandbox-only failures are environment artifacts and must be recognised as such
  before anyone re-derives them as bugs.

---

## 2026-09-05 — Overview, batch execution, guide panes, explicit Load

**Ask (verbatim asks, one line each):** open on Overview and delete Subject
Info; make the terminal scrollable and clearable; give every page a uniform
subject-batch grammar with parallel/sequential control; stop run-page panes
rendering the selected subject and show a general (Ernie) individual instead;
give the Viewer's top bar more selectors and stop auto-loading on subject pick.

**Shipped:**
- `GET /api/catalog/overview` (`tit/server/routes/overview.py`, new schemas in
  `tit/server/schemas.py`); the Subjects page became Overview and Subject Info
  was deleted (`_VALID_PANELS` in `routes/settings.py` still accepts
  `"subject-info"` so old saved `settings.json` files load).
- A shared `ui/Jobs.tsx::JobConsole`; Clear is a per-source `clearedThrough`
  sequence watermark, with no mutation or truncation, over one pure
  event → line module (`app/jobs/logLines.ts`).
- `SubjectsInParallel.tsx` plus `jobGroups.ts`; `/api/jobs/groups` widened to
  `[pre, sim, flex, flex_adaptive, flex_pareto, ex, mex]` (an additive contract
  change); `tit/jobs/plans.py::plan_per_subject`; one `POST /api/jobs/groups`
  request per batch with a server-forced `subject_id` per entry; the cap is
  enforced by `tit.jobs.scheduler` (`group_cap`), not by client request timing.
- A fixed Ernie "guide" scene: `tit/scene/guide_build.py` generates packaged
  surfaces, atlases and nets from Dataset 000's `sub-ernie`; five immutable
  `GET /api/guide/*` endpoints with no subject parameter, inside the `TVSC1`
  budget. Run-page panes draw the guide, and subject-RAS sphere click-to-config
  is disabled on it.
- The Viewer split into `draft` and `loaded` selection: Load is the only thing
  that fires `GET /api/view/{kind}` and posts to the iframe, a failed Load keeps
  the prior scene, and an optional `atlas` query parameter was added to
  `GET /api/view/{kind}` and `tit.viewspec.build_view` (absent means unchanged
  behaviour, and an unknown id falls back rather than 404-ing).

**Decisions that survived** (each recorded in `docs/dev/DECISIONS.md`, with
`docs/dev/ARCHITECTURE.md` §3/§5/§6 and `docs/dev/DESIGN.md` §§4.6, 9, 10, 13 and
`docs/dev/ROADMAP.md` rows R1–R5 alongside): Overview is the landing page and
Subject Info is deleted; terminal Clear is presentational, not destructive;
batch execution is a scheduler cap rather than renderer request timing, and the
cap counts **jobs, not distinct subjects** (a Simulator subject with three
montages is three jobs); the workflow 3-D panes draw a fixed guide, not the
selected subject; the Viewer loads on command, not on selection.

**Reversed / superseded:** nothing within the program. The 2026-09-06 program
below reverses parts of it — the panes become the app's own WebGL2 renderer
rather than the embed, the Viewer becomes an external-Tetravox launcher, and
Simulator/Analyzer move to a jobs-table model.

**Lessons and gotchas:**
- Cortical `.annot` atlases (FreeSurfer surface parcellations) cannot be offered
  in the Viewer's volume-based ViewSpec. A real gap, still open.
- Overview cold latency is 3.4 s on Dataset 000 (5 subjects, 25 optimisation
  runs) against 0.12–0.14 s warm; the cost is manifest parsing in `tit.catalog`,
  not request count.
- The `source` pipeline kind is deliberately excluded from `GROUP_KINDS` and the
  batch cap — it is a single job over the whole selection with its own `cpus` /
  `workers`.
- Guide asset generation from sub-ernie takes 6.9 s and packages **15.48 MB**
  against 184 MB of raw mesh (skin 77,032 tris / 1.39 MB; gm 145,402 tris /
  2.59 MB; three atlases; eight EEG nets). Its licence is GPL-3.0 via the
  SimNIBS example-dataset repo — *not* the CC BY-NC 4.0 that applies only to
  "Ernie Extended" and the non-human-primate models.
- One flake was chased rather than smoothed: `analyzer.spec.ts`'s dead-space
  bound (≤0.65) read 0.61 once and reproduced clean twice after. Recorded as a
  marginal layout measurement, not a state leak; threshold left alone.
- Gate: typecheck and lint clean; desktop unit 79 files / 892 tests; full
  offscreen e2e 172 passed / 3 skipped / 0 failed; `pnpm run build` ok; host
  pytest 3655 passed / 47 skipped; route-import guard clean over 20 modules;
  real-container checks against Dataset 000 all 200.

---

## 2026-09-05/06 — Tetravox auto-update, electrode dots, selection grammar, pipeline canvas

**Ask:** ship the new Tetravox visualisation fixes; auto-update the embedded
viewer without a TI-Toolbox release; draw EEG electrodes as colour-only dots
with no rings and tested select/deselect; one selection grammar for every
window, modelled on 2.5.0 (job cards plus one pick list); and a canvas-style
pipeline builder that runs as one job group and exports to Jupyter notebooks.

**Shipped:**
- **Tetravox update channel** — `tit/tetravox/updates.py`. The source of truth
  is the GitHub Releases API of `idossha/tetravox`: non-draft, non-prerelease,
  newest first, looking for the asset pair `tetravox-embed-<ver>.tgz` +
  `.tgz.sha256` and a `tetravox-embed-<ver>.manifest.json` (read for `protocol`
  without downloading the tarball). `TIT_TETRAVOX_RELEASE_INDEX` overrides the
  index for air-gapped mirrors. `tetravox.auto_update` (default on) checks at
  startup non-blocking and every 24 h, installs and activates automatically, and
  emits `tetravox.updated` for a single desktop toast. The pin is a **protocol
  range, never a version**; the last two installs are kept for rollback; and
  `container/blueprint/build.sh` resolves the newest compatible release when
  `--tetravox-tgz` is omitted.
- **Electrode dots** — `shape: "dot"`, `dotRadiusPx: 5` (7 when active or
  hovered), no layer-level `selected` colour (`stateColors` carries only `idle`
  and `disabled`). Every point gets an explicit `color`, because a per-point
  colour always beats `stateColors` and one layer cannot be both idle-grey and
  disabled-grey. `setPointTool` / `setPointSelection` are never sent, so no ring
  can appear — asserted by tests rather than assumed. Names show only on
  selected or hovered points. `SCENE_PALETTE.channels` moved to the **Okabe-Ito**
  colour-blind-safe six-hue set; the old blue/orange/green/pink collided under
  deuteranopia at four-pair mTI.
- **One selection grammar** — the `ui/SelectionList` primitive: click selects
  one, ⇧-click ranges, ⌘/Ctrl-click toggles, ⌘A all, Esc none, a visible
  checkbox column as the toggle's visible state (a row is never click-only), an
  always-on filter, `All · None` as the only bulk buttons, an `N of M selected`
  badge, and virtualisation past 150 rows. It replaced five prior idioms. A new
  `PageLayout` `receipt` slot (a sibling of the action bar, not inside the
  scroller — which fixes a sticky-overlap bug caught by a hit test) renders
  `Receipt.tsx` ("This will run N jobs: …", first 15 rows plus "and K more")
  from the same `planModelFrom` rows as the grid, so grid, digest and receipt
  cannot disagree; one shared existing-outputs Skip/Replace/Cancel dialog serves
  all four run pages.
- **Pipeline canvas** — React Flow (`@xyflow/react`, a new dependency) on a
  `pipeline` page. A pipeline is a DAG whose nodes are existing job kinds
  (`pre`, `sim`, `flex`, `ex`, `mex`, `analyzer`, `source`, `stats`); a run is
  **one job group** via `POST /api/jobs/groups` with `after` edges;
  `tit/pipeline/` validates and resolves bindings server-side
  (`POST /api/pipelines/validate|run`, `contracts/pipeline.schema.json` v1).
  Dynamic-binding write-back lives in `tit/jobs/bindings.py`, where the path is
  a pure function of `(pipeline, node, port)` so the *consumer* carries it — the
  resolve step runs before the consumer's job id exists — and
  `JobManager._runner_config_path` merges it in. Notebook export
  (`tit/pipeline/notebook.py`) writes `nbformat` v4 with one markdown plus code
  cell per node against the public `tit` scripting API, round-tripping the
  pipeline JSON in `metadata.ti_toolbox.pipeline`; importing from a notebook is
  a non-goal.

**Decisions that survived:** `docs/dev/ARCHITECTURE.md` §7 (7.1 update channel, 7.2
points-layer/electrode contract, 7.3 pipelines, 7.4 selection grammar, receipt
and derived ⌘-number), eight `docs/dev/DECISIONS.md` entries, six `docs/dev/ROADMAP.md`
rows plus its new ten-item "Known follow-ups" table, ADR row 26, and
`docs/dev/DESIGN.md` §§4.8, 4.9, 9.1, 9.2.

**Reversed / superseded:**
- The earlier draft plan (decisions T1/U1/U2/E1/E2/S1/S2, lanes T/U/E/S) was
  superseded within a day by the A–D plan (lanes TX/AU/EL/SG/PC/CX2) that was
  actually implemented and gated. Only the latter is cited by code and tests.
- The explicit per-point idle colour is a deliberate workaround kept pending
  Tetravox PR #35, which fixes `resolvePoint` upstream so idle points fall
  through to `stateColors.idle`; `pointsFromMarkers` carries a `TODO(tetravox)`
  naming the removal condition (a bundle built from 0.3.12 or later).

**Lessons and gotchas:**
- Auto-update channel rules, exactly: the GitHub Releases API, non-draft,
  non-prerelease, newest first; a release needs all three of
  `tetravox-embed-<ver>.tgz`, `.tgz.sha256` and `.manifest.json`; the protocol
  is read from the ~2 KB manifest asset alone, never by fetching the tarball; a
  release whose protocol exceeds `SUPPORTED_PROTOCOL_MAX` is reported as
  "needs a TI-Toolbox update" and never installed. At the time of the gate,
  v0.3.11 was `main` and carried **no embed asset at all**, so there was nothing
  to install — blocked on Tetravox PR #35 being merged and `v0.3.12` tagged.
- Electrode dot geometry, measured against the real 0.4.0 embed: idle RGB
  `148,155,167`, pair 1 `0,106,166`, pair 2 `215,149,0`; the radial pixel
  profile `[1,8,12,16,32,25,31,22,21,21,10,7,3,0,0,…]` is byte-identical before
  and after a toggle — one solid disc, no ring. `dotRadiusPx` is currently inert
  in 3-D (5 → 209 px and 15 → 209 px), a pinned known defect awaiting the 0.3.12
  dot pass; `real/embed-electrodes.spec.ts` is deliberately written to start
  failing once 0.3.12 lands, as the signal to invert it.
- Selection grammar rules worth keeping: the checkbox column is the toggle's
  visible state; `All` and `None` are the only bulk buttons; filter and
  selection interact through explicit `bulkExclude` rules; the receipt is a
  `PageLayout` sibling slot and never inside the scrollable body; the receipt
  list is capped and scrolled at ~3 rows, because an uncapped one cost the
  Analyzer page its dead-space budget. Pre-processing measured 41.8% → 41.9%
  after the receipt was added — a self-funding change.
- Hard rules: **never `git stash` in this worktree** (it cost the shared
  container mid-FEM); **never two Playwright runs at once**. During the real
  gate something outside the session restarted the container mid-FEM, orphaning
  a running `sim` to `lost` and skipping its dependent analyzer — job
  re-adoption across `--reload` is not implemented, and this is the single most
  user-visible open gap. `e2e-quiet-check` can false-FAIL on a machine that is
  actively in use (other Electron apps running); observed independently by three
  lanes and reported unresolved rather than dismissed.
- `tit/jobs/bindings.py` is a module separate from `tit/pipeline/` on purpose:
  `tit.jobs` (the runner) must never import a pipeline module to run an ordinary
  job. The key is defined once in `tit.jobs` and `tit.pipeline.plan` re-exports
  it.
- Gate: rail-derived ⌘ shortcuts (⌘1 Overview … ⌘6 Pipeline … ⌘9 Jobs, ⌘0
  Settings) fixed two hard-coded specs; desktop 84 files / 949 tests;
  mock-server contract 33/33; full offscreen e2e 195 passed / 3 skipped /
  0 failed; host pytest 3741 passed (+7 from `test_pipeline_bindings.py`);
  `contracts_check.py` showed only 7 pre-existing unrelated problems;
  real-container `/api/pipelines*` and `/api/tetravox/updates` all 200; and the
  real embed-electrode pixel tests reproduced the exact colour numbers above.

---

## 2026-09-06 — Native panes, external viewer

**Ask:** stop embedding Tetravox in the run-page panes and in the Viewer tab.
Give Simulator/Optimizer/Analyzer back their own interactive WebGL2 renderer
with a clickable atlas and electrode dots, and make the Viewer a data selector
that opens the scene in the standalone Tetravox desktop app.

**Shipped:**
- The 2026-09-04 native WebGL2 renderer restored (`desktop/src/renderer/scene/`,
  5,048 lines) and made the only renderer under `pages/`.
- Guide packaging regained TVSC1 per-vertex atlas labels
  (`tit/scene/guide_build.py`), so a pane can highlight DK40 / HCP-MMP1 /
  a2009s regions; `<ScenePane>` and `<RoiPicker>` share one region-selection
  model.
- Electrodes as colour-only screen-space dots (the Okabe-Ito six-hue channel
  set, idle grey, no ring); stacked translucent skin and GM surfaces resolved by
  a two-sheet depth-peel ported from Tetravox 0.3.10.
- The Viewer page rewritten as a data selector (a "what will open" list,
  `+ Add…`, reorder, Reset). `Open in Tetravox` posts `POST /api/view/open`,
  writes `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`, and Electron
  main spawns or reuses the host-installed Tetravox app.
- Every piece of embed-delivery machinery deleted for good: `tit/tetravox/`,
  the `/tetravox/` static route and its CSP, `/ws/tetravox`, the Settings embed
  card, the Dockerfile and `build.sh` embed bake, and
  `desktop/src/renderer/viewer/`.
- Simulator, Analyzer and Optimizer gained per-row jobs tables (one row is one
  job with its own subject/source/montage), replacing the page-level
  subject-set × montage cross-product.
- A Notebooks page (SUNA-derived, in-container kernel) shipped alongside.

**Decisions that survived** — all recorded, so this is only a pointer: the
external-viewer contract and host-installed (never bundled) Tetravox
(`docs/dev/DECISIONS.md` 2026-09-06, `docs/dev/ARCHITECTURE.md` §7.1); the native
run-page renderer, TVSC1 labels and one region-selection model
(`docs/dev/ARCHITECTURE.md` §7.2, `docs/dev/DESIGN.md` §9/§10); the jobs table as the
run-page grammar (`docs/dev/ARCHITECTURE.md` §7.5, `docs/dev/DESIGN.md` §4.10); rail
digits counting from ⌘0, superseding the 2026-09-05 Settings-digit entry; grey
matter always opaque, the camera owned by the user, and free-hand placement in
the Simulator (`docs/dev/DECISIONS.md`, commit `d068782e`); ADR rows 27/28, which
supersede rows 15 and 23 and the Tetravox/electrode halves of row 26.

**Reversed / superseded:**
- Lane VE's evening reinstatement of the in-image Tetravox embed (the bake,
  `/tetravox/`, `/ws/tetravox`, the rail sub-items) was itself reversed later in
  the same program. The embed is retired for good.
- Lane TI's managed-download / auto-install Tetravox flow (`tetravoxInstall.ts`)
  lost to the simpler host-installed-app plus download-link design.
- The embed-convergence plan's E6 and the Viewer-in-iframe half of ADR rows
  15/23 are superseded.

**Lessons and gotchas:**
- `Fiducials.csv` was listed as an EEG net — it holds only registration
  landmarks and never resolves an electrode. A real e2e spec caught it; no unit
  test did.
- **Never run two Playwright invocations against one worktree at once.** They
  share the mock `webServer` on 8790, and one lane's `pnpm run pree2e` rebuilds
  `out/` underneath a suite already executing. Enforce it with a lock file
  (`/tmp/tit-e2e.lock`), not with convention.
- `VITE_SCENE_HOOKS=1` must be built (`pnpm run pree2e`) immediately before real
  scene specs, or `window.__scene` is absent and the spec times out 30 s later
  with no hint why.
- **Never `git add -A` in a shared worktree.** It swept another lane's
  uncommitted files into the wrong commit three times in one day — the content
  was right, the attribution was not. Use disjoint explicit paths.
- `desktop/package-lock.json` was stale: `npm ci` failed on
  `@xyflow/react@12.11.6` and `zustand@4.5.7`, which existed only in
  `pnpm-lock.yaml`. Separately, the isolated `fastsurfer` Docker stage could not
  download checkpoints, because `download_checkpoints.py` imports `torch` at
  module level while that stage installs only `requests`; the download moved to
  the final stage. Both are written up in `container/blueprint/README.md`.
- The CI known runtime problem declared at `.circleci/config.yml:29`: deleting
  `Dockerfile.ti-toolbox.layered` removed the only thing that made the image job
  tractable. The job now builds SimNIBS from scratch — 30–60+ minutes on a
  2-vCPU / 8 GB `machine` executor against a 15 m `no_output_timeout`. Declared,
  not fixed.
- The Mac ran out of disk mid-gate (359 MiB free of 926 GB), killing the full
  offscreen e2e twice with `ENOSPC` while a second lane ran Playwright
  concurrently. About 100 GB was reclaimable in Docker images, build cache and
  volumes; pruning was left to the maintainer rather than taken unilaterally.
- A real `sim → analyzer` run hit the Docker bind-mount phantom write: SimNIBS
  logged writing `Simulations/.../TI/mesh/*.msh`, but the directory held only
  `fsaverage/` afterwards, on host and in container alike. Already known against
  the mTI optimization program; not this program's bug.
- The 2026-09-04 native renderer was recovered from a
  `~/.treehouse/ti-v3-firstmate/uiux/desktop/src/renderer/scene/` copy, **not**
  from git history. That copy was its only surviving source.
- A viewer test that checks only that the plumbing ran — no requests, no error —
  can still be showing nothing on screen. It happened twice in one day: a
  1224×0 pane, and a scene never posted because `pendingScene` was nulled by a
  StrictMode double-invoke in dev only. Assert visibility, not success.
- Open, unfixed: an idle electrode's worst measured contrast against the
  now-opaque scalp is 2/255. Left as a design call for the maintainer.
- **`.tetravox.json` is a compound extension and load-bearing.** Tetravox's
  `isScenePath` is `/\.tetravox\.json$/i`; any other suffix (the plan's working
  name `.tvx.json`) is classified as *data* and silently read as a volume, with
  no error on either side.
- **A Tetravox left running with no window swallows the scene and `open` still
  exits 0.** Measured: against a windowless instance, `open -a Tetravox <scene>`
  and `open -n -a …` both exit 0 with 0 windows; upstream's `open-file` handler
  parks the path in `startupScene` and nothing drains it. The fix is a second,
  document-less `open -a` as an activation kick. Tetravox also has **no
  `--version` flag** — assert an install by bundle structure and `codesign`,
  never by launching it.
- **`dev/build_contract.py` was non-deterministic**: it iterated a `set[str]`,
  whose order follows the per-process `PYTHONHASHSEED`, so two runs on identical
  inputs differed by 220 then 265 lines. Two lanes concluded the JSON was
  "stale" and hand-spliced schema edits because of it. Fixed with `sorted(...)`;
  the generator is safe to run again.
- **`--reload` persists settings to a 0600 JSON file that every reloaded worker
  re-reads**, so removing a `ServerSettings` field mid-session made `cls(**data)`
  raise on every reload and took the shared dev container's HTTP server down for
  a whole lane's window. `from_json` now drops undeclared keys. Corollary: **a
  200 from `/api/health` is not evidence the new code loaded** — it can come
  from the pre-reload process.
- **A browser silently drops a declaration whose `var()` is undefined** — no
  console warning, no build error, no failing test. `pipeline.css` had 36
  references to a token vocabulary this app never had; the page was not
  "broken", it was unstyled. Eight more undefined refs remain in
  `jobs-rail.css`, `scene-pane.css`, `optimizer.css`, `viewer-page.css`.
- `window.prompt` is not implemented in Electron (it silently resolves
  `undefined`), and `<a download>` on a `blob:` URL is inert without a
  `will-download` handler. Both look like success and write nothing.
- **`emit_artifact` verifies nothing.** A `sim` job reported `succeeded` with an
  artifact path that was not on disk, and its dependent analyzer failed five
  seconds later with `FileNotFoundError` naming its producer's own declared
  output. One `Path(path).exists()` at emit time would turn a confusing
  downstream failure into an honest upstream one.
- `antialias: true` forbids an exact depth-equality sheet test (the colour pass
  is multisampled while the depth pre-pass is not, so an edge fragment's
  `gl_FragCoord.z` disagrees and fragments are dropped at every facet edge). Use
  an inequality with `SHEET_EPS = 1e-5`. For a selection outline use `fwidth`
  and read the varying as a signed field whose 0.5 contour is the boundary:
  treating `0 < v < 1` as "the rim" paints every triangle straddling it, a band
  of shards several triangles thick on a decimated cortex.
- A `Select` popover (z-index 60) is **unclickable inside a `Dialog`** (80/90) —
  a known `ui/components.css` gap, and the reason the montage and free-hand
  editors are inline cards rather than dialogs.
- `GET /api/view/presets` would have been shadowed by `GET /api/view/{kind}`,
  returning 404 — indistinguishable from "no presets". The real path is
  `/api/viewer/presets`. Related: `/tetravox/` answering 200 is **correct**, not
  a leak — once it left `RESERVED_PREFIXES` the path falls through to the SPA
  catch-all — and `host_path: null` is an honest answer from a server running on
  the host, not a defect.
- Still-open traps: `/api/scene/*` is live and called by nothing; the guide
  packages ~11.3 MB of GIfTI copies nothing reads (`SURFACE_FORMATS` /
  `LABEL_FORMATS` could drop to `("tvsc",)`); job re-adoption does not survive a
  `--reload` (the pid is held in memory, though `status.json` already persists
  it); and `FlexConfig.output_folder` is the run name while ex/mEx use
  `run_name` — two names for one user-facing idea.

## 2026-09-07 — External audit response

**The ask.** An external audit of the shared scientific core and of the v3 server, delivered as a
findings list. Every finding was to be **reproduced in this repository first** and then fixed at its
cause, or, where it was a modelling question rather than a defect, written up and left to the
maintainer. Four lanes ran it — science, backend, frontend, release — and this section is their
joint record. CX6 consolidated them.

### What shipped

**Science (`682cbfcf`, `35a833ec`, `5b3bc6cb`, `4abf5181`, `e6a6eb15`).** Six numerical defects in
`tit/stats/**` and `tit/analyzer/**`, SCI-01 to SCI-06. The user-facing record — what was wrong,
which versions, which outputs move and by how much, how to spot an affected result, and whether to
re-run or rescale — is [`SCIENTIFIC-CORRECTIONS.md`](SCIENTIFIC-CORRECTIONS.md); the reasoning is in
`DECISIONS.md § 2026-09-07 (CX6)`; the numbers are in `BENCHMARKS.md`. Two lower-priority items were
cheap enough to take here (`channels` must partition `fields`; `hf_peak_is_exact` exposes the
>8-carrier lower bound) and two were deliberately left (`_envelope_from_PQ` cancellation, which
belongs with the SCI-07 decision; preallocation outside the group-stacking loop, which is small).

**SCI-07 is open on purpose.** Whether `channels` should govern `hf_peak`/`hf_sar` the way it
governs the envelope is a modelling call, not a bug. The recommendation, written out with both
models and their numbers, is **Model B**: sum same-carrier fields before any exposure metric, gated
on the montage actually declaring `channels`, leaving the `channels=None` path bit-identical.

**Backend (`ada4f3d7`, `0b58b89a`, `2d35120b`, `aef163c7`, `2414fbeb`, `cefd8310`).** RUN-01 to
RUN-06. Two of them were the same shape — a check and an acquisition in two critical sections with
a multi-second gap between them — and got the same answer, reserve under the lock: the kernel cap,
and the scheduler's exclusive write locks. The rest: a kernel's idle clock now starts at
*completion* rather than submission (the reaper was killing cells that ran longer than the timeout);
an `after` naming an unknown job is no longer treated as satisfied; one subject-id grammar
(`SUBJECT_ID_RE`) is enforced wherever an id becomes a path rather than only at the API; and a
`tools` job's arguments are jailed to the project root before the argv is built.

**Frontend (`aefcbbc3`, `04cc09bd`, `48cfbe0d`, `6e0bfe2a`, `3c7574a7`, `1da333b1`).** A notebook
save carries the revision it wrote (a save in flight was joined by the next, so `dirty` cleared
without the text ever being sent); the reconnect job snapshot is authoritative rather than
additive; rich notebook output passes an allowlist sanitiser; the quit plan moved out of the Docker
branch so ⌘Q asks about running jobs on every backend; the Analyzer's batch submit settles all
specs and names both halves instead of rejecting on the first failure; and the contract test parses
YAML in memory instead of rewriting a tracked fixture on every run.

**Release (`6f12c39c`, `f7b2787d`, `2d48dd0b`, `86711e7a`).** The single largest finding was that
pushing a `v3.0.0` tag would have built and published the **legacy 2.x launcher**.
`.github/workflows/release-v3.yml` replaces the two workflows that would have done it, `package/`
is retired (ADR decision 5's Phase 6), `RELEASE.md` is the written procedure that did not exist, and
`desktop/scripts/verify-package.mjs` — run against a scratch `--dir` build — found two
configurations that could not have shipped at all.

### Gate

The full CX6 gate table is in [`BENCHMARKS.md § External audit response`](BENCHMARKS.md) and the
ROADMAP row cites it. Headline: typecheck clean, lint 0 errors, vitest 1,304, host pytest 4,069,
container subset 410, contracts and route-import guards clean, actionlint clean, mock e2e 317.

### Gotchas

- **A test that writes `sys.modules` without `monkeypatch` is a time bomb for every later test in
  the process.** `tests/test_atlas_coverage.py` assigned `sys.modules["nibabel.freesurfer.io"] =
  MagicMock()` in four tests. The assignment was never undone, so `test_scene_guide`'s
  `pytest.importorskip("nibabel.freesurfer.io")` later *succeeded*, handed the test a mock instead
  of the real reader, and failed — but only in that file order, which is why it was carried for two
  gates as "a known order-dependent flake". Reproduced deterministically with a one-function pytest
  plugin that plants the leak, then fixed with `monkeypatch.setitem`/`setattr` (`c799e7e2`).
  `tests/test_catalog_v1.py:829` had already got this right and says why in a comment.
- **A numerical test leg must run against the real libraries.** The host conftest mocks numpy's
  neighbours; `tests/numerical/` is therefore run in the container under `simnibs_python`, where
  `scipy` and `nibabel` are real, and its SCI assertions are compared against independent
  reference implementations rather than against retyped expected values.
- **Lint errors get attributed to whichever file the reporter printed last.** 17 `no-undef` errors
  reported as "pre-existing in `pages/preprocess/index.tsx`, `ui/DataTable.tsx`,
  `ui/VirtualList.tsx`" were all in `scripts/verify-package.mjs`: the flat config gave Node globals
  to `tests/mock-server/**` only, so a new script under `scripts/` linted as browser code. Those
  three renderer files only ever emitted React Compiler warnings (`f1ea7fcf`).
- **A global `.gitignore` rule can hide a required build input indefinitely.** `build/` swallowed
  `desktop/build/`, so the four icon and entitlement files `electron-builder.yml` names by path had
  never been committed — invisible on the maintainer's machine, fatal on a fresh checkout. The old
  `!package/build/` exception had been covering the same hazard for the legacy launcher, and
  retiring `package/` is what surfaced it.
- **`electron-builder`'s `files:` is not "what the repository contains".** `docker/**` was outside
  it while `src/main/stack.ts` reads `docker/docker-compose.v3.yml` from `app.getAppPath()` at every
  stack start. Every packaged build would have failed on first launch.
