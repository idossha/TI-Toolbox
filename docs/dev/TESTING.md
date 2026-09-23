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

## Daily CI and the local release gate

CircleCI keeps the existing required check names. `build-and-run-tests` runs the **entire host
Python suite**, coverage, documentation/build self-tests, route guard and contract guard in a
Python 3.11 VM environment. It excludes `tests/numerical` explicitly. `desktop-checks` runs all
TypeScript checks, lint, Vitest units and a normal production build. Browser installation,
Electron E2E and scientific-image pulls are absent from the ordinary workflow. Coverage is host
coverage, not proof of real scientific execution. Image verification remains an explicit
`build_image` pipeline choice.

Before an official release, run the existing full layers through the serial local entry point:

```bash
# First export TIT_E2E_PROJECT_HOST, TIT_E2E_SERVER_URL and TIT_E2E_TOKEN for a copied project.
# Use a clean committed candidate, installed host/desktop dependencies and an existing dev stack.
.venv/bin/python dev/verify_release.py \
  --image idossha/ti-toolbox:<candidate> --container <existing-copied-project-container> \
  --notebook-project /absolute/path/to/disposable-notebook-project \
  --package /absolute/path/to/TI-Toolbox.app \
  --real-spec tests/e2e/real/<applicable>.spec.ts \
  --smoke-row <applicable-row> --out /tmp/tit-release-evidence-<candidate>
```

Repeat `--real-spec` and `--smoke-row` for every workflow affected by the release. A major release
requires the applicable matrix, not a token smoke row. Smoke rows use `--full` (completion, not
start/cancel); the notebook adds a real flex search, FEM solve and analysis. The wrapper holds
`/tmp/tit-e2e.lock`, runs each stage serially, runs numerical tests in a fresh real-image Python
process, verifies the supplied package, and restores a normal build last even after a failed
stage. Coordinate all other heavy jobs before invocation; this E2E lock cannot stop a separately
launched FEM job. The quiet monitor currently requires macOS, and an inconclusive exit 2 fails.

The new output directory stores per-stage logs and `receipt.json` with the source SHA, immutable
local image ID, inspected container ID/image/mounts, selected real specs/rows and actual stage exit
codes (including failures). Numerical and notebook commands use the immutable inspected image ID.
The real-test container must mount this checkout at `/ti-toolbox`; this source-mounted acceptance
is distinct from a baked-image or installed-package acceptance run. A changed/dirty source
or any failed stage prevents a passed receipt. Review skips in the logs explicitly: a zero exit
with optional tests skipped does not certify missing hardware/data. The receipt certifies only its
selected stages and package; verify the dev stack's mounts/source and image pairing, retain native
installer first-launch/platform evidence, and run workflow-specific checks from the sections below.
It is a local operator gate, not a hosted publication interlock. Never publish solely because daily
CI is green. `tests/test_release_gate.py` verifies that failures, inconclusive monitor exits and empty
pytest collections remain failures and their logs survive.

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

## Automatic FreeSurfer licensing

`tests/test_freesurfer_license.py` covers clean-install bundled resolution, optional override
precedence and license-independent FastSurfer segmentation. Worker-command tests in
`tests/test_pre_freesurfer.py` and `tests/test_pre_qsi_docker.py` check license staging and host
mount paths. Run these with `tests/test_surfer_settings.py` after changing provisioning.
`tests/test_apptainer_license.py` checks default image-license provisioning and executed
Apptainer/Slurm arguments, including optional overrides. It does not build an Apptainer image.
These host checks do not prove that a built image or wheel contains the resource: inspect the
package and resolve the bundled file in the real container before claiming packaged acceptance.
Never print the license contents in test failures or verification logs.

## Commands

Run from the repository root unless a command says otherwise. Use the host environment installed
by CONTRIBUTING. `tests/conftest.py` mocks SimNIBS, Blender and several scientific/plotting packages;
NumPy is real and some tests restore SciPy. Never infer real-library success from a host run.

