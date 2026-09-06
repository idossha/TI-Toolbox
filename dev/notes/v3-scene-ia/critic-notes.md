# Critic pass — v3 scene panes + subject grammar + layout (plan §S8, §2, §3, §4)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Read-only: nothing fixed, nothing committed, nothing pushed, nothing stashed. Container
`ti-toolbox-fad740e5-tit-1` (`http://127.0.0.1:8765`, project `/Users/idohaber/datasets/000`) —
never restarted, never recreated; the maintainer's own dev server on `127.0.0.1:5173` was never
touched. Every Electron/Playwright run below went through `TIT_E2E_OFFSCREEN=1` and
`desktop/scripts/e2e-quiet-check.sh`, and every one reported **PASS** — no window reached the
screen, no focus moved to a test binary.

## 0. Host + desktop gates (RUNBOOK, `dev/notes/v3-pipelines/RUNBOOK.md` + this program's convention)

| Gate | Command | Result |
|---|---|---|
| Host pytest | `python3 -m pytest -q` (repo root; smoke deselected by default) | **3462 passed, 30 skipped, 21 deselected, 38.61s** |
| `desktop` typecheck | `npm run typecheck` | clean, 0 errors |
| `desktop` lint | `npm run lint` | **0 errors**, 3 pre-existing warnings (React Compiler "incompatible library" notes on `react-hook-form`/`useReactTable`/`useVirtualizer`; unrelated to this pass) |
| `desktop` vitest | `npm test` | **836 passed (836)**, 68 test files, 4.04s |
| `desktop` build | `npm run build` (plain, per RUNBOOK Level B) | succeeded, 1.95s |

## 1. Level A — API smoke matrix (`dev/smoke.sh`)

```
dev/smoke.sh
```

**21 passed, 68 deselected, 253.09s (0:04:13).** All 21 rows green, 0 failed. Results table of
record: `tests/smoke/artifacts/results-20260904T085816Z-035402.md`; manifest
`tests/smoke/artifacts/manifest-20260904T085816Z-035402.json`. `find /Users/idohaber/datasets/000
-iname "*smoke*"` after the run: empty. `GET /api/jobs` clean (0 running/queued) before and after.

### Level A by kind

| kind | rows | behaviour | result |
|---|---|---|---|
| pre | 5 (pre_dicom, pre_charm, pre_fastsurfer, pre_tissue, pre_qsiprep, pre_report — 6 actually) | completed/started_then_cancel/refused | all green — pre_dicom 8.0s, pre_charm cancel 6.2s, pre_fastsurfer cancel 5.9s, pre_tissue 16.1s, pre_qsiprep refused 4.0s (no DWI), pre_report 2.0s |
| sim | 2 (sim_ti, sim_mti) | started_then_cancel | green — cancel in 0.0s both, banners at 2.0s/3.0s |
| flex | 1 | started_then_cancel | green — cancel 0.0s, banner 3.1s |
| leadfield | 1 | started_then_cancel | green — cancel 0.0s, banner 2.0s |
| ex | 1 | completed | green — 26.1s, 2 artifacts |
| mex | 1 | completed | green — 36.2s, 2 artifacts |
| analyzer | 2 (mesh, voxel) | completed | green — 2.0s each, 5/4 artifacts |
| source | 1 | started_then_cancel | green — cancel 0.0s, banner 4.1s |
| nifti_average | 1 | completed | green — 2.0s, 2 artifacts |
| stats | 1 | completed | green — 2.0s, 8 artifacts |
| nilearn | 1 | completed | green — 12.1s, 4 artifacts |
| blender | 1 | completed | green — 12.1s, 5 artifacts |
| tools | 1 | completed | green — 0.0s, 2 artifacts |
| project_init | 1 | completed | green — 0.0s, 0 artifacts |

**21/21 rows, 0 failed.** No open issue from Level A this pass (compare to critic-w2's prior pass,
which caught a real `pre_fastsurfer` root-user bug — that row is `started_then_cancel` in this
program's matrix, cancelled before FastSurfer's root check fires, so it is not exercised here).

## 2. Level B — real Playwright project (`desktop/tests/e2e/real/`), scene specs included

