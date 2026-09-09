# Verification and performance evidence

[CONTRIBUTING.md](CONTRIBUTING.md) owns commands and gate requirements;
[RELEASE.md](RELEASE.md) owns current readiness. This page retains useful measurements and their
limits, not a running count of every test invocation. Git history and ignored local receipts retain
superseded runs. Local `/tmp` and ignored receipt paths are provenance pointers, not durable
artifacts guaranteed to exist; use the named committed suites and CONTRIBUTING to reproduce
checks. Add or replace evidence when it changes a decision or closes a milestone.

These are dated observations, not fresh verification of every later commit. Unless stated
otherwise, performance measurements used an Apple M2 host with an amd64 container under emulation,
Dataset 000/sub-ernie. Emulated timings do not predict native performance. Host tests mock heavy
scientific dependencies; they do not substitute for real-library or artifact acceptance.

## Development closeout checks — 2026-09-09

The last recorded clean internal artifact used source `b06b4493bea5aa4834c107fe60301fcd9075afe1`:
image `sha256:01d66ed257f0341f8467e31e9cd4d1dc3197cefb448812ded00e05931fffa5b6`;
wheel SHA-256 `3e740a7b7253576856e70797fc825163e8365e6803086551ea0a98c6729f6f56`
(14,962,142 bytes). Later source/UI fixes are not certified by that pairing. No image or installer
publication was established by these checks. Receipts below are under ignored `dist/internal/`.

| Check | Recorded result | Evidence and limit |
|---|---|---|
| `.venv/bin/python -m pytest tests/ -q` | 4,769 passed, 46 skipped, 21 deselected; 107.17 s | `host-pytest-develop-final.log`; source validation |
| Desktop typecheck, lint, `npx vitest run` | 1,516 tests / 119 files passed; typecheck passed; lint 0 errors, 3 existing warnings | `desktop-*-followup.log` |
| Full functional mock suite | 364 passed, 1 skipped, 0 failed; 6.1 min | `mock-e2e-current-contract.log`; not native visibility certification |
| Baked numerical, boundary and Blender tests | 223 passed, 1 skipped; 61.68 s | `baked-develop-tests.log`; selected suite, not all real jobs |
| Linux containment checks | 107 passed; final unset-project control 17 passed | `develop-linux-boundaries.log`, `catalog-linux-develop-final.log` |
| Route and contract guards | 24 routes; 114 operations / 136 schemas; 244 existing contract warnings | `routes-develop.log`, `contracts-develop.log` |
| Python dev loader without repo mount; installed wheel | Healthy clean-image container; wheel attached, exit 0 | `dev-loader-develop-receipt.json`, `wheel-develop-receipt.json` |

The packaged YAML repair passed actual Browse → Start with a dirty-source app and an earlier
clean security image: 1224 × 720 renderer, no source/UI mounts, zero jobs. App samples showed no
visible/focused window, but the native monitor exited **2, inconclusive** because short-lived
process ancestry was unresolved. This demonstrates a functional repair, not final installer or
quiet-check acceptance. A failed full suite is never waived by an isolated pass.

## Clean baked candidate progress — 2026-09-09

Historical comparison, **superseded by subsequent security and source fixes**: source
`e3bee214cea67be1f0867b74aceaf9c718c9eaf3`, image
`sha256:56faec6cecce2c1645a8895f75d01ff2125eb006abb6b9152e03704573e8b0c9`.
The recorded real run passed 42 tests in 35.8 min, including a 16.7-minute simulation/analyzer
pipeline and an EEG forward job of 727.9 s with three artifacts. It excluded docs-shots,
scene-atlas-border and scene-electrodes; it was not every real-project spec. Native monitor exit
2 remained inconclusive, with no attributed test-descendant failure.

