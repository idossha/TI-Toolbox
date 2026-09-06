# CR2 — verification of the fix round (FIX-A/B/C/D)

Worktree `.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`, 2026-09-04.
Nothing committed, staged, stashed or pushed by this pass. Every Electron/Playwright run went
through `TIT_E2E_OFFSCREEN=1` + `desktop/scripts/e2e-quiet-check.sh`; every one reported
**PASS — no window reached the screen**. Container `ti-toolbox-fad740e5-tit-1` was never
restarted or recreated; port 5173 (the maintainer's own `npm run dev`) was never touched.
`desktop/out/` is left on a **plain** `npm run build` at the end of this pass.

This file reproduces the specific number each lane claimed moved, not the lane's summary.

## Per-claim verification

| # | Claim (lane) | How checked | Before (as lane recorded) | Now (measured this pass) | Verdict |
|---|---|---|---|---|---|
| 1 | Pick draws both faces; region under cursor is picked, not a surface behind it (FIX-A defect 1) | `tests/e2e/scene.spec.ts` "picks the surface the eye can see…" (offscreen, gallery-flagged build), + read `glScene.ts::drawPickSequence` | expected `[23]`, received `[]` | selects region **23**; `drawPickSequence` calls `gl.disable(CULL_FACE)` before drawing (glScene.ts:649) | HOLDS |
| 2 | A click reports a world point (`onPickAt`) (FIX-A defect 2) | same spec, "reports where the click landed" case | `unprojectDepth is not a function` | `SCENE-PICKAT error=1.086mm tolerance=1.865mm` / `radial=0.293mm form=0.99128` | HOLDS — reproduces FIX-A's exact numbers |
| 3 | Camera framing at narrow pane width | same spec, "frames the head to fill the pane" case | fill 0.483 (348×544) / 0.589 (1192×544) | `SCENE-FRAMING 348x544 fill=0.908`; `1192x544 fill=0.926`; `880x420 fill=0.926`; `420x420 fill=0.897` | HOLDS — matches FIX-A's numbers exactly |
| 4 | `/api/scene/*` answers readably for subject 102 (onboarded-vs-catalog gate) (FIX-B defect 1) | live `curl` against the container, all 6 routes, subject 102, plus subject `zzz` and a `../../etc` traversal | all 6 routes: `"Unknown subject: 102"`, identical to a genuinely absent id | all 6 routes: `"102 has no head model yet: m2m_102/ does not exist and the only data staged for it is sourcedata/sub-102/. Run Pre-processing on 102 -- convert the raw data, then charm -- to create it."`; `zzz`/traversal: `"This project has no subject 'zzz'. It has: 101, 102, ernie, MNI152, test."` | HOLDS |
| 5 | Generated TS contract for the six scene ops (FIX-B defect 2) | `grep` `schema.d.ts` for `/api/scene/*` paths; read the generated `parts` type | hand-written `id: string`, `world: [number, number, number]`, no generated paths | `schema.d.ts` has all 6 `/api/scene/*` paths; `parts[].id: "skin" \| "gm"`, `kind: "surface"`, `bbox?: number[] \| null` — matches claim verbatim | HOLDS |
| 6 | Route-module import guard fails red on a planted violation | planted `os.listdir(".")` at module level in a **scratch copy** of `tit/` (never the real tree), ran `dev/route_import_guard.py --repo <scratch>` | n/a (new tool) | scratch: exit **1**, `2 violation(s)` (`filesystem`, `import-time-call`) on the planted module; real tree unaffected (`git status` clean) — real tree itself: `17 route module(s) clean`, exit 0 | HOLDS |
| 7 | Default e2e suite gives the same layout numbers as `layout.spec.ts` alone, across two consecutive full runs (FIX-C defect 1) | isolated `layout.spec.ts`, then full `--project=default` suite twice in a row (no rebuild between run 1 and run 2), same server process | full-suite (critic, pre-fix): 46.1/45.2/56.0/54.9 % (all over the 45 % limit) | isolated: **36.3/34.4/39.6/41.0 %**; full-suite run 1: **36.3/34.4/39.6/41.0 %** (identical); full-suite run 2: **36.3/34.4/39.6/41.0 %** (identical) — see run tallies below | HOLDS |
| 8 | `real/source.spec.ts` passes with its new budget | ran fresh against the live container, sub-101, `GET /api/jobs` clean before | old 600 000 ms budget: SUB's run exceeded it; LAY/critic <30 s margin | job `84f80a5203994ce9` **succeeded in 565.0 s** (JOB_TIMEOUT_MS=900 000 ms, 335 s / 59 % margin), **1 passed (9.6 m)**, quiet-check PASS; `FORWARD_DIR` created then removed by `afterAll` (confirmed absent after) | HOLDS |
| 9 | RUNBOOK's Level B command makes the scene specs pass | `VITE_INCLUDE_GALLERY=1 npx electron-vite build` then `--project=real` on the 3 `scene-*.spec.ts` files, against the live container | critic (plain build): 3 failed / 10 skipped | **13 passed (19.2 s)**, quiet-check PASS | HOLDS |
| 10 | Plain `npm run build` ships no test hooks and no gallery (grep it) | `npm run build`, then grepped every `out/renderer/assets/*.js` for `Design gallery`, `Every primitive`, `Mount scene`, `window.__scene`, `__scenePane` | present in a plain build before FIX-C | **0 occurrences of any of the five strings**, in any asset file | HOLDS |
| 11 | ROI-mode control is the same idiom on Optimizer and Analyzer (FIX-D defect 1) | `grep` for `RadioGroup`/`SegmentedControl` in `RoiPicker.tsx` and `AnalyzerPage.tsx`; ran `roi-idiom.spec.ts` inside the full suite | Optimizer: `RadioGroup`; Analyzer: `SegmentedControl` | both use `SegmentedControl` (`RoiPicker.tsx` 4 instances, `AnalyzerPage.tsx` 3 instances); `roi-idiom.spec.ts` defect-1 case **passed** | HOLDS |

Two more FIX-D/FIX-B numbers reproduced live in the same suite run (not on the task's explicit
list, but re-measured because they were cheap and load-bearing for defect 1's isolation claim):

- **FIX-D defect 2a** (`roi-saved-row` vs `subject-picker-row`): diagnostic line inside the full
  suite read `FIXD-ROWS subject-picker-row=0 roi-saved-row=3 (subjects closed)` — matches the
  lane's claimed after-state exactly.
- **FIX-D defect 4** (empty-state dead space), all 6 pages at 1280×800 and 1440×900, measured
  inside the same full-suite run: `panel-source` 41.7/43.7 %, `panel-cluster-permutation`
  37.6/35.6 %, `panel-nifti-group-average` 41.5/44.0 %, `panel-nilearn-visuals` 38.8/42.3 %,
  `panel-subject-info` 18.9/19.8 %, `jobs` 12.5/15.7 % — identical to the lane's own table.

## Full default-suite tallies (defect 1, FIX-C)

Both runs used the same `VITE_INCLUDE_GALLERY=1` build (built once, not rebuilt between runs —
the race FIX-A/FIX-C's own notes warn about), so `scene.spec.ts` and `gallery.spec.ts` are
included and green in both.

| Run | Result | Wall time | `LAY … light 1280x800` (preprocess/simulator/optimizer/analyzer) |
|---|---|---|---|
| isolated `layout.spec.ts` | 6 passed | 17.3 s | 36.3 / 34.4 / 39.6 / 41.0 % |
| full suite, run 1 | **129 passed, 1 skipped, 0 failed** | 7.9 m | 36.3 / 34.4 / 39.6 / 41.0 % |
| full suite, run 2 | **129 passed, 1 skipped, 0 failed** | 7.9 m | 36.3 / 34.4 / 39.6 / 41.0 % |

Every diagnostic line this pass could cross-check between the two full-suite runs was byte-identical:
`SCENE-PICKAT`, `SCENE-FRAMING` (all 4 pane sizes), `roi-idiom`'s `FIXD-ROWS`, and all 6
`panels-shape.spec.ts` empty-state percentages. Two consecutive full runs, zero drift.

(The 1 skip in both full-suite runs is `viewer-real.spec.ts`'s conditional real-Tetravox-embed
case, consistent with FIX-C's own report.)

## Gate re-run (`dev/notes/v3-pipelines/RUNBOOK.md`)

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3507 passed, 30 skipped, 21 deselected, 41.3 s** |
| `npm run typecheck` | clean, both projects |
| `npm run lint` | **0 errors**, 3 pre-existing warnings (`DataTable.tsx`, `VirtualList.tsx`, react-hook-form) |
| `npx vitest run` | **879 passed / 71 files** |
| `python3 dev/route_import_guard.py` | **17 route module(s) clean**, exit 0 |
| `python3 -m pytest tests/test_route_import_guard.py` | **24 passed** |
| `python3 -m pytest tests/test_scene_routes.py` | **49 passed** (31→49, matches FIX-B) |
| `dev/contracts_check.py contracts/openapi.v1.yaml <live dump>` | **47 problems** (gate failures) — unchanged, all pre-existing; 140 warnings (FIX-B recorded 139 at its own measurement moment — 1-warning drift, not a gate failure, see note below) |
| Level B real: `scene-simulator`+`scene-optimizer`+`scene-analyzer` | **13 passed (19.2 s)**, quiet-check PASS |
| Level B real: `real/source.spec.ts` (isolated, own budget) | **1 passed (9.6 m)**, job `84f80a5203994ce9` succeeded in 565.0 s, quiet-check PASS |
| Level A smoke matrix (`dev/smoke.sh`, whole) | **21 passed, 68 deselected, 571.3 s (0:09:31)**, exit 0; `find … -iname "*smoke*"` after: empty; `GET /api/jobs` clean after |
| Level B real project, remaining 14 spec files (26 tests) | **26 passed (5.1 m)**, quiet-check PASS — includes the 3 scene specs re-verified (identical numbers), analyzer-mesh/voxel, cluster-permutation, ex (2), flex, mex, nifti-group-average, nilearn-visuals, preprocess (2, incl. the 1.3 m tissue run), sim-mti, sim |
| Default e2e suite (two consecutive full runs) | run 1: 129 passed/1 skipped/0 failed; run 2: 129 passed/1 skipped/0 failed — **identical** |
| Plain-build hook/gallery grep | 0 occurrences |

Note on the 139→140 warning count: `dev/contracts_check.py` counts warnings across **every**
route with an undeclared response schema, not just the six scene ones (19 of the 140 warnings
here are scene-route warnings, one more than FIX-B's own "18 of 139"). The concurrent worktree
carries other lanes' in-flight, uncommitted route edits outside this program's scope, so a
1-warning drift in a total that spans the whole API is expected noise, not a regression in
anything FIX-B touched — the number that matters (**47 problems**, i.e. actual gate failures) is
exactly unchanged.

## Open issues (still open — not claimed fixed by any FIX-A/B/C/D lane this round)

- **`tit/scene/build.py`'s `gm` surface is still wound inward.** FIX-A's own request to FIX-B
  (fix-a-notes.md §5.1); FIX-B's notes do not touch `build.py`. Confirmed still true by construction (no
  code changes were made to `tit/scene/build.py` in this round). Affects: back-to-front
  translucency order, and `real/_scene.ts::chooseRegionPixel`'s culling filter cannot yet be
  dropped (FIX-A §5.3).
- **Mock server still answers `"Unknown subject: ${subject}"`** (`tests/mock-server/server.mjs`
  lines 1709/1772/1781/1792/1815/1830) instead of the real server's new sentence — FIX-B's O2,
  confirmed still present verbatim.
- **`ScenePane.tsx:95`'s comment still quotes the old sentence** ("Unknown subject: 102") —
  FIX-B's O3, confirmed still present.
- **`useRunPaneController.ts` still not deleted**, still imported by
  `pages/optimizer/index.tsx`, `pages/simulator/index.tsx`, `pages/analyzer/AnalyzerPage.tsx` —
  now the third lane (LAY, FIX-C, FIX-D) to flag the same exact request.
- **The scene e2e hooks (`window.__scene`/`__scenePane`) are still gated by
  `VITE_INCLUDE_GALLERY`, not a dedicated flag** — FIX-C's open issue 2, unaddressed (both gate
  sites are outside every fix lane's ownership).

## State left behind

- `desktop/out/` left on a **plain** `npm run build` (0 occurrences of `Design gallery`,
  `Every primitive`, `Mount scene`, `window.__scene`, `__scenePane` in any built asset).
- Container `ti-toolbox-fad740e5-tit-1` never restarted/recreated; `/api/health` = 200
  throughout (uptime only grew, 4090 s → 6771 s over this pass). `GET /api/jobs` clean
  (0 running/queued) before this pass and after it; every job this pass itself submitted (1
  `source` build, 21 Level A smoke rows, 26 Level B real specs) reached a terminal state and left
  no stray output — `find /Users/idohaber/datasets/000 -iname "*smoke*"` empty,
  `derivatives/SimNIBS/sub-101/forward/` absent (created then removed by `source.spec.ts`'s own
  `afterAll`).
- The whole `tests/e2e/real/` project (all 15 spec files) was run this pass, in two batches:
  `source.spec.ts` alone (1 passed) plus the other 14 files together (26 passed, and among them
  the 3 scene specs a second time, unchanged). **27/27 real tests passed** — critic's original
  27-test count for the whole project, all green this time (critic's own RUNBOOK-literal run had
  3 failures, all scene specs, all traced to the missing `VITE_INCLUDE_GALLERY=1` build flag —
  see claim 9).
- Port 5173 (the maintainer's own `npm run dev`) untouched; its process (`electron-vite dev`,
  pid 77069 and children) left running throughout.
- Nothing committed, staged, stashed or pushed.
