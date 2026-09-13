# Testing strategy and evidence

[CONTRIBUTING](../../CONTRIBUTING.md) owns setup and workflow; [ARCHITECTURE](ARCHITECTURE.md)
owns behavior, [BENCHMARKS](BENCHMARKS.md) performance, and [ROADMAP](ROADMAP.md) remaining
acceptance work. This file owns test layers, fixtures, commands and verification limits.

## Strategy

Run the smallest meaningful regression checks during implementation and the full gate for a release
candidate. A full gate includes desktop static/unit tests, host Python, real-library numerical tests,
repository guards, hidden mock e2e, relevant real-container workflows and a final normal build.
Workflow or packaging changes add their specialized checks. Report numbers, skips and unrun legs;
a local success does not establish hosted CI, security review or artifact acceptance.

| Layer | What it proves | What it cannot prove |
|---|---|---|
| Desktop units and static checks | UI/state logic, types, lint | Actual drawing, native shell or scientific execution |
| Host pytest | API, jobs, config, path logic with controlled fixtures | SimNIBS and other mocked library behavior |
| Container numerical tests | Independent numerical claims against real libraries | A complete production workflow unless explicitly executed |
| Mock Electron e2e | Integrated UI requests, layout/pixels, interaction | Real server/scientific outputs |
| Real e2e and smoke matrix | Actual container/API jobs and produced artifacts | Other datasets/platforms, or completion when only start/cancel ran |
| Packaged acceptance | Runtime assets and actual installer launch | A different source/image/package pairing |

## Launcher lifecycle checks

`tests/test_launch_image.py`, `test_loader_interactive.py`, `test_bash_loader_lifecycle.py`
and `test_electron_loader_handoff.py` use synthetic Docker records and recording executables.
They pin explicit cross-project selection, cancellation without mutation, replacement preflight,
and CLI-to-Electron environment handoff. Desktop `stack-image-attach`, `dev-stack-start` and
`quitPlan` unit suites cover the matching Engine API and shutdown rules, including explicit
stop/quit confirmation when job status is unavailable and preservation after cancellation or stop failure. `launcher.test.ts`
covers typed/picked paths, inline destination cancellation, duplicate-start prevention and failed
starts. `dev-entry.test.ts` pins build-before-Electron, optional defaults and failure propagation.

`desktop/tests/e2e/launcher.spec.ts` runs the built Electron app against a fake Docker Engine
socket: it checks session choice, CLI startup and clearing its one-shot selection, window-close stop/remove, the disconnected navigation
and absence of backend requests, direct cross-project switching, and preservation of the old session
when a destination is invalid or confirmation is cancelled. Run it under the
same offscreen lock and quiet wrapper described below. These tests do not validate installed
executables against a real Docker engine; packaged host acceptance remains in the roadmap.

## Commands

Run from the repository root unless a command says otherwise. Use the host environment installed
by CONTRIBUTING. `tests/conftest.py` mocks SimNIBS, Blender and several scientific/plotting packages;
NumPy is real and some tests restore SciPy. Never infer real-library success from a host run.

```bash
.venv/bin/python -m pytest tests/ -q
cd desktop
npm run typecheck
npm run lint
npx vitest run
```

In an existing development/test container with this checkout mounted:

```bash
docker exec -w /ti-toolbox <container> simnibs_python -m pytest tests/numerical -q
```

`tests/numerical/conftest.py` restores real libraries and reloads tested modules. Changes to the
scientific core require independent numerical coverage; use authored fixtures/reference calculations,
not expected values copied from the implementation. A real-library test with stubbed FEM is an
interface test, not a completed simulation. Published-output changes also need release-note guidance.

Repository guards:

```bash
python3 dev/route_import_guard.py
python3 dev/contracts_check.py
```

The import guard prevents heavy scientific imports during route registration. The contract guard
regenerates outputs in a temporary directory and checks byte drift against the authored contract.
Fix drift with `cd desktop && npm run gen`; never hand-edit generated output. Contract warnings
must be reported rather than counted as zero.

### Hidden end-to-end tests

Serialize every Playwright run under the shared `/tmp/tit-e2e.lock` and coordinate build ownership;
its mock server port and `desktop/out/` are shared. Do not start another build/test workload beside
measurement-sensitive GUI tests. The quiet-check wrapper monitors visibility; the caller must still
coordinate the shared lock. Never kill all Playwright processes to recover one run.

```bash
cd desktop
TIT_E2E_OFFSCREEN=1 npm run e2e:quiet
```

For a selected real spec against an existing container, set the copied dataset, server and session
credentials in the process environment (never commit or print the token):

