# What happened, and what it cost

> Historical. The living records are [`ARCHITECTURE.md`](ARCHITECTURE.md) (what the system is),
> [`DECISIONS.md`](DECISIONS.md) (why), [`DESIGN.md`](DESIGN.md) (the UI contract),
> [`BENCHMARKS.md`](BENCHMARKS.md) (every measured number) and [`RELEASE.md`](RELEASE.md) (how it
> ships and what is still open). **Where this file and those disagree, they win.**

One record of the v3 (Electron desktop) programs on `feature/v3-electron-gui`, 2026-08-27 →
2026-09-07, plus the pre-v3 findings still worth having. It replaces ~120 per-program plan files and
per-lane evidence notes that used to live under `dev/notes/`, and the plan, requirement and spike
documents that used to sit beside it in this directory.

What is kept is only what the living records do not carry: for each program the ask, what shipped,
what was reversed, and the **gotchas** that were paid for once and would otherwise be lost.

---

## The maintainer's dated asks

Four requirement documents used to sit in `docs/dev/requirements/`. Their gate tests all passed and
their rules are now `ARCHITECTURE.md` §§2–7 and `DESIGN.md`; what is kept is the ask itself, because
a rule reads differently when you know the sentence that forced it. **Where two conflict, the later
one wins.**

**2026-09-04 — tab continuity, one control grammar, a focused 3-D preview.** *"users can interact
with the pre-processing tab, jump to the simulator tab, make changes, go back … and everything will
be the same"*; *"they could look at the visualizer, move to a different tab and when they're back
everything will be the same. This is highly highly important and is a non-negotiable"*; *"there is
no clear design philosophy in terms of the button layouts, the different drop downs the subject
selection"*; *"we only require the 3D visualization panel … the two sliders that we had earlier for
the skin and the gray matter were removed and they were actually good to have"*; *"make sure to
consolidate such that you and i can test it with pnpm run dev"*. → ARCHITECTURE §§2–4, DESIGN §4.4.2
and §13. R3's two sliders became one on 2026-09-06: grey matter is opaque.

**2026-09-05 (first batch) — Overview, terminal, batch, guide, explicit Load.** *"the first tab
should not be subjects, it should be overview"*; *"delete the subject info page completely"*;
*"regarding the terminal in all pages, make sure that A it is scrollable, b that it can be cleared.
Make sure the logic is modular and recyclable"*; *"all pages that require subject selection … need
to behave like the pre-processing does"*; *"users should be able to select multiple subjects for
either a parallelized or a sequential processing"*; *"instead of rendering the selected individual,
we can be rendering a general individual, for example, Ernie"*; *"the top [bar] will have more
selection … and it does not load information automatically based on subject selection"*. → the five
requirements **R1** (Overview replaces Subjects, one aggregate read), **R2** (one scrollable,
clearable console), **R3** (one subject grammar, the cap enforced by the scheduler), **R4** (a fixed
packaged guide in the run-page panes), **R5** (the Viewer loads on command) — the labels other
documents cite as "the 2026-09-05 R1–R5". Contract: ARCHITECTURE §6.

**2026-09-05 (second batch) — Tetravox currency, dots, selection, pipelines.** *"automatically gets
updated if Tetravox is releasing a new version"*; *"dot-like visuals for the electrodes … change
their colors and make sure that the selection deselection works properly"*; *"in the TI toolbox
2.5.0 we had a great logic for selecting multiple jobs … right now it's too convoluted"*; *"a
canvas-like graphical programming where users create nodes of processing and (1) run it as a
pipeline … as a single job and (2) create Jupyter notebooks out of it"*. → decisions **A–D**;
contract ARCHITECTURE §7.

**2026-09-06 — native panes, external viewer, jobs tables.** *"we had a really neat implementation
that … showed the electrodes in a better fashion and also the atlas ROIs were interactive"*; *"write
our own little module based on the logic from Tetravox and embed it exactly how we need it"*; *"the
viewer tab only acts as the data selection and it actually opens up everything in [an external
window] like we have in 2.5.0"*; *"I want the complexity to be as simple as possible"*; *"it's hard
to separate users, montages, modes in different jobs … we need a list of jobs in a table"*. →
decisions **N1–N4** (our own renderer), **V1–V5** (the external viewer — reversed the same day, ADR
row 29) and **J** (jobs tables). Contract ARCHITECTURE §7.2, §7.5.

---

