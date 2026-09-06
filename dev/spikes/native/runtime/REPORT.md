# N0.1 — Native SimNIBS runtime on macOS arm64 — Stage N0 spike report

Status: **proven** (materialised by the orchestrator from the lane's structured return, 2026-09-03; the lane could not write files named REPORT.md).

## Headline

A pip + python-build-standalone (NOT conda-packed) SimNIBS 4.6.0 + tit runtime runs natively on this M2 Mac. import simnibs works (warm 2.2-2.3s repeat; 27.1s on the very first import after grafting, likely ad-hoc-codesign/dyld-cache warmup); tit.sim/tit.opt import in 9.6s; tit.server answers a real /api/health (200 OK) and dumps 56 OpenAPI routes; subject_atlas output is BYTE-IDENTICAL (sha256 match on both lh/rh DK40 .annot files) to the emulated x86_64 container's; and a REAL two-pair TI simulation on sub-ernie (F7-P7/F8-P8, EEG10-10_Cutini_2011 net, scalar conductivity, 1.0/1.0 mA — the exact montage from the dataset's pre-existing "Thalamus" run) completed in 366.49s wall (6.1 min) with whole-mesh TI_max mean=0.14605754393982354 V/m, max=10.29371206441698 V/m — matching the container's existing result (mean=0.14605754393982395, max=10.293712064403254) to ~13-14 significant figures, despite a completely different distribution channel (pip+wheels vs. upstream's conda-packed installer), CPU architecture (native arm64 vs. emulated x86_64-under-QEMU) and OS (macOS vs. Linux container). Two genuine upstream packaging defects were found and fixed with small, scripted, reproducible workarounds (both documented loudly per the brief, not swept under the rug): (1) python-mumps has NO PyPI wheel on ANY platform (sdist only; needs compiled MUMPS/SCOTCH/METIS C/Fortran libs at build time) — resolved by building it in a throwaway micromamba/conda-forge env (never shipped) and grafting the compiled extension + its 21-dylib transitive closure into the pip runtime via install_name_tool, verified working standalone (ctx.factor()/ctx.solve() on a 2000x2000 sparse system, 0.06s). (2) The SimNIBS 4.6.0 macOS-arm64 wheel's 3 CGAL Cython extensions carry a non-relocatable, hardcoded absolute LC_RPATH pointing at the SimNIBS developer's own build machine (/Users/axelt/miniforge3/envs/simnibs_dev/lib) — fixed the same way (graft libmpfr/libgmp + add a working rpath). IMPORTANT CORRECTION to the Stage N0 brief's premise: SimNIBS 4.6's default TES FEM solver is "hypre" (PETSc CG+BoomerAMG) on EVERY platform per simnibs/simulation/fem.py source (VALID_SOLVER_OPTIONS default), NOT platform-conditional pardiso-vs-mumps — both the native and container simulation logs show "Using solver options: hypre". MUMPS itself works fine once grafted but is simply not SimNIBS's default anywhere; it is available as an explicit opt-in. win_amd64 and manylinux_2_28_x86_64 wheel sets fully resolve (all 6 GitHub-release/PyPI URLs per platform, HTTP 200, real sizes matching upstream's yml) but were NOT installed or run — no x86_64 machine was available in this spike, so those two platforms' packaging-defect status (does the same rpath bug exist? does the same mumps graft work?) remains unverified by analogy only. charm itself (--help + simnibs.segmentation import only) was proven at the CLI-exists level; a full ~1h charm run was not attempted — time went to the higher-signal proof (a real completed TI simulation with numerically-matching output) instead.

## Measured numbers

