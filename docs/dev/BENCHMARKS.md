# Benchmarks

The measured numbers the v3 desktop application was built against. Everything
here was produced by a real run during the programs recorded in
[`docs/dev/HISTORY.md`](../docs/dev/HISTORY.md), which
carries the narrative and the gotchas; this page carries the figures.

Unless a row says otherwise, the host is an Apple M2 (macOS, arm64) and the
container is `idossha/ti-toolbox` running amd64 **under emulation**, against
Dataset 000 `sub-ernie`. Emulated timings are not comparable to native ones and
are labelled where it matters.

## Image and runtime size

| Artifact | Content size | Disk usage | Measured |
|---|---|---|---|
| `idossha/ti-toolbox:dev` (one image) | **6.66–6.67 GB** | 21.3 GB with `simnibs:v2.5.0` cached alongside | 2026-09-03 |
| `idossha/simnibs:v2.5.0` (old stack) | 6.15 GB | 19.2 GB | 2026-09-03 |
| `ti-toolbox_freesurfer:v7.4.1` (old stack, dropped) | 21.9 GB | 67.5 GB | 2026-09-03 |
| Native pip runtime, no bpy (spike, parked) | 2.0 GB | — | 2026-09-03 |
| Native Electron `.app`, minimal runtime (spike, parked) | 468 MB (175 MB runtime + 286 MB Electron) | — | 2026-09-03 |

`docker images` prints non-deduplicated *disk usage*. Always cite content size —
it is the fresh-pull cost and it is stable.

Largest packages in a native runtime: simnibs 384 M (219 M of it atlases),
torch 345 M, PyQt5 136 M, llvmlite 113 M, scipy 100 M, sympy 77 M, pandas 73 M,
samseg 60 M, petsc4py 45 M, numpy 36 M.

## Server import cost

| Import | Wall | RSS |
|---|---|---|
| `import simnibs` alone | 3.4 s | 387 MB |
| `tit.sim` | 3.1–3.3 s | 388 MB |
| `tit.opt` | 3.1–3.3 s | 388 MB |
| `tit.analyzer` / `tit.stats` / `tit.pre` | 0.4–0.9 s | — |

This is why `tit.server` imports SimNIBS lazily: `/api/health` answers
immediately.

## Job runtimes (smoke matrix, Dataset 000, emulated)

Bare matrix: **21/21 passed in 280.7 s**, zero paths left on disk; an
independent rerun six minutes later also went 21/21. Reproduce with
`dev/smoke.sh` (see [`docs/dev/RUNBOOK.md`](../docs/dev/RUNBOOK.md)).

| Kind | Note |
|---|---|
| `sim` | 16 min to full completion |
| `ex` | 44.2 s — slowest completed job |
| `mex` | 40.2 s |
| `blender` | 32.5 s of bpy import before 12.1 s of work — slowest start |
| all long kinds | cancel latency **0.0 s** against a 15 s budget |
| all kinds | runner banner in 2.0–7.1 s (except blender); `accepted` leg under 10 s |

9 of the 21 rows replayed the UI's own recorded payload, proving the UI and the
runner agree on the request body.

## Scene service

| Measurement | Value |
|---|---|
| `ernie.msh` | 184 MB, 847,165 nodes, 5,899,838 elements, 1.7 s to read in-container |
| Skin surface (tag 1005) | 77,032 triangles / 38,952 vertices, 1.33 MiB |
| Grey matter (tag 1002) | 335,930 raw triangles, simplified to the 150 k budget (145,402 for DK40 gm) |
| Cold atlas build (HCP_MMP1, 362 regions) | 173 ms |
| First paint | 258 ms fresh, 19 ms warm |
| Orbiting | 121.2 fps (floor 30) |
| Pick accuracy after the winding fix | world point within 1.086 mm of an independently solved intersection; sphere-centre error 0.093–0.164 mm |
| `focus_bbox` crop | removes 34.2% of neck height on ernie, 7.2 mm of jaw on MNI152 |

Packaged Ernie guide assets: generated in 6.9 s, **15.48 MB** total against
184 MB of raw mesh (skin 77,032 tris / 1.39 MB, gm 145,402 tris / 2.59 MB,
three atlases, eight EEG nets). `TVSC1` budget is ≤3 MB and ≤150 k triangles per
surface.

## Catalog and API latency

