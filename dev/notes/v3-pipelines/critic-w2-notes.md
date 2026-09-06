# Critic pass (CR) — Workflow 2, after the fix-lane barrier (2026-09-04)

Read-only: fixes nothing, edits no source file. Ran only the commands the runbook
(`dev/notes/v3-pipelines/RUNBOOK.md`) documents, in the worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed, staged,
or stashed. Shared container: `ti-toolbox-fad740e5-tit-1`, `http://127.0.0.1:8765`, token
`devtoken`. Every Electron/Playwright run went through `TIT_E2E_OFFSCREEN=1` and
`desktop/scripts/e2e-quiet-check.sh`; the maintainer's own `npm run dev:web` on `127.0.0.1:5173`
and its Electron window (already on screen before every run started) were never touched — the
quiet-check's own before/after windows-list confirms this on every invocation (the maintainer's
window listed as a pre-existing note, not a violation).

## 0. Pre-flight

`GET /api/jobs` on the shared container: 240 jobs total, **0 running/queued** before starting.
`dev/smoke.sh --list`: one container, `ti-toolbox-fad740e5-tit-1 port=8765
project=/Users/idohaber/datasets/000` — matches the runbook exactly.

## 1. Level A — `dev/smoke.sh` (whole matrix, no selector)

```
smoke: container f17995acd796 -> http://127.0.0.1:8765, project /Users/idohaber/datasets/000
collected 89 items / 68 deselected / 21 selected
tests/smoke/test_kinds.py ..F..................                          [100%]
1 failed, 20 passed, 68 deselected in 248.64s (0:04:08)
```

**20/21 green, 1 failed: `pre_fastsurfer`.** The row is `started_then_cancel` (started, then
cancel, assert `cancelled`); the FastSurfer runner itself failed (`exited with code 2`,
`Preprocessing failed: FastSurfer failed for subject 102 (exit 1)`) 0.0s after the cancel was
issued — the runner lost the race and reached `failed` before the cancel landed, so the row's
assertion `status["state"] == "cancelled"` saw `'failed'` instead. **Root cause, from the job's own
log**: `run_fastsurfer.sh` refuses to run as root —
`ERROR: You are trying to run 'run_fastsurfer.sh' as root. ... If you want to force running as
root, you may pass --allow_root to run_fastsurfer.sh.` — and the runner does not pass
`--allow_root` (nor `-u $(id -u):$(id -g)`), so every FastSurfer job on this container fails
outright, independent of cancel timing; the cancel race is incidental, not the bug. Not a harness
or cancel-path bug — the banner (`^FastSurfer`) fired correctly at 4.1s, the underlying tool just
refuses to start as this container's (root) user. Not one of Workflow 2's known findings
(F0/FX1-5); new since the last full run of record. Cleanup:
manifest shows the row's own claim `derivatives/fastsurfer/sub-102` noted `never created` (nothing
to remove) — **0 net paths left on disk** across the whole run
(`tests/smoke/artifacts/manifest-20260904T021230Z-210821.json`, every non-pre-existing claim is
either `removed: true` or `never created`). `GET /api/jobs` and `GET /api/system` both clean
(0 running/queued, 0 processes) after the run.

Results table of record: `tests/smoke/artifacts/results-20260904T021230Z-210821.md`.

## 2. Level B — real Playwright project

`cd desktop && npm run build`: succeeded, 1.9s render build (`out/` was not stale — no `src/`
file was newer than `out/renderer/index.html` before the build; ran it anyway per the task).

```
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=devtoken TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real --workers=1
```

(the runbook's per-spec form uses the same `--project=real`; run here against the whole
`tests/e2e/real` project, no spec path, workers 1 — 12 spec files, 14 tests: `ex.spec.ts` and
`preprocess.spec.ts` each hold 2). `--project real` (space, no `=`) was **not** tried — the
runbook and HX's notes already document that form failing on this Playwright version, so it was
avoided as instructed ("do not improvise a replacement beyond what \[...\] also document").

Quiet-check: **PASS** — frontmost app unchanged (`ghostty`) start to finish, no window from
Electron/Chromium/TI-Toolbox appeared during the run; the maintainer's own pre-existing Electron
window (`title=TI-Toolbox`, on screen before this run started) is listed as a note, correctly
ignored per the quiet-check's own documented behaviour.

**14/14 real specs green, 14.5m total wall time.** `source.spec.ts` alone is 9.7m (flagged by
Playwright itself as "Slow test file") — the real MNE/SimNIBS point-electrode leadfield for a
75-electrode net (`EEG10-10_UI_Jurak_2007`), ~5.8s/electrode, genuinely takes that long; watched
it complete live (`Running Simulation 75 of 75` → `✓ sub-101_net-...-fwd.fif, ...-src.fif,
...-morph.h5` → `✓ Source pipeline complete.`), well inside its own `test.setTimeout(700_000)`.
See `results_table_md` for the per-spec table (job id, time-to-running, outcome).