- runtime-macos-arm64/ total size: 2.0 GB (no bpy) — `du -sh runtime-macos-arm64`
- python-build-standalone download: cpython-3.11.16+20260901-aarch64-apple-darwin-install_only.tar.gz, 27,087,450 B, sha256 50424fa409e8ae84b82a3052522f64695b47dff2158b70bb7358e0ebd6c085c9
- simnibs wheel: 184,051,752 B, sha256 fd312341f6de77586f9574458122f4eea2f6d57b9a0ea4ad1b982fee42715dea (v4.6.0 macosx_11_0_arm64, from github.com/simnibs/simnibs releases)
- interpreter cold start (no imports): 0.01-0.03s across 3 runs — `time python3 -c pass`
- import simnibs: first import after grafting 27.12s; repeat/warm imports 2.27s and 2.21s — `/usr/bin/time -l python3 -c 'import simnibs'`
- import tit.sim, tit.opt: 9.61s (first import, pulls in the simnibs+torch chain)
- pip check across ~65-package closure: 'No broken requirements found.' (exit 0)
- tit.server --dump-openapi: 0.44s wall, 234,308 byte output, 56 API paths
- tit.server /api/health: HTTP 200, {"status":"ok","uptime_s":1.864}
- subject_atlas DK40 native: 2.27s wall; container (docker exec tit-v3-spike, amd64-under-QEMU): 3.91s wall — native ~1.7x faster (single run each, not a controlled benchmark)
- subject_atlas output sha256: lh.ernie_DK40.annot c560cd1ea68057aab6617515f787d15178bfd6fe8d10f466e0bd8516e5f0fd9c IDENTICAL native vs container; rh.ernie_DK40.annot 948fe15617964ef7bae063c20a122e8a236b5fe5e0d5850865561e98769acc01 IDENTICAL native vs container
- native TI simulation (F7-P7/F8-P8, sub-ernie): total wall 366.49s (6.1 min), user 579.12s (multi-core), sys 55.54s — `/usr/bin/time -p python -m tit.sim config.json`
- FEM assemble/solve per pair, native vs container(pre-existing log, same montage): pair1 assemble 6.35s vs 6.77s, solve 4.82s vs 5.32s; pair2 assemble ~6.3s vs 6.76s, solve ~4.9s vs 5.63s — solver in both cases 'hypre'
- native TI_max whole-mesh (n=5,899,838 elements): mean=0.14605754393982354 V/m, max=10.29371206441698 V/m; container's pre-existing Thalamus result: mean=0.14605754393982395 V/m, max=10.293712064403254 V/m — agree to ~13-14 significant figures
- MUMPS standalone verification: Context().factor()+.solve() on a 2000x2000 identity*2 sparse system, 0.06s, correct result (0.5 everywhere) — grafted mumps/ package 27 MB (extension + 21-dylib closure)
- throwaway micromamba build env (mm/mumbaenv, never shipped): 302 MB, built in ~18s + a follow-up mpfr install ~2s
- per-package sizes in runtime (du -sh): simnibs 384M (219M atlases), torch 345M, PyQt5 136M, llvmlite 113M, scipy 100M, sympy 77M, pandas 73M, samseg 60M, brainnet 59M, sklearn 47M, petsc4py 45M, numpy 36M, brainsynth 34M, numba 31M, OpenGL 30M, matplotlib 30M, mumps(grafted) 27M, nilearn 25M, mne 25M
- win_amd64 wheel HEAD checks: all 6 URLs HTTP 200 (simnibs 189,428,894B; petsc4py 11,279,399B; fmm3dpy 7,109,898B; cortech 1,361,843B; samseg 47,528,222B; torch+cpu 206,540,444B)
- manylinux_2_28_x86_64 wheel HEAD checks: all 6 URLs HTTP 200 (simnibs 188,305,161B; petsc4py 25,252,811B; fmm3dpy 6,371,594B; cortech 1,882,346B; samseg 51,144,128B; torch+cpu 178,655,896B)
- charm --help: real usage text printed, matches container's charm --help shape; python -c 'import simnibs.segmentation' exit 0 — full charm run NOT attempted (time-boxed out)

## Files changed

- /Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/dev/spikes/native/runtime/build-runtime.sh (new)
- /Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/dev/spikes/native/runtime/graft_mumps.sh (new)
- /Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/dev/spikes/native/runtime/graft_cgal_libs.sh (new)
- /Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/dev/spikes/native/runtime/resolve-other-platforms.sh (new)
- /Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/dev/spikes/native/runtime/manifest-macos-arm64.json (new)
- /Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/dev/spikes/native/runtime/manifest-win_amd64.json (new)
- /Users/idohaber/01_production/TI-toolbox/.claude/worktrees/v3-electron-gui/dev/spikes/native/runtime/manifest-manylinux_x86_64.json (new)
- NOTE: REPORT.md was NOT written as a file — the Write tool explicitly refused it ('Subagents should return findings as text, not write report files') both in the scratch path and (untried, by inference) the repo path. The full report content (verdict, per-proof-point detail, the two packaging-defect writeups, sizes, what this does/does not prove, Stage N1 follow-ups) is included in this structured response's headline/numbers/verification/followups fields instead — the orchestrator should persist it if a REPORT.md file is still required for the N0 gate.
- git status: all of the above are untracked new files under dev/spikes/native/runtime/ (git add/commit not performed, none was requested)

## Verification

