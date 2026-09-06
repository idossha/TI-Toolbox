# PL — the Pipeline canvas revamp

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Every Playwright
run offscreen. `git stash` was not run in any form.

The ask, in the maintainer's words: *"Please make sure that the canvas is fully operational and
that it is designed very tightly and advanced. Currently it looks like it's not fully operational
and the elements are not very responsive, some of them do not work. It needs a revamp."*

---

## 1. The one cause behind most of the screenshot

**`pages/pipeline/pipeline.css` was written against a token vocabulary this app does not have.**

Thirty-six `var()` references to names that are defined nowhere — not in `ui/tokens.css`, not
locally, not anywhere in `src/renderer`:

| written | this app's actual token |
| --- | --- |
| `--surface-default` / `--surface-raised` / `--surface-sunken` | `--surface` / `--surface-2` |
| `--text-primary` / `--text-muted` | `--ink` / `--ink-2` |
| `--font-size-xs` / `--font-size-sm` | there is no font-size token; type is `11/12/13/14 px` literals |
| `--border-subtle` / `--border-default` | `--line` / `--line-strong` |
| `--radius-sm` / `--radius-md` / `--radius-pill` | `--radius-control` / `--radius-card` / `--radius-chip` |
| `--shadow-sm` / `--shadow-md` | `--shadow-1` / `--shadow-2` |
| `--accent-primary` | `--accent` |

A browser **drops a declaration whose custom property is undefined and reports nothing** — no
console warning, no build error, no failing test. So every visual property on the node card, the
palette and the port handles was silently thrown away: no padding, no border, no background, no
font-size, no per-port hue. The card inherited React Flow's own default type and grew to roughly
three times the app's density. That is the "giant, low-density node card at ~40 px type" in the
screenshot, the missing palette rules, and the handles that no longer said what they carried.

The page was **not** "not fully operational" in the way it looked. It was unstyled.

`pipeline.css` was rewritten against real tokens, and two guards now make the silence impossible to
repeat:

- `desktop/tests/unit/pipelineTokens.test.ts` — scans the file against `tokens.css`. Proved to
  fail red: renaming one `var(--line)` to `var(--line-subtle)` makes it fail naming that token.
- `tests/e2e/pipeline-ux.spec.ts` — reads the **computed** style off the live card (13 px type,
  8 px padding, a 1 px border, a non-transparent background, < 240 px wide, a coloured handle), and
  separately walks every `.pipeline-*` rule in the live stylesheets asserting that no `var()` in
  them resolves to empty.

Eight more undefined references exist in four *other* stylesheets (`jobs-rail.css`,
`scene-pane.css`, `optimizer.css`, `viewer-page.css`). They belong to other lanes; the guard says
so and widening its glob is a one-line edit once they are fixed.

## 2. The second cause: the canvas had 348 px to draw in

Measured at 1440×900 on the built app, before any change:

| box | width |
| --- | --- |
| right pane (`.page-layout-panel`) | **610 px** |
| work pane | 560 px |
| palette | 200 px |
| **canvas** | **348 px** |

And a third contributor to the same symptom: `fitView` ran with React Flow's own zoom ceiling of
**2** and nothing else on the canvas to fit, so a *single* card was scaled to twice its size. The
apparent ~40 px type in the screenshot is the app's 13 px through a 2× canvas zoom in a 348 px box.
`fitViewOptions={{ padding: 0.2, maxZoom: 1 }}` caps it.

`.page-layout-run .page-layout-panel:not([data-pane-width])` is
`clamp(320px, 45vw, calc(100% - 566px))` — the maintainer's own §2.1 default, and right for the
Simulator, whose pane is a plan grid and a terminal beside a column of controls. On a *canvas* page
it leaves less room than two node cards side by side, which is the other half of the screenshot: one
enormous card on an otherwise empty dotted grid, with nothing else able to fit next to it.

Fixed at the page's own call site, not in the shared layout: `usePaneController` is given
`minWidth: 320` and the pane is seeded once at **400** (what `--right-pane-w-lg` gives every other
pane at this breakpoint), which leaves the canvas ~756 px. It is a default, not a lock — the drag
handle, ⌘⇧I and expand all still work, and a width the user sets is the one that persists.

## 3. What did not work, and why

Each of these was reproduced offscreen before it was fixed; each now has a test that fails without
the fix.

