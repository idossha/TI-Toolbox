# Lane CX4 — second consolidation: seams, records, gate

Branch `feature/v3-electron-gui`, worktree `.claude/worktrees/v3-electron-gui`, 2026-09-06.
Plan of record `dev/notes/v3-native-panes-external-viewer-plan.md`; lanes
`{CX3,TR,PL,TI,VM,VM2,OJ}.md`. Every Playwright run was **offscreen and serial** — never two at
once. `git stash` was not run in any form.

Four lanes in one worktree had reported reds against each other's pages, and every one of them
disowned the same `layout.spec.ts` failure. The job here was to find out who was right.

---

## 1. Seams

### (a) `preprocess light 1440x900` — 64.5 % against 0.62, disowned by four lanes

Every lane was right to disown it, and every lane was looking in the wrong place — including the
comment at the constant, which is what kept sending them there.

`LAY_DIAG=1` prints a *profile*, not just a ratio, and the profile settles it:

| page @1440 light | dead | work | right |
|---|---|---|---|
| **preprocess** | **64.5 %** | **40.4 %** | **82.6 %** |
| simulator | 37.0 % | 50.6 % | 14.0 % |
| optimizer | 51.4 % | 79.2 % | 16.3 % |
| analyzer | 48.3 % | 74.5 % | 16.3 % |

Pre-processing's **work column is the best-filled of any run page** — better than the two pages
that pass. Its children measure 11–25 % dead each. The 64.5 % is almost entirely the **right
pane**, and that pane is a decision rather than a defect. `RunPanel.tsx` states it in its own
header:

> Pre-processing has no head model to preview and must not grow a tab strip with one empty half.

So this page's pane is a Plan grid over a Terminal that is idle until a run starts, where every
other run page fills the same pane with a 3-D canvas. **Nothing can honestly go in the gap**: the
subject whose anatomy would be drawn there is the subject this page exists to create, and inventing
rows to fill it is precisely what L5a exists to catch.

The allowance therefore moves to **0.66** with that measurement and that reason written at the
constant. The old comment attributed the number to the work column — the removed ground rows, the
removed receipt strip — and that attribution is what four lanes checked, found untouched, and
correctly concluded was not theirs. The number moved with the *pane*, not the column.

Measured 59.9 % @1280x800 and 64.5 % @1440x900, identical in light and dark, on the three-subject
fixture; both fall back towards the global 0.45 as a project's subject list grows and as soon as a
job is running and the Terminal fills.

### (b) The two Optimizer reds the Viewer lane saw

Both real, both the Optimizer lane's page, neither the Viewer's.

**`#optimizer-run-name` never appears.** Correct — it does not exist. The Optimizer's page-level run
name became a per-row `#opt-run-name-<rowId>` inside the jobs table's row editor (`JobRows.tsx`),
which is a dialog. Two specs referenced the dead id:

* `page-memory.spec.ts:383` used it to prove a control in a *hidden* panel cannot take focus. It now
  addresses the first focusable in that panel structurally — the claim was never about which
  control.
* `_pageMemory.ts:136` used it as "something typed". This one was worse than a red: it was guarded
  by `if (count > 0)`, so it silently typed **nothing** and the helper's own
  "this page offered nothing to change" assertion was carried by other state. It now fills the
  first text field in the page's work column, and the run log shows it landing in
  `Filter subjects: n2-probe` on Pre-processing.

**A run-page scroll comes back 66 instead of 80.** Not an app defect and not a memory failure. The
test set `scrollTop = Math.min(80, max)` and asserted the value survived a collapse/expand cycle.
Collapsing the pane gives the work column the whole window, its content re-flows shorter, and the
browser **clamps `scrollTop` to the new maximum on the spot** — a loss no application code can undo
on the way back. 80 was inside the range when it was written and is outside it now that the
Simulator's page-level sections became a jobs table. The offset is now half the available range,
which is inside both widths' range and still nonzero; the run prints `scroll=131->131`.

### (c) `tests/mock-server` contract coverage — already closed at HEAD

