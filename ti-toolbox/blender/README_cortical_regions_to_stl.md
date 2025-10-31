# SimNIBS Cortical Mesh → STL (Atlas Regions)

This repository provides a single tool to export subject‑specific cortical regions from SimNIBS `.msh` files to binary STL format for Blender (or other 3D software). It uses the subject's atlas from the `m2m_*` directory to ensure region accuracy.

## Overview

The single script `cortical_regions_to_stl.py`:
- **Exports individual cortical regions to binary STL** using the specified atlas
- **Supports cortical surface generation** from field meshes using `msh2cortex`
- **Preserves field values** in ROI regions while setting non-ROI values to zero
- **Note**: STL format does not support vertex colors or field data - only geometry is exported

## Requirements

### Software Dependencies
- **SimNIBS 4.0+** (with Python API)
- **Python 3.7+**
- **NumPy**

### Input Requirements
- Field mesh (`.msh`) containing the field data to preserve in ROI regions
- Subject's `m2m_*` directory (for the subject atlas)
- Supported atlases: `DK40`, `DKTatlas40`, `HCP_MMP1`, `aparc.a2009s`

## Usage

### Basic Usage

Export atlas‑accurate region STLs with preserved field values:

```bash
simnibs_python cortical_regions_to_stl.py \
  --mesh /path/to/surface.msh \
  --m2m /path/to/m2m_001 \
  --atlas DK40 \
  --field TI_max \
  --output-dir /path/to/output
```

### Command Line Options

```bash
simnibs_python cortical_regions_to_stl.py [OPTIONS]

Required (one of):
  --mesh           Cortical surface .msh (from msh2cortex)
  --gm-mesh        Tetrahedral GM .msh (the tool will run msh2cortex)
  --m2m            Subject m2m directory
  --output-dir     Output directory

Optional:
  --atlas          Atlas name (default: DK40)
  --surface        Surface when using --gm-mesh: central|pial|white (default: central)
  --msh2cortex     Path to msh2cortex executable (if not on PATH)
  --field          Field name to preserve (default: TI_max)
  --skip-regions   Do not export individual region STLs
  --skip-whole-gm  Do not export the whole GM STL
  --keep-meshes    Keep individual cortical region meshes as .msh files
```

### Examples

1) Export DK40 atlas regions with TI_max field (surface mesh input):
```bash
simnibs_python cortical_regions_to_stl.py \
  --mesh data/B/TI/mesh/B_TI_central.msh \
  --m2m data/m2m/m2m_001 \
  --atlas DK40 \
  --field TI_max \
  --output-dir out
```

2) Start from tetrahedral GM mesh (auto-runs msh2cortex):
```bash
simnibs_python cortical_regions_to_stl.py \
  --gm-mesh data/A/TI/mesh/A_TI.msh \
  --surface central \
  --m2m data/m2m/m2m_001 \
  --atlas HCP_MMP1 \
  --field normE \
  --output-dir out
```

3) Export DKTatlas40 regions with different field:
```bash
simnibs_python cortical_regions_to_stl.py \
  --mesh simulation/mesh/field_central.msh \
  --m2m m2m_subject \
  --atlas DKTatlas40 \
  --field magnitude \
  --output-dir results
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

- **Region STLs**: `<region_name>.stl` for each atlas region
- **Output structure**: `{output_dir}/{atlas_type}/{region_name}.stl`

## STL Format Notes

- **Binary STL format**: Compact, efficient for 3D software
- **No vertex colors**: STL format only supports geometry (vertices and faces)
- **Surface normals**: Automatically calculated for proper lighting in 3D software
- **Blender compatibility**: Direct import support in Blender and most 3D software

## Usage Tips

- **Binary STL files** are much smaller than ASCII STL and load faster in 3D software
- **For field data visualization**, use `cortical_regions_to_ply.py` instead, which supports vertex colors
- **Quality validation** automatically removes degenerate triangles and validates mesh connectivity
- **Surface mesh generation** is automatic - the script runs `msh2cortex` if needed

## Processing Method

The script uses a simple but effective approach:

1. **ROI Mask Creation**: Uses atlas to create boolean mask for each region
2. **Field Value Preservation**: Preserves original field values in ROI, sets others to zero
3. **Triangle Extraction**: Extracts triangles where at least 2 out of 3 vertices have non-zero field values
4. **STL Generation**: Creates binary STL files with proper surface normals

## Troubleshooting

### Common Issues

- **Field not found**: Ensure the specified field name exists in your mesh file
- **Atlas mismatch**: The atlas must be generated for the same subject as your mesh
- **Empty regions**: Some atlas regions may have no nodes or no positive field values
- **msh2cortex errors**: Ensure `msh2cortex` is available in your PATH

### Verification Steps

1. **Check field availability**:
   ```bash
   simnibs_python -c "import simnibs; mesh = simnibs.read_msh('your_mesh.msh'); print(list(mesh.field.keys()))"
   ```

2. **Verify atlas alignment** - the atlas nodes should correspond to your mesh nodes

3. **Check output directory** - ensure you have write permissions to the output directory
