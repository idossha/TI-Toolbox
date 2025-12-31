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
│  tit/cli/simulator.sh                                 │
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
│     └─> tit/sim/TI.py                                 │
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
│  tit/cli/flex-search.sh                               │
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
│     └─> tit/opt/flex/flex_config.py                  │
│                                                              │
│  2. Setup optimization object                                │
│     └─> Configure ROI (spherical or atlas-based)            │
│     └─> Configure non-ROI (for focality)                    │
│     └─> Set electrode constraints                           │
│                                                              │
│  3. Call main optimization script                            │
│     └─> tit/opt/flex/flex.py                         │
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

## 3. Ex-Search Pipeline

### Purpose
Perform exhaustive search optimization across all electrode combinations and current ratios to guarantee finding the globally optimal TI montage.

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      ENTRYPOINT                              │
│  tit/cli/ex-search.sh                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                         INPUT                                │
│  • Subject ID(s)                                             │
│  • ROI definition:                                           │
│    - Spherical: (x,y,z,radius) in MNI or subject space      │
│  • EEG net selection (auto-detected from pre-processing)    │
│  • Electrode groups (E1+, E1-, E2+, E2-)                     │
│  • Current parameters:                                       │
│    - Total current (mA)                                      │
│    - Current step size (mA)                                  │
│    - Channel limit (mA)                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   INFORMATION FLOW                           │
│                                                              │
│  1. Parse and validate inputs                                │
│     └─> Interactive electrode and current parameter input   │
│                                                              │
│  2. Setup optimization environment                           │
│     └─> Locate m2m directory and ROI files                   │
│     └─> Load/select EEG net and leadfield                    │
│                                                              │
│  3. Call main optimization script                            │
│     └─> tit/opt/ex/ti_sim.py                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      COMPUTATION                             │
│  (ti_sim.py + SimNIBS TI_utils)                              │
│                                                              │
│  1. Generate current ratios                                  │
│     └─> Systematic ratios respecting channel limits          │
│                                                              │
│  2. Load leadfield and mesh                                  │
│     └─> Find ROI and grey matter elements                    │
│                                                              │
│  3. Exhaustive combination loop                              │
│     └─> For each electrode combination (N⁴):                │
│         ├─> For each current ratio:                          │
│         │   ├─> Calculate E-fields for both channels         │
│         │   ├─> Compute TI_max field                          │
│         │   ├─> Extract ROI and GM values                     │
│         │   ├─> Calculate metrics (TImax, TImean, Focality)  │
│         │   └─> Store results                                 │
│         └─> Progress tracking with ETA                        │
│                                                              │
│  4. Generate analysis outputs                                │
│     └─> Statistical summaries and histograms                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                        OUTPUT                                │
│                                                              │
│  Directory structure:                                        │
│  derivatives/SimNIBS/sub-{ID}/ex-search/{roi_name}_{net}/    │
│    ├── analysis_results.json                                  │
│    │   └─> Complete results for all combinations             │
│    ├── final_output.csv                                       │
│    │   └─> Summary CSV with metrics and current ratios       │
│    ├── montage_distributions.png                              │
│    │   └─> Histograms: TImax, TImean, Focality distributions │
│    └── logs/                                                  │
│        └─> Complete pipeline log                              │
│                                                              │
│  Metrics included:                                           │
│    • TImax_ROI - Maximum TI field in ROI                     │
│    • TImean_ROI - Mean TI field in ROI                       │
│    • TImean_GM - Mean TI field in grey matter                │
│    • Focality - TImean_ROI / TImean_GM                       │
│    • Current ratios for each channel                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Differences

| Aspect | Simulator | Flex-Search | Ex-Search |
|--------|-----------|-------------|-----------|
| **Purpose** | Simulate predefined montages | Optimize electrode positions | Exhaustive montage search |
| **Input** | Montage names or coordinates | ROI specification | Electrode groups + ROI |
| **Algorithm** | Direct FEM simulation | Differential evolution | N⁴ × current_ratios combinations |
| **Optimality** | N/A (predefined) | Local optimum | **Global optimum guarantee** |
| **Duration** | Minutes per montage | Minutes to hours | Minutes to hours |
| **Output** | TI field distributions | Optimal positions | All results + best montage |
| **Use Case** | Test known configurations | Find optimal positions | Find globally optimal montage |

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