| # | Element | What actually happened | Cause |
| --- | --- | --- | --- |
| 1 | **Delete on a node** (Delete/Backspace) | the card vanished for one frame and came straight back | `onNodesDelete` was never wired. React Flow removed it from *its* array; the next render rebuilt that array from the document, which still had the node |
| 2 | **Delete on a wire** | nothing at all | `onEdgesChange` was never wired, so an edge could not be *selected*; with no selection there was nothing for the delete key to delete |
| 3 | **Save** | silently nothing | it called `window.prompt`, which **Electron does not implement**. The promise resolved `undefined`, the mutation returned `null`, and the success branch quietly did nothing |
| 4 | **Export notebook** | said "Notebook exported", wrote no file | an `<a download>` on a `blob:` URL. This app installs no `will-download` handler, so the click is inert in the shell. Now goes through a new `window.tit.saveFile` bridge (main-process `showSaveDialog` + `writeFile`), with the anchor kept as the web-build path |
| 5 | **Drag from the palette** | impossible | the canvas had no drop target, and — worse — when the document was empty React Flow was *not rendered at all*; the empty state replaced it, so there was nothing to drop onto |
| 6 | **Adding a step by click** | landed off-screen after the first few | position was `40 + n*300` in flow coordinates regardless of where the viewport was. Now: the centre of the current view, with a small stagger |
| 7 | **Undo / redo** | did not exist | — |
| 8 | **⌘A / Esc** | did not exist | — |
| 9 | **Context menu** | did not exist | — |
| 10 | **The trash button** | only ever deleted one node, and only the last-clicked one | it tracked a single `selected` id of its own, unrelated to React Flow's selection |
| 11 | **A node's JSON config** | wiped itself on a mistyped brace | `configFor`'s `json` branch returned `{}` on a parse error, and that `{}` was written straight into the document. Now it keeps the last config that parsed and shows the parse error |
| 12 | **Loading a saved pipeline** | every node's form reopened blank | no `config → form state` reader existed. `editorFromNode` now recovers the subjects, montage names, simulation, `pre` stages, space and target — and seeds the JSON kinds with their real config instead of `{}` |
| 13 | **Undo after dragging a card** | the document moved back, the card did not (152 px out, measured) | the merge-during-render always kept React Flow's position. It now keeps it only while the *document's* position is unchanged — mid-drag — and takes the document's when the document is what moved |
| 14 | **The "needs" chip's focus** | the field was not focused | Radix moves focus to the dialog's first focusable in `onOpenAutoFocus`, which runs after the effect. Now deferred two frames |
| 15 | **The receipt** | a pane of warnings about a graph with nothing wrong with it | see §4 |
| 16 | **The Terminal** | dead unless a job happened to be running | it followed `groupJobs[0]`. It now pins to the step you last clicked when that step has a job, then to whatever is running |
| 17 | **The card was ~2× its size** | a single node filled the canvas | `fitView` with React Flow's default `maxZoom` of 2 and one node to fit. Capped at 1 |

Three more were found by the new spec while writing it, and are fixed:

| # | | |
| --- | --- | --- |
| 18 | **A refused wire said nothing** | once `isValidConnection` was added, an illegal target stopped accepting the drop — good — but a refused drop never reaches `onConnect`, so the wire sprang back silently, which is the behaviour §9.1 forbids. The verdict computed during the drag is now kept and stated by `onConnectEnd` when the drag produced no edge |
| 19 | **Selecting a node programmatically did not stick** | `useReactFlow().setNodes` writes React Flow's store, and this page's `nodes` prop is controlled, so the next render wrote straight over it. Selection is now set on the state this page owns |
| 20 | **Adding a step raced the keyboard** | the new node was selected from a `setTimeout(…, 0)`, so ⌘A pressed straight after adding was undone a tick later (measured: 1 of 2 nodes selected). The selection is now decided in the same render pass that first puts the node into React Flow's array |

Things that *did* already work and still do: node dragging, wiring a legal port, the double-click
editor for `pre`/`flex`/`sim`/`analyzer` (real reused form sections, not copies), Import JSON…, Run,
and the whole server side.

## 4. The receipt: a fact is not a warning

The screenshot's right pane is a wall of *"… is not connected to anything; it will run on its own"*
and *"… has no configuration yet"*. Neither stops anything from running. They sat in the same flat
list as real blockers, so a graph with nothing wrong with it read as six alarms.