`contract.test.ts` does not merely exercise routes, it asserts
`[...exercised].sort()` equals `[...declared].sort()` over every path+method in
`contracts/openapi.v1.yaml` (minus the two WebSocket upgrades, which have their own tests). It
**passes**: 33 tests across the two mock-server files. The routes PL saw missing mid-flight are all
present and all exercised — `/api/viewer/candidates`, `/api/viewer/presets{,/{name}}`,
`/api/catalog/flex-runs/{run}/mapping`, `/api/pipelines/kinds`. Nothing to reconcile; recorded
because "declared == exercised" is the property that makes this test worth having and it is easy to
weaken by accident.

### (d) `dev/build_contract.py` — the generator had a real defect, and it was not drift

OJ and PL both reported that a full rebuild produces ~560 lines of unrelated diff, and PL concluded
the committed JSON was stale against the YAML and hand-spliced both of the day's schema additions
rather than run the generator. The conclusion was wrong and the caution was right.

The committed JSON is **not** stale. Regenerating and comparing the parsed documents:

```
deep-equal ignoring key order: True
schemas only-before: []   schemas only-after: []
paths   only-before: []   paths   only-after: []
77 paths, 145 schemas, both sides
```

Every line of that diff is key **ordering**. The cause, in `merge()`:

```python
for ref_name in referenced - copied:      # a set of str
    copied.add(ref_name)
    copy_in(ref_name, rename.get(ref_name, ref_name))
```

`referenced` is a `set[str]`, and set-of-str iteration order depends on `PYTHONHASHSEED`, which
Python randomises **per process**. That loop decides the insertion order of
`components.schemas`. So two runs of the generator, on identical inputs, in the same checkout,
disagree — I measured 220 changed lines on the first run and 265 on the second. A generator whose
output depends on the process it ran in is a generator nobody can use, which is exactly what
happened: it was quarantined and edits went in by hand.

Fixed with `sorted(...)` and a comment saying why. Three consecutive processes now produce
byte-identical output (`md5 47f4e159…` ×3). Regenerated `contracts/openapi.v1.json` once and
`desktop/src/renderer/api/schema.d.ts` from it (`pnpm run gen:api`), and committed both: the diff
is 289/289 in the JSON and 303/303 in the `.d.ts`, all ordering, with typecheck and 1110 unit tests
green over the regenerated types. **`dev/build_contract.py` is safe to run again.**

### (e) VM's unused `overrides` / `extras` server plumbing — kept

`tests/test_viewspec_overrides.py` **38 passed**. There is no client: the only `overrides` in
`src/renderer` are the unrelated `allow_unsafe_overrides` setting. Kept, deliberately — it is
additive, declared in the contract, exercised by the mock-server contract test and covered by those
38 tests, and `_extra_layers` reusing the *existing* layer builders (VM §4.1) is the property that
keeps an extra from drifting into a second description of the same file. Carried to ROADMAP as a
follow-up with the deletion cost stated: five lines, and that test file says what would be lost.

### (f) The mid-flight typecheck reds — all fixed at HEAD

Confirmed by running them, not by reading commits:

* `pnpm run typecheck` — **clean**, both projects (`AnalyzerPage`/`JobRows` prop mismatch gone).
* `npx eslint src tests` — **0 errors**, 3 warnings, all pre-existing `react-hooks/incompatible-library`
  on `ui/DataTable.tsx`, `ui/VirtualList.tsx`, `pages/preprocess/index.tsx`.
