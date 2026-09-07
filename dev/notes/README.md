# dev/notes

Working notes that are not part of the documentation contract. The durable
records are `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, the ADR table in
`tracks/active/v3-electron-gui.md`, `desktop/DESIGN.md`, `docs/requirements/*`
and `docs/ROADMAP.md`.

What lives here now:

| File | What it is |
| --- | --- |
| `v3-program-history.md` | One chronological record of every v3 program (2026-08-27 → 2026-09-06): the ask, what shipped, decisions that survived and where they are recorded, what was reversed, and the measurements and gotchas that exist nowhere else. |
| `v3-pipelines/RUNBOOK.md` | Live runbook for running the two-level smoke harness. Cited by `desktop/tests/e2e/batch.spec.ts` and `real/pipeline.spec.ts`. |
| `v3-ui-program/u0-design-notes.md` | The verbatim TypeScript contract signatures and API field mappings that `desktop/DESIGN.md` §5 defers to instead of restating. |
| `v3-ui-program/wireframes.md` | Per-page ASCII layouts with inline dimensions, and per-page empty-state copy. Its §9 dead-space ceilings are superseded by `desktop/DESIGN.md` §12.3. |
| `flex-search-multicore-analysis.md` | Unrelated 2026-04 backend analysis of why `cpus` does not accelerate flex-search. |

`../spikes/README.md` holds the merged verdicts of the 2026-09-03 native-desktop
spikes; the spike code itself was never shipped and has been deleted.

## Retired paths

On 2026-09-07 about 120 plan and lane-evidence files were folded into
`v3-program-history.md` and deleted. Source comments and older documents may
still cite them. Everything below now resolves to the named section of
`v3-program-history.md`.

| Retired path | Now |
| --- | --- |
| `v3-build-plan.md`, `v3-spikes.md` | § 2026-08-27 — v3 build program + spikes |
| `j3-verdict-frontend.md`, `v3-ux-redesign-plan.md`, `v3-research/*` | § 2026-09-02 — UX redesign, workflow-first IA |
| `v3-native-desktop-plan.md`, `v3-native-research/*` | § 2026-09-03 — Native desktop research (parked), plus `../spikes/README.md` |
| `v3-docker-streamline-plan.md`, `v3-docker-streamline/*` (`w2-image-notes.md`, `w3a-server-notes.md`, `w3b-preprocessing-notes.md`, `w6-docs-ci-notes.md`, …) | § 2026-09-03 — Docker streamline (one image, `tit.server`); image-recipe detail lives in `container/blueprint/README.md` |
| `v3-pipelines-program.md`, `v3-pipelines/*` except `RUNBOOK.md` (`2026-09-03-smoke.md`, `s1-notes.md`, `f0-notes.md`, …) | § 2026-09-03 — Pipelines program |
| `v3-ui-program.md`, `v3-ui-program/*` except `u0-design-notes.md` and `wireframes.md` | § 2026-09-03 — UI program |
| `v3-scene-ia-plan.md`, `v3-scene-ia/*` (`sca-notes.md`, `scc-notes.md`, `critic-notes.md`, `fix-a/b/c-notes.md`, `n2-notes.md`, …) | § 2026-09-04 — Scene service, subject-selection grammar, layout pass |
| `v3-embed-convergence-plan.md`, `v3-embed-convergence/*` (`u-notes.md`, …), `v3-3d-panes-plan.md`, `v3-consolidation-recovery.md` | § 2026-09-04 — Embed convergence and runtime-installable Tetravox |
| `v3-overview-batch-viewer/*` (`OV.md`, `CX.md`, …) | § 2026-09-05 — Overview, batch execution, guide panes, explicit Load |
| `v3-tetravox-selection-pipeline-plan.md`, `v3-tetravox-update-electrodes-selection-plan.md`, `v3-tetravox-selection-pipeline/*` (`AU.md`, `CX2.md`, …) | § 2026-09-05/06 — Tetravox auto-update, electrode dots, selection grammar, pipeline canvas |
| `v3-native-panes-external-viewer-plan.md`, `v3-native-panes-external-viewer/*` (`NR.md`, `VE.md`, `VM.md`, `VM2.md`, `VX.md`, `IB.md`, `PL.md`, `TR.md`, `CX3.md`, `CX4.md`, `CX5.md`, …) | § 2026-09-06 — Native panes, external viewer, and `docs/requirements/2026-09-06-native-panes-external-viewer.md` |
| `dev/spikes/native/*/REPORT.md` and all spike code | `../spikes/README.md` |
