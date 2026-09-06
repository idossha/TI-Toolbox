# Lane OJ — the Optimizer's jobs table

**Branch** `feature/v3-electron-gui` · **Date** 2026-09-06

## The ask

A screenshot of the Optimizer still showing the old page-level Subjects list ("No subjects
selected"), with:

> "create something similar logically to the Simulator and Analyzer: choose a subject, then an
> optimisation approach (Flex, Ex, mEx…) and configure each job exactly how they want, so users
> create a list of jobs and run them."

This is lane JB's ask (§4.7, "one row is one job") arriving at the third run page. What the
Optimizer had was the *shape of a PyQt tab*, carried through U7's merge: one page-level subject
set, one Method segment, one global TARGET / OBJECTIVE / ELECTRODES / SOLVER form, one run name.
Three subjects was three copies of the same search, and "flex on ernie's insula **and** ex on 101's
thalamus" could not be said at all.

Ground truth read off `git show v2.5.0:tit/gui/flex_search_tab.py` / `ex_search_tab.py`: 2.5.0's
"Global Parameters" box was **per tab**, which is per method — so nothing global is being taken
away here. There was never anything on this page that was a property of the *run* rather than of a
search.

## What the row owns now

### `Subject · Method · Net / leadfield · Goal · actions`, then the target line

| Cell | Flex family | Ex / mEx |
| --- | --- | --- |
| **Method** | `Flex` · `Flex adaptive` · `Flex Pareto` | `Ex` · `mEx` |
| **Net / leadfield** | the EEG net optimised positions are mapped onto, or `Optimised positions` | the subject's leadfields, each with its size; a net *without* one is listed as `<net> — no leadfield` and is unselectable |
| **Goal** | `mean` / `max` / `focality` / `focality_tf`; fixed to `focality` (disabled) for the two orchestrated methods | `—`, with the reason in its `title`: an exhaustive search ranks every montage by the ROI field and has no goal to choose |
| **line 2** | `Cortical · DK40 · lh.bankssts · avoid everything else · 2 pairs · 1 mA · ratio 1:1 · population 13 × 500 generations ≈ 6,500 solves` | `Saved · Thalamus_target · r3 mm · Subject · buckets: 4 · 2 mA total · 4 electrodes · 7 splits · 7 combinations` |

* **The method vocabulary is five, not three.** `flex_adaptive` / `flex_pareto` were a mode buried
  three controls inside a focality form, while being *separate job kinds on the wire*
  (`jobKindFor`) that queue a different number of solves. They are methods now, and
  `flexFormForMethod` derives `goal`/`focalityMode` from the method so the two cannot disagree —
  including in the row editor, where changing the Objective section's Goal away from `focality`
  moves the row back to plain `Flex` rather than being silently reverted.
* **The subject is a `SelectionPicker` inside the row** (J3), and its "why not" is per row: `no
  head model (m2m)` always, plus `no leadfield — create one first` when *that row* is Ex/mEx.
  Measured on Dataset 000: `101` is offered (it has an EEG10-10 leadfield), `MNI152` is refused for
  the leadfield, `102`/`test` for the head model.
* **The row editor is a dialog per method**, assembled from the page's own existing
  `FlexSections` / `ExSections` scoped to one row's form state — nothing was rewritten to fit the
  table, because those sections always took `{form, onChange}`. It also holds the row's `RoiPicker`
  (target **and** avoid ROI), its run name, and — for Ex/mEx — the `LeadfieldStrip`, which is
  finally able to say *whose* leadfield it means.
* **Fixed geometry**, the Simulator's grammar: a `<colgroup>` from `resolveOptColumnWidths` (whose
  total is the container by construction), `table-layout: fixed`, resizable header boundaries under
  `tit-opt-jobs-columns-v1`, and an active-row wash over both lines. Asserted: switching a row
  Flex→mEx moves no column, and the container never scrolls sideways.
* **The entry is 63.5 px** (34.5 + 29), inside the Analyzer's own asserted 56–64 band.
* **The 3-D pane follows the active row** — its atlas and regions via `onAtlasChange` /
  `onRegionsChange`, exactly as the Analyzer's does.