The combined container runner `tests/run_tests.sh` adds PETSc's `-no_signal_handler` option before
Python starts, preserving other options. Otherwise real-library imports can replace Python's
SIGPIPE handling and abort subprocess tests (CircleCI #1048). `test_container_test_runner.py`
checks the executed runner's environment and argument forwarding.

```bash
.venv/bin/python -m pytest tests/ -q --ignore=tests/numerical
cd desktop
npm run typecheck
npm run lint
npx vitest run
```

In an existing development/test container with this checkout mounted:

```bash
docker exec -w /ti-toolbox <container> simnibs_python -m pytest tests/numerical -q
```

`tests/numerical/conftest.py` restores real libraries and reloads tested modules, so the host command
excludes that directory explicitly; numerical coverage is a separate container leg. Changes to the
scientific core require independent numerical coverage; use authored fixtures/reference calculations,
not expected values copied from the implementation. A real-library test with stubbed FEM is an
interface test, not a completed simulation. Published-output changes also need release-note guidance.

Repository guards:

```bash
python3 -m unittest tests.test_documentation_policy -v
python3 dev/documentation_policy.py
python3 dev/route_import_guard.py
python3 dev/contracts_check.py
```

The documentation-policy self-test drives absent, empty-directory, file, symlink and nested-content
fixtures before the guard rejects `docs/requirements` itself. Durable behavior goes directly to
ARCHITECTURE, rationale to DECISIONS, verification here and open work to ROADMAP; an intent archive is
not a second source of truth. The import guard prevents heavy scientific imports during route
registration. The contract guard
regenerates outputs in a temporary directory and checks byte drift against the authored contract.
Fix drift with `cd desktop && npm run gen`; never hand-edit generated output. Contract warnings
must be reported rather than counted as zero. `test_config_schema.py` compares full generated
schemas across fresh 1/4/12-CPU processes while asserting independent runtime QSI thread defaults
and explicit override preservation; generation must not embed the build host's CPU count.

The packaged example notebook (`tit/server/examples/example_workflow.ipynb`, the one source;
`examples/notebooks/` symlinks to it) is guarded two ways. `tests/test_example_notebook_api.py`, in the
host suite, resolves every import, keyword argument and `pm.` attribute of every cell against the
real `tit` API. `dev/run_example_notebook.sh` executes the
notebook in the release image against a fresh project (downloads ernie, runs the reduced flex
search, one TI FEM solve and the analyzer); it is the run that proves the notebook works and is
run before a release, not on every CI push, because it needs a real solve.

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

### Documentation screenshots

The app screenshots in `docs/assets/imgs/v3/` come from
`desktop/tests/e2e/real/docs-shots.spec.ts`, run offscreen against a dev container on Dataset 000.
Close the desktop app on that project first (it owns the same container), then:

```bash
cd desktop
TIT_DEV_IMAGE_TAG=v3.0.1 npx tsx ../dev/capture_docs_screenshots.ts            # every picture
TIT_DEV_IMAGE_TAG=v3.0.1 npx tsx ../dev/capture_docs_screenshots.ts -g "Help"  # one picture
```

The script starts or attaches to the container, builds with scene hooks, runs the spec under
`/tmp/tit-e2e.lock`, restores the plain build, and stops the container only if it started it. The
spec opens existing results and fills job rows but never submits a job or saves anything. Downscale
new pictures with `sips --resampleWidth 1600` before committing.

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
- [tests/README_TESTING.md](../../tests/README_TESTING.md) documents the two shell runners in that
  directory; it does not replace these desktop, numerical and artifact acceptance layers.

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

## Optimizer candidate and replay checks

`tests/test_flex_candidates.py` checks valid-only streamed records and scoring isolation;
`tests/test_candidate_catalog.py` uses authored histories and actual Ex CSV writers to test
pagination, containment and replay validation. `tests/test_candidate_replay.py` pins independent
per-carrier centres, orientation, current and layer settings. Their real-library siblings under
`tests/numerical/` exercise actual SciPy/SimNIBS boundaries without FEM; run them with the image's
`simnibs_python`, not the host scientific mocks.

`candidate-browser.test.tsx` and `candidate-history.test.ts` cover linked selection across table pages, missing metrics/anatomy, historical labels, bounded history loading and cancellation; frontier fixtures include ties and dominated points rather than only a monotonic happy path. The hidden `desktop/tests/e2e/optimizer-candidates.spec.ts` verifies the table/plot layout, cross-page selection, exact Simulator draft, cap snapping, displacement annotations and restoration of original XYZ without automatic submission. `tests/numerical/test_candidate_snap.py` compares candidate-specific cap assignment against exhaustive enumeration, including invalid caps and path confinement. These are UI, metadata and assignment checks, not a remeshed-field guarantee.

`dev/flex_candidate_benchmark.py` is an explicitly invoked real-subject benchmark. It requires a
project, subject and new output directory; run observation off/on in separate serial processes with
identical saved parameters. It loads the checkout integration only within that process. Receipts
record the configuration, source hash, sample counts, potential-solve counts, setup/evaluation time
and RSS. Its tiny `--optimizer-only` run checks execution and stopping status, not convergence.
Never run its FEM work concurrently with another simulation or optimization.

The developer-runtime regression is covered by `tests/test_flex_runtime.py` (source selection,
installed fallback, and failed-import propagation), and the real optimizer contract now uses the
production resolver. On 2026-09-13 the ordinary `simnibs_python -m tit.opt.flex` entry point completed
a one-iteration ernie run from `/tmp` in the existing container, without a custom class loader or
installed-package replacement. Output: `validation-loader-20260913` under the subject's flex-search
directory. This proves normal driver execution, not convergence; final electrode simulation was off.

### Flex objective regression case

`tests/numerical/test_flex_candidate_metrics.py` checks the real-library three-goal contract using
authored ROI samples 0..1000 and non-ROI [1,1,1,5]. Mean TImax is 500; Max TImax is 999
(linear 99.9th percentile); pure Focality is 250. At weight 1 the score is 125000. The solver
minimizes their negatives. The asymmetric non-ROI distinguishes mean from p95, and separate
candidates prove that intensity weighting can reverse the pure-focality ranking. Scaling and
invalid-field cases prevent accidental dose preference at zero weight and division artifacts.
This deterministic test verifies formulas, not convergence on a particular head.

The same fixture exercises the production builder for all three goals with current-ratio search
on and off, substituting only FEM field acquisition. A strictly positive parallel-carrier
fixture independently yields mean 501, percentile 1000, ratio 250.5, and weight-one score
125500.5. This covers native/callable scoring and recorder dispatch without a head solve.
Known upstream edge: exact zero vectors in both carriers produce NaN during maxTI normalization;
nonfinite candidate rejection remains active. This edge has not been corrected in the upstream
field routine and is not a claim about any observed dataset failure.

Completed-log regressions: `desktop/tests/unit/job-log-completion.test.tsx` verifies final-tail
retention and stability after succeeded/failed/cancelled states. `jobsStream.test.ts` covers
reconnect cursors and shared consumers; `tests/test_jobs_manager.py` and `tests/test_jobs_routes.py`
cover oversized backfill and ordered batch draining.


### Native viewer lifecycle release gate

ARCHITECTURE §7.1 defines the macOS arm64/x64, Windows x64 and Linux x64 acceptance matrix, including
Wayland and X11. Local suites cover application identity, concurrent initial setup, digest-verified downloads and
refusals, update-and-swap, rediscovery of earlier directories, legacy profiles, serialized handoff
and setup UI (there is no picker or machine-wide search to test: TI launches only its own copy). Fixtures also pin one shared
installation during startup/Retry/Results races and zero release-network requests on a second launch
with an identified installation. Run them with:

```sh
cd desktop
npx vitest run src/main/tetravoxNative.test.ts src/main/viewerHandoff.test.ts tests/unit/native-viewer.test.ts tests/unit/open-in-viewer.test.tsx tests/unit/tetravox-card.test.tsx tests/unit/viewer-page.test.ts
```

These fixtures do not prove package signing, native self-update, native window activation or completed
scene rendering. The Viewer mock E2E suite stubs native launch; a successful mock is not an upstream
TetraVox test. The legacy `tests/e2e/real/viewer-drop.spec.ts` still targets the retired iframe and
must be replaced with native acceptance coverage before release. The real package gate exercises clean
install, existing-install reuse, native update/relaunch, open/closed/minimized/no-window handoff, paths
with spaces and non-ASCII characters, preservation of busy/unsaved work and isolation from a second
installation on every matrix leg. Foreground assertions run only in an explicit QA desktop session;
ordinary automated tests remain hidden. Linux tar and Windows ZIP/NSIS update ownership must be
resolved upstream before claiming automatic setup support on those platforms.


### Live native scene saving

`nativeScenePreview.test.ts` covers bounded serialized capture, cached PNG reuse, confinement,
project changes, invalid sidecar preservation and render failures. The Viewer E2E covers lazy preview
publication, inline metadata, Escape/focus return and unchanged native open state. Native preview
smoke checks render actual saved scenes with `--job`, verify nonuniform PNG pixels and unchanged
scene hashes, and use the quiet monitor; fixture PNGs alone do not prove native rendering.

`src/main/nativeSceneBridge.test.ts` covers capture without a preceding TI open, attachment changes,
canonical project destinations, non-overwrite and receipts. `src/main/nativeSceneSave.test.ts` covers
host/server path mapping and project/session/trust changes during native readiness. The library test
`test_native_scene_without_metadata_uses_mtime_for_newest_first` verifies a native-only file can be
listed and read without companion metadata. These are fixture proofs, not native renderer tests.

`tests/unit/native-viewer.test.ts` validates confirmed-path receipts, cancellation, unavailable bridges
and incomplete/refused saves without HTTP recipe writes. `tests/e2e/viewer.spec.ts` adds mocked IPC
coverage for capability-disabled Save, confirmed-save list refresh and refusal without a saved claim.
It also checks the removed Save selection/Recent controls. These mock tests do not verify TetraVox.

The [upstream integration record](../../dev/upstream/tetravox-live-scene/README.md) identifies
TetraVox PR #44's generic scene API and TI's adapter boundary; it is not an acceptance checklist.
Do not mark live saving or macOS foreground recovery release-ready until the capability is tested in a
real native package and edited camera/layer state is reopened from the resulting project file. Include
closed, minimized and no-window states, existing-file refusal and unchanged originals. Installations without the declared capability show Save as disabled.

Native-scene verification on 2026-09-19: the source and local unsigned arm64 TetraVox package both
pass cold open, edited cursor snapshot, unchanged-original and no-window recreation tests using the
real engine. Source-run metadata monitoring passed; the packaged run's explicit hidden-window
assertions passed but its external metadata monitor ended inconclusive due to unresolved short-lived
process ancestry. This does not establish OS foreground behavior or Windows/Linux package support.
TI typecheck, lint (existing warnings), production build and 1,850 desktop unit tests pass; all 23
focused Viewer/Jobs/shell E2E tests pass. The 13 path/export tests also pass in Linux Python 3.11.
