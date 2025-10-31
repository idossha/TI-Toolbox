# SimNIBS Cortical Mesh → PLY (Regions + Whole GM)

This repository provides a single tool to export subject‑specific cortical regions and the whole gray‑matter (GM) surface from SimNIBS `.msh` files to PLY for Blender (or other tools). It uses the subject's atlas from the `m2m_*` directory to ensure region accuracy (default atlas: `DK40`).

## Overview

The single script `cortical_regions_to_ply.py`:
- **Exports individual cortical regions to PLY** using the chosen atlas (default `DK40`)
- **Exports the whole GM surface to PLY**
- **Optionally samples a NIfTI field onto mesh nodes** and maps it to vertex colors or stores as scalars
- **Supports global colormap normalization** from a NIfTI file so colors are comparable across regions/meshes
- **Uses consistent ROI extraction** with preserved field values for accurate visualization

## Requirements

### Software Dependencies
- **SimNIBS 4.0+** (with Python API)
- **Python 3.7+**
- **NumPy**
- **nibabel** (for NIfTI field data handling)
- **matplotlib** (optional, for colormaps; otherwise a simple blue↔red map is used)

### Input Requirements
- EITHER a cortical surface mesh (`.msh`) produced by `msh2cortex` OR a tetrahedral GM `.msh` (the tool can run `msh2cortex` for you)
- Subject’s `m2m_*` directory (for the subject atlas)
- Supported atlases: `DK40` (default), `DKTatlas40`, `HCP_MMP1`, `aparc.a2009s`
- Optional: NIfTI field file (e.g., `*_TI_max.nii.gz`) for field coloring


## Usage

### Basic Usage

Export atlas‑accurate region PLYs and the whole GM PLY (default atlas: `DK40`):

```bash
simnibs_python cortical_regions_to_ply.py \
  --mesh subject_overlays/subject_central.msh \
  --m2m m2m_subject \
  --output-dir out \
  --field-file subject_overlays/subject_TI_max.nii.gz
```

### Command Line Options

```bash
simnibs_python cortical_regions_to_ply.py [OPTIONS]

Required (one of):
  --mesh           Cortical surface .msh (from msh2cortex)
  --gm-mesh        Tetrahedral GM .msh (the tool will run msh2cortex)
  --m2m            Subject m2m directory
  --output-dir     Output directory

Optional:
  --atlas          Atlas name (default: DK40)
  --surface        Surface when using --gm-mesh: central|pial|white (default: central)
  --msh2cortex     Path to msh2cortex executable (if not on PATH)
  --field-file     NIfTI file to sample onto nodes (e.g., TI_max)
  --field          Field name to use/store (default: TI_max)
  --scalars        Store scalars instead of vertex colors
  --colormap       Colormap name (default: viridis)
  --field-range    MIN MAX explicit range for mapping
  --global-from-nifti  Use global min/max from the given NIfTI for color scaling
  --skip-regions   Do not export individual region PLYs
  --skip-whole-gm  Do not export the whole GM PLY
```

### Examples

1) Regions + whole GM with default atlas and NIfTI colors (surface mesh input):
```bash
simnibs_python cortical_regions_to_ply.py \
  --mesh subject_overlays/subject_central.msh \
  --m2m m2m_subject \
  --output-dir out \
  --field-file subject_overlays/subject_TI_max.nii.gz
```

2) Start from tetrahedral GM mesh (auto-runs msh2cortex):
```bash
simnibs_python cortical_regions_to_ply.py \
  --gm-mesh m2m_subject/subject.msh \
  --surface central \
  --m2m m2m_subject \
  --output-dir out
```

3) Without field data (gray colors) and custom atlas:
```bash
simnibs_python cortical_regions_to_ply.py \
  --mesh subject_overlays/subject_central.msh \
  --m2m m2m_subject \
  --atlas HCP_MMP1 \
  --output-dir out
```

4) Global color normalization from NIfTI (comparable colors across regions):
```bash
simnibs_python cortical_regions_to_ply.py \
  --mesh subject_overlays/subject_central.msh \
  --m2m m2m_subject \
  --output-dir out \
  --field-file subject_overlays/subject_TI_max.nii.gz \
  --global-from-nifti subject_overlays/subject_TI_max.nii.gz
```


## Supported Atlases

### HCP_MMP1 (Human Connectome Project Multi-Modal Parcellation)
- **Regions**: ~180 cortical areas per hemisphere
- **Based on**: Multi-modal MRI features
- **Reference**: Glasser et al. (2016) Nature

### DK40 (Desikan-Killiany 40) / DKTatlas40 (Desikan-Killiany-Tourville)
- **Regions**: ~40 cortical areas per hemisphere
- **Based on**: Structural MRI
- **Reference**: Desikan et al. (2006) NeuroImage

### aparc.a2009s (Destrieux Atlas)
- **Regions**: ~75 cortical areas per hemisphere
- **Based on**: Sulco-gyral anatomy
- **Reference**: Destrieux et al. (2010) NeuroImage

## Output Files

- **Region PLYs**: `<region_name>_region.ply` for each atlas region
- **Whole GM PLY**: `whole_gm.ply`

## Processing Method

The script uses a consistent ROI extraction approach:

1. **ROI Mask Creation**: Uses atlas to create boolean mask for each region
2. **Field Value Preservation**: Preserves original field values in ROI, sets others to zero
3. **Triangle Extraction**: Extracts triangles where at least 2 out of 3 vertices have non-zero field values
4. **Global Color Scaling**: Uses consistent field range across all regions for comparable visualization
5. **PLY Generation**: Creates PLY files with proper field data mapping

## Usage Tips

- **Use `--global-from-nifti`** for consistent color scaling across regions
- **Specify `--field-range`** for explicit color mapping ranges
- **Use `--scalars`** to store field data as scalars instead of vertex colors
- **Skip regions or whole GM** with `--skip-regions` or `--skip-whole-gm` for faster processing
- **Consistent visualization**: All regions use the same color scale, so combined regions look identical to whole GM