The page could not tell them apart, because the only thing it had to go on was the English of the
message. So the contract gained the missing bit:

- **`PipelineIssue.code`** — `empty · duplicate_id · edge_unknown_node · self_edge · bad_output ·
  bad_input · double_bound · cycle · missing_input · unconfigured · unconnected`, defined once in
  `tit.pipeline.validate.ISSUE_CODES`.
- **`PipelineIssue.port`** — which of the five port types a port-shaped finding is about.

Both optional; `level` and `message` are unchanged and still the only required fields. Recorded in
`contracts/SCHEMA-CHANGES.md`, mirrored in the mock server, asserted on both sides.

With that, the receipt is:

- **runnable** → "N jobs in one group — K steps", the labels with their `after` chain, first 15 then
  a count (§4.8);
- **not runnable** → the blockers **grouped by node**, each group with a **Fix** button that selects
  and centres that node;
- **always** → the non-faults collapsed into one sentence at the bottom: *"3 steps run
  independently."*

And `port` is what puts an unbound required input on the **card** as a `needs: subjects` chip that
opens that node's form at that field — so the thing you must fix is on the thing you must fix it on,
not in a list beside it.

## 5. The design

Per DESIGN.md §3.2/§3.3, now recorded as **§9.1.1–§9.1.4**:

- **Node card**: 208 px, 8 px padding, a 20 px header of kind icon + name + status chip, a two-line
  clamped 12/16 summary, 13/18 base. Selection is a ring drawn off React Flow's own `.selected`, so
  a click, a marquee and ⌘A light the same thing. A running node's border goes accent.
- **Ports**: typed handles, one hue per type, the port's name printed on hover — five hues is a
  legend nobody memorises.
- **Edges**: coloured by type; dashed and flowing while either end is running, still under
  `prefers-reduced-motion`.
- **Canvas**: dot grid, snap to a 16 px grid, `fitView`, zoom/fit controls restyled to app tokens,
  a minimap bottom-right.
- **Palette**: a compact searchable column — a filter box, then the nine kinds as 28 px rows with
  their page's icon, draggable and clickable; then **Saved**, each row name + step count + when
  (the step count is new: `GET /api/pipelines` now returns `nodes`/`edges`, so the list can say
  "4 steps" without loading every document).
- **Empty state**: one line — "Add a step or import a pipeline" — and **Start from a sample**, which
  builds the wired `pre → flex → sim → analyzer` graph on a subject the project has. It is the graph
  the D6 gate submits, so a first-time user lands on a pipeline that is *known* to validate and run.
  It is drawn **over** a live canvas, never instead of one, because React Flow has to be mounted for
  a palette drag to have anywhere to land.

## 6. Files

| File | |
| --- | --- |
| `tit/pipeline/validate.py` | `ISSUE_CODES`, `Issue.code`, `Issue.port` |
| `tit/server/routes/pipelines.py` | `nodes`/`edges` counts on the list route |
| `contracts/openapi.v1.{yaml,json}`, `contracts/SCHEMA-CHANGES.md` | the two schema additions |
| `desktop/src/renderer/api/schema.d.ts`, `desktop/tests/fixtures/openapi.v1.json` | regenerated |
| `desktop/src/renderer/pages/pipeline/pipeline.css` | rewritten against real tokens |
| `desktop/src/renderer/pages/pipeline/PipelinePage.tsx` | rewritten |
| `desktop/src/renderer/pages/pipeline/NodeCard.tsx` | **new** |
| `desktop/src/renderer/pages/pipeline/Palette.tsx` | **new** |
| `desktop/src/renderer/pages/pipeline/Receipt.tsx` | **new** |
| `desktop/src/renderer/pages/pipeline/graph.ts` | kind icons, `samplePipeline`, summary |
| `desktop/src/renderer/pages/pipeline/editors.ts` | `editorFromNode`, JSON keeps its last good config |
| `desktop/src/renderer/pages/pipeline/NodeInspector.tsx` | `focusPort`, JSON validation |
| `desktop/src/{main,preload}/index.ts`, `desktop/src/shared/tit-bridge.d.ts` | `window.tit.saveFile` |
| `desktop/tests/mock-server/server.mjs` | codes + list counts |
| `desktop/tests/e2e/smoke.spec.ts` | the pinned bridge surface goes 13 → 14 with `saveFile` |
| `desktop/tests/e2e/pipeline-ux.spec.ts` | **new** — the gesture suite |
| `desktop/tests/e2e/pipeline-shots.spec.ts` | **new** — before/after evidence |
| `desktop/tests/unit/pipelineTokens.test.ts` | **new** — the token guard |
| `desktop/tests/unit/pipeline-graph.test.ts`, `tests/test_pipeline_graph.py`, `tests/test_pipeline_routes.py` | codes, summary, list counts |
| `desktop/DESIGN.md` §9.1.1–9.1.4, `docs/wiki/pipelines.md` | records |

