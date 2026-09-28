---
layout: wiki
title: Diffusion (DTI) processing
permalink: /wiki/diffusion-processing/
---

TI-Toolbox turns diffusion-weighted imaging (DWI) into the tensor file SimNIBS uses for anisotropic conductivity, `DTI_coregT1_tensor.nii.gz`. [QSIPrep](https://qsiprep.readthedocs.io/) preprocesses the DWI; TI-Toolbox then fits the tensor itself with [DIPY](https://dipy.org/) and maps it into the head model with QSIPrep's own transforms. [QSIRecon](https://qsirecon.readthedocs.io/) is an optional extra for tractography, scalar maps and connectivity; the tensor does not need it.

### Platform

**QSIPrep needs an x86-64 (Intel/AMD) Docker host: Linux, or Windows with Docker Desktop.** It cannot run on Apple Silicon: its SynthSeg step uses TensorFlow built for AVX instructions, which emulation does not provide, and the run stops there. TI-Toolbox refuses to start QSIPrep on an arm64 Docker host and says so. On a Mac, run QSIPrep on an x86-64 machine and copy `derivatives/qsiprep/sub-<id>/` into the project; the DTI step then runs anywhere.

## Pipeline overview

```
Raw BIDS DWI (+ reverse phase-encoding fieldmap, if acquired)
    |
    v
[ QSIPrep ]  -->  preprocessed DWI + gradient table (ACPC space), ACPC <-> T1w transforms
    |
    v
[ DTI step ]  -->  DIPY WLS tensor fit (b <= 1500)
    |             exact ACPC -> T1 transform chain (NCC check)
    |             trilinear resampling + tensor rotation + brain mask
    |             QC gate
    v
DTI_coregT1_tensor.nii.gz + DTI_coregT1_qc.json  -->  SimNIBS anisotropic simulation

[ QSIRecon ]  (optional)  -->  tractography / scalar maps / connectivity
```

### Requirements

- Raw DWI in BIDS format (`.nii.gz` + `.bval` + `.bvec` + `.json` sidecar with `PhaseEncodingDirection`)
- A T1w image, and the SimNIBS head model (`m2m` folder from charm) built from **that same T1w file**
- An x86-64 host for QSIPrep (above)

## Stage 1: QSIPrep

TI-Toolbox runs QSIPrep 26.0.0 with defaults chosen from your data, so most users never open the settings:

| Setting | Default | Why |
|---|---|---|
| Distortion correction | Always on (see below) | Uncorrected EPI distortion misplaces tensors near the frontal and temporal lobes |
| Unringing | `auto`: `rpg` when the DWI sidecar has `PartialFourier` < 1, else `mrdegibbs` | `mrdegibbs` assumes full k-space |
| Denoising | `dwidenoise` | MP-PCA, QSIPrep's recommended default |
| Head motion / eddy | `eddy` (FSL eddy inside QSIPrep) | stated explicitly |
| Reverse-PE method | `TOPUP` | stated explicitly |
| b=0 threshold | 100 s/mm² | stated explicitly |
| Output resolution | the DWI's native voxel size (finest axis, rounded to 0.1 mm) | no invented resolution |
| MNI normalization | off | only QSIRecon atlases need it |

### Distortion correction is mandatory

Before QSIPrep starts, TI-Toolbox looks at the subject's `fmap/` folder:

- A **reverse phase-encoding fieldmap** (`fmap/*_epi` whose `acq` label says `dwi`/`dti`, or with no `acq` label and the DWI's matrix, or whose `IntendedFor` already names the DWI) with a `PhaseEncodingDirection` opposite to the DWI's is used with **TOPUP**. If its sidecar lacks `IntendedFor` or `TotalReadoutTime`, TI-Toolbox writes them into that fieldmap's own JSON (the readout time is derived from `EstimatedTotalReadoutTime` or `EffectiveEchoSpacing × (ReconMatrixPE − 1)`). Nothing else in your BIDS folder is touched, and a value that is already there is never overwritten.
- **DWI series with opposite phase encoding** in `dwi/` are used with TOPUP directly.
- **No fieldmap**: fieldmap-less **SyN** correction (`--use-syn-sdc warn`). SyN places its prior through the anatomical MNI transform, so MNI normalization is switched on for that run.
- **A DWI fieldmap that cannot be used** (no sidecar, no `PhaseEncodingDirection`, the same phase encoding as the DWI, or no readout time) is reported. If it is the only one, the run is refused with the reason instead of silently falling back; fix the sidecar, or move the fieldmap out of `fmap/` to accept SyN. When another usable fieldmap exists, the bad one is only logged.

The chosen mode is written to the preprocessing log (`Distortion correction: ...`).

### Advanced options

**Configure QSIPrep** keeps every option: output resolution (leave empty for native), denoising, unringing, BIDS validation, image tag and MNI normalization. CPU, memory and OpenMP threads live in [Pre-processing settings]({{ site.baseurl }}/wiki/pre-processing/#pre-processing-settings).

### QSIPrep output used by TI-Toolbox

```
derivatives/qsiprep/sub-{id}/
├── anat/
│   ├── sub-{id}_from-ACPC_to-anat_mode-image_xfm.mat
│   ├── sub-{id}_space-ACPC_desc-preproc_T1w.nii.gz
│   └── sub-{id}_space-ACPC_desc-brain_mask.nii.gz
└── dwi/
    ├── sub-{id}_space-ACPC_desc-preproc_dwi.nii.gz
    ├── sub-{id}_space-ACPC_desc-preproc_dwi.b          # gradient table, scanner RAS
    └── sub-{id}_space-ACPC_desc-brain_mask.nii.gz
```

## Stage 2: the DTI step

1. **Fit.** DIPY `TensorModel`, weighted least squares, on the shells with b ≤ 1500 s/mm² (the diffusion tensor model holds there; higher shells bias it). QSIPrep's `.b` table is in scanner coordinates, so the fitted tensors are already in world orientation. At least six diffusion-weighted volumes are required.
2. **Transform chain.** The ACPC → T1 map is composed exactly from QSIPrep's files: its reorientation of the T1w to LPS and removal of any oblique rotation (a step no transform file records), then the inverse of `from-ACPC_to-anat`. A rigid NCC registration of QSIPrep's ACPC T1 to the m2m T1 is run only as a check.
3. **Resampling.** Tensor components are interpolated trilinearly onto the m2m `T1.nii.gz` grid, normalised by the interpolated brain mask so edge voxels are not dragged towards zero, and every tensor is rotated with the transform. Voxels outside white matter, grey matter and CSF (charm labels 1–3, with white and grey matter dilated by two voxels) are zeroed.
4. **SimNIBS frame.** SimNIBS rotates stored tensors by $$M = A_{3\times3} / \lVert \text{columns} \rVert$$ (x flipped when $$\det M > 0$$) when it reads them. The file stores $$M^{-1} T_{\text{world}} M^{-\mathsf{T}}$$, so SimNIBS reads back exactly $$T_{\text{world}}$$.

### QC gate

The tensor is written only if every check passes; otherwise the step fails with the reasons and `DTI_coregT1_qc.json` records the numbers.

| Check | Threshold |
|---|---|
| NCC of QSIPrep's ACPC T1 against the m2m T1 under the chain | ≥ 0.90 |
| Mean brain displacement, chain vs NCC refinement | ≤ 1 mm |
| Positive-definite tensors | ≥ 99 % |
| White + grey matter voxels without a tensor | ≤ 5 % |
| Tensors outside the brain | 0 |
| White-matter median mean diffusivity | 0.5–1.1 × 10⁻³ mm²/s |

The step also refuses to run when the m2m `T1.nii.gz` is not on the grid of the raw T1w QSIPrep used (charm must have run on the same file), because the transform chain would not apply.

### Output

```
derivatives/SimNIBS/sub-{id}/m2m_{id}/
├── DTI_coregT1_tensor.nii.gz   # SimNIBS T1 grid, 4D (X, Y, Z, 6), mm²/s
└── DTI_coregT1_qc.json         # QC gate record
```

A QC report is written alongside: FA on the T1, principal direction coloured on **world** axes (red = left-right, green = anterior-posterior, blue = superior-inferior), tensor statistics and the QC gate table.

## Stage 3 (optional): QSIRecon

QSIRecon offers [over 20 reconstruction workflows](https://qsirecon.readthedocs.io/): MRtrix CSD tractography, DIPY DKI, NODDI, MAP-MRI, TORTOISE, DSI Studio and more. Select it only if you want those outputs. The preselected `dsi_studio_gqi` runs a trimmed spec (`resources/qsirecon_pipelines/dsi_studio_gqi_scalar.yaml`: GQI scalar maps, no tractography, no connectivity node, which also avoids QSIRecon's mandatory `--atlases` and a reporting bug in QSIRecon ≥ 1.2.0). Choosing connectivity atlases uses the upstream spec and requires a QSIPrep run with **MNI normalization** enabled.

## Usage

```python
from tit import get_path_manager
from tit.pre import run_pipeline

get_path_manager("/mnt/my_project")  # your project path inside the container
run_pipeline(
    subject_ids=["001"],
    create_m2m=True,     # or an existing m2m built from the same T1w
    run_qsiprep=True,    # x86-64 host only
    extract_dti=True,
)
```

Then select an anisotropic conductivity model (`vn`, `dir` or `mc`) in the **Simulator**; it uses `DTI_coregT1_tensor.nii.gz`.

Results from TI-Toolbox before this change came from a translation-only alignment without tensor rotation and should be regenerated; see the [changelog]({{ site.baseurl }}/releases/changelog/).

## Docker and resources

QSIPrep and QSIRecon run as sibling Docker containers spawned from the TI-Toolbox container (Docker-out-of-Docker). Expect QSIPrep to take one to several hours per subject on native x86-64 cores and to need 16 GB+ of RAM. The DTI step runs inside the TI-Toolbox container in a few minutes.

## References

- [QSIPrep documentation](https://qsiprep.readthedocs.io/)
- [QSIRecon documentation](https://qsirecon.readthedocs.io/)
- [DIPY](https://dipy.org/) — tensor fitting
- [SimNIBS dwi2cond](https://simnibs.github.io/simnibs/build/html/documentation/command_line/dwi2cond.html) — SimNIBS's own FSL-based workflow
- Cieslak et al. _QSIPrep: an integrative platform for preprocessing and reconstructing diffusion MRI data._ Nature Methods 18, 775–778 (2021). [doi:10.1038/s41592-021-01185-5](https://doi.org/10.1038/s41592-021-01185-5)
- Garyfallidis et al. _Dipy, a library for the analysis of diffusion MRI data._ Frontiers in Neuroinformatics 8, 8 (2014). [doi:10.3389/fninf.2014.00008](https://doi.org/10.3389/fninf.2014.00008)

## Related

- [Pre-Processing]({{ site.baseurl }}/wiki/pre-processing/)
- [Simulator]({{ site.baseurl }}/wiki/simulator/) — anisotropic conductivity
