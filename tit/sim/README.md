# TI/mTI Simulation Module

Unified Python-only simulation module for Temporal Interference (TI) and multipolar TI (mTI) simulations.

## Overview

This module provides a clean, modular interface for running TI simulations using SimNIBS. It automatically detects whether to run standard TI (2 electrode pairs) or mTI (4 electrode pairs) based on the montage configuration.

## Architecture

```
sim/
├── __init__.py           # Package exports
├── config.py             # Configuration dataclasses (SimulationConfig, ParallelConfig, etc.)
├── montage_loader.py     # Montage loading and validation
├── session_builder.py    # SimNIBS session construction
├── post_processor.py     # TI/mTI calculation and mesh saving
├── simulator.py          # Main unified entry point with parallel execution
├── visualize-montage.sh  # Montage visualization script
└── README.md             # This file
```

## Key Features

- **Unified Interface**: Single entry point for both TI and mTI simulations
- **Automatic Detection**: Simulation type determined from montage configuration
- **Parallel Execution**: Run multiple montage simulations across CPU cores
- **Type Safety**: Dataclass-based configuration with validation
- **Modular Design**: Clear separation of concerns
- **Pure Python**: No bash script dependencies
- **PathManager Integration**: Full BIDS compliance using PathManager
- **Flexible Montages**: Support for regular, flex, and freehand montages
- **Complete Pipeline**: Includes all post-processing steps from original implementation

## Full Pipeline Features

The refactored module includes ALL features from the original pipeline:

1. **Directory Structure Creation**: Complete BIDS-compliant directory hierarchy
   - `high_Frequency/{mesh,niftis,analysis}`
   - `TI/{mesh,niftis,surface_overlays,montage_imgs}`
   - `mTI/{mesh,niftis,montage_imgs}` (for mTI mode)
   - `documentation/`

2. **Montage Visualization**: PNG visualization of electrode montages
   - Calls `visualize-montage.sh` for standard electrode caps
   - Gracefully skips freehand/flex XYZ coordinate modes

3. **SimNIBS Simulation**: Full simulation with configurable parameters
   - Anisotropic conductivity support (DTI tensor)
   - Custom electrode configurations
   - Per-channel intensity control

4. **TI/mTI Field Calculation**: Complete field processing
   - TI max field calculation
   - TI normal (cortical surface) calculation
   - mTI intermediate fields (TI_AB, TI_CD)

5. **Field Extraction**: Grey matter and white matter mesh separation
   - Uses `field_extract.py` or direct extraction
   - Proper BIDS-compliant naming

6. **NIfTI Transformation**: Mesh to NIfTI conversion
   - MNI space conversion (`subject2mni`)
   - Subject space conversion (`msh2nii`)
   - Automatic handling of surface meshes

7. **T1 to MNI Conversion**: Subject T1 to MNI space

8. **File Organization**: Automatic organization of output files
   - HF mesh files to proper directories
   - Surface overlays to TI/surface_overlays
   - Log and mat files to documentation
   - Analysis files to high_Frequency/analysis

9. **Parallel Execution**: Multi-core simulation support
   - Run multiple montages simultaneously across CPU cores
   - Configurable worker count (default: half of CPU cores)
   - Per-worker logging for debugging
   - Progress callbacks for GUI integration

## Parallel Execution

The module supports parallel execution of multiple montage simulations:

```python
from tit.sim import run_simulation, SimulationConfig, ParallelConfig

# Enable parallel execution
config = SimulationConfig(
    subject_id="001",
    project_dir="/mnt/my_project",
    conductivity_type=ConductivityType.SCALAR,
    intensities=IntensityConfig.from_string("2.0"),
    electrode=ElectrodeConfig(),
    eeg_net="EGI_template.csv",
    parallel=ParallelConfig(
        enabled=True,     # Enable parallel mode
        max_workers=4     # Use 4 CPU cores (0 = auto-detect)
    )
)

# Run multiple montages in parallel
results = run_simulation(config, montages)
```

