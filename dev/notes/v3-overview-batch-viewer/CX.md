# Lane CX — consolidation: cross-lane seams, records, and the delivery gate (2026-09-05)

Plan of record: `desktop/IMPLEMENTATION_PLAN.md` (delivery steps 1 and 7). Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. **Nothing committed,
staged, stashed, checked out or reverted.** Every Playwright run was offscreen; the quiet check
reports `no new Electron/Chromium window reached the screen` on both the mock and the real run.

## 1. Seams closed

| Seam (from the lane notes) | What it turned out to be | Files touched |
| --- | --- | --- |
| (a) `tests/unit/subjects-readiness.test.ts` imports the deleted `pages/subjects/readiness` | **already closed** — lane OV deleted the file and replaced it with `tests/unit/overview-model.test.ts`; typecheck was clean on arrival | — |
| (b) `page-memory` / `smoke` viewer cases wait for `data-viewer-status="ready"` while R5 loads only on Load | the specs now perform the two-act R5 flow (draft, then **Load**); R5 itself is untouched. `page-memory`'s combobox-count assertion now pins the view type first, because R5 makes the bar's shape a function of the type | `tests/e2e/smoke.spec.ts`, `tests/e2e/page-memory.spec.ts` |
| (c) GD's page-file prop deletion | deleted `subject=`/`unavailable=` from all three `<ScenePane>` call sites and `sphere=`/`onSphereChange=` from Optimizer and Analyzer; then deleted the four props, their doc comments and the four `void` statements from `ScenePane`. `sceneSubject`/`sceneUnavailable` became dead in all three pages and are gone; the spherical/subcortical pane notes stopped claiming the pane draws "this subject's own anatomy" | `pages/_shared/scene/ScenePane.tsx`, `pages/simulator/index.tsx`, `pages/optimizer/index.tsx`, `pages/analyzer/AnalyzerPage.tsx` |
| (d1) `tests/e2e/gallery.spec.ts:40` | **deleted as superseded** by `tests/e2e/terminal.spec.ts`, which drives the same gallery console and makes the identical assertions correctly (TM's own first option); a comment at the old site says where the gate lives and why the old case read `scrollLeft === 0` | `tests/e2e/gallery.spec.ts` |
| (d2) `ui/VirtualList.tsx` follow-tail resets `scrollLeft` | the horizontal offset is captured before `scrollToIndex` and restored after it, so following the tail no longer snaps a reader back to column 0 of a long log line | `src/renderer/ui/VirtualList.tsx` |
| (e) ⌘1 label in `pages/help/KeyboardTab.tsx` | **already closed** — OV had made the one-word change; kept (the sheet must name a page that exists) | — |
| (f) `pyproject.toml` package data for `tit/scene/guide/` | no other `tit` package data is declared anywhere (no `MANIFEST.in`, no existing `package-data` block), so GD's block was added verbatim with a comment saying why `include-package-data` is not enough. **Proved, not assumed:** `python3 -m pip wheel . --no-deps` → `tit-2.4.0-py3-none-any.whl` contains **20 `tit/scene/guide/*` data files** (manifest, PROVENANCE, 2 surfaces ×2 formats, 3 labels, 3 legends, 8 nets) | `pyproject.toml` |
| (g) lint errors in `tests/e2e/panels.spec.ts` | **already closed** — OV deleted that spec (its only test was the Subject Info panel); `pnpm run lint` is 0 errors | — |
| (g) five undeclared `/api/guide/*` mock routes | **already closed** — GD added them; `npx vitest run tests/mock-server` is 33/33, contract coverage included | — |

Three further reds surfaced only in the *combined* suite (no single lane could see them) and were
closed here:

* `tests/e2e/settings.spec.ts:86` asserted the **Subject info** rail link is visible after a save.
  R1 deleted that page; the assertion is now `toHaveCount(0)`.
* `tests/e2e/roi-idiom.spec.ts:116` counted `.subject-picker-row` document-wide with the
  Optimizer's disclosure closed and got 3. Cause: since R3 every retained hidden page keeps an
  **open** `SubjectsField` mounted, so a document-wide count sees another page's rows. The two
  counts are now scoped to `[data-page-active="true"]`, which is what the assertion always meant.
* `tests/e2e/preprocess.spec.ts:163` expected the shared **Clear terminal** control immediately
  after queueing. `JobTerminal`'s source is `live` only once the job it picked has emitted a line
  (`job ? (lines.length > 0 ? "live" : "preview")`), and a group's newest member is queued behind
  its `after` dependencies. The spec now waits for `data-source="live"` first, then asserts the
  control. No product change — the R2 rule that the pane is never an empty box is unchanged.
* `tests/e2e/gallery.spec.ts:156` read `status-space` on the Viewer without loading anything; under
  R5 that cell labels the **loaded** scene. The spec now drafts subject `ernie` and presses Load.

## 2. Records landed (delivery step 1)

| File | Entry |
| --- | --- |
| `docs/requirements/2026-09-05-overview-batch-viewer.md` | **new** dated intent document: the seven verbatim asks and R1–R5 with their gate tests, stating that it supersedes the 2026-09-04 requirements and reverses DESIGN.md §§9–10 where they conflict |
| `docs/ARCHITECTURE.md` | **§3 amended** (run-page panes draw the fixed guide; `guide-ras` is not a subject's space; the Viewer and `/api/scene/*` remain where subject-RAS picking lives). **§5 amended** (the 2026-09-05 requirements join the observable gate; the four new spec files named). **New §6** — the contract amendments in one section: `GET /api/catalog/overview` + `PresenceState`; `/api/jobs/groups` as the batch seam with server-forced `subject_id`; the one console renderer + one pure transform and Clear's semantics; `GET /api/guide/*` (immutable, no subject, `TVSC1` budget, wheel packaging); optional `atlas` on `GET /api/view/{kind}`; the Viewer's draft/loaded split. Section numbers 1–5 are untouched |
| `docs/DECISIONS.md` | five appended entries, in the file's existing `## <date> — <sentence>` + Decision/Why/Alternatives-rejected shape: **"The app opens on a project Overview, and Subject Info is deleted"**, **"Terminal Clear is presentational, not destructive"**, **"Batch execution is a scheduler cap, not renderer request timing"** (with the job-count-not-subject-count limit recorded), **"The workflow 3D panes draw a fixed guide, not the selected subject"**, **"The Viewer loads on command, not on selection"** (carrying the `atlas` fallback and the `.annot` exclusion). OV's, TM's, BX's, GD's and VW's overlapping proposals are deduped into these five |
| `docs/ROADMAP.md` | intent-document link added; six rows appended to the "What is next" table — R1–R5 with the spec that proves each and the lane note that records it, plus the consolidation-gate row pointing here |
| `tracks/active/v3-electron-gui.md` | ADR **row 25**, "Overview, batch, terminal, guide, Viewer (2026-09-05)", in the table's existing three-column form, quoting the maintainer and citing plan/requirements/§6/lane notes |
| `desktop/DESIGN.md` | **§9**: rail row 1 is `overview` / Overview / `LayoutGrid` / ⌘1; "Landing page is Subjects" replaced by what Overview is and is not; `panel-subject-info` recorded as deleted (five panel pages → four). **§4.6**: the terminal names the shared renderer and transform, and Clear's local/presentational semantics. **§10**: the source-bar figure and bullet rewritten for draft-vs-Load, plus the "a failed load keeps the picture" bullet. **§13**: run-page panes draw the fixed guide; a Results link prefills the draft |
| `desktop/IMPLEMENTATION_PLAN.md` | Status line now states what is gated, what the consolidation lane landed, and that `pnpm run dev` is deliberately the maintainer's own smoke |

## 3. Gate (delivery step 7)

| Command | Where | Result |
| --- | --- | --- |
| `pnpm run typecheck` | `desktop/` | clean (both projects) |
| `pnpm run lint` | `desktop/` | **0 errors**, 3 warnings — all pre-existing `react-hooks/incompatible-library` on `ui/DataTable.tsx` and `ui/VirtualList.tsx` |
| `pnpm run test` | `desktop/` | **79 files, 892 tests passed** |
| `pnpm run e2e:quiet` (full suite, offscreen) | `desktop/` | **172 passed, 3 skipped, 0 failed** (9.9 min); `e2e-quiet-check: PASS`, `no new Electron/Chromium window reached the screen` |
| `pnpm run build` | `desktop/` | `✓ built in 1.91s` |
| `python3 -m pytest tests/ -q` | repo root | **3655 passed, 47 skipped, 21 deselected** (51 s) |
| `python3 dev/route_import_guard.py` | repo root | `route_import_guard: 20 route module(s) clean` |
| `python3 -m pip wheel . --no-deps` | repo root | wheel contains the 20 packaged guide assets (seam f) |
| `npx tsx scripts/dev.ts --help` | `desktop/` | resolves and prints its usage (`--web`, `--down`, `--force`); `pnpm run dev` itself **not** run — that is the maintainer's final smoke |

Real container `ti-toolbox-fad740e5-tit-1` (port 8765, worktree mounted, `--reload`; token from
`docker inspect`), Dataset 000:

```
GET /api/health            200  {"status":"ok","uptime_s":4480.051}
GET /api/guide/manifest    200  2518 B  space "guide-ras", guide "ernie (SimNIBS example head)"
GET /api/catalog/overview  200  3486 B  0.14 s warm
   subjects 101, 102, ernie, MNI152, test
   totals   5 subjects · 10 simulations · 25 optimizations · 9 analyses
   coverage raw 3/5 · recon 2/5 · m2m 3/5 · dwi 0/5 · leadfield 2/5
GET /api/view/subject?subject=ernie&atlas=aparc.DKTatlas+aseg.mgz  200
   layers = [m2m_ernie/T1.nii.gz, freesurfer/sub-ernie/mri/aparc.DKTatlas+aseg.mgz]
            (the requested atlas, not the server's default segmentation/labeling.nii.gz)
```

`--project=real` Playwright subset (per `dev/notes/v3-pipelines/RUNBOOK.md`, `--project=real`,
offscreen, quiet-checked), chosen to cover this program's seams without starting an FEM run:

```
$ TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> TIT_E2E_OFFSCREEN=1 \
    bash scripts/e2e-quiet-check.sh npx playwright test --project=real \
      tests/e2e/real/{scene-preview,tetravox,embed-occlusion,page-memory}.spec.ts
11 passed (37.6s)          e2e-quiet-check: PASS
```

Notable lines from that run: the three run-page previews keep their camera/opacity across a
navigation with the same iframe; `page-memory`'s simulator and optimizer state dumps show the new
`Execution` section (R3) round-tripping; the occlusion tests still read the GIfTI the scene service
builds over HTTP. `sim`, `flex`, `ex`, `mex` and the preprocessing real specs were **not** run:
they start real FEM/optimization jobs on the shared container, which the pipelines RUNBOOK forbids
here, and nothing in this program changes what those runners compute.

### One flake seen and chased, not left unexplained

`analyzer.spec.ts:142`'s `deadSpaceRatio ≤ 0.65` failed once in a full-suite run (the first of
three). Re-run in isolation and again after `preprocess.spec.ts`, the analyzer numbers are
identical and inside the bound (0.5335 at 1280×800, 0.6092 at 1440×900), and the two subsequent
full-suite runs were green. It is a marginal layout measurement (0.61 against a 0.65 bound), not a
state leak I could reproduce; recorded here rather than papered over by raising the threshold.

## 4. Open items (all lanes)

**Product / science**

1. **Cortical `.annot` atlases cannot be offered in the Viewer** (VW). They are FreeSurfer surface
   parcellations, not volumes, so the atlas menu filters them out; overlaying one needs a surface
   layer in the ViewSpec. Real work for anyone who wants DK40 on the 3D pane.
2. **The batch cap counts jobs, not distinct subjects** (BX). On the Simulator one subject with
   three montages is three jobs, so a cap of 2 can run two montages of the same subject together.
   `tit.jobs.locks` keeps that safe and the control's help says "jobs". Subject-count semantics
   would be a scheduler change plus a contract note.
3. **`source` is not in `GROUP_KINDS` and has no cap** (BX). Both Source pipelines are single jobs
   over the whole selection with their own `cpus`/`workers` fields. If forward-solution building
   ever becomes one job per subject, `source` joins the enum and `SubjectsInParallel` replaces its
   `Workers` field.
4. **The Viewer's `group` type reuses the subject's atlas list for its ROI selector** (VW). It
   renders "None" rather than misleading anyone, but a group-scoped catalog call would be right.
5. **`analysis` and `custom` views show no space control** because `build_view` builds both in
   subject space; `controlsFor` is the one line to change if either gains an MNI form.
6. **Overview cold latency** is 3.4 s on Dataset 000 (5 subjects, 25 optimization runs) against
   0.12–0.14 s warm — manifest parsing inside `catalog.flex_runs`/`ex_runs`/`analyses`. If a large
   project makes this bite, the fix is a counts-only path in `tit.catalog`, not more requests.

**Code hygiene**

7. **`SceneGesture` still contains `"sphere"`** (GD) — the pane never produces it; only
   `embedScene.ts` and its unit tests still branch on it. Two-file removal once nothing reads it.
8. **`sphereMarkers` / `roundCoord` / `vecFromCentre`** in `pages/_shared/scene/{model,embedScene}.ts`
   now have no product caller — only `tests/unit/scene-pane-model.test.ts`. Left in place this
   round; delete with the `"sphere"` gesture.
9. **`/api/scene/*` is live and uncalled by the app** (GD). It is still the right service for a
   *subject's* scene and for a future MNI picking mode; if it stays uncalled through the next round
   it should be considered for retirement, with `dev/contracts_check.py` and the mock kept in step.
10. **`tit/server/routes/settings.py`'s `_VALID_PANELS` still accepts `"subject-info"`** (OV),
    deliberately: an existing project `settings.json` must keep loading, and no page claims the id.
    Drop it in a later cleanup.
11. **The packaged guide is 15.5 MB of binary in a source tree** (GD). Acceptable (it replaces a
    per-project 184 MB read) and reproducible from `tit.scene.guide_build`, so a release-time build
    step is a drop-in if it becomes a problem.
12. **`dev/contracts_check.py` reports 7 pre-existing problems** — `Capabilities.tetravox_embed`,
    `Capabilities.fastsurfer` and `Subject.has_fastsurfer` are served but not required in the
    contract. Untouched by this program (no lane edits those schemas); recorded, not fixed.
13. **`tests/e2e/artifacts/*/metrics.json` from older runs still name `subjects-light-*.png`.**
    They are historical run records; the live screenshot names are `overview-*`.

**Still owed by the plan**

14. Step 7's `pnpm run dev` interactive smoke is the maintainer's, and was deliberately not run.
15. Nothing in this program is committed. `desktop/` and `tit/server/` remain untracked WIP.
