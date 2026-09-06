# Desktop verification and open work

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the current contract and [DECISIONS.md](DECISIONS.md)
for rationale. The broader v3 program remains in `dev/notes/`; this page tracks the maintainer's
[2026-09-04 polishing requirements](requirements/2026-09-04-maintainer-polish.md) and
[2026-09-05 overview/batch/viewer requirements](requirements/2026-09-05-overview-batch-viewer.md)
the [2026-09-05 Tetravox/selection/pipeline requirements](requirements/2026-09-05-tetravox-selection-pipeline.md)
and the [2026-09-06 native-panes/external-viewer requirements](requirements/2026-09-06-native-panes-external-viewer.md).

## What exists

The developing desktop has shared workflow forms, a jobs table on each multi-job run page, a job
rail, the Python job server and its own WebGL2 scene renderer. 3-D **viewing** is the separate
Tetravox desktop app on the host, which the Viewer page opens with a scene file (2026-09-06); this
app embeds no viewer. Production PyQt remains the reference for continuity while switching tabs.

## What is next

| Gate | Evidence | Result |
|---|---|---|
| R1 — retain workflow and viewer state | Hidden navigation, subject isolation and iframe identity tests | Pending |
| R2 — consistent usable controls | Shared-control tests, layout geometry and token contrast | Pending |
| R3 — viewport and surface opacity | Renderer unit assertions and a real drawing-buffer pixel test | Pending |
| Integration | Typecheck, lint, unit suite, build and relevant hidden e2e suites | Pending |
| 2026-09-05 R1 — Overview replaces Subjects | One aggregate `GET /api/catalog/overview`; `overview.spec.ts` at 3 and 30 subjects; Subject Info deleted | Passed (`dev/notes/v3-overview-batch-viewer/OV.md`) |
| 2026-09-05 R2 — shared scrollable, clearable terminal | `terminal.spec.ts` geometry; `job-console.test.tsx` watermark semantics | Passed (`.../TM.md`) |
| 2026-09-05 R3 — subject selection and execution policy | `batch.spec.ts` one-request/cap 1/cap 2; `tests/test_jobs_routes.py` against the real scheduler | Passed (`.../BX.md`) |
| 2026-09-05 R4 — fixed guide in run-page panes | `guide.spec.ts` zero guide requests on subject change; packaged-asset and TVSC1 budget tests | Passed (`.../GD.md`) |
| 2026-09-05 R5 — Viewer loads on command | `viewer.spec.ts` R5 cases; optional `atlas` on `GET /api/view/{kind}` | Passed (`.../VW.md`) |
| 2026-09-05 consolidation gate | Typecheck, lint, unit, full offscreen e2e, build, host pytest, route-import guard, real-container checks | See `dev/notes/v3-overview-batch-viewer/CX.md` |
| 2026-09-05 A — Tetravox currency and automatic updates | `tests/test_tetravox_updates.py` against a loopback fake GitHub (protocol pre-check, digest, provenance, health latency); `build.sh` resolver both directions | Passed (`dev/notes/v3-tetravox-selection-pipeline/AU.md`); **first real automatic install blocked on Tetravox PR #35 and the 0.3.12 tag** |
| 2026-09-05 A6 — Tetravox release assets and the 3-D dot pass | Tetravox PR #35: `pnpm test` 1918, embed e2e 49 both legs, sidecars round-trip through `sha256sum -c` | Open PR (`.../TX.md`) — merge and tag are the maintainer's |
| 2026-09-05 B — electrode dots, colour as state | `scene-pane.spec.ts` 5–8; `real/embed-electrodes.spec.ts` pixel + radial-profile tests against the live embed | Passed (`.../EL.md`); B1's 3-D dot radius blocked on 0.3.12 |
| 2026-09-05 C — one selection grammar, receipt, shared existing-outputs dialog | `selection.spec.ts` (9), `selection-model.test.ts` (19), `run-receipt.test.ts`, `layout.spec.ts` hit-test | Passed (`.../SG.md`) |
| 2026-09-05 D — pipeline canvas, one job group, notebook export | `pipeline.spec.ts` (8), `test_pipeline_{graph,plan,notebook,routes,bindings}.py`, real `sim → analyzer` on sub-ernie end to end | Passed (`.../PC.md`, write-back in `.../CX2.md`) |
| 2026-09-05 second consolidation gate | Typecheck, lint, unit, full offscreen e2e, build, host pytest, route-import guard, contracts check, wheel contents, real-container subset | See `dev/notes/v3-tetravox-selection-pipeline/CX2.md` |
| 2026-09-06 N1–N4 — native run-page panes, interactive atlas, electrode dots | Nine restored renderer suites; `scene-pane.spec.ts` region ↔ `RoiPicker` both directions and an aimed electrode pick; `guide.spec.ts` zero requests / same canvas across subject switches; real `scene-electrodes.spec.ts` drawing-buffer pixels | Passed (`dev/notes/v3-native-panes-external-viewer/NR.md`, real leg in `.../CX3.md`) |
| 2026-09-06 V1–V5 — the viewer is a separate application | `viewer-launch.test.ts` (14) pinning Tetravox's own launch contract; `viewer.spec.ts` one file / one launch call and no iframe anywhere; `tests/test_view_open.py` (10); real `POST /api/view/open` on sub-ernie validated against the ViewSpec schema on the host | Passed (`.../VX.md`) |
| 2026-09-06 J — jobs tables on the Simulator and the Analyzer | `simulator.spec.ts`, `simulator-table.spec.ts`, `analyzer.spec.ts`, `batch.spec.ts`; real `montage-shape` TI/mTI wire shapes and `flex-result-selection` on sub-ernie | Passed (`.../JB.md`) |
| 2026-09-06 consolidation gate | Typecheck, lint, unit, full offscreen e2e, build, host pytest, route-import guard, contracts check, real-container subset | See `dev/notes/v3-native-panes-external-viewer/CX3.md` |