### Parallel Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `False` | Enable/disable parallel execution |
| `max_workers` | `0` | Number of worker processes (0 = auto, uses CPU_count // 2) |

### Notes

- Each worker process has its own log file for debugging
- SimNIBS simulations are memory-intensive; limit workers on low-RAM systems
- Progress callbacks work in both sequential and parallel modes
- For single montages, parallel mode is automatically disabled

## Usage

### As a Module

```python
from tit.sim import run_simulation, SimulationConfig, ElectrodeConfig, IntensityConfig, ConductivityType
from tit.sim.montage_loader import load_montages

# Configure simulation
config = SimulationConfig(
    subject_id="001",
    project_dir="/mnt/my_project",
    conductivity_type=ConductivityType.DIR,
    intensities=IntensityConfig.from_string("2.0,2.0"),
    electrode=ElectrodeConfig(
        shape="ellipse",
        dimensions=[8.0, 8.0],
        thickness=4.0
    ),
    eeg_net="EGI_template.csv"
)

# Load montages
montages = load_montages(
    montage_names=["montage1", "montage2"],
    project_dir="/mnt/my_project",
    eeg_net="EGI_template.csv"
)

# Run simulations
results = run_simulation(config, montages)
```

### Command-Line

```bash
simnibs_python simulator.py SUBJECT_ID CONDUCTIVITY PROJECT_DIR SIMULATION_DIR MODE \
    INTENSITY ELECTRODE_SHAPE DIMENSIONS THICKNESS EEG_NET MONTAGE_NAMES...
```

**Example:**

```bash
simnibs_python simulator.py 001 dir /mnt/project /mnt/project/derivatives/SimNIBS/sub-001/Simulations \
    TI 2.0 ellipse 8,8 4 EGI_template.csv montage1 montage2
```

## Configuration

### SimulationConfig

Main configuration dataclass for simulations.

**Fields:**
- `subject_id`: Subject identifier (e.g., "001")
- `project_dir`: Project directory path
- `conductivity_type`: ConductivityType enum (SCALAR, VN, DIR, MC)
- `intensities`: IntensityConfig object
- `electrode`: ElectrodeConfig object
- `eeg_net`: EEG net filename (default: "EGI_template.csv")
- `map_to_surf`: Map to cortical surface (default: True)
- `map_to_vol`: Map to volume (default: True)
- `map_to_mni`: Map to MNI space (default: True)
- `map_to_fsavg`: Map to FreeSurfer average (default: False)
- `tissues_in_niftis`: Tissues to export (default: "all")
- `open_in_gmsh`: Open in Gmsh GUI (default: False)

### IntensityConfig

Current intensity configuration for TI/mTI simulations.

Each electrode pair requires one intensity value (in mA). SimNIBS automatically applies equal and opposite currents to the two electrodes within each pair. For example: `pair1=2.0` means electrode 1 gets +2.0mA and electrode 2 gets -2.0mA.

**Fields:**
- `pair1`: Intensity for first electrode pair (mA)
- `pair2`: Intensity for second electrode pair (mA)
- `pair3`: Intensity for third electrode pair (mA) - mTI only
- `pair4`: Intensity for fourth electrode pair (mA) - mTI only

**Usage:**
- TI mode (2 pairs): Uses `pair1` and `pair2`
- mTI mode (4 pairs): Uses `pair1`, `pair2`, `pair3`, and `pair4`

**Parsing from string:**
- `"2.0"` → All pairs: 2.0 mA
- `"2.0,1.5"` → Pair 1: 2.0 mA, Pair 2: 1.5 mA (TI mode)
- `"2.0,1.5,1.0,0.5"` → All pairs individually specified (mTI mode)

### ElectrodeConfig

Electrode properties configuration.

**Fields:**
- `shape`: Electrode shape ("ellipse" or "rect")
- `dimensions`: [x_dim, y_dim] in mm
- `thickness`: Gel thickness in mm
- `sponge_thickness`: Sponge thickness in mm (default: 2.0)

### MontageConfig

Individual montage configuration.

**Fields:**
- `name`: Montage name
- `electrode_pairs`: List of (pos1, pos2) tuples
- `is_xyz`: True if positions are XYZ coordinates, False if electrode names
- `eeg_net`: Optional override for EEG net

**Properties:**
- `simulation_mode`: Automatically determined (TI or MTI)
- `num_pairs`: Number of electrode pairs

## Simulation Types

### TI (2-pair)

Standard temporal interference with 2 electrode pairs.

**Montage format:**
```python
electrode_pairs = [
    ("E1", "E2"),   # First pair
    ("E3", "E4")    # Second pair
]
```

### mTI (4-pair)

Multipolar temporal interference with 4 electrode pairs.

**Montage format:**
```python
electrode_pairs = [
    ("E1", "E2"),   # Pair A
    ("E3", "E4"),   # Pair B
    ("E5", "E6"),   # Pair C
    ("E7", "E8")    # Pair D
]
```

## Montage Loading

The module supports three types of montages:

### 1. Regular Montages

Stored in `config/montage_list.json`:

```json
{
  "nets": {
    "EGI_template.csv": {
      "uni_polar_montages": {},
      "multi_polar_montages": {
        "montage1": [["E1", "E2"], ["E3", "E4"]]
      }
    }
  }
}
```

### 2. Flex Montages

Loaded from file specified in `FLEX_MONTAGES_FILE` environment variable.

**Types:**
- `flex_mapped`: Electrode names from EEG cap
- `flex_optimized`: XYZ coordinates
- `freehand_xyz`: Freehand XYZ coordinates

**Example:**
```json
{
  "name": "optimized_montage",
  "type": "flex_optimized",
  "electrode_positions": [
    [10.5, 20.3, 65.2],
    [-10.5, 20.3, 65.2],
    [15.2, -25.1, 70.5],
    [-15.2, -25.1, 70.5]
  ]
}
```

### 3. Freehand Montages

Same as flex montages but loaded from `FREEHAND_MONTAGES_FILE` environment variable.

## Output Structure

```
derivatives/SimNIBS/sub-{ID}/Simulations/{montage_name}/
├── high_Frequency/                          # SimNIBS raw outputs
│   ├── {subject_id}_TDCS_1_{cond}.msh      # HF mesh for pair 1
│   ├── {subject_id}_TDCS_2_{cond}.msh      # HF mesh for pair 2
│   └── ...
├── TI/
│   └── mesh/
│       ├── {montage_name}_TI.msh           # TI max field
│       └── {montage_name}_normal.msh       # TI normal (if available)
└── mTI/  (for 4-pair montages only)
    └── mesh/
        ├── {montage_name}_TI_AB.msh        # Intermediate TI (pairs A-B)
        ├── {montage_name}_TI_CD.msh        # Intermediate TI (pairs C-D)
        └── {montage_name}_mTI.msh          # Final mTI field
```

## Migration from Old Code

The old implementation has been moved to `bk/` directory:

- `bk/TI.py` - Old TI simulator
- `bk/mTI.py` - Old mTI simulator
- `bk/main-TI.sh` - Old TI bash wrapper
- `bk/main-mTI.sh` - Old mTI bash wrapper
- `bk/visualize-montage.sh` - Old visualization script

**Key differences in new implementation:**

1. **Single entry point**: `simulator.py` handles both TI and mTI
2. **Pure Python**: No bash scripts required
3. **Type-safe**: Dataclass-based configuration
4. **Modular**: Clear separation of concerns
5. **Automatic detection**: Simulation type determined from montage

## Environment Variables

- `FLEX_MONTAGES_FILE`: Path to flex montages JSON file
- `FREEHAND_MONTAGES_FILE`: Path to freehand montages JSON file
- `TISSUE_COND_{N}`: Override tissue conductivity (N = 1, 2, 3, ...)
- `SIMULATION_SESSION_ID`: Session identifier for reporting
- `TI_LOG_FILE`: Override default log file path

## Error Handling

The simulator provides detailed error reporting:

- Invalid montage configurations
- Missing files (mesh, EEG cap, DTI tensor)
- SimNIBS execution errors
- Post-processing failures

All errors are logged and included in the completion report.

## Completion Report

After execution, a JSON report is saved to `derivatives/temp/simulation_completion_{subject_id}_{timestamp}.json`:

```json
{
  "session_id": "...",
  "subject_id": "001",
  "project_dir": "/mnt/project",
  "simulation_dir": "...",
  "completed_simulations": [...],
  "failed_simulations": [...],
  "timestamp": "2025-12-14T00:48:00",
  "total_simulations": 2,
  "success_count": 2,
  "error_count": 0
}
```

## Dependencies

- SimNIBS 4.5+
- NumPy
- tit core modules (PathManager, logging_util, calc)

## Testing

See `tests/test_sim.py` for unit tests and usage examples.

## Future Enhancements

Potential improvements:

- [ ] Parallel simulation execution
- [ ] GPU acceleration for field calculations
- [ ] Real-time progress reporting
- [ ] Validation of montage configurations
- [ ] Automatic mesh quality checks
- [ ] Integration with visualization pipeline

## Maintainer

Ido Haber (ihaber@wisc.edu)
