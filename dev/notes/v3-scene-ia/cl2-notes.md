# Lane CL2 — one idiom, one wrapper fewer, one ground-row rule

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, staged, stashed or pushed; no `Co-Authored-By` anywhere. Every Electron and
Playwright run went through `TIT_E2E_OFFSCREEN=1 desktop/scripts/e2e-quiet-check.sh` and every one
reported **PASS — no window reached the screen, no focus moved**. Nothing under `tit/` was touched;
`/api/health` answered **200** before and after anyway. The container was never restarted or
recreated, port 5173 was never taken, and no process this lane did not start was killed.
`desktop/out/` is left on a **plain `npm run build`**.

This lane closes the three items three earlier rounds carried forward: the eight `RadioGroup` call
sites outside lane FIX-D's ownership, the `useRunPaneController` wrapper LAY/FIX-C/FIX-D each asked
to have deleted, and FIX-D's two cross-lane requests about a table's room and its ground rows.

---

## 1. Headline numbers

| # | Item | Before | After |
|---|---|---|---|
| 1 | `RadioGroup` for a small exclusive choice (DESIGN.md §4.2 rule 9) | **8** call sites outside FIX-D's files, including the subject/MNI space on every run page | **0**; all eight are `SegmentedControl` with an `aria-label` |
| 1b | A control that cannot act | the montage editor drew a mode switcher wired to `() => {}` — it moved and snapped back | not drawn at all when the caller has one mode |
| 2 | `useRunPaneController` | named in **5** files, called by all three run pages | **0**; module and barrel export deleted |
| 2b | The pane controller's `contentRect` fallback | `borderLeftWidth: "medium"` → `NaN` → the whole measurement dropped; `measured` stuck at the 320 px minimum | measures 400 px on both engine paths |
| 3a | The Source panel's subject table | 684 px box, **0** rendered ground rows, a gradient painted behind it, three `.panel-page` overrides of `pages/_shared` classes | 684 px, **20** real ground rows, `background-image: none`, **0** overrides |
| 3a | Pre-processing's subject table | **169 px / 5 rows** at 1440×900 **and** at 1440×1300 (`minRows={5}`, `max-height: 176px`) | **365 px / 12 rows** at 900, **757 px / 26 rows** at 1300 |
| 3b | Ground rows behind `ui/DataTable` | Jobs `.jobs-page-filler` = 1, `.data-table-filler` = **0**; Subject info `.panel-table-filler` = 1 | Jobs **22** rows, Subject info **20** rows; both painters **0** |

Dead space (`tests/e2e/_metrics.ts::deadSpaceRatio`, definition untouched), L5a limit 45 %:

| page | 1280×800 | 1440×900 | note |
|---|---|---|---|
| `preprocess` | **28.7 %** (was 36.3 %) | **31.1 %** | populated state, `layout.spec.ts`'s own instrument |
| `simulator` / `optimizer` / `analyzer` | 34.5 / 39.7 / 40.9 % | 38.4 / 41.3 / 43.5 % | unchanged by this lane |
| `panel-source` | 43.0 % | 44.8 % | was 41.7 / 43.7 % with the painted gradient |
| `panel-subject-info` | 21.1 % | 21.6 % | was 18.9 / 19.8 % |
| `jobs` | 14.7 % | 16.7 % | was 12.5 / 15.7 % |

The three pages that moved 1–2 points did so for one reason, stated so a reviewer can weigh it:
rendered ground rows stop on a row boundary, so the last partial row (≤ 27 px) is now ground where
a painted gradient covered it. Every page is inside the limit, and the rows are now the shape the
table actually draws instead of a stripe pattern that happened to match its pitch.

---

## 2. Item 1 — one idiom for a small exclusive choice

### 2.1 The reproduction

`tests/unit/segmented-idiom.test.ts` (new) scans `src/renderer` for `<RadioGroup`. Before:

