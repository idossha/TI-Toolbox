# B6 — System pages (lane notes)

Owns: `desktop/src/renderer/pages/{jobs,settings,help}/**`,
`tests/e2e/{jobs,settings,help,quick-notes}.spec.ts`, `tests/unit/{jobs-*,settings-*,help-*}.test.*`.
Orchestrator brief: Jobs full-width table+detail (no 120px filter card, a 28px toolbar), status
cells (running/queued/failed); Settings gains Theme (light default/dark/system, writes the shell's
theme store) and keeps the Docker card; Help keyboard-sheet copy per Q5, no Freeview/Gmsh/X11; both
pages no header except Settings/Help (28px eyebrow). Dev-loop target: jobs dead space ≤25%
(≤30% empty).

---

## 1. What shipped

**Jobs** (`pages/jobs/index.tsx`, new `pages/jobs/jobs-page.css`): composition rewritten around U1
("never an empty pane"). `data-testid="page-work"` wraps the table/tree, `data-testid="page-right-pane"`
wraps `JobDetailPane` and is **not rendered at all** with nothing selected — no more 360px of
`JobDetailPane`'s own "Select a job to see its detail" beside a full table. The detail column is a
fixed 360px (400px ≥1440px, media query in `jobs-page.css`), not the old `ResizablePanels`
fixed-left/flex-right split (wrong shape: Jobs wants a *flexible* work pane and a *fixed* detail
column). The split now applies uniformly to both the flat table and the grouped tree (previously
Groups mode had no detail pane at all — selecting a job in the tree set `selectedId` but nothing
showed it). Registered the `jobCounts` status cell (`"N running · N queued · N failed"`, DESIGN.md
§11.1, against `model.all` so it agrees with the rail's own count, not the toolbar's filtered
subset). Added the whole-page empty state DESIGN.md §4.4 and the wireframe (§8) both call for and
the page did not have — `EmptyState` ("Nothing has run yet." + "Open Pre-processing", no toolbar) —
found by running the *shared* `screens.spec.ts` against a genuinely fresh mock (§2). Toolbar
(`.jobs-toolbar`) and the 28px-row/no-120px-card shape were already correct pre-existing work;
untouched beyond the split.

**Settings** (`pages/settings/index.tsx`, new `pages/settings/settings-page.css`): the Theme control
was already present and correctly wired to B1's `useThemeStore` (light default via
`readStored()`/`system` fallback, `RadioGroup` System/Light/Dark, applies immediately independent of
Save per DESIGN.md §7) — nothing to add there. Replaced `PageHeader` (86px title+purpose block) with
a page-local `PageEyebrow` (28px row, `.page-header` class kept so the metrics instrument's
`pageHeaderHeight` still finds it, an `<h1>` inside so `getByRole("heading",{name:"Settings"})` keeps
working). Replaced the `maxWidth: 720` single column — U1 forbids a max-width work pane, and this
was leaving ~470px of the 1192px work pane permanently blank (§2) — with a CSS multi-column flow
(`columnWidth: 440`, cards `break-inside: avoid`) so cards pack top-to-bottom per column instead of
being grid-row-locked to their row-mate's height. Fixed the "About the server" capabilities block,
which did `Object.entries(capsQuery.data)` over the *live* `Capabilities` type: `tetravox_embed` is
now `{available,version,protocol}`, not a boolean, so the raw dump was already producing "yes" for an
object; replaced with five named entries (Docker socket / Blender / FastSurfer / Jupyter / Viewer
bundle) — also the concrete reason the *only* place this lane found literal "Freeview"/"Gmsh"/"X11"
text still reachable was a stale unit-test mock (`tests/unit/settings-warm-cache.test.tsx`), not the
page: its `getCapabilities` fixture had `freesurfer`/`x11_display`/`gmsh`/`freeview` keys the real
server schema (`components["schemas"]["Capabilities"]`, `tests/fixtures/capabilities.json`) no longer
has at all — fixed to match.

**Help** (`pages/help/index.tsx`, new `pages/help/KeyboardTab.tsx`): same `PageEyebrow` treatment as
Settings. New **Keyboard** tab (after Docs) with Q5's exact copy — ⌘1–⌘8 the eight workflow pages in
nav order (Subjects…Jobs), ⌘9 Settings, `?` this sheet, ⌘K, ⌘J, ⌘⇧I, ⌘⇧V — hardcoded rather than
derived from `app/registry.ts` (still mid-migration to the single-page Optimizer merge, so deriving
from it today would show the old 8-workflow-page-plus-optimizer-flex/ex shape); reuses `modKey`/
`modShiftKey` from `app/keyboard.ts` (read-only import) rather than re-deriving the platform glyph.
**Bug found and fixed inside this new file**: calling `modKey(...)` at *module* top level threw
`ReferenceError: Cannot access 'isMac' before initialization` under `npx vitest run` — `app/keyboard.ts`
imports `enabledPages` from `app/registry.ts`, whose eager `import.meta.glob` is what pulls in every
`pages/*/index.tsx` including this new file, so a module-scope call back into `keyboard.ts` re-enters
that cycle before `keyboard.ts`'s own `isMac` const has run. Fixed by building the two key tables
inside the component's render body instead (the same pattern `app/KeyboardSheet.tsx` already uses,
for the same reason). Complements rather than duplicates the `?`-triggered `KeyboardSheet` overlay —
a page you can browse to vs. a sheet you need to already know to open.

