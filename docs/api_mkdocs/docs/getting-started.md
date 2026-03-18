# Getting Started

This guide covers the core APIs you'll interact with most frequently.

## Initialization

Every TI-Toolbox session starts with logging setup and path management:

```python
from tit import init, add_file_handler, get_path_manager

# Configure logging with terminal output (or use setup_logging for file-only)
init("INFO")

# Initialize the path manager singleton (BIDS-compliant paths)
pm = get_path_manager("/data/my_project")

# Access BIDS paths directly
mesh_path = pm.m2m("001")              # -> .../derivatives/SimNIBS/sub-001/m2m_001/
sims_path = pm.simulations("001")      # -> .../derivatives/SimNIBS/sub-001/Simulations/
```

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
    project_dir="/data/my_project",
    eeg_net="GSN-HydroCel-185",
)

# Configure the simulation (montages are part of the config)
config = SimulationConfig(
    subject_id="001",
    project_dir="/data/my_project",
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
from tit.opt import FlexConfig, run_flex_search

config = FlexConfig(
    subject_id="001",
    project_dir="/data/my_project",
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
    project_dir="/data/my_project",
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
    project_dir="/data/my_project",
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

### Individual Steps

Each preprocessing step can also be called independently:

```python
from tit.pre import (
    run_dicom_to_nifti,
    run_recon_all,
    run_charm,
    run_tissue_analysis,
    run_subcortical_segmentations,
    run_qsiprep,
    run_qsirecon,
    extract_dti_tensor,
    discover_subjects,
    check_m2m_exists,
)

# Discover subjects from sourcedata
subjects = discover_subjects("/data/my_project")

# Check if head mesh already exists
if not check_m2m_exists("/data/my_project", "001"):
    run_charm("/data/my_project", "001", logger=my_logger)
```

## Report Generation

TI-Toolbox generates interactive HTML reports for simulations, flex-search results,
and preprocessing runs.

### Simulation Reports

```python
from tit.reporting import SimulationReportGenerator

report = SimulationReportGenerator(
    project_dir="/data/my_project",
    simulation_session_id="motor_cortex",
    subject_id="001",
)
report.add_simulation_parameters(
    conductivity_type="scalar",
    simulation_mode="TI",
    eeg_net="GSN-HydroCel-185",
    intensity_ch1=1.0,
    intensity_ch2=1.0,
)
report.add_montage(
    montage_name="motor_cortex",
    electrode_pairs=[("C3", "C4"), ("F3", "F4")],
    montage_type="TI",
)
output_path = report.generate()
print(f"Report: {output_path}")
```

### Flex-Search Reports

```python
from tit.reporting import create_flex_search_report

# Generate from optimization data dict
output_path = create_flex_search_report(
    project_dir="/data/my_project",
    subject_id="001",
    data=optimization_data,  # dict with optimization results
    output_path="/data/my_project/derivatives/ti-toolbox/reports/flex_report.html",
)
```

### Preprocessing Reports

```python
from tit.reporting import create_preprocessing_report

output_path = create_preprocessing_report(
    project_dir="/data/my_project",
    subject_id="001",
    processing_steps=[],  # auto-populated if auto_scan=True
    output_path=None,     # auto-generates BIDS-compliant path
    auto_scan=True,
)
```

### Report Building Blocks (Reportlets)

Reports are assembled from reusable reportlets:

```python
from tit.reporting import (
    ReportAssembler,
    ReportMetadata,
    MetadataReportlet,
    ImageReportlet,
    TableReportlet,
    ConductivityTableReportlet,
    SummaryCardsReportlet,
    MethodsBoilerplateReportlet,
    TIToolboxReferencesReportlet,
)

# Create a custom report
metadata = ReportMetadata(title="My Analysis", subject_id="001")
assembler = ReportAssembler(metadata=metadata, title="Custom Report")

section = assembler.add_section("results", "Results", description="Analysis output")
cards = SummaryCardsReportlet(title="Key Metrics")
cards.add_card(label="ROI Mean", value="0.152 V/m", color="#4CAF50")
section.add_reportlet(cards)

assembler.save("/data/output/report.html")
```

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
- **TI_Max**: Multi-channel TI maximum envelope (4-pair mTI simulations, from binary-tree combination)

### Coordinate Spaces
- **Subject space**: Native coordinates aligned to the individual's head mesh
- **MNI space**: Standard MNI152 coordinates (transformed via SimNIBS)

### Analysis Spaces
- **Mesh** (`space="mesh"`): Surface-based analysis on the cortical mesh (weighted by node areas)
- **Voxel** (`space="voxel"`): Volume-based analysis on NIfTI data (weighted by voxel volumes)
