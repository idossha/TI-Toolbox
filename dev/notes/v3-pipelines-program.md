# v3 pipelines program — every pipeline runs from the UI, and `npm run dev` is the whole system (plan of record, 2026-09-03)

Maintainer's brief, verbatim: *"bring this branch to a point that all the pipelines are working … test the
behavior of the system on the 000 dataset … do not try to complete full long pipelines like the diffusion
pipeline or the charm pipeline, but come up with a framework to test the behavior: that the input is being
accepted by the process and that the process begins, and if it's a short process, look at the artifact it
creates … clean up the entire development approach such that I can open the UI and look at the system as it
is being developed … if those tokens are not absolutely necessary, remove that … treat it as a `pnpm dev` to
bring up the system and tinker while it's being developed."*

House rules (`/Users/idohaber/00_development/agentic-rules`, `docs/PRINCIPLES.md`; skills `testing-backend`
Procedure B, `testing-frontend-offscreen`, `ci-guards`): every rule states the failure it prevents; an agent
judges numbers, not pictures; real-data tests are env-gated and skip with a reason; GUI/e2e tests run hidden and
never take the screen; docs are the single source; no AI co-author trailers; nothing is committed unless the
maintainer asks.

## 0. Evidence that drives this (the maintainer's own runs today, `code/ti-toolbox/jobs/` in Dataset 000)

