# Lane R3 — FreeSurfer-free brain parcellation/segmentation alternatives

Scope: find a replacement for `recon-all` (cortical parcellation + volumetric
subcortical labeling) that can ship inside a self-contained desktop
executable, no FreeSurfer install required. All claims below are tagged
**VERIFIED** (I read the file/ran the command myself) or **REPORTED** (a
doc/paper says it, not independently reproduced). Time-boxed research; no
multi-GB model downloads performed.

---

## 0. The load-bearing finding: most of the "FreeSurfer problem" is already solved

Before evaluating FastSurfer/SynthSeg, I read what the toolbox actually does
today and what SimNIBS 4.6's own `charm` pipeline already produces. This
changes the shape of the problem substantially.

**VERIFIED** — `tit/pre/charm.py:102` calls `charm` with no `--fs-dir` flag,
so it always runs charm's own (non-FreeSurfer) pipeline:
```python
cmd = ["charm", form_flag, subject_id, str(t1_file)]
```

**VERIFIED** — SimNIBS 4.6's charm does **not** need FreeSurfer for cortical
surfaces by default. `simnibs/segmentation/charm_main.py:354-369` (checkout
at `/Users/idohaber/01_production/simnibs`):
```python
if fs_dir is None:
    logger.info("Estimating cortical surfaces")
    cortex, curv = brain_surface.cortical_surface_estimation(
        [sub_files], surface_settings["topofit_contrast"], ...)
    ...
else:
    logger.info("Loading surfaces from existing FreeSurfer run")
    cortex = cortech.Cortex.from_freesurfer_subject_dir(fs_dir, ...)
```
`fs_dir` comes from the optional `--fs-dir` CLI flag
(`simnibs/cli/utils/args_charm.py:105-114`, help text: *"If you have a
FreeSurfer run of your subject, you can pass the subject directory and CHARM
will simply grab the surfaces... instead of estimating them"*) — i.e.
FreeSurfer is opt-in, not required. The default path uses a bundled
TopoFit deep-learning surface network (`brainnet.helpers.topofit`,
`simnibs/segmentation/brain_surface.py:97-125`; package `BrainNet` is a
declared SimNIBS dependency, `pyproject.toml:21: "brainnet>=0.2"`).
The official docs confirm this in prose:
`docs/documentation/command_line/charm.rst:40-46` — *"As of SimNIBS 4.6, we
use an implementation of the TopoFit network to reconstruct cortical
surfaces... It is also possible to use cortical surfaces created by
FreeSurfer's recon-all pipeline with CHARM. To do this, pass the subject
directory using the option `--fs-dir`."*

**VERIFIED** — `subject_atlas` (SimNIBS's own tool) already gives the
toolbox DK40 / Destrieux(a2009s) / HCP_MMP1 cortical parcellation as
`.annot` files on the subject's own central surface, purely from charm
output, no FreeSurfer: `tit/pre/charm.py:117-184` (`run_subject_atlas`,
`ATLASES = ["a2009s", "DK40", "HCP_MMP1"]`), consumed by
`tit/atlas/mesh.py` (`MeshAtlasManager`). `simnibs/cli/subject_atlas.py`
takes only an `m2m_dir` and calls `atlas2subject(m2m_dir, atlas, ...)` — no
FreeSurfer subjects-dir argument exists in its CLI at all.

**VERIFIED (unexpected)** — charm's own volumetric segmentation
(`m2m_{sid}/segmentation/labeling.nii.gz`, path helper
`tit/paths.py:320-322`) is **already an aseg-style label map using
FreeSurfer's own label IDs**, produced by charm's internal SAMSEG variant
(`simnibs/segmentation/samseg_whole_head.py:215-218`, `FreeSurferLabels`
array). I read the shipped LUT,
`/Users/idohaber/01_production/simnibs/simnibs/resources/labeling_FreeSurferColorLUT.txt`
(57 lines) — it has per-hemisphere **Thalamus-Proper, Caudate, Putamen,
Pallidum, Hippocampus, Amygdala, Accumbens-area, VentralDC**, plus
ventricles/brainstem/cerebellum, at the standard FreeSurfer aseg numeric IDs
(10=Left-Thalamus-Proper, 17=Left-Hippocampus, 18=Left-Amygdala, etc.).
`tit/atlas/voxel.py:76-79` already surfaces `labeling.nii.gz` as a targetable
voxel atlas, and `tit/pre/tissue_analyzer.py:37-58` (`TISSUE_CONFIGS`)
already reads label IDs straight out of it for CSF/bone/skin analysis. So
whole-structure subcortical volumetric ROIs (not sub-parcellated) are a
**zero-cost, already-shipping, FreeSurfer-free** capability today.

### What `recon-all` is therefore actually still buying the toolbox

Re-reading `tit/pre/recon_all.py` and `tit/atlas/constants.py:9-17`
(`VOXEL_ATLASES`) with the above in mind, `recon-all` is used for exactly
three things nothing else in the pipeline currently supplies:

1. **`aparc.DKTatlas+aseg.mgz` / `aparc.a2009s+aseg.mgz`** — a *volumetric*
   map where cortical gray-matter voxels carry a specific DK/Destrieux gyrus
   label, not just the generic "Left/Right-Cerebral-Cortex" charm gives.
   (Surface-space DK40/a2009s is already free via `subject_atlas`; this is
   the voxel-space version, used by the NIfTI viewer / flex-search
   subcortical-ROI picker per `tit/atlas/voxel.py:38-83`.)
2. **`ThalamicNuclei.v13.T1.mgz`** — FreeSurfer's `segmentThalamicNuclei.sh`,
   13 individual thalamic nuclei (charm gives one whole-thalamus label).
3. **`lh/rh.hippoAmygLabels-T1.v22.mgz`** — FreeSurfer's `segmentHA_T1.sh`,
   hippocampal subfields + amygdala nuclei (charm gives one whole-hippocampus
   and one whole-amygdala label each).

`tit/pre/recon_all.py:32-61` (`_run_subcortical_segmentations`) runs exactly
those two scripts (`segmentThalamicNuclei.sh`, `segmentHA_T1.sh`) after
`recon-all -all` completes — confirming (2) and (3) are the only reason
`recon-all` runs at all beyond producing (1)'s substrate.

This reframes the R3 question from "replace recon-all wholesale" to "find a
FreeSurfer-free source for these three specific outputs" — items 2 and 3 are
niche (sub-structure detail most TI-focality use cases don't need — TI field
foci are typically several mm to cm, coarser than individual thalamic nuclei
or hippocampal subfields), and item 1 has a direct drop-in candidate below.

---

## 1. FastSurfer (github.com/Deep-MI/FastSurfer)

**VERIFIED via `raw.githubusercontent.com` fetches of `README.md`,
`INSTALL.md`, `doc/overview/INSTALL.md`, `doc/overview/OUTPUT_FILES.md`,
`recon_surf/README.md`, `requirements.txt`, `pyproject.toml`, `LICENSE`,
dev branch, fetched 2026-09-02/03.**

- **`--seg_only` output**: `aparc.DKTatlas+aseg.deep.mgz` — "cortical and
  subcortical segmentation" on the DKT atlas — **this filename is a
  near-exact match for the toolbox's own `VOXEL_ATLASES["aparc.DKTatlas+aseg.mgz"]`**
  (`tit/atlas/constants.py:12`), i.e. it could be dropped in with a rename or
  by adding the `.deep.mgz` name as a second accepted filename. Also emits
  `aseg.auto_noCCseg.mgz` (simplified subcortical, no CC), plus two modules
  that run automatically unless disabled: `cerebellum.CerebNet.nii.gz`
  (detailed cerebellar sub-segmentation) and
  `hypothalamus.HypVINN.nii.gz`/`hypothalamus_mask.HypVINN.nii.gz`
  (hypothalamus sub-segmentation, optional T2w). None of these three do
  thalamic-nuclei or hippocampal-subfield sub-segmentation — FastSurfer has
  no equivalent of FreeSurfer's `segmentThalamicNuclei.sh` /
  `segmentHA_T1.sh` (items 2/3 above remain unaddressed by FastSurfer).
- **`--seg_only` needs no FreeSurfer at all**: confirmed by web search
  synthesis of the FastSurfer docs — *"No FreeSurfer license is needed with
  the `--seg_only` flag."* The full pipeline / `recon_surf` (`--surf_only`)
  is the opposite: `recon_surf/README.md` states a native install needs *"a
  working installation of __FreeSurfer__ (the supported version, usually the
  most recent)"* because recon_surf calls FreeSurfer binaries internally
  (mris_expand etc.) for the surface pipeline — so **only `--seg_only` is
  relevant to a FreeSurfer-free build**; the surface/thickness half of
  FastSurfer is a dead end for this goal and should not be used.
- **License**: Apache License 2.0 (`LICENSE` file fetched directly, header
  confirmed) — commercially redistributable, no copyleft obligation on the
  toolbox.
- **PyTorch / Python**: `requirements.txt` (dev branch) pins
  `torch==2.7.1`, `torchvision==0.22.1`, `numpy==2.4.4`, `nibabel==5.4.2`,
  `monai==1.5.2`. `pyproject.toml` declares `requires-python = '>=3.10'`.
  **VERIFIED against the actual runtime**: `docker exec tit-v3-spike
  simnibs_python -c "import torch; print(torch.__version__)"` → `torch
  2.6.0+cpu`, Python `3.11.14`. Python is compatible (3.11 ≥ 3.10); torch is
  one minor version behind FastSurfer's pin (2.6.0 vs 2.7.1) — needs
  bumping/testing, not a hard blocker; note the container already carries
  torch as a dependency of SimNIBS's own `BrainNet`/`BrainSynth` packages
  (`docker exec tit-v3-spike simnibs_python -m pip show torch` →
  `Required-by: BrainNet, BrainSynth, pytorch-ignite`), so FastSurfer adds no
  new ML framework, only a version bump.
- **Not pip-installable from PyPI**: `curl -s
  https://pypi.org/pypi/FastSurfer/json` (and `FastSurferCNN`,
  `fastsurfercnn`) all return `{"message": "Not Found"}` (checked
  2026-09-03). It has a local `pyproject.toml` (package name `fastsurfer`,
  version `2.6.0-dev0`) so it is `pip install`-able *from a git clone*
  (`pip install .` / `pip install git+https://github.com/Deep-MI/FastSurfer`)
  — must be vendored into the build, not pulled from a package index at
  install time.
- **Platforms**: `doc/overview/INSTALL.md` — native install officially
  tested/supported on **Linux** (Ubuntu 20.04/22.04) and **macOS Apple
  Silicon** (native or Docker); **macOS Intel is Docker-only**; **Windows is
  Docker-only, via WSL2** (*"In order to run FastSurfer on your Windows
  system using docker make sure that you have: WSL2 [and] Docker Desktop
  installed and running"*) — no native Windows path exists. This matters
  directly for the maintainer's "single Electron executable, no Docker"
  goal: FastSurfer's `--seg_only` PyTorch path itself has no Windows-native
  blocker (it's pure PyTorch + a handful of Python deps — Docker is just how
  the project ships/tests it), but it has never been verified running
  natively on Windows by the FastSurfer team, so first-run validation on
  Windows is real integration work, not a checkbox.
- **Model size**: checkpoints are hosted on Zenodo, not bundled in the repo.
  I fetched the record pages (not the files): FastSurferVINN `aparc`
  segmentation weights (3 planes, v2.0.0) = 3 × 22.4 MB = **67.2 MB**
  (`zenodo.org/records/10390573`); CerebNet weights (3 planes) = 3 × 21.7 MB
  = **65.1 MB** (`zenodo.org/records/10390742`); HypVINN weights not
  individually sized (record `zenodo.org/records/11184216`, not fetched —
  budget). Core `aparc.DKTatlas+aseg` capability alone is ~67 MB, comfortably
  under the 500 MB guidance; the full `--seg_only` bundle (asegdkt + CerebNet
  + HypVINN) is very likely still well under 500 MB.
- **Runtime**: **REPORTED**, not independently benchmarked (no model
  downloaded in this pass — out of time-box). FastSurfer's docs/README
  (web-search synthesis) state whole-pipeline surface reconstruction takes
  ~60-90 min, and the original paper's abstract (arXiv:1910.03866, fetched)
  states *"volumetric analysis (in under 1 minute)"* — that figure is GPU.
  No official CPU-only number was found for `--seg_only` in the docs I
  fetched; `INSTALL.md` only says CPU is *"much slower"* than GPU without a
  number. Given the container is CPU-only (`torch.cuda.is_available()` →
  `False`, verified above, x86_64-emulated M2), treat "~1 min" as a
  GPU-only figure and budget several minutes per subject on CPU until
  measured — this needs an actual timed run before it goes into any user-facing
  estimate.

## 2. SynthSeg / SynthSeg+ (github.com/BBillot/SynthSeg)

**VERIFIED via `raw.githubusercontent.com` fetches of `README.md` and
`LICENSE.txt`, master branch, fetched 2026-09-03.**

- **Output**: whole-brain volumetric labels (aseg-like — subcortical
  structures individually labeled per the repo's `data/labels table.txt`,
  which I did not fetch in this pass) at 1 mm isotropic. SynthSeg 2.0 adds
  `--parc` for cortical parcellation plus automated QC and ICV estimation;
  the README text I retrieved does not name the specific cortical atlas used
  by `--parc` (DKT vs Destrieux) — this needs a follow-up read of
  `data/labels table.txt` or the SynthSeg 2.0 paper (Billot et al.) before
  relying on it for atlas-name compatibility with the toolbox's `DK40`
  naming.
- **License**: Apache 2.0 (`LICENSE.txt` fetched directly) — same
  commercial-friendly terms as FastSurfer.
- **Standalone**: the GitHub repo runs independently of any FreeSurfer
  install (it is also bundled into FreeSurfer 7.2+ as `mri_synthseg`, but the
  standalone repo does not require that).
- **Framework**: TensorFlow-based (version pinned per Python: TF 2.0.0 for
  Python 3.6, TF 2.2.0 for Python 3.8, per README prose — dated pins,
  likely stale for a 2026 build; I could not fetch `requirements.txt`
  directly, `raw.githubusercontent.com/.../requirements.txt` 404'd). **This
  is the decisive point against SynthSeg for this toolbox specifically**:
  the container has zero TensorFlow footprint today and already carries
  PyTorch (for SimNIBS's own `BrainNet`); adding TF as a second deep-learning
  framework just for this one stage is extra weight (TF wheels typically
  ~500 MB-1 GB with CUDA extras, smaller CPU-only) and a second dependency
  surface to keep working across three OSes, for no capability FastSurfer
  doesn't already cover for the toolbox's actual gap (item 1 above).
- **Runtime**: README states *"the code can be run on the GPU (~15s per
  scan) or on the CPU (~1min)"* — this is a real, stated CPU number
  (unlike FastSurfer's docs), reported not reproduced here.
- **Robustness claim** (worth noting as a genuine SynthSeg differentiator):
  README claims robustness to *"any contrast," "any resolution up to 10mm
  slice spacing,"* diverse populations, with/without preprocessing, and
  white-matter lesions — trained entirely on synthetic data, so it doesn't
  need contrast-matched training data. FastSurfer's asegdkt module is
  trained primarily on T1w and is less publicized for this kind of
  contrast-agnosticism (not verified either way in this pass).

## 3. SimNIBS's own charm/samseg + `subject_atlas`

Already covered in full in §0 above — this **is** the "third candidate" and
turns out to already be running inside the toolbox with zero extra
integration cost:

- Cortical ROI by atlas label on the central surface: **covered today**
  (DK40, a2009s/Destrieux, HCP_MMP1 via `subject_atlas`, no FreeSurfer).
- Subcortical ROI by whole-structure volumetric label (thalamus, hippocampus,
  amygdala, caudate, putamen, pallidum, accumbens, ventral DC): **covered
  today** (`labeling.nii.gz`, FreeSurfer-ID-compatible LUT).
- **Not covered**: voxel-space DK/Destrieux cortical parcellation (item 1),
  thalamic-nuclei detail (item 2), hippocampal-subfield detail (item 3).

## 4. Others worth a line

- **nnU-Net-based whole-brain models**: no off-the-shelf "whole-brain
  DKT-aseg" nnU-Net model was located in this pass distinct from FastSurfer
  (FastSurfer's own networks are custom CNNs, not nnU-Net); nnU-Net is more
  commonly seen as the *framework* other groups (e.g. HippUnfold, below)
  build task-specific models on, not a ready segmentation tool itself.
- **ANTs-based** (`antsCorticalThickness`/`antsBrainSegmentation`): produces
  a coarser Desikan-Killiany-*like* label set via joint label fusion against
  an atlas set (not the DKT protocol proper), no GPU, much slower than deep
  models (multi-atlas registration is CPU-heavy, historically tens of
  minutes to hours per subject) — not independently verified in this pass;
  ANTs itself is a large C++ toolkit to vendor, working against the
  "smaller executable" goal.
- **"brainchop" / in-browser TFJS** (github.com/neuroneural/brainchop, JOSS
  2023, Google TensorFlow community spotlight 2022 — **REPORTED** via
  WebSearch, not independently fetched): runs a lightweight model
  (MeshNet-family) fully client-side via TensorFlow.js/WebGL2, "does not
  require technical sophistication from the end-user and maintains user
  data privacy by only processing it on their machines." Directly relevant
  to the maintainer's own architecture question: this could in principle run
  *inside Tetravox* (also Electron+WebGL2) rather than as a Python backend
  stage at all — worth a dedicated follow-up spike, but its segmentation
  granularity (coarse tissue classes / limited label sets in the public
  demo) is very unlikely to match DKT/aseg detail; treat as a "someday,
  in-viewer quick-look" option, not a `tit.pre` replacement for FastSurfer.
- **TotalSegmentator-like / HD-BET / deepmedic**: TotalSegmentator targets
  whole-body CT, not brain MRI parcellation — not applicable here. HD-BET is
  a skull-stripping tool (complementary, not a parcellation replacement;
  charm already does its own skull-stripping-equivalent as part of tissue
  segmentation). deepmedic is a segmentation *framework*, not a pretrained
  whole-brain DKT/aseg model — would need training data and time this task
  doesn't have.
- **HippUnfold** (github.com/khanlab/hippunfold, BIDS-App —
  **REPORTED** via WebSearch, not independently fetched): the most credible
  FreeSurfer-free candidate specifically for hippocampal-subfield detail
  (item 3) — deep-learning + topological unfolding, and its own docs claim
  FreeSurfer-compatible subfield label names are selectable. It ships as its
  own BIDS-App container, so adopting it means vendoring a second, separate
  ML pipeline (nnU-Net-based per its methods) just for one niche
  sub-structure — only worth doing if a concrete TI-targeting use case
  actually needs subfield-level hippocampal ROIs (CA1 vs CA3 etc.), which is
  finer than the toolbox's field-focality resolution in practice. No
  equivalent FreeSurfer-free thalamic-nuclei tool was found in this pass;
  that gap (item 2) is currently unresolved.

---

## Compatibility matrix

| Tool | Cortical (surface) | Cortical (voxel/DKT) | Subcortical (voxel) | Atlas(es) | MNI | Runtime | Size | License | FreeSurfer-free | pip-able | Platforms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **SimNIBS charm + `subject_atlas`** (already in use) | Yes (.annot on central surface) | No | Yes, whole-structure only (thalamus/hipp/amyg/caudate/putamen/pallidum/accumbens/VDC) | DK40, a2009s (Destrieux), HCP_MMP1 | Via charm's own affine reg | Minutes (already run today) | Already shipped | GPL-3.0 (SimNIBS) | Yes, by default | N/A (bundled) | Linux/macOS/Windows (SimNIBS-supported) |
| **FastSurfer `--seg_only`** | No (surf pipeline needs real FreeSurfer — do not use) | **Yes** — `aparc.DKTatlas+aseg.deep.mgz` | Yes, whole-structure (`aseg.auto_noCCseg.mgz`) + cerebellum sub-seg (CerebNet) + hypothalamus sub-seg (HypVINN); **no** thalamic-nuclei/hippocampal-subfield detail | DKT | Not itself, but drop-in for the toolbox's own DKT voxel atlas naming | REPORTED ~1 min GPU (paper abstract); CPU not officially benchmarked, expect several min | ~67 MB (asegdkt) + ~65 MB (CerebNet) + HypVINN (unmeasured), all well under 500 MB combined | **Apache-2.0** | **Yes**, for `--seg_only` only | git-clone + `pip install .` (own `pyproject.toml`, not on PyPI) | Native: Linux, macOS ARM. Docker-only: macOS Intel, Windows (WSL2) |
| **SynthSeg / SynthSeg+** | No | Yes via `--parc` (atlas name not confirmed in this pass) | Yes, whole-structure aseg-like | Unconfirmed atlas name for `--parc` | Not stated | REPORTED ~15s GPU / ~1 min CPU (README, stated CPU number) | Not sized in this pass | **Apache-2.0** | Yes | Not on PyPI; git-clone | Cross-platform in principle (pure TF); needs a new TF dependency the container doesn't have today |
| **HippUnfold** | No (hippocampus-only) | N/A | Hippocampal subfields only | FreeSurfer- and ASHS-compatible label sets (REPORTED) | Not confirmed | Not confirmed | Not confirmed | Not confirmed | Yes | BIDS-App container (own pipeline) | Docker/Singularity (per BIDS-App convention) |
| **brainchop (TFJS, in-browser)** | Coarse | Unclear/limited | Coarse | Unclear | Unclear | Interactive (client-side) | Small (browser-deliverable) | Not confirmed | Yes | N/A (JS) | Any browser (Electron-embeddable) |

---

## Ranked recommendation

1. **Keep SimNIBS charm + `subject_atlas` exactly as today** for everything
   they already give the toolbox for free: surface-space DK40/a2009s/HCP_MMP1
   and whole-structure subcortical volumetric ROIs. This is not new work —
   it is recognizing that `tit/pre/charm.py`'s existing behavior (no
   `--fs-dir`) already made the toolbox's *cortical-surface and
   whole-structure-subcortical* story FreeSurfer-free. Nothing to build here.

2. **Add FastSurfer `--seg_only` as the `recon-all` replacement** for the one
   thing it and charm together don't cover: voxel-space DKT cortical
   parcellation (`aparc.DKTatlas+aseg.deep.mgz`). It is Apache-2.0, needs no
   FreeSurfer license or binaries in `--seg_only` mode, is PyTorch (a
   framework the container already carries via SimNIBS's `BrainNet`), and
   its checkpoint sizes (tens of MB) are trivial to vendor. Do **not** adopt
   FastSurfer's `recon_surf`/full pipeline — it explicitly requires a real
   FreeSurfer install, which defeats the purpose.

3. **Drop thalamic-nuclei and hippocampal-subfield segmentation from the
   FreeSurfer-free build's default scope**, falling back to charm's own
   whole-structure thalamus/hippocampus/amygdala labels (already available,
   already FreeSurfer-free). Revisit only if a specific TI-targeting
   workflow needs sub-structure granularity; if so, evaluate HippUnfold
   (subfields) as a separate, optional add-on rather than trying to keep
   FreeSurfer around just for these two scripts — vendoring one extra
   BIDS-App is a smaller footprint than vendoring all of FreeSurfer.

4. **Do not add SynthSeg.** Its capabilities are a near-duplicate of what
   FastSurfer `--seg_only` already provides for this toolbox's gap, but it
   would require introducing TensorFlow as a brand-new ML framework
   dependency solely for this stage, alongside the PyTorch the container
   already has for SimNIBS itself — worse for install size and cross-platform
   maintenance than the FastSurfer path, for no incremental coverage. (Its
   contrast-robustness claim is real and would matter if the toolbox ever
   needed to segment non-T1w or low-quality clinical scans reliably; keep as
   a documented fallback option, not a default dependency.)

5. **File "brainchop-in-Tetravox" as a separate, later spike**, not part of
   this replacement. It's architecturally interesting (client-side,
   zero-Python-backend segmentation inside the viewer itself) but its public
   model granularity is very unlikely to match DKT/aseg fidelity, and it
   doesn't fit today's `tit.pre` pipeline shape at all — it's a different
   product idea (interactive quick-look, not a submitted preprocessing job).

---

## Concrete integration sketch: `tit.pre` FastSurfer stage

Modeled directly on the existing `run_recon_all` / `run_charm` shape
(`tit/pre/recon_all.py`, `tit/pre/charm.py`) so it slots into the same
`_STAGE_FLAGS` / job-DAG machinery (`tit/jobs/plans.py`) with minimal churn.
Coordinate the exact input/output paths with lane R2's audit of the
`m2m`/`derivatives` layout before implementing — this is a sketch, not a
verified path contract.

- **New module**: `tit/pre/fastsurfer.py`, public function
  `run_fastsurfer_seg(project_dir, subject_id, *, logger, runner=None)` —
  same signature shape as `run_charm`/`run_recon_all`.
- **Input**: the subject's T1 (`_find_anat_files(subject_id)`, same helper
  `tit/pre/charm.py:90` already uses) — no dependency on `m2m_{sid}` output,
  so this can run in parallel with `G2a` (charm) rather than after it, unlike
  today's `recon-all` which is already parallel to charm (`G2b` has no
  `after_labels` on `g2a` per `tit/jobs/plans.py`'s `G2b` block) — same
  parallelism story, just a different tool.
- **Command**: `run_fastsurfer.sh --sd <out> --sid sub-<id> --t1 <T1.nii.gz>
  --seg_only --device cpu` (or `cuda` where available) — vendored as a
  script/console-entry inside the app bundle, not a `docker run`.
- **Output landing spot** — write in FreeSurfer-compatible names where cheap,
  per the brief:
  - Copy/rename FastSurfer's `<sd>/sub-<id>/mri/aparc.DKTatlas+aseg.deep.mgz`
    to `m2m_{id}/segmentation/aparc.DKTatlas+aseg.mgz` (the exact filename
    `tit/atlas/constants.py:12`'s `VOXEL_ATLASES` dict already expects under
    `freesurfer_mri_dir` today — either physically copy it into that dict's
    search location, or extend `VOXEL_ATLASES`/`VoxelAtlasManager.list_atlases`
    (`tit/atlas/voxel.py:58-83`) with a second search root pointing at
    `m2m_{id}/segmentation/` so no FreeSurfer directory needs to exist at
    all). This is the one-line reason FastSurfer is a clean drop-in: naming
    was already FreeSurfer-shaped on the toolbox side.
  - `aseg.auto_noCCseg.mgz`, `cerebellum.CerebNet.nii.gz`,
    `hypothalamus.HypVINN.nii.gz` can land alongside it as additional
    optional voxel atlases (extend `VOXEL_ATLASES` similarly) — pure
    addition, not required for parity with today's `recon-all` output set.
  - Also copy the FreeSurfer-format LUT FastSurfer ships for `aparc+aseg`
    (its label IDs are FreeSurfer's, so `mri_segstats --ctab-default` in
    `VoxelAtlasManager.list_regions` (`tit/atlas/voxel.py:108-134`) keeps
    working unmodified — **but note `mri_segstats` itself is a FreeSurfer
    binary**; if FreeSurfer binaries are fully removed, this call needs its
    own replacement (e.g. `nibabel` + a bundled LUT parse, computing region
    voxel counts/coords in pure Python) — flag this as a second, smaller
    piece of FreeSurfer-binary surface area beyond `recon-all` itself that
    R2/R3 should track together.
- **Preflight/config wiring**: mirror `tit/pre/preflight.py`'s
  `STEP_RECON_ALL` handling — add `STEP_FASTSURFER_SEG`, reuse the same
  `_has_bids_t1` input check (`tit/pre/preflight.py:66-72`), same
  already-exists / remove-before-rerun policy as `run_recon_all`
  (`tit/pre/recon_all.py:155-162`).
- **Job plan**: add a `run_fastsurfer_seg: bool` flag to `PreprocessConfig`
  (`tit/pre/config.py`) alongside `run_recon`, and a `g2c` stage in
  `plan_preprocessing` (`tit/jobs/plans.py`) parallel to `g2a`/`g2b`, so
  existing projects can run both `recon-all` and FastSurfer side by side
  during a transition period before `recon-all` is retired.
