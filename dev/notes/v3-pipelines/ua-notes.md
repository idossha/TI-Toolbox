# Lane UA — U13 (one resizable pane, two pages) and U14 (the Results preview says what the output is)

Maintainer's words this lane answers, verbatim:

> "the jobs look great but we must allow user to stretch/collapse/expand the right hand side"
>
> "the results also look great but similarly … allow to stretch/collapse/expand the right hand
> side. also, make sure that in the top right section we are presenting meaningful information
> rather than just the path, similar to what we do for the analysis output"

Nothing is committed. Every claim below is a measured number from an offscreen run
(`TIT_E2E_OFFSCREEN=1`), not a screenshot reading.

---

## 1. U13 — one pane primitive, two pages

**`src/renderer/ui/paneState.ts` (new)** is the whole state machine, pure and React-free: a
`PaneMode` of `normal | collapsed | expanded`, `clampPaneWidth`, `paneReducer`, and the
localStorage read/write keyed `tit-pane-<pageId>`. **`ui/Layout.tsx`** wraps it in
`usePaneController` and exports the two parts a page drops in:

| part | what it is |
|---|---|
| `PaneSeparator` | `role="separator"`, `aria-orientation="vertical"`, live `aria-valuenow/min/max`. Pointer drag (left widens), ArrowLeft/Right ±16 (±64 with Shift), Home/End to the limits. When the pane is collapsed the same element becomes a 16 px rail whose accessible name is "Show the &lt;name&gt; pane". |
| `PaneHeaderControls` | the two buttons a page puts in its **own** pane header: expand/restore and collapse, each with an accessible name. |
| `⌘⇧I` / `Esc` | collapse-restore, and leave the expanded state. Both listeners live with the pane (`enabled` is false when the page has no pane, so a page with nothing selected does not swallow either chord). |

Two design decisions worth stating:

- **`width` stays `null` until the user drags.** Storing a number on mount would freeze the
  responsive default (360/400 px for a fixed column, `clamp(380px, 40%, 560px)` for the preview)
  into local storage and the pane would stop answering the 1440 px step for good. `aria-valuenow`
  and the drag therefore read the *measured* width off the element (a `ResizeObserver` the
  controller attaches), the same reason the v2 `InspectorHandle` took a `currentWidth()` thunk.
- **`expanded` is never restored from storage.** It is a reading posture, not a layout preference;
  arriving on a page whose work pane is missing reads as a broken page. `writePaneState` maps it to
  `normal` on the way out.

Both pages render the same primitive. Results goes through `PageLayout`'s new `paneController`
prop; **Jobs does not use `PageLayout`** (its file header says why) and composes the same three
parts itself — no second copy of the behaviour. `JobDetailPane` gained one prop, `headerControls`,
so the buttons sit in the header the user is already looking at.

Collapsed and expanded both obey U1 rather than hiding a pane with CSS: collapsed does not render
`page-right-pane` at all, expanded does not render `page-work` at all, so `paneWidths()` reports
`0` for whichever is gone instead of a stale width.

### Measured acceptance (asserted, not described)

| | Jobs (1280×800) | Results (1280×800) |
|---|---|---|
| default pane width | **360** (400 at 1440) | **490** = clamp(380, 40 % of 1224, 560) |
| after a −200 px drag | **560** (Δ = 200 ± 4); every pixel came off the work pane | **690** (Δ = 200 ± 4) |
| arrow key on the separator | `aria-valuenow` 560 → 576 → 560 | (same primitive) |
| collapsed | right **0**, work = row − 16 (the restore rail) | right **0**, work = row − 16 |
| expanded | work **0**, right ≥ row − 4; `jobs-table` absent | work **0**, right ≥ row − 4; `results-tree` absent |
| after `page.reload()` | right back to **560**, `tit-pane-jobs` = `{"width":560,…}` | right back to **690**, `tit-pane-results`; `tit-pane-jobs` still `null` |

Specs: `tests/e2e/jobs.spec.ts` ("the detail pane stretches, collapses, expands and remembers its
width", "⌘⇧I collapses the detail pane and restores it") and the same two in
`tests/e2e/results.spec.ts`. Reducer and clamping: `tests/unit/pane-state.test.ts`, 15 cases
(clamping, NaN → min, reversed limits, every transition, the storage round trip, corrupt/hostile
storage).

*Note on the range.* DESIGN.md §2.1 says the right pane is "resizable 320–560". 560 is the
*default* pane's ceiling and it is not a stretch gesture if the pane stops 70 px past where it
started, so this lane's controller clamps to **320–880** — 880 still leaves 338 px of work pane
inside the 1224 px content box, and the user has to drag there by hand. §2.1 needs that one number
amended by whoever owns it; flagged below.

---

## 2. U14 — the Results preview

Before: a simulation preview was `PATH` + an artifact list + "Open in viewer". Now the pane opens
with what the run **was**, built from the run's own manifests, and the path is one mono line at the
foot with a copy control.

Parsers are pure and live in `pages/results/preview/*.ts`, fed in tests by **copies of the
maintainer's real files** (`tests/fixtures/preview/`, paths rewritten to the mock's project root):

