# Lane LAY — the layout pass (plan of record `dev/notes/v3-scene-ia-plan.md` §4, L1–L5)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, staged, stashed or pushed. Every Electron/Playwright run below went through
`TIT_E2E_OFFSCREEN=1 scripts/e2e-quiet-check.sh`; every one reported **PASS** and no window
reached the maintainer's screen.

Delivers: L4's action-bar defect fixed at its cause in `ui/Layout.tsx`'s stylesheet, lane UC's
second finding (the fill controller) fixed, one skeleton and one Tier-1 rule stated and asserted
across the four run pages and the panels, and L5's four numbers met at both sizes in both themes —
with a **new gate**, `desktop/tests/e2e/layout.spec.ts`, that fails when one of them is missed.

---

## 1. Headline numbers

Dead space = `deadSpaceRatio` over `[data-testid="shell-content"]`, the shared instrument,
**unchanged** (see §6.1 for why I did not touch its definition). Populated state = the subject
scoped to `ernie` through the palette, exactly as `screens.spec.ts` does it.

| page | 1280×800 before | after | 1440×900 before | after |
|---|---|---|---|---|
| Pre-processing | 61.3 % | **36.3 %** | 61.0 % | **42.0 %** |
| Simulator | 43.0 % | **34.4 %** | 42.5 % | **38.3 %** |
| Optimizer | 55.0 % | **41.6 %** | 53.0 % | **42.8 %** |
| Analyzer | 57.0 % | **40.8 %** | 57.8 % | **43.5 %** |

Identical in light and dark (the layout is theme-independent; both were measured, not assumed).
Limit is 45 %. No page outside the run shape moved by more than 2.3 points in either direction —
Results 31.9 → 31.9, Subjects 51.3 → 51.3, Jobs 99.1 → 99.1, Viewer 0.4 → 0.4, Help 20.8 → 20.8,
Settings 70.8 → 70.6, panel-source 84.8 → 82.5 at 1440.

The other three L5/L4 numbers, on all four pages, at both sizes, in both themes:

| | limit | result |
|---|---|---|
| Tier-1 controls below the fold | 0 | **0** of 21 / 16 / 18 / 28 |
| interactive controls under the action bar, at any scroll offset | 0 | **0** of 176–219 controls per page over 5–7 scroll steps |
| horizontal page scroll | 0 px | **0** |
| work + handle + right pane + 2 × `--page-pad` | = content box | **1224 = 1224** at both sizes |

---

## 2. L4 — "nothing overlaps", fixed at its cause

### 2.1 The defect, restated from the measurement

Lane UC found it on the real container and could not fix it from its own files; lane SCC hit it
again (its §6.5). `.page-layout-main` was **both** the `overflow: auto` scroller **and** the sticky
`.action-bar`'s flex parent. A sticky element resolves its offsets against its own flow position,
and that position tracks the *flex-allocated* box (`clientHeight − 44`), not "below however tall
the overflowing content actually is". So the moment a form overflowed at all, the bar rendered
**inside** the content, and because both moved together under scroll no offset ever cleared it —
UC scanned `scrollTop` 0→161 in 10 px steps and found the same ~29 px overlap at every one
(`anyClear: false`). `click({ force: true })` did not rescue it: Chromium's own hit-testing still
resolved the point to the bar, and UC proved the click was swallowed by asserting the toast that
never appeared.

### 2.2 The fix

`ui/components.css`: the work pane stops being the scroller and its scroll child becomes one.

```css
.page-layout-main       { overflow: hidden; }   /* was auto — still a clipping box */
.page-layout-main-scroll{ overflow: auto;  }    /* flex: 1; min-height: 0 already */
```

The bar is then a `flex: none` sibling **outside** the scrollport, so the scrollport is exactly
`pane height − 44 px` and content cannot be painted under it at any offset. `position: sticky` is
kept on `.action-bar` because the `< 1100 px` stacked shape still needs it (there `.shell-content`
is the only scroller, and `.page-layout-main-scroll` is put back to `overflow: visible` alongside
`.page-layout-main`, or the form would be clipped twice).

