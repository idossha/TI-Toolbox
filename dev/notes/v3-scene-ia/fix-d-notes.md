# Lane FIX-D — one control per idea, and the pages the program never reached

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, staged, stashed or pushed; no `Co-Authored-By` anywhere. Every Electron and
Playwright run below went through `TIT_E2E_OFFSCREEN=1 desktop/scripts/e2e-quiet-check.sh`, and
every one reported **PASS** — no window reached the maintainer's screen, no focus moved. Nothing
under `tit/` was touched, so the shared container's `--reload` was never at risk; `/api/health`
answered **200** before and after the session anyway. The container was never restarted or
recreated, port 5173 was never taken, and no process this lane did not start was killed.

`desktop/out/` is left on a **plain `npm run build`**, which is what the maintainer sees and what
the container serves.

This lane answers the maintainer's own two sentences: *"come up with a consistent schema/UI so
users are familiar with a consistent approach"* and *"position all UI elements in a way that makes
sense"*.

---

## 1. Headline numbers

| Defect | Measurement before | after |
|---|---|---|
| 1 — one idea, two controls | the Optimizer's ROI-type control had **no `.segmented` at all** (it was a `RadioGroup`); 6 `RadioGroup`s across the four files this lane owns | one idiom, **0** `RadioGroup`s left in `pages/{_shared/roi,analyzer,panels,jobs}` |
| 2a — a class that lies | Optimizer/Ex with the Subjects table closed: `.subject-picker-row` = **3**, `.roi-saved-row` = **0** | `.subject-picker-row` = **0**, `.roi-saved-row` = **3** |
| 2b — an option with no addressable identity | `[role="option"][data-option-value="lh:1"]` = **0** of 70 options | **1**, with `aria-label="L · bankssts"` |
| 3 — a fourth idiom | `participants-field` = **0** on all three row-list panels | **1** each, same header band / summary / table / "Why not" as `SubjectsField`; 18 unit tests, 4 of them a stylesheet-parity guard |
| 4 — the empty state | see the table below | see the table below |

**Defect 4, dead space on the state a user lands on** (nothing chosen, nothing run), `deadSpaceRatio`
over `[data-testid="shell-content"]` — the shared instrument, definition untouched:

| page | 1280×800 before | after | 1440×900 before | after |
|---|---|---|---|---|
| `panel-source` | 82.3 % | **41.7 %** | 84.4 % | **43.7 %** |
| `panel-cluster-permutation` | 74.4 % | **37.6 %** | 67.3 % | **35.6 %** |
| `panel-nifti-group-average` | 65.3 % | **41.5 %** | 65.2 % | **44.0 %** |
| `panel-nilearn-visuals` | 71.1 % | **38.8 %** | 72.7 % | **42.3 %** |
| `panel-subject-info` | 86.6 % | **18.9 %** | 85.8 % | **19.8 %** |
| `jobs` | 99.1 % | **12.5 %** | 99.4 % | **15.7 %** |

Limit 45 %, the same L5a number the run pages are held to. All 24 measurements (6 pages × 2 sizes ×
2 themes) pass; light and dark are **identical to 0.1 points** on every page — measured, not
assumed. Gate: `desktop/tests/e2e/panels-shape.spec.ts`, **6 passed (19.3 s)**.

---

## 2. Defect 1 — one idiom for a small exclusive choice

### 2.1 The reproduction, before the fix

`tests/e2e/roi-idiom.spec.ts`, first test, against the mock server:

```
✘ defect 1: the ROI type is the same control on the Optimizer and the Analyzer (5.1s)
  Error: expect(locator).toBeVisible() failed
  Locator: getByTestId('page-work').locator('.roi-picker').locator('.segmented').first()
  Error: element(s) not found
```

