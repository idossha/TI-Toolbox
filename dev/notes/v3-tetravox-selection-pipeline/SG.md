# Lane SG — one selection grammar, the receipt, and the shared existing-outputs question

Plan of record: `dev/notes/v3-tetravox-selection-pipeline-plan.md` §1-C (C1–C5). Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. **Nothing committed.**

The ask, in the maintainer's words: *"in the TI toolbox 2.5.0 we had a great logic for selecting
multiple jobs … right now it's too convoluted for the users to choose and to understand the jobs
that they're selecting."*

## 1. What was wrong, measured

v3 had **five** ways to choose several things, and none of them agreed on what a click did:

| where | idiom | the ambiguity |
|---|---|---|
| `SubjectsField` | row-click **and** a checkbox in that row | two gestures one pixel apart, both toggling, neither saying which you were about to hit; a row-click *added*, so "these three, not those" took three clicks and an untick |
| `ParticipantsField` | the same table, deliberately with no filter and no bulk buttons | a twelve-row paired design was twelve trash clicks |
| electrode pairs | two `Select` combos per pair | a third keyboard, a third way to search 185 names |
| ex/mEx buckets, ROI regions | `MultiSelect` chips | one add per popover; the closed control truncated at ~2 chips, so it could not answer "what is in E1+?" |
| Jobs | *no selection at all* | cancelling five queued jobs meant opening five of them |

And the confirmation was in the wrong place: the plan **grid** (right pane) states coverage, the
action bar's digest states a count — neither says *which* jobs, and neither is next to Run. The
existing-outputs question had four different wordings across the four run pages, two of which
offered no way to run only the new jobs.

## 2. What it is now

**One primitive** — `ui/SelectionList.tsx` (+ `ui/selection.css`, exported from `ui/index.ts`):

- click = select exactly one (and park the range anchor); ⇧-click = the inclusive range from the
  anchor, **adding**; ⌘/Ctrl-click = toggle one; ⌘A = every **visible** row; Esc = clear the
  visible rows;
- a visible **checkbox column** — the same toggle, so mouse-only and touch users never need a
  modifier and nobody has to guess whether a row is selected;
- an always-on **filter**, `All · None` as the only bulk buttons, and an `N of M selected` badge
  that is the whole status line;
- **filter interplay**, the rule with teeth: a row the filter hides keeps its state. `All` adds the
  visible rows, `None` removes only the visible rows;
- **selection order is the submission order** (`optimizer`'s `flexSubmissions`, `simulator`'s rows);
- keyboard: ↑/↓/Home/End move a roving `aria-activedescendant`, ⇧+↑/↓ extends, Space/Enter toggles;
- ARIA: a `role="listbox" aria-multiselectable` box of `role="option"` rows — or `role="grid"` with
  `role="row"` rows where the list is a genuine multi-column table (the Jobs page), which is the
  correct pattern for that shape and keeps every existing jobs spec's `getByRole("row")` working;
- **virtualised** past 150 visible rows (spacer rows carry the height), and **measured ground rows**
  below that, so a short or empty list still shows the shape of the list;
- `bulkExclude` — rows `All`/⌘A skip while they stay individually selectable. That is the subject
  grammar's J3 rule ("an ineligible subject keeps its checkbox, because its reason is what Run then
  prints") expressed once instead of re-derived per page.

**Two shapes, one model.** `SelectionList` where a page has room (subjects, participants, jobs);
`SelectionPicker` — the same list in a dialog behind a trigger that states the selection in words
(`F7, P7, +3 more`) — where it does not (ex/mEx buckets, the electrode pool, ROI regions, and each
slot of an electrode pair in `mode="single"`).

**The receipt** (`pages/_shared/run/Receipt.tsx`): *"This will run 6 jobs:"*, the first 15 rows,
`… and K more`, and the existing-outputs line — the last thing in the work column, immediately
before the sticky action bar, on all four run pages. Derived from the same `planModelFrom` rows the
grid draws, so **the grid, the digest and the receipt cannot disagree**.

