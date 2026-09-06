# v3 UI program — "use the real estate" (plan of record, 2026-09-04)

Maintainer's brief, verbatim: *"we try to replicate the original TI toolbox with PyQt too closely. Now, with
the new framework, we have much more flexibility … maximize and optimize our digital real estate and improve
our overall UI/UX to the maximum … perform a development and testing loop … take screenshots … give yourself
feedback … light/dark theme, by default light."* Plus eight annotated screenshots, each turned into a decision
below. Supersedes the layout parts of `dev/notes/v3-ux-redesign-plan.md` §1–§3 where they conflict; the
density rules, tokens and offscreen harness stay.

House rules (from `/Users/idohaber/00_development/agentic-rules`, `docs/PRINCIPLES.md`, skills
`testing-frontend-offscreen`, `project-docs`): every rule states the failure it prevents; **an agent judges
numbers, not pictures** — every UI claim ships a measured assertion; GUI tests run hidden and never take the
screen; no AI co-author trailers; docs are the single source.

## 0. Decisions (from the maintainer's screenshots)

| # | Decision | Failure it prevents |
|---|---|---|
| U1 | **Real estate.** Every page uses the full width of the content area (no 880 px cap, no decorative margins). A page has at most two panes: work + a *purposeful* right pane (run panel, preview, or nothing). Measured: dead-space ratio of the content area ≤ 25 % at 1280×800 and 1440×900 on every page in its populated state. | The Pre-processing screenshot: a 300 px Plan card and 900 px of nothing beside a form. |
| U2 | **Run panel** on every run page (Pre-processing, Simulator, Optimizer, Analyzer): right pane = **Plan** (top, U3) + **Terminal** (rest of the height: the live console of the running or last job of that page's kind, virtualised, follow-tail, level colours, "Reveal log"). The action bar stays at the bottom of the work pane. | Dead space beside forms; the user having to open the jobs panel to see what their run is doing. |
| U3 | **Plan is a structured grid**, not prose: a stats strip (jobs · CPUs · memory · waits as compact tiles), then a **subject × stage matrix** whose cells are one chip each from a fixed vocabulary — `new`, `skip` (exists), `overwrite`, `blocked`, `wait` — with one legend, no repeated "Output" labels, no free text except warnings (which get a callout). | The current Plan card repeats "Output — exists, will skip" three times with inconsistent chips. |
| U4 | **Results is subject-centric**: no subject dropdown; a left list of subjects (all of them, with output counts) → the selected subject's **outputs tree** (simulations, flex, ex/mex, analyses, reports; group outputs under a "Group" pseudo-subject) with type badges and a filter box; right pane = preview (report iframe, artifact list, "Open in viewer"). Default subject = the current one. | The tab-per-kind + dropdown page that mirrors the PyQt tabs. |
| U5 | **Viewer page = the embed.** TI's inspector (Layers / Cursor / Scene) is removed entirely; the embed owns its chrome. The page is the 40 px source bar + the iframe filling the rest (≥ 1200 px wide at 1280 with the icon rail). | Duplicated controls with the embed's own panels. |
| U6 | **Context bar is slim**: project name · subject switcher (id + chevron, no presence chips, no "+ Add subjects") · ⌘K · connection · running count. Presence chips live only in the Subjects page. | A top rail carrying data that belongs to a table. |
| U7 | **Nav rail is flat and workflow-ordered**, no subject-id group header, no subject scoping in the rail: Subjects · Pre-processing · Simulator · **Optimizer** (one page: Flex / Ex / mEx method segment) · Analyzer · Results · Viewer · Jobs · Settings · Help. Icons + labels at ≥ 1440; icons + tooltips below 1440 (Q1 below). | "101" printed as a group label; two Optimizer entries copied from PyQt tabs. |
| U8 | **Status bar is contextual**: each page registers its cells (Viewer: RAS · space · renderer; Jobs: running/queued/failed counts; run pages: last job state + elapsed; Results/Subjects: item counts). Always at the right: connection · `tit x.y · api vN`. A cell with no value is not rendered — never "—". | "RAS — Space — Renderer —" on the Jobs page. |
| U9 | **Theme**: light by default, dark available (Settings and ⌘K "Theme: …"), system-follow optional; both screenshotted for every page at 1280 and 1440. Tokens unchanged. | Dark-by-default drift from the earlier lanes' screenshots. |
| U10 | **Dev loop is the method**: every build lane iterates build → offscreen screenshots (light+dark, 1280×800 + 1440×900) → DOM metrics → self-critique against the checklist (§3) → fix, at least two rounds, and records the numbers per round in its notes. A critic panel then reviews the artifacts and a fix round follows, bounded to two passes. | "Looks fine" as a gate. |

**U6 amendment** (2026-09-03 evening, from the maintainer's screenshots — "we still need to remove
this from the top rail"): the project crumb and the subject switcher this row specified are gone
from the context bar. `dev/notes/v3-pipelines-program.md` §6 U11 is the record of the decision and
DESIGN.md §2.3 the implemented contract; the store, `data-subject`, the palette's subject rows and a
page's own subject/batch control (Pre-processing already has one) all stay — scope moved off the
rail, it did not disappear.

**U1 amendment — the dead-space number the run pages are actually held to** (2026-09-04, lane LAY,
after the scene+IA plan's §4). U1 wrote "≤ 25 %" for every page. On a **run** page that number was
never met by any lane and, measured, is not reachable without turning a form into something that is
not a form: a label-left row is a 12 px label and a 28 px control in a 389 px column, and a page of
them is ~40 % ink at best. The plan of record `dev/notes/v3-scene-ia-plan.md` §4 L5 therefore states
**≤ 45 % on a run page's populated state**, at both sizes in both themes, and that is the gate
(`desktop/tests/e2e/layout.spec.ts`). Measured after the layout pass: Pre-processing 36.3 / 42.0 %,
Simulator 34.4 / 38.3 %, Optimizer 41.6 / 42.8 %, Analyzer 40.8 / 43.5 % (1280x800 / 1440x900,
identical in both themes) — from 61.3 / 43.0 / 55.0 / 57.0 % before it. U1's <= 25 % still stands for
the **browse** and **embed** shapes. Round-1 UI/UX closed the recorded browse gaps against the
same 4-subject fixture: Results 7.4 / 6.7 %, Subjects 16.8 / 14.7 %, Viewer 0.4 / 0.4 %, and Help
20.8 / 20.8 % (1280x800 / 1440x900, identical in both themes). §3's checklist item 1 is read with
this split.

**U2 amendment — the right pane's lower half is tabbed** (2026-09-04, from the scene plan's S7): it
is **Plan** over **Terminal · Scene**, Scene by default while configuring and Terminal from the
moment a job of that page's kind is queued or running. U2's "Terminal (rest of the height)" is now
one of two tabs in that space. DESIGN.md §4.5/§4.6 and `pages/_shared/run/RunPaneTabs.tsx` are the
implemented contract.

**§2 amendment — the instrument gained three readers** (2026-09-04, lane LAY). `tests/e2e/_metrics.ts`
now also exports `actionBarReach(page, step)` (scans the work pane's whole scroll range and
hit-tests every enabled control's centre — L4's assertion), `horizontalOverflow(page)` (L5's "no
horizontal page scrolling"), and two diagnostics the layout rounds were steered by rather than
gated on: `deadSpaceProfile(page)` (the same ratio split by pane and by horizontal band) and
`deadSpaceByChild(page, root, sel)` (per component, with its height). `deadSpaceRatio`,
`paneWidths` and `firstScreenControls` are unchanged, deliberately: every earlier lane's number was
taken with them, and a mid-programme redefinition would make those numbers incomparable.

**Q1** (raised while building B1, settled during the FXU3 fix round): U7 wrote the label breakpoint
as 1280, but a 216 px labelled rail at 1280 leaves only 1064 px of content — short of the Viewer's
own ≥ 1200 px embed floor (U5). Rather than force the Viewer alone onto a permanent icon rail, the
rail is **icons below 1440, labels at ≥ 1440**, for every page: 1440 − 1280 = 216 − 56, so the
content box lands at the same 1224 px at both sizes and no page pays a special case. DESIGN.md
§2.1/§2.2/§9, `NavRail.tsx`'s `LABEL_RAIL_QUERY`, and `tests/e2e/_helpers.ts`/`screens.spec.ts` all
implement and cite this as "Q1" — this line is what they cite.

## 1. Layouts

```
Run page (U2)                                     Results (U4)                              Viewer (U5)
┌───────┬──────────────────────┬───────────────┐  ┌───────┬──────────┬───────────┬────────┐  ┌───────┬────────────────────────────┐
│ rail  │ work pane (form,     │ RUN PANEL     │  │ rail  │ subjects │ outputs   │preview │  │ rail  │ source bar (40)            │
│ 56/216│ flush sections,      │ ┌───────────┐ │  │       │ list     │ tree      │ report │  │       ├────────────────────────────┤
│       │ 2-col grid, fills)   │ │ PLAN grid │ │  │       │ + counts │ + filter  │ iframe │  │       │ <iframe> Tetravox embed     │
│       │                      │ ├───────────┤ │  │       │          │ + badges  │ /files │  │       │ (fills; ≥1200 px @1280)     │
│       │                      │ │ TERMINAL  │ │  │       │          │           │ open in│  │       │                            │
│       ├──────────────────────┤ │ (fills)   │ │  │       │          │           │ viewer │  │       │                            │
│       │ action bar 44        │ └───────────┘ │  └───────┴──────────┴───────────┴────────┘  └───────┴────────────────────────────┘
├───────┴──────────────────────┴───────────────┤  jobs rail 32/260 · status bar 24 (contextual cells)
```
Widths: rail 56 (< 1280) / 216; run panel 360–420 px, resizable, collapsible (⌘⇧I) — never the only thing
on the right; Results columns 200 / flex / 40 %; the Viewer has no inspector.

## 2. Contracts
- `PageDef.statusCells?: () => StatusCell[]` or a `useStatusCells(cells)` hook (B1) — pages register cells; the shell renders them; nothing else writes the status bar.
- `<RunPanel kind="pre|sim|flex|ex|mex|analyzer" plan={PlanModel} subjects={…} />` (B2, in `pages/_shared/run/`) with `<PlanGrid>` and `<JobTerminal jobFilter>`; the action bar keeps `Run` and the digest.
- `PlanModel` = `{ stats: {jobs, cpus, memoryGb, waits}, stages: Stage[], subjects: SubjectPlan[] , warnings: string[] }` built from `POST /api/plan/{kind}` (server unchanged).
- `desktop/tests/e2e/_metrics.ts` (B1): `deadSpaceRatio(page, selector)` (grid sample of `elementFromPoint` hits that resolve to a leaf with text, an input, a canvas/iframe or an image, versus background), `paneWidths(page)`, `firstScreenControls(page)`; `screens.spec.ts` captures every page in both themes at both sizes and writes `metrics.json` under the run's artifact dir — the lanes' and the critic's shared instrument.

## 3. Self-critique checklist (every lane, every round; the critic uses the same list)
1. Dead-space ratio ≤ 25 % on the populated state; no pane exists without content (U1).
2. Nothing on screen restates the nav label; no page header (unchanged from v2).
3. Every chip/badge is from the shared vocabulary; no ad-hoc colours.
4. Every number is tabular; units are suffixes; paths are mono and truncate from the left.
5. Both themes: contrast ≥ 4.5:1 for text (token test), no hard-coded colours.
6. Status bar shows only registered cells; no placeholder dashes.
7. The first screen (no scroll) at 1280×800 shows all Tier-1 controls of a run page.
8. Keyboard: ⌘K, ⌘J, ⌘⇧I, Esc scoped; focus visible.
9. Copy: sentence case, verbs on buttons, no exclamation marks, no "Freeview/Gmsh/X11".
10. The page still passes its e2e spec, and the spec asserts DOM state, not pixels.

## 4. Lanes
| Lane | Model | Owns | Delivers |
|---|---|---|---|
| **U0 Design** | Opus | `desktop/DESIGN.md` (v3: §2 layouts, §4 run panel + plan grid, §9 nav, §10 viewer, §11 status bar, §12 dev loop), `dev/notes/v3-ui-program/wireframes.md` | Per-page ASCII wireframes at 1280 and 1440, the plan-grid spec, the status-cell registry spec, the metric definitions, the checklist with numbers |
| **B1 Shell + instrument** | Opus | `desktop/src/renderer/app/**`, `ui/Layout.tsx`, `ui/Chrome.tsx`, `ui/tokens.css` (theme default only), `tests/e2e/{_helpers,_metrics,screens.spec}.ts`, `tests/unit/shell-*` | U6, U7 (rail; Optimizer merge target id `optimizer`), U8 registry, U9 default light + palette/Settings hook, PageLayout v3 (`rightPane` variants), the metrics instrument and screens spec |
| **B2 Run pages** | Opus | `pages/_shared/run/**` (new), `pages/preprocess/**`, `pages/simulator/**`, `pages/analyzer/**` | RunPanel + PlanGrid + JobTerminal; the three pages on it; two dev-loop rounds each |
| **B3 Optimizer merge** | Opus | `pages/optimizer/**` (new), `pages/optimizer-flex/**` + `pages/optimizer-ex/**` (delete), `pages/_shared/roi/**`, their specs | One page, Method segment Flex/Ex/mEx, one ROI picker, on RunPanel (polls for B2's component; codes against §2 meanwhile) |
| **B4 Results** | Opus | `pages/results/**`, `pages/subjects/**` (presence chips home; subject-centric summary) | U4 outputs browser + preview; Subjects page as the data home |
| **B5 Viewer** | Sonnet | `pages/viewer/**`, `viewer/**` (store surface only), `tests/e2e/viewer*.spec.ts` | U5: inspector removed, full-width embed, status cells registered |
| **B6 System pages** | Sonnet | `pages/{jobs,settings,help}/**`, their specs | Status cells, theme control in Settings, Help keyboard sheet copy, jobs page real-estate |
| **C Critic panel** | Sonnet ×2 (designer, researcher) then a fix round (Opus/Sonnet by finding) | reads `screens` artifacts + metrics | Findings by checklist item with numbers; bounded to two rounds |

Gates per lane: `npm run typecheck && npm run lint && npx vitest run && npm run build`, the lane's specs under `scripts/e2e-quiet-check.sh`, and the lane's two dev-loop rounds recorded with metrics in `dev/notes/v3-ui-program/<lane>-notes.md`. Final: full e2e quiet, screens artifacts for every page light+dark at both sizes, `metrics.json` within limits.