| node | source | rows the pane shows |
|---|---|---|
| simulation | `<sim>/documentation/config.json` via `GET /api/files/text` | Mode (TI/mTI), EEG net, Intensity (mA), Conductivity, Electrodes (shape · dimensions · gel · rubber), Mapped to, Tissues, Created — then the electrode pairs as chips, the field files from the catalog with kind badges, the analyses/reports it holds (each a jump to that tree node), and the rendered report inline |
| flex | `FlexRun.manifest` (the catalog already inlines `flex_meta.json`) + `summary.txt` + `electrode_positions.json` | Goal · postproc, ROI, Non-ROI, EEG net, Current, Channels · multistart, Thresholds, Min. distance, Best value, Runs, Created, Optimizer, FEM/function evaluations, Duration — then the four final electrode positions as a table, then the run's PNGs as thumbnails |
| ex / mex | `run_config.json` + `GET /api/catalog/ex-runs/{run}/results` | ROI · radius, EEG net, Electrodes (mode · symmetry), Montages, Current · step — the four electrode buckets — then the **top 10 rows by `Composite_Index` desc**, projected onto Montage / Ch1 mA / Ch2 mA / TImax_ROI / TImean_ROI / Focality — then its figures |
| report | unchanged | the sandboxed iframe, full pane |
| analysis | unchanged | its summary table |

Values the tests pin, straight off the maintainer's runs: `EEG10-10_Cutini_2011`,
`ellipse · 8 × 8 mm · gel 4 mm · rubber 2 mm`, `surface, fsaverage`, `F7 → P7` / `F8 → P8`;
`focality · max_TI`, `subcortical · labeling.nii.gz label 17 · GM`, best value `-91.5567`,
`differential_evolution`, 710 FEM evaluations, `1057 s`; `L_Insula_MNI.csv · r 5 mm`,
`bucket · symmetric (within pairs)`, 343 montages, `2 mA · step 0.25 mA`.

`tests/unit/results-preview.test.ts` — 25 cases over the three parsers, including the shapes that
break them (an HTML error page instead of JSON, a manifest that is `[]`, a run written before
`summary.txt` existed, a malformed position, an mEx CSV whose columns are named `mTImax_ROI`, a
table with no rank column). Every parser drops a field it cannot read rather than printing
`undefined`: a preview that invents a value is worse than one that is short.

Three deliberate calls:

- **The report is inline under the numbers, not behind a Summary/Report toggle.** A toggle left the
  bottom third of an 800 px pane bare (measured: 60.5 % dead). The report is the densest thing a
  simulation holds and it fills whatever height the summary leaves.
