---
title: DWI/DTI Pipeline
---

# DWI/DTI Pipeline (QSIPrep/QSIRECON)

This pipeline integrates QSIPrep and QSIRECON into TI-Toolbox preprocessing so
you can run diffusion preprocessing/reconstruction while staying inside the
`simnibs_container`.

## Requirements (Best Practice)

- **Valid BIDS structure** at the project root
- DWI files with matching `.bval` and `.bvec`
- JSON sidecars with acquisition metadata (e.g., `PhaseEncodingDirection`, `TotalReadoutTime`)
- QSIPrep container enabled in `loader.sh`

## BIDS Naming (Required)

QSIPrep runs the BIDS validator before it starts. All files in the project
root must be BIDS-compatible (not just DWI). Typical pitfalls:

- DWI files must start with `sub-<id>` and end with `_dwi`
- Anat files must be named `sub-<id>_T1w` / `sub-<id>_T2w`
- If you include `ses-<label>` in a filename, the file must live under
  `sub-<id>/ses-<label>/...`

If you have non-BIDS files, move them to `sourcedata/` or `derivatives/`,
or add a `.bidsignore` file to exclude them.

## Example BIDS Layout (Single Session)

```
project/
├── sub-001/
│   └── dwi/
│       ├── sub-001_dwi.nii.gz
│       ├── sub-001_dwi.bval
│       └── sub-001_dwi.bvec
│       └── sub-001_dwi.json
│   └── anat/
│       ├── sub-001_T1w.nii.gz
│       ├── sub-001_T1w.json
│       ├── sub-001_T2w.nii.gz
│       └── sub-001_T2w.json
└── derivatives/
    ├── qsiprep/
    └── qsirecon/
```

## Example BIDS Layout (Sessioned)

```
project/
├── sub-001/
│   └── ses-base/
│       ├── dwi/
│       │   ├── sub-001_ses-base_dir-LR_dwi.nii.gz
│       │   ├── sub-001_ses-base_dir-LR_dwi.bval
│       │   ├── sub-001_ses-base_dir-LR_dwi.bvec
│       │   └── sub-001_ses-base_dir-LR_dwi.json
│       └── anat/
│           ├── sub-001_ses-base_T1w.nii.gz
│           └── sub-001_ses-base_T1w.json
└── derivatives/
    ├── qsiprep/
    └── qsirecon/
```

## Run from GUI

- Pre-processing tab → enable:
  - **Run QSIPrep (DWI preprocessing)**
  - **Run QSIRECON (DTI reconstruction)** (optional)

## Run from CLI

```bash
./loader.sh
simnibs_python -m tit.cli.pre_process --subjects 001 --run-qsiprep
```

### With QSIRECON

```bash
simnibs_python -m tit.cli.pre_process --subjects 001 --run-qsiprep --run-qsirecon
```

## Notes

- Outputs are written to `derivatives/qsiprep/` and `derivatives/qsirecon/`
- The pipeline validates that each subject has a DWI series with matching `.bval`/`.bvec`
- Single-shell, multi-shell, and multiple acquisitions are supported as long as BIDS metadata is correct
- Default QSIPrep `--output-resolution` is set to `2.0` mm for reasonable runtime/memory usage
- TI-Toolbox preprocessing currently assumes **single-session** data. If you
  have sessioned data, run QSIPrep directly in the QSIPrep container and use
  `--session-id` (see below).

## Using the QSIPrep container

If you enable the optional QSIPrep service in `loader.sh`, you can run QSIPrep
directly from the container:

```bash
docker exec -ti qsiprep_container \
  qsiprep /data /out/derivatives/qsiprep participant \
  --participant-label 001 \
  --session-id base \
  --fs-license-file /opt/freesurfer/license.txt
```

When enabled, QSIPrep runs inside its own container and writes outputs to the
shared project directory under `derivatives/qsiprep/`.

For convenience, the loader also exposes `qsiprep` and `qsirecon` inside
`simnibs_container` as proxy commands that forward to the QSIPrep container:

```bash
qsiprep --version
qsirecon --version
```

## References

- QSIPrep installation and usage docs: https://qsiprep.readthedocs.io/en/latest/installation.html
- Cieslak et al., 2021, *QSIPrep: An integrative platform for preprocessing and reconstructing diffusion MRI data* (Nature Methods). https://pmc.ncbi.nlm.nih.gov/articles/PMC8596781/