| Endpoint | Cold | Warm |
|---|---|---|
| `GET /api/catalog/overview` (5 subjects, 25 optimisation runs) | 3.4 s | 0.12–0.14 s |
| Tetravox embed resolution, nothing installed | 21.6 µs | — |
| Tetravox embed resolution, three installs + a pin | 95.1 µs | — |

Overview's cold cost is manifest parsing in `tit.catalog`, not request count.

## Tetravox embed delivery

| Measurement | Value |
|---|---|
| Baked embed floor | `/opt/tetravox/embed`, v0.3.4, protocol 1, sha `c56c3c84…` |
| Live install wall time | 0.14 s for a 5.6 MB bundle |
| wasm chunk | 848,311 bytes, served as `application/wasm` |
| Rollback to baked | byte-identical ETag |
| Manifest read to learn `protocol` | ~2 KB asset, tarball never fetched |

Electrode dots against the real 0.4.0 embed: idle RGB `148,155,167`, pair 1
`0,106,166`, pair 2 `215,149,0`. Radial pixel profile
`[1,8,12,16,32,25,31,22,21,21,10,7,3,0,0,…]`, byte-identical before and after a
toggle — one solid disc, no ring. `dotRadiusPx` is currently inert in 3-D
(5 → 209 px, 15 → 209 px), a pinned defect awaiting Tetravox 0.3.12.

## NiiVue evaluation (2026-08-27, superseded by Tetravox)

| Measurement | Value |
|---|---|
| Four 256×256×208 volumes | 1.1–1.5 s to load |
| GM mesh, 169 k vertices | 144–272 ms |
| Central surface, 491 k vertices | 379 ms |
| JS heap | ~190 MB |
| `elm_data2node_data()` interpolation | 38 s once, then 0.2–0.6 s per surface export |

`TI_max` percentiles must be GM-masked: scalp p99 = 0.81 V/m against GM
p99 = 0.17 V/m.

## FastSurfer

| Measurement | Value |
|---|---|
| `--seg_only`, CPU, 8 threads | 292 s inference, 392 s end to end (~5 min) |
| Peak RSS | 4.84 GiB |
| Checkpoints | 67 MB |
| Dice vs real `recon-all`, 14 subcortical labels | **0.922** mean |
| Dice vs real `recon-all`, 20 cortical DKT labels | **0.914** mean |
| Centroid shift | mostly <1.5 mm; pallidum 3–4 mm, one cortical 3.1 mm |

n = 1 subject. Negligible for 10–15 mm ROI spheres, a real caution at 5 mm.
Pinning `torch==2.7.1` / `torchvision==0.22.1` from the CPU wheel index before
the FastSurfer install cuts that build step from ~140 s to ~49 s and avoids
~2 GB of `nvidia-cu12*` wheels on a machine with no GPU.

## Native runtime spike (parked)

A pip + python-build-standalone runtime on macOS arm64 ran a real two-pair TI
simulation on sub-ernie in 366.49 s and matched the emulated amd64 container to
13–14 significant figures:

| | Native arm64 | Emulated amd64 container |
|---|---|---|
| TI_max mean | 0.14605754393982354 | 0.14605754393982395 |
| TI_max max | 10.29371206441698 | 10.293712064403254 |
| FEM assemble / solve per pair | 6.3 s / 4.8 s | 6.8 s / 5.3 s |

`subject_atlas` DK40 output was byte-identical (sha256) and 1.7× faster.
`import simnibs` was 2.2–2.3 s warm, 27.1 s cold. Exact replacements were also
proven: `mri_convert --reslice_like` → `nibabel.processing.resample_from_to
(order=0)` differs in **0 of 13,631,488 voxels**, and `tit/atlas/segstats.py`
matches `mri_segstats` label ids and voxel counts exactly on four real atlases
(102/102, 188/188, 48/48, 56/56). Full verdicts:
[`docs/dev/SPIKES.md`](../docs/dev/SPIKES.md).

## Layout dead space

Measured by `desktop/tests/e2e/_metrics.ts::deadSpaceRatio` (a
topmost-element-is-content test, stricter than the pixel-occupancy proxy it
replaced). The acceptance table of record is `docs/dev/DESIGN.md` §12.3; the
limit for run pages is 45%.

| Page | Value | When |
|---|---|---|
| Pre-processing | 41.8% → 41.9% after the receipt slot was added | 2026-09-05 |
| `panel-source` | 44.8% — 0.2 points inside the limit | 2026-09-04 |
| Analyzer | 0.61 once against a ≤0.65 bound, clean on two reruns | 2026-09-05 |