| Job | Kind | Outcome | Root cause class |
|---|---|---|---|
| `35ea5755…` | sim, sub-101, montage `asdfasdf` | **succeeded** in 16 min (emulated FEM) | — (proves the runner path end to end) |
| `d0036f3c…` | pre (DICOM→NIfTI), sub-101 | **succeeded** in 12 s, report artifact | — |
| `c45cb53b…` | flex, sub-101 | **failed** `TypeError: expected str … not list` in `_validate_roi_input` | UI emits `atlas_path: string[]` (ROI unions, PR #130); runner validation assumes a scalar |
| `614b6667…`, `d6ccfcce…` | report (trailing job of a `pre` group) | **failed** `unknown job kind: 'report'` | `tit/jobs/plans.py` plans a kind `tit/jobs/kinds.py` cannot run |

Two of the four pipelines the maintainer touched failed for reasons a harness would have caught in seconds:
a UI→config shape mismatch, and a planned kind with no runner. That is the failure class this program exists to
close, for every kind.

## 1. Decisions

| # | Decision | Failure it prevents |
|---|---|---|
| P1 | **`npm run dev` is the whole system.** One command from `desktop/`: ensure the project's container is up (attach-or-start through the same Engine-API stack code the app uses — one implementation, no duplicate), start Vite with HMR, start Electron already connected to that server (no launcher form). `npm run dev:web` does the same without Electron so the browser tab at `http://127.0.0.1:5173/` is enough. Configuration comes from `desktop/.env.dev` (gitignored; `.env.dev.example` committed): `TIT_DEV_PROJECT_DIR` (required), `TIT_DEV_IMAGE_TAG`, `TIT_DEV_PORT`, `TIT_DEV_MOUNT_REPO` (default 1). | Today's loop: hand-run `docker run` with eight flags and labels, read the token out of `docker inspect`, paste `/auth/session?token=` into a browser, relaunch `nohup npm run dev` when it dies. |
| P2 | **No token in the developer's hands.** The token stays in the protocol (the packaged app needs it: attach-or-start reads it from the container's env, and the server is reachable by any local process). In dev it never surfaces: the dev script recovers it from the container (or generates it on start), hands it to Vite and Electron through the environment, and the Vite proxy injects `Authorization: Bearer …` and rewrites `Origin` to the server's own origin on every proxied `/api`, `/auth`, `/ws` request. The browser needs no cookie, no `?token=`, no `TIT_DEV_ORIGINS`; a server restart does not log the tab out. Electron dev auto-connects with the same token. | Manual token plumbing; sessions lost on every container restart; the 403 origin dance. |
| P3 | **Live backend code in dev.** The dev container bind-mounts the worktree at `/ti-toolbox` (`TIT_REPO_DIR`, `PYTHONPATH=/ti-toolbox`) so runner subprocesses always import the working tree, and runs `tit.server` with `--reload` scoped to `tit/` (`TIT_SERVER_RELOAD=1` in the entrypoint → `--reload --reload-dir /ti-toolbox/tit`). The dev script recreates the container when its mounts/env differ from what dev needs, and says so. | Editing Python and testing against the image's baked copy. |
| P4 | **A pipeline smoke harness, three behaviours per kind:** `accepted` (validate → plan → submit all succeed for the config the UI emits), `started` (the job reaches `running` and its log shows the runner's own banner/first stage within a budget), and `completed` (short kinds only: the job succeeds and every artifact it reports exists on disk and appears in the catalog). Long kinds (`sim`, `flex`, `leadfield`, `charm`, `fastsurfer`, `qsiprep`/`qsirecon`, `blender`) assert `started`, then cancel and assert `cancelled` with no surviving process. Every kind declares which behaviour it asserts and why. | "It probably works" for kinds nobody has run through the new server. |
| P5 | **The harness lives at two levels that share one payload.** Level A (`tests/smoke/`, pytest, marker `smoke`, gated by `TIT_SMOKE_SERVER_URL` + `TIT_SMOKE_TOKEN`, skipped with a reason otherwise and excluded from the default run) talks to the server over HTTP. Level B (`desktop/tests/e2e/real/*.spec.ts`, Playwright against `TIT_E2E_SERVER_URL`, always offscreen) drives each run page, records the exact `POST /api/jobs` payload it submitted to `tests/smoke/payloads/<kind>.json`, and asserts the job started (and, for short kinds, that Results lists the output). Level A replays those recorded payloads, so a UI→config divergence is caught at B and a config→runner divergence at A, with the same JSON. | The flex failure: the UI and the runner each "worked" against a different idea of the config. |
| P6 | **Smoke outputs are namespaced and cleaned up.** Every run tags its outputs `smoke-<runid>` (simulation/run names, subject `sub-102` for preprocessing), records every path it creates in a manifest, and deletes exactly those paths at the end (`--keep` to inspect). Never overwrite a pre-existing output; never touch `m2m_101`, `m2m_ernie`, `m2m_MNI152`. | Trashing the maintainer's dataset. |
| P7 | **One heavy job at a time.** The harness runs kinds sequentially by default; the FEM-class kinds never overlap (emulated amd64 on this Mac). | Two emulated FEM solves fighting for the same cores until both time out. |
| P8 | **Numbers, not impressions.** Each harness run writes `dev/notes/v3-pipelines/<date>-smoke.md`: per kind — behaviour asserted, result, wall time, artifact paths, and for failures the first traceback line. Fix lanes cite this table; the final report is this table. | "All pipelines work" as a sentence instead of a table. |
| P9 | **UI work only where a pipeline needs it.** A page change is in scope only when it blocks a pipeline (a field the runner requires that the form cannot produce, a submit that never happens). | Drifting back into the UI program. |

## 2. Dev mode (P1–P3) — the contract D0 implements

```
desktop/.env.dev                 TIT_DEV_PROJECT_DIR=/Users/idohaber/datasets/000  (+ optional TIT_DEV_IMAGE_TAG, TIT_DEV_PORT, TIT_DEV_MOUNT_REPO)
npm run dev                      → scripts/dev.ts:  ensureDevStack() → { origin, token }   (attach, or recreate/start via the app's stack code)
                                                   → electron-vite dev  with TIT_DEV_SERVER_URL, TIT_DEV_SERVER_TOKEN, TIT_DEV_PROJECT_DIR
npm run dev:web                  → same, renderer-only (no Electron); open http://127.0.0.1:5173/
Vite proxy                       injects Authorization: Bearer + Origin=<server origin> for /api, /auth, /ws (also proxyReqWs)
Electron main (unpackaged only)  TIT_DEV_SERVER_URL + TIT_DEV_SERVER_TOKEN present → connect() immediately; launcher never shown
Container (dev)                  image idossha/ti-toolbox:<tag>, labels tit.*, -v <worktree>:/ti-toolbox, PYTHONPATH, TIT_SERVER_RELOAD=1, docker.sock, project mount
```

Constraints: the packaged app's flow (launcher → stack.start → cookie session) is unchanged and its e2e still passes;
the stack logic is not duplicated (refactor `stack.ts`'s Electron-only dependencies — `app.getPath`, `app.isPackaged`,
`app.getAppPath` — behind an injected host object so the dev script can run the same code under Node; `tsx` may be
added as a devDependency to run it); no secret is written to disk by the dev script; `desktop/README.md` "Dev loop"
is rewritten to the new commands and nothing else documents the old ones; `Ctrl-C` stops Vite/Electron and leaves
the container running (attach next time), `npm run dev:down` stops it.

Acceptance (numbers): from a cold shell with the container already running, `npm run dev:web` serves
`GET http://127.0.0.1:5173/api/version` → 200 with no cookie and no header from the client; `WS /ws/system` connects
from a plain browser page; after `docker restart` of the container the same tab keeps working without a reload;
`npm run dev` under `TIT_E2E_OFFSCREEN=1` reaches `data-page="subjects"` with real subjects listed (no launcher),
proven by the quiet check.

## 3. Smoke harness (P4–P8) — the contract S1/S2 implement

Level A layout: `tests/smoke/{conftest.py, client.py, matrix.py, cleanup.py, test_kinds.py, payloads/, README.md}`;
`dev/smoke.sh [kind…] [--keep] [--full]` discovers the dev container (labels `tit.stack=ti-toolbox-v3`) and runs
Level A against it (host Python 3, stdlib only). Level B layout: `desktop/tests/e2e/real/<kind>.spec.ts` with a
`real` Playwright project that only exists when `TIT_E2E_SERVER_URL` is set.

Behaviour vocabulary (P4) and budgets: `accepted` ≤ 10 s; `started` ≤ 120 s to `running` + banner; `completed`
≤ the kind's own budget (table); cancel ≤ 15 s to `cancelled` and no runner pid in `GET /api/system`.

Fixture matrix on Dataset 000 (S1 refines names after inspecting; every row must say why that subject):

| Kind | Subject / input | Asserts | Budget | Notes |
|---|---|---|---|---|
| pre: DICOM→NIfTI | `sub-102` (sourcedata DICOMs, no BIDS dir yet) | completed → `sub-102/anat/sub-102_T1w.nii.gz` + report | 120 s | creates the subject; cleanup removes `sub-102/` + its derivatives |
| pre: charm | `sub-102` (after the row above) | started (charm banner) → cancel | — | cleanup `m2m_102` |
| pre: FastSurfer | `sub-102` | started (FastSurfer banner) → cancel | — | cleanup `derivatives/fastsurfer/sub-102` |
| pre: tissue analysis | `sub-101` | completed (`replace_existing_outputs`) | 300 s | outputs under `derivatives/ti-toolbox/tissue_analysis` |
| pre: QSIPrep / QSIRecon / DTI | `sub-101` (no DWI data in 000) | accepted-then-refused: preflight reports "no DWI" as a readable job error, not a traceback | 60 s | the images exist locally; nothing is pulled |
| pre: trailing `report` | any `pre` group | completed | 60 s | **known broken** (F0) |
| sim (TI) | `sub-101`, net BioSemi-128 (the maintainer's own succeeded config), name `smoke-<id>` | started (solver banner) → cancel; `--full` runs to completion (≈16 min) | — | cleanup `Simulations/smoke-*` |
| sim (mTI) | same | accepted + started → cancel | — | |
| flex | `sub-ernie`, atlas ROI (list form) | started → cancel | — | **known broken** (F0); cleanup `flex-search/smoke-*` |
| leadfield | `sub-101`, a net that has no leadfield yet | started → cancel | — | cleanup |
| ex | `sub-ernie`, existing `EEG10-10_UI_Jurak_2007` leadfield, small candidate set | completed → csv + png artifacts | 600 s | cleanup `ex-search/smoke-*` |
| mex | same | completed | 600 s | cleanup `m-ex-search/smoke-*` |
| analyzer (mesh + voxel) | `sub-ernie`, simulation `Thalamus`, sphere + atlas ROI | completed → analysis artifacts | 300 s | cleanup `Simulations/Thalamus/Analyses/smoke-*` |
| source (EEG forward) | `sub-ernie` | completed if mne is in the image, else accepted-then-refused readable | 600 s | |
| stats: nifti_average | `L_Insula` across 101/ernie/MNI152 | completed | 300 s | |
| stats: group comparison / correlation | same three subjects | completed or readable refusal (needs ≥ 2 per group) | 300 s | |
| nilearn | one `L_Insula` NIfTI | completed → png | 120 s | |
| blender (montage) | `sub-ernie` | started → cancel (`--full` completes) | — | bpy under emulation |
| tools (`electrode_overlay` or `montage_visualizer`) | `sub-ernie` | completed | 120 s | |
| project_init | the project itself | completed (idempotent) | 30 s | |

## 4. Lanes (Workflow 1)

| Lane | Model | Owns (exclusive) | Delivers |
|---|---|---|---|
| **D0 Dev mode** | Opus | `desktop/scripts/dev*.ts`, `desktop/electron.vite.config.ts`, `desktop/src/main/{index,stack,launcher}.ts` (+ the injected host), `desktop/src/shared/compose*.ts`, `desktop/package.json`, `desktop/.env.dev.example`, `desktop/README.md`, `.gitignore`, `container/blueprint/entrypoint.ti-toolbox.sh` + both Dockerfiles, `tit/server/__main__.py`, `tests/test_server_*` for its change, `desktop/tests/unit/dev-*` | §2 in full, with the acceptance numbers recorded in `dev/notes/v3-pipelines/d0-notes.md` |
| **S1 API smoke** | Opus | `tests/smoke/**`, `dev/smoke.sh`, `pytest.ini` (marker + default deselect), `tests/conftest.py` (smoke gating only), `dev/notes/v3-pipelines/*-smoke.md`; may fix runner bugs anywhere under `tit/` **except** F0's and D0's files, logging each fix in its notes | Level A for every row of §3, a first full run against the dev container, the results table |
| **S2 UI smoke** | Sonnet | `desktop/tests/e2e/real/**`, `desktop/playwright.config.ts` (a `real` project), `desktop/tests/e2e/_helpers.ts` (additive), `tests/smoke/payloads/**` (writer); may fix page bugs under `desktop/src/renderer/pages/**` **except** `pages/optimizer/**` and `pages/_shared/roi/**` | Level B for every run page, the recorded payloads, a run against the dev container, results table |
| **F0 Known failures** | Sonnet | `tit/jobs/kinds.py`, `tit/jobs/plans.py`, `tit/pre/**` (report generation), `tit/opt/flex/flex.py`, `desktop/src/renderer/pages/optimizer/**`, `desktop/src/renderer/pages/_shared/roi/**`, their tests | The `report` kind runs (or the group no longer plans it — decide from what the report job was meant to do); flex accepts the list-form ROI end to end; both proven by a real run on the dev container |

Shared container rules: the dev container is `ti-toolbox-fad740e5-tit-1` on `http://127.0.0.1:8765`, token `devtoken`,
worktree mounted at `/ti-toolbox` with `PYTHONPATH=/ti-toolbox`. Runner subprocesses import the working tree, so a
change under `tit/<runner>` is live immediately; a change under `tit/server/**` or `tit/jobs/**` needs
`docker restart ti-toolbox-fad740e5-tit-1` — check `GET /api/jobs` for running jobs first (a restart kills them), wait
for `/api/health`, and note the restart in your lane notes. Never run two FEM-class jobs at once (P7). Nothing on the
screen: every Electron/Playwright run under `TIT_E2E_OFFSCREEN=1` via `scripts/e2e-quiet-check.sh`.

Gates per lane: host `pytest -q` stays green and under ~30 s (smoke deselected by default); desktop
`npm run typecheck && npm run lint && npx vitest run && npm run build`; the lane's own real run recorded as numbers.

## 5. After Workflow 1

Workflow 2 takes S1/S2's results table and assigns one fix lane per failing kind (Opus for runner/config work, Sonnet
for page/plumbing), each re-running its kind's smoke to green; then a critic pass (a fresh agent re-runs
`dev/smoke.sh` and the `real` e2e project from the documented commands only) and the final table. Decisions about
committing and merging `main` stay with the maintainer.

