# TI-Toolbox native desktop — feasibility verdict and plan of record (2026-09-03)

Answers the maintainer's question: *"completely remove the x11, freesurfer, gmsh dependencies and
just have our codebase, tetravox, and simnibs compiled into a desktop electron executable that can be
deployed on linux, windows, mac like tetravox or SUNA. realistic?"* — plus a FreeSurfer-free
parcellation and a native Docker integration.

Evidence: six research reports and three adversarial reviews in `dev/notes/v3-native-research/`
(r1 SimNIBS packaging · r2 FreeSurfer audit · r3 parcellation alternatives · r4 Python-in-Electron ·
r5 Docker · r6 native dependency audit · skeptic-1/2/3). Every claim below cites one of them; claims
marked **SPIKE** are not yet proven and are what Stage N0 exists to prove.

## 0. Verdict

**Realistic, with three precise corrections to the wording.**

| Wish | Reality (verified) |
|---|---|
| "compiled into an executable" | A **bundled, signed private Python runtime** (python-build-standalone 3.11 + SimNIBS's own wheels + our package) launched by Electron as a child process — the same `tit.server` + `python -m tit.<module>` contract the container uses today. Freezing (PyInstaller/Nuitka) is not viable: SimNIBS spawns sibling binaries, ships Cython/CGAL extensions and package data (r4). |
| "linux, windows, mac" | **Linux x86_64, Windows x64, macOS Apple Silicon.** No native macOS Intel: bpy ≥5, torch 2.6 and SimNIBS's petsc4py fork all ship no x86_64-mac wheels (r4, re-verified by skeptic-1); SimNIBS itself discontinued Intel Mac at 4.5 (r1). No Linux/Windows ARM64 (no upstream wheels). Intel Mac keeps the existing Docker path. |
| "like tetravox or SUNA" | Tetravox is ~100 MB; this app is **~2.5–3.5 GB installed** (SimNIBS 185 MB wheel + atlases 220 MB + torch-cpu 715 MB, a hard dependency of charm's FreeSurfer-free surface reconstruction + bpy 200–400 MB + numpy/scipy/mne/nilearn + interpreter) (r1, r4, skeptic-2). Auto-update must be component-wise, not whole-app. |
| "remove x11" | **Yes.** Freeview/Gmsh viewing is replaced by Tetravox (embedded as a service, `dev/notes/v3-ux-redesign-plan.md` §4); `desktop/src/main/x11.ts`, the X11 mounts and `xhost` go away. Gmsh as SimNIBS's *meshing* binary stays inside SimNIBS's wheel. |
| "remove gmsh" | Yes as a user-facing dependency; see above. |
| "remove freesurfer" | **Yes for the default pipeline.** charm is already FreeSurfer-free by construction (TopoFit surfaces, MIT-licensed samseg volumes); `subject_atlas` gives DK40 / Destrieux / HCP-MMP1 on the subject surface with no FreeSurfer present (verified live, 0.65 s); `labeling.nii.gz` carries FreeSurfer-identical aseg IDs for thalamus/hippocampus/putamen/caudate/pallidum/amygdala/accumbens; fsaverage (163,842-vertex ico7) ships inside SimNIBS (r2, skeptic-2). What FreeSurfer still uniquely supplies: (a) a **voxel-space cortical parcellation** (aparc.DKTatlas+aseg) → FastSurfer `--seg_only` (Apache-2.0, PyTorch, ~67 MB checkpoints, no FreeSurfer binaries) **SPIKE for accuracy and CPU time**; (b) **thalamic nuclei and hippocampal subfields** → no FreeSurfer-free tool exists; dropped from the default, kept only via optional Docker FreeSurfer. Two incidental binary calls (`mri_segstats`, `mri_convert --reslice_like`) are replaced with nibabel/scipy **with a validation against real recon-all output** (skeptic-2's conform/RAS caution). |
| "replace dockerode" | Already gone in v3 (`desktop/src/main/dockerCli.ts` shells out). The native design is a **dependency-free typed Docker Engine API client over the socket / named pipe** (Node in main; a stdlib Python one for DWI containers), not dockerode and not CLI text parsing. Podman/Colima/OrbStack compatibility is *not* free (Podman's compat socket is off by default, API 1.40, no default amd64 emulation) — supported engines are declared, not assumed (skeptic-3). |
| "no docker at all" | **Not achievable for DWI.** QSIPrep/QSIRecon are Linux containers with no native path on any OS (r5, r6, skeptic-1). Docker becomes an *optional capability* for DWI (and legacy FreeSurfer); the core app never needs it. |

**Already true today, verified:** `tit.server` + `tit.jobs` + catalog + analyzer + stats + reporting run on a bare Python 3.11 venv with no SimNIBS and no Docker (277 tests green) (r6). Only `tit.sim`, `tit.opt.*` and `tit.blender` import SimNIBS at module scope — the genuine boundary.

**Biggest risks, in order:** (1) nobody has assembled the native runtime and run a simulation on it yet — Stage N0.1; (2) macOS notarization of a multi-GB tree of Mach-O binaries — SimNIBS's own installer *avoids* it with a password-zip trick (r4); (3) FastSurfer accuracy/consistency vs the charm surface atlases is unmeasured; (4) SimNIBS's dependency supply chain: not on PyPI, wheels on GitHub releases, one (samseg) on a personal account — we pin by URL + sha256 and mirror them in our own release; (5) Windows job control: `tit/jobs/runner.py:213` calls `signal.SIGKILL` (AttributeError on Windows) and `start_new_session` is a no-op there; (6) QSIPrep cancel is dead code (no `tit.job_id` label is ever set) (skeptic-3).

License notes for a redistributed bundle: SimNIBS GPL-3 (compatible), samseg MIT, cortech GPL-3, FastSurfer Apache-2.0, Tetravox MIT; **ADMlib** inside the SimNIBS wheel is GPLv2 non-commercial (unused by our code) and **Intel MKL** has its own EULA on Linux/Windows — both need a decision before any commercial distribution (r1). Third-party notices ship in the app.

## 1. Target architecture

```
Electron app (per platform)
├─ desktop renderer (existing v3 UI)  ──iframe──▶  Tetravox Embed (released static bundle, /tetravox/)
├─ main: native launcher ──spawn──▶ resources/runtime/<platform>/bin/python -m tit.server --project <host dir> --port <free> --token <random>
│        docker client (Engine API over socket/npipe; optional capability)            │
└─ resources/runtime/<platform>/         (python-build-standalone 3.11 + site-packages)   ▼
       simnibs 4.6.0 wheel + cortech/brainsynth/samseg/petsc4py/mumps/fmm3dpy (SimNIBS GitHub-release wheels, pinned by sha256)
       tit + numpy/scipy/nibabel/mne/nilearn/bpy/torch-cpu + FastSurfer (seg_only) + vendored fsaverage
       charm atlases, MNI templates, EEG caps (SimNIBS package data)
Jobs: unchanged `python -m tit.<module> config.json` runners, now children of the native runtime; process-tree kill made Windows-safe.
Optional Docker (capability-gated): QSIPrep / QSIRecon (DWI), legacy FreeSurfer (subfields), future GPU FastSurfer.
```

Project directories are host paths (no `/mnt/<name>` mapping); `PathManager` stays, its root becomes the host directory.

## 2. Stages

### Stage N0 — Spikes (Sonnet lanes, parallel; this session; nothing merges without numbers)
| Lane | Proves | Deliverable |
|---|---|---|
| **N0.1 Native runtime (macOS arm64, this Mac)** | SimNIBS 4.6 runs natively from a python-build-standalone env; `subject_atlas` and a TI simulation on sub-ernie succeed; timings vs the emulated container; env size; mumps/petsc wheel status | `dev/spikes/native/runtime/{build-runtime.sh, requirements.lock, REPORT.md}` — the script is the seed of the CI runtime build |
| **N0.2 FastSurfer seg_only** | CPU runtime on ernie's T1 on this Mac; per-label Dice vs ernie's real recon-all `aparc.DKTatlas+aseg.mgz` and vs charm `labeling.nii.gz` for subcortical; torch 2.7 vs 2.6 compatibility; integration sketch as a `tit.pre` stage | `dev/spikes/native/fastsurfer/{run.sh, compare.py, REPORT.md}` |
| **N0.3 Docker Engine API** | Raw HTTP over the live socket: version/info, pull progress NDJSON, create/start/wait, multiplexed logs, events; `docker context inspect` discovery; a stdlib Python equivalent; a fake Engine-API server for tests | `desktop/src/main/docker/{engine.ts, discover.ts, frames.ts}` + `desktop/tests/unit/docker-engine.test.ts` + `tit/jobs/docker_engine.py` + tests |
| **N0.4 Packaging** | electron-builder config with a runtime dir as `extraResources`; main spawns the bundled server; packaged app answers `/api/health` in an offscreen e2e; measured `.app` size; ad-hoc walk-and-sign of the runtime tree (count, minutes) | `desktop/electron-builder.yml`, `desktop/src/main/nativeRuntime.ts`, `desktop/scripts/sign-runtime.sh`, `tests/e2e/native-launch.spec.ts`, `REPORT.md` |
| **N0.5 FreeSurfer binaries out** | `mri_segstats` and `mri_convert --reslice_like` replaced with nibabel/scipy, validated voxel-for-voxel against real recon-all outputs on ernie; nilearn's runtime fsaverage download vendored | changes in `tit/atlas/voxel.py`, `tit/analyzer/*`, `tit/stats/surface.py` + tests |
| **N0.6 Cross-platform job control** | Windows-safe `terminate_tree` (no SIGKILL; job objects/`taskkill /T`), `start_new_session` branch, QSIPrep `tit.job_id` label so cancel works, hard-coded `/ti-toolbox` + `/mnt` paths → package-relative | changes in `tit/jobs/runner.py`, `tit/pre/docker_builder.py`, `tit/tools/montage_visualizer.py`, `tit/atlas/constants.py`, `tit/blender/montage_publication.py` + tests |

Gate for N0: every lane's REPORT.md carries measured numbers; host pytest green; desktop typecheck/lint/vitest green; `npm run e2e:quiet` PASS.

### Stage N0 — RESULTS (2026-09-03; six Sonnet lanes, all "proven"; full reports in `dev/spikes/native/<lane>/REPORT.md`)

| Lane | Measured |
|---|---|
| **N0.1 native runtime** | pip + python-build-standalone runtime (2.0 GB without bpy) on this M2: `import simnibs` 2.2 s warm; **real two-pair TI simulation on sub-ernie in 366 s (6.1 min)**; TI_max over 5.9 M elements mean 0.1460575439398235 / max 10.2937120644 V/m, **identical to the emulated container's result to 13–14 significant figures**; `subject_atlas` DK40 output **byte-identical** (sha256) to the container's and 1.7× faster; FEM assemble/solve per pair 6.3/4.8 s vs 6.8/5.3 s emulated. Default solver is **hypre** on every platform (brief's pardiso/MUMPS premise corrected). win_amd64 and manylinux_2_28 wheel sets resolve (all 6 URLs each, sizes match upstream) but were not run. **Two upstream packaging defects, fixed by scripted grafts:** python-mumps has no wheel anywhere (built once in a throwaway micromamba env, 27 MB grafted with `install_name_tool`); the SimNIBS macOS wheel's CGAL extensions carry the developer's absolute `LC_RPATH` (`/Users/axelt/miniforge3/...`) — libmpfr/libgmp grafted + rpath added. Scripts: `dev/spikes/native/runtime/{build-runtime.sh, graft_mumps.sh, graft_cgal_libs.sh, resolve-other-platforms.sh}` + three wheel manifests with sha256. |
| **N0.2 FastSurfer** | v2.5.4 `--seg_only` natively on CPU: **~5 min** (292 s inference, 392 s end-to-end, 8 threads), peak RSS 4.8 GiB, checkpoints 67 MB. Versus real recon-all on sub-ernie: **mean Dice 0.922 (14 subcortical) / 0.914 (20 cortical DKT)**; centroid shifts mostly < 1.5 mm, pallidum 3–4 mm, one cortical outlier 3.1 mm — matters for 5 mm ROI spheres, negligible at 10–15 mm. torch 2.7.1 (FastSurfer) and SimNIBS's `torch>=2.1` do not conflict. Production invocation must add `--no_cc`. n = 1 subject. |
| **N0.3 Docker Engine API** | Dependency-free typed clients in Node (`desktop/src/main/docker/{discover,engine,frames}.ts`) and stdlib Python (`tit/jobs/docker_engine.py`), verified **live against Docker Desktop 4.57 / Engine 29.1.3 / API 1.52**: discovery via `docker context inspect`, NDJSON pull progress (10 events, 1.4 s cold), create/start/demuxed logs/wait (exit code 3 exact), events, `tit.job_id` label round-trip. 37 vitest + 30 pytest (also 29 in the container). Windows named pipe and Podman/Colima untested. |
| **N0.4 packaging** | `electron-builder --dir --mac --arm64` → **468 MB .app** with a 175 MB minimal runtime (Electron 286 MB); packaged app spawns the bundled `tit.server`, health OK, shell connects, process tree gone 2 s after quit; **`native-launch.spec.ts` PASS under the quiet check**. Ad-hoc walk-and-sign: 38 Mach-O in 165 MB signed in < 1 s (scan 16 s); extrapolated single-digit minutes for the full runtime. Two real findings: electron-builder 26.15 resolves `extraResources.from` before expanding `${env.X}` (worked around with `scripts/stage-runtime.sh`); signing with `--options runtime` **without entitlements silently breaks every C-extension import** while the app still launches — `scripts/sign-runtime.sh` passes `build/entitlements.mac.plist`. |
| **N0.5 FreeSurfer binaries out** | `mri_convert --reslice_like` → `nibabel.processing.resample_from_to(order=0)`: **0 / 13,631,488 voxels differ** on two real atlases (0.3 s); `mri_segstats` → `tit/atlas/segstats.py`: exact label-id and voxel-count match on four real atlases (102/102, 188/188, 48/48, 56); nilearn's runtime fsaverage download replaced by **18 MB of SimNIBS's bundled fsaverage** under `resources/fsaverage/{5,6,7}` (vertex/face counts verified). `rg mri_convert|mri_segstats tit/atlas tit/analyzer` → 0 hits. |
| **N0.6 job control** | New `tit/jobs/processes.py`: Windows-safe spawn (`CREATE_NEW_PROCESS_GROUP`) and kill (psutil, never `signal.SIGKILL`), POSIX unchanged (real spawn/kill integration tests); QSIPrep/QSIRecon containers now carry `--label tit.job_id/tit.kind` (cancel was dead code); `tit.paths.resolve_resource_path()` replaces three hard-coded `/ti-toolbox` paths (env `TIT_RESOURCES_DIR` → container → checkout). 208 tests; container run green. Windows branch exercised only via monkeypatching. |

**N0 gate:** host pytest 3122 passed / 17 skipped; desktop typecheck clean, lint 0 errors, vitest 43 files / 418 tests; build clean; full e2e under `scripts/e2e-quiet-check.sh` — see the session report for the PASS line.

**What N0 did not prove:** any x86_64 or Windows run (wheels resolve, nothing executed); a full charm run on the native runtime; the real 2–3.5 GB runtime through electron-builder and Developer ID notarization; FastSurfer on more than one subject; Podman/Colima; the Windows named pipe.

### Stage N1 — Go/no-go and build (after the maintainer reads N0)
1. Runtime build pipeline in CI (ubuntu x86_64, windows x64, macos-14 arm64): python-build-standalone + pinned wheels (SimNIBS GitHub releases mirrored into our own release assets with sha256) → `runtime-<platform>-<ver>.tar.zst`; cached; tested by running the host suite + a smoke simulation.
2. Native launcher replaces `stack.ts`/`compose.ts`/`x11.ts`: attach-or-spawn the bundled server, health, token, quit = process-tree kill; project directory = host path; capabilities report `native: true`.
3. Preprocessing: charm + `subject_atlas` default; FastSurfer `--seg_only` stage for voxel DKT; recon-all/subfields become an optional Docker feature ("Advanced ▸ FreeSurfer"); migration note for labs with existing recon-all derivatives (they keep working: the readers already accept both).
4. Docker: Engine-API client module used by the DWI feature only; onboarding UX for "not installed / not running / socket permission"; supported engines: Docker Desktop, Docker Engine; Colima/OrbStack "should work", Podman "unsupported" until tested.
5. Packaging + signing: electron-builder per platform; macOS walk-and-sign + notarization in CI (Developer ID already provisioned); Windows NSIS; Linux AppImage/deb; component download for the runtime on first run **if** installer size proves prohibitive (Tetravox-extension style).
6. Docs: installation without Docker; platform matrix; what needs Docker; what changed for FreeSurfer users.

### Stage N2 — Retire the container path for the core (keep `idossha/simnibs` for HPC/Jupyter use only).

## 3. Decisions recorded (ADR rows 18–21)
- **18** Deployment: native bundled runtime on Linux x86_64 / Windows x64 / macOS arm64; Docker optional for DWI and legacy FreeSurfer; Intel Mac stays on Docker.
- **19** FreeSurfer: not required by default; charm + `subject_atlas` + FastSurfer seg_only; subfield segmentation only via optional Docker FreeSurfer.
- **20** Docker integration: Engine API over socket/npipe with our own typed client; no dockerode; CLI only for `docker context inspect`.
- **21** Viewers: Tetravox Embed (already row 15); X11 removed from the product.

## 4. Open decisions for the maintainer
1. Intel Mac: accept "Docker only" there? (No native path exists upstream.)
2. Thalamic nuclei / hippocampal subfields: drop from the default, or keep an optional Docker FreeSurfer feature?
3. Commercial distribution: resolve ADMlib (non-commercial GPLv2 inside the SimNIBS wheel) and MKL EULA — or ship MUMPS-only builds.
4. Installer shape: one 3 GB installer vs a small app that downloads the runtime component on first run.
5. Supported container engines beyond Docker Desktop/Engine.
