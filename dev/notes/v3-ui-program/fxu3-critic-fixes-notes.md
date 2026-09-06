# FXU3 — critic round 1 fix round (fix round, lane notes)

Owns: `desktop/src/renderer/pages/panels/**` (5 pages), `pages/preprocess/index.tsx`,
`pages/settings/index.tsx`, `pages/_shared/run/{JobTerminal,run.css}`, `ui/tokens.css`,
`tests/unit/tokenContrast.test.ts`, `tests/e2e/{panels,panels-forms}.spec.ts`,
`tests/mock-server/server.mjs`, `DESIGN.md`, `dev/notes/v3-ui-program.md`. Source: the orchestrator's
CLOSE message plus `dev/notes/v3-ui-program/critic-round1-notes.md` (7 findings total — the
orchestrator's message said "the orchestrator saw only the first seven," but the file has exactly
seven; there is no eighth-or-later finding to close, so item (7) of the CLOSE message closes
nothing further).

## 1. What shipped

1. **HIGH — panel-page headers dropped** (critic finding 1). `header={<PageHeader .../>}` removed
   from all five `PageLayout` calls: `pages/panels/{source,subject-info,cluster-permutation,
   nilearn-visuals,nifti-group-average}/index.tsx`. Per the orchestrator's explicit decision, the §9
   fold (panels → modes inside Subjects/Pre-processing/Analyzer) is **not** this round's scope — the
   five pages still ship as independent rail rows. Each page's one-line `purpose` sentence moved into
   a `Tooltip` + `IconButton` ("About this page") on its **first CardHeader with a title** (not
   necessarily the first `<Card>` — `cluster-permutation`'s first Card has no header at all, just an
   "Analysis type" radio, so the tooltip landed on the next header down, "Subjects", the same
   placement `subject-info` and `nifti-group-average` already used for their own "Subjects" header).
   `pageHeaderHeight` is now `0` for all five (was `48`, per the critic's own metrics). DESIGN.md §9
   gained an explicit "**Not yet done**" paragraph naming the five page ids and stating "Panels
   remain standalone pages until folded" (Stage-2 follow-up, recorded per the orchestrator's
   instruction, not attempted this round). Settings' "Feature panels" copy changed from "Optional
   tools shown under Panels in the nav" (there is no "Panels" group — DESIGN.md §9 already says so;
   the old sentence was simply wrong) to "Optional tools. Enabled panels appear in the nav rail."
   `tests/e2e/{panels,panels-forms}.spec.ts`'s eight `getByRole("heading", {name: "<Panel>"})`
   assertions (one per page, light + dark) replaced with `expectPage(page, "panel-<id>")` —
   `_helpers.ts`'s existing `data-page` shell attribute check, the same mechanism every other
   header-less page's spec already uses for page identity. Settings' own "Settings" heading
   assertion is untouched (Settings keeps its header, per §2.3's two named exceptions).

2. **HIGH — `--field`/`--warning` soft-chip contrast, light theme** (critic findings 2, 3).
   Recomputed both pairs myself from `ui/tokens.css`'s literal light-block hex via the standard WCAG
   relative-luminance formula (verified the formula against black/white = 21.0:1 first): `--field
   #e25b22` on `--field-soft #fce9e0` = **3.11:1** (matches the critic's figure) and `--warning
   #9a6412` on `--warning-soft #fbf0da` = **4.42:1** (also matches). The critic's own suggested
   replacement for `--field` (`#c24a16`) computes to **4.17:1** by my script, not their claimed
   4.65:1 — short of the 4.5 floor — so I did not use it; instead chose `--field: #a53d0c` (5.46:1)
   and `--warning: #835410` (5.73:1), both with real margin rather than another near-miss, darkening
   only `--field`/`--warning` in the light `:root` block (`--field-soft`/`--warning-soft` and the
   entire dark block are untouched — dark already passed and DESIGN.md §7 says not to touch it for a
   light-only bug). `--field`/`--warning` have exactly two consumers each in `components.css`
   (`.status-dot-*`, decorative; `.chip-*`, the text-on-fill pair that was failing) — checked before
   editing, nothing else depends on the exact hex.
   `tests/unit/tokenContrast.test.ts` gained a new `describe` block asserting `--<kind>` on
   `--<kind>-soft` ≥ 4.5:1 for all six chip kinds (`accent, success, warning, danger, field, lost`)
   across all three theme reads (light, dark system-preference, dark explicit) — 18 new assertions
   (`themes` hoisted to module scope so both describe blocks share one set of parsed CSS vars rather
   than three redundant `extractVars` passes). `npx vitest run tests/unit/tokenContrast.test.ts` →
   29/29 green. Screenshots: the chips still read as the same semantic colours (still orange/amber,
   just a shade darker) — confirmed in the `fxu3-27848`/`fxu3-final-*` screens captures
   (`results-light-*.png`'s TI/mTI badges, `subjects-light-*.png`'s readiness chips).

3. **MEDIUM — nav-rail breakpoint docs vs. shipped 1440** (critic finding 4). The code was already
   right (`NavRail.tsx`'s `LABEL_RAIL_QUERY = "(min-width: 1440px)"`, `screens.spec.ts:113-114`'s own
   hard assertion `panes.nav === (width >= 1440 ? 216 : 56)`) — only the docs said 1280. Fixed
   DESIGN.md §2.1's table (nav-rail row now "icons below 1440; labels at ≥ 1440"), §2.2's breakpoint
   row (merged the stale "1280: nav 216→56" row into the corrected "1440" row — it was describing the
   same event at the wrong number), and §9's Viewer bullet. Added a **Q1** entry to
   `v3-ui-program.md` §0 so the "program Q1" citations in `NavRail.tsx`, `_helpers.ts` and
   `screens.spec.ts` resolve to an actual decision record instead of nothing (confirmed by grep
   before this round: `Q1` matched nowhere in either doc).
   **Found and fixed beyond the four named locations**, because leaving them would have made
   DESIGN.md self-contradictory the moment the nav-rail row was corrected: §2.1's "content box" and
   "work pane" rows were computed from the *old* wrong nav width even in the *already-corrected*
   parts of the table (`1064` px content box at 1280, assuming a 216 px labelled rail that hasn't
   shipped there since Q1) — replaced with real, DOM-measured numbers pulled from
   `tests/e2e/artifacts/critic-30421/metrics.json` (content box is **1224 px at both 1280 and 1440**,
   a genuine emergent property of Q1: `1440-216 == 1280-56`). The "C source bar / embed" row and §10's
   wireframe both stated `1384×764` for the Viewer at 1440 — also stale: nothing forces the Viewer's
   icon rail any more (`grep railMode` across `pages/*/index.tsx` returns nothing;
   `NavRail.tsx:73`'s own comment says "nothing does [force icons] today, and the width rule above is
   why"), and `viewer.spec.ts:239-244`'s own pre-existing comment already stated the corrected
   1224-at-both-sizes conclusion — I did not invent it, I matched DESIGN.md to a fact the Viewer's own
   spec already knew. Fixed to `1224×764`, and §10's "the only page that forces the 56 px icon rail"
   sentence rewritten to describe why it no longer needs to. Left **untouched, flagged instead**: the
   "form grid columns" row's 1-vs-2-up claim at 1280 (with the work pane now 826 px, up from the
   pre-Q1 666 px, a form section's container may already clear the 760 px two-up threshold at 1280 as
   well as 1440 — a real, plausible consequence of Q1 I could not fully verify against the container's
   own padding chain in the time box; softened the prose to say so and to point at a live
   `screens.spec.ts` capture rather than this table). The "B two-pane degenerate" row's numbers were
   also unverifiable from data I had (my only measurement was the *unselected*/empty state,
   `right: 0`) — replaced the stale numbers with the honest empty-state ones rather than guess at a
   populated-state figure I have no evidence for.

4. **MEDIUM — "recon-all" legacy label** (critic finding 5). `describePreStageDir()`
   (`pages/preprocess/index.tsx`): `"FreeSurfer recon-all (legacy)"` → `"Structural segmentation
   (legacy)"`. `rg -i "recon-all|recon_all|reconall"` across `desktop/src` and `desktop/tests` found
   one more **user-facing** hit: `tests/mock-server/server.mjs`'s `stagesFor("pre")` returned
   `["charm", "recon-all", "tissue"]` — these stage ids are interpolated directly into the
   JobTerminal's live log lines (`${stage}: ${what} (${subjectLabel})`, e.g. "recon-all: reading
   inputs (ernie)"), so this was reachable, shown text, not a dead comment. The real server
   (`tit/jobs/plans.py` G2a/G2b/G3 tags) never emits `"recon-all"` — it emits `"charm"`,
   `"fastsurfer"`, `"tissue"` — so the mock's list was itself out of sync with the real API it mocks;
   fixed to match. Left as-is (not user-facing): `api/schema.d.ts` (generated OpenAPI doc comment,
   never rendered), `pages/preprocess/PARITY.md` (a markdown parity doc, not shipped UI),
   `tests/unit/preprocess-defaults.test.ts:136-137` (asserts `stageLabelFor()`'s server-stage
   pass-through using `"FreeSurfer recon-all"` as an arbitrary example string proving the server's
   `job.stage` wins over the client guess — not testing `describePreStageDir`'s fallback wording, and
   not a string the app would ever show unless a real backend literally sent it).

5. **LOW — Terminal eyebrow** (critic finding 6). `JobTerminal.tsx`'s header gained a
   `<span className="text-eyebrow job-terminal-eyebrow">Terminal</span>` ahead of the existing
   identity block, matching `PlanGrid.tsx`'s "Plan" eyebrow rhythm per DESIGN.md §4.6's own
   wireframe. Wrapped eyebrow + identity in one `.job-terminal-title` flex group so
   `.job-terminal-head`'s existing `justify-content: space-between` still resolves to exactly two
   items (title cluster vs. the optional pin button) — the same two-item shape `plan-grid-head` uses
   for its eyebrow-vs-refresh-button split, rather than fighting `space-between` with three siblings.

6. **LOW — mock warning copy** (critic finding 7). `tests/mock-server/server.mjs`'s two
   `"output already exists; pass overwrite to replace it"` strings (the pre-specific `warningsPre`
   path and the generic `warnings` path shared by sim/flex/ex/mex/analyzer/stats/nilearn/
   nifti_average) reworded to GUI voice and to name the real control each kind actually offers:
   pre → `"Output already exists. Choose "Replace and rerun" to overwrite it."` (matches
   `preprocess/index.tsx`'s actual "Existing outputs" radio option, value `"replace"`); every other
   kind → `"Output already exists. Running will ask you to confirm the overwrite."` (generic on
   purpose — those kinds' confirm-button wording varies by page: "Overwrite and run", "Run analysis",
   "Run group averaging", …, so the message names the *mechanism*, not one page's button label). The
   paired "will be overwritten" strings reworded to sentence case ("Existing output will be
   replaced.") for the same reason. `rg` found no e2e/unit assertion on the old exact strings, so
   nothing else needed sync.

7. **Remaining critic findings** — none. The critic notes file has exactly seven findings (1–7,
   confirmed by reading start to end); all seven are items 1–6 above. Nothing left to triage.

## 2. Root-caused, not fixed: two chronically-flaky §12.3 dead-space assertions

`tests/e2e/preprocess.spec.ts:155` ("hits its acceptance numbers…") and
`tests/e2e/simulator.spec.ts:107` (same name) each failed in **both** of the two mandated full-suite
gate runs (`fxu3-27848` and `fxu3-final-8222`), both on the **same shape of assertion**:
`deadSpaceRatio` a few thousandths over an already-tight cap (preprocess: `0.7642` then `0.7280` vs.
`<= 0.76`; simulator: `0.5276` both times vs. `<= 0.52`) at **light @ 1440 only**. Both files' own
comments already flag these exact numbers as fragile: *"This limit is the number this page actually
reaches with every honest lever pulled… reported to the orchestrator as a calibration issue, not
silently met."*

Investigated rather than assumed: re-ran `preprocess.spec.ts` + `simulator.spec.ts` alone, outside the
full 92-test suite — simulator passed clean (`0.5276` did not reproduce in isolation, only inside the
full suite, twice); preprocess reproduced close but not identical (`0.7642`, then `0.7703` after I
shortened the mock's pre-warning text, i.e. *less* content), which rules out my content-length
hypothesis and points to ordinary timing noise plus accumulated system load from ~90 sequential
Electron launches (test 42 captures whatever job-progress state test 41's queued job happens to be in
at that exact moment — a timer-driven mock, not a fixed state). Decisive evidence this predates this
round entirely: `find test-results -iname "*preprocess-hits*"` turns up **20+ prior failure
directories** (Playwright only writes `error-context.md` on failure) going back through `b2-*`,
`b3-cal*` and `fxu1-*` — this exact test has been intermittently failing since the B2 build lane, long
before this fix round touched anything. `simulator-hits*` gained its first two directories only in
this round's two full-suite runs, both when run as part of the whole 92-test suite and never in
isolation — consistent with load-dependent flakiness, not a content regression tied to any specific
edit.

**Not fixed**: the assigned findings (7 items above) name nothing about these two thresholds, and
"edit what the findings name and nothing more" is the explicit rule for this lane — nudging an
already-self-described-as-arbitrary number without being asked is exactly the kind of scope creep the
program's other rules (measured claims, docs as source) argue against. Recommend: the next lane that
does own `preprocess.spec.ts`/`simulator.spec.ts`, or a dedicated stabilization pass, either widens
these two caps by the couple of points the calibration-issue comment already anticipated, or replaces
the point-in-time capture with 2–3 samples and a median, since a timer-driven mock plan by
construction cannot promise the same log-line count between runs.

## 3. Gate

`npm run typecheck && npm run lint && npx vitest run && npm run build` — all green (typecheck clean;
lint 0 errors/3 pre-existing `react-hooks/incompatible-library` warnings unrelated to this round's
files; vitest 617/617 across 54 files; build succeeds, `out/renderer/index.html` + chunks emitted).

Full e2e, run twice (`TIT_E2E_RUN_ID=fxu3-27848` then `fxu3-final-8222`, both
`bash scripts/e2e-quiet-check.sh npm run e2e`): **89 passed / 2 failed / 1 skipped** (92 total) both
times, identically — `viewer-real.spec.ts` skips as it always does (needs a real Tetravox embed this
environment doesn't have); the 2 failures are §2 above (`preprocess.spec.ts:155`,
`simulator.spec.ts:107`). Quiet-check PASS both times: no Electron/Chromium window ever reached the
screen (`CGWindowListCopyWindowInfo` clean, `layer=0` OWNERS never matched); frontmost before/after
`ghostty` both runs, with the wrapper's own non-failing note that focus passed through `Arc`/`Finder`
mid-run — the maintainer's own foreground activity, not a test binary, exactly the distinction the
wrapper is built to draw.

`screens.spec.ts` (dedicated `TIT_E2E_RUN_ID=fxu3-screens bash scripts/e2e-quiet-check.sh npx
playwright test tests/e2e/screens.spec.ts`): **5/5 green, PASS, quiet** — 48 captures in
`tests/e2e/artifacts/fxu3-screens/`. `pageHeaderHeight` for the two panel pages the default mock
fixture puts in the rail (`panel-source`, `panel-subject-info` — `cluster-permutation`,
`nilearn-visuals`, `nifti-group-average` are gated by `settings.panels` and not in this fixture's
rail, matching the critic's own round-1 capture) is **0 at every size/theme** (was 48 before this
round). Dead-space at 1280×light, all 12 rail pages (`pageHeaderHeight` alongside, confirming 0
everywhere but the two allowed exceptions):

| page | deadSpaceRatio | pageHeaderHeight |
|---|---|---|
| subjects | 0.5135 | 0 |
| preprocess | 0.6166 | 0 |
| simulator | 0.4151 | 0 |
| optimizer | 0.5775 | 0 |
| analyzer | 0.5772 | 0 |
| results | 0.3065 | 0 |
| viewer | 0.0042 | 0 |
| jobs | 0.9910 | 0 |
| panel-source | 0.8663 | 0 |
| panel-subject-info | 0.8660 | 0 |
| settings | 0.7016 | 28 |
| help | 0.2078 | 28 |

Jobs' 0.99 and both panels' 0.86–0.87 are pre-existing (unselected/empty states in this fixture, not
this round's concern — no finding named them); flagged here only because the gate asked for the full
table, not because they are new.