## 6. UI items from the maintainer's screenshots (2026-09-03 evening) — Workflow 1b

| # | Decision | Failure it prevents |
|---|---|---|
| U11 | **No project/subject crumb in the context bar.** The `000 › No subject` crumb goes; the bar keeps ⌘K search (now left-aligned, wide), connection and the running count. The current-subject store, `data-subject`, the palette's "Change subject" command and every page's own subject control stay — scope is chosen where the work is, not in a rail. DESIGN.md §(context bar) and plan U6 are amended to say so. | A second place to pick a subject that no page needs. |
| U12 | **Viewer in dev renders the app, not the embed.** The iframe's `/tetravox/…` URL is origin-relative; under Vite it hits the SPA fallback and nests TI-Toolbox in itself. `/tetravox` joins `/api`, `/auth`, `/ws` in the dev proxy (D0's file — done by the orchestrator after D0 lands). | A Viewer that only works in the packaged app. |
| U13 | **Jobs and Results right panes stretch, collapse and expand.** One shared behaviour from `ui/Layout.tsx`'s handle: a drag handle (pointer + arrow keys), a collapse/restore toggle (⌘⇧I, and a chevron in the pane header), an expand state that gives the pane the whole content width (for reading a long log or a report) and restores. Width persists per page in local storage. Jobs, which does not use `PageLayout`, gets the same primitive rather than its own. Measured: after a drag of +200 px `paneWidths().right` grows by 200 ± 4; collapsed → right pane 0 and work pane takes the width; expanded → work pane 0. | Fixed 360/400 px panes beside a 1200 px table. |
| U14 | **The Results preview says what the output is, not where it is.** For a simulation: mode (TI/mTI), EEG net, electrode pairs, intensities, conductivity, electrode geometry, mapping options, created date, the field files and analyses it holds (from `documentation/config.json` + the catalog). For a flex run: goal, ROI, net, iterations, best value and the final electrode positions with its figures (`flex_meta.json`, `summary.txt`, `electrode_positions.json`, PNGs). For ex/mex: the run config and the top rows of `final_output.csv` as a table (montage, currents, TImax_ROI, focality) with its figures. Reports keep the iframe; analyses keep their summary. The path stays as one mono line at the bottom. | A preview pane that is a path and a button. |
| U15 | **3D panes in Simulator and Optimizer** (skin + GM with transparency, the chosen EEG net's electrodes, click to (de)select electrodes, orbit; for the optimizer the same on mesh or NIfTI with click-to-target ROIs) are a **Tetravox Embed protocol extension first** — `dev/notes/v3-3d-panes-plan.md`. The embed already has `tagStyle` per mesh tissue, `opacity`, `pickable` and a `3d` layout; it has no marker layer and no pick event. TI-Toolbox contains no Tetravox code (the microservice rule), so the host pages follow the embed release, not the other way round. | Re-implementing a renderer inside TI-Toolbox to get electrodes on a head. |
| U16 | **Run pages own their subject set.** U11 deleted the only control that could set a multi-subject batch (`useSubject().batch` has no writer left); Simulator, Optimizer and Analyzer still read it. Each run page gets a page-owned subjects control in its Tier-1 fields — the pattern Pre-processing already uses (its own subjects table seeded from the current subject) — so a multi-subject run is reachable again, and the Plan grid's subject × stage matrix is fed from the page, not from the shell. Measured: selecting two subjects on Simulator yields a plan with two jobs and two matrix rows; the recorded UI payload (`tests/smoke/payloads/`) carries both ids. | Multi-subject runs unreachable from three of the four run pages after U11. |

Lanes (1b, done 2026-09-03 evening: UA 24 e2e assertions, Results preview dead space 60.5 → 16.1 %; UB full suite 91/1): **UA** (Opus) owns U13 + U14 — `desktop/src/renderer/ui/Layout.tsx` (pane primitive), `pages/jobs/**`, `pages/results/**`, `app/jobs-rail/JobDetailPane.tsx` (only as needed for the pane), `tests/unit/{pane,results-preview}*`, `tests/e2e/{jobs,results}.spec.ts`, mock fixtures for the new preview files; **UB** (Sonnet) owns U11 — `app/AppContextBar.tsx`, `app/Shell.tsx`, `app/SubjectSwitcher.tsx` (delete or fold into the palette), `app/CommandPalette.tsx`, `tests/e2e/_helpers.ts` (only what the crumb's removal breaks), `tests/e2e/{subjects,smoke,screens}.spec.ts`, `desktop/DESIGN.md` context-bar section, `dev/notes/v3-ui-program.md` U6 amendment. The pipelines lanes (D0, S1, S2, F0) keep their ownership; UA/UB re-read a file before every edit because S2 may be fixing pages concurrently.

Follow-ups recorded after Workflow 1b: U16 (above) goes to Workflow 2 as lane **UC** (Sonnet: `pages/simulator/**`, `pages/optimizer/**` Tier-1 subject field only, `pages/analyzer/**`, their specs). The quiet check now ignores owner windows that were on screen before a run starts (identity = window-server id) and fails only on windows that appear during it — the maintainer's own dev window is a note, not a failure (`desktop/scripts/e2e-quiet-check.sh`).

## 7. Workflow 1 results (2026-09-03 evening) and Workflow 2 lanes

Workflow 1 landed everything in §2–§4: dev mode (`npm run dev` / `dev:web` / `dev:down`, bearer-injecting proxy, no
token in hand, `StackHost` refactor so one attach-or-start serves the app and the script), Level A (21 rows, all
green in 281 s against Dataset 000, 9 replaying UI payloads, zero paths left behind), Level B (12 real specs, 9 kinds
green through the pages), and both known failures fixed (flex list-form ROI; the trailing `report` job now runs
`tit.pre.report`). Per-lane records: `dev/notes/v3-pipelines/{d0,s1,s2,f0}-notes.md` and
`dev/notes/v3-pipelines/2026-09-03-smoke.md`.

What the runs surfaced, and who fixes it in Workflow 2:

| Lane | Model | Finding (evidence) | Owns |
|---|---|---|---|
| **FX1 Optimizer** | Opus | Ex/mEx cannot be run from the UI against real data: the electrode-bucket multi-selects are empty for every leadfield-backed net (s2-notes, `real/ex.spec.ts` waits for option `Fp1` forever). Plus the optimizer half of U16 (page-owned subject set). | `desktop/src/renderer/pages/optimizer/**`, `pages/_shared/roi/**` (if needed), `tests/e2e/real/{ex,mex,flex}.spec.ts`, `tests/e2e/optimizer.spec.ts` |
| **UC Run-page subjects** | Sonnet | U16 for Simulator and Analyzer: a page-owned subjects control (the Pre-processing pattern); two subjects → two plan jobs and two matrix rows; payload carries both ids. | `pages/simulator/**`, `pages/analyzer/**`, their unit/e2e specs, `tests/e2e/real/{sim,sim-mti,analyzer-*}.spec.ts` |
| **FX2 Jobs + server** | Opus | `GET /api/project.host_path` is null (smoke has to `docker inspect`); no live OpenAPI (`openapi_url=None`); cancelling any job writes a PETSc/MPI "Caught signal 15 / MPI_Abort" block that reads as a crash (even for blender); the `report` job holds no locks (`locks.py` has no per-subject report branch); `GET /api/jobs/{id}` shape `{spec,status}` vs what a client expects (s2-notes item 3). | `tit/server/**` (not `__main__.py` reload flags), `tit/jobs/**`, their tests |
| **FX3 Runner artifacts + catalog** | Opus | stats, blender and tools jobs report zero artifacts though they write files (stats: 9 files); an analyzer run with a custom `output_dir` is invisible to the catalog (`tit/catalog.py` scans only `Analyses/{Mesh,Voxel}`); nilearn's default `min_cutoff` 0.3 V/m is above every real TI field (ernie L_Insula peaks at 0.1385) so the default run dies — replace with a data-driven preflight/default. | `tit/stats/**`, `tit/blender/**`, `tit/tools/**`, `tit/plotting/nilearn/**`, `tit/catalog.py`, `tit/analyzer/**` (output dir only), tests |
| **FX4 Source forward** | Opus | The EEG forward pipeline starts, computes for ~10 min, then fails `AttributeError: No mne.source_space attribute _complete_source_space_info` — the image's mne is newer than the code (memory: pin mne~=1.5). Fix the code path for the installed mne (preferred) or pin it; prove with one full `source` run to completion. | `tit/source/**`, the mne pin in `container/blueprint/Dockerfile.ti-toolbox*`, `tests/test_source.py` |
| **FX5 Subject onboarding** | Sonnet | A subject that exists only under `sourcedata/` (DICOMs, no BIDS dir — the matrix's own sub-102 row) is not selectable in the UI, so Pre-processing cannot onboard a new subject at all (Level A does it through the API). The catalog lists sourcedata-only subjects with a `raw: dicom` readiness; Subjects and Pre-processing show them as "not converted" and let the DICOM stage be planned. | `tit/catalog.py` (subject listing), `tit/server/routes/catalog*.py`, `pages/subjects/**`, `pages/preprocess/**`, `tests/e2e/real/preprocess.spec.ts`, `tests/test_catalog*.py` |
| **HX Harness polish** | Sonnet | Replayed UI payloads that name a fixed output (stats `analysis_name`, analyzer null `output_dir`) skip on the second run by P6 — the loader rewrites name fields to the smoke tag; `dev/smoke.sh` explains the two-container case; a one-page runbook `dev/notes/v3-pipelines/RUNBOOK.md` (dev mode, smoke, real e2e, restart rules). | `tests/smoke/**`, `dev/smoke.sh`, the runbook |
| **CR Critic** | Sonnet, after the barrier | Re-runs `dev/smoke.sh` (every kind) and `npx playwright test --project=real` from the runbook's commands only, offscreen; reports the two tables; fixes nothing. | read-only |

Container rules for Workflow 2 are those of §4 (shared container `ti-toolbox-fad740e5-tit-1`, token `devtoken`,
worktree mounted; `tit/server/**` and `tit/jobs/**` changes need a restart with no jobs in flight). The image is being
rebuilt with the reload entrypoint in parallel; the orchestrator flips `TIT_DEV_MOUNT_REPO=1` and recreates the shared
container through `npm run dev:web` only after Workflow 2 ends.

## 8. State of record after Workflow 2 (2026-09-04, early)

Critic re-run from the runbook alone (`dev/notes/v3-pipelines/critic-w2-notes.md`): Level A 20/21 (the FastSurfer row
failed because `run_fastsurfer.sh` refuses to run as root — fixed afterwards by passing `--allow_root` in
`tit/pre/fastsurfer.py`; the row passes when run after the DICOM row it depends on, 2 passed in 19.6 s), Level B 14/14
real specs green in 14.5 min including a full EEG forward solution (9.7 min), host pytest 3354 passed, desktop
typecheck/lint/vitest 716/build clean, zero paths left on Dataset 000.

What Workflow 2 fixed (lane notes under `dev/notes/v3-pipelines/`): optimizer ex/mEx electrode buckets (bare vs
`.csv` net names across two catalogs; `pages/optimizer/nets.ts`), U16 on Simulator/Optimizer/Analyzer, `host_path`
on `/api/project`, `/api/openapi.json`, cancel noise (`PETSC_OPTIONS=-no_signal_handler` + one "cancelled by user"
line), report-job locks, artifacts for stats/blender/tools/analyzer-group, analysis discovery anywhere under a
simulation, nilearn data-driven cutoff, the source forward path (four faults: lazy mne namespace, SimNIBS cortech
alias, our channel order, missing `h5io`), sourcedata-only subject onboarding, payload renaming so replays never
skip, `dev/smoke.sh --list`, `RUNBOOK.md`.

Remaining, none blocking a pipeline:
- Image: `h5io` added to both recipes; the shared container must run the rebuilt image (orchestrator, after W2).
- `ui/Layout.tsx`: the sticky action bar does not reserve its 44 px in the scrollable work pane (UC found it; UA's
  primitive owner); `RunWork`'s fill controller re-measures only on pane resize, not content growth.
- `tit/jobs/events.py` artifact kinds: `.blend/.glb/.stl` reported as `txt`.
- nilearn panel UI still defaults `min_cutoff` to 0.3 V/m (above real TI data); leave both cutoffs unset by default.
- `GET /api/catalog/analyses/{name}/summary` cannot address a name containing `/` (uvicorn decodes `%2F`).
- Harness: `source` row is once-per-project under P6 (fixed output dir) and its payload sets `overwrite: true`;
  no Level A row for stats correlation mode (no effect-size CSV in Dataset 000); nilearn row still carries the old
  percentile workaround; `expect_files` unused for payload rows.
- Mock coverage for the Subjects page's "not converted" state.
- With `-no_signal_handler` PETSc prints no stack for a genuine solver SIGSEGV either.
- 3D panes (U15): Tetravox protocol 2 ask in `dev/notes/v3-3d-panes-plan.md`; maintainer decides who builds it.
