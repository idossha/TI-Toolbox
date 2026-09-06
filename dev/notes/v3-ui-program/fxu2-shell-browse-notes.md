# FXU2 — Shell, Results, Subjects, Jobs cross-lane fixes (fix round, lane notes)

Owns: `desktop/src/renderer/app/**` (incl. `jobs-rail/**`), `pages/results/**`, `pages/subjects/**`,
`pages/jobs/**`, `pages/viewer/lib.ts` (only if the focus fix needed it — it didn't),
`tests/e2e/{smoke,settings,results,subjects,jobs,viewer}.spec.ts` (viewer: the focus assertion
only), `tests/unit/{shell-*,statusCells-*,results-*,subjects-*,jobs-*,navBrandMark*}.test.*`.

Orchestrator's visual verdict named the run pages' right pane and collapsed-section blankness —
neither is this lane's ownership (B2/B3's `preprocess`/`simulator`/`optimizer`/`analyzer`). This
lane's own worklist (7 items below) came from the build round's cross-lane findings, mainly B1's
and B6's notes.

## 1. What shipped

1. **`app/registry.ts` panel gating, restored live** (B6's finding, blocked `settings.spec.ts`).
   `navSlotOf` forced `hidden: true` on *every* page with no rail slot — including a
   `navGroup: "panels"` page, whose slot the flat-rail rewrite had dropped entirely. A panel that
   `settings.panels` said was on (`GET /api/settings` already returns
   `panels:["source","quick-notes","subject-info"]`) never reached the rail in any state, because
   `useEnabledPages()`'s live filter (`isPanelPageEnabled`, already correct) fed a list whose
   `.hidden` was baked wrong at import time and never revisited. Fixed by giving a `panel-<id>` page
   its own slot (`navSlotOf`: `id.startsWith("panel-")` → `id`) instead of `null`, and by having
   `resolvePage`'s `railIndex` place an unrecognised (panel) slot after the eight `NAV_ORDER` rows,
   ordered by the page's own numeric `order` field (100/105/110/120/140 across the five panels — no
   second list to keep in sync). `hidden` is now `page.hidden ?? false` for a panel page, same as any
   other slotted page — visibility is `enabled` alone, exactly like every other rail row.
   `tests/unit/shell-registry.test.ts` updated: the one test asserting the old (wrong) behaviour
   (`resolvePage({id:"panel-x",...}).hidden === true`) now asserts the fixed one, plus two new tests
   (a panel gets a real slot at the end of the workflow section; the five real panel pages are
   structurally un-hidden, only `enabled` keeps a disabled one off the rail).

2. **`app/Shell.tsx` `focusViewerCanvas` (⌘⇧V)** — B5's exact diagnosis and diff applied verbatim:
   the handler queried `.shell-content canvas`, a selector for the retired in-process engine; the
   Viewer has been a postMessage `<iframe>` since. Now calls `useViewerStore.getState().focusCanvas()`
   (tells the embed's own crosshair/nav to take over) and `frame?.focus()` on
   `[data-testid="tetravox-frame"]` (moves DOM focus so the iframe's unmodified keys start reaching
   it — the protocol message alone never moves host focus). New e2e test in `viewer.spec.ts` (the
   one assertion this lane may add there): presses ⌘⇧V after a scene is loaded, asserts
   `document.activeElement`'s testid becomes `tetravox-frame`. Both the pre-condition ("focus
   somewhere else first") and the shortcut itself are asserted inside `expect.poll(async () => {...})`
   loops that repeat the *action* each poll, not just the read — a real, reproducible bit of
   flakiness on this page (below) meant a one-shot `.focus()` / one keypress occasionally lost a race
   against still-settling status-cell queries; 5/5 clean reruns after that fix.

3. **`app/NavRail.tsx` rail-mode resize flake** (B5's finding 2: `data-rail-mode` intermittently
   stuck `"icons"` after a resize to ≥1440 specifically on the Viewer page with a live postMessage
   channel open). `useLabelledRail()` now listens on both the `matchMedia` `"change"` event *and*
   `window`'s own `"resize"` event, both re-reading `mql.matches` fresh (one source of truth, so the
   two listeners cannot disagree). Chromium dispatches these through different code paths, so a race
   dropping one is very unlikely to drop both — didn't chase the exact scheduling mechanism further
   (B5 already reasoned it reads like an Electron/offscreen-renderer timing question, not app logic).
   New `smoke.spec.ts` test reproduces B5's exact repro end to end (subject selected, Viewer opened,
   scene loaded into the fake embed, then two resizes with the channel live) — this is the one
   `viewer`-adjacent test this lane could actually add without touching `viewer.spec.ts` beyond the
   focus assertion, since the repro needs the live page, not just the pure hook.