```
AssertionError: expected [ …(8) ] to deeply equal []
+ [ "pages/optimizer/ExSections.tsx:143",   "pages/optimizer/FlexSections.tsx:112",
+   "pages/optimizer/FlexSections.tsx:171", "pages/preprocess/index.tsx:434",
+   "pages/settings/index.tsx:269",         "pages/simulator/index.tsx:318",
+   "ui/CoordinateInput.tsx:46",            "ui/ElectrodePairsEditor.tsx:37" ]
```

Exactly FIX-D's list (`fix-d-notes.md` §9 request 2). A scan, not an e2e assertion, because no
spec can catch a page nobody wrote a spec for — and the rule has to hold for the next page too.
The second test in that file requires an `aria-label` on every `SegmentedControl` call site, which
is what makes a segment addressable by a spec and nameable by a screen reader.

### 2.2 Converted, with the name each choice now carries

| file | choice | `aria-label` |
|---|---|---|
| `ui/CoordinateInput.tsx` | Subject / MNI | `Coordinate space` |
| `ui/ElectrodePairsEditor.tsx` | From EEG net / Free-hand coordinates | `Electrode source` |
| `pages/optimizer/FlexSections.tsx` | Manual thresholds / Adaptive / Pareto sweep | `Threshold mode` |
| " | Ellipse / Rectangle | `Electrode shape` |
| `pages/optimizer/ExSections.tsx` | Bucketed / All combinations | `Search space` |
| `pages/preprocess/index.tsx` | Skip existing outputs / Replace and rerun | `Existing outputs` |
| `pages/simulator/index.tsx` | Ellipse / Rectangle | `Electrode shape` |
| `pages/settings/index.tsx` | System / Light / Dark | `Theme` |

None is an exception: every one is two or three short, mutually exclusive words. `dev/Gallery.tsx`
keeps its `RadioGroup` deliberately (it documents both primitives) and `ui/Toggle.tsx` defines it —
both are named in the guard's allow-list with their reason, so an exception is a decision on the
record rather than an oversight. The settings theme control lost a `name="settings-theme"`
attribute that nothing in the repo read.

`CoordinateInput` is the one FIX-D called the one that matters most, and the reason survives
inspection: it is reached from `RoiPicker`'s own "Add ROI" dialog, whose *other* space control FIX-D
had already converted — two idioms for one idea, one click apart, in a single flow.

### 2.3 After, and the failure shown

`tests/e2e/segmented-idiom.spec.ts` (new, mock server, 3 tests) drives the pages a user opens: the
Simulator's shape, the Optimizer's shape / threshold mode / search space and its Add ROI dialog,
Pre-processing's output policy, Settings' theme. It asserts more than "a segment exists": the
option list in order, that the choice still reaches the *form* (the section's collapsed summary
reads `rectangle · 8×8 mm · gel 4 mm`, `replace and rerun · 1 in parallel`), and that the page's
whole work pane holds **no** `.radio-group`. **3 passed.**

Shown failing, by putting the `RadioGroup` back in `ui/CoordinateInput.tsx` and rebuilding:

```
✘ the Optimizer's shape, threshold mode and search space are segments — and so is the Add ROI dialog's space
  expect(locator).toHaveCount(1) failed
  Locator: getByRole('dialog').locator('.segmented')   Expected: 1  Received: 0
```

Restored, rebuilt, green. Every pre-existing spec that clicks these controls by role still passes,
because Radix renders `role="radiogroup"`/`role="radio"` for both — including `real/preprocess`'s
`getByRole("radio", { name: "Replace and rerun" })`, run against the container (§6).

### 2.4 One control that could not act (found while converting)

`pages/simulator/MontageManager.tsx` rendered the pairs editor with `mode="net"` and
`onModeChange={() => {}}`: clicking "Free-hand coordinates" called a no-op and the control snapped
back. A montage built on an EEG net has no free-hand mode to switch to, so `onModeChange` is now
optional and the switcher is drawn only when the caller can act on it. Asserted in
`tests/unit/ground-rows.test.tsx` ("a control is drawn only when it can act").

---

## 3. Item 2 — the wrapper, and the loop it worked around

### 3.1 The reproduction

