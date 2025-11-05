# Cortical Regions -> STL Exporter

`ti-toolbox/3d_exporter/cortical_regions_to_stl.py` exports atlas-defined cortical regions as binary STL meshes. Use it to create lightweight geometry for CAD, 3D printing, or any workflow that does not require colour information. The script is also triggered by the 3D Visual Exporter extension, so you can run it either as a standalone command or from the GUI.

## Highlights
- Produce per-region STL meshes plus an optional whole grey-matter surface.
- Accept either an existing cortical surface (`--mesh`) or a volumetric GM mesh (`--gm-mesh`) that is converted via `msh2cortex`.
- Optionally keep the intermediate region `.msh` files for validation with SimNIBS.
- Export only the regions you care about with `--regions` or skip entire groups of outputs.
- Resulting STLs use consistent normals and are ready for import into Blender, MeshLab, or CAD packages.

## Requirements
### Software
- SimNIBS 4.0 or later with the `simnibs_python` environment.
- Python 3.8+ with `numpy` (bundled with SimNIBS).

### Inputs
- Cortical surface mesh from `msh2cortex` (`--mesh`) **or** GM tetrahedral mesh (`--gm-mesh`).
- Subject `m2m_*` directory for atlas lookup.
- Mesh field that identifies positive regions (default `TI_max`).

Supported atlases: `DK40` (default), `DKTatlas40`, `HCP_MMP1`, `aparc.a2009s`.

## Quick Start

Export DK40 regions and the whole surface from an existing cortical mesh:
```bash
simnibs_python cortical_regions_to_stl.py \
  --mesh derivatives/SimNIBS/sub-001/TI/subject_central.msh \
  --m2m derivatives/SimNIBS/sub-001/m2m_sub-001 \
  --output-dir exports/sub-001/sessionA
```

Start from a GM mesh and keep only selectable regions:
```bash
simnibs_python cortical_regions_to_stl.py \
  --gm-mesh derivatives/SimNIBS/sub-001/TI/subject_TI.msh \
  --m2m derivatives/SimNIBS/sub-001/m2m_sub-001 \
  --output-dir exports/sub-001/sessionA \
  --regions insula,caudalanteriorcingulate \
  --keep-meshes
```

## Command Line Reference
```bash
simnibs_python cortical_regions_to_stl.py [OPTIONS]

Required:
  --m2m PATH           Subject m2m directory
  --output-dir PATH    Destination directory
  --mesh FILE          Cortical surface mesh (.msh from msh2cortex)
    or
  --gm-mesh FILE       GM tetrahedral mesh; converts with msh2cortex

Optional:
  --atlas NAME         Atlas (default: DK40)
  --surface {central,pial,white}
                       Surface to extract when using --gm-mesh (default: central)
  --msh2cortex PATH    Path to msh2cortex if it is not on PATH
  --field NAME         Mesh field to sample (default: TI_max)
  --regions A,B,...    Only export the listed atlas regions
  --skip-regions       Skip per-region STLs
  --skip-whole-gm      Skip the whole grey-matter STL
  --keep-meshes        Retain intermediate region meshes (.msh)
```

## Output Structure
```
{output-dir}/
  cortical_stls/
    regions/
      <Region>.stl
    whole_gm.stl      # unless --skip-whole-gm
  meshes/             # only when --keep-meshes is set
```

## Using the 3D Visual Exporter extension
When you launch **Settings -> Extensions -> 3D Visual Exporter**, choosing the "Cortical Regions" mode will call this script with the selections you make (atlas, regions, formats, keep meshes). STL exports are written alongside the PLY outputs in the `visual_exports` directory managed by TI-Toolbox.

## Tips
- STL carries geometry only. Use the PLY exporter when you need colour-mapped fields.
- Verify the requested `--field` exists in the mesh before running the export.
- Because STLs remove scalar fields, keep the `.msh` intermediates (`--keep-meshes`) if you plan to revisit the data in SimNIBS.
- Combine the STL export with the PLY output when you need both colour-rich visualisations and clean CAD geometry.
