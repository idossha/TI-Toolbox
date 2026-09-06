# Lane JB — Jobs tables for the Simulator and the Analyzer

**Branch** `feature/v3-electron-gui` · **Date** 2026-09-06

## The ask

> "The simulator UI looks very very good, but there is a problem where it's hard to separate users,
> montages, modes in different jobs. In 2.5.0, within a job users could manipulate the subject, the
> mode, the montage, the current intensities, and so on. We need that capability. This is also true
> for the Analyzer — we need a list of jobs in a table that allows users flexibility in what they
> input to the job."

Ground truth read off `git show v2.5.0:tit/gui/simulator_tab.py` and `analyzer_tab.py`:

* the Simulator's **job cards** — subject · source (Montage/Flex/Freehand) · U/M · mA · net ·
  "N selected", with the job list the sum of the per-card cross-products, and a
  "This will run N simulation(s)" confirmation;
* the Analyzer's **Subject × Simulation pair table** — "+ Add Pair", "Quick Add" (every subject
  having a simulation), group vs single inferred from the row count, ROI/space options global.

What v3 had instead: a page-level subject SET fanned out across a montage list. Three subjects ×
two montages was six jobs and there was no way to say "ernie on F3_F4, 101 on the flex result".
The cross-product was the only thing the page could express.

## What the row owns now

### Simulator — `Subject · Source · EEG net · Montage · Pairs · Currents (mA) · actions`

One row is one job, is one `SimulationConfig` with exactly one `Montage`. The cells that mean
different things under different sources change **inside their column**:

| Source | EEG net cell | Montage cell | Pairs cell |
| --- | --- | --- | --- |
| Montage | the net's `Select` | that net's montages, `name · TI` / `name · mTI` + polarity chip | `E1–E2 · E3–E4` |
| Flex result | the placement (a mapped net, or `Optimised positions (XYZ)`) | that subject's flex runs | labels, or `N XYZ coordinates` |
| Free-hand | `own XYZ` | that subject's saved placements | `N XYZ coordinates` |

* **Subject** is a `SelectionPicker` (`mode="single"`) — blocked subjects are *listed with their
  reason* and unselectable, which is the subject grammar's J3 rule moved inside the row.
* **Currents** count follows the polarity (2 for TI, one per pair for mTI), reserved to 4 slots so
  the TI↔mTI switch moves nothing.
* **Actions**: duplicate (the "same job for another subject in one click" gesture), edit montage,
  remove row.
* `Add job for each ready subject` is 2.5.0's fan-out, kept as a button: it repeats the active row
  for every subject that can run it, skipping duplicates. Flex/free-hand rows do not fan out —
  those artifacts belong to one subject's derivatives.
* The page-level `SubjectsField` and the Montage/Flex/Free-hand **source tabs are gone**. The
  free-hand *editor* survives as its own collapsed section ("Free-hand placements"): authoring a
  placement and choosing one in a job row are two different acts, the same split the montage
  catalog already had.
* Global sections unchanged and still global: Electrodes, Conductivity, Output fields.
* The table **keeps its rows after a run** (2.5.0's cards did too — a queued batch is usually the
  thing you then tweak and run again).

### Analyzer — `Subject · Simulation · Space · Field · actions`

* `+ Add row`, `Quick add: every subject with "<simulation>"` (2.5.0's Quick Add — every subject
  that has *run* it, never a duplicate), duplicate, remove.
* `Combine into one group analysis` is a switch over the same rows: on, the rows are the cohort and
  one `run_group_analysis` job is submitted over `subject_ids`; off, each row is its own
  single-subject job. A cohort runs **one** simulation/space/field, so rows that disagree are
  refused outright with the reason on the button (`groupMismatchReason`) rather than silently
  resolved to the first row's answer.
* Space and Field moved *into* the row (they are per-job); Tissue, the coordinate space and the ROI
  (`RoiPicker` / `SphereRows`) stay global, as in 2.5.0.