```bash
TIT_E2E_PROJECT_HOST=/absolute/path/to/copied/project \
TIT_E2E_SERVER_URL=http://127.0.0.1:8765 TIT_E2E_TOKEN=<token> TIT_E2E_OFFSCREEN=1 \
  bash scripts/e2e-quiet-check.sh npx playwright test --project=real tests/e2e/real/<spec>.spec.ts
```

Use `--project=real`: the space form can consume the spec path as another project. Do not use
`npm run e2e` for real-server runs, because its prehook rebuilds the shared output. Build scene
hooks before scene specs (`npm run pree2e` includes both gallery and scene hooks); a narrower real
scene build can use `VITE_SCENE_HOOKS=1 npx electron-vite build`. Gallery tests also need
`VITE_INCLUDE_GALLERY=1`. `electron-vite build --mode` does not make `import.meta.env.DEV` true.
Restore `npm run build` after tests so the shared server no longer serves the hook-enabled bundle.

A quiet monitor exit 2 is inconclusive, not a pass. Keep functional assertions and native
visibility/focus certification separate. Do not rerun solely to replace unresolved shared-host
process attribution with a more convenient result.

### Real-container smoke tests

Use a copied representative BIDS project; never substitute a maintainer dataset for destructive
fixtures. [dev/smoke.sh](../../dev/smoke.sh) drives `tests/smoke/` through HTTP:

```bash
dev/smoke.sh --list
dev/smoke.sh <row-id-or-kind>
dev/smoke.sh
dev/smoke.sh --full <row>
```

Select `TIT_SMOKE_CONTAINER` when multiple stacks exist. Heavy rows wait for an idle queue; never
run competing FEM jobs under emulation. Fresh output namespaces and cleanup manifests live under
`tests/smoke/artifacts/`; `--keep` preserves generated artifacts. State whether each check completed
computation or only tested start/cancel. Real UI specs can record payloads for replay.

Before restarting a backend, inspect running/queued jobs. After reload, wait for health and probe
behavior proving the new source loaded; immediate health may still come from the old process.
Recreating changes the token. Neither restart nor recreation is safe for active jobs by default.

### Workflows, packages and final build

```bash
actionlint                                  # when workflows change
cd desktop && npm run verify:package        # after creating the package under test
cd desktop && npm run build                 # final frontend step
```

Artifact construction and signed/internal publication are in [RELEASING](RELEASING.md). A package
validator checks bundled content; actual first-launch acceptance must use the distributed pairing
without source/UI mounts. A later source fix invalidates claims based only on an earlier image.

## Fixtures and failure diagnosis

- Use deterministic synthetic fixtures and assert observable behavior. Real paths and symlinks need
  Linux/container checks; case-insensitive host results are insufficient.
- Use `tests/numerical/` for real SciPy/SimNIBS claims. Full scientific jobs use the smoke harness or
  real e2e with a copied project; numerical unit success is not equivalent to a completed FEM run.
- `tests/test_blender_process_boundary.py` enables real Blender through `TIT_TEST_BLENDER_BIN`.
  Report its skip when the executable is unavailable. Validate export and reopen separately from
  scientific-environment imports.
- An isolated `tests/test_scene_guide.py` pass diagnoses order-dependent state leakage; it never
  waives a failed full suite. Scope mock changes so subsequent tests restore real module state.
- `docs-shots.spec.ts` rewrites tracked screenshots. Use it only when that output is intended;
  review generated changes rather than treating a passing capture as permission to replace images.
- Existing seeded project notebooks do not automatically update when the template changes. Use a
  fresh fixture or deliberately migrate the example when testing a repaired template.
- The older [test-script reference](../../tests/README_TESTING.md) documents shell runner options;
  it does not replace these desktop, numerical and artifact acceptance layers.

## Current verification and remaining gaps — 2026-09-09

Receipts live under ignored `dist/internal/` and `/tmp`; they may expire. The committed suites
above are the reproduction surface. A source test does not certify a later image rebuild.

| Scoped check | Result |
|---|---|
| Host Python suite | 4,825 passed, 48 skipped, 21 deselected; `/tmp/tit-rebuild-host-full.log` |
| Desktop units | 1,601 passed; `/tmp/tit-rebuild-desktop-tests.log` |
| Scene interactions | Seven mock e2e passed, including first Analyzer atlas pick and toggle |
| Subject net rendering | Subject 101/BioSemi-128: real GPU electrode selection/color check passed; native quiet monitor passed with nine samples |
| Backend route and contract guards | 24 route modules; 114 operations / 136 schemas; 244 existing contract warnings |
| Prior internal image | Source `3f2af30c`: 355 baked numerical/backend/Blender tests, 83 loader/packaging tests and clean Python/Bash launcher acceptance passed |