```
AssertionError: expected [ 'pages/_shared/run/index.ts', …(4) ] to deeply equal []
+ [ "pages/_shared/run/index.ts", "pages/_shared/run/useRunPaneController.ts",
+   "pages/analyzer/AnalyzerPage.tsx", "pages/optimizer/index.tsx", "pages/simulator/index.tsx" ]
```

### 3.2 The migration

FIX-C's exact request, applied: the three pages now call
`usePaneController({ pageId: "<page>", name: "run" })` from `../../ui/Layout`; the module and its
barrel export are deleted. `tests/unit/run-pane-controller.test.tsx` asserts both halves — no file
names the wrapper, and each page asks for its own pane by id.

### 3.3 The defect it existed for, asserted rather than assumed

The wrapper existed for lane SCC's **720 renders in 2 s** on the Optimizer (`scc-notes.md` §4.2),
whose real cost was the page's 400 ms plan debounce: `POST /api/plan/flex` was never sent. Lane LAY
fixed both causes in `ui/Layout.tsx`; deleting the wrapper without a guard would leave nothing
watching them. The new unit file renders the real `PageLayout` with the real `usePaneController`
against a `ResizeObserver` fake that behaves like the browser's — **a delivery is owed for every
`observe()`** — and drains the deliveries a page causes until nothing is owed or a cap is hit:

| assertion | fixed | `ui/Layout.tsx` regressed to the pre-LAY behaviour |
|---|---|---|
| `measured` after one drain (both engine paths) | **400** (the border box) | 400, but the widths passed through `[320, **388**, 400, 400]` — the oscillation itself |
| `observe()` calls over 20 commits | **1** | **22** |
| renders over 10 further deliveries | ≤ 10 | **30** |
| renders over 25 interleaved commits + drains | ≤ 50 | **125** |
| deliveries owed after settling | **1** | 1 per commit, for ever |

