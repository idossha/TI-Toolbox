---
layout: wiki
title: Scripting
permalink: /wiki/scripting/
---

The TI-Toolbox supports three complementary workflows for running tools:

- **Interactive mode**: Guided, prompt-based configuration -- ideal for exploration and first-time runs
- **Direct mode**: Fully specified command-line flags -- better for shell scripts and advanced control
- **Python scripting**: Import `tit` modules directly and build custom pipelines with full API access

## Interactive vs Direct Mode

### Interactive Mode

```bash
# Run command with no arguments for guided prompts
simulator
```

The CLI will guide you through:
- Subject selection
- Framework choice (montage/flex)
- EEG cap selection
- Montage configuration
- Parameter setup

### Direct Mode

```bash
# All parameters specified explicitly
simulator \
  --sub 101 \
  --framework montage \
  --eeg GSN-HydroCel-185.csv \
  --montages my_montage \
  --intensity 2.0
```

Mode selection is automatic:
- **No arguments** -> Interactive mode
- **Any arguments present** -> Direct mode

## Available Commands

| Command | Description | Interactive | Direct Examples |
|---------|-------------|-------------|---------|
| `pre_process` | Preprocessing pipeline | `pre_process` | `pre_process --subs 101 --run-recon --create-m2m` |
| `flex_search` | Electrode optimization | `flex_search` | `flex_search --subject 101 --roi-method spherical` |
| `create_leadfield` | Generate leadfield matrices | `create_leadfield` | `create_leadfield --sub 101 --eeg cap.csv` |
| `ex_search` | Leadfield-based optimization | `ex_search` | `ex_search --sub 101 --lf leadfield.hdf5 --pool` |
| `simulator` | Run TI simulations | `simulator` | `simulator --sub 101 --montages my_montage` |
| `analyzer` | Analyze single subject results | `analyzer` | `analyzer --sub 101 --sim montage --coordinates 0 0 0` |
| `group_analyzer` | Analyze multiple subjects | `group_analyzer` | `group_analyzer --subs 101,102 --sim montage` |
| `cluster_permutation` | Statistical analysis | `cluster_permutation` | `cluster_permutation --csv data.csv --name analysis` |
| `blender` | Create visualizations | `blender` | `blender --subject 101 --simulation montage` |

All commands support detailed help via the `-h` or `--help` flag:

```bash
simulator -h
analyzer --help
blender -h
```

---

## JSON Config Entry Points

Each major module can be invoked as a subprocess with a JSON config file. This is the pattern the GUI uses to run operations in separate processes:

```bash
simnibs_python -m tit.sim        config.json
simnibs_python -m tit.analyzer   config.json
simnibs_python -m tit.opt.flex   config.json
simnibs_python -m tit.opt.ex     config.json
simnibs_python -m tit.stats      config.json
simnibs_python -m tit.pre        config.json
```

Each `__main__.py` reads the JSON file, reconstructs typed config dataclasses, and calls the corresponding `run_*` function.

### Config Serialization (`tit/config_io.py`)

The `tit/config_io.py` module handles serialization of typed config dataclasses to JSON and back. It supports:

- **Enum fields** -- serialized as their `.value`
- **Nested dataclasses** -- recursively serialized
- **Union-typed fields** -- uses a `_type` discriminator to identify the concrete class (e.g., `SphericalROI`, `AtlasROI`, `LabelMontage`, `XYZMontage`)

```python
from tit.config_io import write_config_json, read_config_json

# Serialize a config dataclass to a temp JSON file
path = write_config_json(my_flex_config, prefix="flex")

# Read it back as a plain dict
data = read_config_json(path)
```

The `_type` discriminator pattern allows `__main__.py` entry points to reconstruct the correct dataclass variant from a plain JSON dict. For example, an ROI field in the JSON might look like:

```json
{
  "_type": "SphericalROI",
  "center": [-45.0, 0.0, 0.0],
  "radius": 5.0
}
```

### How the GUI Uses This