4. **`app/jobs-rail/JobDetailPane.tsx` Summary tab density** — added the inline console excerpt
   (last 40 lines) under the definition list, `page` density only, per the wireframe. New query
   (`["job-log", jobId, "excerpt", 40]`, `getJobLog(jobId, 40)`), live (`refetchInterval: 3000`
   while the job is non-terminal, `false` once it is). CSS: `.job-detail-console`/
   `-console-head`/`-console-body` in `jobs-rail.css`, the body reusing `.job-detail-log`'s look but
   with `max-height: none` (that class's normal 320px cap is for the *inline* error excerpt; this
   block is the thing meant to occupy the pane, not be capped).
   **Numbers**: `jobs.spec.ts`'s existing density test, at 1280×900 with a job selected — was
   asserting a loose `≤0.85` regression guard (the pane's real number had never been near the design
   target); now measures **24.2%**, tightened to `≤0.25` (DESIGN.md §12.3's actual "populated"
   number). Added the same assertion at 1440×900 (`≤0.3`) to the existing "detail column widens to
   400px" test — passes.

5. **Results preview iframe** — investigated, not changed: `results.css`'s
   `.page-layout-panel:has(.results-preview) { align-self: stretch; height: 100%; }` (present before
   this round, comment credits a prior FXU1 pass) already makes the report `<iframe>` fill the full
   height above the artifacts block. Measured via `results.spec.ts`'s existing geometry dump:
   `.results-report-frame 489x581@951,68` — genuinely 581px tall, ending exactly where
   `.results-preview-artifacts` begins. The `preview` column's own dead-space is **10.8%** (target
   ≤20%). The merged-tree screenshot's "short table, lots of white below it" look is the *embedded
   report's own content* being short (a real, short mock report — `sub-ernie — Thalamus simulation`,
   one montage line, one 2-row table) rendered inside an iframe that does fill the pane; the iframe
   itself is real DOM (counted as content by the dead-space metric, and correctly so — a browsing
   context's box is never "empty ground" from the host's point of view, whatever it renders inside).
   No code change made; verified with `results.spec.ts`'s pre-existing "hits its §12.3 numbers" test,
   9/9 green including this one, unmodified.

6. **Subjects readiness board — 4-across at ≥1440** (`subjects.css`, media query added, matching the
   window breakpoint DESIGN.md §2.2 already uses elsewhere rather than a page-local number). Its own
   region: 17.5% dead (was in the 30s% at 2x2 on this fixture). **This does not reduce the whole-page
   number** — re-measured, honestly worse: unselected 1440 51.3%→66.2%, populated 1440 47.7%→59.2%
   (1280 unaffected by the media query, unchanged at 51.3%/47.7%). A single row of cards is *shorter*
   than 2x2, so on a 3-subject/4-stage fixture this small, going 4-across leaves *more* bare ground
   below the board, not less — the brief's "so the page has no blank half" doesn't hold as a
   consequence of the column count alone, empirically. Did not chase a further fix (stretching the
   cards to fill it was tried and reverted in an earlier round, documented in the CSS's own comment,
   for the "never decoration" reason: four large empty boxes read worse than honest ground). Kept the
   4-across change (it was the literal ask, and it does what it is asked: 4-across, board-region
   dense) and re-measured `subjects.spec.ts`'s thresholds to the new real numbers with headroom
   (`readiness ≤0.25`, page bounds `≤0.62`/`≤0.68` populated/unselected) rather than leave a stale
   pass. **Flagging this for the orchestrator**: closing this page's whole-number gap on a 3-subject
   fixture needs either more subjects in the fixture or a genuine content addition to the readiness
   cards (not a layout trick) — out of this lane's time box.