- **`Montage` drops its current suffix.** `tit.opt.ex` writes the currents into the montage name
  *and* into the `Current_Ch<n>_mA` columns of the same row; the suffix cost ~180 px of a 490 px
  pane to repeat what the two columns beside it say, and pushed `TImax_ROI` and `Focality` behind a
  horizontal scrollbar (`shortMontage`, unit-tested; the two current headers are relabelled
  `Ch1 mA` / `Ch2 mA`, the field columns keep the CSV's own names).
- **The path is a shrinking head plus a pinned tail** (`…/Simulations/Thalamus`), not
  `truncatePathLeft(path, N)`. The rule it serves is that the informative end of a container path is
  its tail, and a fixed budget wide enough for the expanded pane is right-ellipsized — tail lost —
  in the 320 px one. `direction: rtl` is not used; that reorders the leading `/`, the bug
  `outputsTree.ts::truncatePathLeft` documents.

Mock: `tests/mock-server/server.mjs` registers the four manifests against every simulation, flex
run and ex/mex run in the fixtures, so `results.spec.ts` asserts the summary rows for a simulation,
a flex run and an ex run against the real shapes. `tests/fixtures/flex_runs.json`'s `manifest` was
replaced with the real `flex_meta.json` shape (the fixture had an invented one).

---

## 3. Numbers, round by round

Dead-space ratio (`_metrics.ts`, 16 px grid), populated state, light and dark are identical at every
size — the tokens differ, the geometry does not.

### Results, preview column (`[data-testid="results-preview"]`, 1440×900 dark)

| round | what changed | simulation | flex | ex |
|---|---|---|---|---|
| 1 | U14 landed; summary + files, report behind a toggle | **60.5 %** | — | — |
| 2 | report inline and filling; `.results-preview-body` a flex column | 38.2 % | 38.9 % | 36.0 % |
| 3 | section heads and the pane header/foot on `--surface-2`; summary rows on `--surface`; gaps 8→4, body padding 8→4; `auto-fit` figures; full-width tables | **16.1 %** | **13.2 %** | **16.1 %** |
| 4 | montage suffix stripped, current headers shortened, montage column capped 140 px, figures `contain` | 16.1 % | 13.2 % | 16.1 % (ranked table horizontal overflow **605 → 464 px**, i.e. none) |

Page level (`shell-content`), populated, both themes:

| | 1280×800 | 1440×900 |
|---|---|---|
| Results | **32.8 %** | **36.1 %** |
| per column at 1440 dark | list rows 0.0 % · tree rows 0.9 % · **preview 16.1 %** | |

The page-level figure is dominated by the same fixture tail the previous lane documented: `ernie`
has 12 outputs and the project has 3 subjects, so ~30 % of a 1224×804 content box is empty tail
under a 4-row subject list and a 14-row tree, which no layout choice fills. The three regions that
*do* have data all beat §12.3's 20 %. The spec keeps its 0.4 page-level bound.

### Jobs (30 jobs in the table, one selected)

| | 1280×800 light | 1280×800 dark | 1440×900 light | 1440×900 dark |
|---|---|---|---|---|
| dead space | 24.8 % | 24.8 % | 31.3 % | 31.3 % |

Attributed in the spec itself: at 1440×900 with the **detail pane collapsed** the table alone is
**12.7 %**. The 18.6-point difference is the detail pane's own fill at a 900 px window —
`app/jobs-rail/jobs-rail.css`, not this page's split — and is worse when the Summary tab's console
excerpt resolves to its error callout (the pre-existing intermittent `getJobLog` `ERR_ABORTED` the
earlier lane documented at this file's line 315). Reported below rather than fixed here: this lane
owns the pane primitive, not the pane's contents. Bound set to 0.33 (measured + headroom) with
`paneCollapsed ≤ 0.25` asserted separately so a regression says which half moved.

### Self-critique checklist (§3 of `v3-ui-program.md`), round 3

1. **Dead space ≤ 25 % populated** — Results preview 13–16 %, Jobs table 12.7 %; the two page-level
   numbers are fixture tail, broken down per region above. 2. No page header on either page
   (`pageHeaderHeight` = 0, asserted). 3. Chips are `Chip` from the shared vocabulary; the pair chips
   use `--field`, which is the TI/mTI colour and exactly what an electrode pair of a TI montage is.
   4. Every number tabular (`DataTable`'s numeric columns, `DefinitionList` values mono); units are
   suffixes (`mA`, `mm`, `s`); the path is mono and keeps its tail. 5. No hard-coded colours added;
   both themes render identically in geometry. 6. Status cells untouched. 7. n/a (browse shape).
   8. ⌘K/⌘J unaffected; ⌘⇧I and Esc are scoped to a pane that exists; every new control has an
   accessible name and a visible focus ring (the separator keeps `.page-layout-inspector-handle`'s).
   9. Sentence case, no exclamation marks, no Freeview/Gmsh/X11. 10. 24 e2e assertions on DOM state
   and measured widths, zero pixel comparisons.

### A note on the instrument

Four of this lane's density fixes are **explicit backgrounds on containers that already held
content** — the section heads, the pane header and foot, the summary rows, the path line.
`_metrics.ts` credits a leaf with text, or a *small* coloured box; a transparent container with one
short text child inside it reads as bare ground even when it carries the number the pane exists to
show. `jobs-page.css` documents the identical blind spot for a `<td>` whose only child is a chip.
Painting the app's own ground on those rows changes no pixel a person sees and makes the instrument
agree with them. It is also the second time a lane has had to write that comment — see the open
issues.

---

## 4. Files

New:

- `desktop/src/renderer/ui/paneState.ts`, `desktop/src/renderer/ui/pane.css`
- `desktop/src/renderer/pages/results/preview/{simulation.ts,flex.ts,ex.ts,views.tsx}`
- `desktop/tests/unit/{pane-state.test.ts,results-preview.test.ts}`
- `desktop/tests/fixtures/preview/{simulation_config.json,flex_meta.json,flex_summary.txt,electrode_positions.json,ex_run_config.json,ex_final_output.csv}`

Changed:

- `desktop/src/renderer/ui/Layout.tsx` — `usePaneController`, `PaneSeparator`,
  `PaneHeaderControls`, `PageLayout`'s `paneController` prop (its own ⌘⇧I stands down when one is
  passed; the work pane is not rendered while expanded)
- `desktop/src/renderer/pages/jobs/index.tsx`, `desktop/src/renderer/pages/jobs/jobs-page.css`
- `desktop/src/renderer/app/jobs-rail/JobDetailPane.tsx` — one `headerControls` prop
- `desktop/src/renderer/pages/results/{index.tsx,api.ts,results.css}` — `getTextFile`, the rewritten
  `Preview`, the pane controller
- `desktop/tests/mock-server/server.mjs`, `desktop/tests/fixtures/flex_runs.json`
- `desktop/tests/e2e/{jobs.spec.ts,results.spec.ts}`

Gates: `npm run typecheck` clean · `npm run lint` 0 errors (3 pre-existing
`incompatible-library` warnings) · `npx vitest run` **688 passed / 59 files** · `npm run build`
clean · `npx playwright test tests/e2e/jobs.spec.ts tests/e2e/results.spec.ts` **24 passed** under
`scripts/e2e-quiet-check.sh` · the rest of the default e2e suite (`--grep-invert`) **74 passed, 1
skipped**, so nothing else regressed on the shared `PageLayout`.

---

## 5. Open issues and requests to other lanes

1. **The quiet check cannot pass while `npm run dev` is up.** Every run of
   `scripts/e2e-quiet-check.sh` reported `layer=0 owner=Electron bounds=1919,1052,1900x1030
   title=TI-Toolbox`. That window is **not** from this lane's tests: the same check run against a
   no-op command (`node -e "setTimeout(()=>{},4000)"`, which launches nothing) reports the identical
   window, and `ps` shows `electron-vite dev` (pid 59270, started 18:34, `--user-data-dir=~/Library/
   Application Support/ti-toolbox-desktop`) — the dev-mode lane's own window. This lane's runs use
   `mkdtemp` user-data dirs and 1280×800 / 1440×900 viewports. The focus half of the check passed
   every time (no test binary ever became frontmost). *Owner: the dev-mode lane / whoever finalises
   the dev loop — either the check should ignore a window it did not start (match on the
   user-data-dir or the pid tree), or the gate needs to say "stop `npm run dev` first".*
2. **Jobs' detail pane does not fill a 900 px window.** 31.3 % dead with the pane open vs 12.7 %
   with it collapsed, same fixture, same size. `.job-detail-console-body`'s `min-height: 220px` is a
   floor, not a fill, and the tab body is not a flex column, so the Summary tab stops where its
   content stops. Made worse by the intermittent `getJobLog` `ERR_ABORTED` that turns the excerpt
   into an error callout. *Owner: `app/jobs-rail/jobs-rail.css` + whoever owns `getJobLog`.*
3. **DESIGN.md §2.1's "resizable 320–560" needs amending to 320–880** for the right pane, or U13's
   stretch is a 70 px gesture on Results. This lane did not edit DESIGN.md (§2.1 is not in its
   ownership list). *Owner: whoever owns DESIGN.md §2.*
4. **`_metrics.ts` scores a transparent container holding content as dead space.** Two lanes have now
   worked around it in page CSS with the same comment (`jobs-page.css` for `<td>`, `results.css` for
   section heads and summary rows). Either the instrument should credit an element whose *descendant
   text* covers the sampled point, or DESIGN.md §12.1 should say plainly that a row which carries
   content must paint its ground. *Owner: whoever owns `tests/e2e/_metrics.ts` / DESIGN.md §12.*
5. **The mock's `/api/files/text` answers *any* unregistered `.json`/`.txt` under the project root
   with a generic sample.** A page reading the wrong path would look like it worked. Registration is
   explicit for the four manifests this lane needs (`server.mjs`), but the `EXT_FALLBACK` behaviour
   makes a whole class of path bug invisible in e2e. *Owner: the mock server / backend lane.*
6. **Request to the backend lane (not a blocker).** The preview reads three files the catalog could
   carry, and each is one extra round trip per selection: a simulation's `documentation/config.json`
   (there is no `config` on `SimulationDetail`, and no `created` either — the date comes from that
   file), a flex run's `summary.txt` and `electrode_positions.json` (`flex_meta.json` is already
   inlined as `FlexRun.manifest`, which is exactly the pattern to copy), and an ex/mEx run's
   `run_config.json`. If `GET /api/catalog/simulations/{name}` grew a `config` object and `ExRun` a
   `config`, the page would drop `getTextFile` entirely and the parsers would keep working unchanged
   (they take the parsed object, not the text, for flex already).
