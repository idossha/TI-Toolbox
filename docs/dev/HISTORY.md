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

**2026-09-07 — a mesh, a surface and a volume are three kinds.** *"Please distinguish between
NIfTI, mesh, and a surface — a mesh is a tetrahedral FEM, a surface is just a triangular 2-D
surface. Refer to the latest Tetravox release."* — on a screenshot of the Menu chipping
`lh.central`, `lh.pial` and `lh.white` as MESH beside the true `Head mesh (ernie)`. The rule behind
the chip was `path.endswith((".msh", ".gii"))`. One classifier now decides
(`tit/catalog.py::classify_view_file`, seven kinds, tested over sub-ernie's real 225-file listing);
the Anatomy branch is grouped by it; a surface expands to the `.annot`, morph and data-GIfTI files
that share its hemisphere — which SimNIBS had been writing all along and nothing had ever offered,
because with one word for two objects there was nowhere to put them. Emission is gated on the
`surfaces` capability (protocol 3, Tetravox 0.4.0, embed protocol range now **1–3**); an older
embed gets the rows disabled with the reason, never a sheet sent as a FEM mesh. A scene may no
longer span two subjects. Contract: `contracts/CHANGES.md` (2026-09-07), DESIGN §8.

---

## 2026-08-27 — build program and spikes

Build every screen in parallel against a frozen contract, backed by real `tit.server` endpoints,
ending in a real run on Dataset 000. Shipped `tit/server/routes/`, `contracts/openapi.yaml`, one
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

## 2026-09-07 — the Viewer keeps what you chose and what you saw

Maintainer, on the Menu's `Type / Subject / Simulation / Field / Space` card: *"please change the
menu such that there is subject and then it kind of like shows two little branches with the anatomy
and then there is a simulation section where they can choose the different simulations — they can
potentially choose multiple — and then they choose analysis output; and in each one the user should
be able to choose what input they want for each stage ... At the end they could choose to save it as
a JSON for future reproducibility. Also we should be integrating scene saving where users can
essentially save scenes — not only the input selection but also the scene for the user — and we
should be very opinionated about that and save it in the Tetravox [scene format]."*

**Two artefacts, not one.** The sentence asks for both a saved *selection* and a saved *scene*, and
the temptation is to make the second a superset of the first. They are kept apart because they age
differently. A **composition** (`compositions/<name>.json`) records ids — subject, space, the inputs
ticked — so reloading it re-resolves against a project that has since been re-run, and reports what
is missing rather than failing: *"show me the same thing, from the current data"*. A **scene**
(`scenes/<name>.tetravox.json`) is the embed's own `serialize` reply written verbatim, camera and
per-layer window included: *"show me exactly this picture again"*. Collapsing them would make one of
those two questions unanswerable.

Saving a scene is the embed's answer and never a re-derivation, because everything worth saving
about a scene is what changed *after* it loaded. `store.ts` had removed `serializeScene()` with the
note that "nothing on the v3 page has anywhere to put a Save scene affordance"; the Tetravox
sub-page now does, and `screenshot` comes with it — a list of names all shaped
`<subject>_<sim>_<field>_<date>` is a list nobody can choose from, so the thumbnail leads the row.
A screenshot that fails does not fail the save, and a "PNG" that decodes but lacks the signature is
dropped rather than written: this route puts bytes in someone's project.

**The tree.** `GET /api/viewer/tree` answers anatomy / simulations / analyses for one subject, from
the catalog and from what is on disk right now. Every node carries its size and an
`available`/`reason` pair, because a tree that offers a file which is not there moves the failure to
Open. The id is the container path — a composition saved today has to resolve against a project that
has gained and lost files, and the only thing that survives that is what the file is called. It
reads no voxels (`listdir` and `stat`), because it is redrawn as a person clicks. Space is honoured
in both directions: a subject-space scene is not offered the MNI copies, since two spaces in one
scene is a misregistration nobody asked for; meshes are offered in both, because there is no MNI
mesh and hiding them would hide a real option.

**The Menu is the tree now.** `Type / Subject / Simulation / Field / Space` is gone: a subject, a
space, and three branches of what that subject has. The tree owns no selection — a row is ticked
when its path is in the page's one editable list — so the branches and the list cannot disagree,
and Reset, reordering, presets and deep links needed no second mechanism. Ticking a *field* row is
the one tick that also moves the draft (it decides which layer the window chip describes); every
other tick is a free local edit, which is what keeps the Menu fast.

**And then the labels went away entirely.** Maintainer, on the Tetravox Layers panel: *"Please do
not change the name of the files that we load into the viewer. For example, `labeling.nii.gz` should
be `labeling.nii.gz` and not [Atlas]."* Every layer's `name` is now the file's basename, exactly as
on disk. The curated names explained a layer at the cost of naming nothing a person could find on
disk, grep a log for, or match against the list they had just composed — and the engine's
`LayerBase` has no description field, so the context is dropped rather than smuggled back into the
name. The labels survive only in the composition tree, where they label a *choice* and the filename
is beside them. Pinned across every `build_view` kind, including the `files` branch.

That makes the two label fixes below matter to the tree rather than to the panel, but they were
real either way and are worth recording:

Two label defects surfaced the moment forty rows were on screen at once, both older than the tree
and both visible in the viewer's own Layers list all along. `_scene_field_name` matched substrings,
so `L_Insula_TI_subject_hf_peak.nii.gz` — which contains "ti" twice — was answered `TI_max`, and a
simulation's TI_max, hf_peak and hf_sar volumes all rendered as "TI_max (volume)": three identical
rows. It now reads the basename's **last token**, and the loose hint chain is restricted to meshes,
which genuinely carry no trailing field token (that chain was also calling `final_tissues.nii.gz` a
TI_max layer, because "tissues" contains "ti"). Separately, a high-frequency simulation writes one
output per electrode pair, so two rows came out "magnE (volume)" and two 412 MB meshes came out
"Mesh mesh · magnE"; the pair number now disambiguates them, and a mesh with no tissue prefix is
"Head mesh" rather than the "Mesh mesh" stutter.

## 2026-09-07 — viewer defaults and resolve latency

Three screenshots from the maintainer, of the Viewer Menu and of the scene it handed to Tetravox:
*"there is still a lot of loading time once the user starts manipulating the input data ... it
launches the selected input, but for some reason it provides it with some very strange defaults ...
it would be much more reasonable to set more logical thresholds, for example 95 to 99.9 of the
electric field and so on, plus the sizing and the location of the scans can be improved."*

**Latency.** A resolve of `sub-101/L_Insula/TI_max` cost **16.4 s** cold and 4 ms warm. Two causes,
both in `tit/viewspec.py`. The module read every volume in the scene **twice** — once through
`_volume_stats` for the scene's concrete `Scale`, once through `_resolve_layer_percentile`'s
independent `get_fdata()` — and it cached the answer only in memory, so the whole cost was paid
again on every server process, which under `--reload` and on every app start is once per sitting.
The two paths are now one (`_percentiles_from_stats`; the old array read survives only for a window
outside the fixed percentile set, because a p90 answered with p95 would be wrong), the reads for one
scene run concurrently (`prefetch_volume_stats`), and the result is written to a sidecar under
`<project>/code/ti-toolbox/viewer/cache`, keyed by `(size, mtime_ns)`. First-ever resolve of a
simulation **16.4 s → 10.2 s**; every resolve after that, in this process or any later one,
**16.4 s → ~14 ms**. Nothing is sampled: a percentile from a subsample is a different number, and
the window it produces is what the reader sees.

Client-side the Menu asked on every keystroke with no debounce and nothing to cancel a superseded
request, and blanked the "what will open" card to *Resolving…* while it waited — so a resolve that
now takes 10 ms still looked like a reload. Now: 150 ms debounce, `AbortController` through React
Query's signal, and `keepPreviousData`, so the card keeps the previous list greyed instead of
emptying. The card also names the window before anything opens (`p95–p99.9 · 0.25–3.34 V/m`).

**Defaults.** Every number in the emitted scene was either a constant or the wrong statistic:

| | was | is |
|---|---|---|
| field overlay window | `[nz_lo, p99.9]` — `5.08e-09` V/m, i.e. every non-zero voxel | `[p95, p99.9]` |
| field threshold | none (`clamp`, `lo: null`) | `lo: p95`, `mode: "hide"` |
| T1 window | `[min, max]` = `0–3238` | `[p2, p98]` = `1–715` |
| 2D pane zoom | fixed `0.6` mm/px | fitted to the scene's bounding box |
| 3D camera | fixed 350 mm from world origin | fitted to the bounding box |
| crosshair | world `(0, 0, 0)` — a corner of the FOV | the field's peak voxel, or the ROI centre |
| GM mesh | hidden, under a layout that reserved it a 3D pane | visible |

The panes were never fitted because the engine fits only in `#onFirstDataset` and only when
`datasets.size === 1`; every scene this module writes carries four or five. `_fit_mm_per_px` and
`_fit_camera` are deliberate duplicates of the engine's own `fitMmPerPx`/`fitCamera`, because the
number the server sends becomes the pane's *fit reference* — the zero point the corner `ZOOM`
readout and `r` measure from. Bounding boxes come from each NIfTI's affine, never from its voxels.

Also added: a signed statistic map (`_tstat`, `_zmap`, `cohens_d`, `_diff`) is recognised and gets a
symmetric `±|v|p99` window on `coolwarm` rather than a heat ramp that would delete its negative half.

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

**Merged `origin/main` @ `b5eb63c3` (v2.5.0) into the branch** (merge commit `03156b69`), 60 commits
and the first reconsolidation since `0c0ef614`. What main brought, and what it cost:

- **`tit.calc` is now three envelope functions** — `get_TI_vectors`, `get_TI_avg`, `get_TI_dir` —
  taking a positional field list. `get_nTI_vectors` and the legacy `channels=` parameter are gone
  (`b19a1c26`, `ab92267a`, `cb822a17`, `d4706e5a`), and **mTI is always positional**: `electrode_pairs`
  two at a time, each pair its own carrier (`7a5ee2dd`). `Montage.channels` and `MExConfig.channels`
  no longer exist.
- **SCI-07 had to be restated on that model**, not merely re-applied. The physics from `1694c69f`
  survives — coherent within a carrier, incoherent across, the ½ once — but with the wiring fixed at
  the identity, the `channels=` argument, `channel_index_groups` and `_carrier_stack` were dead
  surface and were deleted. `DECISIONS.md` § 2026-09-07 records the amendment; the SCI-07 entry now
  says plainly that **no released version ever shipped the grouping** (added `ff823ce1`, removed
  `7a5ee2dd`, both inside the v2.5.0 pre-release window), so no user-visible number moves.
- **A merged accelerator can carry a defect the merge is silent about.** Main's numba mTI kernel
  (`65bd2355`) has its own scalar copy of the envelope, and it still had the cancelling
  `√(2(P+Q)) − √(2(P−Q))` form that SCI-08 fixed in `tit/calc.py`. Nothing conflicted, nothing failed:
  the two paths would simply have disagreed in the far-field tail. Found by grepping the merged tree
  for the formula, not by the gate.
- **`TI_normal` and fsaverage projection for mTI** (`c7cfd940`), **atlas resampling that compares the
  affine, not just the shape** (`333b4f96`), **multi-sphere ROI unions in the analyzer** (`90cc6ba8`),
  **symmetric ex/mex buckets with a zero-candidate failure** (`230fa10a`), **forked candidate
  evaluation with `n_jobs`** (`b66a5389`). The analyzer merges took both sides by hand: main's
  multi-sphere union with our SCI-05 world-space distance grid, main's affine-keyed resample cache
  with our cm³ volumes.
- **Wiki restructure is main's** (`2950830e`, `d6b0734c`, `4afb6099`, `db3e230b`): the mTI page is
  dissolved into simulator/analyzer/ex-search, the nav reordered, vocabulary unified around
  electrodes/channels/carriers, Botzanowski attributions corrected (`0f617236`). The v3 rewrite's
  content and screenshots were carried into that structure page by page. `README.md` is main's
  verbatim.
- **A contract change arrived through a merge, not through a design.** Removing `channels` from two
  config dataclasses and gaining `n_jobs`/`symmetric_bucket`/`symmetry_*` changed the generated
  schema, which the desktop app types against — the Optimizer still rendered a "Carrier wiring"
  select that could only send a rejected field.

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

### Addendum — the v2.5.0 merge, the contracts restructure, and CX8

`origin/main`'s v2.5.0 merged into the branch (`03156b69`), followed by the optimizer's
carrier-wiring removal, the release notes, the plugin refresh, the launcher structure and the
contracts restructure. CX8 gated all of it (`BENCHMARKS.md` § CX8 consolidation gate).

**A merge's damage is in what still calls the old thing, not in the diff.** Every real defect this
lane found was a caller the merge did not touch and therefore did not flag:

- **The packaged notebook example was broken for every user** (`2a276bb8`). v2.5.0 consolidated
  `tit.calc` to three list-argument functions; `examples/getting-started.ipynb` cell 3 still called
  `calc.get_TI_vectors(E1, E2)` and raised `ValueError: mTI requires an even number of fields >= 2,
  got 3` — on the toolbox's own headline computation, in the file a new user opens first. The real
  spec had been red for this since the merge and was read as flake. Its sting: `seed_example()`
  writes the file only when absent, so **fixing the source does not fix an existing project**
  (`RELEASE.md` §B).
- **The MCP plugin's version tool was renamed and its test was not** (`6325eb57`), and the plugin
  still offered `desktop/docker/`, deleted in `f8b8f4b6` (`5cbee155`).
- **`tit/source/fsaverage.py` said fsaverage projection is "standard TI only … exactly two
  carriers"** while three resolvers in the same file handle mTI and N carriers (`5cbee155`). The
  wiki was right and the code's own docstring was wrong — the opposite of the usual direction.
- **The container leg failed on `loader.sh` behaving correctly** (`1febfb15`): the container's
  `python3` is 3.10 and its 3.11 is `simnibs_python`, a name the host launcher does not probe.

**The twelve contract findings were not a budget; they were three bugs** (`f9f32745`,
`contracts/CHANGES.md` 2026-09-07). Opened that morning as `_KNOWN_FINDINGS`, each group turned out
to be wrong on a different side, and the most interesting was inert rather than merely stale:
`Overview*.reason` spelled nullability as OpenAPI **3.0**'s `nullable: true` inside a document whose
first line is `openapi: 3.1.0`, where the keyword does not exist. The contract was not disagreeing
with the server — **it was saying nothing, in valid-looking YAML.** `_KNOWN_FINDINGS` is now empty
and warnings are down 232 → 222.

The gate's own finding overturns CX7's: **the "1 test in 325, a different one each run" flake is
machine load.** See `BENCHMARKS.md` for the numbers — ten simultaneous failures at load average
63–74, zero on the same build at rest, and a density measurement that moved ten points between the
two. Do not chase the test name, and do not run anything beside a Playwright suite.

---

## 2026-09-07 (evening) — the Viewer became a tree, results grew panes, and a group of one stopped being nothing

An addendum to the three 2026-09-07 entries above, covering what landed after them and what the CX9
consolidation gate found.

**The Viewer's Menu is a composition tree.** The kind/simulation/space selectors are gone
(`509100ef`, `4d77d375`): the bar above the tree is the two facts every branch depends on — Subject
and Space — and everything else is a row you tick. Anatomy is grouped by *what a file is* rather
than by the directory it came out of, because a flat list put an 8 MB cortical sheet between a T1
and a 64 MB FEM volume with nothing to say they were three different kinds of thing (`bc643865`,
`86162e89`: a mesh is a tetrahedral FEM, a surface is a triangular sheet, and a surface reaches the
embed as a surface or not at all). Compositions and scenes save and reload (`a7338dcc`, `c8c0b678`),
and the subject rule is enforced: changing subject drops the other subject's rows *and says how
many*, because a scene spanning two people is two head-shaped brains roughly aligned with no way to
see that it is wrong.

**The gate's own finding: three e2e specs had been red since that change.** `smoke.spec.ts` and
three tests in `page-memory.spec.ts` were still driving `viewer-select-kind` /
`viewer-select-simulation`, testids that no longer exist anywhere in `src/renderer`. Nothing in the
app was wrong; the specs had simply not been carried across (`8b82ee43`, `611fb54f`). **A lane that
deletes a testid owns every spec that used it** — grep for it before the commit, not at the next
gate.

**Results has one shape per output kind** (`0a3d329c`, `cfbb349b`, `4f614684`), PDFs render as
images at their own aspect rather than being handed to Chromium's PDF viewer, and a report is an
*attachment of the job that produced it*, not a job of its own (`ac09534e`). Help popovers and the
preprocess flows landed (`1b4ee3b3`, `072f446e`), the jobs rail lost its Console and Report tabs for
a remembered 62/38 divider (`b92fc521`, `bf64bfe9`), and the System page arrived as a real-time
monitor pinned above Settings (`107b41eb`, `2244587f`, `48089caf`) — one rolling five-minute CPU and
memory chart, because the question people have is whether the two moved *together*.

**"Open in viewer" did not open.** Two maintainer reports with one cause: the deep link pre-filled
the Viewer's draft and left an Open button to press. `?open=1` now carries the intent and the Viewer
runs the same `open()` its own button runs (`e52a8c5f`). The same link is what the Jobs detail
pane's Artifacts tab uses: no `View`, no per-row `Open` (every artifact of a job is in the job's own
folder, so N buttons opened one place), one **Open folder** under the list, and **Open in Tetravox**
only on the rows a scene can draw — never on `roi_overlay.msh.opt`, the Gmsh options file that sits
beside the mesh with nothing in it to view.

