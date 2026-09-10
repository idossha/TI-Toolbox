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
