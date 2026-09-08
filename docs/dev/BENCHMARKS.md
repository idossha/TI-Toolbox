# Benchmarks

The measured numbers the v3 desktop application was built against. Everything
here was produced by a real run during the programs recorded in
[`HISTORY.md`](HISTORY.md), which
carries the narrative and the gotchas; this page carries the figures.

Unless a row says otherwise, the host is an Apple M2 (macOS, arm64) and the
container is `idossha/ti-toolbox` running amd64 **under emulation**, against
Dataset 000 `sub-ernie`. Emulated timings are not comparable to native ones and
are labelled where it matters.

## Image and runtime size

| Artifact | Content size | Disk usage | Measured |
|---|---|---|---|
| `idossha/ti-toolbox:dev` (one image, `0ae4757968`, Tetravox embed 0.4.0 / protocol 3) | **2.32 GB** | 8.92 GB | 2026-09-07 |
| `idossha/ti-toolbox:dev` (one image, `853220d5`, after the slimming pass) | **2.32 GB** | 8.93 GB | 2026-09-07 |
| `idossha/ti-toolbox:dev` (one image, pre-slimming — superseded) | 6.66–6.67 GB | 21.3 GB with `simnibs:v2.5.0` cached alongside | 2026-09-03 |
| `idossha/simnibs:v2.5.0` (old stack) | 6.15 GB | 19.2 GB | 2026-09-03 |
| `ti-toolbox_freesurfer:v7.4.1` (old stack, dropped) | 21.9 GB | 67.5 GB | 2026-09-03 |
| Native pip runtime, no bpy (spike, parked) | 2.0 GB | — | 2026-09-03 |
| Native Electron `.app`, minimal runtime (spike, parked) | 468 MB (175 MB runtime + 286 MB Electron) | — | 2026-09-03 |

`docker images` prints non-deduplicated *disk usage*. Always cite content size —
it is the fresh-pull cost and it is stable.

The 2026-09-07 row is the image after the Dockerfile slimming pass (gmsh, PyQt5,
TMS coil models, neovim and the build compilers removed): `docker image inspect
--format '{{.Size}}'` reports 2.32 GB, `docker images` / `docker system df`
report 8.93 GB for the same id. The documentation site states both, as
"≈ 2.3 GB to download, ≈ 9 GB unpacked on disk" (`docs/about/about.md`), because a
reader planning disk space needs the second number and a reader planning a pull
needs the first. The 2026-09-03 row is kept so the two measurements are not read
as a contradiction.

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
`dev/smoke.sh` (see [`CONTRIBUTING.md` §2.6](CONTRIBUTING.md)).

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
[`HISTORY.md` § 2026-09-03 — native desktop research](HISTORY.md).

## Layout dead space

Measured by `desktop/tests/e2e/_metrics.ts::deadSpaceRatio` (a
topmost-element-is-content test, stricter than the pixel-occupancy proxy it
replaced). The acceptance table of record is [`DESIGN.md`](DESIGN.md) §12.3; the
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
| 2026-09-06/07 (native panes, CX5) | 3970 passed / 36 skipped | 105 files / 1275 tests | 285 passed, quiet-check PASS |
| 2026-09-07 (external audit, CX6) | 4069 passed / 37 skipped | 109 files / 1304 tests | 317 passed / 2 skipped |
| 2026-09-07 (docs/launch consolidation, CX7) | 4141 passed / 37 skipped | 109 files / 1304 tests | 322 passed / 2 skipped |
| 2026-09-07 (v2.5.0 merge + contracts, CX8) | 4165 passed / 45 skipped | 109 files / 1304 tests | 323 passed / 2 skipped |

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
| SCI-07, `hf_sar` for two aligned unit fields in one declared channel | **2 → 4**; RMS 1 → 2; `hf_peak` unchanged at 2 (the aligned case) | resolved — carriers grouped per Cassarà 2025 Part II p. 8, `SCIENTIFIC-CORRECTIONS.md § SCI-07` |
| SCI-07, an *opposing* group: `E₀=(1,0,0)`, `E₁=(−0.9,0,0)` on one carrier, `E₂=(0,0.4,0)` on another | `hf_peak` **1.942 → 0.412**, `hf_sar` **1.97 → 0.17** | grouping removes sign patterns the hardware cannot realise |
| SCI-07, `hf_sar / 2` vs an independent time-domain `mean|E(t)|²`, 1–3 carriers, 2 fields each | agreement to **1e-9 relative** | `tests/numerical/test_sci07_exposure_channels.py`; commensurate carriers, exact common period |
| SCI-07, `hf_peak` vs the measured `max_t |E(t)|`, 3 fields on 2 carriers | agreement to **2e-4 relative** (time-grid resolution) | the phasor worst case is *attained*, not merely a bound |
| SCI-08, `_envelope_from_PQ` relative error vs 60-digit `decimal`, `Q/P` from 1e-8 to 1e-20 | rationalised **< 1e-14**; naive **> 0.1** | the naive form returns exactly 0 below `Q/P ≈ 1e-16` |

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
| Real e2e | `npx playwright test --project=real` against the dev container | **39 of 40 passed**, 28 min; the one red is `mex.spec.ts`, written against the pre-jobs-table Optimizer (`RELEASE.md` §B) |
| Viewer Open, mock | `viewer.spec.ts` | click → response 23 ms, response → scene on screen 16 ms |