Receipts: `dist/internal/real-final-baked.log`, `real-final-baked-receipt.json`,
`image-receipt-before-security.json`. The image's local `.Size` was 2,403,717,605 bytes while
`docker image ls` displayed 9.27 GB. Neither establishes compressed registry transfer size, and
neither is a current-image measurement. A local `RepoDigests` entry is not proof of publication.

## Latest scoped evidence — 2026-09-09

These later checks cover their named changes, not a new complete release gate.

| Scope | Reproduction / receipt | Recorded result |
|---|---|---|
| Latest full host refresh before later UI/dev changes | `.venv/bin/python -m pytest tests/ -q`; `/tmp/tit-loader-host-tests.log` | 4,788 passed, 46 skipped, 21 deselected; 113.87 s |
| Frontend forms/mapping/folder changes | `npx vitest run`; `/tmp/tit-touchup-final-unit.log` | 1,568 passed / 123 files; 22.93 s |
| Developer attach | `python3 -m pytest tests/test_launch.py tests/test_launch_image.py tests/test_loader_interactive.py -q`; `/tmp/tit-dev-loader-tests.log` | 98 passed; desktop dev/stack checks 66 passed |
| Live dev loop | `pnpm dev:web`; checkout/import/source-hash inspection | Current checkout at `/ti-toolbox`, reload enabled, frontend HTTP 200 and proxied API healthy; Python/Bash attach succeeded |
| Overwrite handoff | `python3 -m pytest tests/test_jobs_manager.py tests/test_jobs_routes.py tests/test_pipeline_routes.py tests/test_plan_routes.py tests/test_sim_pipeline.py tests/test_sim_utils.py -q`; `/tmp/tit-overwrite-integrated.log` | 221 passed, one warning; 21.43 s |
| Native SimNIBS overwrite guard | `simnibs_python -m pytest tests/numerical/test_sim_overwrite.py -q`; `/tmp/tit-overwrite-real.log` | 1 passed; real SESSION existence guard with stubbed FEM, not a numerical simulation |
| Overwrite UI | `/tmp/tit-overwrite-*` receipts | 44 focused units and 7 selection e2e passed; final rerun/dialog/pipeline follow-up 17 passed |
| Plugin process protocol | `python3 -m unittest discover -s agent-plugin/mcp -p 'test_*.py' -v` | 3 passed: real offline process outside checkout, discovery, call/error recovery |
| Plugin tools | `TI_TOOLBOX_OFFLINE=1 python3 agent-plugin/mcp/server.py --selftest` | 14 tools / 15 calls passed; native-client conversation not tested |
| Documentation | Release-docs MkDocs/Jekyll builds; `dist/internal/site-release-docs-receipt.json` | 314 HTML pages, 12,184 local href/src references, 0 missing files; 5 HTTP routes passed |

The overwrite live check returned 409 without creating a job when confirmation was absent;
it did not change project settings or rerun user outputs. Typecheck, targeted lint and final plain
renderer builds passed for these UI changes. The latest selection e2e native monitor still exited
2 (20 samples, unresolved ancestry): no reported window/focus violation, visibility certification
**unverified**. Documentation warnings and security/hosted acceptance belong to RELEASE; no local
count clears a hosted alert or certifies another source revision.

## Progressive viewer loading

One before/after observation on the same six-volume selection, 149.07 MB compressed, 2026-09-09:

| Behavior | Before | After |
|---|---|---|
| First visible layer | 9.211 s | 4.124 s |
| All six layers | 9.211 s | 4.800 s |
| Add four volumes after two loaded | — | Four new raw-file requests; original dataset IDs retained |
| One missing file | — | Error retained alongside the successfully loaded T1 |

Receipts: `dist/internal/tetravox-six-volume-{baseline,progressive}.json`,
`tetravox-incremental-receipt.json`, `tetravox-partial-failure-receipt.json`.
Locally installed embed source `3b16a47ec1235640f5f392f71a609cc80dce75ed`, archive SHA-256
`298e9247e0ed55ec3e36780ceea7c0f5b2ed65760e6f46cc3e2390e5f8e37048`.
This is not a cross-platform benchmark or evidence of an updated baked image.