(The regression was staged by hand — the inline `<aside>` ref plus `entry.contentRect.width` — and
reverted immediately; `git status` for `ui/Layout.tsx` shows only this lane's intended change.)

### 3.4 A second defect found by that test

`usePaneController`'s `contentRect` fallback — the branch that exists "for jsdom and older engines"
— parsed `getComputedStyle(el).borderLeftWidth`, which computes to the **keyword `medium`** on an
element with no border (jsdom returns exactly that). `parseFloat("medium")` is `NaN`, the sum is
`NaN`, and the `rounded > 0` guard then dropped the whole measurement: the fallback silently
measured nothing in the one environment it was written for, leaving `measured` at the 320 px
minimum instead of the pane's 400 px. Fixed with a `Number.isFinite` guard on each length.

---

## 4. Item 3 — a table's room, and whose rows the ground rows are

### 4.1 The reproductions

```
CL2-ROOM panel-source scroll=684px slackBelow=0px fillers=0  painted=true
CL2-ROOM preprocess   scroll=169px rows=5 fillers=2          (1440x900 AND 1440x1300)
CL2-GROUND jobs dataTableFillers=0 painter(.jobs-page-filler)=1 dead=15.7%
```

Three copies of one rule: `.panel-page .run-subject-scroll` lifted `pages/_shared/run/run.css`'s
`max-height: 176px` from another page's stylesheet **and** painted a repeating gradient behind the
table; `.panel-table-filler` and `.jobs-page-filler` painted the identical gradient for the two
pages whose table is `ui/DataTable`, which owns its own `<tr>`s and would not draw them.

### 4.2 What was built

- **`SubjectsField` takes `fill`** (`pages/_shared/subjects/{SubjectsField.tsx,types.ts}`): it
  measures the room and draws ground rows into it, and `.run-subject-scroll[data-fill="true"]`
  lifts the 176 px cap — which stays as the **default** for every other page, with the reason it
  exists written beside it (a 40-subject project must not push a run page's steps off the first
  screen).
- **`ui/DataTable` takes `fill` and `minRows`** and renders `tr.data-table-filler` — `aria-hidden`,
  full-width, at the table's own `--row-h` pitch and surface. `app/jobs-rail/JobsTable.tsx`
  forwards the prop; Jobs and Subject info pass it and their painted `<div>`s are gone.
- **Deleted**: `.jobs-page-filler`, `.panel-table-filler`, `.panel-page .run-subject-scroll`,
  `.panel-page .subjects-field`, `.panel-page .subjects-field-body`, and the Jobs page's
  `height: auto; max-height: 100%` override of `.jobs-table` (it existed only to leave room for the
  gradient below it).

### 4.3 The measurement, and why it cannot oscillate

A subject table lives in two shapes, and the control asks the *page* which one it is (`display:
flex` on the control's host) rather than inferring it from the box:

- **stretched** (the Source panel: `.panel-page [data-tier="1"]` is a flex column of definite
  height) — the box's own `clientHeight` is the room, and **no `max-height` is written back**.
  Writing one from a measurement *of* the box is a ratchet: an early short measurement pinned the
  Source table to 631 px of a 684 px column and it could never grow back. Measured, then fixed.
- **content-sized** (a run page's scrolling column) — the room is
  `scroller.clientHeight − (column.height − box.clientHeight)`. The subtrahend is everything in the
  column *except* this box, so it does not move when the box grows: one step, then a fixed point.
  Never `scroller.scrollHeight`, which is `max(content, box)` and reports zero slack exactly when
  there is slack — the same trap `RunWork.tsx` documents for the fill controller, and the reason a
  first attempt here measured Pre-processing as having no room at all (`scrollHeight` insisted
  712 = 712 while the column was 553 px in a 712 px scrollport).

`ResizeObserver` absence (jsdom, older engines) is guarded in both controls: the table then renders
exactly the rows it has, which is the pre-`fill` behaviour, never a crash.

### 4.4 After

```
CL2-ROOM   panel-source scroll=684px slackBelow=0px fillers=20 painted=false   dead=44.8%
CL2-ROOM   preprocess 1440x900  scroll=365px rows=12 fillers=9  dead=31.1%
CL2-ROOM   preprocess 1440x1300 scroll=757px rows=26
CL2-GROUND jobs              dataTableFillers=22 painter=0 dead=16.7%
CL2-GROUND panel-subject-info dataTableFillers=20 painter=0 dead=21.6%
```

`tests/e2e/table-room.spec.ts` (new, 3 tests) is the gate: the room taken, the ground rows rendered
rather than painted, the painters gone, every Tier-1 control still on the first screen
(`firstScreenControls().hidden === []`), and every page inside L5a. It measures with a subject
selected, for `layout.spec.ts`'s stated reason — a page measured with nothing chosen is measuring
its empty state.

`tests/unit/ground-rows.test.tsx` (10 tests) holds the contract no screenshot can: the pad rows are
`aria-hidden` and span the table, the empty state keeps its message row and pads *below* it, a page
that asks for nothing gets nothing, neither stylesheet contains `repeating-linear-gradient` any
more, and the rule exists exactly once — in the stylesheet of the component that renders the rows.
Shown failing by pasting `.panel-table-filler` back into `panels.css`:

```
AssertionError: pages/panels/panels.css still paints ground rows:
  expected '/* Shared geometry for the job-submit…' not to match /repeating-linear-gradient/
```

DESIGN.md §4.4 records the rule and the failure it prevents.

---

## 5. Gates

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3519 passed, 32 skipped, 21 deselected, 41.6 s** (nothing under `tit/` touched) |
| `/api/health` on `ti-toolbox-fad740e5-tit-1` | **200**, before and after |
| `npm run typecheck` | clean, both projects |
| `npm run lint` | **0 errors, 3 pre-existing warnings** at the end of the session (mid-session it showed 1 error and 5 warnings, all in another lane's in-flight scene files — see §7.1) |
| `npx vitest run` | **909 passed / 74 files** (+18 from this lane) |
| `npm run build` (plain) | clean; this is the bundle left in `out/` |

Mock Playwright, `--project=default`, in groups (never `npm run e2e`), every group quiet-check
**PASS**:

| Group | Result |
|---|---|
| `layout` + `table-room` + `segmented-idiom` + `roi-idiom` + `panels-shape` | **21 passed (53.4 s)** |
| `preprocess` + `simulator` + `optimizer` + `analyzer` + `subjects` | **29 passed (59.5 s)** |
| `jobs` + `panels` + `panels-forms` + `settings` + `results` | **30 passed (2.4 m)** |
| `smoke` + `help` + `screens` + `quick-notes` + `scene-tabs` + `viewer` | **31 passed (2.3 m)** |
| `launcher` + `native-launch` | **12 passed (33.2 s)** |

Not run, and why: `gallery.spec.ts` and `scene.spec.ts` need a `VITE_INCLUDE_GALLERY=1` build
(RUNBOOK Level B), and this lane deliberately left `out/` on a plain build rather than rebuild
twice while another lane was working in the tree; `viewer-real.spec.ts` needs a real Tetravox embed.

`--project=real`, container `ti-toolbox-fad740e5-tit-1`, project `/mnt/000`, quiet-check **PASS**:

| Spec | Result |
|---|---|
| `real/preprocess` | **2 passed (1.7 m)** — job `f883c18029654f98` (tissue, sub-101) and `ac0d86a6a81e4519` (DICOM, sub-102) both succeeded; drives the converted "Existing outputs" segment and the `fill` subject table on a five-subject project |
| `real/ex` | **2 passed (34.9 s / 0.8 s)** — job `646e5a9618464911` succeeded, 2 artifacts; the ROI picker and its subcortical/saved modes on real data |
| `real/source` | **1 passed (10.6 m)** — job `01c5ee791c1a4490` succeeded in **583.1 s**, 3 artifacts; the Source panel is the page whose subject table this lane rebuilt |

After the last source change the bundle was rebuilt (plain) and the affected specs re-run against
it: `segmented-idiom` + `simulator` + `table-room` + `jobs` + `panels-shape` — **29 passed
(1.6 m)**, quiet-check PASS. `desktop/out/renderer` greps clean for `Design gallery`, `Every
primitive`, `Mount scene`, `window.__scene`, `__scenePane` (0 occurrences each).

---

## 6. Files

Owned by this lane:

```
src/renderer/ui/{CoordinateInput,ElectrodePairsEditor,DataTable,Layout}.tsx
src/renderer/ui/components.css
src/renderer/pages/optimizer/{index.tsx,FlexSections.tsx,ExSections.tsx}
src/renderer/pages/simulator/{index.tsx,MontageManager.tsx}
src/renderer/pages/analyzer/AnalyzerPage.tsx
src/renderer/pages/preprocess/index.tsx
src/renderer/pages/settings/index.tsx
src/renderer/pages/_shared/run/{index.ts,run.css}
src/renderer/pages/_shared/run/useRunPaneController.ts        (DELETED)
tests/unit/{segmented-idiom.test.ts,run-pane-controller.test.tsx,ground-rows.test.tsx}   (new)
tests/e2e/{segmented-idiom.spec.ts,table-room.spec.ts}                                   (new)
```

Cross-lane, each one required by the item and listed for the record:

- `pages/_shared/subjects/{SubjectsField.tsx,types.ts,subjects.css}` — the `fill` prop (FIX-D's
  request 1; the control is lane SUB's file).
- `pages/panels/panels.css` — the three `.panel-page` overrides of `pages/_shared` classes and the
  `.panel-table-filler` gradient deleted; `pages/panels/{source,subject-info}/index.tsx` — `fill`.
- `pages/jobs/{index.tsx,jobs-page.css}` and `app/jobs-rail/JobsTable.tsx` — `fill` forwarded, the
  `.jobs-page-filler` gradient and the content-height override deleted.
- `DESIGN.md` §4.4 — the ground-rows rule and the numbers behind it.

## 7. Failures seen, and whose they are

1. **Not mine — in flight while this lane ran.** For part of the session `npm run lint` reported
   `tests/e2e/real/scene-optimizer.spec.ts:21 'chooseMarker' is defined but never used` plus two
   extra warnings in `tests/unit/scene-framing.test.ts` — files last written at 07:16 today by the
   lane editing `src/renderer/scene/**`. No file this lane touched ever appeared in that output,
   and the final run is back at FIX-D's baseline: **0 errors, 3 pre-existing warnings**.
2. **Not mine — the same lane, transient.** `npm run typecheck` was red for one run on
   `tests/unit/scene-pane-model.test.ts(210,37) TS2554` and clean on every run after it.
3. **Mine, fixed while writing the test.** The first version of the `RadioGroup` scan matched only
   single-line call sites (3 of 8) and the `aria-label` scan ended each element at the first `>`,
   which is inside `(v) => …`. Both corrected before the fix was applied, so the "before" numbers
   in §2.1 are from the corrected instrument.

## 8. Open issues

1. **`panel-source` sits at 44.8 % dead at 1440×900**, 0.2 points inside L5a, and
   `panel-nifti-group-average` at 44.0 %. Neither is this lane's page, and neither moved more than
   1.1 points here (rendered ground rows stop on a row boundary where a painted gradient did not).
   The next lane touching those pages should treat the limit as reached, not as headroom.
2. **`RunWork`'s fill controller and a `fill` table share the same pixels.** On Pre-processing the
   table now takes the slack first and the controller leaves the third section collapsed (2 of 3
   open at both window heights). That is the right priority on the page whose job is batch
   selection — Tier-1 before Tier-2 detail — but it is an arbitration by ordering, not by rule.
   If a second run page ever asks for `fill`, the two should be made to agree explicitly.
3. **The scene e2e hooks are still gated by `VITE_INCLUDE_GALLERY`** (FIX-C's open issue 2,
   unchanged), which is why `gallery.spec.ts` and `scene.spec.ts` are the two default specs this
   lane did not run: doing so needs a flagged build, and `out/` must be left plain.
4. **The mock server still leaks state between spec files** (FIX-D's request 5, four lanes now).
   Not hit in this lane's runs, but nothing changed about it.

## 9. How to re-run this lane

```bash
cd desktop
npx vitest run tests/unit/segmented-idiom.test.ts tests/unit/run-pane-controller.test.tsx \
               tests/unit/ground-rows.test.tsx
npm run build                       # PLAIN — this is the bundle the container serves

TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/segmented-idiom.spec.ts \
  tests/e2e/table-room.spec.ts tests/e2e/layout.spec.ts tests/e2e/panels-shape.spec.ts

# the two real specs that cover the pages this lane changed
TOK=$(docker inspect ti-toolbox-fad740e5-tit-1 --format '{{range .Config.Env}}{{println .}}{{end}}' \
      | grep TIT_SERVER_TOKEN | cut -d= -f2)
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
  tests/e2e/real/preprocess.spec.ts tests/e2e/real/source.spec.ts

# the diagnostics the room measurements were steered by (never gates)
CL2_DIAG=1 TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/table-room.spec.ts
```

`--project=real` **with** the equals sign, and never `npm run e2e`.

## 10. State left behind

- `desktop/out/` on a **plain** `npm run build`; 0 occurrences of `Design gallery`, `Every
  primitive`, `Mount scene`, `window.__scene`, `__scenePane` in any built asset.
- Container `ti-toolbox-fad740e5-tit-1` never restarted or recreated; `/api/health` = **200**
  before and after; `GET /api/jobs` reports **0 running, 0 queued** at the end. Every job this lane
  submitted (`f883c18029654f98`, `ac0d86a6a81e4519`, `646e5a9618464911`, `01c5ee791c1a4490`)
  reached a terminal state and its outputs were removed by the specs' own `afterAll`.
- Port 5173 and the maintainer's `electron-vite dev` (pid 77069) untouched. One orphaned Electron
  from another lane's run (pid 31865, started 22:35 yesterday) was left alone.
- Nothing committed, staged, stashed or pushed.