The GUI tabs build config dataclasses, serialize them via `write_config_json()`, then launch:

```
simnibs_python -m tit.<module> /tmp/flex_abc123.json
```

in a `QThread`. Stdout from the subprocess is captured by `BaseProcessThread` and displayed in the tab's console widget.

---

## Python Scripting API

All tools can be used as a Python library. Below is the API for each module with current signatures. A complete end-to-end example is available in `scripts/pipeline.py`.

### Setup

```python
from tit import setup_logging, add_stream_handler

setup_logging()
add_stream_handler("tit")  # optional: print logs to terminal
```

### Preprocessing

```python
from tit.pre import run_pipeline

run_pipeline(
    "/path/to/project",
    ["101", "102"],
    convert_dicom=True,
    run_recon=True,
    create_m2m=True,
    parallel_recon=True,
    run_subcortical_segmentations=True,
)
```

| Option | Description |
|--------|-------------|
| `convert_dicom` | Include DICOM-to-NIfTI conversion stage |
| `run_recon` | Run FreeSurfer recon-all |
| `create_m2m` | Create SimNIBS head model (also runs `subject_atlas`) |
| `parallel_recon` | Multiple subjects simultaneously, 1 core each |
| `run_tissue_analysis` | Run tissue segmentation analysis |
| `run_qsiprep` | Run QSIPrep DWI preprocessing via Docker |
| `run_qsirecon` | Run QSIRecon reconstruction via Docker |
| `extract_dti` | Extract DTI tensors for anisotropic conductivity |
| `run_subcortical_segmentations` | Thalamic nuclei and hippocampal subfield segmentations |

### Leadfield Generation

```python
from tit.opt.leadfield import LeadfieldGenerator

lfg = LeadfieldGenerator(subject_id="101", electrode_cap="EEG10-20_Okamoto_2004")
lf_path = lfg.generate()
```

### Flex Search (Differential Evolution Optimization)

```python
from tit.opt import FlexConfig, FlexElectrodeConfig, SphericalROI, run_flex_search
from tit.opt.config import OptGoal, FieldPostproc

config = FlexConfig(
    subject_id="101",
    project_dir="/path/to/project",
    goal=OptGoal.MEAN,              # "mean", "max", or "focality"
    postproc=FieldPostproc.MAX_TI,  # "max_TI", "dir_TI_normal", or "dir_TI_tangential"
    current_mA=8.0,
    electrode=FlexElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
    roi=SphericalROI(x=-31.3, y=24.0, z=-37.0, radius=10.0, use_mni=True),
    anisotropy_type="scalar",       # "scalar", "vn", "dir", or "mc"
    n_multistart=3,
)

result = run_flex_search(config)
print(result.success, result.best_value, result.output_folder)
```

`FlexConfig` validates parameters in `__post_init__`, including automatic string-to-enum coercion for `goal`, `postproc`, and `non_roi_method`, and validation that focality goal with `specific` non-ROI method requires a `non_roi` specification.

#### Reading the Output Manifest

```python
from tit.opt.flex.manifest import read_manifest

meta = read_manifest("/path/to/flex-search/run_001")
print(meta["goal"], meta["result"]["best_value"])
```

### Ex-Search (Exhaustive Leadfield Optimization)

```python
from tit.opt import ExConfig, ExCurrentConfig, PoolElectrodes, BucketElectrodes
from tit.opt.ex import run_ex_search

# Pooled mode: all electrodes can go to any channel
config = ExConfig(
    subject_id="101",
    project_dir="/path/to/project",
    leadfield_hdf="/path/to/leadfield.hdf5",
    roi_name="target_roi",
    electrodes=PoolElectrodes(electrodes=["Fp1", "Fp2", "C3", "C4", "Pz", "Oz"]),
    currents=ExCurrentConfig(total_current=2.0, current_step=0.5),
    roi_radius=3.0,
    eeg_net="EGI10-20_Okamoto_2004",
)

# Bucketed mode: electrodes pre-assigned to channels
config = ExConfig(
    subject_id="101",
    project_dir="/path/to/project",
    leadfield_hdf="/path/to/leadfield.hdf5",
    roi_name="target_roi",
    electrodes=BucketElectrodes(
        e1_plus=["Fp1", "Fp2"],
        e1_minus=["Pz", "Oz"],
        e2_plus=["C3", "F3"],
        e2_minus=["C4", "F4"],
    ),
    currents=ExCurrentConfig(total_current=2.0, current_step=0.5),
    roi_radius=3.0,
    eeg_net="EGI10-20_Okamoto_2004",
)

result = run_ex_search(config)
print(result.success, result.n_combinations, result.results_csv)
```