### 2a. Literal RUNBOOK command — build gap found

RUNBOOK's Level B section documents exactly:
```
cd desktop
npm run build
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/<spec>.spec.ts
```
Run here against the whole project (no spec path, 15 spec files / 27 tests):
```
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real --workers=1
```

**RUNBOOK GAP (finding):** `npm run build` (plain, exactly as documented) does **not** set
`VITE_INCLUDE_GALLERY=1`, so `SCENE_DEBUG = import.meta.env.DEV || import.meta.env.VITE_INCLUDE_GALLERY
=== "1"` (`desktop/src/renderer/scene/SceneCanvas.tsx:63`) is false in the built bundle, and
`window.__scene` / `window.__scenePane` never exist. All three real scene specs read those handles
and fail — two on their own explicit throw (`"window.__scenePane is absent — build out/ with
VITE_INCLUDE_GALLERY=1"`, `tests/e2e/real/scene-analyzer.spec.ts:47` /
`scene-optimizer.spec.ts`/`scene-simulator.spec.ts`), one (`scene-optimizer`) failing in 224 ms on
the first `paneState()` call, the other two timing out at 30 s waiting on a `waitForFunction` that
polls the same absent handle. This is exactly what lane SCC's own notes (§7, "State left behind")
flagged as a requirement for the critic — but the RUNBOOK's Level B section, which is what this
pass was told to follow literally, never mentions the flag. **Result with the literal command: 24/27
tests passed, 3 failed (one per scene spec file), 10 skipped (the remaining tests in those 3 files,
`describe.configure(mode:"serial")` stops after the first failure in each file).**

Quiet-check: **PASS** throughout (frontmost unchanged, no new window).

### 2b. Non-scene specs (12 files, 14 tests) — all green

| spec | job id | time | outcome |
|---|---|---|---|
| analyzer-mesh | `d5413132f1894bfc` | 9.7s | succeeded, 5 artifacts |
| analyzer-voxel | `b65dacb9b76148d9` | 9.1s | succeeded, 4 artifacts |
| cluster-permutation | `b68dad77d908487a` | 7.4s | succeeded, 8 artifacts |
| ex (subcortical ROI) | `6f370d00d09547fb` | 35.3s | succeeded, 2 artifacts |
| ex (second-subject plan) | — (plan-only) | 0.7s | passed |
| flex (DK40 bankssts) | `23573b55d0c54891` | 2.9s | started, cancelled |
| mex | `2f48e31a82fd40ff` | 44.0s | succeeded, 2 artifacts |
| nifti-group-average | `8d8c5e1a05014bfb` | 7.4s | succeeded, 2 artifacts |
| nilearn-visuals | `f34e7fdb71334e13` | 16.1s | succeeded, 4 artifacts |
| preprocess (tissue, sub-101) | `b99f779cb6594667` | 1.3m | succeeded, 1 artifact |
| preprocess (DICOM onboarding, sub-102) | `0347433e151a49c8` | 22.0s | succeeded, 1 artifact |
| sim-mti | (not logged by the spec) | 5.6s | started, cancelled — confirmed via `GET /api/jobs` mid-run |
| sim (TI) | `89f58f4504364eb0` | 5.1s | started, cancelled — confirmed via `GET /api/jobs` mid-run |
| source (forward solution, sub-101) | `6f4bc3c393d243ce` | 9.5m | succeeded, 3 artifacts |

**Overall (RUNBOOK-literal plain build): 14 passed, 3 failed, 10 skipped, 27 total, 15.8m wall.**
Quiet-check: no new Electron/Chromium window reached the screen throughout (1395 samples over the
whole 15.8m run); the script's own exit code is 1 only because the *test command* exited 1 (3
real test failures) — the window/focus check itself is clean. `forward/` for sub-101 was removed
by the spec's own `afterAll` (verified gone); no `*cr-levelb*`-tagged path left anywhere under the
project; `GET /api/jobs` clean after.

### 2c. Scene specs against the plain build (RUNBOOK-literal)