**One existing-outputs question** (`pages/_shared/run/ExistingOutputsDialog.tsx`): *Skip / Replace
and rerun / Cancel*, with Skip the default and its label counting the batch (`Skip 3, run 1`). It
replaced four different dialogs; two of them had no Skip at all, so finishing a half-done batch
meant deselecting its finished rows by hand.

**Jobs** rows are selectable with the same grammar, and `Cancel N` acts on the selection (only the
non-terminal ones are sent). Selecting exactly one row still opens its detail pane, so the gesture
people already have keeps working.

## 3. Files

New:
- `desktop/src/renderer/ui/SelectionList.tsx`, `desktop/src/renderer/ui/selection.css`
- `desktop/src/renderer/pages/_shared/run/Receipt.tsx`
- `desktop/src/renderer/pages/_shared/run/ExistingOutputsDialog.tsx`
- `desktop/src/renderer/pages/jobs/JobsSelectionTable.tsx`
- `desktop/tests/unit/selection-model.test.ts`, `desktop/tests/unit/run-receipt.test.ts`
- `desktop/tests/e2e/selection.spec.ts`

Changed (source):
- `ui/index.ts` (export), `ui/ElectrodePairsEditor.tsx` (slots → single-select picker; **new
  `activeSlot` / `onActiveSlotChange`**, flattened `pair*2+col`, for lane EL; pair index coloured
  from `channelCss()` — no colour literals)
- `pages/_shared/subjects/SubjectsField.tsx` + `subjects.css` (keeps the head, the summary line,
  the disclosure and the measured `fill`; the table is now the shared list)
- `pages/panels/_participants/ParticipantsField.tsx` + `participants.css` (filter, checkbox column
  with ⇧-range, `All · None`, badge, **`Remove N`**)
- `pages/_shared/roi/RoiPicker.tsx` (cortical + subcortical regions → `SelectionPicker`)
- `pages/optimizer/ExSections.tsx` (four/eight buckets and the pool → `SelectionPicker`)
- `pages/_shared/run/{index.ts,run.css}`, `pages/preprocess/index.tsx`,
  `pages/simulator/{index.tsx,RunControls.tsx}`, `pages/optimizer/index.tsx`,
  `pages/analyzer/AnalyzerPage.tsx` (receipt + shared dialog)
- `pages/jobs/{index.tsx,jobs-page.css}`

Changed (tests — minimal, each with its reason in a comment): `tests/e2e/_helpers.ts` (new
`answerExistingOutputs`), `tests/e2e/_subjects.ts` (`All · None` + badge), and one assertion each in
`tests/e2e/{batch,preprocess,layout,panels-shape,table-room,roi-idiom,optimizer,jobs}.spec.ts`,
`tests/unit/{subjects-field,participants-field,ui-controls}.test.tsx`.

`ui/Combobox.tsx`'s `MultiSelect` is **not** deleted: `forms/SchemaField.tsx` and the dev Gallery
still use it (it is the array-of-strings control for schema-driven forms).

## 4. Gate

