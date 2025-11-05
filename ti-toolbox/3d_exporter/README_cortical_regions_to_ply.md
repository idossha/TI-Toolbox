# Cortical Regions -> PLY Exporter

`ti-toolbox/3d_exporter/cortical_regions_to_ply.py` converts SimNIBS cortical surfaces into region-specific PLY files that can be loaded in Blender or other 3D tools. The same script powers the 3D Visual Exporter extension so you can run it either from the command line or from the TI-Toolbox GUI.

## Highlights
- Generate atlas-aware region PLY files plus an optional whole grey-matter surface.
- Start from an existing cortical surface (`--mesh`) or let the tool extract it from a volumetric GM mesh (`--gm-mesh` through `msh2cortex`).
- Preserve mesh fields (default `TI_max`) as vertex colours or store them as scalars.
- Restrict exports to a subset of regions and optionally retain intermediate `.msh` files for inspection.
- Share a global colour range across regions using `--field-range` or `--global-from-nifti`.

## Requirements
### Software
- SimNIBS 4.0 or later (CLI and Python API available in the `simnibs_python` environment).
- Python 3.8+ with `numpy` and `nibabel` (installed with SimNIBS).
- Optional: `matplotlib` for named colormaps. When it is missing the script falls back to a blue/red gradient.

### Inputs
- Cortical surface mesh produced by `msh2cortex` (`--mesh`) **or** a tetrahedral GM mesh (`--gm-mesh`) that the script converts on the fly.
- Subject `m2m_*` directory containing atlas definitions.
- Mesh field to export (default `TI_max`). Specify `--field` if you stored a different quantity.

Supported atlases: `DK40` (default), `DKTatlas40`, `HCP_MMP1`, `aparc.a2009s`.

## Quick Start

Export DK40 regions with colours sampled from `TI_max`:
```bash
simnibs_python cortical_regions_to_ply.py \
  --mesh derivatives/SimNIBS/sub-001/TI/subject_central.msh \
  --m2m derivatives/SimNIBS/sub-001/m2m_sub-001 \
  --output-dir exports/sub-001/sessionA
```

Start from a GM mesh and keep only a subset of regions:
```bash
simnibs_python cortical_regions_to_ply.py \
  --gm-mesh derivatives/SimNIBS/sub-001/TI/subject_TI.msh \
  --m2m derivatives/SimNIBS/sub-001/m2m_sub-001 \
  --output-dir exports/sub-001/sessionA \
  --regions rostralanteriorcingulate,insula \
  --skip-whole-gm \
  --keep-meshes
```

## Command Line Reference
```bash
simnibs_python cortical_regions_to_ply.py [OPTIONS]

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
  --field NAME         Mesh field to export (default: TI_max)
  --scalars            Store field values as PLY scalars instead of colours
  --colormap NAME      Matplotlib colormap when colouring vertices
  --field-range MIN MAX
                       Explicit min/max used for colour scaling
  --global-from-nifti FILE
                       Derive colour range from a NIfTI volume
  --regions A,B,...    Only export the listed atlas regions
  --skip-regions       Skip per-region PLYs
  --skip-whole-gm      Skip the whole grey-matter PLY
  --keep-meshes        Retain intermediate region meshes (.msh)
```

## Output Structure
```
{output-dir}/
  cortical_plys/
    regions/
      <Region>.ply
    whole_gm.ply        # unless --skip-whole-gm
  meshes/               # only when --keep-meshes is set
```

## Using the 3D Visual Exporter extension
Open **Settings -> Extensions -> 3D Visual Exporter** in TI-Toolbox to launch a GUI that orchestrates this exporter (and the STL/vector tools). The extension supplies the subject, simulation, atlas, and output selections you make in the dialog and then runs `cortical_regions_to_ply.py` behind the scenes.

## Tips
- Confirm the selected `--field` exists in the mesh: `simnibs_python -c "import simnibs; print(simnibs.read_msh('mesh.msh').field.keys())"`.
- Use `--global-from-nifti` or `--field-range` to maintain consistent colour scales across subjects or simulations.
- Pair with `cortical_regions_to_stl.py` when you need geometry-only outputs for CAD or 3D printing workflows.