| spec | result | failure mode |
|---|---|---|
| scene-analyzer.spec.ts | **1 failed / 3 skipped** | 30.0s timeout in `waitForFunction` polling `window.__scenePane` |
| scene-optimizer.spec.ts | **1 failed / 4 skipped** | 224ms — immediate throw, `paneState()`'s own guard |
| scene-simulator.spec.ts | **1 failed / 3 skipped** | 30.2s timeout, same as scene-analyzer |

## 3. Scene budgets (plan §S8, §2, §3) — measured live against the container

### 3a. Manifest triangle/vertex/byte counts vs S3 budget (≤150k triangles, ≤3MB/surface)

| subject | part | triangles | vertices | bytes | within_budget | max_deviation_mm |
|---|---|---|---|---|---|---|
| ernie | skin | 77,032 | 38,952 | 1,391,840 (1.33 MiB) | **true** | 0.0 |
| ernie | gm | 145,402 | 70,586 | 2,591,888 (2.47 MiB) | **true** | 5.266 |
| 101 | skin | 69,818 | 35,135 | 1,259,468 (1.20 MiB) | **true** | 0.0 |
| 101 | gm | 147,193 | 70,961 | 2,617,880 (2.50 MiB) | **true** | 6.245 |
| MNI152 | skin | 80,380 | 40,503 | 1,450,628 (1.38 MiB) | **true** | 0.0 |
| MNI152 | gm | 138,239 | 66,648 | 2,458,676 (2.34 MiB) | **true** | 4.149 |

All 6 surfaces (3 subjects × 2 parts) within budget. `cache.built_ms` reported by the manifest at
measurement time: ernie 2486.6ms, 101 2231.8ms, MNI152 1275.2ms (these are the last-build costs
recorded on the cached manifest, not a fresh cold measurement — see §3c for a live cold run).

### 3b. Warm HTTP timings — `/api/scene/manifest` and both surfaces, 3 runs each

| Request | ernie | 101 | MNI152 |
|---|---|---|---|
| `manifest` (warm) | 82/49/50 ms | 70/49/49 ms | 72/49/49 ms |
| `surface?part=skin` (warm) | 15/11/10 ms | 14/11/10 ms | 13/11/12 ms |
| `surface?part=gm` (warm) | 22/17/15 ms | 16/15/14 ms | 17/17/14 ms |

All well inside S8's 2.5s warm-first-paint budget (the sum of manifest+gm warm is at most ~100ms).

### 3c. Cold path, live (sub-101 `skin`+`gm` cache deleted, then measured)

```
rm derivatives/ti-toolbox/scene_cache/sub-101/{skin,gm}.*.{tvsc,json}
GET /api/scene/manifest?subject=101
```
First call: **202 in 117ms**, `cache.state:"building"`. Polled at 0.3s cadence: **200 (ready)
after 2.81s wall** (7 polls) — well inside S8's 12s cold budget. `surface?part=skin` and
`part=gm` immediately after (now warm, built as part of the manifest build): **13ms** / **19ms**.
Cache rebuilt to the **identical fingerprint** `f9d8470556f60e1c` sub-101 had before — verified,
so this leaves the container exactly as found.

### 3d. Scene spec results — re-run against a `VITE_INCLUDE_GALLERY=1` build (§7 issue 1)

```
VITE_INCLUDE_GALLERY=1 npx electron-vite build
TIT_E2E_SERVER_URL=... TIT_E2E_TOKEN=$TOK TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=real \
  tests/e2e/real/scene-simulator.spec.ts tests/e2e/real/scene-optimizer.spec.ts tests/e2e/real/scene-analyzer.spec.ts
```
**13/13 passed (19.5s), quiet-check PASS.** S8 numbers exactly as the specs' own `console.log`
lines report them:

| spec | triangles | markers/regions | firstPaintMs (fresh mount) | firstPaintMs (warm/revisit) | fps orbiting | firstScreen |
|---|---|---|---|---|---|---|
| scene-analyzer (ernie, inspect) | gm 145,402 + skin 77,032 | 68 markers | 258 | 19 | **121.2** | 28/28 |
| scene-optimizer (ernie, target, DK40) | 222,434 (gm+skin) | 70 regions | 175 | 2 (degrade case, no head model) | — | 26/26 |
| scene-simulator (ernie, montage) | 222,434 (gm+skin) | 18 markers | 167 | 5 | **121.0** | 13/13 |

