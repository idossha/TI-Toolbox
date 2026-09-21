---
layout: wiki
title: Scripting
permalink: /wiki/scripting/
---

Every page of the app does its work by calling the `tit` Python API — it builds a config object,
serialises it to JSON and runs the same module you can run yourself. This page walks the app page
by page and shows, for each one, the call its **Run** button makes.

A runnable version of the same sequence is the
[example notebook]({{ site.baseurl }}/wiki/notebooks/#the-example-notebook).

## Where scripts run

Scripting happens **inside the container** — that is where SimNIBS and `tit` live. Your project is
mounted at `/mnt/<project_name>/` and everything is pre-installed.

**1. The Notebooks page, in the app.** Open it and start typing; the kernel is the container's
SimNIBS Python with your project mounted.

**2. `docker exec`**, from your own terminal:

```bash
tit launch --project ~/datasets/000 --status   # prints the container's name
docker exec -it ti-toolbox-<hash>-tit-1 bash
simnibs_python my_script.py
```

> Installing `tit` on your **host** (`pip install tit`) gives you the
> [`tit launch` launcher]({{ site.baseurl }}/installation/bash-cli/) and nothing else usable —
> the scripting API needs SimNIBS, which is in the image.

## The project

In the GUI you open a project. In code, `get_path_manager` does the same: it is the object that
knows where everything in a BIDS project lives, and every module uses it.

No data of your own yet? `tit.examples.fetch_ernie(project)` downloads both parts of the `ernie`
dataset (its raw T1/T2 and its finished `m2m_ernie` head model, ~1.1 GB, GPL-3.0) into the project
once and returns immediately when they are already there — the same call behind the Overview page's
**Add example data** button and `python -m tit.examples --project DIR`; `tit.examples.fetch(dataset,
part, project)` takes any [catalogue part id]({{ site.baseurl }}/wiki/example-data/), such as
`fetch("mni152", "headmodel", project)`:

```python
import os
from tit import get_path_manager
from tit.examples import fetch_ernie

PROJECT = os.environ.get("TIT_PROJECT_DIR") or "/path/to/your/project"
pm = get_path_manager(PROJECT)
fetch_ernie(PROJECT)
```

```python
from tit import get_path_manager
from tit.pre import discover_subjects

pm = get_path_manager("/mnt/000")
print(discover_subjects("/mnt/000"))
```

| Call | GUI equivalent |
|---|---|
| `get_path_manager(project_dir)` | Opening a project |
| `discover_subjects(project_dir)` | The subject list |
| `pm.m2m(sid)` | The head model of a subject |
| `pm.simulations(sid)` | The Simulator's results list |
| `pm.flex_search(sid)` / `pm.ex_search(sid)` | The Optimizer's results list |

## Pre-processing

In the GUI you tick the conversion and head-model boxes on the **Pre-processing** page and press
Run. Those tick boxes are the keyword arguments of `run_pipeline`.

```python
from tit.pre import run_pipeline, check_m2m_exists

if not check_m2m_exists("/mnt/000", "ernie"):
    run_pipeline(["ernie"], convert_dicom=True, create_m2m=True)
```

| Argument | GUI label | Default |
|---|---|---|
| `subject_ids` | Subject selection | required |
| `convert_dicom` | Convert DICOM to NIfTI | `False` |
| `create_m2m` | Create head model (charm) | `False` |
| `run_fastsurfer` | FastSurfer segmentation | `False` |
| `run_freesurfer` | FreeSurfer recon-all | `False` |
| `run_tissue_analysis` | Tissue analysis | `False` |
| `run_qsiprep` / `run_qsirecon` | DWI preprocessing / reconstruction | `False` |
| `extract_dti` | Extract DTI tensor | `False` |
| `skip_existing_outputs` | Skip completed steps | `False` |

## Optimizer — flex-search

In the GUI you fill the **Optimizer ▸ Flex** form — goal, current, electrode size, target ROI —
and press Run. That form is `FlexConfig`.

```python
from tit.opt import FlexConfig, run_flex_search

cfg = FlexConfig(
    subject_id="ernie",
    goal="mean",
    postproc="max_TI",
    current_mA=1.0,
    electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
    roi=FlexConfig.SphericalROI(x=-37.0, y=-21.0, z=58.0, radius=10.0, use_mni=True),
)
result = run_flex_search(cfg)
print(result.best_value, result.output_folder)
```

| Field | GUI label | Default |
|---|---|---|
| `subject_id` | Subject | required |
| `goal` | Optimization goal (`mean`, `max`, `focality`, `focality_tf`) | required |
| `postproc` | Field post-processing (`max_TI`, `dir_TI_normal`, `dir_TI_tangential`) | required |
| `current_mA` | Current per channel (mA) | required |
| `electrode` | Electrode Parameters box | required |
| `roi` | Target ROI | required |
| `anisotropy_type` | Conductivity | `"scalar"` |
| `intensity_weight` | Intensity weight $w$ (`focality_tf` only) | `0.0` |
| `eeg_net` / `enable_mapping` | Map result to an EEG net | `None` / `False` |
| `n_multistart` | Restarts | `1` |
| `max_iterations`, `population_size` | Solver settings (blank = SimNIBS default) | `None` |
| `min_electrode_distance` | Minimum electrode distance (mm) | `5.0` |
| `run_final_electrode_simulation` | Simulate the winning montage | `False` |

ROI types: `FlexConfig.SphericalROI(x, y, z, radius, use_mni=, volumetric=, tissues=)`,
`FlexConfig.AtlasROI(atlas_path, label, hemisphere)` for a cortical `.annot` region, and
`FlexConfig.SubcorticalROI(atlas_path, label, tissues, atlas_space)` for a volumetric one. Each
scalar field also accepts a list, which unions several regions into one target.

The `focality_tf` goal maximises a threshold-free contrast:

$$\frac{\overline{E}_{\mathrm{ROI}}^{\,1+w}}{p_{95}\!\left(E_{\mathrm{non\text{-}ROI}}\right)}$$

## Optimizer — exhaustive search

In the GUI you pick a leadfield, an ROI file and the electrodes to search on the **Optimizer ▸
Ex** page. That is `ExConfig`.

```python
from tit.opt import ExConfig, run_ex_search

cfg = ExConfig(
    subject_id="ernie",
    leadfield_hdf="ernie_leadfield_EEG10-20_Okamoto_2004.hdf5",
    roi_name="L-Insula.csv",
    electrodes=ExConfig.PoolElectrodes(electrodes=["Fp1", "Fp2", "C3", "C4", "Cz", "Pz"]),
)
run_ex_search(cfg)
```

| Field | GUI label | Default |
|---|---|---|
| `leadfield_hdf` | Leadfield | required |
| `roi_name` | ROI file | required |
| `electrodes` | `PoolElectrodes` (one list) or `BucketElectrodes` (four lists) | required |
| `total_current` | Total current (mA) | `2.0` |
| `current_step` | Current step (mA) | `0.5` |
| `channel_limit` | Per-channel limit (mA) | `None` |
| `roi_radius` | ROI radius (mm) | `3.0` |
| `roi_coordinate_space` | ROI coordinates (`subject`/`mni`) | `"subject"` |
| `n_jobs` | Parallel workers | `-1` |

`MExConfig` + `run_m_ex_search` are the same fields for the multipolar (4-pair) search, with
`current_mA` in place of `total_current`/`current_step`.

## Simulator

In the GUI you choose a montage from the dropdown, set the electrode parameters and press Run.
The dropdown is the project's montage list; `load_montages` reads exactly that file.

```python
from tit.sim import SimulationConfig, run_simulation, load_montages, list_montage_names

print(list_montage_names("GSN-HydroCel-185.csv", mode="U"))
montages = load_montages(montage_names=["L_Insula"], eeg_net="GSN-HydroCel-185.csv")

cfg = SimulationConfig(
    subject_id="ernie",
    montages=montages,
    conductivity="scalar",
    intensities=[1.0, 1.0],
    output_fields=["TI_max"],
)
run_simulation(cfg)
```

| Field | GUI label | Default |
|---|---|---|
| `subject_id` | Subject | required |
| `montages` | Montage selection | required |
| `conductivity` | Conductivity (`scalar`, `vn`, `dir`, `mc`) | `"scalar"` |
| `intensities` | Current per pair (mA) | `[1.0, 1.0]` |
| `electrode_shape` | Electrode shape | `"ellipse"` |
| `electrode_dimensions` | Electrode dimensions (mm) | `[8.0, 8.0]` |
| `gel_thickness` | Gel thickness (mm) | `4.0` |
| `rubber_thickness` | Rubber thickness (mm) | `2.0` |
| `output_fields` | Output fields (`TI_max`, `TI_avg`, `hf_peak`, `hf_sar`) | `["TI_max"]` |
| `map_to_surf` / `map_to_vol` / `map_to_mni` / `map_to_fsavg` | Output mapping checkboxes | `True` / `False` / `False` / `True` |

Two electrode pairs run a TI simulation, four or more run mTI — the API picks for you.

## Analyzer

In the GUI you choose a simulation, a space and a region on the **Analyzer** page. `Analyzer` is
that form, and its methods return the numbers the results table shows.

```python
from tit.analyzer import Analyzer

analyzer = Analyzer(subject_id="ernie", simulation="L_Insula", space="mesh")
roi = analyzer.analyze_cortex(atlas="DK40", region="lh.insula")
print(roi.roi_mean, roi.roi_max, roi.roi_focality)
```

| Field | GUI label | Default |
|---|---|---|
| `subject_id` | Subject | required |
| `simulation` | Simulation | required |
| `space` | Space (`mesh` or `voxel`) | `"mesh"` |
| `tissue_type` | Tissue (voxel space only) | `"GM"` |
| `field` | Field file (blank = auto) | `None` |
| `analyze_cortex(atlas, region, visualize)` | Cortical (atlas region) analysis | — |
| `analyze_sphere(center, radius, coordinate_space, visualize)` | Spherical analysis | — |

`run_group_analysis(subject_ids, simulation, space, analysis_type, ...)` runs the same analysis
across subjects, as the Analyzer's multi-subject mode does.

## Group statistics

In the GUI you define a comparison on the **Statistics** page and press Run. That is
`GroupComparisonConfig` plus `run_group_comparison`.

```python
from tit.stats import GroupComparisonConfig, run_group_comparison

cfg = GroupComparisonConfig(
    analysis_name="active_vs_sham",
    subjects=GroupComparisonConfig.load_subjects("subjects.csv"),
    test_type=GroupComparisonConfig.TestType.UNPAIRED,
)
res = run_group_comparison(cfg)
```

| Field | GUI label | Default |
|---|---|---|
| `analysis_name` | Analysis name | required |
| `subjects` | Subject table (or a CSV via `load_subjects`) | required |
| `test_type` | Test type (paired / unpaired / one-sample) | `UNPAIRED` |
| `alternative` | Alternative hypothesis | `TWO_SIDED` |
| `cluster_stat` | Cluster statistic (mass / size) | `MASS` |
| `cluster_threshold` | Cluster-forming threshold | `0.05` |
| `n_permutations` | Permutations | `1000` |
| `alpha` | Alpha | `0.05` |
| `tissue_type` | Tissue | `GREY` |
| `space` | Space (`MNI` or `fsaverage`) | `MNI` |

## The JSON config interface

The app never calls these functions in-process — it writes the serialised config to JSON and runs
the module. You can run the exact same thing:

```bash
simnibs_python -m tit.sim        config.json
simnibs_python -m tit.opt.flex   config.json
simnibs_python -m tit.opt.ex     config.json
simnibs_python -m tit.opt.mex    config.json
simnibs_python -m tit.analyzer   config.json
simnibs_python -m tit.stats      config.json
simnibs_python -m tit.pre        config.json
```

Config files are written by `tit.config_io.write_config_json()`.

## AI coding agents

Full guide: [AI Assistant]({{ site.baseurl }}/wiki/ai-assistant/).

If you write scripts with an AI assistant, install the
[TI-Toolbox agent plugin](https://github.com/idossha/TI-Toolbox/tree/main/agent-plugin): it gives
the assistant this wiki, the `tit` source and a read-only view of your project through an MCP
server, so it stops guessing API fields. In Claude Code:
`/plugin marketplace add idossha/TI-Toolbox` then `/plugin install ti-toolbox@ti-toolbox`.