## Scene and catalog performance

Historical 2026-09-04–07 measurements; use the corresponding real specs under
`desktop/tests/e2e/real/` with the current CONTRIBUTING harness to refresh them.

| Measurement | Observation / limit |
|---|---|
| Reference mesh | 184 MB; 847,165 nodes / 5,899,838 elements; 1.7 s in-container read |
| Packaged guide with TVSC1 labels | 18.44 MB; 8.4 s build; surfaces bounded at 150k triangles / 3 MB each |
| Real native pane first paint, warm | 91–219 ms |
| Orbit, 222,434 triangles | About 122 fps; 0.10–0.20 ms CPU/frame |
| Independent electrode picking | 1.086 mm error against 1.865 mm tolerance |
| Atlas border spikes | 8 / 129 crossings over 24 scan lines (6.20%) |
| Idle marker/scalp contrast | Worst 2/255, median 35 over 24 nearest markers; unresolved design limit |
| Overview, five subjects / 25 optimization runs | 3.4 s cold; 0.12–0.14 s warm; cold cost is manifest parsing |
| Viewer selection resolution | Previously 16.4 s; about 14–28 ms with persisted statistics/cache; first-ever resolve remained about 10.2 s |

Scene timings measure rendering, not scientific correctness. Warm cache and first-ever load are
different conditions. Full-data percentiles remain exact; cached identities use file size/mtime.

## Blender and montage output

The September 8 full-net `ernie/L_Insula` Blender export was reopened successfully: 378 objects,
185 meshes, 668,092 base vertices and six cameras; 69,387,270-byte scene. Scientific preparation
retained its own NumPy environment. The successful capped run used 12 GiB RAM plus about 1 GiB
swap; this is not an uncapped peak. Earlier 3 and 8 GiB attempts were OOM-killed. The resulting
montage reservation is 16 GiB; lightweight exports retain their separate budget.
Reproduce through the real montage job and `tests/test_blender_process_boundary.py` with its
real-Blender environment gate; use the saved job config for full-subject comparisons.

September 9 montage overlay regression: 17 real-container tests passed, including PNG decoding
and atomic failure. Colored pixel counts near four named electrodes were 2311/2178/2341/2357
against a 50-pixel threshold. The prior blank images matched the base template byte-for-byte.
Receipt: `/tmp/tit-montage-container-tests.log`; backups `dist/internal/montage-repair/`.

## Scientific validation

Numerical regression coverage is in `tests/numerical/`, using real libraries and independent
reference calculations. Run it with the container command in [CONTRIBUTING.md](CONTRIBUTING.md).
Affected historical workflows and user actions belong solely in the
[release notes](../releases/v3.0.0.md#scientific-corrections).

### FastSurfer and parked native runtime

September 3, one Apple M2/sub-ernie only: FastSurfer CPU `--seg_only`, eight threads, 292 s
inference / 392 s end-to-end, peak RSS 4.84 GiB. Mean Dice against recon-all: 0.922 over 14
subcortical labels and 0.914 over 20 cortical DKT labels. Centroids mostly shifted less than
1.5 mm, with pallidum 3–4 mm. This is a single-subject comparison, not segmentation validation;
the shifts matter particularly for small ROIs. Spike scripts were retired; these observations
cannot be refreshed through a retained dedicated benchmark command.

The parked native runtime completed a real two-pair simulation in 366.49 s and matched emulated
amd64 TI_max mean/max to 13–14 significant figures. Native DK40 atlas output was byte-identical.
Nearest-neighbor Python resampling differed from `mri_convert --reslice_like` in 0 of 13,631,488
voxels; replacement segmentation statistics matched label IDs/counts on four atlases. These
historical results support the recorded design choices, not native-platform release certification.