### Simulation

```python
from tit.sim import (
    SimulationConfig, ElectrodeConfig, IntensityConfig,
    ConductivityType, LabelMontage, run_simulation, load_montages,
)

# Load pre-defined montages from the project's montage file
montages = load_montages(
    montage_names=["L_Insula"],
    project_dir="/path/to/project",
    eeg_net="GSN-HydroCel-185.csv",
)

# Or define montages manually
montages = [
    LabelMontage(
        name="montage1",
        electrode_pairs=[("E1", "E2"), ("E3", "E4")],
        eeg_net="GSN-HydroCel-256",
    ),
]

config = SimulationConfig(
    subject_id="101",
    project_dir="/path/to/project",
    conductivity_type=ConductivityType.SCALAR,
    intensities=IntensityConfig(values=[1.0, 1.0]),
    electrode=ElectrodeConfig(
        shape="ellipse",
        dimensions=[8.0, 8.0],
        gel_thickness=4.0,
        rubber_thickness=2.0,
    ),
)

run_simulation(config, montages)
```

### Analyzer

```python
from tit.analyzer import Analyzer, run_group_analysis

# Single-subject analysis
analyzer = Analyzer(subject_id="101", simulation="montage1", space="mesh")

# Spherical ROI analysis
result = analyzer.analyze_sphere(
    center=(-31.3, 24.0, -37.0),
    radius=10.0,
    coordinate_space="subject",  # or "MNI"
    visualize=True,
)

# Cortical atlas ROI analysis
result = analyzer.analyze_cortex(
    atlas="DK40",
    region="lh.insula",
    visualize=True,
)

# Access typed result fields
print(result.roi_mean, result.roi_max, result.roi_focality)
```

#### Group Analysis

```python
result = run_group_analysis(
    subject_ids=["101", "102", "103"],
    simulation="montage1",
    space="mesh",
    analysis_type="spherical",
    center=(10, 20, 30),
    radius=5.0,
    coordinate_space="MNI",
    output_dir="/path/to/group/output",
)
```

### Cluster-Based Permutation Testing

```python
from tit.stats import (
    run_group_comparison,
    run_correlation,
    GroupComparisonConfig,
    CorrelationConfig,
    GroupSubject,
    CorrelationSubject,
    load_group_subjects,
    load_correlation_subjects,
)

# Group comparison
subjects = load_group_subjects("subjects_classification.csv")
config = GroupComparisonConfig(
    project_dir="/path/to/project",
    analysis_name="responders_vs_nonresponders",
    subjects=subjects,
    n_permutations=1000,
)
result = run_group_comparison(config)

# Correlation analysis
subjects = load_correlation_subjects("subjects_correlation.csv")
config = CorrelationConfig(
    project_dir="/path/to/project",
    analysis_name="dose_response",
    subjects=subjects,
    correlation_type="pearson",
    n_permutations=1000,
)
result = run_correlation(config)
```

The `run_group_comparison` and `run_correlation` functions are resolved lazily via `__getattr__` so that `import tit.stats` does not pull in nibabel or scipy at import time.

---

## Full Pipeline Example

See `scripts/pipeline.py` for a complete end-to-end script that chains preprocessing, leadfield generation, optimization (flex + ex), simulation, and analysis.
