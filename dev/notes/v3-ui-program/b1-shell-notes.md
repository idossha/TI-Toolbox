# B1 — Shell + the instrument (lane notes)

Owns: `desktop/src/renderer/app/**`, `ui/Layout.tsx`, `ui/Chrome.tsx`, the layout rules in
`ui/components.css`, `tests/e2e/{_helpers,_metrics,screens,smoke,gallery,launcher}`,
`tests/unit/{shell-*,cssRules,layoutPrimitives,tokenContrast,statusCells-*,navBrandMark}`,
`pages/dev/**`. Program decisions U6–U9 and Q1/Q5; `desktop/DESIGN.md` §2, §9, §11, §12.

---

## 1. What shipped

### The instrument — `tests/e2e/_metrics.ts` (delivered first, ~25 min in)

`deadSpaceRatio` is the u0 §1.1 snippet verbatim, including the `< 25 % of the sampled rect` clause
on background-colour — the clause is the whole metric, since without it a page paints one surface
and scores zero. Plus `paneWidths`, `firstScreenControls`, `captureScreen`, `writeMetrics`,
`artifactDir`.

Two additions beyond the u0 contract, both because a checklist item was otherwise unmeasurable:

- `PageMetrics.statusCells` — the ids in the bar, read from `data-status-cell`. §12.4 item 6 ("only
  registered cells, no placeholder dashes") is a claim about the *set* of cells; a screenshot cannot
  be asserted on and a dash would pass a text check while still being the bug.
- `PageMetrics.pageHeaderHeight` — §8's 0 px budget outside Settings and Help, as a number.

`captureScreen` takes both u0 obligations seriously: it waits out `.skeleton` (a skeleton is content
to the metric and would flatter the ratio) and resets every `[data-page-work-scroll]` to the top
before sampling, because `elementFromPoint` reads the viewport.

### `app/statusCells.ts` + the shell rendering only registered cells (U8)

`useStatusCells(cells)` registers per component instance (`useId`) and unregisters on unmount, so a
stale cell from a page you left is unwritable. Empty values (`null` / `undefined` / `""`) are
dropped at registration, not at render, so the DOM and the metric agree. `AppStatusBar` lost its
`viewerStatus` import and all three placeholder cells; it now renders the registry plus the shell's
fixed right cluster (connection, `tit x.y · api vN`). `StatusCell` gained an optional `id` →
`data-status-cell`. `Shell.tsx` no longer imports `useViewerReadout` at all.

### `PageLayout` v3 (U1)

`variant="run" | "browse" | "bleed"` with `standard` → `run` and `full-bleed` → `bleed`;
`rightPane`/`rightPaneKind`/`rightPaneWidth`/`rightPaneCollapsible`/`rightPaneDefaultCollapsed`/
`onRightPaneWidthChange`/`rightPaneMin|MaxWidth` added; `inspector`, `contextPanel`,
`inspectorWidth`, `onInspectorResize`, `inspectorMin|MaxWidth`, `resizableInspector` all still work.
`data-testid="page-work"` on the work pane; `data-testid="page-right-pane"` on the right pane and
**absent from the DOM** when there is none or it is collapsed.

CSS changes, all in the layout section of `components.css`:

- **`.page-layout-main` lost `max-width: 880px`.** One declaration; it is the whole of U1.
- `.page-layout-panel` is `var(--right-pane-w)` — 360 on `.page-layout`, 400 under
  `@media (min-width: 1440px)`; `[data-pane-kind="preview"]` is `clamp(380px, 40%, 560px)`; an
  explicit width sets `data-pane-width="fixed"` and wins over the percentage.
- `.page-layout-run .page-layout-body { gap: 0 }` + a styled 6 px `.page-layout-inspector-handle`,
  because §2.1's arithmetic spends exactly six pixels between the panes and a `--space-4` gap on
  each side of the handle would take 32 px off the work pane.
- `.page-layout-browse` negates the shell padding like `bleed` does.
- `--page-pad` is 16 below 1440 and 24 at or above it, set on `.shell` (not in `tokens.css`, whose
  single definition of the token stays). That step is load-bearing for §2.1's numbers:
  1064 − 2×16 − 360 − 6 = 666 and 1224 − 2×24 − 400 − 6 = 770.

The run pane is **always** resizable now: a page passes `onRightPaneWidthChange` to make the width
*stick*, not to make it draggable. `InspectorHandle` reads the pane's live rect at gesture start, so
a pane sized by CSS drags from where it actually is.

### U6 — the slim context bar

Presence chips are gone from the subject crumb (they collided with the batch crumb at 1280,
`results-light.png`, u0 §1) and the `+ Add subjects` crumb is gone from the bar. Batch is a
collapsed section **inside** the switcher popover, so §2.3's "batch selection stays in the switcher
popover" holds and the 5 % case still costs one click. The bar is now: project · subject · ⌘K ·
connection · running.

### U7 + Q1 — the flat rail

`registry.ts` is rewritten around two arrays. `NAV_ORDER` (subjects, preprocess, simulator,
optimizer, analyzer, results, viewer, jobs) **is** the rail, the order and the ⌘-numbers;
`PINNED_ORDER` is settings + help. A page in neither is palette-only — which is how §9's "there is
no Panels group and no Tools group" is implemented, with `system`, `optimizer-ex`, `dev` and every
`panel-*` still routable and still in ⌘K. `NavSectionId` is now `"workflow" | "pinned"`, sections
carry no `label` at all, and `PageDef.navGroup`/`.shortcut`/`.order` are legacy fields the rail
ignores.

`navSlotOf("optimizer-flex")` returns `"optimizer"` **only while `pages/optimizer` is undiscovered**
— it retires itself, and it already has: B3's page landed during this lane's run and the rail picked
it up with no edit here. `optimizer-ex` has no slot and left the rail.

Q1 is implemented as decided: `LABEL_RAIL_QUERY = "(min-width: 1440px)"`, icons below. The rail mode
is a class (`.nav-rail-icons`) React sets, not a media query, because the mode now has two inputs —
the breakpoint and `PageDef.railMode: "icons"`, which any page may force. That also retires the
source-order dance ra_12 #6 needed: two classes beat one wherever the rule sits.

### Q5 / U9

⌘1–⌘8 = `NAV_ORDER`, ⌘9 = Settings, ⌘, = Settings via `SHORTCUT_ALIASES`, `?` = Help sheet. The
number is derived from the index, so nav, palette and sheet cannot disagree. `theme/store.ts`
exports `DEFAULT_THEME = "light"`; `system` is still a choice, no longer the default.

### Gallery

`pages/dev/DensityGallery.tsx` gains a **Shell ruler (v3)** block that measures the live nav rail,
content box, status bar and page header, and registers three demo status cells — one of them with a
`null` value, which is *not* rendered. The U8 mechanism is visible on the page that documents it.

---

## 2. The dev loop

Every run: `TIT_E2E_RUN_ID=b1-r<n>-$RANDOM bash scripts/e2e-quiet-check.sh npx playwright test …`.
All runs **PASS** the quiet check (no Electron/Chromium window reached layer 0).

### Round 1 — `b1-r1-27877`, 40 captures

First measurement with the instrument. Numbers (light; dark identical to ±0.01 everywhere):

| page | dead @1280 | nav | work | right | gap | header | status cells |
|---|---|---|---|---|---|---|---|
| subjects | 0.60 | 56 | 1224 | 0 | 0 | 0 | counts |
| preprocess | 0.80 | 56 | 832 | 360 | **0** | 0 | — |
| simulator | 0.78 | 56 | 832 | 360 | **0** | 0 | — |
| optimizer | 0.76 | 56 | 832 | 360 | **0** | 0 | — |
| analyzer | 0.81 | 56 | 832 | 360 | **0** | 0 | — |
| results | 0.53 | 56 | 734 | 490 | 0 | 0 | counts |
| viewer | 0.00 | 56 | 1224 | 0 | 0 | 0 | ras, space |
| jobs | 0.88 | 56 | 1192 | 0 | 0 | 0 | jobCounts |
| settings | 0.84 | 56 | 1192 | 0 | 0 | 28 | — |
| help | 0.21 | 56 | 1192 | 0 | 0 | 28 | — |

Self-critique against §12.4, one line each:

1. **fail** — dead space is 0.53–0.92 against limits of 0.20–0.25 on six of ten pages. All of it is
   page content (the shell contributes the 16 px padding band); `viewer` 0.00 and `help` 0.21 pass.
2. **pass** — page header 0 px on all eight workflow pages; 28 px on Settings and Help, which §8
   excepts (and 28 ≪ v1's 86).
3. **n/a to this lane** — the shell renders no chips.
4. **pass** — the status bar's version cell is `tabular-nums`; the shell prints no other number.
5. **pass** — `tokenContrast.test.ts` green; no literal colour was added to `shell.css` or the
   layout rules.
6. **pass** — no `ras`/`space`/`renderer` on subjects, results, jobs or the run pages; the two
   shell cells are on every page; nothing renders a dash.
7. **pass** — `firstScreenControls().hidden` is empty on all four run pages (18/18, 14/14, 15/15,
   26/26 visible).
8. **fail** — ⌘⇧I had no test, and the pane was not resizable without a page callback.
9. **pass** — no copy added beyond "Add subjects to this run" / "Also running N more".
10. **fail** — `smoke` and `gallery` still asserted page headings other lanes had (correctly)
    deleted, and `gallery` asserted the U8 bug (`status-space` reads "—" off the Viewer).

Fixed for round 2: `gap: 0` → the run pane always renders the 6 px handle with `.page-layout-run`
carrying no body gap; ⌘⇧I got a hidden test; the three stale specs rewritten to DOM state.

One round-1 reading was a **measurement artifact, not a defect**: preprocess/simulator/analyzer
reported `right: 360` at 1440 where optimizer reported 400. A direct probe found all four at 400 —
the shared `out/` had been rebuilt by another lane between my build and the capture. Recorded
because it is the failure mode of a shared build directory, and the fix is to rebuild immediately
before a capture (round 2 and 3 do).

### Round 2 — `b1-r2-24849`, 40 captures

| page | dead @1280 / @1440 | nav 1280/1440 | work | right | gap |
|---|---|---|---|---|---|
| subjects | 0.60 / 0.65 | 56 / 216 | 1224 | 0 | 0 |
| preprocess | 0.80 / 0.83 | 56 / 216 | **826 / 770** | **360 / 400** | **6** |
| simulator | 0.78 / 0.80 | 56 / 216 | 826 / 770 | 360 / 400 | 6 |
| optimizer | 0.75 / 0.80 | 56 / 216 | 826 / 770 | 360 / 400 | 6 |
| analyzer | 0.81 / 0.86 | 56 / 216 | 826 / 770 | 360 / 400 | 6 |
| results | 0.53 / 0.59 | 56 / 216 | 734 | 490 | 0 |
| viewer | 0.00 / 0.00 | 56 / 216 | 1224 | 0 | 0 |
| jobs | 0.88 / 0.92 | 56 / 216 | 1192 / 1176 | 0 | 0 |

Items 1 and 8 and 10 re-checked: **8 pass** (`smoke.spec.ts` now asserts that ⌘⇧I removes
`page-right-pane` from the DOM, that the work pane grows by more than 300 px, that it returns to the
same width, and that a page with no pane does not swallow the chord); **10 pass** (smoke 8/8,
gallery 2/2, launcher 13/13 green under the quiet check); **1 unchanged** — the residual is page
content and belongs to B2/B3/B4/B6.

Reading `preprocess-dark-1280x800.png` found one shell defect no ratio catches: the right pane's
content sat ~4 px from the handle's rule. Fixed in round 3 by moving the gutter into the pane
(`.page-layout-run .page-layout-panel { padding-left: var(--space-3) }`) — it is shell furniture, so
it is declared once rather than in each page's pane component.

### Round 3 — `b1-r3-4794` then `b1-r3b-28173` (final), 40 captures each

Final numbers, light; dark differs by ≤ 0.01 on every page and the panes are identical:

| page | dead @1280 | dead @1440 | nav 1280/1440 | work 1280/1440 | right | gap | header | status cells |
|---|---|---|---|---|---|---|---|---|
| subjects | 0.60 | 0.65 | 56 / 216 | 1224 / 1224 | 0 | 0 | 0 | counts |
| preprocess | 0.80 | 0.83 | 56 / 216 | 826 / 770 | 360 / 400 | 6 | 0 | planCost |
| simulator | 0.78 | 0.80 | 56 / 216 | 826 / 770 | 360 / 400 | 6 | 0 | — |
| optimizer | 0.76 | 0.80 | 56 / 216 | 826 / 770 | 360 / 400 | 6 | 0 | — |
| analyzer | 0.81 | 0.86 | 56 / 216 | 826 / 770 | 360 / 400 | 6 | 0 | — |
| results | 0.53 | 0.59 | 56 / 216 | 734 / 734 | 490 | 0 | 0 | counts |
| viewer | 0.00 | 0.00 | 56 / 216 | 1224 / 1224 | 0 | 0 | 0 | ras, space, renderer |
| jobs | 0.88 | 0.92 | 56 / 216 | 1192 / 1176 | 0 | 0 | 0 | jobCounts |
| settings | 0.84 | 0.86 | 56 / 216 | 1192 / 1176 | 0 | 0 | 28 | — |
| help | 0.21 | 0.21 | 56 / 216 | 1192 / 1176 | 0 | 0 | 28 | — |

Shell-owned checklist items 2, 4, 5, 6, 7, 8, 9, 10 all pass. Item 1 is not this lane's to close.

---

## 3. Three consequences of Q1 the program has to decide about

Q1 (icons below 1440, labels at or above) is implemented as instructed. It moves three numbers that
`DESIGN.md` §2.1/§12.3 and `wireframes.md` §9 state, and the docs are now wrong where they disagree
with the measurement:

1. **The content box is 1224 px at *both* sizes** (1280 − 56 = 1224; 1440 − 216 = 1224). §2.1's
   "content box 1064 × 704 at 1280" is superseded. Every per-page pane number derived from 1064
   moves with it.
2. **The Results preview is 490 px at 1280, not 426.** It is `clamp(380px, 40%, 560px)` of the
   content box exactly as §2.1 specifies; 40 % of 1224 is 490. §12.3's `preview 426 ± 8` should
   read `490 ± 8` at both sizes, or the clamp's basis has to change. B4's spec asserts one of them.
3. **The run pages' work pane is *narrower* at 1440 (770) than at 1280 (826).** The window gains
   160 px; the labelled rail takes 160, the wider run panel 40 and the bigger padding 32. Both
   numbers clear §12.3's ≥ 660 floor and the form is two-up (> 760) at both sizes, but "a bigger
   window gives you a smaller form" is a wart worth an explicit decision — the levers are the
   1440 `--page-pad` step and the 360 → 400 run-panel step, both mine to change on request.

And one for **B5 / the Viewer**: at 1440 the labelled rail leaves the embed 1224 px, under the
wireframes' `≥ 1360` target (it clears the 1280 target of ≥ 1200 comfortably). The mechanism is in
place — `PageDef.railMode: "icons"` forces the 56 px rail at every width and the Viewer is the page
§9 allows to use it. It needs one line in `pages/viewer/index.tsx`:

```ts
railMode: "icons",
```

which would make the embed 1384 at 1440 and 1224 at 1280. I did not add it: it is B5's file, and
"the Viewer needs no special case" was part of the Q1 ruling.

## 4. Needs from other lanes

- **B2 / B3** — `simulator`, `optimizer` and `analyzer` register **no** status cells; §11.1 asks all
  four run pages for `lastJob` (priority 10) and `planCost` (20). `preprocess` registers `planCost`
  only. One `useStatusCells([...])` per page closes it.
- **B2 / B3 / B4** — do **not** add left padding to a right-pane component: the run pane's gutter is
  `.page-layout-run .page-layout-panel { padding-left: var(--space-3) }` in `ui/components.css`, and
  a second one doubles it.
- **B4** — `tests/unit/outputsTree-build.test.ts` fails `npm run typecheck` (3 × TS18048/TS2345 on
  possibly-undefined fixture lookups) and `tests/e2e/subjects.spec.ts:11` fails `npm run lint`
  (`'gotoPage' is defined but never used`). Both are the only non-green items in the repo-wide gates.
- **Everyone** — rebuild (`npm run pree2e`) immediately before a capture run. `out/` is shared and
  another lane's rebuild between your build and your measurement produces numbers from a bundle you
  did not write; that is what round 1's phantom `right: 360` was.

## 5. Where the artifacts are

`desktop/tests/e2e/artifacts/b1-r{1,2,3,3b}-*/` — 40 PNGs and `metrics.json` per run. `b1-r3b-28173`
is the final one. `metrics.json` carries `deadSpaceRatio`, `samples`, `dead`, `panes`,
`firstScreenControls`, `statusCells`, `pageHeaderHeight` and the screenshot name per row.
