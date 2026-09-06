# Lane FIX-C — harness hygiene (fix round, 2026-09-04)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed,
staged, stashed or pushed. Container `ti-toolbox-fad740e5-tit-1` (`http://127.0.0.1:8765`, project
`/Users/idohaber/datasets/000`) — never restarted, never recreated. Every Electron/Playwright run
below went through `TIT_E2E_OFFSCREEN=1` and `scripts/e2e-quiet-check.sh`; every one reported
**PASS** — no window reached the maintainer's screen.

Owns: `desktop/tests/mock-server/**`, `desktop/tests/e2e/real/source.spec.ts`,
`dev/notes/v3-pipelines/RUNBOOK.md`, `desktop/src/renderer/pages/dev/**`,
`desktop/src/renderer/pages/_shared/run/useRunPaneController.ts`.

Environment note for the record: this pass shared the tree with (at least) lanes FIX-A and FIX-B,
both actively editing files at the same time (`fix-a-notes.md`, `fix-b-notes.md` alongside this
file; `tests/e2e/scene.spec.ts` and `out/renderer/**` visibly changed mid-run twice — see §1's
"environmental" note).

---

## Defect 1 — the default e2e suite leaks job state across spec files

### Reproduction, before the fix (numbers from the critic's own pass, reproduced fresh here)

Isolated `layout.spec.ts` (mock server, `--project=default`, fresh build): 1280×800 light dead
space **36.3 / 34.4 / 39.6 / 41.0 %** (preprocess/simulator/optimizer/analyzer) — 6/6 tests pass.

Full default suite, one `npx playwright test` invocation, same spec, same assertions: the critic
measured **46.1 / 45.2 / 56.0 / 54.9 %** (all four over the 45 % L5a limit, optimizer by 11.0 pp) —
root cause traced (critic-notes.md §5a) to `RunPaneTabs`'s right pane forced to the Terminal tab by
a leftover `analyzer`/`ernie` job, `queued`, left alive by an earlier spec file in the same
`webServer`-managed mock-server process the whole invocation shares (`playwright.config.ts`,
`workers: 1`). Lane SUB independently hit the same class as a spurious `1 wait` clause in
`optimizer.spec.ts` (`sub-notes.md` §6 item 8) and a whole-suite quiet-check failure from
`scene.spec.ts` (item 7).

### Cause, and why the obvious fix (a wait-duration watchdog) is not enough on its own

`tests/mock-server/server.mjs`'s `isReady(job)` enforces "at most one `running` job per
(kind, subject)" for **every** kind, not only the heavy ones — a job an earlier spec file created
and never itself drove to a terminal state (no assertion awaited it, nothing cancelled it) keeps
that exclusivity slot for every later spec file too, for as long as the one shared server process
lives.

First fix attempt: a bounded wait — `tick()` cancels any `queued` job once it has waited longer than
`QUEUE_WATCHDOG_MS` (90 000, derived from `planPreprocessingStages`'s deepest legitimate DAG chain,
G1→G4→G5→G6→report, 5 levels × `runTimeline`'s ~10 100 ms worst case ≈ 50 500 ms, so 90 s clears it
with ~40 s of margin). Re-ran the full suite with only this in place: **still failed** —
`layout.spec.ts`'s own `error-context.md` this time showed the blocking job (`analyzer`, `ernie`)
as `running`, **3 seconds old**. A duration watchdog cannot distinguish "abandoned by a file that
already moved on" from "legitimately 3 seconds into a `runTimeline` that takes up to 10.1 s" —
by definition nothing is stale yet. Kept as defense-in-depth (a genuinely stuck job, from any
future bug, still gets reclaimed within 90 s) but it cannot be the whole fix.

### The fix

Two parts:

1. **`tests/mock-server/server.mjs`**: `POST /api/__mock/reset` — cancels-and-forgets every
   non-terminal job (clears `jobRegistry`, job WS subscriptions, `groupParallelLimit`), reports
   `{jobs_cleared}`. Deliberately not in `contracts/openapi.v1.yaml`: it has no counterpart on
   `tit.server` and exists only for the e2e harness. Plus `QUEUE_WATCHDOG_MS` above (§ "Cause").