Post-run sweep: `find /Users/idohaber/datasets/000 -iname "*smoke*"` (outside
`code/ti-toolbox/jobs/`) — **empty**; `sub-101/forward/` and `sub-102/` (both real, non-smoke-
tagged outputs the specs create) were removed by their own `afterAll` cleanup, verified gone;
`GET /api/jobs` 0 running/queued and `GET /api/system` 0 processes after the whole project
finished.

### Level B results table

| spec | job id | time to running | outcome | first error line |
|---|---|---|---|---|
| analyzer-mesh | `2fbffc0de7f54588` | 0.12s | succeeded, 5 artifacts, 9.0s test | — |
| analyzer-voxel | `2d15ee84b5a64df4` | 0.20s | succeeded, 4 artifacts, 9.1s test | — |
| cluster-permutation | `a051929c135347ab` | 0.08s | succeeded, 8 artifacts, 7.1s test | — |
| ex (subcortical ROI, bucketed electrodes) | `61d1597004dc4de6` | 0.12s | succeeded, 2 artifacts, 31.8s test | — |
| ex (second-subject plan/block-by-name) | — (no job; plan-only assertion) | — | passed, 0.8s test | — |
| flex (DK40 bankssts, list-form ROI) | `88e749171f8e42ca` | 0.24s | started, cancelled cleanly, 3.0s test | — |
| mex | `7886d88b92904f79` | 0.23s | succeeded, 2 artifacts, 44.1s test | — |
| nifti-group-average | `55d10ff3c5cc4958` | 0.03s | succeeded, 2 artifacts, 7.0s test | — |
| nilearn-visuals | `ecdce9a1c46e4289` | 0.23s | succeeded, 4 artifacts, 16.2s test | — |
| preprocess (tissue analysis, sub-101) | `a5998746028d4ec2` | 0.03s | succeeded, 1 artifact, 1.2m test | — |
| preprocess (sub-102 DICOM onboarding, FX5) | `787f363c01084c5d` | 0.17s | succeeded, 1 artifact, 22.1s test | — |
| sim-mti | `5b293b5854c14aff` | 0.19s | started, cancelled cleanly, 6.0s test | — |
| sim (TI) | `ff6f15b67de24639` | 0.26s | started, cancelled cleanly, 5.3s test | — |
| source (forward solution, sub-101) | `ecbf1f9637ee4d4b` | 0.12s | succeeded, 3 artifacts, 9.7m test (real ~9.7m FEM+MNE compute) | — |

**14/14 passed, 0 failed.** Playwright summary: `14 passed (14.5m)`.

## 3. Gates

| Gate | Result |
|---|---|
| Host `python3 -m pytest -q` | **3354 passed, 18 skipped, 21 deselected, 36.77s** — green (smoke deselected by default) |
| `desktop`: `npm run typecheck` | clean, 0 errors |
| `desktop`: `npm run lint` | **0 errors**, 3 pre-existing warnings (React Compiler "incompatible library" notes on `react-hook-form`/`useReactTable`/`useVirtualizer`, unrelated to this pass) |
| `desktop`: `npx vitest run` | **716 passed (716)**, 61 test files |
| `desktop`: `npm run build` | succeeded (ran once, per task instruction) |

## 4. Container restarts

**0.** Nothing under `tit/server/**`, `tit/jobs/**` or `tit/catalog.py` was touched by this pass
(read-only). No restart was ever needed or issued.

## 5. Open issues

1. **Level A row `pre_fastsurfer` FAILED** (not cancelled/green) — see §1. FastSurfer refuses to
   run as root inside the container (`ERROR: You are trying to run 'run_fastsurfer.sh' as root.
   ... pass --allow_root to run_fastsurfer.sh.`) and the runner passes neither `--allow_root` nor
   a non-root `-u`, so it exits 1 on every invocation, independent of cancel timing. Kind:
   `pre` (FastSurfer stage). Symptom for the harness: cancel raced the failure and saw `'failed'`
   instead of `'cancelled'`, but the underlying bug is that the stage cannot succeed at all on
   this container. Suggested owner: whoever owns `tit/pre/**` FastSurfer integration (FX3/FX5's
   territory) or the container entrypoint/Dockerfile (FastSurfer should run as a non-root user, or
   the runner should pass `--allow_root`) — first error line:
   `runner_failed: exited with code 2 | ['Preprocessing failed: FastSurfer failed for subject 102
   (exit 1).']`, job `2436e095f58141ae`; full job log on the container at
   `/mnt/000/code/ti-toolbox/jobs/2436e095f58141ae/stdout.log` (host path
   `/Users/idohaber/datasets/000/code/ti-toolbox/jobs/2436e095f58141ae/stdout.log`), not copied
   into `tests/smoke/artifacts/` (that directory only holds this pass's results/manifest files).

No runbook command failed to behave as documented in this pass: `dev/smoke.sh --list`/bare run,
`npm run build`, and `--project=real` all matched the runbook's own description exactly.