All firstPaintMs values (19-258ms fresh, 2-19ms warm) are far under S8's 2500ms warm budget; both
fps numbers (121.0, 121.2) are far over the 30fps floor (display-refresh-capped, as lane SCB also
found); `firstScreen` shows 0 hidden Tier-1 controls on all three pages, satisfying S8's "never
pushes Run or the plan off the first screen." A cold atlas switch (ernie, HCP_MMP1, 362 regions,
left uncached by lane SCC specifically for this pass) built in **173ms** — also far under the 12s
cold budget.

**S3/S8 verdict: every budget number in plan §2/§3/§S8 measured this pass is met**, on all three
subjects for the surface budgets and on the three real scene specs for first-paint/fps/first-screen.

## 4. Section-4 layout numbers (LAY's own gate, re-run) — `tests/e2e/layout.spec.ts`

```
TIT_E2E_OFFSCREEN=1 bash scripts/e2e-quiet-check.sh \
  npx playwright test --project=default tests/e2e/layout.spec.ts
```
(mock server, `--project=default`, no `TIT_E2E_SERVER_URL` — this spec never touches the live
container.)

**6 passed (17.7s), quiet-check PASS.**

| page | dead space 1280×800 (light/dark) | dead space 1440×900 (light/dark) | Tier-1 on first screen | obstructed under action bar |
|---|---|---|---|---|
| preprocess | 36.3% / 36.3% | 42.0% / 42.0% | 21/21 | 0 |
| simulator | **32.6% / 34.4%** | 38.3% / 38.3% | 16/16 | 0 |
| optimizer | 41.6% / 41.6% | 42.8% / 42.8% | 18/18 | 0 |
| analyzer | 40.8% / 40.8% | 43.5% / 43.5% | 28/28 | 0 |

L5a limit 45%: **all 16 numbers pass** (max observed 43.5%, Analyzer at 1440×900). L5b (0 Tier-1
controls below the fold): **0 in all cases**. L4 (0 controls under the action bar at any scroll
offset): **0 of 176-219 controls per page over 5-7 scroll steps** — confirmed clean, matching LAY's
claim. L5c (0px horizontal scroll): confirmed 0. The fill-controller settle test and the
panel-pages-reachable test both passed too.

**One discrepancy from LAY's own notes:** LAY's headline table states dead space is "identical in
light and dark (the layout is theme-independent; both were measured, not assumed)" and reports a
single Simulator number (34.4%) for 1280×800. This re-run's own light-mode measurement is
**32.6%**, not 34.4% — the 34.4% value is the **dark**-mode number. Simulator at 1280×800 is the
only one of the 16 light/dark pairs that actually differs (1.8 points); all 15 others are exactly
identical between themes, matching the claim. Both numbers are under the 45% budget regardless, so
this does not change the gate's pass/fail — it is a documentation-accuracy note, not a budget miss.

## 5. Default e2e suite (`npm run e2e:quiet`, per `desktop/package.json`)

```
npm run e2e:quiet    # = bash scripts/e2e-quiet-check.sh npm run e2e
                      # pree2e rebuilds with VITE_INCLUDE_GALLERY=1, then `playwright test`
                      # (project=default, mock server, tests/e2e/real/** excluded)
```

**118 tests, 111 passed, 1 failed, 1 skipped, 5 did not run, 7.2m wall.** Quiet-check: no new
Electron/Chromium window reached the screen (623 samples) — the script's exit 1 is entirely the
one real test failure below, not a window/focus leak. The 1 pre-existing skip is
`viewer-real.spec.ts`'s real-Tetravox-embed test (conditional, unrelated to this pass).

### 5a. Finding — `layout.spec.ts` passes in isolation, fails inside the full suite

Re-running `layout.spec.ts` **alone** (§4 above) reproduces LAY's numbers exactly and passes 6/6.
Running it as **part of the full default suite** — same file, same assertions, same 45% budget —
its first test fails on **all four run pages** at light 1280×800:

