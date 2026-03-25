---
layout: wiki
title: QSIPrep & QSIRecon Reference
permalink: /wiki/qsiprep-reference/
---

# QSIPrep & QSIRecon: Diffusion-to-SimNIBS Pipeline

QSIPrep preprocesses raw diffusion MRI data (denoising, motion correction,
distortion correction). QSIRecon then reconstructs the preprocessed data to
produce diffusion tensor maps. The TI-Toolbox DTI extractor converts these
tensors into the format SimNIBS needs for anisotropic conductivity modeling.

**Citation:** Cieslak, M., Cook, P.A., He, X. et al. QSIPrep: an integrative
platform for preprocessing and reconstructing diffusion MRI data. *Nature
Methods* 18, 775-778 (2021). https://doi.org/10.1038/s41592-021-01185-5

---

## Requirements

- Raw DWI data organized in BIDS format
- FreeSurfer license file (`license.txt`)
- Docker

## Pipeline Overview

```
Raw BIDS DWI
    |
    v
[ QSIPrep ]  -->  preprocessed DWI
    |
    v
[ QSIRecon: dsi_studio_gqi ]  -->  tensor component maps
    |
    v
[ DTI Extractor ]  -->  SimNIBS-compatible DTI tensor
```

## What QSIPrep Does

QSIPrep takes raw diffusion-weighted images and produces analysis-ready data:

- **Denoising** -- MP-PCA denoising and Gibbs ringing removal
- **Motion and eddy current correction** -- head motion and eddy current distortion estimation and correction
- **Susceptibility distortion correction** -- EPI distortion correction using fieldmaps or synthetic methods
- **Coregistration** -- alignment of DWI volumes to the subject's T1-weighted anatomical image
- **Resampling** -- resampling to a standard output resolution (default: 2 mm isotropic)

## What QSIRecon Does

QSIRecon runs reconstruction workflows on the preprocessed QSIPrep output.
For the SimNIBS anisotropic simulation pipeline, the relevant workflow is
**`dsi_studio_gqi`**, which produces the six independent tensor component
files needed by SimNIBS:

- `txx`, `txy`, `txz`, `tyy`, `tyz`, `tzz`

Connectivity atlases (e.g., `4S156Parcels`, `AAL116`) can optionally be
requested for parcellation and connectome analysis, but they are **not
required** for the DTI-to-SimNIBS workflow.

## Docker Images

| Image | Version | Purpose |
|-------|---------|---------|
| `pennlinc/qsiprep` | 1.2.0 | Preprocessing |
| `pennlinc/qsirecon` | 1.2.0 | Reconstruction |

## Configuration Defaults

| Parameter | Default |
|-----------|---------|
| Recon spec | `dsi_studio_gqi` |
| Atlases (optional) | None (not needed for DTI) |
| Output resolution | 2 mm isotropic |

## Output Locations

**QSIRecon output:**

```
derivatives/qsirecon/sub-{id}/
```

**Final SimNIBS-ready DTI tensor:**

```
derivatives/SimNIBS/sub-{id}/m2m_{id}/DTI_coregT1_tensor.nii.gz
```

## For Developers

The full internal reference -- covering all 21 recon specs, 14 atlases,
complete CLI argument tables, version history, eddy configuration, and
BIDS compliance details -- is maintained at:

[`docs/dev/qsirecon-internal-reference.md`](../dev/qsirecon-internal-reference.md)