**The trap in that change, worth remembering.** The auto-open effect first named `open` as a
dependency. `open` is a `useCallback` over `draft`, so the effect re-ran the moment it called
`setDraft` — and because the selection is a fresh object each time, it never converged: the page
re-rendered without pause and `setSub("tetravox")` never landed. It is held in a ref written from
its own effect. **An effect that sets state must not depend on a callback closed over that state.**

**SCI-09: a group of one returned a uniformly null result, not an error.** The pooled variance was
`(n-1) * np.var(x, ddof=1)`, which for a group of one subject is `0 * nan == nan` rather than the
`0` the pooled estimator calls for, so every voxel of a one-vs-many comparison came out `nan`. On
2.2.3–2.5.0 the `valid = se_diff > 0` guard swallowed it — `nan > 0` is `False` — and left
`t = 0, p = 1` everywhere: a complete, well-formed, uniformly null result set from a run that
*succeeded*. That is the worst shape a defect can take. The loud shape appeared only on this branch,
between `682cbfcf` (SCI-06, which made `_safe_t` IEEE-correct) and the fix `1b5ffdd7`.

**This closes a `RELEASE.md` follow-up that had been filed as a data question.** "The
`cluster-permutation` real job fails on Dataset 000 — every voxel is excluded as degenerate" was
recorded as *whether a 2-vs-1 contrast on those three images should be degenerate is a data
question, not a code one*. It was a code question. The generalisable lesson: **a guard that tests a
derived quantity for `> 0` takes its zero branch on `nan`** — `_safe_t` is the pattern to follow
instead, letting the IEEE value through and classifying it explicitly.

