# Desktop verification and open work

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the current contract and [DECISIONS.md](DECISIONS.md)
for rationale. The broader v3 program is in `HISTORY.md`; this page tracks the maintainer's
[2026-09-04 polishing requirements](requirements/2026-09-04-maintainer-polish.md) and
[2026-09-05 overview/batch/viewer requirements](requirements/2026-09-05-overview-batch-viewer.md)
the [2026-09-05 Tetravox/selection/pipeline requirements](requirements/2026-09-05-tetravox-selection-pipeline.md)
and the [2026-09-06 native-panes/external-viewer requirements](requirements/2026-09-06-native-panes-external-viewer.md).

## What exists

The developing desktop has shared workflow forms, a jobs table on each multi-job run page, a job
rail, the Python job server and its own WebGL2 scene renderer for the run-page panes. 3-D
**viewing** is the **Tetravox embed**, baked into the image and served at `/tetravox/`, drawn in
the Viewer page's own Viewer sub-page (2026-09-06, ADR row 29); nothing is installed on the host.
The Viewer page's Menu sub-page composes the scene and one `POST /api/view/open` both posts it into
the embed and writes it to `<project>/code/ti-toolbox/viewer/<kind>.tetravox.json`. Production PyQt
remains the reference for continuity while switching tabs.

## What is next