* Page-level Subjects table, the Scope segment and the single Simulation combobox: gone.

## What still runs

Unchanged, deliberately: `planModelFrom` with the three source stages, one
`POST /api/jobs/groups` with `subject_configs`, one config per row carrying its own subject, and
the existing-outputs dialog. `isRunnableRow` is the single gate between a row being *shown* and
being *planned* — a half-filled row is visible but never reaches the plan.

The Analyzer's `planAnalyzerBatch` changed shape: it now takes `AnalyzerJobSpec[]`
(`{config, subjectIds}`), because since the rework a row names its own subject and one page-level
`subject_ids` would plan every config against every subject.

## Files

**Simulator** — `desktop/src/renderer/pages/simulator/`
`types.ts` (row model, `emptyRow`, `newRowId`, `isRunnableRow`, `SOURCE_OPTIONS`),
`MontageManager.tsx` (→ `JobsTable`, column resolver, montage editor, catalog delete),
`index.tsx` (page shell, `jobsSummary`, `jobSubjectsFrom`), `RunControls.tsx` (blocked wording),
`FlexTab.tsx` (reduced to the pure placement model), `FreehandTab.tsx` (author-only).

**Analyzer** — `desktop/src/renderer/pages/analyzer/`
`JobRows.tsx` (new), `AnalyzerPage.tsx`, `api.ts` (`AnalyzerJobSpec`, `newAnalysisTag`).

**Tests** — `desktop/tests/e2e/_jobs.ts` (new helper: rows and cells by `data-cell`, never by
combobox index), `simulator.spec.ts`, `simulator-table.spec.ts`, `analyzer.spec.ts`,
`batch.spec.ts`, `selection.spec.ts`, `scene-tabs.spec.ts`, `page-memory.spec.ts`,
`real/_simMontage.ts`, `real/{sim,sim-mti,montage-shape,flex-result-selection}.spec.ts`,
`tests/unit/{simulator-defaults,analyzer-defaults,freehand-session}.test.ts`.

Storage key for the resizable columns: `tit-montage-columns-v1` → **`tit-sim-jobs-columns-v1`**
(the columns are not the ones the old key stored).

## Gate

