# QSI Integration — Internal Development Reference

> Last updated: 2026-03-26
> Covers: QSIPrep 1.1.1, QSIRecon 1.2.0

This document is the authoritative reference for agents working on the
QSIPrep/QSIRecon Docker-out-of-Docker (DooD) integration in TI-Toolbox.

---

## Status & Known Issues

**Pipeline status**: Functional and producing stable, consistent results.
The full chain (QSIRecon → cross-correlation registration → FSL convention
pre-compensation → SimNIBS tensor) warrants further validation by domain
experts in diffusion MRI and conductivity modeling. Community input is
welcome on registration accuracy, tensor reorientation correctness, and
downstream simulation fidelity.

**Apple Silicon (ARM)**: QSIPrep and QSIRecon images are `linux/amd64` only.
On Apple Silicon Macs, Docker runs them under Rosetta 2 emulation via
`--platform linux/amd64`. Known issues:
- Significantly slower performance (2–5x)
- Occasional segfaults during eddy current correction
- Higher memory usage — allocate 32 GB+ in Docker Desktop
- Some users report hangs during the SynthSeg step

**Custom pipeline YAML**: We ship `resources/qsirecon_pipelines/dsi_studio_gqi_scalar.yaml`
which removes the connectivity node from the upstream `dsi_studio_gqi` spec.
This avoids both a mandatory `--atlases` requirement and a `plot_reports` bug
in QSIRecon >= 1.2.0. The custom spec retains GQI reconstruction, scalar
export (tensor component maps), and optional tractography.

**Default recon spec choice**: QSIRecon supports 21+ reconstruction workflows.
We default to `dsi_studio_gqi` because it directly produces the 6 tensor
component NIfTIs SimNIBS needs, works with single- and multi-shell data, and
does not require FreeSurfer surfaces or atlases. Other specs may produce
usable tensors but are not validated in the extraction pipeline.

---

## Architecture

TI-Toolbox runs inside the **SimNIBS container**. QSIPrep and QSIRecon run as
**sibling Docker containers** spawned via the Docker socket (DooD pattern).

```
Host (macOS/Linux)
  └─ Docker
      ├─ SimNIBS container (ti-toolbox code lives here)
      │   ├─ /mnt/<project>  ──bind-mount──>  host project dir
      │   ├─ /var/run/docker.sock  ──bind-mount──>  host Docker socket
      │   └─ LOCAL_PROJECT_DIR env var = host path to project
      │
      ├─ QSIPrep container (spawned by SimNIBS via `docker run`)
      │   ├─ /data  ──bind-mount──>  host project dir (ro)
      │   ├─ /out   ──bind-mount──>  host derivatives/qsiprep
      │   └─ /work  ──bind-mount──>  host derivatives/.qsiprep_work
      │
      └─ QSIRecon container (spawned by SimNIBS via `docker run`)
          ├─ /data  ──bind-mount──>  host derivatives/qsiprep (ro)
          ├─ /out   ──bind-mount──>  host derivatives/qsirecon
          └─ /work  ──bind-mount──>  host derivatives/.qsirecon_work
```

**Critical constraint**: Volume mount source paths must be **host paths**
(not SimNIBS container paths). The `LOCAL_PROJECT_DIR` env var provides this.

---

## FreeSurfer License (DooD)

The FS license lives at `/usr/local/freesurfer/license.txt` inside the
SimNIBS container. Sibling containers cannot access this path directly.

**Solution**: Stage the license into the project directory (shared filesystem),
then mount the host-mapped copy and set `FS_LICENSE` env var in the sibling:

```
1. Copy /usr/local/freesurfer/license.txt → {project_dir}/.freesurfer_license.txt
2. Mount -v {host_project_dir}/.freesurfer_license.txt:/opt/freesurfer/license.txt:ro
3. Pass -e FS_LICENSE=/opt/freesurfer/license.txt
4. Pass --fs-license-file /opt/freesurfer/license.txt
```

The `FS_LICENSE` env var is **required** — QSIRecon validates it independently
of `--fs-license-file` during workflow initialization.

---

## Docker Images

| Image | Latest Tag | Notes |
|-------|-----------|-------|
| `pennlinc/qsiprep` | `1.1.1` | **No 1.2.0 release exists** |
| `pennlinc/qsirecon` | `1.2.0` | Feb 2026 |

Use separate image tag constants. Never share a single tag for both.

---

## QSIRecon CLI Arguments

