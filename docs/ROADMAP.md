# Desktop verification and open work

Read [ARCHITECTURE.md](ARCHITECTURE.md) for the current contract and [DECISIONS.md](DECISIONS.md)
for rationale. The broader v3 program remains in `dev/notes/`; this page tracks the maintainer's
[2026-09-04 polishing requirements](requirements/2026-09-04-maintainer-polish.md) and
[2026-09-05 overview/batch/viewer requirements](requirements/2026-09-05-overview-batch-viewer.md)
and the [2026-09-05 Tetravox/selection/pipeline requirements](requirements/2026-09-05-tetravox-selection-pipeline.md).

## What exists

The developing desktop has shared workflow forms, a job rail, the Python job server and a Tetravox
embed. Production PyQt remains the reference for continuity while switching tabs.

## What is next

| Gate | Evidence | Result |
|---|---|---|
| R1 — retain workflow and viewer state | Hidden navigation, subject isolation and iframe identity tests | Pending |
| R2 — consistent usable controls | Shared-control tests, layout geometry and token contrast | Pending |
| R3 — viewport and surface opacity | Protocol assertions and real-embed rendering test | Pending |
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

## Known follow-ups

| Follow-up | Why it is not done | Where it is described |
|---|---|---|
| Per-point `radiusPx` in the embed, so "7 px when active" is a radius rather than a hue | Needs a second per-instance vertex attribute; the 2-D branch culls off-slice points by the existing one | TX.md §"Not done", EL.md §5.2 |
| Hover colour on an electrode dot | Tetravox 0.3.12 adds a `pointHover` event but deliberately no `stateColors.hover` — the host must paint it | TX.md §"Follow-up round", EL.md §2 |
| Remove the explicit idle `color` on every point | Fixed upstream in Tetravox PR #35; no release carries an embed asset yet | `embedScene.ts`'s `TODO(tetravox)`, TX.md |
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