The Optimizer rendered "Cortical / Subcortical / Spherical" as a `RadioGroup`; the Analyzer renders
the identical choice as a `SegmentedControl` (`AnalyzerPage.tsx`'s `Field label="Region"`). Lane LAY
found it and could not fix it from its own files (`lay-notes.md` §8 item 2). Inside `RoiPicker`
itself the two idioms sat 40 px apart: a segment for the ROI type over a radio pair for the
Subject/MNI space, three times over (saved, spherical, subcortical panels).

### 2.2 The rule, and the failure it prevents

`desktop/DESIGN.md` §4.2 is now **nine** rules; rule 9:

> **One idiom per idea: a small exclusive choice is a `SegmentedControl`.** Two to four short,
> mutually exclusive options — a mode, a space, a scope, a target type — render as
> `SegmentedControl` with an `aria-label`, on every page, in one 28 px row. `RadioGroup` is for the
> case a segment cannot carry: five or more options, or options that each need a sentence of their
> own (`layout="cards"`).

`SegmentedControl` is the component that already fits: DESIGN.md §5 has described it as "one-of-N in
one 28 px row — Method, Scope, Space" since v3 began, and nothing new was invented. Both controls
render Radix roles `radiogroup`/`radio` with `aria-checked`, verified in
`node_modules/@radix-ui/react-toggle-group`, so **every existing spec and every screen reader sees
the same thing** — `optimizer.spec.ts`'s `getByRole("radio", {name: "Cortical"})`,
`real/ex.spec.ts`'s `"Subcortical"`, `real/scene-optimizer.spec.ts`'s `"Spherical"` all keep
working untouched. What changes is that a user learns the control once.

### 2.3 Applied

| file | choice | was → is |
|---|---|---|
| `pages/_shared/roi/RoiPicker.tsx` | ROI type (Saved/Cortical/Subcortical/Spherical) | `RadioGroup` → `SegmentedControl aria-label="ROI type"` |
| " | saved-ROI space (Subject/MNI) | → `aria-label="Coordinate space"` |
| " | spherical space | → `aria-label="Coordinate space"` |
| " | subcortical atlas space | → `aria-label="Atlas space"` |
| `pages/analyzer/SphereRows.tsx` | coordinate space | → `aria-label="Coordinate space"` (LAY's exact request) |
| `pages/panels/cluster-permutation/index.tsx` | Analysis type (Classification/Correlation) | → `aria-label="Analysis type"` |

`grep -rn RadioGroup src/renderer/pages/{_shared/roi,analyzer,panels,jobs}` now returns nothing but
two PARITY.md sentences, both updated to name the new control.

### 2.4 After

`roi-idiom.spec.ts` **3 passed**. The test is not "a segment exists somewhere": it asserts the
picker holds **no** `.radio-group` at all on either page, that the three option labels are the same
list in the same order on both, and that the Analyzer's whole work pane is free of the other idiom.
`layout.spec.ts` re-run afterwards: the Optimizer moved 41.6 → **39.6 %** dead and the Analyzer 40.8
→ **41.0 %**, both still inside L5a.

---

## 3. Defect 2a — a class that names what the row is

### 3.1 The reproduction

Optimizer, method Ex, subject `ernie`, the Subjects disclosure **closed** — so the page has no
subject row at all — printed by the spec itself:

```
FIXD-ROWS subject-picker-row=3 roi-saved-row=0 (subjects closed)
```

Three rows matching the subject-row class on a page showing no subjects: `RoiPicker`'s saved-ROI
list borrowed `.subject-picker-row` because the shape was the same. Lane SUB hit it as "6 rows for 5
subjects" on the real project and scoped its own helper around it (`sub-notes.md` §6.2), leaving the
class-borrowing for this file's owner.

### 3.2 The fix

`<label className="roi-saved-row">`, with the geometry in a new `pages/_shared/roi/roi.css` (the
`subjects.css` precedent — a control's own stylesheet, imported by the component). The rule, written
into that file:

> A class names what the row **is**; a row that borrows another control's class is a locator that
> lies.

### 3.3 After

```
FIXD-ROWS subject-picker-row=0 roi-saved-row=3 (subjects closed)
```

The assertion added is the one that would have caught it: with the disclosure closed
`.subject-picker-row` must be **0** anywhere on the page, and with it open the unscoped count must
agree with `_subjects.ts`'s scoped `subjectRows()` — 3 and 3.

---

## 4. Defect 2b — an option that carries its own identity

### 4.1 What was actually wrong (SCC's diagnosis corrected by measurement)

`scc-notes.md` §6.6 reports that `getByRole("option", {name: "L · bankssts"})` "never resolves
against the real server". Measured here, on the container, that is **not true**: the query resolves
and clicks. The diagnostic the spec printed:

```
FIXD-OPTIONS 70 [{"text":"\"L · bankssts\"","label":null,
                  "codes":[76,32,183,32,98,97,110,107,115,115,116,115]}, …]
```

70 options, and the label is exactly `L`, U+0020, **U+00B7**, U+0020, name — the same bytes
`RoiPicker.tsx` writes. So the accessible name was never broken.

The real defect is the one SCC's own sentence names ("the separator the component renders is not the
one a spec types") and it is a *design* gap, not a rendering bug: **a caller holding exactly what
the server gave it — a region's `hemi`, `id` and `name` — could not address the option**, because
reconstructing the accessible name meant also knowing which separator this component chose to print.
Both real scene specs work around it with a `/^L/` regex over the label
(`real/scene-optimizer.spec.ts:102`, `real/scene-analyzer.spec.ts:181`).

Reproduction, mock and container alike:

```
✘ defect 2b: every region option can be found by its accessible name
  Error: an option carries its own value
  expect(locator).toHaveCount(1) failed   Expected: 1  Received: 0
      locator: [role="option"][data-option-value="lh:1"]
```

### 4.2 The fix

`ui/Combobox.tsx` — every option rendered by `Combobox` **and** `MultiSelect` now carries
`aria-label` (the same string it shows, so no accessible name changes) and `data-option-value` (its
own value). A selected option leaves the list, so the chip carries `data-option-value` too and one
attribute addresses either state.

**This is a cross-lane edit** — `ui/**` is not this lane's — kept to four lines, additive, with the
failure written into the file beside it. Listed in §9.

### 4.3 After

`[role="option"][data-option-value="lh:1"]` = 1, `aria-label` = `L · bankssts`, and after selecting
it `[data-option-value="rh:1"]` still resolves. `optimizer.spec.ts`'s own `"L · bankssts"` click is
untouched and still passes.

---

## 5. Defect 3 — the same grammar over a row list

### 5.1 The scope decision, re-checked against the code

Lane SUB deliberately did not convert `nifti-group-average`, `cluster-permutation` and
`nilearn-visuals` to `SubjectsField` (`sub-notes.md` §4), and it is right: each row is a
`(subject, simulation, role)` tuple and **the same subject may legitimately appear twice** —
`cluster-permutation`'s `testType: "paired"` and `nifti-group-average`'s diff pairs are exactly that
design. Verified in the code: `SubjectRow`/`Row`/`Pair` are arrays with their own ids, and every
config builder maps rows, never a set.

What SUB left behind is the risk: three hand-rolled `<div style={{display:"grid"}}>` row lists with
no header row, no summary of what would run, and every problem reported as one page-level sentence
that never said which row it meant. **A fourth idiom.**

### 5.2 What was built

`desktop/src/renderer/pages/panels/_participants/` (≈ 400 lines): `types.ts`, the pure `model.ts`,
`ParticipantsField.tsx`, `participants.css`, `index.ts`. It is `SubjectsField`'s grammar over a row
list:

```
Subjects   3 subjects · 101, ernie, MNI152 · one job over all subjects   (i)  [ + Add subject ]
 # | Subject | Simulation | Group   | Why not
 1 | 101     | L_Insula   | Group1  |
 2 | ernie   | —          | Group1  | no simulation chosen
 3 | …ground rows to the bottom of the box…
```

Kept identical, deliberately: the 28 px `--surface-2` header band, the eyebrow title — **the same
word, "Subjects"** — the one-line summary carrying J4's semantics, a real table with real column
headers, the "Why not" column that exists only while some row has a reason, the warning-coloured
reason text, and ground rows.

Dropped, with the reason: the filter and select-all (set operations over a catalog — this table *is*
the study design) and the disclosure (the rows are the page's first decision, so there is nothing to
disclose).

Added, because a set could not say it: when a subject takes part twice the summary reads
`4 rows · 3 subjects · … · one job over all subjects`. That sentence is the whole reason these three
panels are not a set, said out loud to the user.

The blocked-reason mechanism is the same one, from the same shape of function:
`participantsBlockedReason(complete, blocked, minRows)` →
`Add at least 2 subjects with a simulation.` /
`row 3 cannot run — no simulation chosen. Remove it, or fix it first.` Each page's first clause is
that sentence, and it is what the action bar's digest prints (§6.2).

### 5.3 The drift guard

`participants.css` writes its **own** class names — defect 2's rule applies to this lane too — so
nothing but a test stops the two stylesheets becoming two grammars.
`tests/unit/participants-field.test.tsx` parses both files and compares
`.participants-field-head` ↔ `.subjects-field-head`, `-summary` ↔ `-summary`, `.participants-reason`
↔ `.subjects-field-reason` and the control block itself, **declaration by declaration**.

### 5.4 Before and after

Before: `expect(participants-field).toHaveCount(1)` → **Received: 0** on all three panels.
After: **6 passed** in `panels-shape.spec.ts` (the grammar test asserts the leading columns are
exactly `["#", "Subject", "Simulation"]`, that an unanswered row is `data-eligible="false"` with the
reason `no subject chosen`, and that choosing a subject moves both the summary and the reason on),
plus **18** unit tests.

### 5.5 The rule, recorded

DESIGN.md §4.4.1 *"Choosing who takes part: a set, or a list of rows"*, ending:

> **The rule: a fourth idiom for "who takes part" is a defect.** If a page cannot use
> `SubjectsField`, it uses `ParticipantsField`; if it can use neither, that is a design decision to
> be recorded with the measurement that forced it, not a new control.

---

## 6. Defect 4 — an empty state is the shape of what will appear

### 6.1 The rule

DESIGN.md §4.4 gains one paragraph:

> **A page whose populated state is a table takes the *table* row of the state matrix, not the
> whole-page row.** Its empty state is that same table — column headers, the message inside the
> body, ground rows down to the bottom of the pane — plus one action. The whole-page centred
> `EmptyState` is for a page with no table shape to show.

Jobs was the clearest case: `EmptyState message="Nothing has run yet."` centred in a 1224 × 704 box,
**99.1 % dead**, telling a first-time user nothing about what a job even looks like here.

### 6.2 What each page got

- **Jobs** — the toolbar stays (it is the shape of the page), `JobsTable` renders with
  `emptyMessage="Nothing has run yet."` **inside its own body**, `.jobs-page-filler` draws the rows
  the list will have at `--row-h` pitch below it, and the "Open Pre-processing" action sits under
  the table. `.jobs-table`'s `height: 100%` became `height: auto; max-height: 100%` **on this page
  only**, so a long list still scrolls inside its own box exactly as before. 99.1 → **12.5 %**.
- **Subject info** — the same ground rows under its browse table (painted, because `ui/DataTable`
  owns its own `<tr>`s), and the card fills the pane. 86.6 → **18.9 %**.
- **The three row-list panels** — `ParticipantsField` with `fill`, which measures the box and draws
  ground rows to its bottom; a two-column body (`.panel-page-split`: who takes part on the left,
  how to analyse them on the right); and an **action bar** (§6.3). 65–74 → **37.6–41.5 %**.
- **Source** — the two pipeline cards are now **always** on the page, disabled until a subject is
  chosen, instead of one sentence and 400 px of ground; the same split; the subject table grows to
  the pane. 82.3 → **41.7 %**.

`fill` cannot oscillate, which is the thing to check after lane UC's fill-controller finding: the
scroll box is `flex: 1` inside a grid cell whose height comes from the *other* column, so adding
rows changes the table's scroll height and never its client height. One observation, one answer.
(The first version measured synchronously inside `useLayoutEffect`; the repo's `react-hooks` rule
rejected it as a cascading render — correctly — so the initial value now comes from
`ResizeObserver.observe()`'s own first callback and a row change re-measures on the next frame.)

### 6.3 The panels get the action bar, and one measured rejection

The four job-submitting panels reported problems as a list of sentences above a Run button that
stayed enabled and never said what it was about to cost. They now carry `ui/Chrome`'s `ActionBar`
with `panelDigest(problems, plan, loading)` (`pages/panels/_shared.ts`): the first blocking reason
while it cannot run, `1 job · 8 CPU · 16 GB` once it can, and one `data-testid="run-button"` primary
— L3, in the same words as the four run pages. The full problem list stays beside the plan it
blocks, as `PlanSummary`'s new `problems` prop.

**Measured and rejected** — moving the Plan into a `PageLayout` right pane, exactly as the run pages
do. It improved the *work* pane (cluster-permutation 42.9 → 40.4 % dead) and made the **page** worse,
46.9 → **58.1 %**, because a 360 px column holding one short Plan card is ~70 % ground, which is the
empty pane U1 forbids. Reverted; the reason is written into `panels.css` beside the rule so nobody
retries it. A plan four lines long belongs beside the form.

### 6.4 What the numbers do and do not mean

- The **definition of `deadSpaceRatio` was not touched**, for LAY's reason (§6.1 of its notes):
  changing the instrument mid-programme would make these numbers incomparable with every earlier
  lane's. Everything added here is a diagnostic (`FIXD_DIAG=1`), never a gate.
- Two devices are visible design decisions that the probe happens to reward, stated plainly so a
  reviewer can weigh them: the **ground rows** (`.participants-filler`, `.jobs-page-filler`,
  `.panel-table-filler`) and the **two-column split**. Neither is an invisible box: the ground rows
  are the `.run-table-filler` object `SubjectsField` and `MontageManager` already ship, at the same
  28 px pitch as a real row, and the split is what lets a 1224 px pane hold a form instead of an
  826 px column beside 400 px of nothing. If a reviewer rejects one, §1's table says what it is
  worth.
- The state measured is the **empty** one — nothing chosen, nothing run — because that is exactly
  the state the maintainer's complaint and LAY's §8 item 1 are about. It is a harder state to fill
  than a populated one, not an easier one.

---

## 7. Gates and runs

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3507 passed, 30 skipped, 21 deselected, 42.8 s** (nothing under `tit/` touched) |
| `npm run typecheck` | clean, both projects |
| `npm run lint` | **0 errors**, 3 pre-existing warnings (`DataTable.tsx`, `VirtualList.tsx`, react-hook-form) |
| `npx vitest run` | **879 passed / 71 files** (+18 from this lane) |
| `npm run build` (plain) | clean, 1.96 s — and this is the bundle left in `out/` |

Mock Playwright, `--project=default`, in groups (never `npm run e2e`, whose `pree2e` rebuild races
other lanes); every group quiet-check **PASS**:

| Group | Result |
|---|---|
| `roi-idiom` + `panels-shape` (the two new gates) | **9 passed (24.3 s)** |
| `jobs` | **11 passed (57.2 s)** |
| `panels-forms` + `jobs` | **14 passed / 1 failed** → the one failure was `jobs.spec.ts`'s old empty-state assertion, rewritten (§8.1); green after |
| `analyzer` + `optimizer` + `panels` + `subjects` | **18 passed (49.2 s)** |
| `layout` (LAY's gate, re-run) | **6 passed (17.3 s)** — L5a 39.6–43.6 %, 0 obstructed, 0 px h-scroll |
| `preprocess` + `simulator` + `smoke` + `quick-notes` | **23 passed (1.2 m)** |
| `results` + `settings` + `help` + `screens` | **20 passed (1.4 m)** on re-run (§8.2) |
| `gallery` + `viewer` | **14 passed (1.3 m)** |

`--project=real`, container `ti-toolbox-fad740e5-tit-1`, project `/mnt/000`, every one quiet-check
**PASS**:

| Spec | Result |
|---|---|
| `real/nifti-group-average` | **1 passed (8.3 s)** — job `4083f8130168457e` succeeded, 2 artifacts |
| `real/nilearn-visuals` | **1 passed (16.7 s)** — job `20450eaf0cd54a3f` succeeded, 4 artifacts |
| `real/cluster-permutation` | **1 passed (7.4 s)** — job `e344bc9584244bef` succeeded, 8 files on disk |
| `real/ex` | **2 passed (35.0 s / 0.7 s)** — job `7655c5caab84466f` succeeded, 2 artifacts (the ROI picker's subcortical + saved modes on real data) |
| `real/analyzer-mesh` | **1 passed (9.1 s)** — job `00b5c1424acb4b6c` succeeded, 5 artifacts |
| `real/source` | **1 passed (9.8 m)** — job `bee0a68993de4c9f` succeeded, 3 artifacts (the panel this lane rebuilt) |

The three real panel specs were rewritten off positional indexing (`.card` with the text "Subjects",
then `combos.nth(index * 2)`) onto the participants grammar's own testids — the positional form
broke the moment the card became a table with a `#` column, and it was fragile before that.

State left behind: **none of this lane's.** No `*smoke-ui*` path anywhere under
`/Users/idohaber/datasets/000`; every job this lane submitted reached a terminal state and its
outputs were removed by the specs' own `afterAll`. One `source` job was `running` at the end — it is
**not this lane's** (mine, `bee0a68993de4c9f`, finished 20 minutes earlier) and was left alone.

---

## 8. Failures and flakes seen, and whose they are

1. **Mine, fixed.** `jobs.spec.ts`'s "a centred empty state replaces the toolbar and table" asserted
   the design defect 4 removes. Rewritten as "with no job ever submitted, the page is the table it
   is waiting for": toolbar visible, the table's first header `State`, the message **inside
   `tbody`**, the action still there and still navigating.
2. **Not mine — a suite-order flake.** `settings.spec.ts` failed once (49.7 s, `toBeVisible`) inside
   a four-file group and passed alone, in three different pairs, and on a re-run of the identical
   four-file group (20 passed). Same class as the critic's §7.2 and lane SUB's §6.7-8: one mock
   server, mutable `settingsStore`, shared by a whole invocation.
3. **Not mine — the same class, in vitest.** One whole-suite `npx vitest run` reported
   `tests/mock-server/server.test.ts` failing with `{"detail":"not found"}` from
   `POST /api/__mock/reset` — the request reached a *different* (older) mock server process. The
   file passes in isolation (21/21) and the suite passed 879/879 on the next run.
4. **Not mine — a launch flake.** `panels-shape.spec.ts` once failed in `beforeAll` at 0 ms; passed
   on the next run and on three runs after that.
5. **Not mine — in flight while this lane ran.** `npm run typecheck` was red for about an hour on
   `src/renderer/scene/SceneCanvas.tsx` and `tests/unit/scene-{camera,framing}.test.ts` (another
   lane mid-edit on `scene/camera.ts`). It is clean now; no file of this lane's ever appeared in
   that output.

---

## 9. Cross-lane edits, and requests

**Edits this lane made outside its own files**, listed for the record — one, additive, four lines:

- `desktop/src/renderer/ui/Combobox.tsx` — `aria-label` + `data-option-value` on every
  `Command.Item`, and `data-option-value` on a `MultiSelect` chip (§4.2). No visual change, no
  accessible-name change; covered by `roi-idiom.spec.ts`, `optimizer.spec.ts`, `real/ex`,
  `real/analyzer-mesh` and the three real panel specs, all green.
- `desktop/src/renderer/pages/panels/panels.css` scopes two overrides of classes owned by
  `pages/_shared/{run,subjects}` to `.panel-page`, so no run page can see them (§9 request 2).

**Requests, exact, for the owners:**

1. **`pages/_shared/subjects/SubjectsField.tsx` + `pages/_shared/run/run.css`** — give `SubjectsField`
   the `fill` prop `ParticipantsField` now has (measure the scroll box, draw ground rows to its
   bottom) and make `.run-subject-scroll`'s `max-height: 176px` a default rather than a ceiling;
   then delete the `.panel-page .run-subject-scroll` override in `pages/panels/panels.css`. This is
   LAY's own open issue 5 from the other side, and it is what the Source panel needed to stop being
   82 % empty.
2. **`ui/Toggle.tsx`'s remaining `RadioGroup` call sites** — DESIGN.md §4.2 rule 9 applies to all of
   them; each is a one-line swap to `SegmentedControl` with an `aria-label`, and the Radix roles are
   identical so no spec changes:
   - `ui/CoordinateInput.tsx:46` — Subject / MNI → `aria-label="Coordinate space"`. **This one
     matters most:** it is the same space choice this lane converted three times inside `RoiPicker`,
     and it is reachable from `RoiPicker`'s own "Add ROI" dialog, so the two idioms still meet in
     one flow.
   - `ui/ElectrodePairsEditor.tsx:37` — From EEG net / Free-hand coordinates.
   - `pages/optimizer/FlexSections.tsx:112` (Manual thresholds / Adaptive / Pareto sweep) and `:171`
     (Ellipse / Rectangle).
   - `pages/optimizer/ExSections.tsx:143` — Bucketed / All combinations.
   - `pages/preprocess/index.tsx:434` — Skip existing outputs / Replace and rerun.
   - `pages/simulator/index.tsx:318` — Ellipse / Rectangle.
   - `pages/settings/index.tsx:269` — System / Light / Dark.
   - `dev/Gallery.tsx` keeps both, deliberately: it documents the components.
3. **`ui/DataTable.tsx`** — a `minRows`/`fill` prop would let a browse table draw its own ground rows
   instead of the two pages that need them painting a gradient behind it
   (`jobs-page.css::.jobs-page-filler`, `panels.css::.panel-table-filler` — the same rule twice).
4. **`pages/_shared/run/useRunPaneController.ts`** — LAY's open issue 3 still stands: the wrapper is
   redundant since `ui/Layout.tsx` was fixed, and the three run pages can call `usePaneController`
   directly.
5. **Whoever owns the mock server** — items 2 and 3 of §8 are the third and fourth independent lanes
   to hit cross-spec state leaking through the one shared instance. Either the mock resets its
   `settingsStore` and job registry between spec *files*, or every spec that mutates them needs its
   own `afterAll`.

---

## 10. How to re-run this lane

```bash
cd desktop
npm run typecheck && npm run lint && npx vitest run tests/unit/participants-field.test.tsx
npm run build                       # PLAIN — this is the bundle the container serves

# the two gates (mock server, offscreen)
TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/roi-idiom.spec.ts tests/e2e/panels-shape.spec.ts

# the diagnostics the density rounds were steered by (never gates)
FIXD_DIAG=1 FIXD_SEL=".card, .field, .subjects-field, .panel-page-columns" \
  TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/panels-shape.spec.ts -g "light at 1280x800"

# the real panels, against the container
TOK=$(docker inspect ti-toolbox-fad740e5-tit-1 --format '{{range .Config.Env}}{{println .}}{{end}}' \
      | grep TIT_SERVER_TOKEN | cut -d= -f2)
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
  tests/e2e/real/nifti-group-average.spec.ts tests/e2e/real/nilearn-visuals.spec.ts \
  tests/e2e/real/cluster-permutation.spec.ts
```

`--project=real` **with** the equals sign, and never `npm run e2e`.