## Known follow-ups

| Follow-up | Why it is not done | Where it is described |
|---|---|---|
| **Parked: the Tetravox embed protocol.** Protocol 2 (`feat/embed-protocol2` in the Tetravox repo: a points layer with depth-tested picking, camera get/set, a marker API) and Tetravox PR #35 remain useful upstream, and an embed package is a reasonable thing for *some* host to want | Nothing in TI-Toolbox depends on either any more (2026-09-06): the run-page panes are this app's own renderer and viewing is the desktop app. Neither is on this project's critical path. If an in-window viewer is ever wanted again, the decision to revisit is ARCHITECTURE §7.1, not the protocol | `dev/notes/v3-native-panes-external-viewer-plan.md` V4/V5; the three per-point follow-ups it retires are in `.../v3-tetravox-selection-pipeline/{TX,EL}.md` |
| Notebook **import** (`POST /api/pipelines/import`, reading `metadata.ti_toolbox.pipeline`) | Closes the round trip export already encodes; parsing hand-edited Python stays a non-goal | PC.md §9 |
| Job re-adoption across a server restart | The manager keeps a child pid in memory only, so a `--reload` leaves a finished job at `running`/`stalled` with `pid: None` and its dependants queued behind it forever. `status.json` already persists the `pid`/`create_time` pair for exactly this purpose; `POST /api/jobs/{id}/force` is today's escape hatch and lands the job in `lost` | PC.md open item 7 |
| `POST /api/jobs/{id}/retry` | The Jobs page's selection grammar can cancel and pin a selection but not retry it, because there is no endpoint | SG.md §6.3 |
| A saved pipeline's node forms open at their defaults | The document stores each node's built config; no page has a config → form-state reader | PC.md §8.2 |
| `ex`/`mex`/`leadfield`/`source`/`stats` nodes are edited as JSON | Their builders need values only the Optimizer page computes, or have no v3 form at all; the JSON is still validated server-side | PC.md §8.3 |
| `PageLayout` follow-ups from the selection pass — a `rowAction` slot on `SelectionList` (the saved-ROI list's per-row delete), and folding the Source panel's two page-local confirmations into the shared dialog once `/api/plan` has a source kind | Both are additive and neither blocks the grammar | SG.md §6.2, §6.4 |
| `tags` on `JobStatus`, so the pipeline page maps job → node directly instead of zipping plan order | A contract change the pipeline lane declined to make unilaterally | PC.md §8.4 |

This pass is not a release certification. Full scientific workflow validation on supported runtime
platforms, packaging/signing and release delivery remain owned by the broader v3 program. CI can
reproduce synthetic tests; local GPU/data evidence is recorded separately rather than implied by a
mock-server pass.
