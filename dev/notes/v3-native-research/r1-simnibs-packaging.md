# Lane R1 — Can SimNIBS 4.6 ship inside a desktop app on Linux/Windows/macOS (x86_64 + arm64)?

Evidence checked in ~45 min against: `/Users/idohaber/01_production/simnibs` (SimNIBS 4.6.0 source checkout), the `tit-v3-spike` container (`idossha/simnibs:v2.5.0`), PyPI JSON API, and SimNIBS's own GitHub releases/docs. Every claim below is tagged **VERIFIED** (I read the file, ran the command, or fetched the URL myself) or **REPORTED** (a doc/changelog says it, unconfirmed independently).

## Bottom line

SimNIBS 4.6 **cannot** be pulled in with a plain `pip install simnibs`, and it is **not** a self-contained wheel today. Upstream's own "advanced" install path is: create a **pinned conda-forge environment** (per-OS `environment_*.yml`), then `pip install` a SimNIBS wheel plus four more wheels hosted on scattered GitHub Releases (not PyPI) plus two packages built from git source at install time. The *official* distribution mechanism is literally "run `conda-pack` on that finished environment and ship the tarball" (`packing/pack.py`). That is exactly the shape of thing Electron can embed (a frozen, relocatable directory of a Python runtime + binaries, invoked via `child_process`/a bundled runner) — Tetravox-style bundling is realistic — but it is **not** "just add `simnibs` to a `requirements.txt` inside a PyInstaller/py2app build." Anyone re-bundling it has to reproduce SimNIBS's own conda-pack step (or vendor its output), not treat it as an ordinary pip dependency.

Per-OS wheel coverage is real and current (4.6.0, all cp311-only): **linux_x86_64, win_amd64, macosx_11_0_arm64**. There is **no linux_aarch64, no macOS Intel (explicitly discontinued as of 4.5.0), and no Windows ARM64** wheel anywhere upstream. The FEM solver story bifurcates by platform: Intel MKL Pardiso on Windows/Linux, MUMPS on Apple Silicon (Pardiso is documented as broken there).