Deleted from the page: `SubjectsField`, the Method segment, the global run name, the global TARGET
section, and the global Objective/Electrodes/Solver/After-the-search/Current/Carriers sections.
Nothing replaced them: they are all per row now.

## What still runs

`POST /api/plan/{kind}` per job (the Simulator's one-plan-per-row shape), `planModelFrom`, the
existing-outputs dialog (C3), the disabled-Run grammar (§4.2 rule 8) and the one shared `RoiPicker`
— only their *scope* moved, from the page to the row.

**Plan grid**: per-subject rows × `Flex · Ex · mEx` count cells, via the Simulator's
`cellDetail="counts"` and a `stageFor` fed by a kind-per-job array built alongside the merge (so a
column is never guessed back out of an output directory).

**One Run click is one submission per job KIND.** `POST /api/jobs/groups` takes a single `kind`
(`tit/jobs/plans.py::GROUP_KINDS`), so a table holding a Flex row and an Ex row cannot be one
request without a server change. The page does not pretend otherwise — two groups, both named in
the toast ("Queued 3 searches in 2 groups (ex, flex)"), and asserted as such. Within one kind it is
still exactly one request, with one `subject_configs` entry per job carrying its own subject.

The disabled sentence can now name *which* row: `Job 1: Fill in all eight electrode buckets.`

## Files

**Source** — `desktop/src/renderer/pages/optimizer/`
`rows.ts` (new: the row model, the method vocabulary, the readable summaries, the column
resolver), `plan.ts` (new, pure: `jobsForRow`, `rowFormReason`), `JobRows.tsx` (new: the table and
the per-method row editor), `index.tsx` (rewritten page shell), `optimizer.css` (the table, the
line-2 button, the row-editor dialog), `flexConfig.ts` / `exConfig.ts` (dead `flexSubmissions` /
`exSubmissions` removed — `jobsForRow` supersedes them).

**Tests** — `desktop/tests/e2e/_jobs.ts` (Optimizer section: `optRows`, `setOptCell`,
`openOptEditor`, …), `optimizer.spec.ts` (rewritten, 10 tests), `roi-idiom.spec.ts` (the picker is
in the row editor), `batch.spec.ts` + `selection.spec.ts` (the Optimizer moved from the
subject-taking list to the jobs-table list), `layout.spec.ts` (its own dead-space allowance, with
the reason), `real/{flex,ex}.spec.ts` (re-pointed at the table **and** at `/api/jobs/groups`, which
neither had been updated for), `tests/unit/optimizer-rows.test.ts` (new),
`tests/unit/optimizer-subjects.test.ts` (rewritten against `jobsForRow`).

**Mock** — `tests/mock-server/server.mjs`: `validateConfig` required `eeg_net` on ex/mEx configs.
Neither `ExConfig` nor `MExConfig` **has** that field (it is a `FlexConfig` mapping option,
`tit/opt/config.py`), so the rule refused every valid ex/mEx config. It went unnoticed while the
page validated only flex before submitting; the jobs table validates one config per kind, which is
what found it. Now `leadfield_hdf`, which both configs really do require.

## Gate

| Gate | Result |
| --- | --- |
| `pnpm run typecheck` | pass |
| `npx eslint src tests` | pass (0 errors; 3 warnings, all pre-existing library-compat notes in `preprocess/index.tsx` and `ui/DataTable.tsx`) |
| `npx vitest run` | **1110 passed**, 2 skipped, 0 failed |
| `pnpm run build` | pass |
| mock e2e `optimizer` | **10 / 10** |
| mock e2e `roi-idiom` (3) · `batch` (10) · `selection` (7) | **all pass** |
| mock e2e `layout` | 3 of 4 — the red is `preprocess light 1440x900`, see below |
| real `real/flex` | passed — `job 5743a6e40ab343ad` reached **running**, cancelled |
| real `real/ex` (2) | passed — `job 5024f70612684305` reached **running**, cancelled; subject options `["101","102 no head model (m2m)","ernie","MNI152 no leadfield — create one first","test no head model (m2m)"]` |

Real gate run against the live container at `http://127.0.0.1:8765` with `/api/jobs` verified idle
first, and verified idle again after (no job left running).

Config shapes recorded on the real payloads:

* flex — `config.roi.atlas_path = ["/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/segmentation/lh.ernie_DK40.annot"]`
  (the list form PR #130 introduced and F0 fixed the runner for), inside
  `subject_configs[0]`, `kind: "flex"`;
* ex — `kind: "ex"`, one `subject_configs` entry, `run_name: "smoke-ui-<run>-ex"`,
  `leadfield_hdf` under `sub-ernie` (3.0 GB `EEG10-10_UI_Jurak_2007`),
  `electrodes: {_type: "BucketElectrodes", e1_plus:["Fp1"], e1_minus:["Fp2"], e2_plus:["F3"], e2_minus:["F4"]}`,
  target `Subcortical · aparc.DKTatlas+aseg.mgz · Left-Hippocampus`.

Artifacts: `tests/e2e/artifacts/optimizer-jobs.png`, `optimizer-row-flex.png`,
`optimizer-row-ex.png`.

### Pre-existing failure, not this lane's

`layout.spec.ts › run pages — light at 1440x900` fails on **`preprocess` 64.5 %** against its own
`DEAD_SPACE_BY_PAGE` allowance of 0.62. The comment above that map records the measurement it was
set from ("59.8 % at 1440x900"), so that page has grown some room since; nothing in this lane
touches `pages/preprocess`. The Optimizer passes at both sizes with its own allowance (0.58,
measured 53.6 % @1280 and 51.4 % @1440, with the reason stated in the file exactly as
Pre-processing's and the Analyzer's are).

## Proposed DESIGN §4.7 amendment

§4.7 needs no new rule — the Optimizer is the third page to obey it. Two clauses are worth adding
to the existing ones, because this page is the first to hit them:

> 8. **A row may be a different KIND of job.** Where a page's rows submit as more than one job
>    kind, one Run is one submission *per kind* (`POST /api/jobs/groups` takes one `kind`), and the
>    page says so rather than implying a single atomic batch.
> 9. **A cell with nothing to decide says so.** A column that is meaningless for a row's method
>    prints a muted `—` with the reason in its title, never a disabled control that looks like a
>    choice the user has failed to make.

## Open items

* **Two column resolvers, one shape.** `simulator/MontageManager.tsx`'s `resolveColumnWidths` and
  `optimizer/rows.ts`'s `resolveOptColumnWidths` are the same algorithm over different column keys,
  as are the two `ColumnHandle`s and the two storage readers. They were not merged here because the
  Simulator's copy lives in a file another lane owns concurrently; a `useTableColumns(keys, mins,
  fractions, storageKey)` hook in `pages/_shared/` is the obvious follow-up, and would take the
  Analyzer's fixed-pixel colgroup with it.
* **Two target sentences.** `optimizerTargetLabel` and `analyzer/JobRows.tsx`'s
  `analyzerTargetLabel` word the three shared ROI modes identically on purpose. They differ in the
  modes only one page has (`saved` here, the combine clause there), which is why neither imports
  the other. A shared `roiLabel(value, opts)` in `pages/_shared/roi` is the right home the moment a
  third page needs one.
* **Every row carries all three form states.** A row holds `flex`, `ex` and `mex` at once rather
  than a discriminated union, so a user who tries Ex and returns to Flex has not lost their
  buckets. It is three small objects per row in page-session storage; if a table ever grows to
  dozens of rows this is the first thing to make lazy.
* **`FlexConfig.output_folder` is the run name.** A flex row's run name is written to
  `output_folder` (the field the runner resolves), while ex/mEx use `run_name`. Two names for one
  user-facing idea, inherited from the two config dataclasses — worth unifying server-side.
* **The `adaptive` / `pareto` config blocks are still provisional** (no `AdaptiveFocalityConfig` /
  `ParetoSweepConfig` in `contracts/schema.json`). Unchanged by this lane; see `PARITY.md`. Making
  them first-class methods in the UI raises the priority of formalising them.