- python3 -c "import simnibs; print(simnibs.__version__)" -> '4.6.0', exit 0, repeat-run 2.2-2.3s
- python3 -c "import tit.sim, tit.opt" -> exit 0, 9.61s
- python -m pip check -> 'No broken requirements found.'
- python -m tit.server --project /Users/idohaber/datasets/000 --dump-openapi out/openapi.json -> 56 paths, 234308 bytes
- python -m tit.server --host 127.0.0.1 --port 8791 --token spike-native (background) + curl -H 'Authorization: Bearer spike-native' http://127.0.0.1:8791/api/health -> HTTP 200 {"status":"ok",...}
- subject_atlas -a DK40 -o out/atlas_native m2m_ernie (native) vs docker exec tit-v3-spike subject_atlas ... (container) -> shasum -a 256 on both lh/rh .annot: IDENTICAL hashes
- python -m tit.sim config.json (real SimulationConfig built via tit.config_io.serialize_config, F7-P7/F8-P8 montage, project_dir pointed at a scratch tree with m2m_ernie symlinked in, Simulations/ output fresh — nothing written into the real dataset) -> exit 0, 'SimNIBS simulation: Complete', TI mesh written
- simnibs.mesh_io.read_msh(...Thalamus_repro_TI.msh).field['TI_max'] mean/max computed with numpy, compared against the same computation run in-container (docker exec ... simnibs_python -c ...) on the dataset's pre-existing Thalamus/F7-P7-F8-P8 result -> agree to ~13-14 significant figures
- mumps.Context().factor()/.solve() on scipy.sparse identity matrix -> correct numeric result (0.5), 0.06s
- grep 'solver_options' in runtime's simnibs/simulation/fem.py -> default is "hypre" unconditionally; both native and container sim logs show 'Using solver options: hypre'
- curl -sIL HTTP HEAD on all 12 win_amd64 + manylinux_x86_64 wheel/torch URLs named in environment_windows.yml / environment_linux.yml (fetched live from the v4.6.0 GitHub release) -> all HTTP 200 with content-length matching expected wheel sizes
- api.anaconda.org/package/conda-forge/python-mumps + pypi.org/pypi/python-mumps/json -> confirms PyPI has sdist-only (no wheel, any platform), conda-forge has osx-arm64/osx-64/linux-64/linux-aarch64/linux-ppc64le/win-64 binary packages

## Blockers and risks

- REPORT.md could not be written as a file (harness blocks subagents from writing report/summary/findings .md files) — if the N0 gate literally requires a REPORT.md file on disk at dev/spikes/native/runtime/REPORT.md, the orchestrator (or a follow-up turn) needs to materialize it from this response's content; I did not attempt to route around the restriction.
- The samseg wheel this spike (and upstream itself) depends on comes from a third-party personal GitHub account (github.com/oulap/samseg_wheels), not simnibs org or freesurfer/samseg — supply-chain risk already flagged by r1, unchanged by this spike.
- Two upstream packaging defects (mumps: no PyPI wheel at all; simnibs CGAL extensions: non-relocatable baked-in rpath) mean the Stage N1 CI runtime build needs a micromamba/conda-forge step as a build-time-only helper, even though nothing conda-based ships in the final artifact — this is a real addition to the packaging plan's complexity, not just a one-line pip install.
- Windows x64 and Linux x86_64 are proven only at 'every wheel URL resolves with the right size' — installation, pip check, import, and simulation were NOT attempted on either (no x86_64 machine available). Whether the same two packaging defects (or platform-specific equivalents) exist there is unverified, only plausible by analogy.
- bpy was intentionally not installed (out of scope per the brief) — tit.blender's native-runtime story is completely unverified by this lane.
- A full charm run (~1h, needed to test the FreeSurfer-free head-model reconstruction path that is the maintainer's core question) was not attempted at all — not even started in the background — because the time budget went to completing the harder, higher-signal TI-simulation proof plus writing up the two packaging-defect workarounds properly.
- The 27.1s first-import cost (vs 2.2s warm) after grafting is unexplained beyond a hypothesis (ad-hoc codesign verification + dyld shared-cache population over ~40 newly copied/relinked Mach-O files) — not root-caused, and a packaged app's real (Developer-ID, not ad-hoc) signing may have a different cost profile entirely; r4's walk-and-sign step should measure this for real.
- Timing comparisons throughout (subject_atlas, TI simulation FEM assemble/solve) are single runs against a single pre-existing container log, not a repeated/controlled benchmark on this same Mac at the same time — directionally informative only, not rigorous.

## Follow-ups for Stage N1

- Fold micromamba into the Stage N1 CI pipeline as a build-time-only step reproducing graft_mumps.sh + graft_cgal_libs.sh for all 3 platforms (never ship a conda environment in the final artifact).
- Verify the same two workarounds (or find Windows/Linux-specific equivalents) on real x86_64 Linux and Windows CI runners — this spike proved wheel resolution only, not installation, for those platforms.
- Decide whether to mirror oulap/samseg_wheels (and the now-relinked SimNIBS CGAL extensions + grafted mumps package) into TI-Toolbox's own release assets — doubly justified now since upstream's own wheels need post-install patching anyway, so vendoring an already-fixed copy is a real N1 option, not just a supply-chain hedge.
- Run a full charm reconstruction on sub-ernie natively in the background (~1h) and diff labeling.nii.gz/surfaces against the container's existing charm output — this lane's brief marked it optional and time ran out on it entirely (not even started).
- Root-cause the 27s cold-import cost after grafting (ad-hoc codesign / dyld shared-cache hypothesis, unverified) — a packaged app should pre-warm this at install/build time; measure it again once proper Developer-ID (not ad-hoc) signing is in place per r4's walk-and-sign step.
- Have the parent orchestrator materialize this response's report content as dev/spikes/native/runtime/REPORT.md if the N0 gate requires an on-disk file — I could not write it directly.
