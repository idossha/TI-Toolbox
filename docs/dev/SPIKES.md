# Native-desktop spike verdicts — 2026-09-03

Six throwaway spikes (lanes N0.1–N0.6) asked whether TI-Toolbox could ship as a
single native Electron executable with no Docker, no X11 and no FreeSurfer. The
track was **parked**; v3 ships as Electron + one Docker image. The spike *code*
(build scripts, comparison harnesses, manifests, live-verify drivers) was never
shipped and has been deleted — these verdicts and their numbers are what
mattered, and this file is the only surviving record of them. Everything below
was measured on one Apple M2 Mac; no x86_64 or Windows machine was ever used.

Program context: `docs/dev/HISTORY.md`, section
"2026-09-03 — Native desktop research (parked)".

## runtime (N0.1) — proven, numerically exact

A pip + python-build-standalone runtime (no conda) with SimNIBS 4.6.0 + `tit`,
2.0 GB installed without bpy. A real two-pair TI simulation on sub-ernie ran in
366.49 s (6.1 min) and matched the emulated x86_64 container to 13–14
significant figures (TI_max mean 0.14605754393982354 native vs
0.14605754393982395 emulated; max 10.29371206441698 vs 10.293712064403254).
`subject_atlas` DK40 output was byte-identical (sha256) and 1.7× faster. FEM
assemble/solve per pair 6.3/4.8 s native vs 6.8/5.3 s emulated. `import simnibs`
2.2–2.3 s warm, 27.1 s cold.

Corrections to the brief: SimNIBS's default solver is **hypre on every
platform**, not a platform-conditional pardiso/MUMPS. Two real upstream
packaging defects were worked around by scripted grafts: `python-mumps` has no
PyPI wheel on any platform (built in a throwaway micromamba env, 27 MB grafted
via `install_name_tool`), and SimNIBS's macOS CGAL extensions carry the
developer's absolute `LC_RPATH` (`/Users/axelt/miniforge3/...`), fixed by
grafting libmpfr/libgmp and rewriting the rpath.

Per-package sizes: simnibs 384 M (219 M of that atlases), torch 345 M, PyQt5
136 M, llvmlite 113 M, scipy 100 M, sympy 77 M, pandas 73 M, samseg 60 M,
petsc4py 45 M, numpy 36 M. Windows and Linux x86_64 wheel sets resolve (HTTP
200, correct sizes) but were never installed or run.

## fastsurfer (N0.2) — viable, with a measured accuracy tax

FastSurfer 2.5.4 `--seg_only` on CPU: ~5 min per subject (292 s inference,
392 s end to end, 8 threads), 4.8 GiB peak RSS, 67 MB of checkpoints. Against
real `recon-all` on sub-ernie (n=1): mean Dice **0.922** over 14 subcortical
labels and **0.914** over 20 cortical DKT labels. Centroid shifts mostly
&lt;1.5 mm, with a pallidum outlier at 3–4 mm and one cortical outlier at 3.1 mm —
negligible for 10–15 mm ROI spheres, a real caution at 5 mm. torch 2.7.1 is
compatible with SimNIBS's `torch>=2.1`. Production use needs `--no_cc`.
Single-subject evidence only.

## fs-binaries (N0.5) — proven, exact replacements, zero remaining calls

- `mri_convert --reslice_like` → `nibabel.processing.resample_from_to(order=0)`:
  **0 of 13,631,488 voxels differ** across two real atlases (0.3 s).
- `mri_segstats` → `tit/atlas/segstats.py`: exact label-id and voxel-count match
  across four real atlases (102/102, 188/188, 48/48, 56/56).
- nilearn's runtime fsaverage download → 18 MB of SimNIBS's own bundled
  fsaverage vendored under `resources/fsaverage/{5,6,7}` (vertex/face counts
  verified).
- `rg 'mri_convert|mri_segstats' tit/atlas tit/analyzer` returns zero hits.

Known gap: the bundled `FreeSurferColorLUT.txt` is 2012-vintage and lacks
thalamic-nuclei (8100-series) display names; ids and volumes are still exact.

## job-control (N0.6) — proven on POSIX, Windows monkeypatch-tested only

`tit/jobs/processes.py` gives Windows-safe spawn (`CREATE_NEW_PROCESS_GROUP`)
and psutil-based kill that never calls `signal.SIGKILL` (which does not exist on
Windows), alongside unchanged POSIX behaviour. QSIPrep/QSIRecon containers now
carry `--label tit.job_id` / `--label tit.kind`, fixing a real dead-code bug in
which cancel never worked for them. `tit.paths.resolve_resource_path()` replaced
three hard-coded `/ti-toolbox` paths with env → container → checkout resolution.
208 tests, container run green; no Windows machine was available, so the Windows
branch was exercised only by monkeypatching.

## docker (N0.3) — proven live against a real engine

Dependency-free typed Docker Engine API clients (Node over `http` on a unix
socket / named pipe; Python over `http.client` on `AF_UNIX`), replacing dockerode
and CLI output parsing except for `docker context inspect`, which is still used
for endpoint discovery. Live-verified against Docker Desktop 4.57 / Engine
29.1.3 / API 1.52: NDJSON pull progress (10 events, 1.4 s cold), create → start →
demultiplexed logs → wait with an exact exit code 3, the events stream, and a
`tit.job_id` label round-trip. 37 vitest + 30 pytest tests. Not tested: the
Windows named pipe, and Podman/Colima compatibility sockets.

## packaging (N0.4) — proven end to end on macOS arm64 only

`electron-builder --dir --mac --arm64` produced a 468 MB `.app` (175 MB minimal
runtime + 286 MB Electron) that spawned the bundled `tit.server`, answered
health and had its whole process tree gone 2 s after quit;
`native-launch.spec.ts` passed under the offscreen quiet check. Ad-hoc signing
38 Mach-O binaries in 165 MB took under 1 s (the scan took 16 s), extrapolating
to single-digit minutes for a full runtime. Two real defects found and fixed:
electron-builder 26.15 resolves `extraResources.from` *before* expanding
`${env.X}`, and `codesign --options runtime` without entitlements silently
breaks every C-extension import. The full 2–3.5 GB runtime and Developer ID
notarization were never attempted.