Decision, with the failure it prevents: **the scrollport is the box the content has to fit in, so
the bar must not be in it.** Reserving height with `padding-bottom` (the obvious alternative, and
what UC suggested) leaves the bar painting over the padding and still hit-testing above content
whenever the sticky offset resolves differently — it hides the symptom at one scroll offset rather
than removing the overlap.

### 2.3 A second overlap the new instrument found immediately

`FormSection`'s header was `position: sticky; top: 0`. A sticky header inside the pane's own
scroller necessarily paints over its own body. Measured on the Optimizer at 1280×800: **5 of 219
controls** — the three Target radios, the atlas combobox and the region multi-select — hit-tested
to `span.form-section-header-trigger "Target"` instead of to themselves at `scrollTop` 120–200,
which is precisely where `scrollIntoViewIfNeeded` parks an element (flush at the top of the
scrollport, where the header pins). The header is no longer sticky. The name stays in view anyway
now that the fill rule sizes a section to the pane it is in.

### 2.4 How it is asserted

`tests/e2e/_metrics.ts::actionBarReach(page, step = 40)`: scan the work pane's whole scroll range,
and at each stop call `document.elementFromPoint` at the **centre of every enabled interactive
control** whose centre is at least a pixel inside the scrollport. A control is obstructed when the
element there is neither itself nor a descendant/ancestor. Hit-testing, not rectangle comparison,
because hit-testing is the test Chromium applies to a click — a rectangle check would miss a
transparent overlay and would flag a merely-clipped control.

One measurement bug of my own, found and fixed: the first version judged a control whose centre
sat *exactly* on the scrollport's bottom edge, where the next pixel belongs to the action bar. It
reported 3 phantom obstructions on the Optimizer. The rects proved there was no overlap
(`scroll.bottom 684`, `bar.top 684`), so the guard became "at least 1 px inside", not "inside".

---

## 3. Lane UC's second finding — the fill controller

`RunWork`'s fill rule observed the **pane** and nothing else, so a page whose content grew after
mount kept the answer it had computed for a page that no longer existed (UC's case: the Analyzer's
`ResultsPanel` gains rows the moment a simulation is chosen). It still reproduced. It now observes
the content as well, with two rules that make the loop provably convergent rather than the
flip-flop UC actually measured ("oscillated it open/closed live"):

| rule | what it prevents |
|---|---|
| `selfChange` — a resize the controller caused is not a new question | the controller answering its own reflow, which is what a naive content observer turns into an infinite open/close |
| `closedByOverflow` — a section the rule closed to give height back is not re-opened until the **pane** resizes | between two pane sizes the decision is monotone (sections can only close), so open→close→open cannot cycle however the content moves |

`availableHeight` also stopped subtracting the action bar by hand: since §2.2 the scrollport **is**
the box the sections must fit in, so `scroller.clientHeight` is the honest number (the old
`work.clientHeight − bar.offsetHeight` branch is kept as a fallback for jsdom, where
`clientHeight` is 0).

## 3.1 The pane controller's render loop (lane SCC's exact request, §4.2 of its notes)

Both halves landed in `ui/Layout.tsx`, which this lane owns:

- the `ResizeObserver` now reads `entries[0].borderBoxSize[0].inlineSize` — the same box
  `getBoundingClientRect()` seeds `measured` from, and the same box `width: var(--right-pane-w)`
  sets under the app's global `box-sizing: border-box`. `contentRect` disagreed by the 12 px of
  `.page-layout-run .page-layout-panel { padding-left }`, and each disagreement re-rendered. A
  `contentRect` + computed-padding fallback keeps jsdom and older engines working.
- the `<aside>`'s ref is a `useCallback`, so React stops calling `attach(null)` then `attach(el)`
  on every commit.