| page | isolated (§4) | inside full suite | budget | over by |
|---|---|---|---|---|
| preprocess | 36.3% | **46.1%** | 45% | +1.1pp |
| simulator | 32.6% | **45.2%** | 45% | +0.2pp |
| optimizer | 41.6% | **56.0%** | 45% | **+11.0pp** |
| analyzer | 40.8% | **54.9%** | 45% | **+9.9pp** |

The remaining 5 tests in the file (`describe.configure(mode:"serial")`) are then skipped
("5 did not run"), so dark/1280, both themes/1440, the fill-controller test and the
panels-reachable test were never exercised in this run.

**Root cause, read from the failing test's own `error-context.md` snapshot**
(`desktop/test-results/cr-default/layout-run-pages-—-light-at-1280x800-default/error-context.md`):
the per-page `work=` numbers are unchanged from the isolated run (33.0/31.8/45.7/44.3 — identical),
but `right=` (the right pane) jumps from 17-28% to **62.7-68.9%** dead. The snapshot shows why: the
right pane's tab strip has **`radio "Terminal" [checked]`**, not Scene — and the Terminal shows a
real job, `analyzer · ernie · queued · 39s`. S7's own rule ("Terminal from the moment a job of that
page's kind is running") is working exactly as designed; the problem is that this job is not
`layout.spec.ts`'s own — nothing in `layout.spec.ts` submits a job — it is **leftover state from an
earlier spec file in the same suite run**, still `queued` in the one shared mock-server instance
that the whole `npm run e2e` invocation reuses. Because that leftover job happens to be `kind:
analyzer, subject: ernie`, it forces the Terminal tab active on exactly the subject `layout.spec.ts`
itself selects, on exactly the Analyzer page — and a `queued`-with-plan Terminal view is emptier
than the Scene tab it displaces, which is what pushes all four pages (not just Analyzer) over
budget: `RunPaneTabs` state is page-scoped, but the *fact* that the shared server carries a running
job at all appears to widen every page's dead-space profile.

This is the same class of defect lane SUB already flagged in `sub-notes.md` §6 item 8
("suite-order flake in optimizer.spec.ts... an earlier spec's job was still holding a lock") and
item 7 (the whole-suite quiet-check failure from `scene.spec.ts`) — cross-spec state leaking
through the one shared mock server a whole `npm run e2e` invocation reuses. This pass's version is
a genuine **L5a budget miss**, not just a wording mismatch, and it reproduces on a clean run with
no other lane's work-in-progress involved.

## 6. Every acceptance number in the plan NOT met, with evidence

1. **Level B, run exactly as the RUNBOOK documents it (`npm run build` plain) — the whole real
   project including scene specs is NOT green.** 3 of 27 tests fail (one per scene spec file), 10
   more skipped as a consequence. Evidence: §2a-2c. **Not a defect in the scene panes
   themselves** — the identical specs, run against a `VITE_INCLUDE_GALLERY=1` build (documented
   only outside the RUNBOOK), are 13/13 green with every S8 number inside budget (§3d). The
   acceptance miss is squarely the RUNBOOK's Level B section being incomplete for this feature.