| gate item | command | result |
|---|---|---|
| selection model unit tests (range / toggle / all / none / filter interplay; filtered-out rows keep state; ⌘A takes the visible set) | `npx vitest run tests/unit/selection-model.test.ts` | **19 passed** |
| receipt count = plan rows | `npx vitest run tests/unit/run-receipt.test.ts` | **4 passed** |
| whole unit suite | `npm run test` | **949 passed** |
| typecheck | `npm run typecheck` | clean |
| lint | `npx eslint src tests` | 0 errors (3 pre-existing React-Compiler warnings: `ui/DataTable`, `ui/VirtualList`, `pages/preprocess`) |
| e2e — the grammar itself | `npx playwright test tests/e2e/selection.spec.ts` | **9 passed** (same control + testids on all four subject pages; ⇧-range; ⌘-toggle; filter × All; receipt count = `.plan-cell-button` count and updates live; receipt above the action bar by bounding box; Jobs multi-select cancel sends exactly the selected ids; the dialog's three buttons) |
| full offscreen run | `npm run e2e:quiet` | **193 passed, 3 skipped, 2 failed** — both failures are lane PC's new `pipeline` page shifting the ⌘-number shortcuts (`smoke.spec.ts:124` expects `results`, gets `pipeline`; `smoke.spec.ts:161` the same rail assertion). Every spec this lane touches is green. |

## 5. Design rationale (before/after at 1280 px in `SG-shots/`)

`SG-shots/{simulator,optimizer}-{before,after}-1280.png` (offscreen captures; "before" is the
15:46 run of `screens.spec.ts`, "after" the run after this lane).

1. **One row, one meaning.** The subject table's header band is now `filter · All · None · 2 of 3
   selected` — the count is stated once, in the control, so it cannot disagree with the summary
   line above it. The row keeps its checkbox, and the checkbox is now the *same* action as the
   click rather than a second, competing one.
2. **The closed control answers the question.** Every picker trigger prints its selection
   (`E24, E124`, `L · bankssts`) instead of a truncated chip row, so a collapsed form still says
   what will run.
3. **The confirmation moved next to the button.** The receipt is the last thing above Run and lists
   the jobs; the grid stays as the detail view in the other pane. Measured: it *lowers*
   Pre-processing's dead space from 41.8 % (no receipt) to **41.9 %** open — it pays for its own
   pixels because a list of jobs is dense text.
4. **Density is the tokens'.** 28 px band, 12 px body, 11 px uppercase headings, `--surface-2`
   bands, `--warning` for reasons — the same values `.form-section-header` and `SubjectsField`
   already used.

Two measurements that changed the design:

- the receipt was **sticky** at first. `tests/e2e/layout.spec.ts`'s hit-test caught it floating over
  the form as the page scrolled — 12 of the Optimizer's 358 controls and 7 of the Simulator's 52
  answered a click with the receipt. A confirmation must never sit on top of what it confirms, so it
  is a normal last child now. Doing it properly needs a slot **outside** the work scroller — see §6.
- the receipt's list is capped at three rows and scrolls. A taller list cost the Analyzer a whole
  section of `RunWork`'s 96 px fill budget.

## 6. Proposed records (for the consolidation lane — I did not edit `desktop/DESIGN.md`)

### DESIGN.md, new §4.7 "Selection"

> **One list, everywhere.** Anything chosen out of a set — subjects, montages, ROI regions,
> electrodes, participants, jobs — is `ui/SelectionList`. There is no second selection idiom.
>
> - click selects one; ⇧-click takes the range from the last click; ⌘/Ctrl-click toggles one; ⌘A
>   takes everything the filter is showing; Esc clears it.
> - A checkbox column is the visible form of the same toggle. A row is never *only* clickable and
>   never *only* tickable.
> - An always-on filter box; `All · None` are the only bulk buttons; an `N of M selected` badge is
>   the only place the count is stated.
> - A bulk button acts on the **visible** rows. A row the filter is hiding keeps its state.
> - The value's order is the order rows were chosen, and that is the order jobs are submitted in.
> - A row that cannot be used keeps its checkbox and states its reason in the row (the reason is
>   what the Run button then prints); `bulkExclude` keeps it out of `All` so a bulk convenience can
>   never create a blocked run.
> - No drag-to-reorder anywhere, and no per-item options: options apply to the whole selection.
> - Where a form field has no room for a list, `SelectionPicker` puts the same list in a dialog
>   behind a trigger that states the selection in words. Single-value fields use `mode="single"`.
> - `role="listbox"`/`option` for a list of things; `role="grid"`/`row` where the list is a real
>   multi-column table. Both are keyboard-navigable with a roving `aria-activedescendant`.
>
> **The receipt.** Every run page ends its work column with `pages/_shared/run/Receipt` — "This will
> run N jobs:", the first 15, "… and K more", and the existing-outputs line — derived from the same
> `PlanModel` as the plan grid and the action bar's digest. The grid is the detail view; the receipt
> is the confirmation, and it is adjacent to the button.
>
> **Existing outputs** are one question with three answers, on every run page:
> `pages/_shared/run/ExistingOutputsDialog` — Skip (default) / Replace and rerun / Cancel.

### DECISIONS.md

> **One selection grammar (`ui/SelectionList`).** v3 had grown five selection idioms; the maintainer
> reported that choosing and understanding a batch had become "too convoluted". 2.5.0's rule — a flat
> list, native range selection, exactly two bulk buttons, options that apply to the whole selection,
> a plain receipt, and a Skip/Replace/Cancel decision on existing outputs — is restored as one
> primitive used by every list in the app, plus a dialog form for fields with no room. The plan grid
> stays as the detail view. *Consequences:* a plain click now selects one row instead of adding one
> (⌘-click adds); `MultiSelect` chips and the pair `Select` combos are gone from the pages;
> `PlanGrid` is no longer the primary confirmation.

### ROADMAP / follow-ups

1. **`PageLayout` receipt slot.** Render the receipt between the work scroller and the action bar so
   it can be sticky without overlaying the form (`ui/Layout.tsx`, not this lane's file).
2. **The Source panel's two confirmations** ("Build forward solution?", "Map fields to fsaverage?")
   are still page-local: they are not plan-backed, so there is no `existing` count to put in the
   shared dialog. Giving `/api/plan` a source kind would fold them in.
3. **Jobs "retry"** has no server endpoint; C4's retry half is therefore not implemented (cancel and
   pin-terminal are). `POST /api/jobs/{id}/retry` would close it.
4. The saved-ROI list in `RoiPicker` still has its own row shape, because its rows carry a per-row
   delete button that `SelectionList` has no slot for. A `rowAction` prop would fold it in.

## 7. Open items / other lanes

- Full `npm run e2e:quiet` — **193 passed / 3 skipped / 2 failed in 10.0m**. The two reds are
  **lane PC's**: `tests/e2e/smoke.spec.ts:124` ("keyboard shortcuts jump screens…") and
  `smoke.spec.ts:161`, both because the new `pages/pipeline/` page took a nav-rail slot and the
  ⌘-number shortcut that used to open Results now opens Pipeline (`data-page` is `pipeline`,
  expected `results`). Reported, not touched — `pages/pipeline/` and `app/` registration are PC's.
- The first full run of this lane had 10 reds, all mine; each is fixed and each fix is recorded in
  the file or spec it touches (§3, §5).
- `e2e-quiet-check` reports "a window APPEARED on screen" for `Electron` on this machine even with
  `TIT_E2E_OFFSCREEN=1`; it did so before this lane's changes too (it is the harness's own check,
  not a spec failure). Reported, not investigated — no spec of mine opens a window.
- Lane EL's two asks are done: `activeSlot`/`onActiveSlotChange` on `ElectrodePairsEditor`, and pair
  colours from `channelCss()`. The pairs model shape (`[a, b]` strings) is unchanged. EL's
  `scene-pane.spec.ts:81` / `guide.spec.ts:169` needed no edit in the end: the picker trigger keeps
  `role="combobox"`, so `getByRole("combobox")` still finds an electrode slot.
- Lane AU's `pages/settings/TetravoxCard.tsx` and `tests/unit/tetravox-card.test.tsx` were red
  mid-lane (missing `auto_update` / `setTetravoxPolicy`); both were green again by the end.
  Lane EL's `tests/e2e/real/embed-electrodes.spec.ts` had a `DotProbe` typecheck error mid-lane;
  also green by the end.