Six reds the gate found and fixed, each at its cause: the `test_scene_guide` order dependency
(`c799e7e2`), 17 `no-undef` lint errors from an unlinted `scripts/` directory (`f1ea7fcf`), 17
`actionlint` findings in `python-security.yml` (`a8422ca1`), `GET /api/settings` returning a
document `PUT` refused so Settings could not save at all (`6b26239d`), the participants header
overflowing onto the next card so its Add button was unclickable (`d9773780`), and an empty
`valid_mask` crashing in a numpy reduction (`22129a34`). Three test-side fixes:
`379c7f6f`, `4aeca028`, `50b54000`.

Gate progression across the program's four consolidation passes: host pytest 3,662 → 3,970 →
**4,069 passed**; desktop vitest 1,039 → 1,275 → **1,304** across 88 → 105 → **109** files;
offscreen mock e2e 208 → 285 → **317 passed**.

### CX7 consolidation gate

Run after the docs/dev fold (24 → 9 files), the website pass and the launch-path work landed.

| Gate | Command | Result |
|---|---|---|
| Typecheck (node + web) | `npm run typecheck` | clean |
| Lint | `npm run lint` | **0 errors**, the same 3 React-Compiler `incompatible-library` warnings |
| Desktop unit | `npx vitest run` | **1,304 passed** across **109 files**, 6.1 s |
| Host Python | `python3 -m pytest tests -q` | **4,141 passed**, 37 skipped, 21 deselected, 87.5 s |
| Container numerical | `docker exec … simnibs_python -m pytest tests/numerical -q` | **94 passed**, 1.6 s |
| Container jobs/kernels/server/launch | `… -m pytest tests/test_jobs_* tests/test_kernels* tests/test_server* tests/test_launch* -q` | **387 passed**, 32.1 s |
| Contract | `dev/contracts_check.py` | OK — 10 operations, 9 schemas |
| Route imports | `dev/route_import_guard.py` | 23 modules clean, 8.9–67.1 ms each |
| Workflows | `actionlint` | clean |
| Site build | `bundle exec jekyll build` (Homebrew Ruby 3.3.10) | done in 1.67 s |
| Site links | internal-link scan over `docs/_site` | **195 pages, 0 dead links** outside the vendored `docs/api/` mkdocs tree, whose 123 are its `_`-prefixed assets Jekyll excludes — pre-existing since `574f0a55` |
| Mock e2e | `TIT_E2E_OFFSCREEN=1 npm run e2e:quiet` | **322 passed**, 2 skipped, 4.3–4.4 min, quiet-check PASS |
| Real e2e — docs shots | `npx playwright test --project=real tests/e2e/real/docs-shots.spec.ts` | **7 passed**, 1.1 min, quiet-check PASS |
| Real e2e — UI subset | 9 real specs (tetravox, viewer-open, notebooks, montage-shape, page-memory, scene-atlas-border, scene-electrodes, analyzer-targets, flex-result-selection) | **23 passed**, 1.6 min, quiet-check PASS |
| Build of record | `pnpm run build` | `index-rKWxRs7Q.js` (3,351.54 kB), served by `ti-toolbox-fad740e5-tit-1` |

**The mock suite is flaky at roughly 1 test in 325, and it is a different test each run.** Two full
runs: the first failed `pipeline-ux.spec.ts` "⌘Z steps through the history" (2 nodes where 1 was
expected), the second `page-memory.spec.ts` "changing another tab's subject" (the Viewer's atlas
select still reading its `Atlas…` placeholder instead of `Server default`). Each passes standalone
and in its own file — `pipeline-ux.spec.ts` 26 passed, three times in a row; `page-memory.spec.ts`
12 passed, 1 skipped. Both are queries not yet settled at the 5 s expect timeout in a four-minute
serial run, not product defects, and neither test's code path was touched by this lane. The real
fix is a per-assertion wait, not a longer global timeout; it is not attempted here.