All three are aliases: `--nprocs` / `--nthreads` / `--n-cpus`
All two are aliases: `--mem` / `--mem-mb` (value in MB by default)

| Argument | Type | Notes |
|----------|------|-------|
| `input_dir` | positional | QSIPrep output dir (contains `sub-*`) |
| `output_dir` | positional | Reconstruction output |
| `{participant}` | positional | Always "participant" |
| `--participant-label` | str+ | Subject IDs |
| `--recon-spec` | str | Built-in name or YAML file path |
| `--atlases` | str+ | **Single flag, space-separated values** |
| `--fs-license-file` | path | FreeSurfer license file |
| `--fs-subjects-dir` | path | Required for ACT-hsvs specs |
| `--input-type` | choice | `qsiprep` (default), `ukb`, `hcpya` |
| `--skip-odf-reports` | flag | Skip ODF visualizations |
| `-w, --work-dir` | path | Working directory |
| `--nprocs` | int | CPU threads |
| `--omp-nthreads` | int | Per-process threads |
| `--mem` | str | Memory (bare number = MB; supports G/T/M suffixes) |
| `--denoise-method` | choice | QSIPrep only: `dwidenoise`, `patch2self`, `none` |
| `--unringing-method` | choice | QSIPrep only: `mrdegibbs`, `rpg`, `none` |

---

## Available Atlases (QSIRecon 1.0.0+)

The atlas system was **completely reorganized in 1.0.0**. Legacy names from
pre-1.0 QSIPrep (`Schaefer100`, `Schaefer200`, `Schaefer400`, `power264Ext`,
`MICCAI2012`) are **no longer valid**.

### Valid Atlas Names

| Name | Description | Parcels |
|------|-------------|---------|
| `4S156Parcels` | Schaefer 100 cortical + 56 subcortical | 156 |
| `4S256Parcels` | Schaefer 200 + 56 subcortical | 256 |
| `4S356Parcels` | Schaefer 300 + 56 subcortical | 356 |
| `4S456Parcels` | Schaefer 400 + 56 subcortical | 456 |
| `4S556Parcels` | Schaefer 500 + 56 subcortical | 556 |
| `4S656Parcels` | Schaefer 600 + 56 subcortical | 656 |
| `4S756Parcels` | Schaefer 700 + 56 subcortical | 756 |
| `4S856Parcels` | Schaefer 800 + 56 subcortical | 856 |
| `4S956Parcels` | Schaefer 900 + 56 subcortical | 956 |
| `4S1056Parcels` | Schaefer 1000 + 56 subcortical | 1056 |
| `AAL116` | Tzourio-Mazoyer et al. | 116 |
| `Brainnetome246Ext` | Fan et al. + subcortical | 246 |
| `AICHA384Ext` | Joliot et al. + subcortical | 384 |
| `Gordon333Ext` | Gordon et al. + subcortical | 333 |

### Legacy → New Mapping

| Old (INVALID) | Replacement |
|---------------|-------------|
| `Schaefer100` | `4S156Parcels` |
| `Schaefer200` | `4S256Parcels` |
| `Schaefer400` | `4S456Parcels` |
| `power264Ext` | No equivalent |
| `MICCAI2012` | No equivalent |

### How Atlas Resolution Works

QSIRecon resolves atlases via PyBIDS with this query:
```python
{'space': 'MNI152NLin2009cAsym', 'suffix': 'dseg', 'extension': ['.nii.gz', '.nii']}
```

Built-in atlases are stored in the Docker image at paths set by
`QSIRECON_ATLAS` and `QSIRECON_ATLASPACK` env vars. Custom atlases
can be provided via `--datasets PACKAGE=PATH` pointing to BIDS-Atlas dirs.

---

## Available Recon Specs (QSIRecon 1.2.0)

