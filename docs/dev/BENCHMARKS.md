# Performance measurements

[TESTING](TESTING.md) owns correctness checks and verification receipts;
[CONTRIBUTING](../../CONTRIBUTING.md) owns setup. This page contains performance and resource
measurements only. Add a measurement when it informs a decision; include the source/image,
dataset, cache state, command or procedure, and limitations needed to repeat it.

Unless stated otherwise, these historical measurements used an Apple M2 host with an amd64
container under emulation and Dataset 000/sub-ernie. They are not current-build guarantees or
native-platform predictions. Local ignored receipts may expire; retain the configuration when
refreshing a benchmark. Never compare a warm cache with a first-ever load without labeling both.

## Target preview preparation — 2026-09-09

Dataset 000/sub-101, T1 grid 240×512×512 at 0.8×0.5×0.5 mm, same amd64 dev container
under emulation. Baseline source `bd71ec02`; improved implementation uses compact display anatomy,
cropped targets and a cached display-grid MNI deformation. These timings measure API preparation,
not the time from opening the page to a rendered frame.

| Request/cache state | Before | After |
|---|---:|---:|
| First subject-space sphere | 24.34 s | 2.62 s |
| First MNI volume mask, uncached registration | 126.37 s | 17.22 s |
| Different MNI mask, registration cached | — | 0.398 s |
| Identical MNI mask, target cached | — | 0.005 s |

Repeat authenticated `POST /api/scene/target-preview` requests with the same subject, mask and
space, timing the first request separately from repeated requests and a second mask. Use a copied
project with an empty target-preview cache for cold measurements. The first MNI request reads a
417 MB compressed registration; later masks share its compact deformation. MNI previews sample
the display grid; calculations retain the original mask and registration. A target below preview
resolution reports that limitation instead of silently displaying an empty selection.

A separate headless Chromium probe with the actual embed already initialized measured 1.27 s
for a sphere request through `loaded`, then 0.28 s after changing radius from 10 to 11 mm.
Anatomy was cached on disk, and the second load retained its dataset ID. This confirms reuse,
not cold-start browser performance. The renderer remains alive between target edits.

## Progressive viewer loading — 2026-09-09

One before/after observation on the same six-volume selection, 149.07 MB compressed:

| Measurement | Before | After |
|---|---|---|
| First visible layer | 9.211 s | 4.124 s |
| All six layers visible | 9.211 s | 4.800 s |
| Add four volumes after two loaded | — | Four new raw-file requests; original dataset IDs retained |

To repeat, open the same six-volume composition, record elapsed time and adopted layer count
from Open through final load, then begin with two volumes and add the remaining four while
recording raw-file requests. Preserve file list, byte sizes, cache state and embed identity.
Receipts: `dist/internal/tetravox-six-volume-{baseline,progressive}.json` and
`tetravox-incremental-receipt.json`. Local embed source:
`3b16a47ec1235640f5f392f71a609cc80dce75ed`, archive SHA-256
`298e9247e0ed55ec3e36780ceea7c0f5b2ed65760e6f46cc3e2390e5f8e37048`.
This is not a controlled cross-platform benchmark or evidence of an updated baked image.

## Scene and catalog performance — 2026-09-04–07

