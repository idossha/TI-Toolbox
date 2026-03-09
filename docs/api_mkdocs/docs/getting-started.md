# Getting Started

This guide covers the core APIs you'll interact with most frequently.

## Initialization

Every TI-Toolbox session starts with logging setup and path management:

```python
from tit import setup_logging, add_file_handler, get_path_manager

# Configure logging (file-only by default, no terminal output)
setup_logging("INFO")

# Initialize the path manager singleton (BIDS-compliant paths)
pm = get_path_manager("/data/my_project", "001")

# Access BIDS paths directly
mesh_path = pm.get_head_mesh()          # -> .../derivatives/SimNIBS/sub-001/m2m_001/
sims_path = pm.simulations("001")       # -> .../derivatives/SimNIBS/sub-001/Simulations/
```

## Running Simulations

### Configure and Run

```python
from tit.sim import (
    SimulationConfig, ElectrodeConfig, IntensityConfig,
    ConductivityType, run_simulation, load_montages,
)

# Load montages from the project's montage_list.json
montages = load_montages(
    montage_names=["motor_cortex"],
    project_dir="/data/my_project",
    eeg_net="GSN-HydroCel-185",
)

# Configure the simulation
config = SimulationConfig(
    subject_id="001",
    project_dir="/data/my_project",
    conductivity_type=ConductivityType.SCALAR,
    intensities=IntensityConfig(values=[1.0, 1.0]),
    electrode=ElectrodeConfig(
        shape="ellipse",
        dimensions=[8.0, 8.0],
        gel_thickness=4.0,
    ),
)

# Run (auto-detects TI vs mTI based on number of electrode pairs)
results = run_simulation(config, montages)
```

### Simulation Types

- **TI (2-pair)**: Standard temporal interference with 2 electrode pairs
- **mTI (4+ pairs)**: Multi-channel TI with N electrode pairs (binary-tree combination)

Mode is auto-detected from the montage: 2 pairs -> TI, 4+ pairs -> mTI.

## Analyzing Results

```python
from tit.analyzer import Analyzer

# Spherical ROI analysis
analyzer = Analyzer(subject_id="001", simulation="motor_cortex", space="mesh")
result = analyzer.analyze_sphere(
    center=(-42, -20, 55),
    radius=10,
    coordinate_space="MNI",
    visualize=True,
)

# Access metrics
print(f"ROI Mean:     {result.roi_mean:.4f} V/m")
print(f"ROI Max:      {result.roi_max:.4f} V/m")
print(f"Focality:     {result.roi_focality:.2f}")
print(f"GM Mean:      {result.gm_mean:.4f} V/m")
print(f"N elements:   {result.n_elements}")

# Cortical atlas ROI analysis
result = analyzer.analyze_cortex(atlas="DK40", region="precentral-lh")
```

### Group Analysis

```python
from tit.analyzer import run_group_analysis

group_result = run_group_analysis(
    subject_ids=["001", "002", "003"],
    simulation="motor_cortex",
    space="mesh",
    analysis_type="spherical",
    center=(-42, -20, 55),
    radius=10,
    coordinate_space="MNI",
    visualize=True,
)

# group_result.subject_results: dict of per-subject AnalysisResult
# group_result.summary_csv_path: path to group_summary.csv
# group_result.comparison_plot_path: path to comparison bar chart PDF
```

## Optimization

### Flex-Search (Differential Evolution)

```python
from tit.opt import FlexConfig, FlexElectrodeConfig, SphericalROI, run_flex_search

config = FlexConfig(
    subject_id="001",
    project_dir="/data/my_project",
    goal="mean",              # "mean", "max", or "focality"
    postproc="max_TI",        # "max_TI", "dir_TI_normal", "dir_TI_tangential"
    current_mA=1.0,
    electrode=FlexElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
    roi=SphericalROI(center=(-42, -20, 55), radius=10, use_mni=True),
    eeg_net="GSN-HydroCel-185",
    n_multistart=3,
)

result = run_flex_search(config)
print(f"Best value: {result.best_value}")
print(f"Output: {result.output_folder}")
```

### Exhaustive Search

```python
from tit.opt import ExConfig, PoolElectrodes, run_ex_search

config = ExConfig(
    subject_id="001",
    project_dir="/data/my_project",
    leadfield_hdf="/path/to/leadfield.hdf5",
    roi_name="motor_roi",
    electrodes=PoolElectrodes(pool=["C3", "C4", "F3", "F4", "P3", "P4"]),
    eeg_net="GSN-HydroCel-185",
)

result = run_ex_search(config)
print(f"Combinations tested: {result.n_combinations}")
print(f"Results CSV: {result.results_csv}")
```

## Statistical Testing

```python
from tit.stats import (
    GroupComparisonConfig, GroupSubject,
    run_group_comparison, load_group_subjects,
)

# Load subjects from CSV
subjects = load_group_subjects("/data/subjects.csv")

config = GroupComparisonConfig(
    project_dir="/data/my_project",
    analysis_name="responder_comparison",
    subjects=subjects,
    test_type="unpaired",
    n_permutations=5000,
    alpha=0.05,
    cluster_threshold=0.05,
)

result = run_group_comparison(config)
print(f"Significant clusters: {result.n_clusters}")
print(f"Output: {result.output_dir}")
```

## Preprocessing

```python
from tit.pre import run_pipeline

exit_code = run_pipeline(
    project_dir="/data/my_project",
    subject_ids=["001", "002"],
    convert_dicom=True,
    run_recon=True,
    parallel_recon=True,
    parallel_cores=4,
    create_m2m=True,
    run_tissue_analysis=True,
)
```

## Key Concepts

### BIDS Compliance
All paths are managed by `PathManager`, which enforces a BIDS-compliant directory structure. You never construct paths manually.

### Field Types
- **TI_max**: Maximum TI envelope magnitude (scalar field)
- **TI_normal**: TI field component normal to the cortical surface
- **mTI_max**: Multi-channel TI maximum envelope (from binary-tree combination)

### Coordinate Spaces
- **Subject space**: Native coordinates aligned to the individual's head mesh
- **MNI space**: Standard MNI152 coordinates (transformed via SimNIBS)

### Analysis Spaces
- **Mesh** (`space="mesh"`): Surface-based analysis on the cortical mesh (weighted by node areas)
- **Voxel** (`space="voxel"`): Volume-based analysis on NIfTI data (weighted by voxel volumes)