| Gate | Result |
| --- | --- |
| `pnpm run typecheck` | pass |
| `npx eslint src tests` | pass (only `scene/SceneCanvas.tsx`, lane NR's file, reports) |
| `npx vitest run` | 1039 passed, 0 failed |
| `pnpm run build` | pass |
| mock e2e: `simulator` (13) · `simulator-table` (5) · `analyzer` (4) · `batch` (10) · `selection` (7) · `scene-tabs` (2) | **all pass** |
| mock e2e: `controls-consistency` (4) · `page-memory` (11 of 13) | pass / see below |
| mock e2e: `layout` | 1 pre-existing failure, see below |
| real (`--project=real`, container `ti-toolbox-fad740e5-tit-1`, `/api/jobs` idle first) | **all pass** |

Real gate, run against the live container at `http://127.0.0.1:8765`:

| Spec | Result |
| --- | --- |
| `real/montage-shape` (TI 2-pair/2-current, mTI 4-pair/4-current wire shapes) | 3 passed |
| `real/flex-result-selection` (every real `sub-ernie` flex run resolves to electrodes) | passed |
| `real/sim` (TI montage: accepted → started → cancelled) | passed — `montage=smoke-ui-59257-ti outcome=cancelled` |
| `real/analyzer-mesh` (sub-ernie / Thalamus, spherical, mesh) | passed — `job d000a60d4f72433e state=succeeded artifacts=5`, cleanup diff empty |

Never two FEM simulations at once: `/api/jobs` was checked idle before starting, `sim` is the only
job that starts a runner and it is cancelled within its 120 s "started" budget.

### Pre-existing failures, not this lane's

* `layout.spec.ts › run pages — light at 1280x800` and `page-memory.spec.ts:360 / :394` all assert
  `scene-pane-tetravox-frame`. Lane NR deleted the embed in `d500b5a6` ("open scenes in the host
  Tetravox app; delete the embed, its store, its update channel") and these three specs still
  expect the iframe. Verified red at HEAD without this lane's changes. NR's files, NR's fix.
* `real/analyzer-{mesh,voxel}.spec.ts` were clicking an `alertdialog` button named
  "Overwrite and run"; the shared existing-outputs question (C3) has been a three-answer `dialog`
  for a while. Fixed here (`existing-outputs-replace`) since this lane was re-pointing them anyway.

Artifacts written: `tests/e2e/artifacts/jobs-table-sim.png`,
`tests/e2e/artifacts/jobs-table-analyzer.png`, `tests/e2e/artifacts/sim-plan-summary.png`.

## Proposed DESIGN §4.x

> ### 4.7 Jobs table
>
> A run page that submits **more than one job at a time** describes the run as a table in which
> **one row is one job**, and the row owns every input that differs between jobs. The Simulator's
> row is `Subject · Source · EEG net · Montage · Pairs · Currents`; the Analyzer's is
> `Subject · Simulation · Space · Field`.
>
> 1. **The row owns its subject.** A page with a jobs table has no page-level subject control. The
>    subject grammar (§3, J3) still applies, inside the cell: a subject that cannot run here is
>    *listed with its reason* and cannot be picked.
> 2. **A cell may change with the row, never the layout.** Column widths come from a resolver whose
>    total is the container by construction, so a row switching source (or polarity) changes what
>    is *inside* its cells and moves nothing anywhere else in the table.
> 3. **Incomplete is allowed.** A half-filled row is shown and is not planned. One predicate
>    (`isRunnableRow`) is the gate, and the disabled Run states the *table* being empty before it
>    states anything about subjects.
> 4. **Duplicate, not fan-out.** Repeating a job for another subject is one click on the row. The
>    cross-product is still available as an explicit button ("Add job for each ready subject",
>    "Quick add: every subject with X") — it is something the user asks for, never the only thing
>    the page can express.
> 5. **What is global stays global.** Properties of the *run* rather than of a job — electrode
>    geometry, conductivity, output fields, the analysis ROI — remain page-level sections.
> 6. **A group is a switch over the rows,** not a separate mode with its own selection: the rows
>    name the cohort, and rows that disagree about what a cohort job can only do once are refused
>    with the reason on the button.
> 7. **The table survives the run.** Submitting does not empty it.

## Open items

* **Lane collision, no data lost.** This lane and lane NR share one worktree, and NR's commits
  `5b14d581` / `b8ee1eea` swept up JB files that were mid-edit (`JobRows.tsx`,
  `simulator/index.tsx`, `AnalyzerPage.tsx`, `page-memory.spec.ts`, `real/_simMontage.ts`,
  `real/sim*.spec.ts`, `scene-tabs.spec.ts`). The content is correct and committed, just under
  NR's messages; `11418dbd` is this lane's own remainder. Worth a note in the program: two lanes in
  one worktree cannot both use `git add <their own files>` safely when the files overlap.
* **The free-hand editor now opens on a button**, not permanently. That is a design change forced
  by a measurement, and worth knowing: a permanently-rendered 4-row coordinate table made the
  section tall enough that the run shape's fill controller reached a *different* auto-open decision
  after a navigation away and back, which `page-memory.spec.ts` correctly reports as a page that
  did not come back as the user left it. A dialog would have been the tidier home, but a `Select`
  popover (z-index 60) is unclickable inside a `Dialog` (80/90) — the same known `ui/components.css`
  gap that keeps the montage editor an inline card.
* The Simulator's free-hand *authoring* section and the row's free-hand *picker* are two places one
  workflow lives. If free-hand placements become common, the row's picker should grow a
  "New placement…" entry that opens the same editor in a dialog.
* `currentValues("")` returned `[0, 1]` rather than the documented `[1, 1]` (`Number("")` is 0) —
  a red unit test that predated this lane. Fixed here: a blank cell is an *unset* current.