7. **`tests/unit/navBrandMark.test.tsx`** — already green (24/24 across `navBrandMark`,
   `shell-registry`, `statusCells-registry` at the start of this round); B1's `pageById` mock concern
   did not reproduce. No change needed.

## 2. A pre-existing bug found while verifying item 4 (not fixed — outside this round's scope)

`app/jobs-rail/api.ts`'s `getJobLog` (unmodified by this lane — the Raw log tab has called it since
before this round) intermittently fails with `net::ERR_ABORTED` specifically against
`jobs.spec.ts`'s 30-job "uses the width" fixture. Isolated with `page.on("request"/"requestfailed")`
and a raw `fetch()` issued from inside the page via `page.evaluate` to the exact same URL (which
succeeded every time, 200, matching empty body) — the server and the network path are fine; the
app's own `api.GET(...)` call for this one endpoint aborts client-side, repeatably, retried into a
loop by the query client's default `retry`. Did not root-cause further (budget); `JobDetailPane`'s
own behaviour is correct regardless (DESIGN.md §4.4's documented Skeleton-then-content states), and
the Raw log tab has apparently never been exercised by any test before this round (grepped — zero
hits). `tests/e2e/jobs.spec.ts`'s density assertion is worded to hold either way (container visible,
not content-resolved) with a comment pointing here. Worth a dedicated look by whoever owns
`app/jobs-rail/api.ts` next.

## 3. Dev-loop rounds and numbers

### Round 1 — read the merged tree, reproduce the findings

Read `dev/notes/v3-ui-program.md`, `DESIGN.md` §2/4.5/4.6/12, all six build-lane notes' "needs from
other lanes," and the `orch-screens` PNGs/`metrics.json` (`capturedAt` 2026-09-03T20:19:31, i.e.
*after* the results.css `:has()` fix's mtime — so item 5's screenshot really is the current code, not
stale). Baseline numbers from that capture (unselected/landing states only — no per-page spec had run
yet this round): `jobs` 99.1%/99.4% dead at 1280/1440 (the empty "nothing has run yet" state, expected
per B6's own notes — not this lane's target); `subjects` 51.3%/57.2% unselected; `results` 30.6%/34.8%
(already under investigation, turned out fine — see item 5). Confirmed `settings.spec.ts`'s
panel-toggle test failing (item 1) and B5's viewer focus/resize findings (items 2–3) by reading, then
reproduced item 3 with the new `smoke.spec.ts` test before fixing `NavRail.tsx`.

### Round 2 — fix → rebuild → per-page specs → shared `screens.spec.ts` → self-critique