2. **`tests/e2e/_helpers.ts::launchElectronApp`** (outside this lane's listed ownership — see
   "Cross-lane touch" below): calls a new local `resetMockJobs()` before every launch. Gated
   **twice** for safety: `process.env.TIT_E2E_TOKEN === "mock-token"` (playwright.config.ts's own
   default, which fires only when nothing set a real token — a `--project=real` run against the
   live container always sets a real one first, so this is always false there and no request is
   ever sent toward the container the maintainer is using), and the fetch itself is best-effort
   (2 s `AbortSignal.timeout`, errors swallowed) since the very next thing every spec does is wait
   on the app itself, which fails loudly on its own if the mock is not up.

**Cross-lane touch, flagged explicitly.** `tests/e2e/_helpers.ts` is not in this lane's file list.
Empirical proof above shows a duration-only, mock-server-only fix cannot close the actual measured
gap (a 3-second-old job is not "stale" by any definition), so a per-file boundary call is the only
mechanism that does — exactly the "a reset the fixture calls" option the defect names as preferred.
The edit is additive (one new local function, one call site inside the existing
`launchElectronApp`), and the safety analysis above (double-gated, best-effort, and `server.mjs`
never backs a real run so the endpoint cannot exist there to be hit) is why it was judged safe to
make rather than deferred as a note. Recorded here for visibility rather than silently done.

### Tests (fail-red-first, both proven — `tests/mock-server/server.test.ts`)

