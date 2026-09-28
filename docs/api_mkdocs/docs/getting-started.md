# Getting Started

This guide covers the core APIs you'll interact with most frequently.

## Setup

Start the container using the [installation guide](https://idossha.github.io/TI-Toolbox/installation/).
The desktop app and browser interface both offer **Notebooks**, using the image's
**SimNIBS + TI-Toolbox** Python kernel. Open the supplied example to work with your project.
For standalone scripts inside the container, run `simnibs_python my_script.py`.

Use the container-visible project path when initializing a script:

```python
from tit import get_path_manager, setup_logging
from tit.sim import SimulationConfig, run_simulation

pm = get_path_manager("/mnt/project")  # replace with your mounted project path
setup_logging()
```

The launcher sets the project environment for the server and its notebook kernel. Explicit
initialization makes scripts portable to other container sessions.

## Running Simulations

### Configure and Run

```python
from tit.sim import (
    SimulationConfig, Montage,
    run_simulation, load_montages,
)

# Load montages from the project's montage_list.json
montages = load_montages(
    montage_names=["motor_cortex"],
    eeg_net="GSN-HydroCel-185",
)

# Configure the simulation (montages are part of the config)
config = SimulationConfig(
    subject_id="001",
    montages=montages,
    conductivity="scalar",
    intensities=[1.0, 1.0],
    electrode_shape="ellipse",
    electrode_dimensions=[8.0, 8.0],
    gel_thickness=4.0,
)

# Run (auto-detects TI vs mTI based on number of electrode pairs)
results = run_simulation(config)
```

### Simulation Types

- **TI (2-pair)**: Standard temporal interference with 2 electrode pairs
- **mTI (4+ even pairs)**: Multi-channel TI with N electrode pairs (binary-tree combination)

Mode is auto-detected from the montage: 2 pairs -> TI, 4+ even pairs -> mTI.

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
from tit.opt import FlexConfig, run_flex_search

config = FlexConfig(
    subject_id="001",
    goal="mean",              # "mean", "max", or "focality"
    postproc="max_TI",        # "max_TI", "dir_TI_normal", "dir_TI_tangential"
    current_mA=1.0,
    electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
    roi=FlexConfig.SphericalROI(x=-42, y=-20, z=55, radius=10, use_mni=True),
    eeg_net="GSN-HydroCel-185",
    n_multistart=3,
)

result = run_flex_search(config)
print(f"Best value: {result.best_value}")
print(f"Output: {result.output_folder}")
```

### Exhaustive Search

```python
from tit.opt import ExConfig, run_ex_search

config = ExConfig(
    subject_id="001",
    leadfield_hdf="/path/to/leadfield.hdf5",
    roi_name="motor_roi",
    electrodes=ExConfig.PoolElectrodes(electrodes=["C3", "C4", "F3", "F4", "P3", "P4"]),
)

result = run_ex_search(config)
print(f"Combinations tested: {result.n_combinations}")
print(f"Results CSV: {result.results_csv}")
```

## Statistical Testing

```python
from tit.stats import GroupComparisonConfig, run_group_comparison

# Load subjects from CSV (classmethod on GroupComparisonConfig)
subjects = GroupComparisonConfig.load_subjects("/data/subjects.csv")

config = GroupComparisonConfig(
    analysis_name="responder_comparison",
    subjects=subjects,
    test_type="unpaired",
    n_permutations=5000,
    alpha=0.05,
    cluster_threshold=0.05,
)

result = run_group_comparison(config)
print(f"Significant clusters: {result.n_significant_clusters}")
print(f"Output: {result.output_dir}")
```

## Preprocessing

```python
from tit.pre import run_pipeline

exit_code = run_pipeline(
    subject_ids=["001", "002"],
    convert_dicom=True,
    run_fastsurfer=True,
    fastsurfer_threads=4,
    create_m2m=True,
    run_tissue_analysis=True,
)
```

### Individual Steps

Each preprocessing step can also be called independently:

```python
from tit.pre import (
    run_dicom_to_nifti,
    run_fastsurfer,
    run_charm,
    run_tissue_analysis,
    run_qsiprep,
    run_qsirecon,
    extract_dti_tensor,
    discover_subjects,
    check_m2m_exists,
)

# Discover subjects from a BIDS project
import logging

project = "/path/to/bids_project"
logger = logging.getLogger("preprocessing")
subjects = discover_subjects(project)

# Check if head mesh already exists
if not check_m2m_exists(project, "001"):
    run_charm(project, "001", logger=logger)
```

## Report Generation

TI-Toolbox writes one self-contained HTML report per pipeline run. There are five kinds:
SimNIBS's own charm report (copied from `m2m_<id>/charm_report.html` when charm finishes), and
DTI QC, simulator, flex-search and ex-search reports, which the pipelines write themselves when
they finish. There is no report object to build by hand: each generator reads what its run wrote,
and rebuilds a report from the command line (inside the container):

```bash
simnibs_python -m tit.reporting.generators.dti_qc      /mnt/project 001                 [--out DIR]
simnibs_python -m tit.reporting.generators.simulation  /mnt/project 001 motor_cortex    [--out DIR]
simnibs_python -m tit.reporting.generators.flex_search /mnt/project 001 <run folder>    [--out DIR]
simnibs_python -m tit.reporting.generators.ex_search   /mnt/project 001 <run name>      [--out DIR]
```

or from Python:

```python
from tit.reporting.generators.simulation import create_simulation_report

path = create_simulation_report("/mnt/project", "001", "motor_cortex")
```

A simulator report opens with the grey-matter envelope (99.9th percentile, median and where its
maximum is), the montage on the EEG cap with its dose, the conductivity model and the envelope in
three planes through the hot spot. Only the DTI QC report has checks; each shows its role (gate,
software check, advisory, reported) and citation, and the rules are in
`tit.reporting.qc_rules.RULES`.

## Mesh and NIfTI Tools

Standalone utilities for working with simulation outputs:

```python
from tit.tools.mesh2nii import convert_mesh_dir
from tit.tools.montage_visualizer import visualize_montage

# Convert all meshes in a directory to NIfTI (subject + MNI space)
convert_mesh_dir(
    mesh_dir="/data/sim_output/TI/mesh",
    output_dir="/data/sim_output/TI/niftis",
    m2m_dir="/data/derivatives/SimNIBS/sub-001/m2m_001",
)

# Visualize electrode montage on the scalp
visualize_montage(
    montage_name="motor_cortex",
    electrode_pairs=[["E030", "E020"], ["E095", "E070"]],
    eeg_net="GSN-HydroCel-185",
    output_dir="/data/output/montage_imgs",
    sim_mode="U",  # "U" for TI, "M" for mTI
)
```

## Key Concepts

### BIDS Compliance
All paths are managed by `PathManager`, which enforces a BIDS-compliant directory structure. You never construct paths manually.

### Field Types
- **TI_max**: Maximum TI envelope magnitude (2-pair simulations)
- **TI_normal**: TI field component normal to the cortical surface
- **mTI_max**: Multi-channel TI maximum envelope (4+ even-pair mTI simulations, from binary-tree combination)

### Coordinate Spaces
- **Subject space**: Native coordinates aligned to the individual's head mesh
- **MNI space**: Standard MNI152 coordinates (transformed via SimNIBS)

### Analysis Spaces
- **Mesh** (`space="mesh"`): Surface-based analysis on the cortical mesh (weighted by node areas)
- **Voxel** (`space="voxel"`): Volume-based analysis on NIfTI data (weighted by voxel volumes)