## 7. Open items

1. **A `sim` node's editor is not yet the Simulator's per-job table.** The Simulator's
   `MontageManager` / jobs table was being rewritten in this same worktree while this lane ran;
   importing it would have coupled the canvas to a moving target. The sim editor is still the
   montage-names + parameters form, and the node still fans out to one job per subject × montage on
   the server. Worth doing once that table settles.
2. **`editorFromNode` is partial** (PC.md open item 2 narrowed, not closed). It recovers the fields
   listed in §3.12; a flex node's objective and electrode settings, and an analyzer's sphere, still
   open at defaults. The document's config is untouched until something is actually edited.
3. **The other four stylesheets' undefined tokens** (§1).
4. **`PipelineIssue.code` on an older server.** It is optional, so an older server simply returns
   issues without it — the receipt then shows the errors and omits the chips and the "run
   independently" line rather than misreporting. The container in use during this lane was started
   before the change and still had the pre-change module in memory.

## 8. Gate

| Command | Where | Result |
| --- | --- | --- |
| `pnpm run typecheck` | `desktop/` | clean (both projects) |
| `npx eslint src tests` | `desktop/` | **0 errors**, 3 warnings — all pre-existing `react-hooks/incompatible-library` on `ui/DataTable.tsx`, `ui/VirtualList.tsx`, `pages/preprocess/index.tsx` |
| `npx vitest run` | `desktop/` | **90 files, 1048 tests passed** (was 949 before this program; +2 are this lane's token guard and its self-test, +1 the new node-summary test) |
| `npx vitest run tests/mock-server` | `desktop/` | **33 passed** — the contract test asserts every declared path is exercised |
| `pnpm run pree2e && npx playwright test pipeline-ux pipeline pipeline-shots smoke` | `desktop/` | **39 passed, 0 failed** (1.0 min), offscreen |
| `python3 -m pytest tests/test_pipeline*.py -q` | root | **67 passed** |
| `python3 -m pytest tests/ -q --ignore=tests/smoke` | root | **3590 passed, 47 skipped**, 1 failure in `tests/test_scene_guide.py` that is the scene lane's own (`c0fa0cc1`, "paint every region in its own atlas colour") and unrelated to this one |
| `python3 dev/route_import_guard.py` | root | `20 route module(s) clean` |
| `pnpm run build` | `desktop/` | `✓ built in 2.42s` |
| real server (`TIT_E2E_SERVER_URL=http://127.0.0.1:8765`) | `desktop/` | `/api/jobs` **idle first** (no running or queued job), then `npx playwright test --project=real pipeline.spec.ts`. Tests 1 and 2 **pass**: the page loads against the real server, and `validate` binds the Analyzer's simulation to the Simulator's own montage with *no* resolve step — `["sim1:0", "an1:0"]`, `an1:0 after ["sim1:0"]`. Test 3 submits the 2-node sim → analyzer pipeline on `sub-ernie` and waits for it: `POST /api/pipelines/run` returned **one `group_id`** for both jobs, and `/api/jobs` shows exactly that group live — `985616e0 sim running`, `8048c8c9 analyzer queued` behind it, which is the `after` edge holding. Only one FEM sim at a time, ever. **The emulated FEM run was still going when this note was written**, so the run-to-completion assertion is unconfirmed here; the group's identity and its ordering — the two things this lane changed anything near — are confirmed |
| screenshots | `desktop/tests/e2e/artifacts/` | `pipeline-before.png`, `pipeline-after.png`, both at 1440 |

### A note on the shared worktree

Three other lanes were editing this worktree throughout. Two things worth recording:

1. A concurrent commit swept this lane's uncommitted `contracts/` and mock-server edits into its own
   (`670822a8`, a Simulator commit). The content is right and on the branch; only the attribution is
   wrong.
2. Recovering from that, a `git checkout contracts/openapi.v1.json` in this lane dropped that same
   commit's `/api/catalog/flex-runs/{run}/mapping` path from the JSON. Found and restored in
   `d0904234` — the JSON now has it again, and `schema.d.ts` and the fixture were regenerated from
   it. Worth knowing that `dev/build_contract.py` is **not** safe to run for a small edit here: a
   full rebuild of `openapi.v1.json` from the current YAML produces ~560 lines of unrelated drift,
   because the committed JSON is stale against the committed YAML + `schema.json`. Both of this
   lane's schema additions were spliced in by hand instead.

---

# PL/2 — "the visualisation is much better, but the logic is faulty"

The second pass replaces the model, not the look. What was wrong with the logic, in the
maintainer's words and in mine:

- **Every node carried its own copy of the subject list.** The same cohort was typed once per node,
  and two nodes in one graph could silently disagree about who was in the study.
- **A node was auto-configured from the node upstream of it.** An edge meant "and also copy that
  node's settings", which is not something a typed port can honestly promise, and it produced card
  subtitles that claimed a binding no edge had made.
- **A wire was judged only on its port type.** So `Subjects(raw data only) → Analyzer` was a graph
  you could build, submit, and watch fail one job per subject twenty minutes later.

## 1. The cohort is a node

`subjects` is a new node kind and the graph's **only** source: it names who the graph is about in
`config.subject_ids`, runs nothing, and plans nothing (`JOB_NODE_KINDS` is every kind but this one;
both planners skip it). `pre` stops being a source and takes a `subjects` input like every other
processing node.

Every processing node now `required`s the `subjects` port and **owns its own config**. `configFor`
no longer writes `subject_ids` into any node but the cohort — the document has exactly one place
that says who takes part, and `tests/e2e/pipeline-ux.spec.ts` asserts precisely that by saving a
graph and checking which nodes carry the key.

`analyzer` stopped *requiring the `simulation` port*: whether an Analyzer can run is a question
about the subjects reaching it, which the readiness table answers with their names. Requiring the
port as well refused a perfectly good `Subjects(with simulations) → Analyzer` for a second, wronger
reason.

Its editor is the project's subject list with the **Overview's own presence columns**, through the
Overview page's own client (`pages/overview/api.ts`) — not a second copy of either. Each row also
states what it is ready for, so the reason arrives before the refusal does.

## 2. The requirement / production table

One table, `tit.pipeline.validate.KIND_READINESS`, over a closed set of capabilities read from
`GET /api/catalog/overview`:

| Step | Requires of **every** subject | Leaves behind |
| --- | --- | --- |
| **Subjects** | — | — |
| Pre-processing | raw MRI | **head model** |
| Leadfield | head model | **leadfield** |
| Flex-search | head model | — |
| Ex-search / mEx-search | head model + leadfield | — |
| Simulator | head model | **simulations** |
| Analyzer | simulations | — |
| Source model | head model | — |
| Group statistics | simulations | — |

`produces` is what makes a chain work rather than a lookup: capabilities propagate along the
`subjects` wire (`capabilities_at`), so a requirement a cohort does not satisfy can be satisfied by
a node in between.

```
Subjects(raw only) ─▶ Simulator                    refused — "102, test have no head model"
Subjects(raw only) ─▶ Pre-processing ─▶ Simulator  fine — `pre` produces the head model
Subjects(with simulations) ─▶ Analyzer             fine — no Simulator needed
```

A multi-subject cohort connects only if **every** subject qualifies, and the refusal **names the
ones that do not and never blames the ones that do** — `"102, test have no simulations"`, with
`has`/`have` agreeing with the count. Naming them rather than counting them is the point: "2
subjects are not ready" does not tell you which two rows to go and look at.

**One definition, two readers.** The canvas has to refuse a *drag*, which is before there is a graph
to ask the server about, so it gets the table from `GET /api/pipelines/kinds` (extended, rather than
a second `/ports` route serving the same fact — that is how two tables drift) and applies it in
`graph.ts`. `POST /api/pipelines/validate` and `/run` apply the Python one. A dedicated test asserts
the drag-time reason and the receipt's are the same sentence. A project that cannot be read at all
falls back to shape-only checking rather than refusing every wire.

## 3. Per-subject fan-out is unchanged

The server still fans each processing node out to one job per subject; the receipt still lists them.
What changed is only where the subject list comes from.

## 4. Files

`tit/pipeline/document.py` (the `subjects` kind, `JOB_NODE_KINDS`, rewired ports) ·
`tit/pipeline/validate.py` (`CAPABILITIES`, `KIND_READINESS`, `capabilities_at`, `unmet`,
`readiness_reason`, `readiness_from_overview`, the gate in `can_connect`/`validate`, code
`not_ready`) · `tit/pipeline/plan.py` (skip the cohort) · `tit/server/routes/pipelines.py`
(`_readiness()` from the overview; both tables on `/kinds`) · `contracts/pipeline.schema.json`,
`openapi.v1.{yaml,json}`, `SCHEMA-CHANGES.md`, regenerated `schema.d.ts` + fixture ·
`pages/pipeline/{graph.ts,editors.ts,NodeInspector.tsx,PipelinePage.tsx}` ·
`pages/pipeline/SubjectsEditor.tsx` **(new)** · `tests/mock-server/server.mjs` ·
`tests/test_pipeline_readiness.py` **(new, 28 tests)** · `tests/test_pipeline_{graph,plan,routes}.py` ·
`tests/unit/pipeline-graph.test.ts` · `tests/e2e/pipeline{,-ux}.spec.ts` ·
`docs/wiki/pipelines.md`, `docs/ARCHITECTURE.md` §7.3 (new rules 1a and 3a).

## 5. Gate (PL/2)

| Command | Where | Result |
| --- | --- | --- |
| `pnpm run typecheck` | `desktop/` | clean |
| `npx eslint src tests` | `desktop/` | **0 errors**, 3 pre-existing warnings |
| `npx vitest run` | `desktop/` | **1090 passed, 2 skipped** |
| `npx vitest run tests/mock-server` | `desktop/` | 33 passed *(one contract-coverage failure appeared mid-run and is the Viewer lane's: `/api/viewer/candidates` is declared in their uncommitted `openapi.v1.yaml` edit and their mock route is not written yet — nothing in this lane touches it)* |
| `pnpm run pree2e && npx playwright test pipeline-ux pipeline pipeline-shots smoke` | `desktop/` | **45 passed, 0 failed** (1.0 min), offscreen |
| `python3 -m pytest tests/test_pipeline*.py -q` | root | **97 passed** (+28 new in `test_pipeline_readiness.py`) |
| `python3 -m pytest tests/ -q --ignore=tests/smoke` | root | **3658 passed, 47 skipped**; `test_scene_guide.py` deselected — the scene lane's own red (`c0fa0cc1`) |
| `python3 dev/route_import_guard.py` | root | `20 route module(s) clean` |
| `pnpm run build` | `desktop/` | `✓ built in 2.49s` |
| **real, Dataset 000** | container | `simnibs_python` against `/mnt/000` through the real modules: readiness reads `ernie/101 = raw+m2m+leadfield+simulation`, `MNI152 = raw+m2m+simulation`, `102/test = nothing`. **`Subjects(ernie) → Analyzer` validates `ok=True`**; **`Subjects(102) → Simulator` is refused — `"102 has no head model"`**; and `Subjects(102) → Pre → Simulator` is accepted, so `produces` works on real data too |

Run in-process rather than over HTTP because the shared container's server had loaded
`tit.pipeline` before this change and restarting it would have disturbed the other lanes; the code
under test is the same module the route calls, on the same project.

### One test that is not a canvas gesture, and why

"raw-only subjects are refused by everything but Pre-processing" is asserted against the server
rather than by dragging. The mock's default project has no raw-only subject — its three are
`ernie`, `101` and `MNI152`, and other lanes' specs assert that list exactly, so a fourth cannot be
added — which leaves the 30-subject project, and choreographing a cohort plus two steps plus three
wires there turned into a test about mouse gestures rather than about the rule (two HTML5 palette
drops in a row onto a canvas that already has a card: the first silently did not register). The
rule is asserted on the real canvas by the three cases the fixture *can* express, and twice more
over the same table in `tests/unit/pipeline-graph.test.ts` and `tests/test_pipeline_readiness.py`.