| Gate | Evidence | Result |
|---|---|---|
| R1 — retain workflow and viewer state | Hidden navigation, subject isolation and iframe identity tests | Pending |
| R2 — consistent usable controls | Shared-control tests, layout geometry and token contrast | Pending |
| R3 — viewport and surface opacity | Renderer unit assertions and a real drawing-buffer pixel test | Pending |
| Integration | Typecheck, lint, unit suite, build and relevant hidden e2e suites | Pending |
| 2026-09-06 NB — Notebooks (ARCHITECTURE §7.6) | `pytest -k "kernel or notebook"` (67), `vitest` notebook units (50), `notebooks.spec.ts` (13 mock), `--project=real notebooks` (6, against the dev container) | **Passed**, including the worked example run end to end on a real SimNIBS kernel with its matplotlib PNG and DataFrame tables, and `from tit import get_pa` completed by the kernel itself |
| 2026-09-05 R1 — Overview replaces Subjects | One aggregate `GET /api/catalog/overview`; `overview.spec.ts` at 3 and 30 subjects; Subject Info deleted | Passed (`docs/dev/HISTORY.md § 2026-09-05 (Overview, batch, guide panes)`) |
| 2026-09-05 R2 — shared scrollable, clearable terminal | `terminal.spec.ts` geometry; `job-console.test.tsx` watermark semantics | Passed (`.../TM.md`) |
| 2026-09-05 R3 — subject selection and execution policy | `batch.spec.ts` one-request/cap 1/cap 2; `tests/test_jobs_routes.py` against the real scheduler | Passed (`.../BX.md`) |
| 2026-09-05 R4 — fixed guide in run-page panes | `guide.spec.ts` zero guide requests on subject change; packaged-asset and TVSC1 budget tests | Passed (`.../GD.md`) |
| 2026-09-05 R5 — Viewer loads on command | `viewer.spec.ts` R5 cases; optional `atlas` on `GET /api/view/{kind}` | Passed (`.../VW.md`) |
| 2026-09-05 consolidation gate | Typecheck, lint, unit, full offscreen e2e, build, host pytest, route-import guard, real-container checks | See `docs/dev/HISTORY.md § 2026-09-05 (Overview, batch, guide panes)` |
| 2026-09-05 A — Tetravox currency and automatic updates | `tests/test_tetravox_updates.py` against a loopback fake GitHub (protocol pre-check, digest, provenance, health latency); `build.sh` resolver both directions | Passed (`docs/dev/HISTORY.md § 2026-09-05/06 (Tetravox auto-update, selection, pipeline canvas)`); **first real automatic install blocked on Tetravox PR #35 and the 0.3.12 tag** |
| 2026-09-05 A6 — Tetravox release assets and the 3-D dot pass | Tetravox PR #35: `pnpm test` 1918, embed e2e 49 both legs, sidecars round-trip through `sha256sum -c` | Open PR (`.../TX.md`) — merge and tag are the maintainer's |
| 2026-09-05 B — electrode dots, colour as state | `scene-pane.spec.ts` 5–8; `real/embed-electrodes.spec.ts` pixel + radial-profile tests against the live embed | Passed (`.../EL.md`); B1's 3-D dot radius blocked on 0.3.12 |
| 2026-09-05 C — one selection grammar, receipt, shared existing-outputs dialog | `selection.spec.ts` (9), `selection-model.test.ts` (19), `run-receipt.test.ts`, `layout.spec.ts` hit-test | Passed (`.../SG.md`) |
| 2026-09-05 D — pipeline canvas, one job group, notebook export | `pipeline.spec.ts` (8), `test_pipeline_{graph,plan,notebook,routes,bindings}.py`, real `sim → analyzer` on sub-ernie end to end | Passed (`.../PC.md`, write-back in `.../CX2.md`) |
| 2026-09-05 second consolidation gate | Typecheck, lint, unit, full offscreen e2e, build, host pytest, route-import guard, contracts check, wheel contents, real-container subset | See `docs/dev/HISTORY.md § 2026-09-05/06 (Tetravox auto-update, selection, pipeline canvas)` |
| 2026-09-06 N1–N4 — native run-page panes, interactive atlas, electrode dots | Nine restored renderer suites; `scene-pane.spec.ts` region ↔ `RoiPicker` both directions and an aimed electrode pick; `guide.spec.ts` zero requests / same canvas across subject switches; real `scene-electrodes.spec.ts` drawing-buffer pixels | Passed (`docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`, real leg in `.../CX3.md`) |
| 2026-09-06 V1–V5 — the viewer is a separate application | `viewer-launch.test.ts` (14) pinning Tetravox's own launch contract; `viewer.spec.ts` one file / one launch call and no iframe anywhere; `tests/test_view_open.py` (10); real `POST /api/view/open` on sub-ernie validated against the ViewSpec schema on the host | Passed (`.../VX.md`) — **superseded the same day** by ADR row 29: the embed is the Viewer's renderer again and the host launch path is deleted; `POST /api/view/open` keeps writing the scene file |
| 2026-09-06 J — jobs tables on the Simulator and the Analyzer | `simulator.spec.ts`, `simulator-table.spec.ts`, `analyzer.spec.ts`, `batch.spec.ts`; real `montage-shape` TI/mTI wire shapes and `flex-result-selection` on sub-ernie | Passed (`.../JB.md`) |
| 2026-09-06 consolidation gate | Typecheck, lint, unit, full offscreen e2e, build, host pytest, route-import guard, contracts check, real-container subset | See `docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)` |
| 2026-09-06 TR — stacked transparency and per-label atlas colour | `scene-transparency.spec.ts`; `tests/test_scene_*.py` (187); real `scene-electrodes.spec.ts` drawing-buffer pixels — cos-to-own-hue 0.997 vs cos-to-flat-blue 0.753 at 122 fps | Passed (`.../TR.md`) |
| 2026-09-06 PL — pipeline canvas revamp, then the Subjects node and readiness gating | `pipeline-ux.spec.ts`, `pipeline.spec.ts`, `tests/unit/pipeline-graph.test.ts`, `tests/test_pipeline_readiness.py` (28 new); real readiness and three wire verdicts on Dataset 000 | Passed (`.../PL.md`) |
| 2026-09-06 TI — the managed Tetravox install | `tetravox-install.test.ts` over a loopback release index; `tetravox-install-real.test.ts` (env-gated) resolving the live index and installing v0.3.11, verified by `codesign --verify --deep --strict` | Passed (`.../TI.md`) — **superseded the same day** by ADR row 29: nothing installs Tetravox on the host |
| 2026-09-06 VM/VM2 — the Viewer is a source, a file list and Open | `viewer.spec.ts`, `viewer-page.test.ts`, `tests/test_view_open.py`, `tests/test_viewspec_overrides.py` (38); real `POST /api/view/open` on sub-ernie | Passed (`.../VM.md`, `.../VM2.md`) |
| 2026-09-06 OJ — the Optimizer's jobs table | `optimizer.spec.ts` (10), `roi-idiom`, `batch`, `selection`; real `flex` and `ex` submissions reaching `running` on sub-ernie and cancelled | Passed (`.../OJ.md`) |
| 2026-09-06/07 CX5 third consolidation gate | Typecheck clean (was 18 `noUncheckedIndexedAccess` errors); lint 0 errors / 3 pre-existing warnings; `vitest run` **1275 in 105 files**; host `pytest tests/` **3970 passed, 36 skipped** (`test_scene_guide`'s known order-dependent flake green in isolation); route-import guard 23 modules; `dev/contracts_check.py` OK; full offscreen mock e2e **285**; real subset **22** against the dev container incl. a real `pre` job run to completion, DK40 border spikes 6.20 %, warm first paint 92–122 ms, orbit 122 fps | Passed (`docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`). Two findings landed as fixes (`Fiducials.csv` listed as an EEG net; the net option's label lost its `.csv`), one left open (an idle electrode's worst contrast against the opaque-GM scalp is 2/255) |
| 2026-09-06 second consolidation gate | Typecheck, lint, unit (1110), mock-server contract coverage, the three re-derived e2e suites, host pytest (3740), route-import guard, contracts check, a deterministic contract generator, and the pipeline's real `sim → analyzer` leg run to completion | **Partial** — see `docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)`. The full offscreen e2e, the plain build and the real specs are **outstanding**: the machine ran out of disk (893 GiB of 926 used) and a second lane ran Playwright concurrently in the same worktree. Both runs died on `ENOSPC` |

## Known follow-ups

| Follow-up | Why it is not done | Where it is described |
|---|---|---|
| **The embed protocol is live again, and protocol 2 is on the path.** The Tetravox embed is the Viewer sub-page's renderer (ARCHITECTURE §7.1, ADR row 29). Protocol 2 (`feat/embed-protocol2` in the Tetravox repo: a points layer with depth-tested picking, camera get/set, a marker API) and Tetravox PR #35 are wanted here, not parked | The runtime install channel works end to end against a loopback index, but **the first automatic install still awaits a Tetravox release carrying `tetravox-embed-<v>.tgz`, its `.sha256` and its `.manifest.json` as assets** — no `idossha/tetravox` release carries them yet, so a fresh image bakes the placeholder and `GET /api/tetravox/updates` honestly reports that the index has nothing | `docs/dev/HISTORY.md § 2026-09-04 (embed convergence)`, `docs/dev/HISTORY.md § 2026-09-05/06 (Tetravox auto-update, selection, pipeline canvas){AU,TX}.md` |
| **Two renderers, and no decision to converge them.** The Viewer sub-page draws with the Tetravox embed; the run-page 3-D panes draw with this app's own WebGL2 renderer (`pages/_shared/scene/`, §7.2) | Deliberate for now — the panes draw packaged reference anatomy and need picking and marker behaviour this project controls, while the Viewer draws the user's data and wants the whole engine. Convergence is a future question again, not a settled one | `docs/dev/HISTORY.md § 2026-09-04 (embed convergence)` |
| **CI builds the from-scratch image recipe.** `Dockerfile.ti-toolbox.layered` was deleted and `build.sh` has one recipe; `--layered`/`--from-scratch`/`--skip-ui-build` are accepted and ignored. `.circleci/config.yml`'s `build-and-smoke-image` job passed `--layered`, and removing that reference leaves the job building from scratch | A from-scratch SimNIBS install is 30-60+ minutes natively and far longer emulated — well past what the default `machine` resource class should absorb on every push. Nothing in this repo provisions a large or self-hosted executor, and no nightly/release-gated variant of the job exists yet | `container/blueprint/README.md`, `docs/dev/HISTORY.md § 2026-09-03 (Docker streamline)` |
| Notebook **import** (`POST /api/pipelines/import`, reading `metadata.ti_toolbox.pipeline`) | Closes the round trip export already encodes; parsing hand-edited Python stays a non-goal | PC.md §9 |
| Job re-adoption across a server restart | The manager keeps a child pid in memory only, so a `--reload` leaves a finished job at `running`/`stalled` with `pid: None` and its dependants queued behind it forever. `status.json` already persists the `pid`/`create_time` pair for exactly this purpose; `POST /api/jobs/{id}/force` is today's escape hatch and lands the job in `lost` | PC.md open item 7 |
| `POST /api/jobs/{id}/retry` | The Jobs page's selection grammar can cancel and pin a selection but not retry it, because there is no endpoint | SG.md §6.3 |
| A saved pipeline's node forms open at their defaults | The document stores each node's built config; no page has a config → form-state reader | PC.md §8.2 |
| `ex`/`mex`/`leadfield`/`source`/`stats` nodes are edited as JSON | Their builders need values only the Optimizer page computes, or have no v3 form at all; the JSON is still validated server-side | PC.md §8.3 |
| `PageLayout` follow-ups from the selection pass — a `rowAction` slot on `SelectionList` (the saved-ROI list's per-row delete), and folding the Source panel's two page-local confirmations into the shared dialog once `/api/plan` has a source kind | Both are additive and neither blocks the grammar | SG.md §6.2, §6.4 |
| `tags` on `JobStatus`, so the pipeline page maps job → node directly instead of zipping plan order | A contract change the pipeline lane declined to make unilaterally | PC.md §8.4 |
| **One job group per kind on the Optimizer.** A Run whose rows mix a flex-family and an ex-family method is two `POST /api/jobs/groups` calls and therefore two group ids, which the page states rather than hides | `/api/jobs/groups` takes one `kind`; making one Run one group needs either a mixed-kind group on the server or a client-side grouping that would lie about cancel | OJ.md, ARCHITECTURE §7.5 |
| **A shared `useTableColumns` hook.** `simulator/MontageManager.tsx::resolveColumnWidths` and `optimizer/rows.ts::resolveOptColumnWidths` are the same algorithm over different keys, as are the two `ColumnHandle`s and the two storage readers; the Analyzer's fixed-pixel colgroup would fold in too | The three files were being edited by three lanes at once; merging them across a moving target was the one refactor that could not be verified | OJ.md open items |
| **A shared `roiLabel(value, opts)`.** `optimizerTargetLabel` and `analyzer/JobRows.tsx::analyzerTargetLabel` word the three shared ROI modes identically on purpose and differ only in the mode each page alone has | Two callers is not yet a shared module; the moment a third page needs one it is `pages/_shared/roi` | OJ.md open items |
| **The per-point follow-ups** — a per-point `radiusPx`, per-point opacity and a marker API — are wanted by both renderers | The native pane draws its own dots, so these are now this project's to implement rather than Tetravox's to expose | `.../v3-tetravox-selection-pipeline/{TX,EL}.md`, ROADMAP row above |
| **The Viewer's `overrides` / `extras` server plumbing has no client.** Kept: it is additive, contract-declared and covered by `tests/test_viewspec_overrides.py` (38 passing) | VM2's file-list page does not set per-layer appearance by design, so nothing calls it today. Deleting it is a five-line change and the test file says exactly what would be lost | VM2.md open item 5 |
| **`FlexConfig.output_folder` is the run name.** A flex row writes its run name to `output_folder` while ex/mEx write `run_name` | Two names for one user-facing idea, inherited from two config dataclasses; unifying is a server-side change | OJ.md open items |
| **The Simulator node on the pipeline canvas is not yet the Simulator's jobs table** | The table was being rewritten in the same worktree while the canvas lane ran; the node still fans out per subject × montage on the server | PL.md open item 1 |

This pass is not a release certification. Full scientific workflow validation on supported runtime
platforms, packaging/signing and release delivery remain owned by the broader v3 program. CI can
reproduce synthetic tests; local GPU/data evidence is recorded separately rather than implied by a
mock-server pass.

## Notebooks — open work (2026-09-06, NB lane)

1. ~~Completions and hovers.~~ **Done** (2026-09-06), and not with `pylsp`: completion is a kernel
   round trip over `/ws/kernels`, because the interpreter holding the objects is the only thing
   that can complete them. `python-lsp-server` stays in the image and stays unused.
2. ~~Syntax highlighting in cells.~~ **Done** (2026-09-06): CodeMirror 6 with `lang-python`.
3. ~~Signature help on ⇧⇥.~~ **Done** (2026-09-07): the tooltip shows the kernel's signature and
   the docstring's first paragraph, on `(` and on ⇧⇥, dismissed by Escape or by leaving the call.
4. **A variable explorer.** The kernel is already driven from the server, so a `%whos`-shaped
   inspector is a route and a pane rather than new machinery.
5. **Interactive plots.** Would need a privileged scheme for output frames, the way SUNA's
   `suna-output:` works — a shell change, not a notebook change.
6. **The pipeline canvas should be able to save its export here.** `POST /api/notebooks` already
   accepts a document, so this is one button on the canvas: today its export still goes only to a
   host download.