## 2026-08-27 — build program and spikes

Build every screen in parallel against a frozen contract, backed by real `tit.server` endpoints,
ending in a real run on Dataset 000. Shipped `tit/server/routes/`, `contracts/openapi.v1.yaml`, one
directory per screen, and the job model — queue/group/progress/liveness/cancel/rerun/force,
`events.jsonl`, `WS /ws/jobs`. Every later redesign judged the job model the strongest part of v3 and
left it untouched. Contract-first development survived; the flat per-page IA it produced (19 nav
rows, 7 subject pickers) did not, and NiiVue-as-engine was superseded by Tetravox.

- NiiVue cannot read Gmsh `.msh` (needs server-side `mesh_io` conversion); a `name:` without an
  extension throws; `.curv` scalars do not colour meshes (use GIfTI `.func.gii`); volume clip planes
  do not cut meshes.
- `TI_max` percentiles must be computed **GM-masked**, not whole-volume: scalp p99 = 0.81 V/m
  against GM p99 = 0.17 V/m.
- `write_gifti_surface(msh, fn, geometry=None)` keeps mesh mm in T1 scanner RAS. Never pass a volume
  `geometry` or the surface shifts by `c_ras`.
- `import simnibs` costs 3.4 s and 387 MB; `tit.analyzer`/`tit.stats`/`tit.pre` do not pull it. Hence
  the server imports SimNIBS lazily and `/api/health` answers immediately.
- Host pytest regressed 30 s → 87 s because `test_telemetry.py` joined *every* alive daemon thread
  once another test left a `JobManager` poll thread running. The same audit found live GA4
  production credentials in `tit.constants` being POSTed to from tests; now a session-wide no-op.

## 2026-09-02 — UX redesign, workflow-first IA

Three independent design proposals judged on feasibility, risk and testability. Workflow-first won
(35 vs 33 vs 27) and became the IA of record. Shipped the merged `overview` page, one merged
`optimizer`, the raw-file route and the scene-document delta, and the iframe embed client.
In-process `@tetravox/engine` vendoring was built, measured and then rejected by the maintainer
(*"wrap around it as a microservice"*) and replaced by the iframe/postMessage embed the same day.

- `@tetravox/engine` ships zero React; the app chrome an in-process route would have had to rebuild
  is 9,345 LOC that a whole-app iframe gets free. That single fact reordered the three proposals.
- `packages/wasm/pkg` is git-ignored and `npm pack` silently drops it — Tetravox was not installable
  until an upstream one-liner.
- Embedding the engine needs `optimizeDeps.exclude`, `worker.format: 'es'` (Vite's default IIFE
  worker format cannot be a module worker), `assetsInlineLimit: 0`.
- No custom Electron scheme is needed: the dataset worker does a plain same-origin `fetch` and the
  session cookie rides along. CSP needs `script-src 'self' 'wasm-unsafe-eval'`.
- Density-first had the best evidence and still lost: workflow-first was the only proposal that
  answered the maintainer's actual complaint — the old IA had no notion of *where a subject is*.

## 2026-09-03 — native desktop research (parked)