The first internal upload resolved to
`sha256:4f62a4a9c71ef440d3b3428707eaa71bada486d78a8eed57f5c74449181aa409`.
The maintainer requested rebuilding the same `internal-20260909.1` tag after the scene fixes;
use each rebuild's registry digest and embedded source SHA, not the tag alone, as its identity.
The image receipt is `dist/internal/image-internal-20260909.1-receipt.json`.

The seven-test mock run's native monitor exited 2 (unresolved process attribution), so its
windowlessness measurement is inconclusive despite passing behavior tests. The real net check's
monitor passed. Host numerical mocks and skips do not replace container checks; the overwrite
regression stubs FEM and does not prove a complete simulation. Final installer/platform,
hosted security and manual acceptance remain in [ROADMAP](ROADMAP.md).

### Native FastSurfer acceptance

`npx vitest run src/main/fastsurferWorker.test.ts src/main/fastsurferInstall.test.ts tests/unit/native-fastsurfer-ui.test.tsx` covers the installer digest gate, UI states, real macOS sandbox restrictions, fixed arguments, cancellation and lost leases. macOS-only cases skip on other hosts.

The opt-in `desktop/scripts/test-native-fastsurfer.mjs` uses a hidden Electron window and the actual mounted Docker project. Set `TIT_NATIVE_TEST_PROJECT`, `TIT_NATIVE_TEST_CONTAINER` and a new alphanumeric `TIT_NATIVE_TEST_SUBJECT`; run under the shared e2e lock. It copies subject 101's T1 (or `TIT_NATIVE_TEST_INPUT`) to the new test subject, exercises consent responses, submits a real preprocessing job and checks standard outputs. The native dialog response is supplied by the test harness under maintainer authorization. Test inputs, job records and outputs are retained for inspection. This test performs a full segmentation and must not run alongside another heavy job.

Verified on 2026-09-10: 20 focused desktop tests and 54 backend tests passed (one upstream-checkout test skipped); typecheck, lint and production build passed. Lint retained three existing React Compiler warnings. A hidden Electron install/consent and real Docker-to-Metal completion run passed; measured fixture and output checks are in [BENCHMARKS](BENCHMARKS.md#native-apple-silicon-fastsurfer-acceptance--2026-09-10).

### GPU-preferred container acceptance

Run `python3 -m pytest tests/test_launch_gpu.py tests/test_launch.py tests/test_bash_loader_lifecycle.py tests/test_pre_fastsurfer.py tests/test_native_fastsurfer.py -q` for launcher and job selection. Desktop GPU probe cases are in `src/main/docker/gpu.test.ts`. The image's `verify_runtime.py` rejects CPU-only PyTorch and validates the scientific ABI. A build-time CUDA version assertion proves packaging only: an NVIDIA host must also run the same-image launcher probe and a real FastSurfer job to prove GPU execution. Apple Silicon validates the unavailable-CUDA and native fallback routes.


## EEG consolidation

Independent small-array tests are in `tests/numerical/test_eeg_array_stats.py`, `test_eeg_fields.py`, and `test_eeg_source.py`. Run them with a real NumPy/SciPy/MNE stack:

```sh
python -m pytest tests/numerical/test_eeg_array_stats.py tests/numerical/test_eeg_fields.py tests/numerical/test_eeg_source.py -q
```

The source tests isolate MNE from host-suite mocks in a subprocess; `TIT_EEG_TEST_PYTHON` selects a compatible real-MNE interpreter. They compare actual MNE operations, authored array/graph expectations and exhaustive or independently generated permutation cases. Downstream snapshot parity reads the pre-migration Git tag rather than distributing private source snapshots.

Native macOS checks do not establish Linux container path behavior. The installed SimNIBS 4.6 interpreter currently combines MNE 1.5 with NumPy 2; some MNE covariance/coregistration paths fail in that combination. The source numerical leg passes with the study's real MNE 1.12.1 interpreter. No participant-data or FEM rerun is claimed; the study drive was unavailable during extraction. The synthetic notebook demonstrates API execution only.

2026-09-13 branch verification: 4,886 host tests passed, 48 environment-dependent
skips; 40 EEG numerical/parity tests passed with both study tags supplied.
The route import guard passed all 27 routes, and contracts_check passed with
247 existing schema warnings. These counts cover the extraction on this branch;
they do not establish hosted CI or a new container image.

CircleCI desktop run 985 exposed a pre-existing stale atlas-target assertion:
the unchanged optimizer returns the declared `atlas_space`, but the fixture
omitted it. The failure reproduced locally on the identical baseline desktop
tree. After correcting that assertion, all 1,739 desktop unit tests passed
locally (146 files). This is a test-only correction; the pinned scientific
implementation remains commit `2124ba401ba93badaafce57bacfaff5138306436`.