`docs-shots.spec.ts` rewrites all 16 `docs/assets/imgs/v3/*.png` on every run, and on this machine
it writes them at roughly 2.5× the committed byte size (70 kB vs 28 kB for `overview.png`) — a
device-scale difference, not a UI change. They were reverted, not committed: the website lane's
images are the ones of record.

### CX8 consolidation gate

Run after the `origin/main` v2.5.0 merge, the contracts restructure, the launcher structure and the
plugin refresh had all landed on the branch.

| Gate | Command | Result |
|---|---|---|
| Typecheck (node + web) | `npm run typecheck` | clean |
| Lint | `npm run lint` | **0 errors**, the same 3 React-Compiler `incompatible-library` warnings |
| Desktop unit | `npx vitest run` | **1,304 passed** across **109 files**, 6.6 s |
| Host Python | `python3 -m pytest tests -q` | **4,165 passed**, 45 skipped, 21 deselected, 90.7 s |
| Container numerical | `docker exec … simnibs_python -m pytest tests/numerical -q` | **94 passed**, 68.9 s |
| Container jobs/kernels/server/launch | `… -m pytest tests/test_jobs*.py tests/test_kernel*.py tests/test_server*.py tests/test_launch*.py -q` | **399 passed**, 1 skipped, 36.9 s |
| Contract | `dev/contracts_check.py` | OK — **104 operations, 115 schemas, 0 known findings**, 222 warnings |
| Generated files | `npm run gen` | byte-identical on re-run |
| Route imports | `dev/route_import_guard.py` | 23 modules clean |
| Workflows | `actionlint` | clean |
| Plugin | `python3 agent-plugin/mcp/server.py --selftest` | PASSED |
| Launchers | `python3 loader.py --help`, `bash loader.sh --help` | both exit 0 |
| Site build | `bundle exec jekyll build` (Homebrew Ruby 3.3.10) | done in 1.89 s |
| Site links | internal-link scan over `docs/_site` | **195 pages, 0 dead links** outside the vendored `docs/api/` mkdocs tree (123 pre-existing `_`-prefixed asset refs) |
| Mock e2e | `TIT_E2E_OFFSCREEN=1 npm run e2e:quiet` | **323 passed**, 2 skipped, twice — 4.4 min and 4.7 min, quiet-check PASS both |
| Real e2e — UI subset | the same 9 real specs CX7 ran | **23 passed**, 1.6 min, quiet-check PASS |
| Real e2e — docs shots | `npx playwright test --project=real tests/e2e/real/docs-shots.spec.ts` | **7 passed**, 1.0 min, quiet-check PASS; PNGs reverted |
| Build of record | `pnpm run build` | **built in 4.24 s** — renderer entry `index-DhcoV8Sp.js` (4,109.83 kB), `index-Bxei7s40.css` (361.75 kB) |

**The "1 in 325 flake" CX7 recorded is machine load, not the product, and this gate has the
counter-example.** A middle run of the mock suite failed **ten** tests at once — four
`controls-consistency`, three `jobs` (including its density numbers at 0.3446 against a 0.33
ceiling), one `layout`, two `launcher` — and took **25 minutes** instead of 4.4. `uptime` during it
read **load average 63–74**: Spotlight was indexing the build output while the maintainer used the
machine. Re-run on a quiet machine, the identical build passed 323/323 in 4.7 min. The same effect
explains the two reds this lane was sent to fix: `overview.spec.ts`'s detail pane measured **61.4 %**
once and **51.8 %** on five consecutive clean runs of the same commit (ceiling 0.53), and
`scene-pane.spec.ts`'s `markers: 0` did not reproduce at all after a `pnpm run pree2e`.

**The rule this yields: a density or layout assertion is only evidence on an unloaded machine.**
Check `uptime` before believing one, and never run a second Playwright suite, a docs build or a
container test batch beside one. The quiet-check's focus leg is likewise unreliable on a shared
desktop — it reported `FAIL — a test binary held the focus` twice while its own window leg said
*no new Electron/Chromium window reached the screen*, because the maintainer's `npm run dev`
Electron app was on screen and being clicked by a human.


### CX9 consolidation gate