What re-running does *not* buy is significance. Three subjects admit `C(3,1) = 3` relabellings, so
the permutation null has three members — one of them the observation — and the floor on a cluster
p-value is `1/3` exhaustively, `2/4` under the shipped sampled estimator. **Zero significant
clusters from three subjects is the arithmetic of the design, not a defect**, and the
cluster-permutation wiki page now says so next to its data requirements, naming `C(6,3) = 20` (three
per group) as the first size at which `α = 0.05` is reachable at all.

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

### 2026-09-08 — Internal distribution and local validation

Continued the desktop implementation in the saved checkout. The generic build workflow now
separates export, internal image delivery and public publication; development version preparation
preserves authored notes and stable announcements. Both downloaded loaders bootstrap main in an
isolated cache, while cached management commands remain available offline. The public site marks
the desktop as upcoming and retains the full scientific-corrections guidance.

Validation exposed stale real-test selectors and missing Dataset 000 derivatives rather than
supporting the prior blanket real-green handoff. Real tests now require an explicit copied project
root, and the Results preview's repeated section spacing was corrected without relaxing its density
threshold. Host dependencies are declared by the test extra. Measurements and remaining real/image
gates are recorded in BENCHMARKS.md and RELEASE.md, not a new release-specific ledger.

### 2026-09-08 — Rebuild and colleague handoff verification