For the maintainer's specific worry about FreeSurfer: **SimNIBS's own head-modeling pipeline (`charm` + `subject_atlas`) already does not need FreeSurfer.** It ships its own cross-platform, MIT-licensed segmentation stack (`samseg`) and, as of 4.6.0, an AI-based cortical-surface reconstruction (`brainnet`/`brainsynth`/`cortech`, PyTorch-based) that replaces the older CAT12-binary surface path. FreeSurfer only enters TI-Toolbox today as a **separate, optional, parallel pipeline step** (`tit/pre/recon_all.py`, `STEP_RECON_ALL`) that the DAG (`tit/jobs/plans.py`, `G2b`) runs independently of and in parallel with `charm` (`G2a`) — the core TI simulation path (`G3` tissue analysis, `sim/TI.py`, `sim/mTI.py`) depends only on `G2a`. That makes FreeSurfer/recon-all a clean, already-decoupled thing to swap out (a separate lane's problem, out of scope here, but the coupling is loose).

---

## 1. What upstream actually ships (VERIFIED)

### 1.1 `pyproject.toml` / `setup.py` (VERIFIED, read in full)

- `/Users/idohaber/01_production/simnibs/pyproject.toml`: `requires-python = ">=3.11"`, `license = "GPL-3.0-only"`. Dependencies list (`[project] dependencies`): `brainnet>=0.2, cortech, fmm3dpy==1.0.4, h5py, jsonschema, mkl ; sys_platform != 'darwin', nibabel, numba, numpy>=2, petsc4py, pillow, pygpc>=0.4.1, PyQt5, requests, samseg, scipy, tbb ; sys_platform != 'darwin', gmsh`.
- `/Users/idohaber/01_production/simnibs/setup.py` line ~44: **`if not is_conda: raise Exception("Cannot run setup without conda")`** — building SimNIBS from source is hard-gated on a conda environment (needs CGAL headers, Eigen3, mpfr, gmp, tbb from conda-forge at compile time). You cannot `pip install .` in a bare venv.
- `setup.py` defines 7 Cython/C++ `Extension()`s compiled per-OS: `simnibs.mesh_tools.cython_msh`, `simnibs.segmentation._marching_cubes_lewiner_cy`, `simnibs.segmentation._sanlm`, `simnibs.segmentation._thickness`, and three CGAL-linked ones (`mesh_tools.cgal.create_mesh_surf`, `create_mesh_vol`, `cgal_misc`) — CGAL/Eigen3/mpfr/gmp/tbb include & link paths pulled straight from `$CONDA_PREFIX`, with platform-specific compile flags (MSVC flags on win32, `-flto` on linux, `libc++` on darwin). This is a real per-platform native-build matrix, not a header-only convenience.
- The custom `build_ext_` command **deletes the other two platforms' bundled binaries** after compiling (`simnibs/external/bin/{linux,osx,win}` etc.) — confirms the wheel is platform-specific and that `simnibs/external` ships prebuilt binaries for all three OSes in the source tree but only one survives into any given wheel.

### 1.2 Bundled binaries in `simnibs/external/` (VERIFIED, `find`/`du`)

`/Users/idohaber/01_production/simnibs/simnibs/external/bin/{linux,osx,win}/` each contain: `CAT_Surf2Sphere`, `CAT_WarpSurf` (CAT12 surface tools, GPLv2+), `meshfix` (GPLv3+), `mmg3d_O3` (LGPL, remeshing), plus small helpers (`expr`, `getopt`) and platform runtime libs (`libstdc++.so.6` on linux, `libintl.8.dylib` on osx, `cygwin1.dll`/`cygblas-0.dll` on win — meshfix.exe needs Cygwin on Windows). Total size of all three platforms combined in the source tree: **50M** (`du -sh simnibs/external` = 50M). A plain shell wrapper `simnibs/external/dwi2cond` (12K) drives **FSL** for diffusion-based anisotropic conductivity — FSL is *not* bundled; SimNIBS's own docs (`docs/installation/optional.rst`) list FSL as an **optional** manual install, "Required by: dwi2cond" only.

### 1.3 Atlases / resources (VERIFIED, `du -sh`)

- `simnibs/segmentation/atlases/charm_atlas_mni_v1-0` = **79M**, `charm_atlas_mni_v1-1` = **141M** → **220M** of segmentation atlases alone (source tree; matches the container, see §2).
- `simnibs/resources/` = **111M** total: `templates/fsaverage_surf` 46M, `MNI152_T1_1mm.nii.gz` 10M, `fsaverage_atlases` 7.5M, `fsaverage40k_surf` 4M, EEG cap layouts, coil models, etc.
- `simnibs/_internal_resources/` = 30M (icons, sitecustomize.py for the packed installer, etc).

### 1.4 GPL-3 licensing sweep — `3RD-PARTY.md` (VERIFIED, read in full)

Compatible with TI-Toolbox's own GPL-3.0: SimNIBS core is `GPL-3.0-only`; CGAL (GPLv3+/commercial), gmsh (GPLv2+), meshfix (GPLv3+/commercial), pygpc (GPLv3), brainnet/brainsynth/cortech (GPLv3+, confirmed for `cortech` directly via `pip show` in the container: `License: GPL3`), CAT12 (GPLv2+), mmg (LGPL), MPFR/GMP (LGPLv3/GPLv2 dual). PETSc, NumPy, SciPy, nibabel, zlib, scikit-image, pyvista are permissive (BSD/MIT). **No FreeSurfer-license component is bundled inside SimNIBS itself** — `samseg` (`github.com/freesurfer/samseg`) is listed with `License: ?` in `3RD-PARTY.md` but is actually **MIT** per its own PyPI/wheel metadata (confirmed below) — it is a spun-off, separately-licensed derivative, not full FreeSurfer.

Two licensing items worth the maintainer's attention for a *commercial* desktop redistribution (not blockers for the current academic/GPL use, but real due-diligence items):
- **ADMlib** (`3RD-PARTY.md`): "GNU GPL-v2.0, for non-commercial and academic purposes only" OR a paid Duke University commercial license. It ships inside the general `simnibs` wheel unconditionally. **VERIFIED** it is used only by `simnibs/optimization/tms_optimization.py` (TMS coil optimization) — grepping all of TI-Toolbox's `tit/` for `ADM`/`tms_optimization`/`TMSLIST` returned **zero hits** (TI-Toolbox is TES/TI-electrode-only, not TMS), so TI-Toolbox's own code paths never touch it, but it is physically present in whatever gets redistributed.
- **Intel MKL** (Windows/Linux Pardiso solver): "Intel Simplified Software License" — a proprietary EULA. Intel's terms permit redistribution, so not a GPL conflict, but it's a separate license to track in a commercial build (Apple Silicon avoids this entirely — MUMPS instead, see §3).

## 2. What's actually installed in the running container (VERIFIED, `docker exec tit-v3-spike ...`)

- `simnibs.__file__` → `/root/SimNIBS-4.6/simnibs_env/lib/python3.11/site-packages/simnibs/__init__.py`. The path itself (`simnibs_env`) confirms this container was built from the **conda-packed installer**, not a bare pip install — consistent with §1.
- `pip show simnibs`: `Version: 4.6.0`, `License-Expression: GPL-3.0-only`, `Requires: brainnet, cortech, fmm3dpy, gmsh, h5py, jsonschema, mkl, nibabel, numba, numpy, petsc4py, pillow, pygpc, PyQt5, requests, samseg, scipy, tbb`.
- Sizes on disk: `site-packages/simnibs` = **393M**; `simnibs/external` (linux-only binaries, other platforms pruned) = **15M**; `simnibs/segmentation/atlases` = **220M** (matches source tree exactly); `samseg` package = **65M**; `torch` = **715M** (pulled in for the new AI cortical-surface reconstruction — see §4); `petsc4py` = **46M**; whole `simnibs_env` conda environment = **4.5G** unpacked. Note this 4.5G figure is *this container's* env, which per project memory also carries TI-Toolbox's own extra deps (mne 1.12, nilearn, numba, bpy 5.0.1 for Blender, etc.) on top of stock SimNIBS — it is **not** a clean "stock SimNIBS install size" number; §3's official installer download sizes are the cleaner comparison.
- `which charm` → `/root/SimNIBS-4.6/bin/charm`, a 3-line bash wrapper invoking `"$SIMNIBS_ROOT/simnibs_env/bin/python" -E -u ".../simnibs/cli/charm.py" "$@"` (this is `packing/fix_entrypoints.py`'s output, not a normal pip console-script). `which recon-all` and `which freeview` returned **nothing** — FreeSurfer is genuinely absent from this image (it lives only in the separate 67GB `idossha/ti-toolbox_freesurfer:v7.4.1` image per the task's own framing), confirming SimNIBS's segmentation path has no runtime dependency on it.
- `docker image inspect idossha/simnibs:v2.5.0` → `amd64 linux`; `docker manifest inspect` → single-arch (`architecture: amd64`, no `manifests` list). **This image has no native arm64 build today** — it is running under QEMU emulation on this M2 Mac right now. This is a real argument *for* the desktop-app rebuild: upstream SimNIBS itself ships a native macOS-arm64 wheel (§3), so leaving the Docker-container model would let Apple Silicon users actually go native, which the current toolbox does not.
- `pip show samseg cortech brainnet brainsynth` in-container: `samseg` **0.5a0**, `License: MIT`, `Home-page: https://github.com/freesurfer/samseg`; `cortech` **0.1**, `License: GPL3`; `BrainNet` **0.2** (requires `brainsynth, cortech, torch, pytorch-ignite, tqdm`); `BrainSynth` **0.1** (requires `torch`).

## 3. Per-platform wheel/support matrix (VERIFIED — GitHub Releases via `gh api`, `curl`, and `docs/changelog.rst`)

`gh api repos/simnibs/simnibs/releases/tags/v4.6.0` (published 2026-03-03 per GitHub's own timestamp) lists exactly these assets:

| File | Size |
|---|---|
| `simnibs-4.6.0-cp311-cp311-linux_x86_64.whl` | 188,305,161 B (~180 MB) |
| `simnibs-4.6.0-cp311-cp311-macosx_11_0_arm64.whl` | 184,051,752 B (~176 MB) |
| `simnibs-4.6.0-cp311-cp311-win_amd64.whl` | 189,428,894 B (~181 MB) |
| `simnibs_installer_linux.tar.gz` (conda-packed, full env) | 1,268,595,312 B (~1.27 GB) |
| `simnibs_installer_macos.pkg` (conda-packed, full env) | 849,468,729 B (~849 MB) |
| `simnibs_installer_windows.exe` (conda-packed, full env) | 898,900,463 B (~899 MB) |
| `environment_{linux,macos,windows}.yml` | ~1.1–1.3 KB each |

No `linux_aarch64`, no `macosx_*_x86_64` (Intel), no `win_arm64` wheel exists in this or any prior release I checked (v4.5.0/v4.1.0/v4.0.1/v4.0.0 all list 9 assets each, same pattern per the release listing). `docs/changelog.rst` (VERIFIED, read in full) states for 4.5.0: **"Support of SimNIBS on MacOS on Intel is discontinued"** and **"The PARDISO solver does not work on Apple Silicon (use MUMPS instead)"**; it also lists "Added MUMPS solver ... for FEM calculations on Macs with Apple Silicon" and "Added custom compiled version of FMM3D ... so it runs on Macs with Apple Silicon" as 4.5.0 features. `docs/installation/requirements.rst`: tested OSes are Windows 11 (64-bit), Linux (CentOS 9, Ubuntu 22.04/WSL2), macOS 14.6 Sonoma / 15.3 Sequoia (implicitly Apple Silicon given the Intel-discontinuation note); minimum 4GB disk, 8GB RAM (16GB recommended).

| Platform | Wheel published? | Upstream-tested? | Notes |
|---|---|---|---|
| **Linux x86_64** | Yes (180 MB) | Yes (CentOS 9, Ubuntu 22.04) | MKL/TBB Pardiso solver |
| **Linux arm64** | **No** | **No** (never mentioned in changelog/docs) | Would need a from-scratch rebuild: CGAL/Eigen3/mpfr for aarch64, *and* upstream would have to rebuild `cortech`/`fmm3dpy`/`petsc4py`/`samseg` (their custom-hosted wheels, see §4) for aarch64 too — none exist today |
| **Windows x86_64 (amd64)** | Yes (181 MB) | Yes (Windows 11) | MKL/TBB Pardiso; NSIS installer; meshfix.exe needs bundled Cygwin DLLs |
| **Windows ARM64** | **No** | **No** | Never mentioned |
| **macOS x86_64 (Intel)** | **No** — explicitly discontinued since 4.5.0 | Was tested through 4.0.0, not since | |
| **macOS arm64 (Apple Silicon)** | Yes (176 MB) | Yes (macOS 14.6/15.3) | PARDISO broken here → falls back to MUMPS; FMM3D custom-compiled for Apple Silicon |

The official conda-packed installers (the thing that's actually shippable, per §1) run **849 MB (macOS) to 1.27 GB (Linux)** as compressed downloads — those are the realistic per-platform payload numbers for embedding a full working SimNIBS runtime in a desktop app, well above the bare-wheel sizes.

## 4. The dependency wheels aren't on PyPI either (VERIFIED — this is the sharpest finding)

`curl -sI https://pypi.org/pypi/simnibs/json` → **HTTP 404**. `simnibs` is not published on PyPI at all (checked `simnibs` and `simnibs4`, both 404). Same for `cortech` and `brainsynth` — both hard dependencies of `simnibs` per `pyproject.toml` — **404 on PyPI**. `brainnet` *does* exist on PyPI but only as a stale `0.0.01` (not what SimNIBS actually uses). `petsc4py`, `fmm3dpy`, `pygpc` do exist on PyPI with proper multi-platform wheels, but SimNIBS pins and installs its *own* custom-built versions of `petsc4py`/`fmm3dpy` anyway (see below) rather than the PyPI ones.

I fetched all three official `environment_*.yml` files directly (`curl -sL https://github.com/simnibs/simnibs/releases/download/v4.6.0/environment_{linux,macos,windows}.yml`, VERIFIED). Every one of them installs the "extra" packages from **ad hoc GitHub Release URLs, not PyPI**, e.g. (macOS):
```
- brainnet@git+https://github.com/simnibs/brainnet@v0.2          # built from source at install time
- brainsynth@git+https://github.com/simnibs/brainsynth@v0.1      # built from source at install time
- https://github.com/oulap/samseg_wheels/releases/download/dev/samseg-0.5a0-cp311-cp311-macosx_14_0_arm64.whl
- https://github.com/simnibs/cortech/releases/download/v0.1/cortech-0.1-cp311-cp311-macosx_11_0_arm64.whl
- https://github.com/simnibs/fmm3dpy/releases/download/v1.0.4/fmm3dpy-1.0.4-cp311-cp311-macosx_14_0_arm64.whl
- https://github.com/simnibs/petsc4py/releases/download/v3.22.2/petsc4py-3.22.2-cp311-cp311-macosx_14_0_arm64.whl
```
Notably the `samseg` wheel SimNIBS actually uses (0.5a0) comes from a **third-party personal GitHub account** (`github.com/oulap/samseg_wheels`, presumably a SimNIBS/samseg co-author's personal fork), not the official PyPI `samseg` package (0.4a0, checked separately, `License: MIT`, `Home-page: github.com/freesurfer/samseg`) and not the `freesurfer/samseg` org itself. This is a real supply-chain fragility: reproducing a build of the SimNIBS stack depends on an individual maintainer's personal GitHub releases staying up, on top of the base conda-forge stack (`mpfr`, `numpy`, `python-mumps`, plus `mkl`/`tbb` on Windows/Linux or `freeglut` on Linux only). `torch` is pulled from plain PyPI on macOS (`torch==2.6.0`, arm64 wheel exists there) but from PyTorch's own CPU-only wheel index on Linux/Windows (`https://download.pytorch.org/whl/cpu/torch-2.6.0%2Bcpu-...`) to avoid the multi-GB CUDA build — another non-PyPI source to pin.

**Practical upshot for "add simnibs to a bundled venv":** even the wheel-only route in SimNIBS's own docs (`docs/installation/conda.rst`, VERIFIED, read in full) requires first building a full conda-forge environment from a per-OS YAML, *then* `pip install`ing the platform wheel — it is presented explicitly as the "(Advanced)" path, with the plain installer (`simnibs_installer_{linux,macos,windows}`) as the recommended route for everyone else. There is no path that is "pip install simnibs and go."

## 5. TI-Toolbox's actual SimNIBS surface area (VERIFIED — grepped `tit/`)

`grep -rln "from simnibs\|import simnibs" tit --include='*.py'` → 25 files (`tit/sim/{TI,mTI,base,utils}.py`, `tit/opt/{leadfield,ex/*,flex/*,mex/engine}.py`, `tit/analyzer/{analyzer,visualizer}.py`, `tit/tools/{map_electrodes,mesh2nii,field_extract}.py`, `tit/source/{fsaverage,forward}.py`, `tit/blender/*.py`). CLI-level invocations found by grepping for `simnibs_python`/`charm`/`msh2cortex`/`subject_atlas`:

- **`charm`** — invoked via `tit/pre/charm.py`'s `run_charm()` (subprocess), which then also runs **`subject_atlas`** to build `.annot` parcellations (a2009s, DK40, HCP_MMP1 — `ATLASES = ["a2009s", "DK40", "HCP_MMP1"]`, `tit/pre/charm.py:44`) directly from the `m2m_dir` charm produces. **Neither call touches FreeSurfer** — confirmed by reading `tit/pre/charm.py` in full: its only inputs are the subject's T1/T2 NIfTI files and the m2m directory path.
- **`msh2cortex`** — invoked from `tit/sim/base.py:257` (`_generate_central_surface`) to build the central cortical surface mesh from a finished TI/mTI simulation mesh; pure SimNIBS, no FreeSurfer input.
- Every `tit.<module>` runner (`tit.sim`, `tit.opt.flex`, `tit.opt.ex`, `tit.opt.mex`, `tit.analyzer`, `tit.source`, `tit.blender`, `tit.stats`) is invoked as `simnibs_python -m tit.<module> config.json` (30+ `#!/usr/bin/env simnibs_python` shebangs / docstring examples found across `tit/`), i.e. TI-Toolbox's entire compute layer runs *inside* the SimNIBS Python environment, not alongside it — every one of those features requires the full conda-packed `simnibs_env` (torch, PETSc, gmsh, samseg, etc.), not just an importable `simnibs` module.
- **`tit/pre/recon_all.py`** runs the actual `recon-all` binary (`cmd = ["recon-all", "-subject", ..., "-i", str(t1_file), "-all", "-sd", ...]`, line 165) plus `segmentThalamicNuclei.sh`/`segmentHA_T1.sh` for subcortical segmentations — this is TI-Toolbox's own separate step, **not** something SimNIBS's `charm` needs. `tit/jobs/plans.py` (`plan_preprocessing`, read in full) confirms the DAG: `G2a` (`charm`+`subject_atlas`) and `G2b` (`recon-all`) both depend only on `G1` (DICOM conversion) and run **in parallel**, independently of each other; `G3` (tissue analysis) depends on `G2a` only. `tit/server/routes/system.py` and `tit/gui/system_monitor_tab.py` both track `recon-all`/`charm`/`subject_atlas` as separate, independently-monitored processes, reinforcing that they are already architecturally decoupled.

All of the above "work from a plain pip install" in the loose sense that they're pure calls into `simnibs`'s own CLI/Python API — but per §4, "plain pip install" isn't actually available for `simnibs` itself, so the honest answer is "these features work fine once the *full conda-packed SimNIBS environment* is present," which is the same environment the current Docker image already carries.

---

## Size budget summary (VERIFIED numbers, for the maintainer's "realistic?" question)

| Component | Size | Source |
|---|---|---|
| Official conda-packed installer download | 849 MB (macOS) – 1.27 GB (Linux) – 899 MB (Windows) | `gh api` release assets, v4.6.0 |
| Bare SimNIBS wheel (needs matching conda env already present) | ~176–181 MB per platform | same |
| `site-packages/simnibs` unpacked | 393 MB | container `du -sh` |
| — of which segmentation atlases | 220 MB | container + source tree, matches exactly |
| — of which bundled external binaries (one platform) | 15 MB | container (50 MB across all 3 platforms in source) |
| `torch` (new AI cortical-surface path) | 715 MB | container `du -sh` |
| `samseg` | 65 MB | container `du -sh` |
| `petsc4py` | 46 MB | container `du -sh` |
| Full `simnibs_env` unpacked (this container, includes TI-Toolbox's extra deps) | 4.5 GB | container `du -sh` — **not** a clean stock-SimNIBS number |

A realistic desktop-app budget for *just* the SimNIBS half of the bundle, per platform, is closer to the **850 MB – 1.3 GB compressed / ~2-4 GB unpacked** official-installer range than to the bare-wheel number, because the wheel alone is useless without its full conda-forge + custom-wheel dependency closure.

## Answer to "is it realistic?"

Technically yes, with real caveats:
1. **Packaging shape matches Electron-embeddable-runtime patterns** (a frozen relocatable Python env invoked via subprocess, exactly how the container already runs it, and exactly what `conda-pack` already produces) — this is not a fight against SimNIBS's own distribution model, it's reusing it.
2. **It is not a normal pip dependency.** Anyone building the desktop bundle needs to either (a) vendor SimNIBS's own official conda-packed installer output per OS (849 MB–1.27 GB each, three separate binaries to embed and invoke), or (b) reproduce the `environment_*.yml` + wheel-from-GitHub-Releases + two git-source builds process themselves in CI, which pulls in one third-party personal GitHub account's wheel (`oulap/samseg_wheels`) as a supply-chain dependency.
3. **Platform coverage is asymmetric and already excludes Intel Mac and all ARM Linux/Windows** — so "compiled for linux/windows/mac like Tetravox or SUNA" is achievable for the three combinations upstream itself supports (linux x86_64, win amd64, macOS arm64) but not literally "all platforms": there is no path to Linux ARM (e.g. Raspberry Pi/ARM servers) or Windows ARM today without SimNIBS upstream doing that work first, since the blocking native deps (`cortech`, `fmm3dpy`, `petsc4py`, `samseg`, CGAL/Eigen3 build) have no aarch64/win-arm64 builds anywhere.
4. **A real upside for this specific Mac:** the current `idossha/simnibs:v2.5.0` Docker image is amd64-only (VERIFIED, no arm64 manifest) and is running under QEMU emulation on this M2 machine right now — switching to a native desktop build using upstream's actual arm64 wheel would remove that emulation tax for every Apple Silicon user, which the Docker-container model cannot do today.
5. **GPL-3 compatibility is clean** for the core stack; the two license items worth carrying into a commercial-redistribution decision are ADMlib (GPLv2 non-commercial-only, unused by TI-Toolbox's own code but physically bundled) and Intel MKL (proprietary EULA, Windows/Linux only, avoidable on Apple Silicon since MUMPS is used there instead).
