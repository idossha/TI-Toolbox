---
layout: wiki
title: Diffusion Processing
permalink: /wiki/diffusion-processing/
---

The TI-Toolbox integrates with [QSIPrep](https://qsiprep.readthedocs.io/) and [QSIRecon](https://qsirecon.readthedocs.io/) to process diffusion-weighted imaging (DWI) data for anisotropic conductivity simulations. The pipeline preprocesses raw DWI, reconstructs diffusion tensors, registers them into SimNIBS head-model space, and pre-compensates for SimNIBS's internal FSL tensor rotation — producing a ready-to-use `DTI_coregT1_tensor.nii.gz`.

!!! warning "Validation Status"
    This pipeline is **functional and producing stable, consistent results** in our testing. However, the full chain — from QSIRecon tensor output through cross-correlation registration and FSL convention pre-compensation — **warrants further validation** by domain experts in diffusion MRI and conductivity modeling. We welcome input from the community on registration accuracy, tensor reorientation correctness, and downstream simulation fidelity. If you have expertise in this area, please open an issue or reach out.

!!! warning "Apple Silicon (ARM) Compatibility"
    QSIPrep and QSIRecon Docker containers are built for `linux/amd64`. On Apple Silicon Macs (M1/M2/M3/M4), Docker runs these under Rosetta 2 emulation (`--platform linux/amd64`). This works but has known issues: significantly slower performance, occasional segfaults during eddy current correction, and higher memory usage. If you encounter failures on Apple Silicon, try increasing Docker's memory allocation (32 GB+ recommended) or running on an Intel/AMD machine.

## Pipeline Overview

Anisotropic conductivity modeling uses DTI to account for the direction-dependent electrical conductivity of brain tissue — white matter conducts current preferentially along fiber tracts.

```
Raw BIDS DWI
    |
    v
[ QSIPrep ]  -->  preprocessed DWI (ACPC space, 2 mm)
    |
    v
[ QSIRecon: dsi_studio_gqi ]  -->  6 tensor component maps (txx–tzz)
    |
    v
[ DTI Extractor ]  -->  cross-correlation alignment + resampling
    |                    + FSL convention pre-compensation
    v
DTI_coregT1_tensor.nii.gz  -->  SimNIBS anisotropic simulation
```

### Requirements

- Raw DWI data in BIDS format (`.nii.gz` + `.bval` + `.bvec`)
- SimNIBS head model (`m2m` directory from CHARM)
- FreeSurfer license file
- Docker

## Stage 1: QSIPrep — DWI Preprocessing

QSIPrep takes raw diffusion-weighted images and produces analysis-ready data:

- **Denoising** — MP-PCA denoising and Gibbs ringing removal
- **Motion and eddy current correction** — head motion and eddy distortion estimation/correction
- **Susceptibility distortion correction** — EPI distortion correction using fieldmaps or synthetic methods
- **Coregistration** — alignment to the subject's T1-weighted anatomical
- **Resampling** — to a standard output resolution (default: 2 mm isotropic, ACPC space)

See [QSIPrep documentation](https://qsiprep.readthedocs.io/) for full preprocessing details.

### QSIPrep Output

```
derivatives/qsiprep/sub-{id}/
├── anat/sub-{id}_space-ACPC_desc-preproc_T1w.nii.gz
└── dwi/
    ├── sub-{id}_space-ACPC_desc-preproc_dwi.nii.gz
    ├── sub-{id}_space-ACPC_desc-preproc_dwi.bval
    └── sub-{id}_space-ACPC_desc-preproc_dwi.bvec
```

## Stage 2: QSIRecon — Tensor Reconstruction

QSIRecon supports [over 20 reconstruction workflows](https://qsirecon.readthedocs.io/) — MRtrix CSD, DIPY DKI, NODDI, MAP-MRI, TORTOISE, DSI Studio, and more. We ship **`dsi_studio_gqi`** as the default for SimNIBS because:

- It directly produces the six tensor component maps (`txx`–`tzz`) that SimNIBS needs
- It works with both single-shell and multi-shell acquisitions
- It does not require FreeSurfer surfaces or atlas parcellations
- It has proven reliable across our test datasets

We use a custom pipeline YAML (`resources/qsirecon_pipelines/dsi_studio_gqi_scalar.yaml`) that removes the upstream connectivity node — this avoids a mandatory `--atlases` requirement and a reporting bug in QSIRecon >= 1.2.0, while retaining GQI reconstruction and scalar export.

Other recon specs may also produce usable tensors, but they are not currently validated in our extraction pipeline. See the [QSIRecon documentation](https://qsirecon.readthedocs.io/) for the full list of available reconstruction workflows.

### QSIRecon Output

Six tensor component NIfTIs representing the symmetric diffusion tensor:

```
derivatives/qsirecon/derivatives/qsirecon-DSIStudio/sub-{id}/dwi/
    sub-{id}_space-ACPC_model-tensor_param-{txx,txy,txz,tyy,tyz,tzz}_dwimap.nii.gz
```

```
    | Dxx  Dxy  Dxz |
D = | Dxy  Dyy  Dyz |
    | Dxz  Dyz  Dzz |
```

## Stage 3: DTI Extraction — Registration to SimNIBS

The DTI extractor bridges QSIRecon output and SimNIBS expectations:

1. **Load** — combines 6 tensor component NIfTIs into a single `(X, Y, Z, 6)` array
2. **Align** — 3D cross-correlation between the QSIPrep T1 and SimNIBS T1 to find the translation offset (~50 mm between ACPC and SimNIBS coordinates). Pure Python — no FSL or ANTs required
3. **Resample** — each component onto the SimNIBS T1 grid (0.5 mm isotropic, trilinear interpolation)
4. **Pre-compensate** — rotates tensors so SimNIBS's internal `correct_FSL` produces correct world-space conductivity tensors. DSI Studio does not apply the implicit x-flip that FSL `dtifit` does, so we store `R_fix·T·R_fix^T` such that SimNIBS's `M·stored·M^T` yields the correct result

### Final Output

```
derivatives/SimNIBS/sub-{id}/m2m_{id}/
├── DTI_ACPC_tensor.nii.gz      # Intermediate (ACPC space)
└── DTI_coregT1_tensor.nii.gz   # Final (SimNIBS T1 space, 4D: X,Y,Z,6)
```

### QC Report

An automated QC report is generated after extraction:

- **FA overlaid on T1** — checks registration quality (WM FA should align with T1 anatomy)
- **Color-coded FA** — verifies tensor orientations (red=LR, green=AP, blue=SI)
- **Tensor statistics** — FA mean/median/max, eigenvalue ranges

For deeper investigation, a diagnostic tool is available inside the SimNIBS container:

```bash
python -m tit.pre.qsi.debug_dti /mnt/<project> <subject_id>
```

## Usage

### Full Pipeline

```python
from tit.pre import run_pipeline

run_pipeline(
    subject_ids=["001"],
    run_qsiprep=True,
    run_qsirecon=True,
    extract_dti=True,
)
```

### Individual Steps

```python
from tit.pre import run_qsiprep, run_qsirecon, extract_dti_tensor
import logging

logger = logging.getLogger("diffusion")
project = "/path/to/bids_project"

run_qsiprep(project, "001", logger=logger)
run_qsirecon(project, "001", logger=logger)
tensor_path = extract_dti_tensor(project, "001", logger=logger)
```

### Configuration Defaults

| Parameter | Default | Notes |
|-----------|---------|-------|
| Recon spec | `dsi_studio_gqi` | Recommended for SimNIBS |
| Output resolution | 2 mm isotropic | QSIPrep output |
| Denoise method | `dwidenoise` (MP-PCA) | `patch2self`, `none` also available |
| Unringing method | `mrdegibbs` | `rpg`, `none` also available |
| Atlases | None | Not needed for DTI; optional for connectivity |

## Integration with Simulations

Once extracted, the tensor is automatically available for anisotropic simulations:

1. Navigate to the **Simulator** tab
2. Select your subject
3. Under **Conductivity Model**, select **Anisotropic**
4. The simulator will detect and use `DTI_coregT1_tensor.nii.gz`

## Docker & Resources

QSIPrep and QSIRecon run as **sibling Docker containers** spawned from the SimNIBS container via Docker-out-of-Docker (DooD). CPU and memory limits are inherited from the parent container.

| Image | Version |
|-------|---------|
| `pennlinc/qsiprep` | 1.1.1 |
| `pennlinc/qsirecon` | 1.2.0 |

Resource requirements are highly variable depending on acquisition and hardware:

- **Memory**: 16 GB minimum, 32 GB recommended
- **CPU**: Scales well with 4–8 cores
- **Disk**: QSIPrep work directories can require 10–20 GB per subject
- **Time**: QSIPrep 2–6 hours/subject; QSIRecon 30–90 minutes

## References

- [QSIPrep documentation](https://qsiprep.readthedocs.io/) — full preprocessing reference
- [QSIRecon documentation](https://qsirecon.readthedocs.io/) — all 21+ recon specs, 14 atlases, CLI reference
- [SimNIBS dwi2cond](https://simnibs.github.io/simnibs/build/html/documentation/command_line/dwi2cond.html) — SimNIBS native DTI workflow
- [DSI Studio](https://dsi-studio.labsolver.org/) — GQI reconstruction engine
- Cieslak et al. *QSIPrep: an integrative platform for preprocessing and reconstructing diffusion MRI data.* Nature Methods 18, 775–778 (2021). [doi:10.1038/s41592-021-01185-5](https://doi.org/10.1038/s41592-021-01185-5)
- For developers: [`docs/dev/qsirecon-internal-reference.md`](../dev/qsirecon-internal-reference.md) — complete internal reference (recon specs, atlases, version history, BIDS details)

## Related

- [Pre-Processing](pre-processing.md) — Structural MRI preprocessing
- [Simulator](simulator.md) — Running TI simulations with anisotropic conductivity
