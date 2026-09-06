# Lane S1 — API smoke harness (Level A) — working notes

Program: `dev/notes/v3-pipelines-program.md` §3, decisions **P4–P8**. Worktree
`.claude/worktrees/v3-electron-gui`, branch `feature/v3-electron-gui`. Nothing committed.

Shared dev container: `ti-toolbox-fad740e5-tit-1`, `http://127.0.0.1:8765`, project
`/Users/idohaber/datasets/000` at `/mnt/000`, worktree at `/ti-toolbox`.

## What was built

| Path | What it is |
|---|---|
| `tests/smoke/matrix.py` | 21 rows, one per kind of §3: subject + a "why this subject" sentence, config builder, behaviour, budget, banner patterns, claimed paths, catalog check |
| `tests/smoke/client.py` | stdlib-`urllib` client (bearer auth — a cookie would be CSRF-checked, `tit/server/auth.py`), state/banner polling, `runner_pids_for` |
| `tests/smoke/cleanup.py` | created-path manifest: `claim` (records pre-existence), `claim_produced` (a file this run wrote into a shared directory, mtime-checked), `remove_created` |
| `tests/smoke/conftest.py` | env gate (`TIT_SMOKE_SERVER_URL` + `TIT_SMOKE_TOKEN`), session fixtures, `--smoke-kinds/--smoke-keep/--smoke-full`, results table writer |
| `tests/smoke/test_kinds.py` | the parametrized behaviour test + the payload loader (recorded UI body wins over the built-in config) |
| `tests/smoke/test_harness_selftest.py` | 58 unit tests of the harness itself; **not** marked `smoke`, runs in the default host suite |
| `tests/smoke/payloads/README.md` | contract for lane S2's recorded `POST` bodies |
| `tests/smoke/README.md` | how to run it, the behaviour contract, why it never runs by accident |
| `dev/smoke.sh` | label-based container discovery (`tit.stack=ti-toolbox-v3`), port/token/project from `docker inspect`, exit 0/1/2 |
| `pytest.ini` | registers the `smoke` marker and deselects it by default |

Fixes to runner/server code (each with its own unit test) are in "Bugs found and fixed" below.

## Numbers

| Measurement | Value |
|---|---|
| Host suite before this lane | 3159 passed, 18 skipped, **34.72 s** |
| Host suite after (smoke deselected) | 3224 passed, 18 skipped, **22 deselected**, **34.80 s** |
| Smoke tests run in the default suite | **0** (22 deselected: 21 rows + parametrized coverage) |
| Harness self-tests (in the default suite) | 58 passed in **0.09 s** |
| Matrix rows | 21 |
| Container restarts by this lane | **2** (`tit/server/routes/validate.py`; `tit/sim/config.py`) |
| Matrix run of record | **21 passed, 0 failed, 0 skipped** in 280.7 s; a second full run 6 min later also 21/21 |
| Rows replayed from lane S2's recorded UI payloads | 9 of 21 |
| Paths left on the dataset after the run | **0** |

## Real runs

The results table of record is `dev/notes/v3-pipelines/2026-09-03-smoke.md` (21/21 green, every
job id, wall time and banner). Intermediate runs (each one a bug found and fixed) are in
`tests/smoke/artifacts/results-*.md` with their manifests beside them.

Container restarts, both with `GET /api/jobs` showing nothing running or queued first, healthy
again after 2 s each:

| # | Why | Time |
|---|---|---|
| 1 | `tit/server/routes/validate.py` — envelope-key fix (server module, not picked up by the bind mount) | 23:11 UTC |
| 2 | `tit/sim/config.py` — the server had the old module cached for `/api/validate/sim` | 23:33 UTC |

## Bugs found and fixed (with a unit test each)

1. **`project_init` jobs could never run.** `tit/jobs/kinds.py` maps the kind to `tit.project_init`,
   a package with no `__main__`, so every job died at exec with *"'tit.project_init' is a package
   and cannot be directly executed"* (job `5d0c6180a8004f49`, 2026-08-27). `kinds.module_exists()`
   only checks the package imports, which it always did.
   *Fix:* added `tit/project_init/__main__.py` (the same thin JSON-config runner shape as
   `tit/opt/leadfield_runner.py`). *Test:* `tests/test_project_init_runner.py` (6 tests, incl.
   `importlib.util.find_spec("tit.project_init.__main__")`).
   *Verified:* row `project_init` succeeded in 0.0 s (job `f1e73bdbd5b0458e`).