- **Watchdog**: own server instance, `TIT_MOCK_QUEUE_WATCHDOG_MS=200`. Job A (analyzer/ernie)
  starts running immediately; job B (same kind+subject) queues behind it (no `__mock_fast`, so A's
  natural runtime is 6-10 s — A is still legitimately running when B's 200 ms watchdog fires).
  Asserts B reaches `cancelled` while A stays `running`, and B's own event log carries a
  `mock.watchdog` line. **Before the fix** (condition disabled): `expected 'queued' to be
  'cancelled'` — B waits forever. **After**: green.
- **Reset endpoint**: submits two jobs (one running, one queued behind it — the exact leftover
  shape critic measured), calls `POST /api/__mock/reset`, asserts `{jobs_cleared: 2}`, both job ids
  now 404, `GET /api/jobs` empty; a second call reports `{jobs_cleared: 0}` (idempotent); an
  unauthenticated call is 401. **Before the fix** (route renamed to disable it): `expected 404 to
  be 200`. **After**: green.
- `npx vitest run tests/mock-server/` (`server.test.ts` + `contract.test.ts`) — **26 passed, 0
  failed** (16 pre-existing `server.test.ts` cases + 2 watchdog + 3 reset + 5 `contract.test.ts`).

### Proof (the numbers the task asked for)

| Run | preprocess | simulator | optimizer | analyzer | result |
|---|---|---|---|---|---|
| `layout.spec.ts` isolated (baseline) | 36.3 % | 34.4 % | 39.6 % | 41.0 % | 6/6 pass |
| Full default suite, run 1 | 36.3 % | 34.4 % | 39.6 % | 41.0 % | 6/6 pass, identical |
| Full default suite, run 2 | 36.3 % | 34.4 % | 39.6 % | 41.0 % | 6/6 pass, identical |

(All at 1280×800 light; dark and 1440×900 matched too — see raw logs.) `optimizer.spec.ts`: **7/7
pass** in both full-suite runs, including "Flex: one shared ROI picker, a plan, and a flex job on
the wire" (SUB's own regression) with no spurious wait clause.

Full-suite totals: run 1 **127 passed / 2 failed** (both `scene.spec.ts`, "Design gallery heading
not found" — `out/renderer`'s asset hash changed mid-run, `ls -la` timestamp inside the 8.2 m
window; not this defect, a concurrent lane's build landing on top of mine, exactly the race
`RUNBOOK.md` already warns about). Run 2, rebuilt fresh immediately before: **129 passed / 0
failed / 1 skipped** (the 1 skip is `viewer-real.spec.ts`'s conditional real-embed test,
unconditional to this pass), quiet-check **PASS**, exit 0, 8.0 m. For comparison, the critic's own
pre-fix whole-suite run: **111 passed / 1 failed** with the OLD numbers (46.1/45.2/56.0/54.9 %).

State left behind: none. Mock server is a fresh process per invocation; no jobs persist past it by
construction now.

---

## Defect 2 — `real/source.spec.ts`'s budget and teardown race

### Reproduction, before the fix

The documented (and, before this pass, actual) budget: `waitForJobTerminal(..., timeoutMs:
600_000)` inside a `test.setTimeout(700_000)`. Measured completions on this container, all real,
all cited with their own source: lane LAY's run **9.5 m** (570 000 ms, `critic-notes.md` §7 /
`lay-notes.md` §7); the critic's own run **9.7 m** (582 000 ms, `critic-notes.md` §2b) — both
*inside* 600 000 ms but with under 30 s of margin; lane SUB's own run **exceeded** 600 000 ms
outright (`sub-notes.md` §6 item 5: "the forward-solution job … did not reach a terminal state
within the spec's 600 000 ms. I cancelled it from the API … so it would not hold the one-FEM
slot"). Three independent runs cluster right at or past the documented budget — not a one-off.

Fresh measurement, this pass, this container, sub-101, `GET /api/jobs` clean (0 running/queued)
before starting: job `a9784875fe9144af` reached `succeeded` in **571.0 s** (9.5 min; whole test,
UI steps included: 9.7 m / 582 s wall — matches the critic's own 9.7m almost exactly). This ran
*before* the teardown fix existed only in the sense that the run that measured it also carries the
fix (both changes landed together and were verified in the same real run — there was no separate
"budget-only" real run, since the teardown race only manifests on the timeout path and this run did
not take that path). `tests/e2e/real/source.spec.ts::JOB_TIMEOUT_MS` set to `900_000` (15 min,
~58% / 329 s margin over 571.0 s) from this measurement; `TEST_TIMEOUT_MS = JOB_TIMEOUT_MS +
60_000` for the UI steps around the job wait.

### The teardown race

`afterAll` ran `rmSync(FORWARD_DIR, ...)` unconditionally. On the timeout path (`waitForJobTerminal`
throws when the budget is too tight, exactly what happened to lane SUB), the test fails but
`afterAll` still runs — at that moment the real `tit.source` subprocess on the container is, by
definition of "timed out", still running and still writing into `FORWARD_DIR`. `rmSync` racing
that write is the "afterAll deletes the output directory while the job is still writing" the task
named.

### The fix

`ensureJobStopped(jobId)`: one `GET /api/jobs/<id>`; if already terminal, done. If not, `POST
/api/jobs/<id>/cancel` then `waitForJobTerminal(..., timeoutMs: 60_000)` for the cancel to actually
land (state `cancelled`, not merely the POST returning 200) before `afterAll` touches the
filesystem at all. The job id is lifted to a module-level `let jobId` (set the moment the job is
created, inside the test body) since `afterAll` runs in a separate closure and cannot see a `const`
local to `test(...)`.

### Proof

Real container, sub-101, `FORWARD_DIR` absent beforehand (precondition asserted in `beforeAll`):

| | Before | After |
|---|---|---|
| Budget | job exceeds 600 000 ms on this container (SUB's own run); 570-582 s margin-free even when it does not | 900 000 ms, 329 s (~58 %) margin over the fresh 571.0 s measurement |
| Timeout-path teardown | `rmSync` races a still-writing subprocess | `ensureJobStopped` cancels-and-confirms first |
| **Full real run** (this pass) | — | **1 passed (9.7m)**, job `a9784875fe9144af` `succeeded` in 571.0s, `FORWARD_DIR` created then cleaned up by `afterAll`, quiet-check **PASS**, exit 0 |
| **Cancel-branch check** (this pass, isolated — see below) | — | job `03b313c8954e4eee` submitted with the spec's real payload, cancelled ~2s later: `state: "cancelled"`, `exit_code: -15`, `finished_at` set within the 2s poll — the exact HTTP calls `ensureJobStopped` makes, proven live |

The full real run above took the success path (the job finished before its own budget, so
`ensureJobStopped` found it already terminal on the first `GET` and never needed to cancel
anything) — proving the raised budget, not the cancel branch. The cancel branch is the one that
matters on the *old* 600s-timeout failure mode (SUB's run), which this fix's whole point is to make
unreachable; re-running the same scenario for real would mean deliberately waiting past 900 000 ms,
so instead the cancel branch's own two HTTP calls (`POST /api/jobs/<id>/cancel` then poll) were
verified directly against this container with the spec's real job payload (`kind: "source",
subject_ids: ["101"], config: {mode: "forward", forward: {eeg_net: "EEG10-10_UI_Jurak_2007"}}`):
submitted, state `running` after 2s, cancelled, reached `cancelled` (not merely a 200 on the POST)
within the same 2s poll window `ensureJobStopped` itself uses. `FORWARD_DIR` never appeared (a
cancel this close to submission has nothing written yet), confirmed absent both times.

`GET /api/jobs` clean (0 running/queued) after both; `GET /api/health` answered `{"status":"ok"}`
after both; container never restarted or recreated.

---

## Defect 3 — RUNBOOK Level B's build command is incomplete for the scene specs

### Reproduction, before the fix

Literal RUNBOOK command (`npm run build`, plain) against the three real scene specs: **critic
already measured** 24/27 passed, 3 failed (one per scene spec file), 10 skipped
(`critic-notes.md` §2a-2c) — `window.__scenePane is absent — build out/ with
VITE_INCLUDE_GALLERY=1`. `SCENE_DEBUG = import.meta.env.DEV || import.meta.env.VITE_INCLUDE_GALLERY
=== "1"` lives in `src/renderer/scene/SceneCanvas.tsx` (lane SCB's file) and gates both
`window.__scene` and (via `ScenePane.tsx`, lane SCC's file) `window.__scenePane`. Neither file is
in this lane's ownership, so the preferred fix (a dedicated `VITE_E2E_HOOKS` flag independent of
the design gallery) is left as an exact request rather than done here (§ "Open issues").

### The fix taken: document the flag, verified against the real container

`dev/notes/v3-pipelines/RUNBOOK.md`'s Level B section now has an explicit scene-specs subsection:
build with `VITE_INCLUDE_GALLERY=1 npx electron-vite build` first, run the three `scene-*.spec.ts`
files, then `npm run build` (plain) again before leaving `out/` for anyone else or for the
container. Re-verified live here (not just cited from the critic): container
`ti-toolbox-fad740e5-tit-1`, `GET /api/jobs` clean before, real token —

```
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
  tests/e2e/real/scene-simulator.spec.ts tests/e2e/real/scene-optimizer.spec.ts tests/e2e/real/scene-analyzer.spec.ts
```

**13/13 passed (19.2s), quiet-check PASS.** `GET /api/jobs` clean after; container untouched
otherwise.

---

## Defect 4 — the design gallery ships inside plain production builds

### Reproduction, before the fix (re-verified fresh, not just cited)

Plain `npm run build`, then `grep` the built `out/renderer/assets/*.js`: **"Design gallery"**,
**"Every primitive"** and **"Mount scene"** all present, in the one main chunk
(`index-DPA8bq_Y.js`, **1,386,127 bytes**) — confirms SCB's finding still holds on today's code, not
a stale claim. `desktop/README.md`'s own claim ("a plain build tree-shakes the page and its nav
entry out entirely") was false: `pages/dev/index.tsx` statically imported `Gallery`/`DensityGallery`
at the top of the file, and `Component: DesignGallery` captured that reference on the exported
`PageDef` object regardless of the `enabled` boolean's value — Rollup can never prove a *reference
that is always assigned* unreachable, only a branch that never executes.

### The fix

`pages/dev/index.tsx`: the same `includeGallery` boolean now gates a **dynamic** `import()` inside
a ternary, not a static top-level import — `includeGallery ? lazy(() => import(...)) : null`.
`import.meta.env.DEV` / `import.meta.env.VITE_INCLUDE_GALLERY` fold to literals during each
module's transform (before Rollup ever sees the file), so on a plain build the whole ternary folds
to the `null` branch and the dynamic import is never even an edge in the module graph — proven by
grepping the *output*, not by trusting the mechanism. A `<Suspense>` was added locally around the
lazy component: `App.tsx` renders every `page.Component` with no ambient `<Suspense>` boundary
(only `PageErrorBoundary`, which catches thrown errors, not a suspended lazy import), and wrapping
it here — rather than in `App.tsx`, which this lane does not own — keeps the whole fix inside
`pages/dev/**`.

### Proof

| | Before | After |
|---|---|---|
| "Design gallery" / "Every primitive" / "Mount scene" in `out/renderer` (plain build) | present | **absent** (only survivor: this file's own `purpose` metadata string, unavoidable — `registry.ts` eager-imports every page's `PageDef` to build the nav) |
| Main chunk size (plain build) | 1,386,127 bytes | **1,309,259 bytes** |
| `uplot` chunk (plain build) | 137.84 kB | **35.88 kB** |
| `gallery.spec.ts` against a `VITE_INCLUDE_GALLERY=1` build | (unaffected — needed to confirm the `Suspense` addition didn't break the gallery route) | **2/2 passed (10.7s)**, quiet-check PASS |
| `scene.spec.ts` against the same build | (unaffected — `window.__scene` set inside the now-lazy tree) | **7/7 passed (38.1s)**, quiet-check PASS |
| `npm run typecheck` | — | clean |

Left `out/renderer` on a plain build afterward (confirmed via the same grep, 0 occurrences).

---

## Defect 5 — `useRunPaneController.ts`

**Not deleted.** Re-checked at the start and again just before writing this: still imported and
called by `pages/optimizer/index.tsx:143`, `pages/simulator/index.tsx:105` and
`pages/analyzer/AnalyzerPage.tsx:360` (via the barrel `pages/_shared/run/index.ts`), none of which
are in this lane's file list. Verified the underlying claim is true, not just cited: read
`ui/Layout.tsx`'s `usePaneController` directly — `attach` is a stable `useCallback`, and the
`ResizeObserver` reads `borderBoxSize[0].inlineSize` (the content box, same box
`getBoundingClientRect()` seeds `measured` from) — LAY's fix (§3.1 of `lay-notes.md`) is genuinely
in place, so the wrapper's own dedup workaround (`useRunPaneController.ts`'s whole reason for
existing) is dead weight, exactly as LAY's own request said. Deleting it here would break three
files this lane does not own with no correction in the same pass. Left as an open issue with the
exact request below rather than force-broken or silently skipped.

---

## Open issues / exact requests to other lanes

1. **Delete `desktop/src/renderer/pages/_shared/run/useRunPaneController.ts`** and its export in
   `desktop/src/renderer/pages/_shared/run/index.ts` (`export { useRunPaneController } from
   "./useRunPaneController";`) — swap all three call sites from `useRunPaneController("<page>")` to
   `usePaneController({ pageId: "<page>", name: "run" })`, imported from `../../ui/Layout` (these
   three pages sit one directory shallower than `pages/_shared/run/`, where the wrapper itself
   imports the same module as `../../../ui/Layout`): `pages/optimizer/index.tsx:143`,
   `pages/simulator/index.tsx:105`, `pages/analyzer/AnalyzerPage.tsx:360`. Owner: whoever next
   touches those three pages (lane LAY's own §8 item 3 already asked for this; repeating it here
   since this lane could not do it without editing files outside its list).
2. **Give the scene e2e hooks their own build flag**, independent of `VITE_INCLUDE_GALLERY` (e.g.
   `VITE_E2E_HOOKS`) — `SCENE_DEBUG` in `src/renderer/scene/SceneCanvas.tsx:67` and its use in
   `pages/_shared/scene/ScenePane.tsx:495`. Not done here: both files are outside this lane's
   ownership. The RUNBOOK documents the current single-flag reality in the meantime (§ Defect 3
   above), verified against the real container.

## Environment / hygiene notes

- Two build races were observed live during this pass (`out/renderer`'s asset hash changed mid
  invocation, both times during `scene.spec.ts`'s tail end of a ~8-9 min full-suite run) — matches
  `RUNBOOK.md`'s own existing warning about racing another lane's build. Not a defect in anything
  fixed here; noted because it explains defect 1's contaminated first attempt (§ Defect 1 numbers).
- A `scene.spec.ts` typecheck error appeared and then resolved itself between two `npm run
  typecheck` runs in this pass (another lane's concurrent edit, not this lane's file) — recorded so
  it is not mistaken for something this lane caused or needs to fix.
- Left `out/renderer` on a **plain** build at the end of this pass (verified: 0 occurrences of
  "Design gallery" / "Every primitive" / "Mount scene", `window.__scene` / `window.__scenePane`
  both absent).