| Spec | Shell Req | Needs Atlases | Needs FS | Notes |
|------|-----------|---------------|----------|-------|
| `mrtrix_multishell_msmt_ACT-hsvs` | Multi | Yes | Yes | Recommended MRtrix |
| `mrtrix_multishell_msmt_ACT-fast` | Multi | Yes | No | Uses FSL FAST |
| `mrtrix_multishell_msmt_noACT` | Multi | Yes | No | No anatomical constraints |
| `mrtrix_singleshell_ss3t_ACT-hsvs` | Single | Yes | Yes | |
| `mrtrix_singleshell_ss3t_ACT-fast` | Single | Yes | No | |
| `mrtrix_singleshell_ss3t_noACT` | Single | Yes | No | |
| `dsi_studio_gqi` | Any | Yes | No | GQI + deterministic |
| `dsi_studio_autotrack` | Any | Yes | No | QSDR + 56 WM tracts |
| `dipy_dki` | Multi | Yes | No | Diffusion kurtosis |
| `dipy_mapmri` | Multi/Cart | Yes | No | MAP-MRI |
| `dipy_3dshore` | Multi/Cart | Yes | No | 3dSHORE basis |
| `amico_noddi` | Multi | Yes | No | NODDI model |
| `pyafq_tractometry` | Any | No | No | AFQ bundles |
| `mrtrix_multishell_msmt_pyafq_tractometry` | Multi | No | No | MRtrix + AFQ |
| `ss3t_fod_autotrack` | Any | Yes | No | ss3t + autotrack |
| `multishell_scalarfest` | Multi | Yes | No | All scalar methods |
| `hbcd_scalar_maps` | Multi | Yes | No | DKI+MAPMRI+tensor+GQI |
| `TORTOISE` | Multi | Yes | No | Tensor + MAPMRI |
| `reorient_fslstd` | Any | No | No | Reorient only |
| `csdsi_3dshore` | Cart (DSI) | Yes | No | EXPERIMENTAL |
| `abcd_recon` | Multi | Yes | No | New in 1.2.0 |

---

## QSIPrep → QSIRecon Pipeline

### QSIPrep Output Structure (input to QSIRecon)

```
derivatives/qsiprep/
  dataset_description.json        # REQUIRED by QSIRecon
  sub-<ID>/
    anat/
      sub-<ID>_space-ACPC_desc-preproc_T1w.nii.gz
      sub-<ID>_space-ACPC_desc-brain_mask.nii.gz
      sub-<ID>_space-ACPC_desc-aseg_dseg.nii.gz
      sub-<ID>_space-ACPC_dseg.nii.gz
      sub-<ID>_from-ACPC_to-MNI152NLin2009cAsym_mode-image_xfm.h5
      sub-<ID>_from-MNI152NLin2009cAsym_to-ACPC_mode-image_xfm.h5
    dwi/
      sub-<ID>_space-ACPC_desc-preproc_dwi.nii.gz
      sub-<ID>_space-ACPC_desc-preproc_dwi.bval
      sub-<ID>_space-ACPC_desc-preproc_dwi.bvec
```

### QSIRecon Output Structure

```
derivatives/qsirecon/
  dataset_description.json
  sub-<ID>.html                              # Report
  sub-<ID>/
    dwi/
      *_seg-<atlas>_dseg.nii.gz              # Atlas in DWI space
      *_seg-<atlas>_stat-<measure>_connectivity.tsv
  derivatives/
    qsirecon-<METHOD>/                       # Per-method
      sub-<ID>/dwi/
        *_model-<model>_param-<param>_dwimap.nii.gz
```

---

## Breaking Changes Timeline

### QSIRecon 1.0.0 (2025-03-11) — MAJOR
- Split from QSIPrep into standalone tool
- **Atlas names reorganized** — legacy Schaefer/power/MICCAI removed
- 4S atlas series introduced (AtlasPack)
- `--recon-input-pipeline` → `--input-type`
- `--freesurfer-input` → `--fs-subjects-dir`
- Pipeline configs: JSON → YAML
- Output restructured into BIDS derivative datasets

### QSIRecon 1.2.0 (2026-02-18)
- dkimicro/wmti disabled in recon specs
- Better error on missing atlases (the error we hit)
- ABCD recon spec added
- MSDKI option for DIPY

---

## TI-Toolbox Code Map

| File | Purpose |
|------|---------|
| `tit/constants.py` | Atlas/spec lists, image tags, resource defaults |
| `tit/pre/qsi/config.py` | `QSIPrepConfig`, `QSIReconConfig`, enums |
| `tit/pre/qsi/docker_builder.py` | Docker command construction, FS license staging |
| `tit/pre/qsi/utils.py` | Host path resolution, validation, cgroup detection |
| `tit/pre/qsi/qsiprep.py` | `run_qsiprep()` — high-level runner |
| `tit/pre/qsi/qsirecon.py` | `run_qsirecon()` — high-level runner |
| `tit/pre/qsi/dti_extractor.py` | DTI tensor extraction for SimNIBS |
| `tit/pre/structural.py` | Pipeline orchestration |
| `tit/gui/components/qsi_config_dialogs.py` | PyQt5 config dialogs |