Use the [real e2e procedure](TESTING.md#hidden-end-to-end-tests), particularly
`desktop/tests/e2e/real/scene-electrodes.spec.ts` and `scene-atlas-border.spec.ts`, to refresh pane
measurements on the same anatomy. For API measurements, time repeated authenticated requests
with the same input and record separately the first response and subsequent responses.

| Measurement | Observation |
|---|---|
| Reference mesh read in container | 184 MB; 847,165 nodes / 5,899,838 elements; 1.7 s |
| Packaged guide with TVSC1 labels | 18.44 MB; 8.4 s build; per-surface budgets 150k triangles / 3 MB |
| Real native pane first paint, warm | 91–219 ms |
| Orbit, 222,434 triangles | About 122 fps; 0.10–0.20 ms CPU/frame |
| Overview, five subjects / 25 optimization runs | 3.4 s cold; 0.12–0.14 s warm |
| Viewer selection resolution | Previously 16.4 s; about 14–28 ms with persisted statistics/cache; first-ever resolve remained about 10.2 s |

Overview's cold cost was manifest parsing. Viewer statistics use full data and persist by file
size/mtime; a new process is not necessarily a cold cache. Scene timing is not scientific validation.

## Blender memory and output size — 2026-09-08

A full-net `ernie/L_Insula` export produced a 69,387,270-byte scene with 378 objects, 185 meshes,
668,092 base vertices and six cameras. The successful capped run used 12 GiB RAM plus about
1 GiB swap; this is not an uncapped peak. Earlier 3 and 8 GiB attempts were OOM-killed.
The resulting montage reservation is 16 GiB; lightweight exporters retain a separate budget.

Repeat through the real montage job with the saved subject/configuration and a recorded container
memory limit. `tests/test_blender_process_boundary.py` with `TIT_TEST_BLENDER_BIN` checks actual
Blender export/reopen, but its small fixture does not reproduce full-net memory consumption.
Scientific preparation and Blender run in separate supported dependency environments.

## Historical image size — 2026-09-09

For source `e3bee214cea67be1f0867b74aceaf9c718c9eaf3`, image
`sha256:56faec6cecce2c1645a8895f75d01ff2125eb006abb6b9152e03704573e8b0c9`,
`docker image inspect` reported `.Size = 2,403,717,605` bytes and `docker image ls` displayed
9.27 GB. Receipt: `dist/internal/image-receipt-before-security.json`.

Repeat both commands against the explicitly identified candidate; Docker local size/accounting
and compressed registry transfer are different metrics. These numbers precede subsequent fixes
and cannot be quoted as current download requirements. Registry transfer size remains unmeasured.

## Historical real-job duration — 2026-09-09

The same earlier baked candidate completed the simulation/analyzer pipeline in 16.7 minutes and
an EEG forward job in 727.9 s. Receipt: `dist/internal/real-final-baked-receipt.json`.
Repeat the corresponding `pipeline.spec.ts` and `source.spec.ts` real specs with a copied project,
the same recorded configuration and an idle queue. Run one FEM workload at a time under emulation.
These are workflow durations, not latency guarantees or certification of later security changes.

## Native Apple Silicon FastSurfer acceptance — 2026-09-10

The managed FastSurfer 2.5.4 runtime completed a Docker-owned preprocessing job on the maintainer's Apple Silicon Mac in 80.1 seconds, including native handoff and derived NIfTI conversion. This used a 1 mm resampling of subject 101's T1 (193 × 257 × 257 input), MPS inference, CPU aggregation, batch size 1 and 10 threads. It is an integration fixture timing, not a full-resolution performance claim.

Job `fce5d3e9307d48b5` used the isolated `tit-native-acceptance` container and the current source checkout. The hidden Electron test declined then accepted native consent and reran managed installation before submission. Output under `derivatives/fastsurfer/sub-nativeMetalSmokeB20260910` was readable on both host and container: 256³ voxels, 96 label values and 1,285,285 nonzero voxels. Container-side comparison verified exact voxel equality and matching affine between MGZ and derived NIfTI. The generated label sidecar was present. These checks validate transport and conversion, not anatomical segmentation quality.

Reproduce with the opt-in script in [TESTING](TESTING.md#native-fastsurfer-acceptance), a new test subject and `TIT_NATIVE_TEST_INPUT` set to the same resampled fixture. Test inputs and receipts are retained in the project. A separate full-resolution cancellation run verified termination of the native process group after the Docker requester stopped.

## 2026-09-13 — Flex non-ROI observation, ernie volume smoke

Explicitly invoked `dev/flex_candidate_benchmark.py` in the existing Linux development container
(Python 3.11.14), serial fresh processes, two CPUs, scalar conductivity, `max_TI`, 2 mA per carrier,
10 mm circular electrodes. Subject-space sphere: (-35, -20, 50) mm, radius 15 mm, GM volume.
15,466 target samples and 1,324,563 complementary GM samples. One warm-up plus three measured trials;
small parameter perturbations retained the same discrete electrode footprint. This is a bounded
fixed-placement overhead measurement, not independent-search convergence evidence.

| Measurement | Target only | Non-ROI observed | Change |
|---|---:|---:|---:|
| Median warm evaluation | 0.6654 s | 1.3969 s | +109.9% |
| Setup | 104.74 s | 161.32 s | +54.0% |
| Process peak RSS | 5,534,400 KiB | 6,053,384 KiB | +9.4% |
| Potential solves per trial | 2 | 2 | unchanged |

All four objectives matched exactly and all four candidates remained valid. The 10% evaluation-time
budget failed; the 20% peak-memory budget passed. `observe_background` therefore remains opt-in.
Surface ROIs, searched ratios, varied placements and other heads remain unbenchmarked; these numbers
must not be generalized to them. No AUC was computed. Process peak RSS includes preparation.

Local receipts: project `000` → `code/ti-toolbox/candidate-observation-20260913-166c7a/`,
`baseline-final/benchmark.json` and `observed/benchmark.json`. Both record the patched optimizer SHA256
`5fffac207894bf3e5e207ef15d0f62cd7fca62f2928b0050a833f3c0b9b8036c`, configuration and saved parameters.
The receipts contain local subject paths and are not published as repository fixtures. Reproduce in
new output folders using the script's two-command example and the same subject/configuration.

### Actual threshold-free search and selected-candidate FEM

On the same target, a deliberate DE smoke (`seed=17`, `maxiter=1`, `popsize=1`, no polish)
made 16 evaluations: three valid placements and 13 rejected placements, with six potential solves.
The accepted contrast was 0.78227548. Solver status was `success=false`, maximum iterations exceeded;
a valid returned candidate is not convergence. Another candidate had a higher target mean
(0.37659901 V/m versus the winner's 0.20953420 V/m), demonstrating the intensity/contrast trade-off.

The live candidate list/detail endpoints returned HTTP 200. The standard Simulator SESSION matched
the saved centres, orientations, signed currents, dimensions and layers, then completed two serial
remeshed carrier solves and cortical mapping in 366.46 seconds. Finite fields were verified, with
identical GM mesh nodes/connectivity across carriers. Independently reduced final TI fields gave:

| Metric | Online estimate | Remeshed SESSION | Difference |
|---|---:|---:|---:|
| Target mean, V/m | 0.20953420 | 0.21860216 | +4.33% |
| Non-ROI p95, V/m | 0.26785219 | 0.27620445 | +3.12% |
| ROI mean / non-ROI p95 | 0.78227548 | 0.79145055 | +1.17% |

These are observations, not an accepted numerical-equivalence tolerance. SimNIBS reported electrode
flux-magnitude calibration differences of 9.6% and 3.5%; its code subsequently rescales potentials
using the requested current divided by mean electrode flux. This diagnostic is not the linear-solver
residual or proof of exact per-electrode flux equality. No solver settings were changed to hide it.

The test intentionally bypassed TI-Toolbox's full postprocessing runner, which can rewrite the
original subject's cached T1 MNI image. Thus full job orchestration, Analyzer workflow and repeated-seed
convergence remain unproven. This run predates the new mesh-digest recording guard and was explicitly
labeled unverified for historical mesh identity; the guard itself has synthetic change-detection tests.
The installed runtime was not replaced: the harness loaded the checkout integration in its process.

Local run: `derivatives/SimNIBS/sub-ernie/flex-search/validation-20260913-166c7a/` in project `000`.
Original receipts preserve effective-budget omissions in the early harness configuration;
`validation_run_meta.json` records the actual one-iteration options rather than rewriting history.
Replay receipts: `code/ti-toolbox/candidate-observation-20260913-166c7a/replay-v1/`.
(The one-off `dev/flex_candidate_replay.py` validation script was removed on 2026-09-17; the benchmark script above remains.)