* `tests/unit/pipeline-graph.test.ts` and `tests/unit/viewer-page.test.ts` (TI's
  `ReferenceError: beforeEach is not defined`, the concurrent lane's uncommitted WIP) both pass —
  1110 passed, 2 skipped, 92 files.

### (g) The pipeline's real leg, run to completion — and what it found

The sim→analyzer group from PL's real test (`06652701b38748fc`) finished while this lane ran. **The
ordering claim is proved and the run is red for an unrelated reason**, and both halves matter:

| job | kind | state | started | finished |
|---|---|---|---|---|
| `985616e0` | sim | **succeeded** (exit 0) | 21:36:54 | 22:00:52 |
| `8048c8c9` | analyzer | **failed** (exit 1) | **22:00:53** | 22:00:58 |

The `after` edge held exactly as designed: the analyzer sat queued for 24 minutes and was released
one second after the sim finished. Nothing client-side sequenced it.

The analyzer then failed on `FileNotFoundError: Mesh field file not found:
…/Simulations/pc-real-99628/TI/mesh/pc-real-99628_TI.msh` — **the very path the sim declared as its
own artifact**. The sim's log shows SimNIBS writing that mesh and warping fields out of it. Yet the
directory now holds only `fsaverage/`, on the host as well as in the container:

```
$ ls /Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/Simulations/pc-real-99628/
fsaverage/          # and nothing else — no TI/, no high_Frequency/
```

There is no cleanup step in `tit/sim/` (no `rmtree`, no `unlink`) and none in the job log. This is
the **docker phantom-write on this bind mount** already recorded against the mTI optimization
program, not anything this afternoon changed: files SimNIBS reports writing to `/mnt/000` are not
there afterwards, while `fsaverage/` — written last, by a different code path — survived. Recorded
as an open item, with the evidence, rather than absorbed into a lane's gate as a pass or a fail:
it is an environment defect and it will silently invalidate any real pipeline gate until it is
understood.

One thing worth fixing regardless, and separable from the mystery: a job reported `succeeded` with
an `artifacts` entry for a file that is not on disk. `emit_artifact`'s contract is "an output file
exists now"; nothing verifies it. A dependant is then handed a path that does not resolve.

### (h) Leftovers

| grep | verdict |
|---|---|
| `scene-orientation` | gone |
| `receipt=` | gone |
| `useRunStatusCells` | gone |
| `subject's L` | gone |
| `Load more` | gone from the app; `jobs.spec.ts` asserts its absence; **`pages/jobs/PARITY.md` still listed it as the shipped design** — fixed |
| `Quick add` / `Add job for each` | never built; `analyzer.spec.ts` asserts `Quick add` is absent, and the real gesture is the row's own **Duplicate**. **`docs/ARCHITECTURE.md` §7.5 still described both as existing** — fixed, with a note that they were specified and then not built |

### (i) Carried in mid-lane: `controls-consistency.spec.ts`

`SUBJECT_FIELD_PAGES` still listed `optimizer`, which lost its page-level `SubjectsField` to OJ's
jobs table. Among the run pages only **Pre-processing** keeps the subject disclosure (the optional
Source panel is the other page with one). `JOBS_CONTAINER` also lacked the Optimizer's own
`opt-jobs-table-container`.

Fixing the list exposed a second, sharper thing. The "the first control comes first" assertion finds
`the first .form-section not containing the control` and compares document positions — and on the
Optimizer there is no such section, because OJ dissolved all four global sections into the row. The
expression threw `compareDocumentPosition: parameter 1 is not of type 'Node'`. A single-section page
has nothing to order against, so the spec now reports `subjectsFirst: null` and asserts *that*,
rather than quietly passing an ordering claim it cannot make.

---

## 2. Records landed

| Where | What |
|---|---|
| `docs/DECISIONS.md` | Six entries: the host-managed Tetravox install (and why the Docker bake is rejected); the Subjects node and readiness-gated wires; a jobs table on all three run pages; two-sheet transparency and `.annot` colours; the terminal never auto-pinning a finished job; the Viewer list *is* the scene |
| `docs/ARCHITECTURE.md` §7.1 | Amended for the managed install. Its "no bundled copy, no version pin, no update channel" clause was written before that install existed and **contradicted it**; the amendment keeps "no pin *of ours*" (the publisher's `latest*.yml` digest is the authority), adds the `codesign`-before-unquarantine order, next-launch activation, and the rule that a version is never asserted by launching another application. Also: `POST /api/view/open` opens an explicit, user-edited file list, and layer appearance is Tetravox's |
| `docs/ARCHITECTURE.md` §7.5 | Extended to the Optimizer — all three run pages — with the per-kind-submission and muted-`—` clauses. Corrected the `Add job for each` / `Quick add` claim |
| `docs/ARCHITECTURE.md` §7.3 | Already carried the readiness table (`3a`) from PL; left as written |
| `desktop/DESIGN.md` | §4.10 three pages and the **two-line row grammar** (line 1 scannable columns, line 2 per-row prose, a dialog for anything richer); §4.6 the Jobs Raw log as the shared console; §9.1 the Subjects node and the readiness refusal; §10 was already VM2's and left alone |
| `docs/ROADMAP.md` | Five lane rows (TR, PL, TI, VM/VM2, OJ), this gate's row, and seven follow-ups |
| `tracks/active/v3-electron-gui.md` | ADR **row 28** — extends row 27 and supersedes its "no bundled copy, no version pin" clause |
| `desktop/src/renderer/pages/jobs/PARITY.md` | The stale "Load more" row |

**ROADMAP follow-ups carried:** one job group per kind on the Optimizer; a shared
`useTableColumns` hook (two column resolvers, one algorithm); a shared `roiLabel`; the per-point
`radiusPx`/opacity/marker work the parked embed would have supplied, now this renderer's to build;
the `overrides` plumbing with its deletion cost; `FlexConfig.output_folder` vs `run_name`; and the
pipeline's `sim` node not yet being the Simulator's jobs table.

---

## 3. Gate

GATE_TABLE_PLACEHOLDER

---

## 4. Open items

**Closed by this lane** — (a) the dead-space allowance and its reason, (b) the two Optimizer
specs, (d) the contract generator's non-determinism, (h) and (i) the leftovers.

**New, and the one that matters**

1. **A `sim` job reported `succeeded` with an artifact that is not on disk** (§1g). `emit_artifact`'s
   documented contract is "an output file exists now" and nothing checks it, so a dependant is
   handed a path that does not resolve and fails five seconds later with a `FileNotFoundError`
   naming its producer's own declared output. A one-line `Path(path).exists()` at emit time would
   turn a confusing downstream failure into an honest upstream one. Separable from item 2 and worth
   doing regardless of it.
2. **The bind-mount phantom write, on Dataset 000** (§1g). SimNIBS logs writing
   `Simulations/pc-real-99628/TI/mesh/*.msh` and the whole `TI/` and `high_Frequency/` trees are
   absent afterwards, on the host as well as in the container, while `fsaverage/` — written last —
   survived. There is no `rmtree`/`unlink` in `tit/sim/` and nothing in the job log. Already known
   against the mTI optimization program. **Until this is understood, no real pipeline or simulation
   gate on this machine can distinguish "our bug" from "the mount", which is a bad position to run
   a release from.**
3. **The real viewer-open check is still a shell command in a note, not a spec** (CX3 item 10,
   unchanged). `tests/e2e/real/viewer-open.spec.ts` — post, read the host file, validate against
   `contracts/tetravox-viewspec-v2.schema.json`, assert the spawn *argv* without launching — is a
   direct transcription of what is run by hand each round.
4. **`VITE_SCENE_HOOKS=1` decides whether the real scene specs can run at all** (CX3 item 11), and
   this round proved the footgun is live: a neighbouring lane's plain `pnpm run build` overwrote
   `out/` mid-gate and `controls-consistency.spec.ts`'s gallery cases failed on a missing
   "Design gallery" heading — a failure that says nothing about the gallery. Asserting the hook in a
   `beforeAll` would name the cause immediately. Re-running `pree2e` immediately before Playwright is
   today's workaround and it is not one a person should have to remember.
5. **One lane per worktree, or disjoint `git add` paths** (CX3 item 9, re-observed). Four commits
   landed in this worktree while this lane's gate was running, one of them after the full e2e run
   had started. Content is correct; the gate had to be re-derived around them.

**Carried unchanged from CX3 §4**: job re-adoption across a `--reload` (1); browser-mode download
not e2e-proved (2); `/api/scene/*` live and called by nothing (3); the guide still packaging ~11.3 MB
of GIfTI copies VX no longer needs (4); the pane forgetting its opacity across a page switch (5);
`pages/viewer/PARITY.md` still written against the embed (6, and now three lanes deep — VM and VM2
both left it alone and several of its rows are now deliberately *never* closing, because layer
appearance belongs to Tetravox); `⌘⇧V` lost with the canvas it focused (7); no shared active slot
between the pair editor and the pane (8).

---

## 5. How to test this by hand

Start the app: `cd desktop && npm run dev`. Five things changed that a person can see.

1. **The jobs table, on all three run pages.** Simulator, Optimizer, Analyzer.
   * Each row is **two lines**. Line 1 is the columns you compare rows by, never truncated; line 2
     is what only makes sense inside that row. Add two rows, give them different subjects, and check
     that changing one row's method or montage moves **no column** anywhere.
   * *Simulator:* switch a montage between **TI and mTI** — line 2 goes from two pairs to four, each
     with its own current, and line 1 does not move. Switch a row's Source to **Flex result**: the
     placement cell offers *Optimised* vs *Map to net*.
   * *Optimizer:* the Method cell offers **two** things a person chooses between — **Flex** and
     **Ex** — and the page *derives* which of the five job kinds it submits: the flex variants from
     whether the focality thresholds are derived or swept, and `ex` vs `mex` from the electrode
     count (4 = TI, 8 = mTI). Line 2 tells you which variant it derived. Pick `Ex` and watch the
     columns that mean nothing for it print a muted `—` — hover for the reason. Mix a flex row with
     an ex row and press Run: the page tells you it is **two** submissions, one per kind, rather
     than implying one atomic batch.
   * *Analyzer:* every row has its **own target**, opened from the row (click the target *text*, not
     the row). The global Target and Output sections are gone.
   * On every page: **Duplicate** a row — that is the "same job, another subject" gesture. There is
     no fan-out button. Adding a row opens **no dialog**. Run, and the table is still there.
2. **The pipeline's Subjects node.** Open the Pipeline page.
   * The cohort is a **node**, and it is the only place subjects are named. Drag
     `Subjects → Simulator` with a subject that has no head model (`102`, `test`): the wire is
     **refused, at the moment of the drag**, naming the subject and the reason — not a count, and
     not an hour later inside a container.
   * Now put a **Pre-processing** node between them. The same wire is accepted, because Pre produces
     the head model the Simulator requires.
3. **The Viewer.** Pick a source; the page lists **what will open**.
   * Remove a row — that file is not in the scene. Add one, from the catalogue or any project path.
     Reorder with drag or ↑/↓ — that is the layer order. **Reset** hands it back to the source.
   * There are no opacity/colormap/threshold controls, on purpose: those are Tetravox's, and having
     them in two places means the one you tuned is not the one that opened.
   * Press **Open in Tetravox**. The file written is real and yours —
     `<project>/code/ti-toolbox/viewer/*.tetravox.json` — and double-clicking it later opens the
     same scene with no app in the middle. Press Open again with a different field: the **same
     window** takes it.
4. **The managed install.** **Settings ▸ Viewer** on a machine with no Tetravox.
   * It says it found none and offers to install. Do it: the app downloads the publisher's own
     release, verifies the digest, and on macOS clears quarantine only after `codesign` passes.
   * The card then states **where** it is and **which version**. Install a newer one while a
     Tetravox window is open: it does not swap under you — it takes effect on the next launch.
   * Point the override at a nonsense path: **Open** is disabled and says why, rather than failing
     on click.
5. **Atlas selection in the native panes.** Optimizer or Analyzer, a cortical ROI type.
   * The pane has its own atlas selector (DK40 / HCP-MMP1 / a2009s). **Hover** a region: it lights
     up and is named above the canvas. **Click** it: it takes the ROI tint and joins the legend —
     and every region is in the colour its `.annot` colour table gives it, not one we invented.
   * Remove it **from the form**: it un-tints in the pane. Same selection from both ends.
   * The selection outline is a **thin edge**, not a border — no white shards on the folds.
   * Turn the skin down over the grey matter: the two translucent shells resolve in the right order
     (two depth sheets), rather than flickering by draw order.
6. **The terminal.** Open a run page that ran something earlier and finished.
   * It says **"No job running"** — it does not pin the finished job and show you a log that stopped
     changing. Start a run and it follows it live. On the **Jobs** page, the **Raw log** tab is the
     same console filling the pane: follow-tail, filter, level colours, Reveal — no "Load more".
