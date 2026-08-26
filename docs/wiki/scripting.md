---
layout: wiki
title: Scripting
permalink: /wiki/scripting/
---

The TI-Toolbox exposes the same functionality available in the GUI as a **Python scripting API**. Import `tit` modules directly to build custom, reproducible pipelines.

## Why Script?

| GUI | Scripting |
|-----|-----------|
| Interactive, visual feedback | Reproducible, version-controlled |
| One subject at a time | Batch processing across subjects |
| Fixed parameter sets | Programmatic parameter sweeps |
| Point-and-click | Integrates with your own analysis code |

Both approaches call the same underlying code. Everything you do in the GUI can be done in a script.

## Getting Started

All scripting happens **inside the SimNIBS container**. Open a terminal into the running container:

```bash
docker exec -it simnibs_container bash
```

Your project data is mounted at `/mnt/<project_name>/`. The `tit` package and all SimNIBS dependencies are pre-installed — just import and go.

### Quick import check

```python
simnibs_python -c "from tit.sim import SimulationConfig; print('OK')"
```

## Development Environments

Three ways to write and run scripts inside the container:

### JupyterLab

Best for interactive exploration, demos, and prototyping.

```bash
# Inside the container shell:
NOTEBOOK
```

Then open [http://localhost:8888](http://localhost:8888) in your browser. No token or password required.

Select the **"SimNIBS + TI-Toolbox"** kernel (top-right of the notebook) for full autocompletion and signature help.

### Neovim

The container ships with Neovim pre-configured with LSP autocompletion, signature help, hover docs, and go-to-definition for `tit` and `simnibs` code.

```bash
nvim my_script.py
```

**Key bindings (active in Python files):**

| Key | Action |
|-----|--------|
| `gd` | Go to definition |
| `gr` | List references |
| `K` | Hover documentation |
| `<C-k>` (insert mode) | Signature help |
| `<leader>rn` | Rename symbol |
| `<Tab>` / `<S-Tab>` | Cycle completions |
| `<CR>` | Confirm completion |
| `<C-Space>` | Trigger completion manually |

### Plain Scripts

Write a `.py` file and run it directly:

```bash
simnibs_python my_script.py
```

All `tit` modules auto-initialize logging and path resolution on import. No boilerplate needed.

## Import Quick Reference

```python
# Core
from tit import get_path_manager

# Simulation
from tit.sim import SimulationConfig, Montage, run_simulation, load_montages

# Optimization
from tit.opt import FlexConfig, run_flex_search
from tit.opt import ExConfig, run_ex_search

# Analysis
from tit.analyzer import Analyzer, run_group_analysis

# Statistics
from tit.stats import run_group_comparison, GroupComparisonConfig

# Preprocessing
from tit.pre import run_pipeline
```

## API Reference

### Preprocessing

```python
from tit.pre import run_pipeline

run_pipeline(
    subject_ids=["101", "102"],
    convert_dicom=True,       # DICOM -> NIfTI
    run_recon=True,           # FreeSurfer recon-all
    create_m2m=True,          # SimNIBS CHARM head mesh
    parallel_recon=True,      # Run recon-all in parallel
)
```

See also: `scripts/preprocess.py`

### Simulation

```python
from tit.sim import SimulationConfig, Montage, run_simulation, load_montages

# Option A: Load montages from the project's montage.json
montages = load_montages(
    montage_names=["L_Insula"],
    eeg_net="GSN-HydroCel-185.csv",
)

# Option B: Define a montage explicitly
montages = [
    Montage(
        name="Custom_Motor",
        mode=Montage.Mode.NET,
        electrode_pairs=[("E010", "E011"), ("E012", "E013")],
        eeg_net="GSN-HydroCel-185.csv",
    ),
]

config = SimulationConfig(
    subject_id="101",
    montages=montages,
    conductivity="scalar",        # "scalar", "vn", "dir", or "mc"
    intensities=[1.0, 1.0],      # mA per electrode pair
    electrode_shape="ellipse",    # "ellipse" or "rect"
    electrode_dimensions=[8.0, 8.0],  # mm
    gel_thickness=4.0,            # mm
    rubber_thickness=2.0,         # mm
    output_fields=["TI_max"],     # "TI_max", "TI_avg", "hf_peak", "hf_sar"
)

run_simulation(config)
```

`output_fields` selects which volume-mesh fields the simulation computes and writes. It defaults to `["TI_max"]` only — `TI_avg` and the safety fields (`hf_peak`, `hf_sar`) are off unless explicitly requested.

**Simulation types** (auto-detected from montage):
- **TI** (2 electrode pairs): Standard temporal interference
- **mTI** (4+ electrode pairs): Multi-channel TI with higher focality

**Conductivity models:**
- `"scalar"` — Isotropic, fixed per tissue type (default)
- `"vn"` — Volume-normalized anisotropic (requires DTI)
- `"dir"` — Directly-mapped anisotropic (requires DTI)
- `"mc"` — Mean-conductivity anisotropic (requires DTI)

See also: `scripts/simulator.py`

### Flex Search (Differential Evolution Optimization)

Finds optimal electrode placements by searching over the full scalp surface.

```python
from tit.opt import FlexConfig, run_flex_search

config = FlexConfig(
    subject_id="101",
    goal="mean",                  # "mean", "max", "focality", or "focality_tf"
    postproc="max_TI",            # "max_TI", "dir_TI_normal", "dir_TI_tangential"
    current_mA=2.0,
    electrode=FlexConfig.ElectrodeConfig(
        shape="ellipse",
        dimensions=[8.0, 8.0],
        gel_thickness=4.0,
    ),
    roi=FlexConfig.SphericalROI(
        x=-35.0, y=5.0, z=5.0,
        radius=10.0,
        use_mni=True,
    ),
    n_multistart=3,               # Independent optimization runs
    min_electrode_distance=5.0,   # mm
    skin_region_margin_mm=0.0,    # Signed valid-skin-region margin in mm
    avoid_landmark_regions=True,  # Keep eye/ear guards when expanding
)

result = run_flex_search(config)
print(f"Best value: {result.best_value:.4f}")
print(f"Output:     {result.output_folder}")
```

**ROI types:**
- `FlexConfig.SphericalROI(x, y, z, radius, use_mni, volumetric, tissues)` — Sphere at MNI or subject coordinates. `volumetric=True` evaluates on volume tetrahedra instead of the cortical surface (for deep/subcortical targets); `tissues` (`"GM"`, `"WM"`, or `"both"`) then selects which compartments are included.
- `FlexConfig.AtlasROI(atlas_path, label, hemisphere)` — Cortical surface region from a FreeSurfer `.annot` atlas.
- `FlexConfig.SubcorticalROI(atlas_path, label, tissues, atlas_space)` — Volumetric subcortical region from a volumetric atlas. `atlas_space` (`"subject"` or `"mni"`) is the space of the atlas file.

`x`/`y`/`z`/`radius` (`SphericalROI`) and `atlas_path`/`label`/`hemisphere` (`AtlasROI`) each accept either a single value or a parallel list of values — passing lists unions multiple regions into one combined target.

See also: `scripts/flex.py`

### Exhaustive Search

Evaluates all electrode combinations from a candidate pool. Requires a pre-computed leadfield.

```python
from tit.opt import ExConfig, run_ex_search

# Pooled mode: all electrodes can go to any channel position
config = ExConfig(
    subject_id="101",
    leadfield_hdf="101_leadfield_EEG10-20_Okamoto_2004.hdf5",
    roi_name="L-Insula.csv",
    electrodes=ExConfig.PoolElectrodes(
        electrodes=["Fp1", "Fp2", "C3", "C4", "Cz", "Pz", "T7", "T8"]
    ),
    total_current=2.0,
    current_step=0.2,
    channel_limit=1.2,
)

# Bucketed mode: electrodes pre-assigned to specific channel positions
config = ExConfig(
    subject_id="101",
    leadfield_hdf="101_leadfield_EEG10-20_Okamoto_2004.hdf5",
    roi_name="L-Insula.csv",
    electrodes=ExConfig.BucketElectrodes(
        e1_plus=["Fp1", "Fp2"],
        e1_minus=["Pz", "Oz"],
        e2_plus=["C3", "F3"],
        e2_minus=["C4", "F4"],
    ),
    total_current=2.0,
    current_step=0.5,
)

result = run_ex_search(config)
```

`roi_name` is the single-ROI CSV filename (the `.csv` suffix is appended automatically if missing); it also always supplies the metric-key prefix and output-directory label, even when `roi_names`/`roi_atlas` are used. To union multiple spherical ROIs into one combined target, pass `roi_names` (a list of CSV filenames whose spheres are OR-folded together) — when given, it replaces `roi_name` for the actual centers used, so include `roi_name`'s own file in the list if you want it counted too. `roi_atlas` (a list of `ExConfig.AtlasROI(atlas_path, label)` volumetric atlas/mask ROIs) unions in further, non-spherical regions:

```python
config = ExConfig(
    subject_id="101",
    leadfield_hdf="101_leadfield_EEG10-20_Okamoto_2004.hdf5",
    roi_name="L-Insula.csv",
    roi_names=["L-Insula.csv", "R-Insula.csv"],  # union of spherical centers
    roi_coordinate_space="subject",  # space of roi_name/roi_names centers: "subject" (default) or "mni"
    electrodes=ExConfig.PoolElectrodes(
        electrodes=["Fp1", "Fp2", "C3", "C4", "Cz", "Pz", "T7", "T8"]
    ),
    total_current=2.0,
    current_step=0.2,
)

# roi_names=[] means "no spherical centers at all" -- for a purely atlas-driven ROI
config = ExConfig(
    subject_id="101",
    leadfield_hdf="101_leadfield_EEG10-20_Okamoto_2004.hdf5",
    roi_name="L-Insula.csv",
    roi_names=[],
    roi_atlas=[ExConfig.AtlasROI(atlas_path="aseg.mgz", label=17)],  # label=None treats the file as a binary mask
    electrodes=ExConfig.PoolElectrodes(
        electrodes=["Fp1", "Fp2", "C3", "C4", "Cz", "Pz", "T7", "T8"]
    ),
    total_current=2.0,
    current_step=0.2,
)
```

`roi_atlas` is always subject space, regardless of `roi_coordinate_space`.

See also: `scripts/ex.py`

### Analysis

Extract field statistics from simulation results.

```python
from tit.analyzer import Analyzer, run_group_analysis

# Create an analyzer for a completed simulation
analyzer = Analyzer(
    subject_id="101",
    simulation="L_Insula",   # Must match the montage name
    space="voxel",           # "voxel" or "mesh"
)

# Spherical ROI analysis
result = analyzer.analyze_sphere(
    center=(-35.0, 5.0, 5.0),
    radius=10.0,
    coordinate_space="MNI",  # or "subject"
    visualize=True,
)
print(f"Mean: {result.mean:.4f} V/m")
print(f"Max:  {result.max:.4f} V/m")

# Cortical atlas ROI analysis (requires FreeSurfer parcellation)
result = analyzer.analyze_cortex(
    atlas="DK40",
    region="superiorfrontal",
    visualize=True,
)
```

#### Group Analysis

```python
group_result = run_group_analysis(
    subject_ids=["101", "102", "103"],
    simulation="L_Insula",
    space="voxel",
    analysis_type="spherical",
    center=(-35.0, 5.0, 5.0),
    radius=10.0,
    coordinate_space="MNI",
    visualize=True,
)
```

See also: `scripts/analyzer.py`

### Statistical Testing

Cluster-based permutation testing for group comparisons.

```python
from tit.stats import run_group_comparison, GroupComparisonConfig

subjects = GroupComparisonConfig.load_subjects("path/to/subjects.csv")

config = GroupComparisonConfig(
    analysis_name="active_vs_sham",
    subjects=subjects,
    test_type=GroupComparisonConfig.TestType.UNPAIRED,
    alternative=GroupComparisonConfig.Alternative.TWO_SIDED,
    cluster_stat=GroupComparisonConfig.ClusterStat.MASS,
    n_permutations=1000,
    tissue_type=GroupComparisonConfig.TissueType.GREY,
)
result = run_group_comparison(config)

print(f"Significant clusters: {result.n_significant_clusters}")
print(f"Significant voxels:   {result.n_significant_voxels}")
print(f"Output:               {result.output_dir}")
```

See also: `scripts/cluster_permutation.py`

### Full End-to-End Pipeline

```python
from tit.pre import run_pipeline
from tit.opt import FlexConfig, run_flex_search
from tit.sim import SimulationConfig, run_simulation, load_montages
from tit.analyzer import Analyzer

SUBJECTS = ["ernie"]
EEG_NET = "GSN-HydroCel-185.csv"

# 1. Preprocessing
run_pipeline(subject_ids=SUBJECTS, create_m2m=True)

# 2. Optimization
for subj in SUBJECTS:
    config = FlexConfig(
        subject_id=subj,
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(x=-35, y=5, z=5, radius=10.0, use_mni=True),
        n_multistart=3,
    )
    run_flex_search(config)

# 3. Simulation
montages = load_montages(montage_names=["L_Insula"], eeg_net=EEG_NET)
for subj in SUBJECTS:
    config = SimulationConfig(
        subject_id=subj,
        montages=montages,
        conductivity="scalar",
        intensities=[1.0, 1.0],
    )
    run_simulation(config)

# 4. Analysis
for subj in SUBJECTS:
    analyzer = Analyzer(subject_id=subj, simulation="L_Insula", space="voxel")
    result = analyzer.analyze_sphere(
        center=(-35.0, 5.0, 5.0),
        radius=10.0,
        coordinate_space="MNI",
        visualize=True,
    )
```

See also: `scripts/pipeline.py`

## JSON Config Interface

Each module can also be invoked as a subprocess accepting a JSON config file. This is how the GUI drives computation:

```bash
simnibs_python -m tit.sim        config.json
simnibs_python -m tit.opt.flex   config.json
simnibs_python -m tit.opt.ex     config.json
simnibs_python -m tit.opt.mex    config.json
simnibs_python -m tit.analyzer   config.json
simnibs_python -m tit.stats      config.json
simnibs_python -m tit.pre        config.json
```

`tit.opt.mex` runs multipolar (4-pair, 8-electrode) exhaustive search, consuming `MExConfig`. See [mTI]({{ site.baseurl }}/wiki/mti/) for the full workflow.

Config files are generated programmatically via `tit.config_io.write_config_json()`.

## AI Coding Agents

Full guide: [AI Assistant]({{ site.baseurl }}/wiki/ai-assistant/).

If you write scripts with an AI assistant (Claude Code, Codex, Cursor, ...), install the [TI-Toolbox agent plugin](https://github.com/idossha/TI-Toolbox/tree/main/agent-plugin). It gives the assistant this wiki, the `tit` source and a read-only view of your project directory through an MCP server, so it stops guessing API fields. In Claude Code: `/plugin marketplace add idossha/TI-Toolbox` then `/plugin install ti-toolbox@ti-toolbox`.
