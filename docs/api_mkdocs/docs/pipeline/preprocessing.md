# Preprocessing

The preprocessing pipeline converts raw imaging data into simulation-ready head meshes. This is a **one-time setup** per subject — once complete, you can run unlimited simulations without repeating these steps.

```mermaid
graph LR
    A[DICOM] -->|dcm2niix| B[NIfTI]
    B -->|recon-all| C[FreeSurfer Surfaces]
    C -->|CHARM| D[Head Mesh]
    D -->|tissue analysis| E[Tissue Report]
    style D fill:#2d5a27,stroke:#4a8,color:#fff
```

## Full Pipeline

Run all preprocessing steps with a single call:

```python
from tit.pre import run_pipeline

exit_code = run_pipeline(
    project_dir="/data/my_project",
    subject_ids=["001", "002"],
    convert_dicom=True,
    run_recon=True,
    parallel_recon=True,
    parallel_cores=4,
    create_m2m=True,
    run_tissue_analysis=True,
)
```

!!! tip "Selective Steps"
    Each boolean flag controls a specific step. Set only the ones you need — for example, if FreeSurfer `recon-all` is already done, set `run_recon=False` and `create_m2m=True` to run only CHARM.

## Individual Steps

Each preprocessing step can be called independently for finer control:

```python
from tit.pre import (
    run_dicom_to_nifti,
    run_recon_all,
    run_charm,
    run_tissue_analysis,
    run_subcortical_segmentations,
    discover_subjects,
    check_m2m_exists,
)

# Discover subjects from sourcedata/
subjects = discover_subjects("/data/my_project")

# Check if head mesh already exists
if not check_m2m_exists("/data/my_project", "001"):
    run_charm("/data/my_project", "001", logger=my_logger)
```

### Step Details

| Step | Function | What It Does |
|------|----------|--------------|
| DICOM to NIfTI | `run_dicom_to_nifti()` | Converts DICOM files to NIfTI format using `dcm2niix` |
| FreeSurfer recon-all | `run_recon_all()` | Full cortical reconstruction (takes 6-12 hours per subject) |
| CHARM head mesh | `run_charm()` | Creates SimNIBS-compatible head mesh from FreeSurfer output |
| Tissue analysis | `run_tissue_analysis()` | Generates tissue composition report from the head mesh |
| Subcortical segmentation | `run_subcortical_segmentations()` | Extracts subcortical structures for ROI analysis |

!!! warning "Compute Time"
    FreeSurfer `recon-all` is the most time-consuming step (6-12 hours per subject). Use `parallel_recon=True` with `parallel_cores` to process multiple subjects simultaneously.

## DTI / Diffusion Pipeline

For anisotropic conductivity simulations, TI-Toolbox also supports diffusion processing:

```python
from tit.pre import run_qsiprep, run_qsirecon, extract_dti_tensor

# Run QSIPrep and QSIRecon for diffusion data
run_qsiprep("/data/my_project", "001")
run_qsirecon("/data/my_project", "001")

# Extract tensor for SimNIBS
extract_dti_tensor("/data/my_project", "001")
```

## BIDS Directory Structure

After preprocessing, your project follows this layout:

```
project_root/
├── sourcedata/              # Raw DICOM
├── sub-001/
│   └── anat/               # NIfTI files (T1w, T2w)
└── derivatives/
    ├── SimNIBS/sub-001/
    │   └── m2m_001/         # Head mesh (simulation-ready)
    └── freesurfer/sub-001/  # recon-all outputs
```

## API Reference

::: tit.pre.structural.run_pipeline
    options:
      show_root_heading: true
      members_order: source

::: tit.pre.utils.discover_subjects
    options:
      show_root_heading: true

::: tit.pre.utils.check_m2m_exists
    options:
      show_root_heading: true

::: tit.pre.dicom2nifti.run_dicom_to_nifti
    options:
      show_root_heading: true

::: tit.pre.recon_all.run_recon_all
    options:
      show_root_heading: true

::: tit.pre.charm.run_charm
    options:
      show_root_heading: true

::: tit.pre.tissue_analyzer.run_tissue_analysis
    options:
      show_root_heading: true