The internal preparation audit rebuilt the runtime rather than relying on the old green development
container. This exposed an actual NumPy dependency conflict: `bpy` installed into SimNIBS downgraded
NumPy, so montage rendering now uses the official Blender background runtime while scientific
preparation retains SimNIBS's NumPy. The prepared geometry preserves the existing subject mesh and
float64 coordinates. Architecture §10 and DECISIONS record the boundary and verified checkpoint cache.

Independent distribution review also found that a new loader could attach to a running old image,
and concurrent workflows could resolve to the same internal tag. Loaders now refuse the image
mismatch without disturbing jobs; image publication serializes by the resolved tag. Public release
metadata remains unchanged. Existing real tests gained precise Help-versus-control selectors and
safe cleanup guards; their measurements and outstanding reruns are in BENCHMARKS.

Real mEx planning also exposed a reference to the removed `MExConfig.channels` field; the planner
now uses the engine's actual topology and completes the real eight-electrode search. Actual montage
verification found a legacy-only mesh filename lookup, now routed through PathManager. Full-net
Blender scenes preserve the template's subdivision settings and require a larger memory reservation;
lightweight non-render exports retain their prior estimate. These are runtime/planning fixes, not
additional scientific-formula corrections.


### 2026-09-09 — Security boundaries and hosted CI follow-up