## Gate baselines

| Date | Host pytest | Desktop unit | Offscreen e2e |
|---|---|---|---|
| 2026-09-03 (native research) | 3122 passed / 17 skipped | 43 files / 418 tests | quiet-check PASS |
| 2026-09-03 (docker streamline) | 3159 passed / 18 skipped | 46 files / 499 passed | 51 passed / 1 skipped |
| 2026-09-04 (scene IA) | 3519 passed | 909 passed | 5 passed |
| 2026-09-05 (overview/batch) | 3655 passed / 47 skipped | 79 files / 892 tests | 172 passed / 3 skipped |
| 2026-09-05 (tetravox/pipeline) | 3741 passed | 84 files / 949 tests | 195 passed / 3 skipped |
| 2026-09-06/07 (native panes, CX5) | 3970 passed / 36 skipped | 105 files / 1275 tests | 317 passed, quiet-check PASS |

The 2026-09-06/07 row is the whole-program gate: typecheck clean, lint 0 errors (3
pre-existing React-Compiler warnings), route-import guard 23 modules, `dev/contracts_check.py`
OK, and 22 real specs against the dev container on Dataset 000. `test_scene_guide`'s known
order-dependent failure in a full run is not counted as a red — it passes standalone.

### Real-container measurements, 2026-09-06/07 (sub-ernie, 1280 px, warm)

| What | Value |
|---|---|
| Native pane, first paint (warm) | 92 ms (`scene-electrodes`), 122 ms (`scene-atlas-border`); budget 300 ms |
| Orbit frame rate | 122 fps on 222,434 triangles, 0.10 ms CPU per frame |
| DK40 border quality | 24 scan lines, 129 border crossings, 18 A\|B\|A excursions, 8 sub-triangle spikes = **6.20 %** |
| Region colour fidelity | `rostralmiddlefrontal/lh` cos-to-own-atlas-hue **0.998**, cos-to-flat-blue 0.771 |
| Electrode state change | idle `[155,163,176]` → selected `[0,112,175]`, 94 px changed, solid to r=7 (no ring) |
| Idle marker vs scalp separation | worst **2/255**, median 35 over the 24 nearest front electrodes — see DECISIONS, open |


## Native panes and external viewer (2026-09-06)

| What | Value | Context |
|---|---|---|
| Image, gmsh/X11-set prune | 19.5 → 9.27 GB disk; 5.88 → 2.41 GB content | `Dockerfile.ti-toolbox` slim pass |
| Image, PyQt5 + TMS coil models removed | 9.27 → 8.93 GB disk; 2.41 → 2.32 GB content | |
| Build context, `.dockerignore` allow-list | ~2 GB raw → 262.8 MB → 137.5 MB | local-source build |
| Tetravox embed package (0.3.11, protocol 2) | 1.8 MB tarball | before the embed was retired |
| Guide packaging with TVSC1 labels | 15.48 → 18.44 MB (+2.96 MB), 8.4 s | real `sub-ernie` mesh |
| Guide GIfTI copies, still packaged | ~11.3 MB | open item — droppable |
| Scene render, 152–156 k tris, 1280×800 @dpr2 | 120.0 fps | gallery fixture |
| Scene render, real sub-ernie, 222,434 tris, orbit | 122.5–122.8 fps; last frame 0.10–0.20 ms CPU | |
| Scene warm first paint, real server | 91–219 ms | |
| Electrode pick error | 1.086 mm against a 1.865 mm tolerance | |
| Transparency, worst per-channel colour step | 23/255 (old winding split) → 2/255 (depth-resolved sheets); bound 12, never above 4 in 10 runs | |
| Draw calls per frame, 2 surfaces + markers | 7 → 13 after depth-peel | |
| Atlas border, white pixels in a 100×100 window | 40/441 → 0/441; repainted-outline pixels 4/439 (0.9%) | |
| Atlas border sub-triangle spikes | 8 spikes = 6.20% of 129 border crossings over 24 scan lines | |
| Idle electrode vs opaque-GM scalp contrast | worst 2/255, median 35 | 24 front-most electrodes, ernie / GSN-HydroCel-185. **Open** |
| `/api/view/open` dry run, host | 831 ms cold → 0.4 ms warm (median of 9); target ≤200 ms | |
| `build_view` | 864 ms → 0.3 ms (2,723×) | |
| `/api/view/open`, real emulated container, 5 calls | 2.28 s cold → 0.0055 / 0.0054 / 0.0046 / 0.0039 s (~580×) | |
| ViewSpec scene file | 7,190 bytes | real `simulation.tetravox.json`, 5 datasets |
| Tetravox scene byte cap | `MAX_SCENE_BYTES` = 8 MiB | |
| Menu list edit, after client-side caching | 1 dry run per click → 0 requests; Open click → response 22 ms, response → on screen 16 ms | |
| Managed-Tetravox real download (superseded design) | 131 MB; verify + unpack + codesign in 6.3 s | |
| Disk at the CX4 gate | 893 GiB used of 926; Docker images 280.2 GB (53.8 reclaimable), build cache 50.1 GB (21.4), volumes 26.8 GB (all) | the `ENOSPC` incident |