Could TI-Toolbox drop X11, FreeSurfer and Gmsh and ship as one native executable with no Docker?
Judged "realistic, with three precise corrections", then **parked** in favour of Electron + one
Docker image (ADR rows 18–22). Only Linux x86_64, Windows x64 and macOS Apple Silicon are natively
viable — no Intel Mac (bpy, torch and SimNIBS's petsc4py fork ship no x86_64-macOS wheels), no ARM64
Linux or Windows. Installed size 2.5–3.5 GB. DWI preprocessing has no native path on any OS, so
Docker could only have become optional, never removed. Two licence flags were raised for any
commercial distribution: ADMlib (GPLv2, non-commercial, unused by our code) inside the SimNIBS wheel,
and Intel MKL's EULA on Linux and Windows.

Six throwaway spike lanes ran it. Their code was never shipped and is deleted; these verdicts are the
only surviving record, and everything was measured on one Apple M2 — **no x86_64 or Windows machine
was ever used.**

- **runtime (N0.1) — proven, numerically exact.** A pip + python-build-standalone runtime with
  SimNIBS 4.6.0 + `tit`, 2.0 GB without bpy, matched the emulated container to 13–14 significant
  figures on a real two-pair TI simulation; `subject_atlas` DK40 output was byte-identical and 1.7×
  faster. Corrections to the brief: SimNIBS's default solver is **hypre on every platform**, not a
  platform-conditional pardiso/MUMPS. Two upstream packaging defects needed scripted grafts —
  `python-mumps` has no PyPI wheel on any platform, and SimNIBS's macOS CGAL extensions carry the
  developer's absolute `LC_RPATH`.
- **fastsurfer (N0.2) — viable, with a measured accuracy tax.** `--seg_only` on CPU, ~5 min per
  subject, mean Dice 0.922 (14 subcortical) and 0.914 (20 cortical DKT) against real `recon-all`,
  n = 1. Centroid shifts mostly < 1.5 mm with a pallidum outlier at 3–4 mm — negligible for 10–15 mm
  ROI spheres, a real caution at 5 mm. Production use needs `--no_cc`.
- **fs-binaries (N0.5) — exact replacements, zero remaining calls.** `mri_convert --reslice_like` →
  `nibabel.processing.resample_from_to(order=0)` differs in **0 of 13,631,488 voxels**;
  `mri_segstats` → `tit/atlas/segstats.py` matches label ids and voxel counts exactly on four real
  atlases. Known gap: the bundled `FreeSurferColorLUT.txt` is 2012-vintage and lacks thalamic-nuclei
  display names; ids and volumes are still exact.
- **job-control (N0.6) — proven on POSIX, Windows monkeypatch-tested only.** `tit/jobs/processes.py`
  gives Windows-safe spawn and psutil-based kill that never calls `signal.SIGKILL` (which does not
  exist on Windows). QSIPrep/QSIRecon containers gained `--label tit.job_id`, fixing a real dead-code
  bug in which cancel never worked for them.
- **docker (N0.3) — proven live against Docker Desktop 4.57 / Engine 29.1.3 / API 1.52.** Untested:
  the Windows named pipe, and Podman/Colima compatibility sockets.
- **packaging (N0.4) — proven end to end on macOS arm64 only.** Two real defects found and fixed:
  electron-builder 26.15 resolves `extraResources.from` *before* expanding `${env.X}`, and
  `codesign --options runtime` without entitlements silently breaks every C-extension import. The
  full 2–3.5 GB runtime and Developer ID notarization were never attempted.

## 2026-09-03 — Docker streamline (one image)

*"Keep docker but streamline everything else."* One image `idossha/ti-toolbox:<ver>` (SimNIBS 4.6 +
`tit` + `tit.server` + the built UI + the Tetravox embed + FastSurfer `--seg_only`); the FreeSurfer
image dropped entirely; X11 removed everywhere; the desktop stack moved onto the Docker Engine API.
`Dockerfile.ti-toolbox.layered` was later deleted by the maintainer, leaving one from-scratch recipe;
`--layered` / `--from-scratch` / `--skip-ui-build` are accepted and ignored so old command lines work.

- `docker images` prints non-deduplicated **disk usage**. Always cite *content* size — it is the
  fresh-pull cost and it is stable.
- `pip install -e /opt/fastsurfer` defaults to CUDA torch (~2 GB of `nvidia-cu12*`) on a machine with
  no GPU. Pin `torch`/`torchvision` from the CPU wheel index first.
- `COPY <dir> <existing-dir>` **merges**, it does not replace. `build.sh`'s version `sed` used `\s`,
  which is GNU-only and a silent no-op under macOS BSD sed; use `[[:space:]]`.
- The thalamic-nuclei atlas: sorting label ids into `.volumes.txt` name order is provably wrong
  (verified against three subjects). Fixed by vendoring the thalamus section of FreeSurfer's LUT.
- **Real blocker:** stack start unconditionally bind-mounted a host worktree over `/ti-toolbox`,
  silently replacing the packaged image's `tit`. Now opt-in only, via `TIT_DEV_REPO_DIR`.
- FastAPI's `APIRoute` does not infer `HEAD` from `GET` — explicit `@router.head` handlers are needed.
- Compose-parser contract: anything outside the supported subset (`depends_on`, `tty`, `env_file`,
  long-form volumes) is a named startup error. `platform` goes on the container-create query string.
- Security, flagged not fixed: the bearer token is plaintext-readable via `docker inspect` and
  `docker exec env`. Acceptable for a single user; per-attach rotation is unfixed.
- CI: `build-and-smoke-image` builds SimNIBS from scratch — 30–60+ minutes natively — which is why
  deleting the layered recipe made the job intractable and why no nightly variant exists yet.
  `desktop-checks` needs Xvfb: Electron's Chromium needs a real X display even offscreen.

## 2026-09-03 — pipelines program (dev mode, smoke harness)

*"Bring every pipeline to a real working state under `npm run dev` with no token in hand."* Shipped
`npm run dev` / `dev:web` / `dev:down`, the two-level smoke harness, `dev/smoke.sh`, and fixes for
both known-broken job kinds (flex's list-form `atlas_path`; the trailing `report` job). The commands
and rules are now [`CONTRIBUTING.md` §2.6](CONTRIBUTING.md); the numbers are in `BENCHMARKS.md`.

- `--project=real`, never `--project real` — Playwright's variadic `--project` swallows the spec path.
- Never `npm run e2e` for a real-server run: `pree2e` force-rebuilds `out/` and races other lanes.
- Never run two FEM-class jobs at once. The harness enforces it itself.
- nilearn's default `min_cutoff` of 0.3 V/m is above real TI data (ernie L_Insula peaks at
  0.138 V/m) — still an open UI default.

## 2026-09-03 — UI program (shell, run pages, results)

*"The app was replicating PyQt too closely. Stop capping width, add a real run panel, and prove every
layout claim with a measured DOM metric rather than a screenshot — judge numbers, not pictures."*
Shipped the flat workflow-ordered rail, the `RunPanel` (Plan grid over Terminal), a subject-centric
Results, and the DOM metrics instrument. `PageLayout`'s 880 px cap was removed entirely.

- The DOM `deadSpaceRatio` is *stricter*, not more lenient, than the pixel-occupancy proxy it
  replaced: limits set from the proxy were unreachable and had to be renegotiated (≤ 25 % → ≤ 45 %
  for run pages). `DESIGN.md` §12.3 is the acceptance table of record.
- The shared `out/` build directory races: a screenshot taken without an immediately preceding
  rebuild picks up another lane's in-flight build.
- `.page-layout-panel { align-self: flex-start; max-height: 100% }` sized a pane to its content,
  collapsing report `<iframe>`s to their 150 px intrinsic height.
- `direction: rtl` for left-truncating a mono path bidi-reorders the leading `/` to the end,
  producing a fake trailing slash. Use `truncatePathLeft()`.
- Light-theme-only WCAG AA failures found by hand-computing from `tokens.css`, because the token test
  only covered filled-button pairs and not soft-chip pairs.

## 2026-09-04 — scene service, subject-selection grammar, layout pass

*"A slim scene management"* loading exactly what the three run pages need. Shipped `tit/scene/`, the
`TVSC1` binary wire format, a ~700-line WebGL2 renderer, a shared `<ScenePane>`, one `SubjectsField`
replacing four divergent subject pickers, and the shared run-page skeleton. The renderer was
structurally replaced during the embed-convergence fallout and restored on 2026-09-06; the scene
*service* underneath has been load-bearing throughout.

- `ernie.msh` is 184 MB and is never sent to the browser.
- **Never restart uvicorn `--reload` blind.** An import-time assert in an auto-discovered route
  module took the shared dev container down for ~4 minutes. Rule adopted: a route module does no work
  at import time, and every save under `tit/` is followed by a health check — after a wait, because
  `curl /api/health` returning 200 right after a save can be answered by the pre-reload process.
- Pick-culling bug: on real anatomy the culled pick named a surface *behind* the visible one at 399
  of 400 sampled pixels, because the served `gm` was wound inward everywhere. Fixed by drawing both
  faces in the pick pass and orienting every surface outward, with a `BUILDER_VERSION` cache salt.
- Never repeat a hand-rolled `<div style="display:grid">` row idiom per page.

## 2026-09-04 — embed convergence and runtime-installable Tetravox

Two halves: make the run-page panes drive the embed, and decouple TI-Toolbox releases from Tetravox
updates. The **delivery** half shipped in full and survives (ADR row 29). The **pane-migration** half
was left unfinished and then retired on 2026-09-06: the panes reverted to native WebGL2.

- **`TarFile.extractall()` is not safe even with default filters.** On the container's Python 3.11.14
  it wrote `../escape.txt` outside the destination; host Python 3.14 refused it. Extraction is
  hand-rolled.
- A certifi fallback is required in-container: `simnibs_python`'s OpenSSL default verify paths point
  at absent conda build-time paths, so TLS fails with `CERTIFICATE_VERIFY_FAILED`.
- `pkill -f 'http.server 8919'` kills its own invoking shell when run in the same `sh -lc` string as
  its cleanup; use a self-excluding regex like `http[.]server 8919`.
- A sandboxed `pnpm test` showing 34 `listen EPERM` failures from a unix-socket fixture is a sandbox
  artifact, not a bug — recognise them as such before re-deriving them.

## 2026-09-05 — Overview, batch, guide panes, explicit Load (R1–R5)

Shipped `GET /api/catalog/overview`, the shared `JobConsole` with a watermark Clear,
`/api/jobs/groups` widened to every per-subject kind with the cap enforced by the scheduler, the
packaged Ernie guide, and the Viewer's draft/loaded split. All five requirements passed their gate.

- Cortical `.annot` atlases (FreeSurfer surface parcellations) cannot be offered in the Viewer's
  volume-based ViewSpec. A real gap, still open.
- The `source` pipeline kind is deliberately excluded from `GROUP_KINDS` and the batch cap — it is a
  single job over the whole selection with its own `cpus`/`workers`.
- The guide's licence is GPL-3.0 via the SimNIBS example-dataset repo — *not* the CC BY-NC 4.0 that
  applies only to "Ernie Extended" and the non-human-primate models.
- One flake was chased rather than smoothed: the Analyzer's dead-space bound read 0.61 against ≤ 0.65
  once and reproduced clean twice after. Recorded as a marginal measurement; threshold left alone.

## 2026-09-05/06 — Tetravox auto-update, electrode dots, selection grammar, pipeline canvas

Shipped the update channel against the GitHub Releases API, electrode dots with colour as the whole
state, the `ui/SelectionList` primitive that replaced five prior idioms, and the React Flow pipeline
canvas with notebook export. The earlier draft plan (lanes T/U/E/S) was superseded within a day by
the A–D plan actually implemented; only the latter is cited by code and tests.

- Auto-update rules, exactly: the GitHub Releases API, non-draft, non-prerelease, newest first; a
  release needs all three of `tetravox-embed-<ver>.tgz`, `.tgz.sha256` and `.manifest.json`; the
  protocol is read from the ~2 KB manifest asset alone; a release past the supported range is
  reported as "needs a TI-Toolbox update" and never installed.
- **Never `git stash` in this worktree** (it cost the shared container mid-FEM); **never two
  Playwright runs at once**. `e2e-quiet-check` can false-FAIL on a machine actively in use;
  diagnose with `ps`/`tty` before suspecting the lane's own tests.
- Something outside the session restarted the container mid-FEM, orphaning a running `sim` to `lost`
  and skipping its dependent analyzer. **Job re-adoption across a `--reload` is not implemented**,
  and it is the single most user-visible open gap.
- `tit/jobs/bindings.py` is separate from `tit/pipeline/` on purpose: `tit.jobs` must never import a
  pipeline module to run an ordinary job.

## 2026-09-06 — native panes, external viewer, jobs tables

The run-page panes became the app's own restored WebGL2 renderer with an interactive atlas and dot
electrodes; the Simulator, Analyzer and Optimizer gained per-row jobs tables; a Notebooks page shipped
alongside. The Viewer went to an external Tetravox app in the morning and back to the in-image embed
on its own sub-page in the afternoon (ADR rows 27 → 29) — the reversal is why `docs/dev` carries three
Viewer decisions dated one day apart.

- `Fiducials.csv` was listed as an EEG net — it holds only registration landmarks and never resolves
  an electrode. A real e2e spec that enumerated *every* net caught it; no unit test did.
- **Never `git add -A` in a shared worktree.** It swept another lane's uncommitted files into the
  wrong commit three times in one day. Use disjoint explicit paths.
- The 2026-09-04 native renderer was recovered from a `~/.treehouse` copy, **not** from git history.
  That copy was its only surviving source.
- A viewer test that checks only that the plumbing ran can still be showing nothing on screen — it
  happened twice in one day (a 1224×0 pane; a scene never posted because `pendingScene` was nulled by
  a StrictMode double-invoke in dev only). Assert visibility, not success.
- **`.tetravox.json` is a compound extension and load-bearing.** Any other suffix is classified as
  *data* and silently read as a volume, with no error on either side.
- **`dev/build_contract.py` was non-deterministic**: it iterated a `set[str]`, so two runs on
  identical inputs differed by hundreds of lines and two lanes concluded the JSON was "stale". Fixed
  with `sorted(...)`.
- **`--reload` persists settings to a 0600 JSON file every reloaded worker re-reads**, so removing a
  `ServerSettings` field mid-session made `cls(**data)` raise on every reload and took the shared dev
  container down for a lane's window. `from_json` now drops undeclared keys.
- **A browser silently drops a declaration whose `var()` is undefined** — no console warning, no
  build error, no failing test. `pipeline.css` had 36 references to a token vocabulary this app never
  had; the page was not broken, it was unstyled.
- `window.prompt` is not implemented in Electron and `<a download>` on a `blob:` URL is inert without
  a `will-download` handler. Both look like success and write nothing.
- **`emit_artifact` verifies nothing.** A `sim` job reported `succeeded` with an artifact path that
  was not on disk; its dependent analyzer failed five seconds later naming its producer's own
  declared output. One `Path(path).exists()` at emit time would make that an honest upstream failure.
- `antialias: true` forbids an exact depth-equality sheet test; use an inequality with
  `SHEET_EPS = 1e-5`. For a selection outline use `fwidth` and read the varying as a signed field
  whose 0.5 contour is the boundary — treating `0 < v < 1` as "the rim" paints a band of shards.
- A `Select` popover (z-index 60) is **unclickable inside a `Dialog`** (80/90) — a known
  `ui/components.css` gap, and the reason the montage and free-hand editors are inline cards.
- `GET /api/view/presets` would have been shadowed by `GET /api/view/{kind}`, returning a 404
  indistinguishable from "no presets". The real path is `/api/viewer/presets`.
- Three defects the driven notebook runs found, none of which static reading would have: a
  command-mode guard that tested `target.tagName === "TEXTAREA"` (true for a textarea, false for
  CodeMirror's contenteditable, so typing `print(` re-typed the cell as **raw** under the author's
  cursor); ⇥ falling through to `indentWithTab`, which indented **and** dismissed the completion it
  should have accepted; and a completion range that filtered every option away, because the kernel
  replaces the whole dotted expression.
- Still-open traps: `/api/scene/*` is live and called by nothing; the guide packages ~11.3 MB of
  GIfTI copies nothing reads; job re-adoption does not survive a `--reload`; and
  `FlexConfig.output_folder` is the run name while ex/mEx use `run_name`.

## 2026-09-07 — external audit response

An external audit of the shared scientific core and of the v3 server. Every finding was reproduced in
this repository first, then fixed at its cause or — where it was a modelling question — written up.
Six numerical defects (SCI-01…06, plus SCI-07 and SCI-08) are recorded for users in
[`SCIENTIFIC-CORRECTIONS.md`](SCIENTIFIC-CORRECTIONS.md) and decided in `DECISIONS.md`; the server
findings landed as reserve-before-acquire for the kernel cap and the scheduler's locks, an unknown
`after` no longer counting as satisfied, one enforced subject-id grammar, `tools` argument
confinement, revisioned notebook saves, an authoritative reconnect snapshot, an allowlist sanitiser
for rich output, and a backend-independent quit plan. The largest single finding was that pushing a
`v3.0.0` tag would have built and published the **legacy 2.x launcher**.

Six of the reds were not in the audit at all; the gate found them because it ran the *whole* system.

- **A test that writes `sys.modules` without `monkeypatch` is a time bomb for every later test in the
  process.** Four tests assigned `sys.modules["nibabel.freesurfer.io"] = MagicMock()` and never undid
  it, so a later `importorskip` *succeeded* and handed that test a mock — but only in one file order,
  which is why it was carried for two gates as "a known order-dependent flake".
- **Lint errors get attributed to whichever file the reporter printed last.** 17 `no-undef` errors
  reported against three renderer files were all in `scripts/verify-package.mjs`: the flat config
  gave Node globals to `tests/mock-server/**` only.
- **A global `.gitignore` rule can hide a required build input indefinitely.** `build/` swallowed
  `desktop/build/`, so four files `electron-builder.yml` names by path had never been committed.
- **`electron-builder`'s `files:` is not "what the repository contains".** `docker/**` was outside it
  while `src/main/stack.ts` reads `docker/docker-compose.v3.yml` at every stack start.
- **A whole-system gate finds a different class of defect from a test suite.** A Settings page that
  could not save, a button covered by another card, and a statistics job dying in a numpy reduction
  were all invisible to 4,073 unit tests and 317 mock e2e tests.
- **A `toHaveText` that never matched is not a flake.** Two real specs asserted a string no version of
  the row has produced. They looked like environment trouble because they only ever ran in the real
  leg, which no lane ran on every change.

### Addendum — what landed after the audit, and the consolidation gate (CX7)

Four more programs closed on the same day, and CX7 gated all of them together
(`BENCHMARKS.md` § CX7 consolidation gate).

- **The exposure science** (`1694c69f`, `4483df4b`) — SCI-07 and SCI-08, written up in
  `SCIENTIFIC-CORRECTIONS.md` and measured in `BENCHMARKS.md`. `tests/numerical` carries the
  independent-reader checks: 94 passed.
- **`docs/dev/` folded from 24 files to 9** (7 commits) and `dev/notes/` and `dev/spikes/` deleted.
  The fold left ~60 citations in `tit/`, `tests/`, `desktop/`, `contracts/` and `TODO.md` naming
  paths that no longer existed — **a documentation consolidation is not finished when the documents
  are merged; it is finished when nothing still cites the merged-away name.** CX7 repointed them
  from the retired-paths table in `docs/dev/README.md`, and `git grep "docs/dev/"` now resolves to
  the nine live files everywhere outside that table.
- **The website pass** (6 commits) — every v3 tool has a wiki page, and the 16 screenshots come from
  `desktop/tests/e2e/real/docs-shots.spec.ts` against the real container, so they are reproducible.
  Gotcha: **`docs-shots.spec.ts` rewrites all 16 PNGs on every run, at this machine's device scale**
  (~2.5× the committed byte size). Running the spec to check it passes dirties the tree; revert the
  images unless you meant to re-shoot the site.
- **Three documented ways to run v3** (`f22115e5`, `a5141503`, `a30546b2`) — `tit/launch.py`,
  `tit/cli.py`, `ti-toolbox.sh` and the `scripts/dev.ts` messages, with `browser-mode.spec.ts`
  driving the UI with no Electron bridge. 387 container tests cover jobs, kernels, server and launch.

Two contract-level staleness fixes fell out of the gate rather than out of a program.
`ARCHITECTURE.md` §7.4 still specified `pages/_shared/run/Receipt` in a `PageLayout` `receipt`
slot — removed 2026-09-06, recorded in `DESIGN.md` §4.8, and never propagated to the contract or to
`DECISIONS.md`. **A reversal recorded in one document is not recorded.** §7.4 now describes the two
renderings that ship and `DECISIONS.md` carries the tombstone. And `docs/_data/nav.yml` still called
the rewritten launcher page "Bash/CLI Usage".

The gate's own finding: **the mock e2e suite is flaky at about 1 test in 325, and it is a different
test each run** — `pipeline-ux` once, `page-memory` the next — each passing standalone and in its own
file. Both are 5 s expect timeouts in a four-minute serial run, not product defects. Do not chase the
name of the test; the pattern is the finding.

---

## Pre-v3 backend defect reports (2026-08), rechecked 2026-09-07

A code-reading pass filed three defects against the PyQt build. The Qt tabs are gone; these are what
survives of it, verified against the current source.

1. **The Analyzer's Field selector was a dead control** — the GUI wrote `"field"` into the config and
   nothing read it, so every analysis ran on the default field. **Fixed:** `Analyzer.__init__` and
   `run_group_analysis` both take `field` and pass it to `select_field_file`.
2. **Ex-search keys its output directory on the run name alone.** The GUI's overwrite check looked at
   `ex-search/{roi}_{net}`, which the backend never writes. The check is gone with the GUI; the
   backend behaviour is unchanged and is now stated in `ARCHITECTURE.md` §8 — a second run under the
   same `run_name` overwrites the first in place, so a run name must carry the ROI when more than one
   ROI is queued against one net.
3. **`mex` "force left/right symmetry" still raises `ValueError` for realistically-named leadfields.**
   `_infer_symmetry_eeg_csv` does `name.removesuffix(".hdf5").removesuffix("_leadfield")`, which is a
   no-op for SimNIBS's own `<sid>_leadfield_<net>.hdf5` shape (the net comes *after* `_leadfield_`),
   so the canonical lookup misses and the fallback path does not exist. `tit/opt/leadfield.py`'s
   `list_leadfields` already has the right logic — split on `"_leadfield_"` first. **Still open**,
   verified in `tit/opt/mex/mex.py:118-128`.