2. **`POST /api/validate/{kind}` rejected the body the UI actually submits.** The route
   deserialized with `strict=True` on the raw config, so `project_dir` — which
   `tit.jobs.manager._runner_config_path` injects into every runner config, which every runner's
   `__main__` pops, and which `tit.config_io.deserialize_config` documents by name as ignorable —
   came back as `PreprocessConfig: unknown key(s) ['project_dir']`. The same config was accepted
   by `POST /api/jobs/groups` and ran to success. The maintainer's own succeeded job
   `d0036f3cad7b4be9` carries `project_dir` in `spec.config`.
   *Fix:* `ENVELOPE_KEYS = {"project_dir"}` stripped in `tit/server/routes/validate.py` before the
   strict deserialize (not in `deserialize_config`, so nested dataclasses stay strict).
   *Test:* `tests/test_validate_envelope_keys.py` (7 tests, incl. "a genuinely unknown key is
   still reported").
   *Verified:* `POST /api/validate/pre` → `{"ok":true,"errors":[]}` after **container restart #1**
   (no jobs running/queued at the time; healthy again after 2 s).

## Harness bugs found in its own first runs (fixed here)

- Analyzer `output_dir` outside `Analyses/{Mesh,Voxel}/` is invisible to
  `GET /api/catalog/analyses` (`tit/catalog.py:840` only scans those two). The row now writes
  under `Analyses/<Space>/smoke-…`. *This is also a product finding — see open issues.*
- A path created by an earlier row of the same session looked "pre-existing" to a later row
  (`derivatives/SimNIBS/sub-102`, scaffolded by the DICOM stage, was claimed by `pre_charm` and
  therefore never deleted). Claims are idempotent per path and the first claim wins, so
  `pre_dicom` now claims it.
- A `pre` group's **G1** stage writes its own `pre_processing_report_*.html` beside the trailing
  report job's; only the row's own job's artifacts were being claimed, so one report per run was
  left in `derivatives/ti-toolbox/reports/sub-102/`. Every job of the submission is now swept.
- The P6 "plan must report `exists: false`" assertion is meaningless for `pre`, whose plan is one
  job per *stage* and whose stage directories are shared by construction
  (`tit/server/routes/plan.py`'s own docstring says so). It is now applied only to the paths the
  row itself claims.

## Further harness bugs found by its own runs (all fixed)

- The 10 s `accepted` budget was measuring the **politeness wait** as well: `_wait_no_heavy_job`
  blocks on another lane's job finishing on the shared container, which produced a 42.2 s
  "accepted leg". The clock now stops before the wait and resumes for the submit only.
- The `payloads/<kind>.json` fallback was too coarse. `sim_ti` and `sim_mti` both replayed one
  `sim.json`, so the second job died on SimNIBS's *"Found already existing simulation results in
  directory"* (job `caad925a2e9c4142`); one recorded `pre.json` (a tissue-analysis group) made
  every `pre` row look for a stage tag that group does not contain. The fallback now applies only
  to the first row of a kind and never to a row that selects its job by stage tag; an exact
  `<row id>.json` always wins.
- A payload run writes where *its own* config says, so the row's `expect_files`, catalog check
  and claimed paths were asking about the built-in config's outputs. Payload rows now claim (and
  check) the `output_dir`s the plan reports, and the catalog check is skipped with a note.

## Cross-lane collisions observed

- Two containers carry `tit.stack=ti-toolbox-v3` on this machine (D0's scratch project on 8781
  and the shared one on 8765). `dev/smoke.sh` refuses to guess and asks for `TIT_SMOKE_CONTAINER`
  or `TIT_SMOKE_PROJECT_HOST`; the shared-container runs in this note all set the latter.
- A `source` job submitted from the UI left an empty
  `derivatives/SimNIBS/sub-101/forward/` behind, which made the `source` row skip
  ("recorded payload targets existing output"; P6 working as designed). Removed by hand — it
  was empty and absent from the dataset this morning.
- `payloads/stats.json` carries a fixed `analysis_name`; each time it was rewritten with a new
  id my replay created that directory, and three `smoke-ui-*` group_comparison directories
  accumulated before the plan-claiming fix. Removed by hand.

## Requests to other lanes

- **S2 (already working — 9 of 21 rows replayed your payloads in the run of record):**
  keep writing `tests/smoke/payloads/<row id>.json` (`sim_ti`, `sim_mti`, `pre_dicom`, `flex`,
  `analyzer_mesh`, `analyzer_voxel`, …); the hyphenated spelling (`analyzer-voxel.json`) is
  accepted too. The bare `<kind>.json` fallback now applies **only** to the first row of a kind
  and never to a `pre` row (one recorded `pre.json` encodes one stage combination, and one
  `sim.json` replayed by both sim rows made the second job collide with the first's output
  directory). A `pre` payload therefore needs the row-id filename to be used at all.
- **S2:** a payload that names a fixed output (`stats.json`'s `analysis_name`,
  `analyzer.json`'s derived sphere directory) makes the **second** replay hit an existing
  output, and the row then skips rather than overwrite it (P6). If a row should keep running,
  re-record it with a fresh `smoke-…` name, or leave it — the skip is reported in the table with
  its reason.
- **F0:** both of your kinds are green from this side. `flex` starts on the list-form
  `atlas_path` (`Setting up headmodel` at 3.0 s, job `33e77bfc0c8f479d`) and the trailing
  `report` job completes with its HTML artifact (job `c049e795465d4258`).
- **D0:** `GET /api/project` returns `host_path: null`, so `dev/smoke.sh` has to read
  `tit.host_project_dir` off the container to map `/mnt/000` onto the host. If the server can
  fill that in, the harness (and any client showing a path to a user) stops needing `docker`.


## Third fix: the sim intensity rule the UI could not see

`POST /api/validate/sim` answered `{"ok": true}` for a 4-pair mTI montage with the default
`intensities=[1, 1]`; the job then died one second later with
`ValueError: Montage 'smoke-182517-mti' requires 4 current intensities; got 2.`
(job `cdf272b6556c43fa`). The rule lived only in `tit.sim.utils._validate_simulation_inputs`,
which runs inside the job, and `/api/validate` can only report what the config dataclass raises.

*Fix:* the two rules that need nothing but the config (pair length = 2; one intensity per pair
for mTI) moved into `SimulationConfig.__post_init__`; everything that needs the filesystem (the
`m2m` directory, the EEG-net CSV) stays in `utils`, which is why this is a split, not a move.
A pair count `Montage.simulation_mode` cannot classify (1 or 3) is deliberately left exactly as
it was — deciding it here would make configs existing callers and tests build on purpose
unconstructable (two tests proved that on the first attempt).
*Test:* `tests/test_sim_config_cross_field_rules.py` (7 tests, including the same body through
the route the UI calls).
*Verified:* row `sim_mti` reached `mTI: smoke-…` at 2.0 s and cancelled cleanly.

## Verified, not assumed

- `python3 -m pytest -m smoke tests/smoke` with the gate unset: **21 skipped in 0.04 s**, each
  printing `skipping: pipeline smoke harness needs TIT_SMOKE_SERVER_URL and TIT_SMOKE_TOKEN …`.
- `TIT_SMOKE_CONTAINER=nonexistent dev/smoke.sh` → `smoke: cannot check -- …`, **exit 2**.
  (Found the hard way: the variable was honoured only when several stacks were up, so naming a
  missing container silently ran the whole matrix against the shared one. Fixed.)
- After the run of record, `find /Users/idohaber/datasets/000 -name "smoke-*"` outside
  `code/ti-toolbox/jobs/` returns nothing, and `sub-102`, `derivatives/SimNIBS/sub-102`,
  `derivatives/fastsurfer/sub-102`, `tissue_analysis/sub-MNI152` and `sub-101/forward` are all
  gone. `m2m_101`, `m2m_ernie`, `m2m_MNI152` were never written.