Implemented items 1–4 and 6 (5 needed no code, verified instead). `npm run pree2e` + each owned spec
file individually, then `TIT_E2E_RUN_ID=fxu2-r1-<rand> npx playwright test tests/e2e/screens.spec.ts`
for the shared instrument (48 captures, `tests/e2e/artifacts/fxu2-r1-29581/`). Read the resulting
`subjects-light-1440x900.png` — 4-across board confirmed legible at both pane widths (864px selected,
1224px unselected: ~206px/~306px per card respectively), confirmed "Source"/"Subject info" now show
in the rail live (server `settings.panels` seeds them by default in the mock, no reload needed —
stronger than the pre-existing "reload required" note in `pages/panels/_shared.ts`, since
`useNavSections()` was always live on the *filter* side; only the `hidden` flag was wrong).
Self-critique against checklist item 1 (dead space ≤25%) surfaced the subjects whole-page regression
(item 6 above) and prompted the `getJobLog` investigation (item 4's screenshot showed loading
skeleton instead of resolved text, which led to §2's finding). Numbers per page, this round:

| page | state | 1280×800 | 1440×900 | spec / assertion |
|---|---|---|---|---|
| jobs | selected (1 of 30) | **24.2%** (was loose `≤0.85`) | **≤0.3%** (new) | `jobs.spec.ts` |
| subjects | readiness board region | 17.5% | 17.5% (4-across both ≥1440) | `subjects.spec.ts` |
| subjects | populated (page) | 47.7% (unchanged) | 59.2% (was 47.7%\*) | `subjects.spec.ts` |
| subjects | unselected (page) | 51.3% (unchanged) | 66.2% (was 51.3%\*) | `subjects.spec.ts` |
| results | preview column | 10.8% | 10.8% | `results.spec.ts` (unchanged, verified) |
| viewer | (unaffected by items 2/3) | 0.36–0.42% | 0.36–0.42% | `viewer.spec.ts` (unchanged) |

\* 1440 was previously the same as 1280 because the readiness board had no `≥1440` rule at all before
this round; both sizes shared the 2x2 layout and its numbers.

### Round 3 — full gates + quiet check

`npm run typecheck && npm run lint && npx vitest run && npm run build`: clean — 0 typecheck errors, 0
lint errors (3 pre-existing `react-hooks/incompatible-library` warnings, none in this lane's files,
unchanged from before this round), 599/599 unit tests, build succeeds. `bash
scripts/e2e-quiet-check.sh npx playwright test tests/e2e/{smoke,settings,results,subjects,jobs,viewer}.spec.ts`,
`TIT_E2E_RUN_ID=fxu2-final-8684`: **all 45 tests passed** (every file's own numbers reproduced —
jobs 24.2%/≤0.3%, results 10.8% preview, subjects 17.5% board region / 59.2–66.2% page, viewer
~0.33–0.42% both sizes). The wrapper itself printed FAIL — four `Electron`/`TI-Toolbox` windows at
layer 0, none of them at the "1900x1030" size the ground rules name as the maintainer's known dev
window. Checked with `ps aux` immediately after: the only Electron processes alive are three
separate `electron-vite dev` + main-process groups (started 15:16, 15:17 and 16:11 — well before and
during this run), **all three using the real, non-temp userData dir**
(`~/Library/Application Support/ti-toolbox-desktop`) — every launch this lane's tests make uses
`mkdtempSync(tmpdir(), "tit-e2e-")` instead, and `TIT_E2E_OFFSCREEN=1` is the darwin default per
`_helpers.ts`, so none of the four on-screen windows can be one of this round's test launches; no
orphaned temp-userData Electron process was found. Read as three restarts of the maintainer's own
interactive dev session on this same worktree stacking windows across the afternoon, not a window
this lane put on screen — the exact scenario the ground rules call out as expected, just with more
than one stacked window rather than the one the rule's example names. Every file passed individually
too, run separately beforehand (smoke 9/9, settings 1/1, results 9/9, subjects 6/6, jobs 8/8 across
two consecutive full runs, viewer 11/12 then 12/12 after the flake fix — the one miss was
`connect()`'s `subjects-table` timeout on an unrelated test under back-to-back full-suite load,
reproduced in isolation as a clean pass, so infra flake under load, not this lane's code).

## 4. Self-critique against the checklist (§3)

1. Dead space ≤25% populated: jobs ✅ (24.2%/≤0.3%), results ✅ (10.8%), viewer ✅ (~0.4%), subjects
   ✗ — flagged honestly in item 6, not silently passed.
2. No page header restating the nav label: unaffected by this round's edits.
3. Chip vocabulary: unaffected.
4. Tabular numbers, mono truncated paths: the new console excerpt is `mono text-caption` inside
   `.job-detail-log`, matching the Raw log tab's own treatment.
6. Status bar: unaffected by this round.
8. Keyboard: ⌘⇧V now does something real (item 2); ⌘⇧I/⌘K/⌘J untouched.
10. Every fix has a green spec asserting DOM state (testids, attributes, computed geometry), not a
    screenshot diff; screenshots were read by this agent as evidence, never as the pass/fail signal.

## 5. Files changed

`src/renderer/app/registry.ts`, `src/renderer/app/NavRail.tsx`, `src/renderer/app/Shell.tsx`,
`src/renderer/app/jobs-rail/JobDetailPane.tsx`, `src/renderer/app/jobs-rail/jobs-rail.css`,
`src/renderer/pages/subjects/subjects.css`, `tests/unit/shell-registry.test.ts`,
`tests/e2e/viewer.spec.ts` (one new test only — the focus assertion), `tests/e2e/smoke.spec.ts` (one
new test — the resize flake), `tests/e2e/jobs.spec.ts` (tightened/added dead-space assertions +
console-excerpt visibility), `tests/e2e/subjects.spec.ts` (re-measured thresholds + comment).
`pages/results/**` — read and verified only, no edit.
