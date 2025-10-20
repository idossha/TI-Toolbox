# MOVEA - Multi-Objective Optimization for TI Electrode Placement

MOVEA optimizes temporal interference (TI) electrode montages to maximize field strength at a target ROI while minimizing off-target effects.

## Files

### Core Modules
- **`optimizer.py`** - Multi-objective optimization using differential evolution
- **`leadfield_generator.py`** - SimNIBS leadfield matrix generation and conversion
- **`montage_formatter.py`** - Format optimization results for TI-Toolbox
- **`visualizer.py`** - Generate Pareto front and optimization visualizations
- **`utils.py`** - Helper functions (TI field calculation, target finding, validation)
- **`presets.json`** - Pre-defined ROI target coordinates (motor cortex, DLPFC, hippocampus, etc.)

### Scripts
- **`leadfield_script.py`** - CLI wrapper for leadfield generation (called by GUI as subprocess)

### Initialization
- **`__init__.py`** - Module exports

## Quick Start

### From Python
```python
from MOVEA import TIOptimizer, LeadfieldGenerator

# Generate leadfield
gen = LeadfieldGenerator(m2m_dir)
lfm_path, pos_path, shape = gen.generate_and_save_numpy(
    output_dir="path/to/output",
    eeg_cap_file="EEG10-10_Neuroelectrics.csv"
)

# Optimize electrode placement
import numpy as np
lfm = np.load(lfm_path)
positions = np.load(pos_path)

optimizer = TIOptimizer(lfm, positions, num_electrodes=lfm.shape[0])
optimizer.set_target([47, -13, 52], roi_radius_mm=10)  # Motor cortex
result = optimizer.optimize(max_generations=50, population_size=30)
```

### From GUI
Use the **MOVEA tab** in TI-Toolbox GUI:
1. Select subject
2. Create/select leadfield
3. Choose target ROI (preset or custom coordinates)
4. Run optimization
5. Results saved as CSV and SimNIBS-compatible formats

## Output Files

### Leadfield Files
- `{net_name}_leadfield.npy` - Leadfield matrix (electrodes × voxels × 3)
- `{net_name}_positions.npy` - Voxel positions in MNI space

### Optimization Results
- `movea_montage.csv` - Electrode montage in TI-Toolbox format
- `movea_montage.txt` - SimNIBS-compatible electrode list
- `pareto_front.png` - Intensity vs focality trade-off curve (optional)
- `pareto_solutions.csv` - All Pareto-optimal solutions (optional)

## Architecture

```
GUI Request
    ↓
leadfield_script.py (subprocess for instant termination)
    ↓
leadfield_generator.py (cleanup → SimNIBS → convert → save)
    ↓
optimizer.py (differential evolution)
    ↓
montage_formatter.py (format results)
    ↓
visualizer.py (generate plots)
```

## References

Based on Huang, Y., & Parra, L. C. (2019). *Can transcranial electric stimulation with multiple electrodes reach deep targets?* Brain Stimulation, 12(1), 30-40.

## Notes

- Leadfield generation requires SimNIBS 4.0+
- Optimization uses scipy's differential_evolution
- Supports single-objective (intensity) and multi-objective (intensity + focality) optimization
- All logging goes to `derivatives/ti-toolbox/logs/sub-{id}/MOVEA_*.log`