2. **L5a (dead space ≤45% on the four run pages, both sizes, both themes) is NOT met when LAY's
   own gate, `layout.spec.ts`, runs inside the full default e2e suite** — as opposed to run in
   isolation, where it is met and reproduces LAY's own numbers exactly. Inside the full suite: all
   four run pages fail at light 1280×800 (preprocess 46.1%, simulator 45.2%, optimizer **56.0%**,
   analyzer **54.9%**, vs a 45% limit). Evidence and root cause: §5a. This is a test-isolation
   defect (a leftover `queued` job from an earlier spec bleeds into the shared mock server that the
   whole suite reuses, forcing the right pane's Terminal tab active instead of Scene), not evidence
   that the shipped layout is wrong at the numbers LAY measured it at — but it does mean **the
   plan's own default-suite gate, run whole, does not currently prove L5a**, only the isolated
   `layout.spec.ts` invocation LAY's own re-run recipe uses does.

Every other acceptance number this pass measured is met:

| Area | Numbers | Verdict |
|---|---|---|
| Level A (§1) | 21/21 rows green | met |
| Level B non-scene (§2b) | 14/14 real specs green (incl. the 9.5m `source.spec.ts`) | met |
| S3 budgets (§3a) | all 6 surfaces (3 subjects × skin/gm) `within_budget: true`, ≤150k tris, ≤3MB | met |
| S8 warm (§3b, §3d) | manifest 49-82ms, surfaces 10-22ms warm; firstPaintMs 2-258ms fresh mount, all ≤2500ms | met |
| S8 cold (§3c) | manifest 202→200 ready in 2.81s, cold atlas build 173ms, both ≤12000ms | met |
| S8 fps (§3d) | 121.0-121.2fps orbiting, floor is 30 | met |
| S8 first-screen (§3d) | 13/13, 26/26, 28/28 controls visible, 0 hidden | met |
| L4 (§4) | 0 obstructed controls of 176-219 per page over 5-7 scroll steps, isolated and inside the full suite | met |
| L5b (§4) | 0 Tier-1 controls below the fold, both isolated and full-suite runs | met |
| L5c (§4) | 0px horizontal scroll | met |
| L5a isolated (§4) | 32.6-43.5% across 4 pages × 2 sizes × 2 themes, all ≤45% | met |
| Gates (§0) | pytest 3462 passed, typecheck clean, lint 0 errors, vitest 836 passed, build succeeds | met |

## 7. Open issues

1. **RUNBOOK gap — Level B's documented build command is insufficient for the scene specs.**
   `dev/notes/v3-pipelines/RUNBOOK.md`'s Level B section says `npm run build` (plain); the three
   real scene specs need `VITE_INCLUDE_GALLERY=1 npx electron-vite build` (documented only in lane
   SCC's own notes, §7/§9, not folded into the RUNBOOK). Running the RUNBOOK exactly as written
   against the whole real project fails all three scene spec files (1 failure + several skipped
   each). Evidence: §2a above; error text `"window.__scenePane is absent — build out/ with
   VITE_INCLUDE_GALLERY=1"` at `tests/e2e/real/scene-analyzer.spec.ts:47` (and the equivalent lines
   in `scene-optimizer.spec.ts` / `scene-simulator.spec.ts`). Suggested owner: whoever maintains
   `dev/notes/v3-pipelines/RUNBOOK.md`'s Level B section — add the flag to the build line, or add a
   scene-specific subsection the way LAY's and SCC's own re-run recipes already have it.

2. **The default e2e suite leaks job state across spec files, and this now produces a genuine
   L5a budget failure, not just cosmetic flake.** One shared mock-server instance backs the whole
   `npm run e2e` invocation; a job an earlier spec submits (here: `kind: analyzer, subject: ernie`,
   seen `queued` at 39s) is still live when `layout.spec.ts` runs later in the same invocation,
   forcing its right pane to the Terminal tab (S7's own rule, working correctly) instead of Scene —
   and that swap alone pushes all four run pages' dead-space ratio past the 45% L5a limit (up to
   +11.0pp on Optimizer). Evidence: §5a, `desktop/test-results/cr-default/layout-run-pages-—-
   light-at-1280x800-default/error-context.md`. Same root class as lane SUB's own findings 7-8 in
   `sub-notes.md` (whole-suite quiet-check FAIL from `scene.spec.ts`; a "wait" clause appearing in
   `optimizer.spec.ts` from another spec's held lock) — three independent lanes have now hit
   suite-order leakage through the one shared mock server. Suggested owner: whoever owns
   `tests/mock-server/server.mjs` (each spec file's jobs should not outlive that file — either the
   mock server should auto-terminate jobs between spec files, or every spec that submits a job
   needs its own `afterAll` cancellation, the way the `real` specs already do against the live
   container).

3. **Minor — LAY's own notes overstate theme-independence by one data point.** `lay-notes.md` §1
   states dead space is "identical in light and dark" and gives Simulator's 1280×800 number as
   34.4%; an isolated re-run measures Simulator's **light**-mode number as 32.6%, with 34.4% being
   the **dark**-mode number (a 1.8-point gap). All 15 of the other 16 light/dark pairs this pass
   measured are exactly identical, so the claim is true for everything but this one cell. Neither
   number threatens the 45% budget. Evidence: §4.