Run after the viewer tree/scenes/kinds, the results panes, the report-as-attachment change, the help
popovers, the jobs rail and the System page had all landed, and after this lane's own two changes
(SCI-09's record, and "open in viewer" actually opening).

**Docker Desktop was not running on the gate machine and could not be started without taking the
screen, so every container leg is UNRUN, not green.** They are listed below with that word in them.
Nothing in this table is inferred from a passing host leg.

| Gate | Command | Result |
|---|---|---|
| Typecheck (node + web) | `pnpm run typecheck` | clean — **after fixing 10 pre-existing errors** (below) |
| Lint | `pnpm run lint` | **0 errors**, the same 3 React-Compiler `incompatible-library` warnings |
| Desktop unit | `pnpm exec vitest run` | **1,488 passed** across **115 files**, 8.8 s |
| Host Python | `python3 -m pytest tests -q` | **4,342 passed**, 45 skipped, 21 deselected, 100.1 s |
| Container numerical | `docker exec … -m pytest tests/numerical -q` | **UNRUN — no Docker daemon** |
| Container view/jobs/kernels/server/launch | `docker exec … -m pytest tests/test_view*.py tests/test_jobs*.py …` | **UNRUN — no Docker daemon** |
| Contract | `python3 dev/contracts_check.py` | OK — **114 operations, 136 schemas**, 244 warnings |
| Generated files | `pnpm run gen` | byte-identical on re-run |
| Route imports | `python3 -m pytest tests/test_route_import_guard.py` | **24 passed** |
| Workflows | `actionlint` | clean |
| Plugin | `python3 agent-plugin/mcp/server.py --selftest` | PASSED |
| Launchers | `./loader.sh --help`, `bash dev/loader/loader_dev.sh --help` | both exit 0 — `loader.sh` only after the fix below |
| Site build | `bundle exec jekyll build` (Homebrew Ruby 3.3.10, `ruby@3.3`) | done in 1.85 s |
| Site links | internal-link scan over `docs/_site` | **3,324 internal links, 2 dead**, both in the vendored `docs/api/404.html` mkdocs tree (`/api/.`, `/api/assets/_mkdocstrings.css`) |
| Mock e2e | `pnpm run e2e:quiet` | **363 passed**, 2 skipped, 0 failed — **twice**, 6.8 min and 6.1 min |
| Real e2e (viewer-open, results-group, docs-shots, notebooks, browser-mode) | `--project=real` | **UNRUN — no Docker daemon** (the real project is served by the dev container) |
| `verify-image.sh` vs `idossha/ti-toolbox:dev` | throwaway container, expect embed 0.4.0 / protocol 3 | **UNRUN — no Docker daemon** |
| Dev container serves the new build hash | `pnpm run build`, then read the served asset | **UNRUN — no Docker daemon** |
| Build of record | `pnpm run build` | see below |

**Typecheck was red on arrival, on ten errors in one lane's files.** All the same shape:
`noUncheckedIndexedAccess` types an index read as possibly `undefined`, and the reads were being
passed straight into non-optional slots (`8a1f84ac`). The one that mattered was `Tree.tsx`'s
`openBranches` typed as `Record<string, boolean>` — an index signature makes every read
`boolean | undefined`, and `<Branch open=…>` wants a boolean. The component renders exactly three
branches, so they are now named in a type. **A `Record<string, T>` for a fixed, known key set is a
type that has thrown away the thing worth knowing.**

**The `--help` gate row was vacuous, and the gate is where that showed.** `loader.sh` checked for
`docker` and for a running daemon as the very first thing it did, so `./loader.sh --help` exited 1
on a machine with the daemon down — and
`tests/test_launch.py::test_loader_sh_in_a_checkout_runs_the_checkout`, which asserts `--help` exits
0, had been passing only because every previous gate machine happened to have Docker running. Fixed
at the cause: the preconditions run for a *run*, not for `--help`, and the test now runs with a
`docker` shim whose daemon is down, verified red against the previous script. **A precondition
placed at the top of a script is a precondition on every one of its verbs, including the ones that
do nothing.**

**Three e2e specs had been red on the branch since `509100ef`**, all driving `viewer-select-kind` /
`viewer-select-simulation` — testids deleted when the Menu became a composition tree. Fixed at the
cause in `8b82ee43` and `611fb54f`; see `HISTORY.md` § 2026-09-07 (evening).

**The quiet-check's focus leg failed on every run, and its window leg passed on every run.** It
reported `FAIL — a test binary held the focus` while also reporting *no new Electron/Chromium window
reached the screen* — the same split CX8 recorded, from the same cause: the offscreen Electron
becomes the frontmost *process* without ever showing a window, on a desktop a human is also using.
**The window leg is the assertion that means something; the focus leg is advisory on a shared
machine.**

#### Viewer resolve latency and the group-analysis run

Carried forward from the lanes that measured them, not re-measured here (the real leg is unrun):

| Measurement | Before | After |
|---|---|---|
| Viewer selection → resolved file list | **16.4 s** | **28 ms** |
| Group analysis, three subjects, mesh space | — | see the results lane's own row above |

The 16.4 s → 28 ms figure is a ~590× reduction and is the single largest latency change in the v3
work; it is what makes the Menu a thing you edit rather than a form you submit.