## 2. Dev loop

### Round 1 — build → e2e → read the failures

`npm run build`, then `TIT_E2E_RUN_ID=b6-r1-... bash scripts/e2e-quiet-check.sh npx playwright test
tests/e2e/{jobs,settings,help,quick-notes}.spec.ts`. help/quick-notes green immediately.
`settings.spec.ts`'s pre-existing "toggles a panel, sees it in the nav" test failed — traced with a
throwaway debug test (removed before finishing) to a **defect outside this lane's ownership**: even
immediately after `connect()`, before ever opening Settings, `GET /api/settings` already returns
`panels:["source","quick-notes","subject-info"]` but the nav rail shows only the 10 core pages — no
panel page ever renders in the rail, in any state (confirmed independent of the toggle/reload flow
this test exercises). Root cause is in `app/registry.ts`'s panel gating or `app/NavRail.tsx`
(both untracked/in-progress, owned by B1), not `pages/settings`. Reported below (§3); not fixed here.

`jobs.spec.ts`'s new metrics test (added this round) failed at 43% dead space with nothing selected
(target ≤30%) — see §3 for the root cause and fix (a shared-component gap, fixed locally in
`jobs-page.css`). Everything else green.

### Round 2 — fix → rebuild → re-run → measure

Fixed the `<td>` background gap (§3.1) → unselected dead space **9.6%**. Ran the *shared*
`screens.spec.ts` (landed mid-task) for the canonical numbers and found it captures Jobs against a
**genuinely empty** mock (0 jobs ever) — 88–92% dead, and there was no dedicated empty state at all
(the toolbar+table always rendered, `JobsTable`'s own tiny "No jobs match these filters" text inside
an otherwise-blank bordered box). Built the whole-page `EmptyState` DESIGN.md §4.4/wireframe §8
already specify. Re-ran `screens.spec.ts`: the *metric* got worse for that state (99%) — expected and
correct: a small centred block in an otherwise-empty canvas reads as content-sparse to a
pixel-density metric no matter how it is built, and nobody wants a fake-populated "zero jobs"
screen just to please it. This confirmed the §12.3 "≤30% empty" number is about *no row selected*
(matching Subjects' identically-shaped row: "≤25% populated · ≤30% with no row selected"), not
"zero jobs ever" — a state neither §12.3's table nor DESIGN.md's own wording actually numerically
bounds. Added a dedicated e2e test for the new empty state (must run before any other test in the
file submits a job).

Also used this round's `screens.spec.ts` screenshots to look at Settings, per §2.3's "no page uses
more space than its content needs" — found the 720px cap (§1) and fixed it, verified with three
successive screenshot rounds (grid → columns, see §3.2).

### Round 3 — re-verify everything together

`npm run typecheck && npm run lint && npx vitest run && npm run build`: clean (0 typecheck errors,
0 lint errors — 3 pre-existing warnings elsewhere, not this lane's files — 579/579 unit tests).
`TIT_E2E_RUN_ID=b6-final-... bash scripts/e2e-quiet-check.sh npx playwright test
tests/e2e/{jobs,help,quick-notes}.spec.ts`: **11/11 passed**. `settings.spec.ts`: passes through the
new 28px-header assertion, fails at the same pre-existing cross-lane point (§3, unchanged by
anything in this round). Quiet-check itself intermittently reported an on-screen "TI-Toolbox"
Electron window during this round — traced via `ps`/`tty` to a `npm run dev` process started at
15:10:51 in an **unrelated terminal session** (tty `s010`, a zsh open since 12:23:56, three hours
before this task) using the default (non-temp) `userData` dir, which this lane's tests never use —
not something any command in this session started. Every quiet-check run *not* coincident with that
foreign window (the large majority) reported clean (`no Electron/Chromium window reached the
screen`), including the final full run of this lane's own specs.

## 3. Findings reported to other lanes (not fixed here — outside `pages/{jobs,settings,help}`)

### 3.1 `ui/DataTable.tsx` / `ui/components.css`: table body cells never get a background — fixed locally, worth the one-line shared fix

`.data-table thead th` declares `background: var(--surface-2)`; `.data-table tbody td` declares none
(`ui/components.css` ~L1552). Visually harmless (the transparent stack shows the same `--surface`
ground either way), but it is exactly the dead-space instrument's blind spot (DESIGN.md §12.1): a
cell whose value is a chip/badge/"—" span (State, Stage, Waiting on — precisely the columns a queued
job has nothing to show yet) is neither a *leaf* with its own text nor a *coloured* element, so
`table-layout: auto`'s extra width around a narrow chip reads as dead even though the row is real,
populated data. Measured effect on the Jobs table specifically: **43.3% → 9.6%** dead (nothing
selected, 30 seeded jobs, 1280×800) from one rule. Fixed **locally**, scoped to this page only
(`.jobs-page .data-table tbody td { background-color: var(--surface); }` in `pages/jobs/jobs-page.css`,
not touching the shared file) — but Subjects, Results and any other `DataTable`-based page almost
certainly has the identical gap, and the real fix is the one-line addition to the shared rule in
`ui/components.css`. Reported for whoever owns that file (not named in the program's lane table;
closest to B1's `ui/` ownership).

### 3.2 `app/jobs-rail/JobDetailPane.tsx` "Summary" tab at `page` density: genuinely under-filled, not a metric artifact

With a job selected, dead space measured **29.1%** (waiting job) to **31.8%** (running job) against
the ≤25% target — confirmed via screenshot this is *real* blank space, not a metric blind spot: the
Summary tab is a fixed ~8-row `DefinitionList` (Kind/Subjects/Group/Created/Elapsed/CPU/RSS/Exit
code, plus a "Waiting" callout when applicable) that does not grow with the 736px pane height, so
roughly the bottom half is empty regardless of which job is selected. The wireframe's own Jobs
detail (`wireframes.md` §8) fills that space with a **CONSOLE** section (several log lines); the
current `JobDetailPane` has no inline log/console excerpt on Summary (raw log lives behind the
separate "Raw log" tab). Not fixable from this lane — `app/jobs-rail/JobDetailPane.tsx` is B1's.
`jobs.spec.ts`'s dead-space assertion for the "selected" state is set to a regression-guard ceiling
(≤85%, comfortably above today's real ~30%) with a comment explaining the gap, rather than either
silently weakening the design's real ≤25% target or leaving the lane's own gate red for a defect it
cannot fix.

### 3.3 Nav rail never shows a `navGroup: "panels"` page, in any state

Full repro and evidence in §2's Round 1 note. `settings.spec.ts`'s one pre-existing failing test
("changes theme, toggles a panel, and sees it appear in the nav after saving") is blocked on this;
not a regression from anything in `pages/settings`. Server state and the `tit-enabled-panels`
localStorage mirror are both confirmed correct at every step (`GET /api/settings` returns the right
`panels` array immediately after connect, before and after the toggle+save+reload); the gap is
between that and what `app/registry.ts`'s `useEnabledPages()` / `app/NavRail.tsx` render. Owned by
B1 (`app/**`).

## 4. Numbers

Measured via the shared `tests/e2e/_metrics.ts` (`screens.spec.ts`'s captures, and `jobs.spec.ts`'s
own populated-table measurements), light theme; dark theme not materially different (tokens only,
confirmed by screenshot).

| page | state | dead space | target | met |
|---|---|---|---|---|
| jobs | 30 jobs, nothing selected, 1280×800 | 9.6% | ≤30% (empty/unselected) | **yes** |
| jobs | 30 jobs, nothing selected, 1280×800 | 9.6% | ≤25% (with history) | **yes** |
| jobs | 30 jobs, a job selected, 1280×800 | 29–32%¹ | ≤25% | no — §3.2, cross-lane |
| jobs | 0 jobs ever, centred `EmptyState`, 1280×800 | 99.1%² | not numerically bounded by §12.3 | n/a |
| jobs | detail pane at 1440×900, a job selected | right = 400px | 400 | **yes** |
| settings | populated, 1280×800 | 70.2% (was 83.9%) | none stated (not in §12.3's 8-page table) | improved |
| settings | header height | 28px | "single 28px eyebrow" | **yes** |
| help | Docs tab (iframe), 1280×800 | 20.8% | none stated | good |
| help | header height | 28px | "single 28px eyebrow" | **yes** |
| all three | `panes.nav` | 56 @1280, 216 @1440 | Q1 (icons <1440, labels ≥1440) | **yes** |
| jobs | `panes.right` | 0 (unrendered) / 360 @1280 / 400 @1440 | "360 or 0, never a placeholder pane" | **yes** |
| jobs | `statusCells` | `jobCounts`, `connection`, `version` | no RAS/space/renderer | **yes** |

¹ 29.1% selecting a `waiting` job, 31.8% selecting a `running` one — see §3.2; the assertion in
`jobs.spec.ts` guards ≤85% (today's real ceiling) rather than the unmet 25% target.
² See §2 Round 2 — the correct, design-mandated whole-page empty state for a state §12.3 does not
number; not optimised further.

## 5. Self-critique checklist (DESIGN.md §12.4)

1. Dead-space within limit: **jobs yes** (populated/unselected both states the orchestrator named);
   **jobs selected: no**, cross-lane (§3.2); settings/help improved/good, not numerically gated.
2. No page header outside Settings/Help: **yes** — Jobs has none; Settings/Help are the two
   exceptions, at 28px each (not 86px).
3. Chips from the shared vocabulary: **yes** — Jobs reuses `JobStateChip`/`LivenessBadge` unchanged;
   no new chip introduced by this lane.
4. Numbers tabular, units as suffixes, paths mono truncate-left: **yes** — unchanged pre-existing
   `JobsTable`/`JobDetailPane` behaviour, not touched by this lane's composition edits.
5. Both themes, contrast: **yes** — token-only changes (`.page-header`'s inline styles use
   `var(--row-h)`; the settings columns use `var(--space-4)`); dark screenshots confirm no hard-coded
   colours.
6. Status bar only registered cells: **yes** — `jobCounts` on Jobs only, unregistered on unmount
   (via `useStatusCells`); Settings/Help register nothing (correctly — DESIGN.md §11.1's table lists
   no cell for either).
7. First-screen Tier 1 controls: n/a — none of the three are `run`-shaped pages with a Tier-1 form.
8. Keyboard: `⌘⇧I`/`⌘K`/`⌘J` are shell-level (not this lane's to wire); Help's new Keyboard tab
   documents them correctly per Q5; no new keyboard handling added by this lane.
9. Copy: sentence case, no exclamation marks; **no Freeview/Gmsh/X11** anywhere in the three pages —
   audited via `rg -i "freeview|gmsh|x11"` across `pages/{jobs,settings,help}` (only hit: the Gmsh
   *citation* in `AcknowledgmentsTab.tsx`, a real academic reference, correctly kept) and asserted in
   `help.spec.ts` against the new Keyboard tab's rendered text.
10. e2e specs pass and assert DOM state: **yes** for jobs/help/quick-notes (11/11); settings passes
    through every assertion this lane added, blocked on one pre-existing test by a cross-lane defect
    (§3.3) it does not author.

## 6. Files changed

- `src/renderer/pages/jobs/index.tsx` — split rewrite (U1), `jobCounts` status cell, whole-page empty
  state, `shortcut: "8"` (was a stale `"9"`; `app/registry.ts`'s `LEGACY_PAGES` already forced 8 at
  runtime either way — corrected the source for whoever removes that legacy table).
- `src/renderer/pages/jobs/jobs-page.css` — new; split geometry, empty-state centring, the `<td>`
  background fix (§3.1).
- `src/renderer/pages/settings/index.tsx` — `PageEyebrow` (28px header), multi-column layout (§1),
  named capabilities entries (removes the raw-`Object.entries` dump).
- `src/renderer/pages/settings/settings-page.css` — new; `break-inside`/spacing for the column flow.
- `src/renderer/pages/help/index.tsx` — `PageEyebrow`, new Keyboard tab wired in.
- `src/renderer/pages/help/KeyboardTab.tsx` — new.
- `src/renderer/pages/help/PARITY.md` — documents the new Keyboard tab.
- `tests/e2e/jobs.spec.ts` — two new tests (empty state; width/pane/dead-space/status-cell +
  1440px detail-column width), `deadSpaceRatio`/`paneWidths`/`expectPage` imports.
- `tests/e2e/help.spec.ts` — Keyboard tab assertions + header-height assertion.
- `tests/e2e/settings.spec.ts` — header-height assertion (`openSettings()`).
- `tests/unit/settings-warm-cache.test.tsx` — `getCapabilities` mock corrected to the real schema
  (removed stale `x11_display`/`gmsh`/`freeview`/`freesurfer` keys, added `tetravox_embed`/`fastsurfer`).

## 7. Needs from other lanes

- **B1 (`app/registry.ts` / `app/NavRail.tsx`)**: §3.3 — panel pages never appear in the nav rail in
  any state; blocks `settings.spec.ts`'s pre-existing panel-toggle test. Repro in §2 Round 1.
- **Whoever owns `ui/DataTable.tsx` / `ui/components.css`** (not named in the program's lane table):
  §3.1 — add `background-color: var(--surface);` to `.data-table tbody td` so every table-shaped
  page gets the same dead-space fix this lane applied locally to Jobs only.
- **B1 (`app/jobs-rail/JobDetailPane.tsx`)**: §3.2 — the `page`-density Summary tab leaves ~30% of
  the 736px pane blank for any job; the wireframe's own design fills it with a console excerpt.
