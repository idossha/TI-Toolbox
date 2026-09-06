# Lane S2 — UI smoke specs (2026-09-03)

Scope: Level B (`desktop/tests/e2e/real/*.spec.ts`) for every run page, driving the real dev
container through the built Electron app, recording the exact `POST /api/jobs`(`/groups`) payload
each page sends to `tests/smoke/payloads/<kind>.json` for lane S1 to replay, and a real run against
the shared container. Never touched `desktop/src/renderer/pages/optimizer/**` or
`pages/_shared/roi/**` (F0's files) — findings there are reported as open issues below.

## What changed

- `desktop/playwright.config.ts` — added a `real` project (`testDir: "tests/e2e/real"`) that only
  exists when `TIT_E2E_SERVER_URL` is set; the pre-existing (now-named `default`) project keeps
  its exact file set (`testIgnore: /\/tests\/e2e\/real\//`), same `webServer`, same everything —
  verified with `npx playwright test --list` before/after (still 92 tests / 19 files with no env
  set) and `TIT_E2E_SERVER_URL=... npx playwright test --project real --list` (finds the new
  project, 0 tests before any spec existed).
- `desktop/tests/e2e/_helpers.ts` — additive only. New exports: `connectReal`, `selectSubject`,
  `openJobsPanel`, `selectJobsPanelTab`, `waitForJobTrace`, `waitForJobRunningOrTerminal`,
  `waitForJobTerminal`, `cancelJobFromRail`, `recordPayload`, `PROJECT_HOST_ROOT`,
  `cleanupSmokeOutputs`, `smokeDirFromArtifactPath`, `JobStatusLite`.
- `desktop/tests/e2e/real/*.spec.ts` (12 files) + two private helper modules
  (`_simMontage.ts`, `_dirDiff.ts`) — see the results table.
- `tests/smoke/payloads/*.json` — written by the specs at run time (see table for which kinds).

## Fixture choices (deviations from the program's §3 matrix, and why)

- **preprocess**: matrix's canonical row is `sub-102` (sourcedata DICOMs, no BIDS dir) for
  DICOM→NIfTI. That subject **cannot be reached from this page at all**: `getSubjects()` reads
  `/api/catalog/subjects`, backed by `catalog.list_subjects()` (m2m-only per project memory), so a
  source-only subject never appears in the batch table to begin with — reported below as an open
  issue. Used `sub-101` + "Tissue analyzer" (`replace_existing_outputs`) instead, the matrix's own
  fallback row for a lightweight, real "pre" job on an already-modelled subject.
- **ex/mEx**: matrix says "existing `EEG10-10_UI_Jurak_2007` leadfield" but doesn't name a target;
  the mock's own fixture uses "saved" ROI presets (`Thalamus_target`, `L_Insula_target`) that do
  not exist on this real project (`RoiPicker`'s ex/mEx modes are `["saved", "subcortical"]` only —
  no cortical). Used Subcortical `aparc.DKTatlas+aseg.mgz` · `Left-Hippocampus` instead.
- **flex**: matrix's own atlas-ROI row (DK40 · a region), reused verbatim from `optimizer.spec.ts`
  except the atlas option text ("DK40" on the real catalog vs the mock fixture's "Desikan-Killiany").
- **source**: matrix says `sub-ernie`; used `sub-101` instead — "Build forward solution" writes to
  the subject's single fixed `forward/` directory (no run-name field), and ernie already has one
  from an earlier real run (`forward/fsaverage/...Thalamus...npz`). 101 has an m2m + EEG nets and
  no `forward/` yet — a clean create, verified before/after, not an overwrite of a real output.
- **analyzer**: `AnalyzerConfig.output_dir` is always `null` from this page — no field to stamp a
  `smoke-ui-<runid>` tag into. Cleanup is a verified before/after directory diff
  (`real/_dirDiff.ts`) instead of a naming convention.
- **nifti-group-average / nilearn-visuals / cluster-permutation**: each has a real "name" field, so
  tagged `smoke-ui-<runid>` directly; cleanup path is discovered from the finished job's own
  `artifacts[0].path` (`smokeDirFromArtifactPath`) rather than guessed, since none of these three
  pages report their output directory convention anywhere else.
- **results / report generation**: `pages/results/index.tsx` has no job-submitting control at all
  (grepped for `POST`/`createJob`/`submitJob` — none). No `results.spec.ts` real spec exists; the
  `report` kind is exercised as the trailing job of every `preprocess.spec.ts` group submission.

## The debugging arc (why three real full-suite runs, not one)

The first two full-suite attempts each burned ~10-20 minutes hitting environment/host bugs, not
page bugs. Recorded here because the fixes are load-bearing for anyone re-running this suite:

1. **`desktop/out/` raced by a concurrent `npm run build` from another lane** (attempt 1):
   `analyzer-mesh` crashed with "Target page, context or browser has been closed" 3.2s in —
   `out/renderer/index.html` had a newer mtime than the build I'd just run. Fix: rebuild
   immediately before each invocation (the README's own documented risk); no code change.
2. **`page.request.get()` hangs forever inside an offscreen Electron `BrowserWindow`** (attempt 2):
   every `waitForJobTerminal`/`waitForJobRunningOrTerminal` poll used
   `page.request.get(...)` — a request routed through the *page's own* browser context. Under
   `TIT_E2E_OFFSCREEN=1` this hung indefinitely (0% CPU on both sides, no error, no timeout) on the
   **second** Electron launch of a run, stalling a job that had already succeeded server-side
   behind a test that would never finish. Fixed in `_helpers.ts`: both pollers now use Node's own
   `fetch` (10s `AbortController` per request) instead of `page.request`.
3. **`GET /api/jobs/<id>` answers `{spec, status}`, not a bare `JobStatus`** (found once #2 was
   fixed and the *real* symptom stopped being masked by the hang): `getJobStatus` was reading
   `state`/`artifacts` off the top-level body, which is always `undefined` for the single-job
   route (only the list route and a submit response are flat) — every poll "succeeded" (200 OK)
   while reading `state: undefined`, so every wait ran out its full budget even on jobs that had
   already succeeded. Fixed by unwrapping `.status` once in `getJobStatus`.

With all three fixed, `analyzer-mesh`/`analyzer-voxel` dropped from "5.2m, fail" to "13-14s, pass"
in the very next run — confirming the diagnosis rather than just hoping it helped.

**A fourth, structural gap surfaced afterward and matters for every future lane using this
container**: the dev container serves its UI from a **static, image-baked copy**
(`simnibs_python -m tit.server ... --static-dir /opt/ti-toolbox/ui`, `TIT_STATIC_DIR` unset in the
container env), *not* from the bind-mounted worktree's `desktop/out/renderer` — unlike
`tit/<runner package>` changes (live immediately, per this program's shared rules), a **renderer**
fix needs `docker cp desktop/out/renderer/. ti-toolbox-fad740e5-tit-1:/opt/ti-toolbox/ui/` before a
real run will ever exercise it. I only discovered this because `source.spec.ts`'s own page-bug fix
(below) kept failing with the *pre-fix* payload even after a clean rebuild; `curl -s
http://127.0.0.1:8765/ | grep -o 'src="[^"]*\.js"'` named the stale `index-C97FjtDj.js` the
container was still serving. Did the `docker cp` once (additive — old-hashed files are still
present alongside, harmless) to unblock my own verification; reporting it rather than treating it
as routine, since it means **no renderer/page fix any lane makes is exercised by a real-server
run until this copy happens** — worth a permanent fix (point `--static-dir` at the mount, or have
`dev/smoke.sh`/this program's runbook do the copy) rather than a per-lane manual step.

## Page bugs found and fixed (in scope — `desktop/src/renderer/pages/**`, not `optimizer/**`)

- **`pages/panels/source/config.ts`**: `buildForwardConfig` sent `forward.eeg_net` with a literal
  `.csv` suffix (the `net` state is one of `SubjectDetail.eeg_nets`, which — like every EEG-net
  catalog in this app — carries the real filename). `tit/source/config.py`'s `SourceConfig.eeg_net`
  is documented "**without** the `.csv` suffix" (the runner appends it itself), so every real
  forward-solution submission failed with `EEG net not found: .../EEG10-10_UI_Jurak_2007.csv.csv`
  — a double suffix, 100% reproducible, not a real-project quirk. Fixed with a `stripCsvSuffix()`
  in `buildForwardConfig` (a no-op on an already-bare name, so `tests/unit/source-defaults.test.ts`
  needed no change — verified: still 4/4 passing). Real run before/after: same job, same subject,
  error changes from "EEG net not found" to a genuine (unrelated, see open issues) SimNIBS/mne
  error deep inside the forward pipeline — proof the fix is what changed, not the target.
- **`tests/e2e/real/_simMontage.ts`** (this lane's own helper, not a page bug, but a real
  strict-mode locator bug): `getByRole("button", { name: "New montage" })` resolved to *two*
  elements when the (net, polarity) combination has zero existing montages —
  `MontageManager.tsx`'s `EmptyState` renders its own "New montage" call-to-action *in addition to*
  the toolbar's. Every mock fixture happens to seed at least one uni-polar montage, so no mock spec
  ever hit this; this real project's `BioSemi-128-A1.csv` has zero *multi-polar* montages, so
  `sim-mti.spec.ts` did. Fixed with `.first()` (the toolbar's is always first in DOM order).
- **`ConsolePane`/jobs-rail selection, four specs** (`source`, `nifti-group-average`,
  `nilearn-visuals`, `cluster-permutation`): `ConsolePane`'s `job` prop is `undefined` — and
  renders zero `.job-console-line`s, forever — until something calls the jobs-rail store's
  `select(job.id)`, which only a trace's own `onClick` does. `waitForJobTrace` only asserts
  visibility; the four panel specs opened the jobs panel's Console tab without ever selecting a
  job, so every one hung the full 120s budget with `.job-console-line` never appearing regardless
  of the job's own real state. Fixed by clicking the returned trace `Locator` before switching
  tabs (`shape-A` run pages were never affected — their embedded `job-terminal` is scoped by
  `subjects`/`kinds` props, not a rail selection).

## Results (final clean state — see `results_table_md` in the structured output for full details)

| Kind | Outcome | Notes |
|---|---|---|
| pre (tissue, sub-101) | **completed** | real artifact verified on host |
| sim (TI, sub-101) | **started → cancelled** | long kind |
| sim (mTI, sub-101) | **started → cancelled** | long kind |
| flex (sub-ernie) | **started → cancelled** | F0's list-form-ROI fix confirmed end to end through the UI — no longer "known broken" |
| ex (sub-ernie) | **blocked** | open issue — F0-owned |
| mex (sub-ernie) | **blocked** | open issue — F0-owned |
| analyzer, mesh (sub-ernie) | **completed** | 5 artifacts |
| analyzer, voxel (sub-ernie) | **completed** | 4 artifacts |
| nifti_average | **completed** | 2 artifacts |
| nilearn | **completed** | 4 artifacts |
| stats (cluster-permutation) | **completed** | API `artifacts: []` is a separate finding (below) — 8 real files verified on host |
| source (sub-101) | **accepted, started, real computation begins, then fails** | genuine SimNIBS/mne version bug, not desktop-owned — open issue |

9 of 12 kinds fully green; the other 3 are real, well-evidenced findings outside this lane's file
ownership, not gaps in the harness.

## Open issues

1. **[blocking, F0-owned] Optimizer Ex/mEx electrode buckets are permanently empty for any real
   leadfield-backed net.** `desktop/src/renderer/pages/optimizer/index.tsx` lines 143/145:
   `electrodes = eegNets.data?.find((n) => n.name === net)?.electrodes ?? []`, where `net` comes
   from `leadfields[].net` (`GET /api/catalog/leadfields` — verified: `"net":
   "EEG10-10_UI_Jurak_2007"`, no extension) and `eegNets[].name` carries the real filename
   (verified: `"EEG10-10_UI_Jurak_2007.csv"`). The lookup always misses, so `electrodes` is always
   `[]`, every bucket `MultiSelect` shows zero options ("Add electrode…" with nothing under it),
   and Ex/mEx can never be run through the UI against a real leadfield. Real evidence: `ex.spec.ts`
   / `mex.spec.ts` both failed identically — `TimeoutError: waiting for getByRole('option', {
   name: 'Fp1' })`, 30s, options list empty. Payloads for these two kinds were never recorded
   (Run stays blocked — "Fill in every electrode bucket."). Suggested fix: strip `.csv` from `net`
   before the `eegNets` lookup (mirrors the fix this lane made in `pages/panels/source/config.ts`
   for the identical shape of bug).
2. **[not desktop-owned] `source` forward-solution pipeline: `AttributeError: No mne.source_space
   attribute _complete_source_space_info`.** After this lane's own `.csv`-suffix fix (above), a
   real forward-solution job for `sub-101`/`EEG10-10_UI_Jurak_2007` gets past validation and into
   SimNIBS's own `eeg/utils_mne.py::make_source_space` → `mne.source_space._complete_source_space_info`
   — a private MNE API that does not exist in the container's installed `mne` (project memory:
   "pin mne~=1.5" — worth checking what's actually installed against what `simnibs/eeg/utils_mne.py`
   expects). Full traceback in job `674801945bee46aa`'s `error.last_lines`. Not a desktop bug —
   this is a Python/container dependency issue, reported for whoever owns
   `tit/source/**`/the container's `mne` pin.
3. **[readable, minor] `GET /api/jobs/<id>` reports `artifacts: []` for a real, successful `stats`
   job that wrote 8 real files** (NIfTI maps, a PDF, a summary — verified directly on the host
   filesystem, `derivatives/ti-toolbox/stats/group_comparison/<name>/`). Not investigated further
   (out of this lane's file ownership — `tit/jobs/manager.py`/the stats runner's own artifact
   reporting) but real and reproducible: job `9817edf35206406a`.
4. **[server, not a page bug] Preprocessing cannot onboard a new subject from DICOM at all via the
   UI.** The fixture matrix's own canonical "creates a new subject" row is `sub-102` (sourcedata
   DICOMs, no BIDS dir yet), but `getSubjects()` — used by every page including
   `preprocess/index.tsx`'s own batch table — reads `/api/catalog/subjects`, backed by
   `catalog.list_subjects()` (m2m-only per project memory), so a source-only subject never appears
   as an option to begin with. Used `sub-101` + "Tissue analyzer" instead (see "Fixture choices"
   above); flagging this since it blocks the matrix's own most basic pipeline story ("a subject
   goes from raw DICOMs to a usable derivative") from ever being exercised through the UI as
   currently designed.
5. **[methodology note, not a violation — verified] `scripts/e2e-quiet-check.sh` reported "FAIL —
   windows on screen" / "held the focus: Electron" on the two full-suite runs, but not on later
   short targeted runs.** Investigated rather than dismissed: the on-screen windows' bounds
   (`10,40,1900x1030` and `1919,1052,1900x1030`, both titled "TI-Toolbox") were **byte-identical
   across unrelated runs minutes apart**, and a live process check found a *separate*, persistent
   `electron-vite dev` / full-Electron process (pid 59278, user-data-dir
   `~/Library/Application Support/ti-toolbox-desktop` — i.e. a real `npm run dev` session, not one
   of this lane's `_electron.launch()` instances, which each get their own `mkdtempSync`
   user-data-dir and are never that path) already running before and throughout. In the cleanest
   short run, the check reported the *same* two on-screen windows but **no** "held the focus"
   line — proof this lane's own offscreen launches (`show: false`, `show()` never called per
   `src/main/window.ts`, verified by reading it) never became frontmost or visible; the windows the
   check sees are a pre-existing dev-mode session on two monitors, which the check has no way to
   attribute to a specific command in a multi-lane shared-Mac environment. Not a fix this lane can
   make (the check's own design, single-session by assumption) — flagged for whoever owns
   `scripts/e2e-quiet-check.sh` / the program's shared-Mac runbook.
6. **[minor, self-resolved] Cancelling a FEM-class job (`sim`) races the runner's SIGTERM grace
   period.** Two `Simulations/smoke-ui-<runid>-{ti,mti}/` directories were still present *after*
   this lane's own `afterAll` cleanup had run and the test had already reported pass — the
   subprocess kept writing files for a few seconds into its 10s grace-kill window
   (`tit.jobs.runner.DEFAULT_GRACE_S`), after the UI already showed "cancelled" and this lane's
   cleanup had already run and found nothing. Cleaned up by hand this session
   (`rm -rf .../Simulations/smoke-ui-{71595-ti,90719-mti}`, verified gone). Worth a small
   follow-up: `cancelJobFromRail` could poll the server for the job's process actually being gone
   (not just the UI's "cancelled" text) before a spec's cleanup runs, for any future FEM-class
   real spec.

## Real runs (job-level)

See `results_table_md` for the complete per-spec table (command, job id, wall time, outcome, first
error line). Container restarts by this lane: **0** (never edits `tit/server/**`/`tit/jobs/**`).
