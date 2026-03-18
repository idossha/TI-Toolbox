---
layout: wiki
title: Scripting
permalink: /wiki/scripting/
---

The TI-Toolbox allows **Python scripting**: Import `tit` modules directly and build custom pipelines with full API access

## Python Scripting API

All tools can be used as a Python library by importing `tit` modules directly. Example scripts for each module are available in the `scripts/` directory. A complete end-to-end pipeline is in `scripts/pipeline.py`.

### Setup

Just import -- logging and path resolution are automatic. No initialization call is needed.

```python
from tit.sim import SimulationConfig, run_simulation
```


### Preprocessing

```python
from tit.pre import run_pipeline

run_pipeline(
    subject_ids=["101", "102"],
    convert_dicom=True,
    run_recon=True,
    create_m2m=True,
    parallel_recon=True,
    run_subcortical_segmentations=True,
)
```

See also: `scripts/preprocess.py`

### Leadfield Generation

```python
from tit.opt.leadfield import LeadfieldGenerator

lfg = LeadfieldGenerator(subject_id="101", electrode_cap="EEG10-20_Okamoto_2004")
lf_path = lfg.generate()
```

See also: `scripts/leadfield.py`

### Flex Search (Differential Evolution Optimization)

```python
from tit.opt import FlexConfig, FlexElectrodeConfig, SphericalROI, run_flex_search
from tit.opt.config import OptGoal, FieldPostproc

config = FlexConfig(
    subject_id="101",
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


### Ex-Search (Exhaustive Leadfield Optimization)

```python
from tit.opt import ExConfig, ExCurrentConfig, PoolElectrodes, BucketElectrodes
from tit.opt.ex import run_ex_search

# Pooled mode: all electrodes can go to any channel
config = ExConfig(
    subject_id="101",
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

See also: `scripts/optimizer.py`

### Simulation

```python
from tit.sim import (
    SimulationConfig, Montage, Montage.Mode,
    run_simulation, load_montages,
)

# Load pre-defined montages from the project's montage file
montages = load_montages(
    montage_names=["L_Insula"],
    eeg_net="GSN-HydroCel-185.csv",
)

# Or define montages manually
montages = [
    Montage(
        name="montage1",
        mode=Montage.Mode.NET,
        electrode_pairs=[("E1", "E2"), ("E3", "E4")],
        eeg_net="GSN-HydroCel-256",
    ),
]

config = SimulationConfig(
    subject_id="101",
    montages=montages,
    conductivity="scalar",
    intensities=[1.0, 1.0],
    electrode_shape="ellipse",
    electrode_dimensions=[8.0, 8.0],
    gel_thickness=4.0,
    rubber_thickness=2.0,
)

run_simulation(config)
```

See also: `scripts/simulator.py`

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

See also: `scripts/analyzer.py`

### Cluster-Based Permutation Testing

```python
from tit.stats import (
    run_group_comparison,
    run_correlation,
    GroupComparisonConfig,
    CorrelationConfig,
    load_group_subjects,
    load_correlation_subjects,
)

# Group comparison
subjects = load_group_subjects("subjects_classification.csv")
config = GroupComparisonConfig(
    analysis_name="responders_vs_nonresponders",
    subjects=subjects,
    n_permutations=1000,
)
result = run_group_comparison(config)

# Correlation analysis
subjects = load_correlation_subjects("subjects_correlation.csv")
config = CorrelationConfig(
    analysis_name="dose_response",
    subjects=subjects,
    correlation_type="pearson",
    n_permutations=1000,
)
result = run_correlation(config)
```

See also: `scripts/cluster_permutation.py`
