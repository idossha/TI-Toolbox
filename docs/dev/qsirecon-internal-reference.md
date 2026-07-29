---
layout: wiki
title: QSIPrep & QSIRecon Internal Reference
permalink: /wiki/qsiprep-reference/
---

# QSIPrep & QSIRecon: Complete Internal Reference

This document is the authoritative internal reference for QSIPrep and QSIRecon.
It covers every CLI argument, every output file, the pipeline architecture, version
history, Docker details, BIDS compliance, and the QSIPrep-to-QSIRecon migration.

**Primary Citation:**
Cieslak, M., Cook, P.A., He, X. et al. QSIPrep: an integrative platform for
preprocessing and reconstructing diffusion MRI data. *Nature Methods* 18, 775-778
(2021). https://doi.org/10.1038/s41592-021-01185-5

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Pipeline](#2-architecture--pipeline)
3. [Installation & Docker](#3-installation--docker)
4. [QSIPrep CLI Reference](#4-qsiprep-cli-reference)
5. [QSIPrep Preprocessing Details](#5-qsiprep-preprocessing-details)
6. [QSIPrep Output Specification](#6-qsiprep-output-specification)
7. [QSIRecon Overview](#7-qsirecon-overview)
8. [QSIRecon CLI Reference](#8-qsirecon-cli-reference)
9. [QSIRecon Built-In Workflows](#9-qsirecon-built-in-workflows)
10. [QSIRecon Output Specification](#10-qsirecon-output-specification)
11. [Available Atlases](#11-available-atlases)
12. [Available Diffusion Models](#12-available-diffusion-models)
13. [BIDS Compliance](#13-bids-compliance)
14. [Spaces & Orientations](#14-spaces--orientations)
15. [Eddy Configuration](#15-eddy-configuration)
16. [The QSIPrep/QSIRecon Split](#16-the-qsiprepqsirecon-split)
17. [Version History](#17-version-history)
18. [TI-Toolbox Integration Notes](#18-ti-toolbox-integration-notes)

---

## 1. Project Overview

**QSIPrep** is a BIDS-App for preprocessing diffusion-weighted MRI (dMRI) data.
It automatically configures preprocessing workflows based on acquisition metadata
recorded in BIDS, handling nearly all static q-space sampling schemes (single-shell
DTI, multi-shell, Cartesian DSI, compressed-sensing DSI, etc.).

**QSIRecon** is a companion post-processing pipeline that takes QSIPrep outputs
and runs reconstruction workflows producing biologically meaningful dMRI
derivatives: ODF/FOD reconstruction, model fits, tractography, tractometry,
fixel estimation, and regional connectivity.

| Property | QSIPrep | QSIRecon |
|---|---|---|
| **Purpose** | Preprocessing | Reconstruction & analysis |
| **GitHub** | PennLINC/qsiprep | PennLINC/qsirecon |
| **Docker** | `pennlinc/qsiprep` | `pennlinc/qsirecon` |
| **Docs** | qsiprep.readthedocs.io | qsirecon.readthedocs.io |
| **License** | BSD-3-Clause | BSD-3-Clause |
| **Language** | Python 3.10+ (94.8%) | Python 3.10+ |
| **Foundation** | Nipype | Nipype |

---

## 2. Architecture & Pipeline

### Full Pipeline Flow

```
Raw BIDS DWI Data
    |
    v
[QSIPrep] ── Preprocessing ──> derivatives/qsiprep/
    |                               |
    | (preprocessed DWI,            | (T1w, masks, transforms,
    |  bval, bvec, confounds)       |  tissue segmentations)
    v                               |
[QSIRecon] ── Reconstruction ──> derivatives/qsirecon/
    |                               |
    | (scalar maps, FODs,           | (connectivity matrices,
    |  tensor fits, bundles)        |  tractography, atlases)
    v
[Downstream Analysis]
```

### QSIPrep Preprocessing Steps (in order)

1. **Conform**: Ensure consistent LPS+ orientation across all inputs
2. **Denoise**: MP-PCA (`dwidenoise`) or Patch2Self denoising
3. **Unring**: Gibbs ringing artifact removal (`mrdegibbs`)
4. **B1 bias correction**: N4BiasFieldCorrection (ANTs/MRtrix3)
5. **B0 harmonization**: Rescale DWI scans for matching b=0 intensities
6. **Motion correction**: Head motion estimation and correction
7. **Eddy current correction**: FSL eddy or SHORELine
8. **Susceptibility distortion correction**: TOPUP, DRBUDDI, or SyN fieldmap-less
9. **B0 template creation**: Normalized averaging of b=0 images
10. **Coregistration**: Register DWI to T1w anatomical (ANTs)
11. **Spatial normalization**: Warp to MNI152NLin2009cAsym template (ANTs)
12. **Resampling**: Single interpolation step combining all transforms

### QSIPrep Anatomical Processing

1. Conform all T1w/T2w images to LPS+ orientation
2. Bias correction using N4BiasFieldCorrection (ANTs)
3. Register multiple images using `mri_robust_template` (FreeSurfer)
4. Brain extraction via SynthStrip
5. Tissue segmentation via SynthSeg
6. Register to MNI template space (ANTs)

---

## 3. Installation & Docker

### Docker (Recommended)

```bash
# QSIPrep
docker run -ti --rm \
    -v /path/to/bids:/data:ro \
    -v /path/to/output:/out \
    -v /path/to/license.txt:/opt/freesurfer/license.txt:ro \
    pennlinc/qsiprep:26.0.0 \
    /data /out participant \
    --fs-license-file /opt/freesurfer/license.txt \
    --output-resolution 2

# QSIRecon
docker run -ti --rm \
    -v /path/to/qsiprep-output:/data:ro \
    -v /path/to/recon-output:/out \
    -v /path/to/license.txt:/opt/freesurfer/license.txt:ro \
    pennlinc/qsirecon:26.0.0 \
    /data /out participant \
    --fs-license-file /opt/freesurfer/license.txt \
    --recon-spec mrtrix_multishell_msmt_ACT-hsvs \
    --input-type qsiprep
```

### Apptainer/Singularity

```bash
# Build image
apptainer build qsiprep-26.0.0.sif docker://pennlinc/qsiprep:26.0.0

# Run
apptainer run --containall --writable-tmpfs \
    -B /path/to/bids,/path/to/output,/path/to/license.txt:/opt/freesurfer/license.txt \
    qsiprep-26.0.0.sif \
    /path/to/bids /path/to/output participant \
    --fs-license-file /opt/freesurfer/license.txt \
    --output-resolution 2
```

### Python (Not Recommended)

```bash
pip install --user --upgrade qsiprep
```

Many non-Python dependencies (FSL, ANTs, MRtrix3, FreeSurfer, DSI Studio)
must be installed separately. Container deployment is strongly preferred.

### Critical Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `TEMPLATEFLOW_HOME` | TemplateFlow template cache directory | `$HOME/.cache/templateflow` |
| `FS_LICENSE` | FreeSurfer license file path (inside container) | — |
| `OMP_NUM_THREADS` | OpenMP thread count | 1 |

### TemplateFlow for Offline Systems

```bash
# On internet-connected node:
export TEMPLATEFLOW_HOME=/path/to/persistent/templateflow
python -c "from templateflow import api; api.get('MNI152NLin2009cAsym')"

# Bind into container:
-B ${TEMPLATEFLOW_HOME}:${TEMPLATEFLOW_HOME}
--env "TEMPLATEFLOW_HOME=$TEMPLATEFLOW_HOME"
```

### Container Base Images

| Version | Base OS | CUDA | FSL | FreeSurfer |
|---|---|---|---|---|
| 1.1.x | Ubuntu 22.04 | 12.2.2 | 6.0.7.15 | 7.4.1 |
| 1.0.x | Ubuntu 20.04 | 11.1.1 | 6.0.7.9 | 7.3.1 |
| 0.24.x | Ubuntu 20.04 | 11.1.1 | 6.0.7.9 | 7.3.1 |

### Memory Requirements

Docker Desktop (macOS): allocate **6GB or more** RAM to avoid "Killed" errors.

---

## 4. QSIPrep CLI Reference

### Positional Arguments

| Argument | Description |
|---|---|
| `bids_dir` | Root folder of BIDS-valid dataset (sub-XXXXX folders at top level) |
| `output_dir` | Output path for preprocessing outcomes and visual reports |
| `analysis_level` | Processing stage. Only `participant` is available |

### BIDS Filtering Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--skip-bids-validation` | flag | `False` | Assume input is BIDS compliant |
| `--participant-label` | list | all | Space-delimited participant IDs (sub- prefix optional) |
| `--session-id` | list | all | Space-delimited session IDs (ses- prefix optional) |
| `--bids-filter-file` | path | — | JSON file with custom PyBIDS filters |
| `--bids-database-dir` | path | — | Path to PyBIDS database for faster indexing |

### Performance Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--nprocs` / `--nthreads` / `--n-cpus` | int | all available | Max threads across all processes |
| `--omp-nthreads` | int | — | Max threads per individual process |
| `--mem` / `--mem-mb` | int | — | Upper bound memory limit (MB) |
| `--low-mem` | flag | `False` | Reduce memory usage (increases disk usage) |
| `--use-plugin` / `--nipype-plugin-file` | path | — | Nipype plugin configuration file |
| `--sloppy` | flag | `False` | Use low-quality tools for speed (**TESTING ONLY**) |

### Workflow Subset Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--anat-only` | flag | `False` | Run anatomical workflows only |
| `--dwi-only` | flag | `False` | Ignore anatomical data; process DWIs only |
| `--boilerplate-only` | flag | `False` | Generate boilerplate only |
| `--reports-only` | flag | `False` | Only generate reports |

### Workflow Configuration

| Argument | Type | Default | Valid Values | Description |
|---|---|---|---|---|
| `--ignore` | list | `[]` | `fieldmaps`, `t2w`, `phase` | Ignore selected aspects |
| `--infant` | flag | `False` | — | Configure for infant brain (MNIInfant template) |
| `--longitudinal` | flag | `False` | — | Treat dataset as longitudinal |
| `--subject-anatomical-reference` | choice | `first-lex` | `first-lex`, `unbiased`, `sessionwise`, `first-alphabetically` | Anatomical space strategy |
| `--skip-anat-based-spatial-normalization` | flag | `False` | — | Skip template space normalization (saves ~20 min) |
| `--anat-modality` | choice | `T1w` | `T1w`, `T2w`, `none` | Anatomical modality for reference |
| `--b0-threshold` | int | `100` | — | Values below this in .bval treated as b=0 |
| `--dwi-denoise-window` | str/int | `auto` | odd int or `auto` | Denoising window size in voxels |
| `--denoise-method` | choice | `dwidenoise` | `dwidenoise`, `patch2self`, `none` | Denoising algorithm |
| `--unringing-method` | choice | `none` | `none`, `mrdegibbs`, `rpg` | Gibbs ringing removal method |
| `--b1-biascorrect-stage` | choice | `final` | `final`, `none`, `legacy` | When to apply B1 bias correction |
| `--no-b0-harmonization` | flag | `False` | — | Skip b=0 intensity rescaling |
| `--denoise-after-combining` | flag | `False` | — | Denoise after combining DWIs |
| `--separate-all-dwis` | flag | `False` | — | Process each DWI separately |
| `--distortion-group-merge` | choice | `none` | `concat`, `average`, `none` | How to combine distortion groups |
| `--anatomical-template` | choice | `MNI152NLin2009cAsym` | `MNI152NLin2009cAsym` | Template space |
| `--output-resolution` | float | **REQUIRED** | — | Isotropic voxel size (mm) for output resampling |

### DWI-to-Anatomical Coregistration

| Argument | Type | Default | Valid Values | Description |
|---|---|---|---|---|
| `--b0-to-t1w-transform` | choice | `Rigid` | `Rigid`, `Affine` | Registration DoF for b0-to-anatomical |
| `--intramodal-template-iters` | int | `0` | — | Iterations for b0 midpoint template |
| `--intramodal-template-transform` | choice | `BSplineSyN` | `Rigid`, `Affine`, `BSplineSyN`, `SyN` | Transform type for intramodal template |

### FreeSurfer Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--fs-license-file` | path | — | Path to FreeSurfer license key file |

### Motion Correction Options

| Argument | Type | Default | Valid Values | Description |
|---|---|---|---|---|
| `--b0-motion-corr-to` | choice | `iterative` | `iterative`, `first` | Align b0s to midpoint or first |
| `--hmc-transform` | choice | `Affine` | `Affine`, `Rigid` | Transform type for head motion correction |
| `--hmc-model` | choice | `eddy` | `none`, `3dSHORE`, `eddy`, `tensor` | Model for generating HMC target images |
| `--eddy-config` | path | — | — | JSON file with custom eddy parameters |
| `--shoreline-iters` | int | `2` | — | Number of SHORELine iterations |

### Fieldmap Options

| Argument | Type | Default | Valid Values | Description |
|---|---|---|---|---|
| `--pepolar-method` | choice | `TOPUP` | `TOPUP`, `DRBUDDI`, `TOPUP+DRBUDDI` | SDC method for PEPOLAR fieldmaps |
| `--fmap-bspline` | flag | `False` | — | B-Spline field fitting (experimental) |
| `--fmap-no-demean` | flag | `True` | — | Do not remove median from fieldmap |

### SyN Distortion Correction

| Argument | Type | Default | Valid Values | Description |
|---|---|---|---|---|
| `--use-syn-sdc` | choice | `False` | `warn`, `error` | Fieldmap-less distortion correction |
| `--force-syn` | flag | `False` | — | Use SyN alongside fieldmap correction |

### Other Options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--version` | flag | — | Show version and exit |
| `-v` / `--verbose` | counter | `0` | Increase verbosity (`-vvv` = debug) |
| `-w` / `--work-dir` | path | — | Working directory for intermediate results |
| `--resource-monitor` | flag | `False` | Enable Nipype resource monitoring |
| `--config-file` | path | — | Pre-generated configuration file |
| `--write-graph` | flag | `False` | Write workflow graph |
| `--stop-on-first-crash` | flag | `False` | Force stopping on first crash |
| `--notrack` | flag | `False` | Opt-out of usage tracking |
| `--debug` | list | — | Debug modes: `fieldmaps`, `pdb`, `all` |

---

## 5. QSIPrep Preprocessing Details

### Motion Correction Models

| Model | Flag Value | Description | Compatible Schemes |
|---|---|---|---|
| **FSL eddy** | `eddy` | Default. Combined motion + eddy + distortion correction | Single-shell, multi-shell |
| **SHORELine** | `3dSHORE` | Iterative model-based correction | Multi-shell, DSI, CS-DSI |
| **Tensor** | `tensor` | Tensor model for target generation | Single-shell, multi-shell |
| **None** | `none` | Basic b=0 registration only | Any (not recommended) |

### SHORELine Algorithm (for non-shelled schemes)

1. Align all b=0 images to midpoint/first
2. Fit 3dSHORE/MAPMRI model to all images
3. Leave-one-out: generate target signal, register image, rotate gradients
4. Repeat with updated DWI and gradient set
5. Output 6-parameter motion estimates per volume

### Denoising Methods

| Method | Flag Value | Description | When Applied |
|---|---|---|---|
| **MP-PCA** | `dwidenoise` | MRtrix3 dwidenoise (default) | Before combining DWIs |
| **Patch2Self** | `patch2self` | DIPY self-supervised denoising | Before combining DWIs |
| **None** | `none` | No denoising | — |

### Denoising Window

The `--dwi-denoise-window` parameter controls the patch size:
- `auto` (default): Calculated from number of DWI volumes
- Integer: Must be odd (e.g., 5, 7, 9)
- **Bug in 1.0.2 and earlier**: Window size of 1 was calculated for short runs (<25 volumes), causing crashes. Fixed in 1.0.2.

### Distortion Correction Options

| Source | Method | Notes |
|---|---|---|
| PEPOLAR fieldmaps | TOPUP, DRBUDDI, TOPUP+DRBUDDI | `--pepolar-method` |
| Phase-difference fieldmaps | Standard SDC | Auto-detected from BIDS |
| No fieldmaps | SyN (fieldmap-less) | `--use-syn-sdc` |

### HCP-Style Processing

```bash
--distortion-group-merge average  # Average images from opposing PE directions
```

### Processing Interpolations

FSL-based workflow: exactly **2 total interpolations** (Eddy + ANTs registration).
Upsampling occurs in a single interpolation step alongside motion and distortion
correction.

---

## 6. QSIPrep Output Specification

### Directory Structure

```
<output_dir>/
├── dataset_description.json
├── sub-<label>.html                    # Visual QA report
├── desc-image_qc.tsv                   # QC metrics (single-line TSV)
└── sub-<label>/
    ├── anat/
    │   ├── sub-<label>_space-ACPC_desc-preproc_T1w.nii.gz
    │   ├── sub-<label>_space-ACPC_desc-brain_mask.nii.gz
    │   ├── sub-<label>_space-ACPC_dseg.nii.gz
    │   ├── sub-<label>_space-ACPC_label-CSF_probseg.nii.gz
    │   ├── sub-<label>_space-ACPC_label-GM_probseg.nii.gz
    │   ├── sub-<label>_space-ACPC_label-WM_probseg.nii.gz
    │   ├── sub-<label>_space-MNI152NLin2009cAsym_desc-preproc_T1w.nii.gz
    │   ├── sub-<label>_space-MNI152NLin2009cAsym_desc-brain_mask.nii.gz
    │   ├── sub-<label>_space-MNI152NLin2009cAsym_dseg.nii.gz
    │   ├── sub-<label>_space-MNI152NLin2009cAsym_label-CSF_probseg.nii.gz
    │   ├── sub-<label>_space-MNI152NLin2009cAsym_label-GM_probseg.nii.gz
    │   ├── sub-<label>_space-MNI152NLin2009cAsym_label-WM_probseg.nii.gz
    │   ├── sub-<label>_from-anat_to-ACPC_mode-image_xfm.mat
    │   ├── sub-<label>_from-ACPC_to-anat_mode-image_xfm.mat
    │   ├── sub-<label>_from-ACPC_to-MNI152NLin2009cAsym_mode-image_xfm.h5
    │   └── sub-<label>_from-MNI152NLin2009cAsym_to-ACPC_mode-image_xfm.h5
    ├── ses-<label>/anat/               # (if multi-session)
    │   ├── sub-<label>_ses-<label>_from-orig_to-anat_mode-image_xfm.txt
    │   └── sub-<label>_ses-<label>_from-anat_to-orig_mode-image_xfm.txt
    └── dwi/
        ├── sub-<label>_space-ACPC_desc-preproc_dwi.nii.gz
        ├── sub-<label>_space-ACPC_desc-preproc_dwi.bval       # FSL format
        ├── sub-<label>_space-ACPC_desc-preproc_dwi.bvec       # FSL format
        ├── sub-<label>_space-ACPC_desc-preproc_dwi.b           # MRTrix format
        ├── sub-<label>_space-ACPC_dwiref.nii.gz                # Reference b=0
        ├── sub-<label>_space-ACPC_desc-brain_mask.nii.gz       # Brain mask
        ├── sub-<label>_space-ACPC_stat-cnr_desc-<label>_dwimap.nii.gz
        ├── sub-<label>_space-ACPC_stat-cnr_desc-<label>_dwimap.json
        └── sub-<label>_desc-confounds_timeseries.tsv
```

### Anatomical Derivatives

| File | Description |
|---|---|
| `*_space-ACPC_desc-preproc_T1w.nii.gz` | N4 bias-corrected T1w in ACPC space |
| `*_space-ACPC_desc-brain_mask.nii.gz` | Binary brain mask (SynthStrip) |
| `*_space-ACPC_dseg.nii.gz` | Tissue class segmentation map (SynthSeg) |
| `*_space-ACPC_label-{CSF,GM,WM}_probseg.nii.gz` | Tissue probability maps |
| `*_space-MNI152NLin2009cAsym_*` | Same files warped to MNI template space |

### DWI Derivatives

| File | Description |
|---|---|
| `*_space-ACPC_desc-preproc_dwi.nii.gz` | Preprocessed DWI 4D series |
| `*_space-ACPC_desc-preproc_dwi.bval` | b-values (FSL format) |
| `*_space-ACPC_desc-preproc_dwi.bvec` | b-vectors (FSL format) |
| `*_space-ACPC_desc-preproc_dwi.b` | Gradient table (MRTrix format) |
| `*_space-ACPC_dwiref.nii.gz` | Reference b=0 image |
| `*_space-ACPC_desc-brain_mask.nii.gz` | DWI brain mask (generous) |
| `*_stat-cnr_desc-*_dwimap.nii.gz` | Contrast-to-noise ratio maps |

### Transform Files

| File | Description |
|---|---|
| `*_from-anat_to-ACPC_mode-image_xfm.mat` | Native anatomical to ACPC |
| `*_from-ACPC_to-anat_mode-image_xfm.mat` | ACPC to native anatomical |
| `*_from-ACPC_to-MNI152NLin2009cAsym_mode-image_xfm.h5` | ACPC to MNI (ANTs composite) |
| `*_from-MNI152NLin2009cAsym_to-ACPC_mode-image_xfm.h5` | MNI to ACPC (inverse) |
| `*_from-orig_to-anat_mode-image_xfm.txt` | Session-specific: original to anatomical |

**Note:** Motion/eddy/distortion transforms from FSL Eddy are NOT exported as
reusable files.

### Confounds TSV Columns

| Column | Description |
|---|---|
| `framewise_displacement` | Head movement between volumes (mm) |
| `trans_x`, `trans_y`, `trans_z` | Translation parameters |
| `rot_x`, `rot_y`, `rot_z` | Rotation parameters |
| `hmc_r2` | Whole-brain R-squared between model target and corrected image |
| `hmc_xcorr` | ANTs cross-correlation score |
| `original_file` | Source DWI filename |
| `grad_x`, `grad_y`, `grad_z` | Gradient direction unit vector |
| `bval` | Gradient strength (b-value) |

### QC Metrics TSV (`desc-image_qc.tsv`)

| Prefix | Description |
|---|---|
| `raw_*` | QC metrics from raw data (DSI Studio methodology) |
| `t1_*` / `mni_*` | QC metrics on preprocessed data |
| `mean_fd`, `max_fd` | Frame-wise displacement statistics |
| `max_translation`, `max_rotation` | Maximum absolute motion |
| `max_rel_translation`, `max_rel_rotation` | Maximum relative motion |
| `t1_dice_distance`, `mni_dice_distance` | Spatial overlap between masks |

### dataset_description.json

QSIPrep generates a BIDS-compliant `dataset_description.json` in the output root:

```json
{
    "Name": "QSIPrep - Preprocessed DWI",
    "BIDSVersion": "1.9.0",
    "DatasetType": "derivative",
    "GeneratedBy": [
        {
            "Name": "qsiprep",
            "Version": "26.0.0",
            "Container": {
                "Type": "docker",
                "Tag": "pennlinc/qsiprep:26.0.0"
            }
        }
    ]
}
```

### Visual QA Reports

One HTML report per subject: `<output_dir>/sub-<label>.html`

Contents:
- Q-space sampling scheme animation (before/after preprocessing)
- Slice-by-slice cross-correlation "carpet" plots
- Registration quality checks
- Distortion correction before/after comparisons
- Brain mask overlays

---

## 7. QSIRecon Overview

QSIRecon builds post-processing workflows that produce biologically meaningful
dMRI derivatives used for hypothesis testing. It integrates methods from:

- **MRTrix3**: Constrained spherical deconvolution (CSD), tractography
- **DSI Studio**: Generalized q-sampling imaging (GQI), AutoTrack
- **DIPY**: DKI, MAPMRI, 3dSHORE
- **PyAFQ**: Automated fiber quantification
- **AMICO**: NODDI model fitting
- **TORTOISE**: Tensor and MAPMRI fitting

### Input Requirements

QSIRecon requires **preprocessed** data as input (not raw BIDS). Primary source
is QSIPrep output. The first argument is the QSIPrep derivatives directory
containing `sub-*` folders.

### Input Types

| `--input-type` | Source | Notes |
|---|---|---|
| (default) | QSIPrep output | Direct compatibility |
| `ukb` | UK BioBank preprocessed dMRI | No MNI transforms; must re-estimate |
| `hcpya` | HCP Young Adult preprocessed | No MNI transforms |

### Anatomical Data Requirements

Varies by workflow:
- **Requires T1w + FreeSurfer**: mrtrix ACT workflows (hsvs, fast)
- **Requires T1w only**: mrtrix noACT workflows
- **No anatomical needed**: amico_noddi, pyafq_tractometry, reorient_fslstd

### FreeSurfer Integration

When provided via `--fs-subjects-dir`:
1. `brain.mgz` is registered to the T1w image
2. Converted to NIfTI with adjusted affine (no extra interpolation)
3. If atlases are requested, brain.mgz is normalized to MNI152NLin2009cAsym
4. Inverse transform brings parcellations into DWI space

---

## 8. QSIRecon CLI Reference

### Positional Arguments

| Argument | Description |
|---|---|
| `input_dir` | QSIPrep output directory (containing sub-* folders) |
| `output_dir` | Output path for reconstruction derivatives |
| `analysis_level` | Processing stage: `participant` |

### Key Arguments

| Argument | Type | Description |
|---|---|---|
| `--recon-spec` | string | Reconstruction workflow name or path to custom JSON |
| `--atlases` | list | Atlases for connectivity analysis |
| `--input-type` | choice | Input data type: default, `ukb`, `hcpya` |
| `--fs-subjects-dir` | path | FreeSurfer subjects directory |
| `--fs-license-file` | path | FreeSurfer license file |
| `--participant-label` | list | Subject IDs to process |
| `--skip-odf-reports` | flag | Skip ODF report generation |
| `--nthreads` | int | Max threads across all processes |
| `--omp-nthreads` | int | Max threads per process |
| `--mem-mb` | int | Memory limit in MB |
| `-w` / `--work-dir` | path | Working directory |
| `-v` / `--verbose` | counter | Increase verbosity |

---

## 9. QSIRecon Built-In Workflows

All pipeline definitions are YAML files in the QSIRecon source:
[qsirecon/data/pipelines/](https://github.com/PennLINC/qsirecon/tree/main/qsirecon/data/pipelines/)

Docs: [QSIRecon Built-In Workflows](https://qsirecon.readthedocs.io/en/latest/builtin_workflows.html)

### MRTrix3-Based Workflows

These vary on two axes: **shell requirement** (multi-shell vs single-shell SS3T) and
**anatomical constraint** (ACT with HSVS or FAST segmentation, or no ACT).

| Workflow | Shell Req. | ACT | Segmentation | FreeSurfer Required | YAML |
|---|---|---|---|---|---|
| `mrtrix_multishell_msmt_ACT-hsvs` | Multi-shell | Yes | Hybrid surface-volume | Yes | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/mrtrix_multishell_msmt_ACT-hsvs.yaml) |
| `mrtrix_multishell_msmt_ACT-fast` | Multi-shell | Yes | FSL FAST | Yes | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/mrtrix_multishell_msmt_ACT-fast.yaml) |
| `mrtrix_multishell_msmt_noACT` | Multi-shell | No | None | No | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/mrtrix_multishell_msmt_noACT.yaml) |
| `mrtrix_singleshell_ss3t_ACT-hsvs` | Single-shell | Yes | Hybrid surface-volume | Yes | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/mrtrix_singleshell_ss3t_ACT-hsvs.yaml) |
| `mrtrix_singleshell_ss3t_ACT-fast` | Single-shell | Yes | FSL FAST | Yes | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/mrtrix_singleshell_ss3t_ACT-fast.yaml) |
| `mrtrix_singleshell_ss3t_noACT` | Single-shell | No | None | No | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/mrtrix_singleshell_ss3t_noACT.yaml) |

All MRTrix3 workflows use iFOD2 probabilistic tracking with SIFT2 weighting:
- 10 million streamlines
- 250mm max length, 30mm min length
- FOD power 0.33
- Produce 4 connectivity matrix variants per atlas (raw/SIFT x count/length)

### DSI Studio Workflows

| Workflow | Method | Description | YAML |
|---|---|---|---|
| `dsi_studio_gqi` | GQI + deterministic tractography | 5M streamlines. Produces QA, GFA, ISO, RDI, tensor params | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/dsi_studio_gqi.yaml) |
| `dsi_studio_autotrack` | QSDR + 56 bundle AutoTrack | MNI-space reconstruction with Hausdorff distance matching | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/dsi_studio_autotrack.yaml) |

### DIPY Workflows

| Workflow | Model | Outputs | YAML |
|---|---|---|---|
| `dipy_dki` | Diffusion Kurtosis Imaging | AK, RK, MK, AD, RD, MD, FA, plus microstructural params | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/dipy_dki.yaml) |
| `dipy_mapmri` | MAPMRI (EAP estimation) | RTOP, RTAP, QIV, MSD scalars + ODFs | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/dipy_mapmri.yaml) |
| `dipy_3dshore` | BrainSuite 3dSHORE | Anisotropy scalars + ODFs | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/dipy_3dshore.yaml) |

### PyAFQ Workflows

| Workflow | Description | YAML |
|---|---|---|
| `pyafq_tractometry` | Automated Fiber Quantification; recognizes major WM pathways | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/pyafq_tractometry.yaml) |
| `mrtrix_multishell_msmt_pyafq_tractometry` | Combines MRTrix3 IFOD2 with PyAFQ analysis | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/mrtrix_multishell_msmt_pyafq_tractometry.yaml) |

### Microstructural / Scalar Workflows

| Workflow | Description | YAML |
|---|---|---|
| `amico_noddi` | NODDI via AMICO: ICVF, ISOVF, OD scalars | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/amico_noddi.yaml) |
| `TORTOISE` | TORTOISE tensor + MAPMRI fitting | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/TORTOISE.yaml) |
| `multishell_scalarfest` | **Composite**: DKI + TORTOISE + GQI + NODDI (no tractography) | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/multishell_scalarfest.yaml) |
| `hbcd_scalar_maps` | **Composite**: DKI + TORTOISE + GQI + DSI autotrack | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/hbcd_scalar_maps.yaml) |
| `ss3t_fod_autotrack` | Single-shell FOD variant of autotrack | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/ss3t_fod_autotrack.yaml) |

**Note on composite specs**: `multishell_scalarfest` subsumes the individual `dipy_dki`,
`TORTOISE`, `dsi_studio_gqi`, and `amico_noddi` specs. `hbcd_scalar_maps` subsumes
`dipy_dki`, `TORTOISE`, `dsi_studio_gqi`, and `dsi_studio_autotrack`. Running a
composite spec eliminates the need to run its constituent specs separately.

### Study-Specific Workflows

| Workflow | Description | YAML |
|---|---|---|
| `abcd_recon` | ABCD study-specific reconstruction | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/abcd_recon.yaml) |