The first hosted analysis of the internal candidate reported a broad CodeQL delta, including
path-injection findings and existing baseline alerts. Independent review and failing-first
fixtures identified concrete containment and DOM-rendering defects; the fixes are pending
commit and scanner rerun, not an assertion that every alert is resolved.

The source now checks atlas, hemisphere, sidecar, ROI and catalog-content containment; rejects
subscriptions to unknown WebSocket jobs; and prevents job/lock metadata, notebooks and saved
views from following pre-existing outward symlinks. Storage writes use exclusive temporary
files and atomic replacement. The static-content empty-index case also rejects an outward
symlink. Documentation search now constructs DOM text/highlights without parsing user queries
or indexed labels as HTML. These changes protect storage/path boundaries, not numerical
algorithms, so they do not add a scientific-correction notice. Kernels remain deliberately
unsandboxed, and these checks do not promise protection against a concurrent malicious local
filesystem race; see ARCHITECTURE.md and DECISIONS.md for the trust boundary.

Hosted source CI exposed a test fixture whose mocked `isdir` collided with the actual checkout
path. The fixture was repaired and checked on host and container. Hosted desktop CI stopped
at an interactive system-service restart prompt before reaching e2e; the existing configuration
now explicitly requests noninteractive package setup and was accepted by the CircleCI CLI.
Neither repair turns the earlier failed jobs into passes. The earlier baked runtime completed
its real assertions with an inconclusive native monitor; it predates the security source fixes
and must not be presented as their rebuilt-image acceptance. Exact results and raw receipts
remain in BENCHMARKS.md; rebuild, packaging and hosted reruns remain in RELEASE.md.


