# Vector PLY Exporter (TI/mTI)

One-command exporter that generates arrow PLYs for CH1, CH2, and TI (or mTI) from SimNIBS `.msh` files. Optional outputs include the vector sum (SUM) and the TI normal component (TI_normal). Uses the same TI/mTI math as `TI_quick_volumetic.py`.

## Overview

The script `scripts/vector_ply.py`:
- **Exports CH1, CH2, and TI vector fields** as arrow PLY files for visualization
- **Supports mTI calculation** with 4 input meshes
- **Optional vector sum and normal components** for comprehensive analysis
- **Configurable arrow styling and color schemes** for different visualization needs

## Quick Start

Prerequisites: SimNIBS environment; Python packages: numpy, trimesh, scipy.

Defaults export CH1, CH2, and TI. Use `--mti` to provide meshes 3 and 4 for mTI.

```bash
simnibs_python scripts/vector_ply.py tdcs1.msh tdcs2.msh output/TI
simnibs_python scripts/vector_ply.py tdcs1.msh tdcs2.msh output/TI --sum --ti-normal --surface-id 1002
simnibs_python scripts/vector_ply.py tdcs1.msh tdcs2.msh output/mTI --mti tdcs3.msh tdcs4.msh
```

## Inputs and Outputs

### Input Files
- **TDCS simulation result files** (`.msh` format) containing E-field data (`field['E']`)
- Must be SimNIBS mesh files with element-based E-field vectors from TDCS simulations

### Output Files
- **PLY files with arrow glyphs** at sampled element barycenters:
  - `_CH1.ply`, `_CH2.ply`, `_TI.ply` (or `_mTI.ply`)
  - Optional: `_SUM.ply` (or `_SUM4.ply` in mTI), `_TI_normal.ply` (or `_mTI_normal.ply`)
  - Optional combined PLY with all requested types: `_combined.ply`

## Command Line Options

```bash
simnibs_python scripts/vector_ply.py [OPTIONS] mesh1.msh mesh2.msh output_prefix
```

### Required Arguments
- `mesh1.msh` - First TDCS simulation result file (with E-field data)
- `mesh2.msh` - Second TDCS simulation result file (with E-field data)
- `output_prefix` - Output file prefix

### Optional Arguments

#### TI/mTI Options
- `--mti mesh3.msh mesh4.msh` - Compute mTI (4 TDCS simulation files) instead of TI
- `--sum` - Also export SUM (TI: E1+E2; mTI: E1+E2+E3+E4)
- `--ti-normal` - Also export TI_normal (projection onto surface normals)
- `--combined` - Export a single PLY containing all requested types

#### Sampling Options
- `--surface-id INT` - Crop meshes by tissue/surface tag before sampling (e.g., 1002 for GM surface)
- `--top-percent FLOAT` - Keep only top X% by |TI/mTI| before sampling (e.g., 50)
- `--count INT` - Number of vectors to sample (default: 100)
- `--seed INT` - Random seed (default: 42)

#### Arrow Styling
- `--length-mode {linear,visual}` - Length scaling mode (default: linear)
- `--length-scale FLOAT` - Scene units per V/m (linear mode)
- `--vector-scale FLOAT` - Global arrow scale
- `--vector-width FLOAT` - Shaft thickness
- `--vector-length FLOAT` - Base arrow length (visual mode)
- `--anchor {tail,head}` - Which end touches barycenter

#### Color Options
- `--color {default,rgb,magscale}` - Color scheme
- `--blue-percentile FLOAT` - Blue percentile (default: 0)
- `--green-percentile FLOAT` - Green percentile (default: 50)
- `--red-percentile FLOAT` - Red percentile (default: 95)

## Color Modes

- **default**: CH1 blue, CH2 green, TI red, SUM yellow, TI_normal cyan
- **rgb**: CH1 red, CH2 blue, TI green, SUM yellow, TI_normal cyan
- **magscale**: Magnitude-based gradient (blue→green→red) normalized using percentiles across full magnitudes of all vectors present (reduces outlier skew). Percentiles set the blue pivot, green pivot, and red cap.

## Tags and Surfaces

Use `--surface-id` to crop meshes to a single tissue/surface (e.g., GM=1002) before sampling, limiting arrows to that region. TI_normal uses a simple per-element surface normal approximation; for high-fidelity grey-matter normals and node mapping, compute normals via `TI_quick_volumetic.py`.

## Usage Tips

- **Increase `--count`** for denser arrow fields (mind file size)
- **Use `--top-percent`** to highlight hotspots before sampling
- **Prefer `--length-mode linear --length-scale`** to make arrow length proportional to |E| in scene units

## Examples

### Basic TI Export
```bash
simnibs_python scripts/vector_ply.py tdcs1.msh tdcs2.msh output/TI
```

### TI with Additional Components
```bash
simnibs_python scripts/vector_ply.py tdcs1.msh tdcs2.msh output/TI --sum --ti-normal --surface-id 1002
```

### mTI Export (4 meshes)
```bash
simnibs_python scripts/vector_ply.py tdcs1.msh tdcs2.msh output/mTI --mti tdcs3.msh tdcs4.msh
```

### Custom Styling
```bash
simnibs_python scripts/vector_ply.py tdcs1.msh tdcs2.msh output/TI \
  --count 500 \
  --length-mode linear \
  --length-scale 0.001 \
  --color magscale \
  --top-percent 25
```