### Utility Workflows

| Workflow | Description | YAML |
|---|---|---|
| `reorient_fslstd` | Reorient preprocessed DWI to FSL standard orientation | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/reorient_fslstd.yaml) |

### Experimental Workflows

| Workflow | Description | YAML |
|---|---|---|
| `csdsi_3dshore` | For DSI/CS-DSI data; imputes multishell HCP sampling scheme | [YAML](https://github.com/PennLINC/qsirecon/blob/main/qsirecon/data/pipelines/csdsi_3dshore.yaml) |

---

## 10. QSIRecon Output Specification

### Directory Structure

```
<output_dir>/
├── dataset_description.json
├── logs/
├── sub-<label>/
│   └── [ses-<label>/]
│       └── dwi/
│           ├── sub-<label>_seg-<atlas>_dseg.mif.gz
│           ├── sub-<label>_seg-<atlas>_dseg.nii.gz
│           └── sub-<label>_seg-<atlas>_dseg.txt
└── derivatives/
    ├── qsirecon-DKI/
    │   ├── dataset_description.json
    │   ├── sub-<label>.html
    │   └── sub-<label>/dwi/
    │       ├── *_model-DKI_param-AK_dwimap.nii.gz
    │       ├── *_model-DKI_param-RK_dwimap.nii.gz
    │       ├── *_model-DKI_param-MK_dwimap.nii.gz
    │       ├── *_model-DKI_param-KFA_dwimap.nii.gz
    │       ├── *_model-tensor_param-AD_dwimap.nii.gz
    │       ├── *_model-tensor_param-RD_dwimap.nii.gz
    │       ├── *_model-tensor_param-MD_dwimap.nii.gz
    │       └── *_model-tensor_param-FA_dwimap.nii.gz
    ├── qsirecon-TORTOISE/
    │   └── sub-<label>/dwi/
    │       ├── *_model-MAPMRI_param-NG_dwimap.nii.gz
    │       ├── *_model-MAPMRI_param-PA_dwimap.nii.gz
    │       ├── *_model-MAPMRI_param-RTOP_dwimap.nii.gz
    │       ├── *_model-MAPMRI_param-RTAP_dwimap.nii.gz
    │       ├── *_model-tensor_param-AD_dwimap.nii.gz
    │       └── *_model-tensor_param-MD_dwimap.nii.gz
    ├── qsirecon-DSIStudio/
    │   └── sub-<label>/dwi/
    │       ├── *_model-tensor_param-txx_dwimap.nii.gz
    │       ├── *_model-tensor_param-txy_dwimap.nii.gz
    │       ├── *_model-tensor_param-txz_dwimap.nii.gz
    │       ├── *_model-tensor_param-tyy_dwimap.nii.gz
    │       ├── *_model-tensor_param-tyz_dwimap.nii.gz
    │       ├── *_model-tensor_param-tzz_dwimap.nii.gz
    │       ├── *_model-GQI_param-QA_dwimap.nii.gz
    │       ├── *_model-GQI_param-GFA_dwimap.nii.gz
    │       └── *_model-GQI_param-ISO_dwimap.nii.gz
    └── atlases/                        # If atlases requested
        └── <atlas-name>/
            └── connectivity matrices
```

### Connectivity Matrix Outputs

MRTrix3 workflows produce per atlas:
- Raw streamline counts
- SIFT-weighted streamline counts
- Mean length (raw)
- Mean length (SIFT-weighted)

DSI Studio workflows produce per atlas:
- "pass" counting: count, normalized count, mean length, GFA
- "end" counting: count, normalized count, mean length, GFA

### BIDS Extension Proposals Referenced

| BEP | Title |
|---|---|
| BEP016 | Diffusion weighted imaging derivatives |
| BEP017 | Connectivity matrices |
| BEP038 | Atlas specification |

---

## 11. Available Atlases

These atlases are built into QSIRecon and selected with `--atlases`.
All are defined in **MNI152NLin2009cAsym** space.

Source: [PennLINC/AtlasPack](https://github.com/PennLINC/AtlasPack)

### 4S Atlas Series (Schaefer Supplemented with Subcortical Structures)

The "4S" name refers to combining Schaefer cortical parcels with **4 subcortical
source atlases**, yielding a fixed set of **56 subcortical regions** appended to
each Schaefer resolution. These are the recommended atlases for whole-brain
structural connectivity.

| Atlas Name | Schaefer Cortical | Subcortical | Total Regions |
|---|---|---|---|
| `4S156Parcels` | 100 | 56 | 156 |
| `4S256Parcels` | 200 | 56 | 256 |
| `4S356Parcels` | 300 | 56 | 356 |
| `4S456Parcels` | 400 | 56 | 456 |
| `4S556Parcels` | 500 | 56 | 556 |
| `4S656Parcels` | 600 | 56 | 656 |
| `4S756Parcels` | 700 | 56 | 756 |
| `4S856Parcels` | 800 | 56 | 856 |
| `4S956Parcels` | 900 | 56 | 956 |
| `4S1056Parcels` | 1000 | 56 | 1056 |

**The 56 subcortical regions come from 4 sources:**

| Source Atlas | Regions | Structures | Reference |
|---|---|---|---|
| **CIT168Subcortical** | 28 (14 bilateral) | Putamen, caudate, NAc, GP internal/external, SN, red nucleus, STN, hypothalamus, mammillary, habenular, ventral pallidum, extended amygdala | Pauli et al. 2018, *Scientific Data* 5:180063 |
| **ThalamusHCP** | 14 (7 bilateral) | Pulvinar, anterior, medio-dorsal, VLD, CL-LP-MP, ventral anterior, VLV | Najdenovska et al. 2018, *Scientific Data* 5:180270 |
| **HCPSubcortical** | 4 (2 bilateral) | Hippocampus, amygdala | Glasser et al. 2013, *NeuroImage* 80:105-124 |
| **Cerebellum MDTB** | 10 | 10 functional cerebellar regions | King et al. 2019, *Nature Neuroscience* 22(8):1371-1378 |

**Cortical component reference:**
Schaefer, A. et al. (2018). Local-global parcellation of the human cerebral cortex
from intrinsic functional connectivity MRI. *Cerebral Cortex*, 28(9), 3095-3114.
https://doi.org/10.1093/cercor/bhx179

Construction details: [Volumetric4S.ipynb](https://github.com/PennLINC/AtlasPack/blob/main/Volumetric4S.ipynb)

### Classic Atlases

The "Ext" (Extended) suffix indicates the original cortical-only atlas has been
extended with the same subcortical + cerebellar regions used in the 4S series.

| Atlas Name | Regions | Description | Reference |
|---|---|---|---|
| `AAL116` | 116 | Automated Anatomical Labeling — macro-anatomical parcellation based on sulcal landmarks | Tzourio-Mazoyer et al. 2002, *NeuroImage* 15(1):273-289 |
| `Brainnetome246Ext` | 246 | Connectivity-based parcellation using structural and functional connectivity | Fan et al. 2016, *Cerebral Cortex* 26(8):3508-3526. [atlas.brainnetome.org](https://atlas.brainnetome.org/) |
| `AICHA384Ext` | 384 | Atlas of Intrinsic Connectivity of Homotopic Areas — parcels defined by inter-hemispheric homotopic connectivity | Joliot et al. 2015, *J Neuroscience Methods* 254:46-59 |
| `Gordon333Ext` | 333 | Resting-state fMRI boundary-mapping parcellation | Gordon et al. 2016, *Cerebral Cortex* 26(1):288-303 |

### Choosing an Atlas

- **For connectivity matrices at specific granularity**: Use the 4S series at the
  resolution matching your analysis needs (4S256 or 4S456 are common choices)
- **For anatomical ROI analysis**: AAL116 provides familiar macro-anatomical labels
- **For functional network analysis**: Gordon333Ext or Schaefer-based 4S atlases
  align with resting-state network definitions
- **For maximum brain coverage**: Any "Ext" or 4S atlas includes subcortical +
  cerebellar regions, unlike cortical-only parcellations

---

## 12. Available Diffusion Models

QSIRecon provides 5 core diffusion models yielding **40+ whole-brain parametric
microstructure maps** per session:

### DTI (Diffusion Tensor Imaging)

Computes a Gaussian diffusion tensor per voxel.

| Scalar | Description |
|---|---|
| FA | Fractional Anisotropy (0-1 directional dependency) |
| MD | Mean Diffusivity (trace / 3) |
| AD | Axial Diffusivity (lambda-1) |
| RD | Radial Diffusivity (mean of lambda-2, lambda-3) |
| Trace | Sum of eigenvalues |
| txx, txy, txz, tyy, tyz, tzz | Individual tensor components |

### DKI (Diffusion Kurtosis Imaging)

Extension of DTI capturing non-Gaussian diffusion.

| Scalar | Description |
|---|---|
| AK | Axial Kurtosis |
| RK | Radial Kurtosis |
| MK | Mean Kurtosis |
| KFA | Kurtotic Fractional Anisotropy |
| All DTI scalars | (also computed) |

### MAP-MRI (Mean Apparent Propagator MRI)

Estimates the ensemble average propagator (EAP).

| Scalar | Description |
|---|---|
| RTOP | Return-to-Origin Probability |
| RTAP | Return-to-Axis Probability |
| QIV | Q-space Inverse Variance |
| MSD | Mean Squared Displacement |
| NG | Non-Gaussianity |
| PA | Propagator Anisotropy |

### GQI (Generalized q-Sampling Imaging)

Q-space interpolation method from DSI Studio.

| Scalar | Description |
|---|---|
| QA | Quantitative Anisotropy |
| GFA | Generalized Fractional Anisotropy |
| ISO | Isotropic component |
| RDI | Restricted Diffusion Imaging |

### NODDI (Neurite Orientation Dispersion and Density Imaging)

Biophysical model via AMICO framework.

| Scalar | Description |
|---|---|
| ICVF | Intracellular Volume Fraction |
| ISOVF | Isotropic Volume Fraction |
| OD | Orientation Dispersion |
| RMSE | Root Mean Squared Error of fit |

---

## 13. BIDS Compliance

### Required BIDS Input Structure

```
project_root/
├── dataset_description.json
├── participants.tsv            # Optional
├── sub-<label>/
│   ├── anat/
│   │   └── sub-<label>_T1w.nii.gz
│   └── dwi/
│       ├── sub-<label>_dwi.nii.gz
│       ├── sub-<label>_dwi.bval
│       ├── sub-<label>_dwi.bvec
│       └── sub-<label>_dwi.json     # Sidecar with PE direction, etc.
└── [fmap/]                     # Optional fieldmaps
```

### BIDS Entities Used by QSIPrep

| Entity | Key | Description |
|---|---|---|
| subject | `sub-` | Subject identifier |
| session | `ses-` | Session identifier (optional) |
| acquisition | `acq-` | Acquisition variant (used in DWI grouping) |
| run | `run-` | Run index |
| space | `space-` | Output space: `ACPC`, `MNI152NLin2009cAsym` |
| description | `desc-` | Description: `preproc`, `brain`, `confounds` |
| label | `label-` | Tissue label: `CSF`, `GM`, `WM` |
| suffix | — | Data type: `dwi`, `T1w`, `mask`, `dseg`, `probseg`, `dwiref`, `dwimap` |
| stat | `stat-` | Statistic type: `cnr` |

### BIDS Entities Used by QSIRecon

| Entity | Key | Description |
|---|---|---|
| model | `model-` | Diffusion model: `tensor`, `DKI`, `GQI`, `MAPMRI` |
| param | `param-` | Parameter name: `FA`, `MD`, `txx`, `QA`, etc. |
| seg | `seg-` | Atlas segmentation: atlas name |

### Scan Grouping (MultipartID)

QSIPrep automatically groups DWI scans sharing the same susceptibility distortion
characteristics (matching `IntendedFor` fieldmap specs). Scans are merged before
motion correction unless `--separate-all-dwis` is specified.

- Default: all DWIs in same session are grouped for merging
- Never: merging never occurs across sessions
- When `MultipartID` BIDS metadata is present, scans with matching IDs are grouped

---

## 14. Spaces & Orientations

### Output Orientation

All QSIPrep derivatives are in **LPS+** orientation (Left-Posterior-Superior,
positive direction). This is the same convention as DSI Studio's btable.

This differs from fMRIPrep, which uses RAS+ orientation.

### ACPC Space

The primary output space for QSIPrep is **ACPC** (Anterior Commissure - Posterior
Commissure aligned). This is a subject-specific space with:
- Images reoriented to LPS+
- Aligned to the AC-PC line
- Not warped to any template

In QSIPrep versions prior to 0.24.0, this space was called `T1wACPC`. The rename
was: `T1wACPC` -> `ACPC` and `T1wNative` -> `anat`.

### MNI152NLin2009cAsym Space

Optional template space outputs (can be disabled with
`--skip-anat-based-spatial-normalization`). Uses the asymmetric version of
MNI152NLin2009c from TemplateFlow.

For infant processing (`--infant`), the MNIInfant template is used instead,
with automatic cohort selection based on participant age.

### Processing Orientation Chain

```
Input (any orientation)
    --> LPS+ (conform step)
    --> LAS+ (TOPUP/eddy internal processing)
    --> LPS+ (final output space)
```

---

## 15. Eddy Configuration

### Default Parameters (`eddy_params.json`)

```json
{
    "flm": "quadratic",
    "slm": "linear",
    "fep": false,
    "interp": "spline",
    "nvoxhp": 1000,
    "fudge_factor": 10,
    "dont_sep_offs_move": false,
    "dont_peas": false,
    "niter": 5,
    "method": "jac",
    "repol": true,
    "num_threads": 1,
    "is_shelled": true,
    "use_cuda": false,
    "cnr_maps": true,
    "residuals": false,
    "output_type": "NIFTI_GZ",
    "args": ""
}
```

### Parameter Descriptions

| Parameter | Default | Description |
|---|---|---|
| `flm` | `"quadratic"` | First-level EC model (none/linear/quadratic) |
| `slm` | `"linear"` | Second-level EC model (none/linear/quadratic) |
| `fep` | `false` | Fill empty planes in data |
| `interp` | `"spline"` | Interpolation method (spline/trilinear) |
| `nvoxhp` | `1000` | Number of voxels used for hyperparameter estimation |
| `fudge_factor` | `10` | Fudge factor for hyperparameter estimation |
| `dont_sep_offs_move` | `false` | Do NOT separate field offset from subject movement |
| `dont_peas` | `false` | Do NOT perform post-eddy alignment of shells |
| `niter` | `5` | Number of iterations |
| `method` | `"jac"` | Resampling method (jac/lsr) |
| `repol` | `true` | Detect and replace outlier slices |
| `num_threads` | `1` | Number of threads for eddy |
| `is_shelled` | `true` | Data is on concentric shells |
| `use_cuda` | `false` | Use GPU acceleration |
| `cnr_maps` | `true` | Output CNR maps |
| `residuals` | `false` | Output residual maps |
| `output_type` | `"NIFTI_GZ"` | Output file format |
| `args` | `""` | Additional command-line arguments |

### Custom Eddy Configuration

Pass custom eddy parameters via `--eddy-config /path/to/eddy.json`.

When `use_cuda` is `true`:
- CUDA 12.2.2 runtime is included in the 1.1.x Docker image
- CUDA 11.1.1 in the 1.0.x image
- Dramatically faster eddy processing
- Required for `mporder` (slice timing) support

### mporder Support (v0.21.1+)

Adding `"mporder": N` to eddy config enables:
- Automatic slice timing inference
- Within-volume (slice-to-volume) motion correction
- Requires `use_cuda: true`

---

## 16. The QSIPrep/QSIRecon Split

### Timeline

| Version | Date | Event |
|---|---|---|
| QSIPrep 0.22.x | Jul 2024 | Last version with embedded reconstruction |
| QSIPrep 0.23.0 | Aug 2024 | Reconstruction workflows **removed** from QSIPrep |
| QSIPrep 0.24.0 | Nov 2024 | Last `pennbbl` organization release. Major naming changes |
| QSIPrep 1.0.0rc1 | Nov 2024 | First `pennlinc` organization release |
| QSIRecon 1.0.0rc1 | Nov 2023 | First QSIRecon standalone prerelease |
| QSIRecon 1.0.0 | Mar 2024 | QSIRecon stable release |
| QSIPrep 1.0.0 | Apr 2025 | QSIPrep stable 1.0 release |

### What Changed

**Before the split (QSIPrep <= 0.22.x):**
- QSIPrep handled both preprocessing AND reconstruction
- `--recon-spec` was a QSIPrep argument
- Single Docker image: `pennbbl/qsiprep`
- Single process: preprocess then reconstruct

**After the split (QSIPrep >= 0.23.0, QSIRecon >= 1.0.0):**
- QSIPrep handles preprocessing ONLY
- QSIRecon is a separate package/container for reconstruction
- Two Docker images: `pennlinc/qsiprep` + `pennlinc/qsirecon`
- Two-step process: preprocess with QSIPrep, then reconstruct with QSIRecon
- `--recon-spec` is now a QSIRecon argument only

### Migration Checklist

1. **Docker image**: `pennbbl/qsiprep` -> `pennlinc/qsiprep` (preprocessing) + `pennlinc/qsirecon` (reconstruction)
2. **CLI**: Remove `--recon-spec` from QSIPrep calls; add it to QSIRecon calls
3. **Input**: QSIRecon takes QSIPrep output directory as its input
4. **Output naming**: `T1wACPC` -> `ACPC`, `T1wNative` -> `anat`
5. **Confounds**: `_confounds.tsv` -> `_desc-confounds_timeseries.tsv`
6. **CNR**: `_cnr.nii.gz` -> `_stat-cnr_dwimap.nii.gz`
7. **QSIRecon CLI**: `--recon-input-pipeline` replaced with `--input-type`
8. **Parameters**: `mfp` and `mdp` entities merged into single `param` entity
9. **Atlas management**: Reorganized; use `--atlases` flag

### Breaking Changes in QSIRecon 1.0.0

- Renamed from QSIPrep to QSIRecon codebase
- Outputs restructured into proper BIDS datasets
- `--recon-input-pipeline` replaced with `--input-type`
- `--longitudinal` argument removed (unused)
- All parameters and model names converted to lowercase
- Connectivity field names made MATLAB-compatible
- Docker wrapper removed

### Breaking Changes in QSIPrep 1.0.0

- Docker deployment: `pennbbl/qsiprep` -> `pennlinc/qsiprep`
- Common metadata relocated to JSON top level
- Patch radius calculated from DWI volume count
- Output directory specification for derivative datasinks

### Breaking Changes in QSIPrep 0.24.0

- `--anat-space-definition` -> `--subject-anatomical-reference`
- Underscore parameter versions removed
- `T1wACPC` -> `ACPC`; `T1wNative` -> `anat`
- CNR suffix changed to `stat-cnr_dwimap`
- Confounds renamed to `desc-confounds_timeseries`

---

## 17. Version History

### QSIPrep Releases

| Version | Date | Key Changes |
|---|---|---|
| **1.1.1** | Jan 2026 | SynthSeg bugfix |
| **1.1.0** | Jan 2026 | Ubuntu 22.04, CUDA 12.2.2, FSL 6.0.7.15, FreeSurfer 7.4.1 |
| **1.0.2** | Nov 2025 | Critical fix: denoising window calc for short runs |
| **1.0.1** | Apr 2025 | DWI grouped by MultipartID; entity support fixes |
| **1.0.0** | Apr 2025 | pennbbl -> pennlinc; metadata restructure |
| **1.0.0rc1** | Nov 2024 | HBCD first data release prerelease |
| **0.24.0** | Nov 2024 | Major naming changes (ACPC/anat); last pennbbl release |
| **0.23.0** | Aug 2024 | Reconstruction removed; TemplateFlow adopted; nireports |
| **0.22.0** | Jul 2024 | Last version with reconstruction; HSVS fixes |
| **0.21.4** | May 2024 | Niworkflows adoption |
| **0.21.1** | Apr 2024 | mporder support; FSL 6.0.7.8 critical fixes |
| **0.20.0** | Jan 2024 | TOPUP+DRBUDDI; Python 3.10 |
| **0.19.0** | Aug 2023 | CPU memory optimization for SynthSeg/SynthStrip |
| **0.18.0** | Jun 2023 | SynthStrip + SynthSeg integration; DSI Studio AutoTrack |
| **0.16.1** | Oct 2022 | Critical ABCD fix: raw b=0 for TOPUP |
| **0.16.0RC1** | May 2022 | PyAFQ integration |
| **0.15.2** | Mar 2022 | **DEPRECATED**: connectome pipeline bug |
| **0.14.0** | Jul 2021 | NODDI workflow added |
| **0.13.0** | May 2021 | BIDS filter file support |
| **0.12.2** | Nov 2020 | Infant support (`--infant`, `--dwi-only`) |
| **0.11.0** | Aug 2020 | T1w normalization default ON; DWI merging default ON |
| **0.9.0** | Jun 2020 | HCP lifespan support; `--distortion-group-merge` |
| **0.6.0** | Oct 2019 | LAS+ orientation fix for TOPUP/eddy; built-in recon |

### QSIRecon Releases

| Version | Date | Key Changes |
|---|---|---|
| **1.2.0** | Feb 2025 | dkimicro/wmti disabled; MD from TORTOISE; MSDKI; Ubuntu 22.04 |
| **1.1.1** | Aug 2024 | Critical multi-session/multi-run fix |
| **1.1.0** | Apr 2024 | Tissue fraction modulated ICVF/OD; DKI microstructure |
| **1.0.1** | Mar 2024 | DSIQ5 extrapolation option |
| **1.0.0** | Mar 2024 | Stable release; BIDS output restructure; atlas reorganization |
| **1.0.0rc1** | Nov 2023 | Initial prerelease for HBCD |

---

## 18. TI-Toolbox Integration Notes

### Current Configuration (tit/constants.py)

```python
QSI_QSIPREP_IMAGE = "pennlinc/qsiprep"
QSI_QSIRECON_IMAGE = "pennlinc/qsirecon"
QSI_QSIPREP_IMAGE_TAG = "26.0.0"
QSI_QSIRECON_IMAGE_TAG = "26.0.0"
```

**Version Note:** As of May 2026, TI-Toolbox targets the synchronized PennLINC
26.0.0 container line for both QSIPrep and QSIRecon. There is no QSIPrep 1.2.0
container tag; older v1.x-compatible defaults were QSIPrep 1.1.1 and QSIRecon
1.2.0. The 26.0.0 upgrade was smoke-tested for CLI compatibility, but DWI/QSI
outputs may differ from v1.x containers because upstream dependencies and
packaging changed.

### Integration Architecture

TI-Toolbox uses **Docker-out-of-Docker (DooD)** pattern:
- The SimNIBS container spawns QSIPrep/QSIRecon as sibling containers
- `LOCAL_PROJECT_DIR` env var maps container paths to host paths
- FreeSurfer license is staged from SimNIBS container into project dir

### Key Files

| File | Purpose |
|---|---|
| `tit/pre/qsi/config.py` | Dataclass configs: `QSIPrepConfig`, `QSIReconConfig`, `ResourceConfig` |
| `tit/pre/qsi/qsiprep.py` | `run_qsiprep()` -- spawns QSIPrep container |
| `tit/pre/qsi/qsirecon.py` | `run_qsirecon()` -- spawns QSIRecon container(s) |
| `tit/pre/qsi/docker_builder.py` | `DockerCommandBuilder` -- constructs Docker CLI commands |
| `tit/pre/qsi/utils.py` | Path resolution, validation, image pulling |
| `tit/pre/qsi/dti_extractor.py` | Convert QSIRecon tensor output to SimNIBS format |
| `tit/constants.py` | Image names, tags, recon specs, atlases, defaults |

### Output Locations in TI-Toolbox BIDS Layout

```
project_root/
├── derivatives/
│   ├── qsiprep/
│   │   ├── dataset_description.json
│   │   └── sub-<label>/
│   │       ├── anat/   (ACPC-aligned T1w, masks, segmentations)
│   │       └── dwi/    (preprocessed DWI, bval, bvec, confounds)
│   ├── .qsiprep_work/  (intermediate files, can be deleted)
│   ├── qsirecon/
│   │   ├── dataset_description.json
│   │   └── sub-<label>/
│   │       └── dwi/    (atlas segmentations)
│   ├── .qsirecon_work/ (intermediate files, can be deleted)
│   └── SimNIBS/
│       └── sub-<label>/
│           └── m2m_<label>/
│               ├── DTI_ACPC_tensor.nii.gz      # Intermediate
│               └── DTI_coregT1_tensor.nii.gz   # Final for SimNIBS
```

### Recon Specs Configured in TI-Toolbox

All 21 built-in specs are available to users via the GUI and CLI (see `tit/constants.py`):

```python
QSI_RECON_SPECS = [
    # MRTrix3 CSD + tractography (pick based on shell count + anatomy)
    "mrtrix_multishell_msmt_ACT-hsvs",
    "mrtrix_multishell_msmt_ACT-fast",   # default
    "mrtrix_multishell_msmt_noACT",
    "mrtrix_singleshell_ss3t_ACT-hsvs",
    "mrtrix_singleshell_ss3t_ACT-fast",
    "mrtrix_singleshell_ss3t_noACT",
    # DSI Studio
    "dsi_studio_gqi",                     # tensor components for SimNIBS
    "dsi_studio_autotrack",
    # DIPY
    "dipy_dki",
    "dipy_mapmri",
    "dipy_3dshore",
    # Microstructural
    "amico_noddi",
    # PyAFQ
    "pyafq_tractometry",
    "mrtrix_multishell_msmt_pyafq_tractometry",
    # Composite (subsume multiple individual specs)
    "ss3t_fod_autotrack",
    "multishell_scalarfest",              # = DKI+TORTOISE+GQI+NODDI
    "hbcd_scalar_maps",                   # = DKI+TORTOISE+GQI+autotrack
    "TORTOISE",
    # Utility / experimental
    "reorient_fslstd",
    "csdsi_3dshore",
    "abcd_recon",
]
```

For SimNIBS anisotropic simulations, the recommended spec is
**`dsi_studio_gqi`** because it produces the 6 individual tensor component
files (txx, txy, txz, tyy, tyz, tzz) required by the DTI extractor.

### Atlases Configured in TI-Toolbox

All 14 atlases are available (see `tit/constants.py`). Defaults: `["4S156Parcels", "AAL116"]`.

```python
QSI_ATLASES = [
    # 4S series: Schaefer cortical + 56 subcortical (resolution variants)
    "4S156Parcels", "4S256Parcels", "4S356Parcels", "4S456Parcels",
    "4S556Parcels", "4S656Parcels", "4S756Parcels", "4S856Parcels",
    "4S956Parcels", "4S1056Parcels",
    # Classic atlases (extended with subcortical)
    "AAL116", "Brainnetome246Ext", "AICHA384Ext", "Gordon333Ext",
]
```

### Known Limitations

- **ARM Mac incompatibility**: QSIPrep/QSIRecon Docker images do not support
  ARM architecture (Apple Silicon). This is a known upstream limitation.
- **DWI-only mode**: When `--anat-modality none` is used in QSIPrep, QSIRecon
  must re-estimate spatial normalization from the DWI reference image.
- **Large working directories**: QSIPrep work directories can consume 10-50GB
  per subject. The `.qsiprep_work` and `.qsirecon_work` directories can be
  safely deleted after successful runs.

---

## Sources

### Software Documentation
- [QSIPrep Documentation](https://qsiprep.readthedocs.io/)
- [QSIPrep Usage](https://qsiprep.readthedocs.io/en/latest/usage.html)
- [QSIPrep Preprocessing](https://qsiprep.readthedocs.io/en/latest/preprocessing.html)
- [QSIPrep Installation](https://qsiprep.readthedocs.io/en/latest/installation.html)
- [QSIPrep Changelog](https://qsiprep.readthedocs.io/en/latest/changes.html)
- [QSIPrep GitHub](https://github.com/PennLINC/qsiprep)
- [QSIRecon Documentation](https://qsirecon.readthedocs.io/)
- [QSIRecon Built-In Workflows](https://qsirecon.readthedocs.io/en/latest/builtin_workflows.html)
- [QSIRecon Pipeline YAMLs (GitHub)](https://github.com/PennLINC/qsirecon/tree/main/qsirecon/data/pipelines/)
- [QSIRecon Input Data](https://qsirecon.readthedocs.io/en/latest/input_data.html)
- [QSIRecon Models](https://qsirecon.readthedocs.io/en/latest/models.html)
- [QSIRecon Outputs](https://qsirecon.readthedocs.io/en/stable/outputs.html)
- [QSIRecon Changelog](https://qsirecon.readthedocs.io/en/stable/changes.html)
- [QSIRecon GitHub](https://github.com/PennLINC/qsirecon)
- [QSIPrep Docker Hub](https://hub.docker.com/r/pennlinc/qsiprep)
- [FSL eddy_params.json (GitHub)](https://github.com/PennLINC/qsiprep/blob/master/qsiprep/data/eddy_params.json)
- [BIDS Derivatives Specification](https://bids-specification.readthedocs.io/en/stable/modality-agnostic-files/dataset-description.html)

### Atlas Resources
- [PennLINC AtlasPack (GitHub)](https://github.com/PennLINC/AtlasPack) — 4S atlas construction
- [4S Volumetric Construction Notebook](https://github.com/PennLINC/AtlasPack/blob/main/Volumetric4S.ipynb)
- [Brainnetome Atlas](https://atlas.brainnetome.org/)
- [AICHA Atlas](https://www.gin.cnrs.fr/en/tools/aicha/)

### Key Papers
- Cieslak, M. et al. (2021). QSIPrep: an integrative platform for preprocessing and reconstructing diffusion MRI data. *Nature Methods* 18, 775-778. https://doi.org/10.1038/s41592-021-01185-5
- Schaefer, A. et al. (2018). Local-global parcellation of the human cerebral cortex from intrinsic functional connectivity MRI. *Cerebral Cortex* 28(9), 3095-3114. https://doi.org/10.1093/cercor/bhx179
- Pauli, W.M. et al. (2018). A high-resolution probabilistic in vivo atlas of human subcortical brain nuclei. *Scientific Data* 5, 180063. https://doi.org/10.1038/sdata.2018.63
- Najdenovska, E. et al. (2018). In-vivo probabilistic atlas of human thalamic nuclei based on diffusion-weighted MRI. *Scientific Data* 5, 180270. https://doi.org/10.1038/sdata.2018.270
- King, M. et al. (2019). Functional boundaries in the human cerebellum revealed by a multi-domain task battery. *Nature Neuroscience* 22(8), 1371-1378.
- Tzourio-Mazoyer, N. et al. (2002). Automated anatomical labeling of activations in SPM. *NeuroImage* 15(1), 273-289.
- Fan, L. et al. (2016). The Human Brainnetome Atlas. *Cerebral Cortex* 26(8), 3508-3526. https://doi.org/10.1093/cercor/bhw157
- Joliot, M. et al. (2015). AICHA: An atlas of intrinsic connectivity of homotopic areas. *J Neuroscience Methods* 254, 46-59.
- Gordon, E.M. et al. (2016). Generation and evaluation of a cortical area parcellation from resting-state correlations. *Cerebral Cortex* 26(1), 288-303. https://doi.org/10.1093/cercor/bhu239
- Glasser, M.F. et al. (2013). The minimal preprocessing pipelines for the Human Connectome Project. *NeuroImage* 80, 105-124.