The next clean local security image and wheel were built from `6571d06b` and exercised through
all three launcher routes. Baked tests exposed missing development-only contract fixtures;
the two affected cases passed after those fixtures were supplied, which does not erase the
initial failed run. Fresh mock assertions also passed, with native attribution still
inconclusive. Hosted CodeQL continued to gate the PR and further concrete pipeline/cache/view
containment defects were found. The first unsigned packaged launch then failed on a missing
`yaml` runtime dependency. Delivery remains not ready while those repairs, final artifact
identities and fresh acceptance are pending; the earlier successful real suite tested the
pre-security image. Main, Docker Hub and public notifications remain unchanged. See the
interim measurements in BENCHMARKS.md and current blockers in RELEASE.md.


The packaged dependency repair then passed an actual Browse → Start launch and owned-container
cleanup. That app contained uncommitted fixes and ran against the prior clean security image,
so it established the functional repair rather than final delivery acceptance. App visibility
checks passed; native attribution remained inconclusive despite later identification of some
short-lived processes as Spotlight. Final installer identities and acceptance remain pending;
there is no reason to rerun solely to chase shared-host monitor attribution.


The user then narrowed this round's closeout to consolidating the work on one logical
development branch in the saved checkout. The lead owns the branch rename and final commit/check
receipts. Main merge and Docker Hub publication are outside this round; no public release or
update notification is planned. Development testing continues through the existing Python
loader and localhost documentation preview commands in RELEASE.md. The source still requires
its matching final image and installer acceptance; consolidation is not a final-candidate claim.