SCC measured the loop at **720 renders in 2 s** on the Optimizer (5 without the controller), and
what it broke was the page's 400 ms plan debounce — `POST /api/plan/flex` was never sent.
`pages/_shared/run/useRunPaneController.ts` (SCC's file, not mine) still carries the workaround; it
is now redundant but harmless. **Request to whoever next owns it: delete the wrapper and call
`usePaneController` directly.**

---

## 4. L1 / L2 / L3 — the skeleton

L1's skeleton was already close after lanes SUB and SCC; this lane stated it, wrote it into
`DESIGN.md` §4.7, and asserted the parts that are assertable. What changed:

| # | Change | Failure it prevents |
|---|---|---|
| A1 | **Subjects draws the same 28 px header band as every `FormSection`.** It was the only "section" on the page that looked like a bare row of text above a stack of banded headers. | J2 says Subjects is the first section of every run page; a control that does not look like one is a second grammar. |
| A2 | **`panels/source` no longer wraps `SubjectsField` in a `Card` titled "Subjects".** The page printed the word twice, 40 px apart; the page-level (i) moved into the control's own `help` slot, where the four run pages put it. | Two labels for one control, and a card of chrome around a section. |
| A3 | **The three stats panels lose their `maxWidth: 900/960` caps** (`cluster-permutation`, `nifti-group-average`, `nilearn-visuals`). | U1: a page that does not use the content box it was given. |
| A4 | **L3 is asserted**: exactly one action bar, its digest never empty, exactly one `run-button`, and exactly one `.btn-primary` anywhere in the work pane. | Two Run buttons, or a disabled button with nothing beside it saying why. |
| A5 | **Tier-1 stays as SUB/SCC left it** — `data-tier="1"` on Subjects plus each page's science-bearing sections — and `firstScreenControls` reports `hidden: []` on all four pages at both sizes. Nothing was promoted or demoted: the audit found L2 already satisfied. | Re-tiering a page nobody measured a problem on. |

---

## 5. L5 — the density work, round by round

Method (program U10): build → offscreen measure → diagnose *where* the emptiness is → change one
thing → measure again. Two diagnostics were added to the instrument for this and are **not** gates:
`deadSpaceProfile` (the same ratio split by pane and by 8 horizontal bands) and `deadSpaceByChild`
(per component, with its height). They are what turned "the page is 61 % empty" into "the section
headers are 97 % empty and there are five of them".

Numbers are 1280×800 light unless a row says otherwise: preprocess / simulator / optimizer /
analyzer.

| round | change | dead space | note |
|---|---|---|---|
| 1 | baseline | 61.3 / 43.0 / 55.0 / 57.0 | |
| 2 | L4 scroller fix + the new probe | 61.3 / 43.0 / 55.3 / 57.0 | probe found the sticky-header overlap: optimizer **5 obstructed** |
| 2c | text nodes get their own element (§6.1) | 59.2 / 42.8 / 53.9 / 56.7 | isolates the markup artifact: **1.4–2.1 points**, not the story |
| 3 | data-tables full-bleed; header band; select fills its column; `.run-work` gap 12→4 | 57.0 / 39.2 / 51.7 / 56.0 | |
| 4 | header trigger `background: inherit`; Subjects header band | 50.4 / 34.8 / 46.1 / 44.2 | the single biggest step; section headers went 93 % → 1 % |
| 5 | `.form-grid` row gap 8→4; toggle rows become checklist rows | 43.2 / 35.1 / 45.5 / **45.7** | the Analyzer **regressed**: shorter content, bigger empty tail |
| 6 | the Analyzer's "no simulation yet" becomes the empty analyses table | 43.2 / 35.1 / 45.5 / 41.1 | |
| 7 | radio rows become pill rows; **Optimizer span rows un-spanned** | 42.x / 34.x / **47.2** / 40.x | the un-span **made it worse** — rejected and reverted, recorded in `optimizer.css` |
| 8 | revert the un-span; fix the probe's edge case | 42.6 / 34.6 / 45.1 / 40.8 | |
| 10 | `.form-section-body` padding 8/12 → 4/8 | 42.6 / 34.4 / **41.6** / 40.8 | 1440: 45.9 / 38.3 / 42.8 / 43.5 — preprocess still over |
| 11 | the "Why not" column only exists when some row has a reason | 42.5 / 34.4 / 41.6 / 40.8 | 1440: 45.8 — 0.8 short |
| 12 | the Subjects table keeps a minimum row count (`minRows`) | 41.1 / 34.4 / 41.6 / 40.8 | 1440: **43.8 / 38.3 / 42.8 / 43.5 — all pass** |
| final | `minRows` 8 → 5 (8 overflowed the table's own 176 px scroll region), panel fixes, L3 asserts | **36.3 / 34.4 / 41.6 / 40.8** | 1440: **42.0 / 38.3 / 42.8 / 43.5** |

### 5.1 What the diagnostics said, and what each change was for

- **Section headers were 93–97 % empty** and there are four to six per page: a full-width 28 px
  strip carrying ~50 px of eyebrow. They are now a 28 px band on `--surface-2` — the object §4.3
  already defines for a **table** header, so no new shape was invented — which also makes the
  boundaries of a stack of flush sections scannable at a glance. A *collapsible* header measured
  0 % empty and a non-collapsible one 93 % with the identical band, because the trigger is a
  `<button>` in one case and a `<span>` in the other; `background: inherit` on the trigger (visually
  a no-op) is what stopped the header lying about itself.
- **`.field` rows were 40–68 % empty.** A select/combobox now fills its column (DESIGN.md §3.3's
  "200–280 px" was written for a 666 px work pane; at 826 px in two columns it left a ragged right
  edge and ~110 px of ground per row).
- **Toggle rows were 64–80 % empty**, used ~180 px of a 389 px column, and their hit target was the
  four-letter word rather than the row. Pre-processing's Structural and DWI groups **are**
  checklists, so a toggle now gets the row it sits in, as a 28 px surface. Radio rows got the same
  treatment, which also brings `RadioGroup` and `SegmentedControl` — the identical idea on
  neighbouring pages — into one visual language.
- **The Analyzer's sphere table kept a 160 px label gutter** it should never have had: DESIGN.md
  §4.2 rule 3 lists coordinate/sphere tables as full-bleed, but the `:has()` rule named
  `.coordinate-input` and the table is a `.data-table-container`. The rule now names that class, so
  it is true of every data table inside a `Field`.
- **The bottom of a page was 100 % empty** where the form is shorter than the pane (Analyzer at
  1280, Pre-processing at 1440). Two fixes, both of which make the page say more rather than pad
  it: the Analyzer's "pick a simulation" prose became the **empty analyses table** with its four
  column headers and the reason in the body (DESIGN.md §4.4's own rule — "empty: `emptyMessage`,
  one line, **inside the table body**"), and Pre-processing's subject table keeps a minimum row
  count with ground-drawn rows — the `run-table-filler` device `MontageManager` already uses.
- **Row gaps.** `.form-grid` 8 → 4 px and `.form-section-body` 8/12 → 4/8 px. On a page that
  already overflows its pane (the Optimizer needs 767 px of a 628 px scrollport at 1280×800) this
  is not cosmetic: it is two more Solver rows above the fold, and it took the Optimizer from 45.1
  to 41.6 % in one step.

### 5.2 One change measured and rejected

Un-spanning the Optimizer's two `optimizer-span` rows ("Dimensions (x, y)", "Current ratio") so
they pair up in a 389 px column. It looked right on paper — 160 label + 12 + two 96–128 px controls
does fit — and made the page **worse**: 45.5 → 47.2 %, because two 826 px rows became four 389 px
cells of which the extra two were empty, and the number inputs lost the room that kept them off
each other. Reverted; the reason is written into `optimizer.css` beside the rule so nobody retries
it.

---

## 6. Integrity notes — what the numbers do and do not mean

### 6.1 The instrument's definition was not touched

`deadSpaceRatio`, `paneWidths` and `firstScreenControls` are byte-for-byte what every earlier lane
measured with. Redefining the metric mid-programme would make my numbers incomparable with theirs
and would be indistinguishable from moving the goalposts. Everything I added (`actionBarReach`,
`horizontalOverflow`, `deadSpaceProfile`, `deadSpaceByChild`) is additive.

The probe has a known false negative: it resolves a sample point to the **innermost element**, so a
text node that sits beside an element inside its parent is invisible to it (`<label><Checkbox/>text
</label>` scores the text as ground; so does a `<label>` whose `required` `*` makes it a non-leaf).
I fixed that in the **markup**, not in the probe — each text run now gets its own `<span>` — and
measured the effect on its own in round 2c so it can be separated from the design work: **1.4–2.1
points of the 15–25 the pass delivered.** The same applies to `background: inherit` on the section
header trigger, which is visually a no-op and exists only so the tinted band the user can see is
also the band the probe sees.

### 6.2 What is a design decision that the probe happens to reward

Stated plainly so the critic can weigh them: the `--surface-2` **section-header band** (§5.1), the
**checklist/pill row surfaces** for toggles and radios, and Pre-processing's **filler rows**. Each
is a visible change with an argument that does not mention the metric — consistency with §4.3's
table header, a row-sized hit target, and a device already shipping in `MontageManager` — and each
also moves the number. They are not invisible boxes painted to score points; if a reviewer rejects
one, the number it is worth is in §5's table.

### 6.3 What the measurement does not cover

- The **populated state is "a subject is scoped"**, which is what `screens.spec.ts` established. The
  Analyzer with a simulation chosen, or Pre-processing with twenty subjects, are denser states that
  were not measured; the states measured are the ones a user lands on.
- The panel pages are measured in their **empty** state (`panel-source` 84 %, `panel-subject-info`
  86 %, Jobs 99 %) because the mock fixture leaves them with no selection and no jobs. L5's limit is
  stated for run pages, and I did not weaken it by picking a fuller fixture. Those three numbers are
  open (§8).
- Light and dark are identical to 0.1 points on every run page, because nothing in this pass is
  colour-dependent. Both were measured every round anyway.

---

## 7. Gates and runs

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3462 passed, 30 skipped, 21 deselected, 37.2 s** — unchanged (nothing under `tit/` was touched) |
| `npm run typecheck` | clean (both projects) |
| `npm run lint` | **0 errors**, 3 pre-existing warnings (`DataTable.tsx`, `VirtualList.tsx`) |
| `npx vitest run` | **836 passed / 68 files** (was 835; +1 new L4 rule in `cssRules.test.ts`, 1 updated) |
| `tests/e2e/layout.spec.ts` (the new gate) | **6 passed (17.6 s)** — 4 size×theme sweeps, the fill-controller settling test, the panel reachability test |
| `npm run build` (`VITE_INCLUDE_GALLERY=1 electron-vite build`, what `pree2e` does) | clean, 1.8 s |

Default Playwright project, run in five groups rather than one invocation (lane SUB reported the
whole-suite run tripping the quiet check; every group here was **PASS**, no window on screen):

| Group | Result |
|---|---|
| `preprocess` + `simulator` + `optimizer` + `analyzer` | **23 passed (49.1 s)** |
| `panels` + `panels-forms` + `subjects` + `scene` + `scene-tabs` + `quick-notes` | **22 passed (1.7 m)** |
| `results` + `jobs` + `gallery` + `settings` + `help` + `viewer` | **40 passed (3.4 m)** |
| `smoke` + `screens` + `layout` + `launcher` + `native-launch` + `viewer-real` | **32 passed (1.7 m)** (re-run after the L3 and settling tests were added) |
| re-run after the panel + L3 edits: `panels` + `panels-forms` + the four run pages + `subjects` | **34 passed (1.4 m)** |

`--project=real`, container `ti-toolbox-fad740e5-tit-1`, project `/mnt/000`, every one quiet-check
**PASS**:

| Spec | Result |
|---|---|
| `real/scene-simulator` + `real/scene-optimizer` + `real/scene-analyzer` | **13 passed (21.4 s)** |
| `real/preprocess` + `real/sim` + `real/sim-mti` | **4 passed (2.0 m)** — `sim-mti` is the spec UC's action-bar bug broke |
| `real/analyzer-mesh` + `real/ex` | **3 passed (56.8 s)** |
| `real/nifti-group-average` + `real/nilearn-visuals` + `real/cluster-permutation` | **3 passed (47.5 s)** |
| `real/source` | **1 passed (9.7 m)** — exercises `panels/source`, the page whose Subjects card this lane removed |

State left behind: **none of mine.** No job running or queued on the container at the end; the
container was never restarted or recreated; `derivatives/SimNIBS/sub-101/forward/` was cleaned up
by `source.spec`'s own teardown; the only lane-created state on Dataset 000 remains lane SCA's
`derivatives/ti-toolbox/scene_cache/` and its `.bidsignore` line. `desktop/out/` is left on a
`VITE_INCLUDE_GALLERY=1` build, which is what the container serves and what lanes SCB/SCC's specs
need (SCC's §7).

---

## 8. Open issues and requests

1. **The panel pages are 82–87 % empty in their empty state** (`panel-source` 82.5–84.4 %,
   `panel-subject-info` 85.8–86.6 %), and **Jobs is 99.1 %** with no jobs in the fixture. These are
   empty states, not populated ones, so L5 does not gate them — but "a page whose empty state is a
   sentence in the top-left of a 1224 × 704 box" is exactly what U1 was written against. Owner: a
   follow-up pass on `pages/panels/**` and `pages/jobs/**`; the shape to copy is DESIGN.md §4.4's
   whole-page `EmptyState` with one primary.
2. **`pages/_shared/roi/RoiPicker.tsx` renders the Optimizer's "Cortical / Subcortical / Spherical"
   as a `RadioGroup` while the Analyzer renders the identical choice as a `SegmentedControl`.** One
   idea, two controls, on two pages a user moves between. This lane made them look alike (§5.1's
   pill rows) but did not unify them, because the file is lane B3's. **Exact request:** swap that
   `RadioGroup` for `SegmentedControl` with the same options, and do the same for the Analyzer's
   "Coordinate space (Subject / MNI)" in `pages/analyzer/SphereRows.tsx`.
3. **`pages/_shared/run/useRunPaneController.ts` is now redundant.** Its whole reason for existing —
   `PageLayout`'s inline ref plus the border/content box mismatch — is fixed in `ui/Layout.tsx`
   (§3.1). **Exact request:** delete the wrapper and have the three run pages call
   `usePaneController({ pageId, name: "run" })` directly.
4. **Cross-lane edits this lane made, listed for the record**, all layout-only and all under §4's
   remit but in files the plan assigns to Phase-1 lanes: `pages/_shared/subjects/subjects.css` (the
   header band), `pages/_shared/subjects/SubjectsField.tsx` + `types.ts` (the `minRows` prop and the
   conditional "Why not" column), `pages/analyzer/ResultsPanel.tsx` (the empty table),
   `pages/panels/source/index.tsx` and the three stats panels. Every one is covered by a green spec
   in §7, including `real/source`.
5. **`.run-subject-scroll` is capped at `max-height: 176px`**, which is why Pre-processing's
   `minRows` is 5 and not "however many fit". At 1440×900 the page has ~90 px more room than the
   table will take. A table that grew to its pane would be better on the one page whose job is batch
   selection. Owner: `pages/_shared/run/run.css` + `SubjectsField`.
6. **The dead-space probe under-counts text that is not in its own element.** Fixed in three
   components here (`Toggle.tsx`'s checkbox and radio labels, `Field.tsx`'s label); other components
   may still have the pattern. A cheaper long-term fix is to have `isContent` walk up to the nearest
   qualifying ancestor — deliberately **not** done here (§6.1), and worth a decision by whoever owns
   the instrument after this programme.

---

## 9. How to re-run this lane

```bash
cd desktop
npm run typecheck && npm run lint && npx vitest run
VITE_INCLUDE_GALLERY=1 npx electron-vite build        # what `pree2e` does; the container serves out/

# the gate (mock server, offscreen): L4 + L5a/b/c + L3 on the four run pages, both sizes, both themes
TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/layout.spec.ts

# the instrument: every page, both themes, both sizes, + metrics.json
TIT_E2E_RUN_ID=lay TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/screens.spec.ts

# the diagnostics the rounds were steered by (not gates)
LAY_DIAG=1 LAY_SEL=".form-section-header, .field, .form-grid, .run-work" \
  TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/layout.spec.ts -g "light at 1280x800"
```

`--project=real` **with** the equals sign, and never `npm run e2e` (its `pree2e` hook rebuilds
`out/` and races other lanes) — both as lane SCC recorded.
