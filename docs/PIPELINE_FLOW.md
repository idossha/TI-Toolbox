# TI-Toolbox Pipeline Flow

This document illustrates the flow of information for the two main computational pipelines in TI-Toolbox: **Simulator** and **Flex-Search**.

---

## 1. Simulator Pipeline

### Purpose
Run temporal interference (TI) simulations with predefined electrode montages.

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      ENTRYPOINT                              │
│  ti-toolbox/cli/simulator.sh                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                         INPUT                                │
│  • Subject ID(s)                                             │
│  • Conductivity type (scalar/vn/dir/mc)                      │
│  • Simulation mode (Unipolar/Multipolar)                     │
│  • Montage names OR flex-search results                      │
│  • Electrode parameters (shape, dimensions, thickness)       │
│  • Current intensity (mA)                                    │
│  • EEG net template                                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   INFORMATION FLOW                           │
│                                                              │
│  1. Load montage configuration                               │
│     └─> montage_list.json or FLEX_MONTAGES_FILE             │
│                                                              │
│  2. For each subject:                                        │
│     └─> Locate m2m directory                                 │
│     └─> Load head mesh (.msh)                                │
│     └─> Load EEG cap positions                               │
│                                                              │
│  3. Call main simulation script                              │
│     └─> ti-toolbox/sim/TI.py                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      COMPUTATION                             │
│  (TI.py)                                                     │
│                                                              │
│  For each montage:                                           │
│    1. Setup SimNIBS SESSION                                  │
│       └─> Configure conductivity, paths, DTI tensor          │
│                                                              │
│    2. Add electrode pairs (2 pairs for TI)                   │
│       └─> Position electrodes on scalp                       │
│       └─> Set current intensities                            │
│                                                              │
│    3. Run SimNIBS FEM solver                                 │
│       └─> Compute E-field for channel 1                      │
│       └─> Compute E-field for channel 2                      │
│                                                              │
│    4. Calculate TI metrics                                   │
│       └─> TI_max = |E1 - E2|                                 │
│       └─> TI_normal (if central surface available)           │
│                                                              │
│    5. Save mesh results                                      │
│       └─> Write .msh files with TI fields                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                        OUTPUT                                │
│                                                              │
│  Directory structure:                                        │
│  derivatives/SimNIBS/sub-{ID}/Simulations/{montage}/        │
│    ├── high_Frequency/                                       │
│    │   ├── {subject}_TDCS_1_{conductivity}.msh              │
│    │   └── {subject}_TDCS_2_{conductivity}.msh              │
│    └── TI/                                                   │
│        └── mesh/                                             │
│            ├── {montage}_TI.msh (TI max field)              │
│            └── {montage}_normal.msh (TI normal field)       │
│                                                              │
│  Completion report:                                          │
│  derivatives/temp/simulation_completion_{subject}_{time}.json│
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Flex-Search Pipeline

### Purpose
Optimize electrode positions to maximize/target stimulation in specific brain regions.

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      ENTRYPOINT                              │
│  ti-toolbox/cli/flex-search.sh                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                         INPUT                                │
│  • Subject ID(s)                                             │
│  • Optimization goal (mean/max/focality)                     │
│  • Post-processing method (max_TI/dir_TI_normal/tangential) │
│  • ROI definition:                                           │
│    - Spherical: (x,y,z,radius) in MNI or subject space      │
│    - Atlas: hemisphere + atlas + region label                │
│  • EEG net template                                          │
│  • Electrode parameters (radius, current)                    │
│  • Optimization parameters (iterations, population, CPUs)    │
│  • Multi-start runs (for robustness)                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   INFORMATION FLOW                           │
│                                                              │
│  1. Parse and validate inputs                                │
│     └─> ti-toolbox/opt/flex/flex_config.py                  │
│                                                              │
│  2. Setup optimization object                                │
│     └─> Configure ROI (spherical or atlas-based)            │
│     └─> Configure non-ROI (for focality)                    │
│     └─> Set electrode constraints                           │
│                                                              │
│  3. Call main optimization script                            │
│     └─> ti-toolbox/opt/flex/flex.py                         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      COMPUTATION                             │
│  (flex.py + SimNIBS opt_struct)                              │
│                                                              │
│  Multi-start loop (repeat N times):                          │
│    1. Initialize optimization                                │
│       └─> Load head mesh and ROI                             │
│       └─> Define search space (electrode positions)          │
│                                                              │
│    2. Run differential evolution optimizer                   │
│       └─> For each candidate solution:                       │
│           ├─> Place 4 electrodes on scalp                    │
│           ├─> Run fast FEM simulation                        │
│           ├─> Calculate TI field in ROI                      │
│           └─> Evaluate objective function                    │
│                                                              │
│    3. Convergence check                                      │
│       └─> Continue until max iterations or convergence       │
│                                                              │
│    4. Save optimization results                              │
│       └─> Record final electrode positions                   │
│       └─> Record objective function value                    │
│                                                              │
│  5. Select best solution (if multi-start)                    │
│     └─> Compare objective values across runs                 │
│     └─> Keep best result, discard others                     │
│                                                              │
│  6. Optional: Map to EEG net positions                       │
│     └─> Find nearest electrodes on EEG cap                   │
│                                                              │
│  7. Optional: Run final electrode simulation                 │
│     └─> Full-resolution simulation with optimal positions    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                        OUTPUT                                │
│                                                              │
│  Directory structure:                                        │
│  derivatives/SimNIBS/sub-{ID}/flex-search/{roi_name}/       │
│    ├── optimization_summary.txt                              │
│    ├── electrode_mapping.json                                │
│    │   └─> Optimized XYZ positions                           │
│    │   └─> Mapped EEG labels (if enabled)                    │
│    │   └─> Objective function value                          │
│    ├── leadfield/                                            │
│    │   └─> Precomputed E-field basis functions              │
│    └── final_simulation/ (if enabled)                        │
│        └─> Full TI simulation with optimal electrodes        │
│                                                              │
│  Multi-start summary (if N > 1):                             │
│    └─> multistart_optimization_summary.txt                   │
│        └─> Comparison of all runs                            │
│        └─> Best solution selection rationale                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Differences

| Aspect | Simulator | Flex-Search |
|--------|-----------|-------------|
| **Purpose** | Simulate predefined montages | Optimize electrode positions |
| **Input** | Montage names or coordinates | ROI specification |
| **Computation** | Direct FEM simulation | Iterative optimization + FEM |
| **Duration** | Minutes per montage | Minutes to hours (depends on iterations) |
| **Output** | TI field distributions | Optimal electrode positions + optional simulation |
| **Use Case** | Test known configurations | Find best configuration for target |

---

## Integration Point

The output of **Flex-Search** can be used as input to **Simulator**:

```
Flex-Search Output (electrode_mapping.json)
            ↓
    Convert to montage format
            ↓
Simulator Input (FLEX_MONTAGES_FILE)
            ↓
    Run full simulation
```

This allows users to:
1. Optimize electrode positions with Flex-Search
2. Validate results with full-resolution Simulator
3. Compare optimized vs. standard montages