### Development branch closeout — 2026-09-09

The maintainer ended this round at `develop`, before main merge or registry publication.
Additional path regressions covered pipeline documents, named views and statistics caches,
scene inputs/cache, montage resolution and catalog/ETA metadata. The packaged app's missing
YAML dependency was bundled into main and the artifact validator now rejects unresolved
external runtime dependencies. Actual packaged Browse/Start then succeeded. An obsolete
native-Python packaging spike was replaced with the current Docker-launcher startup contract,
including packaged identity and hidden-window assertions. The clean API documentation build
also exposed removed recon-all references; authored examples now use the current FastSurfer API.
Measurements and the unresolved hosted/security/native-monitor limits remain in BENCHMARKS
and RELEASE rather than being treated as a production approval.


### Release branch and current-product documentation — 2026-09-09

The maintainer requested normal product documentation for the impending main integration.
The local and GitHub `develop` branches were renamed to `release/3.0.0` without rewriting
history. Root CONTRIBUTING now owns production, topic, hotfix and release branch policy;
CodeQL and the existing path-scoped Python security scan include release branches and PR
targets. Documentation no longer sends readers to v2.5.0 or presents the interface as a
teaser. Installation owns the source/image pairing and its actual availability. The legacy
Apptainer recipe is identified as incompatible instead of offered as a working current setup.
The maintainer explicitly deferred Docker Hub publication until after manual testing.
No runtime, public version metadata, main merge or release publication changed in this pass.


### Project-only terminal launch — 2026-09-09

The maintainer reported the no-argument loader failure and requested the v2 interaction.
All four root/development Python/Bash launchers now ask only for the project and remember
the selected path. Advanced settings remain flags, including the v2 `--project-dir` alias.
Interactive startup without a pinned image identifies and reconnects to the selected
project's running session; explicit image requests retain the mismatch guard. The live
check attached to the maintainer's existing dev session without replacing it or opening
a browser. No image rebuild, registry publication or main merge was performed.


### Extension previews and viewer load lifetime — 2026-09-09

The maintainer requested the main run-page layout across computational extensions and a
selection-aware visual export preview. The extension plan now sits above the shared live
terminal; returned job IDs persist with the page session. Cortical, segmentation and
recorded montage selections were checked against actual subject data.

A reported viewer failure was no longer reproducible, but the supplied multi-volume case
showed a real blank-until-complete delay and misleading progress entries. Tetravox's engine
now adopts layers as datasets complete and reuses retained datasets when selections grow.
TI corrects progress identity/units and leaves successful layers visible on partial failure.
The new upstream commit was built and locally activated through the existing installer.
Docker Hub publication and production promotion remain deferred.

### 2026-09-09 — Form and Source touch-ups

Left-aligned form labels, stable participant Add actions, and moved fsaverage mapping from
Source into each simulation job’s settings. Terminal and notebook mapping remain supported.

Automatic Flex run folders now agree between preview and submission, and CSV/TSV interchange
supports Cluster permutation and NIfTI group averaging participant tables.

Form alignment clarification: left-aligned labels now share a column so all controls start
on the same vertical line.

Optimizer settings now pair the current-ratio controls and expose Solver and post-search
options without nested disclosures.

Results selection reopens a collapsed preview. Artifact-to-viewer regression coverage checks
the exact requested file in the returned scene. Sphere coordinate rows have vertical padding.

Simulation Results shows channel labels in Channels and montage images only in Figures,
avoiding duplicate pictures while preserving the figure lightbox.

### 2026-09-09 — Restore montage electrode overlays

Missing ImageMagick in the slim image caused a copied cap template to survive as if rendering
had succeeded. Restore ImageMagick and DejaVu fonts; render to a temporary file and publish
atomically. Empty or unrecognized electrode pairs fail explicitly. Repaired the two verified
blank ernie diagrams (stam and L_Insula) using saved configs without rerunning simulation.

Simulator montage selection now displays “No montages available” and disables the selector
when the selected net has no saved montages, instead of opening an empty dropdown.

Per-core load gauges display the percent sign beside each reading.

Local docs startup now resolves its own working directory, checks installed gems, explains
port conflicts without stopping other servers, and defaults to loopback with analytics off.
