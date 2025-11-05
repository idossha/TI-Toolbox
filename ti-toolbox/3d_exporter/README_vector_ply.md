# Vector PLY Exporter (TI and mTI)

`ti-toolbox/3d_exporter/vector_ply.py` samples electric field vectors from SimNIBS meshes and writes them to coloured arrow PLY files. It shares the same TI/mTI calculations as `TI_quick_volumetic.py` and is called by the 3D Visual Exporter extension for GUI-driven exports.

## Highlights
- Export CH1, CH2, and TI vectors as separate arrow clouds, with optional SUM and TI_normal components.
- Enable mTI mode by providing four meshes (`--mti mesh3 mesh4`).
- Flexible sampling controls (`--count`, `--top-percent`, `--surface-id`) to manage density and focus.
- Adjustable arrow appearance (length mapping, scale, width, anchor) and colour schemes.
- Optionally create a single combined PLY that contains all requested vector sets.

## Requirements
- SimNIBS 4.0+ with the `simnibs_python` interpreter.
- Python packages: `numpy`, `scipy`, and `trimesh` (installed with TI-Toolbox dependencies).
- TDCS result meshes must contain an `E` field on elements.

## Quick Start

Basic TI export (CH1, CH2, TI):
```bash
simnibs_python vector_ply.py tdcs1.msh tdcs2.msh output/TI
```

TI export with additional outputs and surface cropping:
```bash
simnibs_python vector_ply.py tdcs1.msh tdcs2.msh output/TI \
  --sum --ti-normal --surface-id 1002 \
  --count 50000 --color magscale
```

mTI export from four meshes:
```bash
simnibs_python vector_ply.py tdcs1.msh tdcs2.msh output/mTI \
  --mti tdcs3.msh tdcs4.msh --sum --combined
```

## Command Line Reference
```bash
simnibs_python vector_ply.py [OPTIONS] mesh1.msh mesh2.msh output_prefix

Positional arguments:
  mesh1.msh              First TDCS mesh (contains field['E'])
  mesh2.msh              Second TDCS mesh (contains field['E'])
  output_prefix          Output file prefix (directories created automatically)

Optional TI/mTI controls:
  --mti mesh3 mesh4      Enable mTI mode using four meshes
  --sum                  Export SUM vectors (E1+E2 or E1+E2+E3+E4)
  --ti-normal            Export TI_normal vectors (projection onto surface normals)
  --combined             Write a single combined PLY alongside individual files

Sampling and filtering:
  --surface-id INT       Crop meshes by tissue/surface tag (for example 1002 for cortex)
  --top-percent FLOAT    Keep only the top X percent by |TI| before sampling
  --count INT            Number of vectors to sample (default: 100000)
  --all-nodes            Disable sampling and keep every vector
  --seed INT             Random seed used during sampling (default: 42)

Arrow styling:
  --length-mode {linear,visual}
  --length-scale FLOAT   Length multiplier when using linear mode (default: 1.0)
  --vector-scale FLOAT   Global arrow scale (default: 1.0)
  --vector-width FLOAT   Shaft thickness (default: 1.0)
  --vector-length FLOAT  Base arrow length for visual mode (default: 1.0)
  --anchor {tail,head}   Choose which end of the arrow sits on the barycenter

Colour modes:
  --color {rgb,magscale} Colour mapping (default: rgb)
  --blue-percentile FLOAT
  --green-percentile FLOAT
  --red-percentile FLOAT  Percentiles for magscale mapping (defaults: 50, 80, 95)

Other:
  --verbose              Print additional diagnostic messages
```

## Output Files
For an output prefix `output/TI`, the exporter creates files such as:
- `output/TI_CH1.ply`
- `output/TI_CH2.ply`
- `output/TI_TI.ply` (or `output/TI_mTI.ply` in mTI mode)
- `output/TI_SUM.ply`, `output/TI_TI_normal.ply` (optional)
- `output/TI_combined.ply` (only when `--combined` is requested)

Arrow glyphs are written as ASCII PLY files with RGBA vertex colours and triangular faces.

## Using the 3D Visual Exporter extension
Switch to the "Field Vectors" mode inside **Settings -> Extensions -> 3D Visual Exporter** to run this script from the GUI. The extension can auto-detect TDCS meshes from a simulation folder, apply your sampling settings, and save the resulting PLY files under `visual_exports/sub-*/<simulation>/vectors`.

## Tips
- `--count` defaults to 100000, which can generate large files. Reduce it for lighter previews or enable `--top-percent` to highlight hotspots before sampling.
- Use `--all-nodes` only when you truly need a dense cloud; the resulting PLY can be very large.
- `--surface-id 1002` limits sampling to cortical elements, which often matches downstream workflows.
- In magscale mode, adjust the percentile cutoffs to balance colour spread across your dataset.