Gate progression across the program's three consolidation passes: host pytest
3,662 → **3,970 passed** / 36 skipped / 21 deselected; desktop vitest 1,039 →
**1,275 passed** across 88 → 105 files; offscreen mock e2e 208 → **285 passed**
(blocked twice at CX4 by `ENOSPC`); real subset **22 passed**. The final CX5 row
with its full detail is in `docs/dev/ROADMAP.md`.

## External audit response (2026-09-07, CX6)

### Scientific corrections — the numbers behind the claims

| What | Value | Where it comes from |
|---|---|---|
| SCI-01, permutations that change value under `alternative="less"` | **2 of 20** | exhaustive relabelling of the 3-vs-3 / 8-voxel design in `tests/numerical/test_sci01_cluster_sign.py` |
| SCI-01, same under `"two-sided"` | **3 of 20** | as above |
| SCI-01, same under `"greater"` | **0 of 20** — the right tail is unaffected | as above |
| SCI-01, largest single discrepancy | null value **−64.06** where the correct oriented value is **+64.06** | the wrong sign, not merely a small null |
| SCI-03, voxel focality overstatement | **10×** (divided by 100 instead of 1000) | `focality_*_area`, voxel path, v2.3.0–v2.5.0; rescalable |
| SCI-04, p-value floor at 1000 permutations | **0 → 1/1001 ≈ 9.99e-4**; every p moves by at most 0.001 | Phipson & Smyth `(b+1)/(m+1)` |
| SCI-05, voxel-volume error on the test's representative shear | **11.3 %** overestimate | `prod(header.get_zooms())` vs `abs(det(affine[:3,:3]))`; 0 % on any orthogonal grid |
| SCI-07 (open), `hf_sar` for two aligned unit fields in one channel | **2 → 4**; RMS 1 → 2; `hf_peak` unchanged at 2 | Model A vs Model B, `SCIENTIFIC-CORRECTIONS.md § Open decisions` |

### CX6 consolidation gate

| Gate | Command | Result |
|---|---|---|
| Typecheck (node + web) | `npm run typecheck` | clean |
| Lint | `npm run lint` | **0 errors**, 3 warnings (React Compiler `incompatible-library`: react-hook-form `watch()`, TanStack Table, TanStack Virtual) |
| Desktop unit | `vitest run` | **1,304 passed** across **109 files** |
| Host Python | `python3 -m pytest tests -q` | **4,069 passed**, 37 skipped, 21 deselected, 92 s |
| Container Python (real libraries) | `docker run --rm --platform linux/amd64 … idossha/ti-toolbox:dev simnibs_python -m pytest tests/numerical/ tests/test_jobs_* tests/test_kernels* tests/test_server_*` | **410 passed**, 33.5 s |
| Contract | `dev/contracts_check.py` | OK — 10 operations, 9 schemas |
| Route imports | `dev/route_import_guard.py` | 23 modules clean, 9.5–62.8 ms each |
| Workflows | `actionlint .github/workflows/*.yml` | clean (was 17 findings in `python-security.yml`) |
| Mock e2e | `TIT_E2E_OFFSCREEN=1 npm run e2e:quiet -- --workers=1` | **317 passed**, 2 skipped, 4.4 min, no window reached the screen |
| Viewer Open, mock | `viewer.spec.ts` | click → response 23 ms, response → scene on screen 16 ms |

Gate progression across the program's four consolidation passes: host pytest 3,662 → 3,970 →
**4,069 passed**; desktop vitest 1,039 → 1,275 → **1,304** across 88 → 105 → **109** files;
offscreen mock e2e 208 → 285 → **317 passed**.
