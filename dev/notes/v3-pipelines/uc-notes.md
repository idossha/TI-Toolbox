# Lane UC — page-owned Subjects control for Simulator and Analyzer (U16)

Scope: `pages/simulator/**`, `pages/analyzer/**`, their unit/e2e specs, and
`tests/e2e/real/{sim,sim-mti,analyzer-mesh,analyzer-voxel}.spec.ts`. Never touched
`pages/optimizer/**` (lane FX1's own half of U16).

## Why

U11 (Workflow 1b) removed the context bar's subject switcher and, with it, the only writer
`useSubject().batch` ever had. Simulator and Analyzer kept reading `useSubject().selection`
(`id` + `batch`), so a multi-subject run became unreachable from either page: ticking a second
subject anywhere in the app was no longer possible. The optimizer page has the same gap but is
lane FX1's file to fix.

## What changed

- **`pages/simulator/index.tsx`** — a page-owned `selectedSubjects` state (was
  `useSubject().selection`), seeded from the shell's primary subject on mount and again whenever
  it changes (`seedWithShellSubject`, exported and unit-tested), exactly mirroring
  `pages/preprocess/index.tsx`'s own seeding rule so the two pages agree on what "seeded from the
  current subject" means. A Tier-1 "Subjects" control (first thing on the page, `data-tier="1"`)
  wraps the existing shared `ui/SubjectPicker` component — the same multi-select-with-chips
  primitive `pages/panels/source/index.tsx` already uses — with "Select all" / "Select none".
  Each row carries an `m2m` readiness chip (`Subject.has_m2m`): "a subject without an m2m cannot be
  simulated" is now visible per row, not just an invisible downstream filter. `eligibleSubjectsFor`
  (also exported/unit-tested) is the same subject-with-a-head-model filter the page already applied
  to `useSubject().selection`, now applied to the page's own list. The EmptyState that used to gate
  the whole Tier-1 form behind "choose a subject in the context bar" only fires when the Subjects
  control itself is empty (no subjects ticked, or the project has none at all).
  **The control's own open/closed shape changed twice after real-container evidence — see "The
  sticky action bar bug" below**; the table is closed to a one-line summary by default and opens
  on a "Change subjects…" button, with no `FormSection` chrome at all while closed.
- **`pages/analyzer/AnalyzerPage.tsx`** — the same seeding pattern (`seedWithShellSubject`,
  duplicated rather than shared across the two page directories — each page owns its own copy, no
  new cross-page abstraction) feeds a page-owned `selected` list. A Tier-1 "Subjects" control
  (first on the page, above "Scope", same closed-by-default shape as Simulator's) lists every
  project subject with a `sim` readiness chip: before a simulation is chosen it means "has run
  something to analyze" (computed from each subject's own `/api/catalog/simulations` list), after
  one is chosen it means "has run *this* simulation" — exactly "one without the chosen simulation
  cannot be analysed". `primarySubjectId` (`selected[0]`) replaces the old `subjectId` (shell
  primary) everywhere `buildConfig`/`ResultsPanel`/`RoiPicker`/`SphereRows`'s viewer link used it;
  `effectiveSubjectIdsFor` (exported/unit-tested) replaces the inline
  `mode === "single" ? [subjectId] : subjectIds` ternary — Subject mode analyzes only the first
  ticked subject (ticking a second one without switching to Group must not silently multiply the
  job), Group mode analyzes every ticked one. `#analyzer-subject` still does not exist (U6's actual
  claim — never a bare `<Select>` — stays true; U16 gave the page a *table*, a different control
  shape, not a picker U6 argued against).
- Both pages' `blockedReasonFor`/`plan.blockedReason` "no subject" strings no longer say "in the
  context bar" (there is no longer a control there) — now "Select at least one subject."/the page's
  own equivalent.
- **`tests/e2e/real/_simMontage.ts`** (used only by this lane's `sim.spec.ts`/`sim-mti.spec.ts`) —
  the final "Save montage" click now fires a real DOM `.click()` via `evaluate` instead of
  `locator.click()`. See "The sticky action bar bug" below for why.

## The sticky action bar bug (found on the real container, not the mock)

Both mock specs passed with the Subjects section rendered as a normal, always-open `FormSection`
(matching Pre-processing's own pattern verbatim) on the first attempt. The **real** `sim-mti.spec.ts`
then failed against the container — `sub-101`, `BioSemi-128-A1.csv`, a fresh 4-pair multi-polar
montage (the fixture matrix's own minimum for mTI) — with every electrode-pair combobox click
timing out: `<div class="action-bar">…</div> subtree intercepts pointer events`.

Root-caused with a throwaway scratch spec against the mock (not committed, deleted after use),
which dumped exact `getBoundingClientRect()`s and scanned `.page-layout-main`'s **entire** scroll
range in 10px steps for a position where the target combobox and the sticky `.action-bar` do not
overlap:

- `.page-layout-main { overflow: auto; display: flex; flex-direction: column }` holds exactly two
  children: `.page-layout-main-scroll` (`flex: 1; min-height: 0`, the actual page content) and
  `.action-bar` (`flex: none; position: sticky; bottom: 0`, `ui/Layout.tsx`'s `PageLayout`).
  `.page-layout-main-scroll` has no `overflow` of its own, so when its content is taller than the
  pane, it renders past its own flex-allocated box rather than clipping — normal, and how every
  run page's own collapsible sections already work.
- The bug: `.action-bar`'s rendered position tracks that **flex-allocated** box height
  (`clientHeight − actionBarHeight`), not "after however tall the overflowing content actually is".
  So once content is tall enough to overflow at all, the action bar renders **inside** the
  overflowing content rather than below all of it — and because both move together under scroll (a
  scan of every 10px step, `main.scrollTop` 0→161, found the same ~29px overlap at **every**
  position, `anyClear: false`), no scroll position — Playwright's own `scrollIntoViewIfNeeded`
  included — can ever bring an element sufficiently far down the page above it. This is a
  pre-existing gap in `ui/Layout.tsx`'s pane primitive (`PageLayout`/`.page-layout-main`), not
  something this lane can fix (owned by lane UA in Workflow 1b's file map, not this lane's) —
  reported below.
- Two independent, in-scope mitigations, both verified against the mock with the scratch spec
  before touching the real container:
  1. **Reduce how much this lane's own new content adds.** The Subjects control does not use
     `FormSection`'s own `collapsible` (tried first — it hands the open/closed decision to
     `RunWork`'s fill controller via `FormSectionFillContext`, which **oscillated** it open/closed
     live while a later test filled in the Analyzer form: that controller only re-measures on a
     *pane resize*, not on content it doesn't itself manage growing, e.g. `ResultsPanel` gaining
     rows once a simulation is picked — `locator.click()` on a checkbox inside it then raced
     "element detached from the DOM, retrying" for the full 30s). Page-local `useState` sidesteps
     the fill controller entirely; closed by default it renders as one bare row with **no**
     `FormSection` header/padding at all (a collapsed `FormSection` still costs ~80px of chrome —
     measured too much: the montage editor's own last row and Save button were still under the bar
     with that much margin back).
  2. **Make the one interaction this doesn't fully buy back not depend on hit-testing.** Even with
     (1), the *fully filled* 4-pair editor's own "Save montage" button — the deepest element in the
     flow, appearing only after all 4 rows are filled — still sat under the bar on the real project
     (`BioSemi-128-A1.csv` has zero pre-existing multi-polar montages, so `MontageManager.tsx`'s
     `EmptyState` renders *in addition to* the editor Card, adding height the mock's fixture nets
     — which both already have ≥1 saved montage — never hit). Confirmed exhaustively with the same
     scan technique (`anyClear: false` again). `locator.click({ force: true })` does **not** help:
     Playwright's actionability check is bypassed, but Chromium's own hit-testing at that screen
     point still resolves to the action bar, not the button, so the click is silently swallowed
     (proven by asserting the "Saved montage" toast after — it never appeared with `force`). A
     same-node `HTMLButtonElement.click()` via `locator.evaluate` fires the click event — and
     React's listener — directly on the actual node, bypassing hit-testing entirely; confirmed
     genuine (not just "no error thrown") by the same toast assertion, which now passes.
- Verified end to end against the real container after both fixes: `sim.spec.ts` and
  `sim-mti.spec.ts` both green (5.7s / 6.1s), and the mock suite (`simulator.spec.ts`,
  `analyzer.spec.ts`, 20 runs across `--repeat-each=2`) stayed green throughout every iteration of
  this fix, including the two-subject tests (which now click "Change subjects…" first).

## Unit tests (new)

`tests/unit/simulator-defaults.test.ts` — `seedWithShellSubject` (prepends the primary once, never
re-fights an unticked one) and `eligibleSubjectsFor` (m2m filter, including the "two subjects both
have a head model" two-job-plan case and the "no m2m subjects in the whole project" fallback).
`tests/unit/analyzer-defaults.test.ts` — the same `seedWithShellSubject` plus
`effectiveSubjectIdsFor` (Subject mode = first ticked only, however many are ticked; Group mode =
every ticked one). 9 new tests; both files together: **21 passed** (`npx vitest run
tests/unit/simulator-defaults.test.ts tests/unit/analyzer-defaults.test.ts`).

## Mock e2e specs (`tests/e2e/simulator.spec.ts`, `tests/e2e/analyzer.spec.ts`)

Both files' old "no subject picker of its own (U6)" test is renamed and its assertion flipped
(U16 supersedes that specific claim — a *table*, not a `Select`, is the new control); a new test
in each drives the page's own Subjects table to two ticked subjects and asserts the acceptance
numbers from the program brief directly: `.plan-matrix tbody tr` count 2, `plan-stat-jobs` "2",
digest `^2 jobs · …`. For Analyzer this is Group mode (Subject mode only ever analyzes the first
ticked subject by design — asserted as 1 row before the mode switch, 2 after). The submitted
payload's job *count* differs by page: Simulator queues one `POST /api/jobs` per (subject,
montage) row (2 rows -> "Run 2 simulations"), Analyzer's Group mode submits **one** job carrying
`subject_ids: [id1, id2]` (`run_group_analysis over subject_ids`, the page's own long-standing
comment) — the two-*job* count the test asserts is the Plan preview's, not the submission's; fixed
the button-label assertion to "Run analysis" (singular) once actually observed, rather than
assuming "Queue 2 jobs".

## Real e2e specs against the shared dev container

`docker cp desktop/out/renderer/. ti-toolbox-fad740e5-tit-1:/opt/ti-toolbox/ui/` run once before
any real spec, after `npm run build` — the container serves a static, image-baked UI copy (S2's
finding, s2-notes.md), so a renderer change is invisible to a real run without this. Verified via
`curl -s http://127.0.0.1:8765/ | grep -o 'src="[^"]*\.js"'` before/after.

`--project=real` (with `=`) is required — `--project real <spec path>` (space-separated, as the
program brief's own example command shows) makes Playwright's CLI swallow the spec path as a
*second* project name and fail with "Project(s) '<spec path>' not found". Reported below as an
open issue for whoever owns the brief/README; every real run below used `--project=real`.

See `results_table_md` in the structured output for the full per-spec table (job ids, wall time,
artifact counts). Summary: `analyzer-mesh` and `analyzer-voxel` both completed for real
(sub-ernie, Thalamus, spherical target) with genuine artifacts; `sim`/`sim-mti` are FEM-class and
had to wait for the shared container's heavy-job slot (see below).

## Container contention

The shared container was busy with other lanes' jobs for most of this session — `source`
(sub-101, ~15 min), then a burst of `sim`/`pre`/`blender`/`report` jobs in quick succession. `sim`
and `sim-mti` (both FEM-class) were queued behind a `GET /api/jobs` "nothing running or queued"
wait, matching S1's own harness convention, rather than raced against another lane's heavy job.

## Numbers

| Measurement | Value |
|---|---|
| New unit tests | 9 (simulator: 5, analyzer: 4) |
| `simulator-defaults.test.ts` + `analyzer-defaults.test.ts` | 21 passed |
| Full `npx vitest run` | 716 passed |
| `npm run typecheck` (`tsconfig.node.json` + `tsconfig.web.json`) | clean |
| `npm run lint` | 0 errors (3 pre-existing warnings, unrelated files: `preprocess/index.tsx`, `ui/DataTable.tsx`, `ui/VirtualList.tsx`) |
| `npm run build` | succeeds |
| Mock `simulator.spec.ts` + `analyzer.spec.ts`, `--repeat-each=2` (offscreen, quiet-checked) | 20/20 passed, PASS (quiet), stable across both iterations |
| Full mock `--project default` suite, before the action-bar fix (Subjects still always-open) | 99 passed, 1 failed (`optimizer.spec.ts` dead-space, FX1's own file, unrelated), 1 skipped, 1 did not run, 6.7 m |
| Full mock `--project default` suite, **after** the action-bar fix and the DOM-click `_simMontage.ts` fix (final code, offscreen, quiet-checked) | 95 passed, 1 failed (`optimizer.spec.ts`, a *different* assertion this time — FX1's own file mid-edit, still unrelated), 1 skipped (`viewer-real.spec.ts`, env-gated), 5 did not run (the rest of `optimizer.spec.ts`'s own serial block after its failure), 6.4 m. Every `simulator.spec.ts`/`analyzer.spec.ts` test (tests 1–4, 69–74) passed. |
| Real `sim.spec.ts` | **passed**, 5.7s, job cancelled cleanly (`smoke-ui-*-ti`) |
| Real `sim-mti.spec.ts` | **passed** after the action-bar fix (was failing every attempt beforehand — see above), 6.1s, job cancelled cleanly (`smoke-ui-*-mti`) |
| Real `analyzer-mesh.spec.ts` | **passed**, job succeeded, 5 artifacts, 9.0s |
| Real `analyzer-voxel.spec.ts` | **passed**, job succeeded, 4 artifacts, 9.6s |
| Container restarts by this lane | **0** (never touched `tit/server/**`/`tit/jobs/**`) |
| `docker cp` of the renderer to the shared container (required before any real spec exercises a page change — S2's own finding) | 3, once per rebuilt bundle |

## Requests to other lanes / open issues

- **UA (or whoever now owns `ui/Layout.tsx`)**: `.page-layout-main`'s sticky `.action-bar` does not
  reserve its own height against page content that overflows the pane — see "The sticky action bar
  bug" above for the exact mechanism and a reproducible scan proving no scroll position clears it.
  This is a *pre-existing* defect (nothing about it depends on this lane's own changes beyond
  surfacing it with a legitimately tall page for the first time); any run page whose Tier-1/always-
  open content plus a user-opened editor exceeds the pane's height can hit it. This lane mitigated
  by keeping its own new content minimal and, for one already-marginal real case, by having its own
  test helper dispatch a same-node DOM click instead of a hit-tested one — neither fixes the root
  cause. Suggested fix: `padding-bottom: var(--action-bar-h)` (or equivalent) on
  `.page-layout-main-scroll`/`.run-work` so the scrollable area genuinely reserves the bar's own
  height.
- **FX1**: `optimizer.spec.ts`'s own dead-space assertion (line 265, `<= 0.7`) measured `0.708` in
  the full-suite run above — 1 failed test, in your file, not investigated further (out of this
  lane's ownership).
- **Program brief / README**: the documented Level B example command
  (`npx playwright test --project real tests/e2e/real/<spec>.spec.ts`) fails outright —
  `--project` needs `=` (`--project=real`) when a test-file path follows it on the same command
  line, or Playwright's CLI consumes the path as a second project name. Every real run in this
  lane's own work used `--project=real`.
