---
layout: wiki
title: Scripting
permalink: /wiki/scripting/
---

Every page of the app does its work by calling the `tit` Python API — it builds a config object,
serialises it to JSON and runs the same module you can run yourself. This page walks the app page
by page and shows, for each one, the call its **Run** button makes.

The app's forms start from their own defaults (`tit/server/app_defaults.py`), not the dataclass
defaults a script gets; where the two differ, the **Default** column adds the app default.

A runnable version of the same sequence is the
[example notebook]({{ site.baseurl }}/wiki/notebooks/#the-example-notebook).

## Where scripts run

Scripting happens **inside the container** — that is where SimNIBS and `tit` live. Your project is
mounted at `/mnt/<project_name>/` and everything is pre-installed.

**1. The Notebooks page, in the app.** Open it and start typing; the kernel is the container's
SimNIBS Python with your project mounted.

**2. `docker exec`**, from your own terminal:

```bash
python3 loader.py --project ~/datasets/000 --status   # prints the container's name
docker exec -it ti-toolbox-<hash>-tit-1 bash
simnibs_python my_script.py
```

`loader.py` is the [command-line launcher]({{ site.baseurl }}/installation/bash-cli/)
(`bash loader.sh … --status` works too). There is nothing to install on your **host**: the
scripting API needs SimNIBS, which is in the image, and `tit` is not published on PyPI. Developers
with a source checkout can `pip install -e .` it, which adds a `tit launch` command — see
[Development]({{ site.baseurl }}/wiki/development/).

## The project

In the app you open a project. In code, `get_path_manager` does the same: it is the object that
knows where everything in a BIDS project lives, and every module uses it.

No data of your own yet? `tit.examples.fetch_ernie(project)` downloads both parts of the `ernie`
dataset (its raw T1/T2 and its finished `m2m_ernie` head model: a ~630 MB download, ~0.7 GB on
disk, GPL-3.0) into the project
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

| Call | App equivalent |
|---|---|
| `get_path_manager(project_dir)` | Opening a project |
| `discover_subjects(project_dir)` | The subject list |
| `pm.m2m(sid)` | The head model of a subject |
| `pm.simulations(sid)` | A subject's simulations on the **Results** page |
| `pm.flex_search(sid)` / `pm.ex_search(sid)` | A subject's flex and ex runs on the **Results** page |

## Pre-processing

In the app you tick steps on the **Pre-processing** page and press Run. Those tick boxes are the
keyword arguments of `run_pipeline`.

```python
from tit.pre import run_pipeline, check_m2m_exists

if not check_m2m_exists("/mnt/000", "ernie"):
    run_pipeline(["ernie"], convert_dicom=True, create_m2m=True)
```

| Argument | App control | Default |
|---|---|---|
| `subject_ids` | Subject selection | required |
| `convert_dicom` | **Convert DICOM to NIfTI** | `False` (app: `True`) |
| `create_m2m` | **SimNIBS charm (m2m + subject atlas)** | `False` (app: `True`) |
| `run_fastsurfer` | **FastSurfer segmentation** | `False` (app: `True`) |
| `run_freesurfer` | **FreeSurfer (optional)** | `False` |
| `run_tissue_analysis` | **Tissue analyzer** | `False` |
| `run_qsiprep` | **QSIPrep** | `False` |
| `run_qsirecon` | **QSIRecon** | `False` |
| `extract_dti` | **Extract DTI tensor** | `False` |
| `skip_existing_outputs` | — (**Skip** in the existing-outputs dialog) | `False` (app: `True`) |

## Optimizer — flex-search

In the app you fill a Flex job on the **Optimizer** page — target, goal, current, electrode size —
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

| Field | App control | Default |
|---|---|---|
| `subject_id` | Subject | required |
| `goal` | **Goal** (`mean`, `max`, `focality`, `focality_tf`) | required |
| `postproc` | **Post-processing** (`max_TI`, `dir_TI_normal`, `dir_TI_tangential`) | required |
| `current_mA` | **Electrodes ▸ Current** (mA per channel) | required |
| `electrode` | **Electrodes** card (shape, dimensions, gel thickness) | required |
| `roi` | **Target** | required |
| `anisotropy_type` | **Anisotropy type** | `"scalar"` |
| `intensity_weight` | **Intensity preference** $w$ (`focality_tf` only) | `0.0` |
| `eeg_net` / `enable_mapping` | **EEG net template** / **Run simulation with mapped electrodes** | `None` / `False` |
| `n_multistart` | **Optimization runs** | `1` |
| `max_iterations`, `population_size`, `tolerance`, `mutation`, `recombination` | **Solver** card (`None` = SimNIBS default) | `None` (app: `500`, `13`, `0.1`, `"0.01,0.5"`, `0.7`) |
| `min_electrode_distance` | **Electrodes ▸ Min distance** (mm) | `5.0` |
| `run_final_electrode_simulation` | **Run final electrode simulation** | `False` |

ROI types: `FlexConfig.SphericalROI(x, y, z, radius, use_mni=, volumetric=, tissues=)`,
`FlexConfig.AtlasROI(atlas_path, label, hemisphere)` for a cortical `.annot` region, and
`FlexConfig.SubcorticalROI(atlas_path, label, tissues, atlas_space)` for a volumetric one. Each
scalar field also accepts a list, which unions several regions into one target (e.g.
`label=[17, 53]` for both hippocampi). `tissues` is `"GM"`, `"WM"` or `"both"`; `atlas_space`
is `"subject"` or `"mni"`; a NIfTI mask is a `SubcorticalROI` with `label=None` (all positive
voxels). `SphericalROI` defaults to `volumetric=False`, which evaluates the sphere on the
cortical surface: set `volumetric=True` for any deep target.

More `FlexConfig` fields:

| Field | Meaning | Default |
|---|---|---|
| `non_roi_method` / `non_roi` | `"everything_else"` or `"specific"` plus an ROI of any type (focality goals) | `None` → `"everything_else"` |
| `thresholds` | `"0.2"` or `"0.2,0.5"` V/m (`focality` only) | `None` |
| `mode` / `adaptive` / `pareto` | `"flex_adaptive"` (`AdaptiveFocalityConfig(roi_percentage=80, nonroi_percentage=20)`) or `"flex_pareto"` (`ParetoSweepConfig(roi_pcts, nonroi_pcts)`); `goal="focality"` only | `"flex"` |
| `optimize_current_ratio` | Search the two-channel current split jointly with placement | `False` |
| `ratio_total_mA` / `ratio_levels` | Total current shared by the channels / splits over 1:3–3:1 (rounded up to odd) | `2 × current_mA` / `21` |
| `aniso_maxratio`, `aniso_maxcond` | Bounds for `anisotropy_type="vn"` | `10.0`, `2.0` |
| `skin_region_margin_mm`, `avoid_landmark_regions` | Signed valid-skin margin; keep ear/eye zones invalid | `0.0`, `True` |

```python
cfg = FlexConfig(
    subject_id="ernie", goal="focality_tf", postproc="max_TI", current_mA=2.0,
    intensity_weight=0.0,
    electrode=FlexConfig.ElectrodeConfig(),
    roi=FlexConfig.SphericalROI(x=-25.0, y=-10.0, z=-20.0, radius=8.0, use_mni=True,
                                volumetric=True, tissues="GM"),
    non_roi_method="everything_else",
    optimize_current_ratio=True, ratio_total_mA=4.0,
)
```

The `focality_tf` goal maximises a threshold-free contrast (see
[Flex search]({{ site.baseurl }}/wiki/flex-search/#goals)):

$$\frac{\overline{E}_{\mathrm{ROI}}^{\,1+w}}{\overline{E}_{\mathrm{non\text{-}ROI}}}$$

## Optimizer — exhaustive search

In the app an Ex job on the **Optimizer** page picks an EEG net (whose leadfield it searches), a
**Target** and the electrodes to search. That is `ExConfig`.

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

| Field | App control | Default |
|---|---|---|
| `leadfield_hdf` | The EEG net (its leadfield) | required |
| `roi_name` | **Target** | required |
| `electrodes` | **Electrodes ▸ Search space**: **Bucketed** = `BucketElectrodes` (four lists), **All combinations** = `PoolElectrodes` (one list) | required |
| `total_current` | **Current ▸ Total current** (mA) | `2.0` |
| `current_step` | **Current ▸ Step** (mA) | `0.5` (app: `0.2`) |
| `channel_limit` | **Current ▸ Channel limit** (mA) | `None`: one balanced split, half the total per channel (app: `1.0`) |
| `roi_radius` | **Target** (sphere radius, mm) | `3.0` |
| `roi_coordinate_space` | **Target** (coordinate space, `subject`/`mni`) | `"subject"` |
| `n_jobs` | — (the app always sends `-1`): parallel workers, `-1` = the global CPU limit, 70 % of the cores by default; larger values are capped at it | `-1` |

`MExConfig` + `run_m_ex_search` take the same fields for the multipolar (four-channel) search, with
`current_mA` in place of `total_current`/`current_step`, no `channel_limit`, and eight lists in
`BucketElectrodes`.

## Simulator

In the app you add a montage row to the **Simulator**'s job table, set the job settings and press
Run. A row's montage choices are the project's montage list; `load_montages` reads exactly that
file.

```python
from tit.sim import SimulationConfig, run_simulation, load_montages, list_montage_names

print(list_montage_names("GSN-HydroCel-185.csv", mode="U"))
montages = load_montages(montage_names=["L_Insula"], eeg_net="GSN-HydroCel-185.csv")

cfg = SimulationConfig(
    subject_id="ernie",
    montages=montages,
    conductivity="scalar",
    intensities=[1.0, 1.0],
    # output_fields defaults to ["TI_max", "hf_peak", "hf_rms"]; map_to_vol=True adds NIfTIs
)
run_simulation(cfg)
```

| Field | App control | Default |
|---|---|---|
| `subject_id` | Subject | required |
| `montages` | **Montage** column of the job table | required |
| `conductivity` | **Conductivity ▸ Model** (`scalar`, `vn`, `dir`, `mc`) | `"scalar"` |
| `intensities` | **Currents (mA)** column | `[1.0, 1.0]` |
| `electrode_shape` | **Electrodes ▸ Shape** | `"ellipse"` |
| `electrode_dimensions` | **Electrodes ▸ Dimensions** (mm) | `[8.0, 8.0]` |
| `gel_thickness` | **Electrodes ▸ Gel thickness** (mm) | `1.0` |
| `rubber_thickness` | — | `2.0` |
| `output_fields` | **Output fields** (`TI_max`, `TI_avg`, `hf_peak`, `hf_rms`, `hf_power_density`) | `None`: `["TI_max", "hf_peak", "hf_rms"]`, or `["hf_peak", "hf_rms"]` with `carrier_only` |
| `carrier_only` | **Carrier-only control** (ΔF = 0): coherent `hf_peak`/`hf_rms`/`hf_power_density`, no envelope fields; two-channel TI, `output_fields` from those three ([details]({{ site.baseurl }}/wiki/simulator/#carrier-only-control)) | `False` |
| `map_to_surf` | — | `True` |
| `map_to_vol` | **Write NIfTI volumes (one per field)** | `False` |
| `map_to_mni` | **Also in MNI space** (turns `map_to_vol` on) | `False` |
| `map_to_fsavg` | **Map fields to fsaverage** | `True` (app: `False`) |

Two channels (electrode pairs) run a TI simulation, four or more run mTI — the API picks for you.

## Analyzer

In the app you choose a simulation, a space and a region on the **Analyzer** page. `Analyzer` is
that form, and its methods return the numbers the results table shows.

```python
from tit.analyzer import Analyzer

analyzer = Analyzer(subject_id="ernie", simulation="L_Insula", space="mesh")
roi = analyzer.analyze_cortex(atlas="DK40", region="lh.insula")
print(roi.roi_mean, roi.roi_max, roi.roi_focality)
print(roi.hf_peak_focality, roi.ti_selectivity)  # None unless the run wrote hf_peak
```

| Field | App control | Default |
|---|---|---|
| `subject_id` | **Subject** | required |
| `simulation` | **Simulation** | required |
| `space` | **Space** (`mesh` or `voxel`) | `"mesh"` |
| `tissue_type` | **Tissue** (voxel space only) | `"GM"` |
| `field` | **Field** (blank = auto) | `None` |
| `analyze_cortex(atlas, region, visualize)` | **Job settings ▸ Cortical** | — |
| `analyze_subcortical(atlas, region, coordinate_space, visualize)` | **Job settings ▸ Subcortical** (a subject volume atlas, or a shipped MNI atlas with `coordinate_space="mni"`) | — |
| `analyze_sphere(center, radius, coordinate_space, visualize)` | **Job settings ▸ Spherical** (one sphere) | — |
| `analyze_mask(mask_path, coordinate_space, visualize)` | **Job settings ▸ NIfTI mask** | — |
| `analyze_spheres(spheres, coordinate_space, visualize)` | — (Python only: several spheres as one ROI; the app runs one analysis per sphere) | — |

`run_group_analysis(subject_ids, simulation, space, analysis_type, ...)` runs the same analysis
across subjects, as the Analyzer's **Combine into one group analysis** does. `simulation` is one
simulation name shared by every subject, and `analysis_type` is `"spherical"`, `"cortical"`,
`"subcortical"` or `"mask"`. Each run writes `group_summary.csv` (with an AVERAGE row),
`group_comparison.pdf` and its log to its own folder,
`derivatives/ti-toolbox/group_analysis/<simulation>_<space>_<target>_<YYYYMMDD>_<HHMMSS>/`
(`PathManager.group_analysis(name)`; `PathManager.logs_group()` is gone), unless you pass
`output_dir`.

## Field metrics (`tit.calc`)

The simulator's field outputs come from five functions in `tit.calc`, which you can call on
any channel fields. The envelope functions take a list of `(N, 3)` arrays in V/m, one per channel
in montage order, two channels per beating pair (`[E1, E2]` for TI, `[E1, E2, E3, E4, ...]` for mTI);
the carrier functions take the fields of any number of channels. The definitions, and how exact each one is, are
under [Field quantities on the Analyzer page]({{ site.baseurl }}/wiki/analyzer/#method-and-accuracy).

```python
from simnibs import mesh_io

from tit.calc import envelope, envelope_max, envelope_mean, hf_peak, hf_power

hf = "derivatives/SimNIBS/sub-ernie/Simulations/L_Insula/high_Frequency/mesh"
E1 = mesh_io.read_msh(f"{hf}/ernie_TDCS_1_scalar.msh").field["E"].value
E2 = mesh_io.read_msh(f"{hf}/ernie_TDCS_2_scalar.msh").field["E"].value

ti_max = envelope_max([E1, E2])                       # TI_max, V/m
ti_max, direction = envelope_max([E1, E2], return_direction=True)  # + unit direction
ti_z = envelope([E1, E2], [0.0, 0.0, 1.0])            # envelope along one direction
ti_avg = envelope_mean([E1, E2])                      # TI_avg
peak = hf_peak([E1, E2])                              # hf_peak, V/m (zero-to-peak)
power = hf_power([E1, E2])                            # mean square, (V/m)^2; hf_rms = sqrt(power)
```

`envelope(fields, normals)` with one unit normal per row is `TI_normal`, and
`envelope_max(fields, perpendicular_to=normals)` is the strongest envelope within the surface
plane (flex-search's `dir_TI_tangential`). `hf_peak(fields, coherent=True)` and
`hf_power(fields, coherent=True)` are the carrier-only (ΔF = 0) forms. A channel with no beating
partner goes into the envelope functions with a zero field as its partner,
`[E1, E2, Eu, np.zeros_like(Eu)]`, and into `hf_peak`/`hf_power` as one more field. The simulator's
`hf_power_density` is `hf_power` weighted by the conductivity the run solved with; for
isotropic conductivity that is `power` times each element's conductivity in S/m (the simulator
uses the full tensor under the anisotropic models).

## Group statistics

In the app, group statistics are the **Cluster permutation** extension panel, turned on under
**Settings ▸ Extensions** (see [Cluster permutation testing]({{ site.baseurl }}/wiki/cluster-permutation-testing/)).
Its **Analysis type** **Classification** is `GroupComparisonConfig` plus `run_group_comparison`.

```python
from tit.stats import GroupComparisonConfig, run_group_comparison

cfg = GroupComparisonConfig(
    analysis_name="active_vs_sham",
    subjects=GroupComparisonConfig.load_subjects("subjects.csv"),
    test_type=GroupComparisonConfig.TestType.UNPAIRED,
)
res = run_group_comparison(cfg)
```

| Field | App control | Default |
|---|---|---|
| `analysis_name` | **Analysis name** | required |
| `subjects` | Participant table (or a CSV via `load_subjects`) | required |
| `test_type` | **Test type** (`UNPAIRED` / `PAIRED`) | `UNPAIRED` |
| `alternative` | **Alternative** | `TWO_SIDED` |
| `cluster_stat` | **Cluster statistic** (mass / size) | `MASS` |
| `cluster_threshold` | **Cluster threshold** | `0.05` |
| `n_permutations` | **Permutations** | `1000` |
| `alpha` | **Alpha** | `0.05` |
| `n_jobs` | **Parallel workers** (`-1` = the global CPU limit) | `-1` |
| `tissue_type` | **Tissue** | `GREY` |
| `space` | **Space** (`MNI` or `fsaverage`) | `MNI` |

**Correlation** is `CorrelationConfig` plus `run_correlation`: the same statistical and data
fields, with per-subject `effect_size` (and optional `weight`) in place of a group label, plus
`correlation_type` (**Correlation type**, `PEARSON` or `SPEARMAN`) and `use_weights`
(**Apply per-subject weights**, default `True`). Serialised, each config carries `_type`
(`"GroupComparisonConfig"` or `"CorrelationConfig"`), which is how `simnibs_python -m tit.stats`
tells a correlation from a group comparison; the panel sends it too.

```python
from tit.stats import CorrelationConfig, run_correlation

cfg = CorrelationConfig(
    analysis_name="dose_vs_effect",
    subjects=CorrelationConfig.load_subjects("effects.csv"),  # subject_id, simulation_name, effect_size[, weight]
)
res = run_correlation(cfg)
```

## The JSON config interface

The app never calls these functions in-process — it writes the serialised config to JSON and runs
the module. You can run the exact same thing. `write_config_json(cfg)` serialises any config
dataclass to a temporary JSON file, adds `project_dir` from the active `PathManager` (every runner
reads its project from that key) and returns the file's path:

```python
from tit import get_path_manager
from tit.config_io import write_config_json

get_path_manager("/mnt/000")
path = write_config_json(cfg)   # then: simnibs_python -m tit.sim <path>
```

| Command | Config it reads |
|---|---|
| `simnibs_python -m tit.pre config.json` | `tit.pre.config.PreprocessConfig` |
| `simnibs_python -m tit.sim config.json` | `SimulationConfig` |
| `simnibs_python -m tit.opt.flex config.json` | `FlexConfig` (its `mode` picks plain, adaptive or Pareto flex) |
| `simnibs_python -m tit.opt.ex config.json` | `ExConfig` |
| `simnibs_python -m tit.opt.mex config.json` | `MExConfig` |
| `simnibs_python -m tit.opt.leadfield_runner config.json` | `tit.opt.leadfield_config.LeadfieldConfig` |
| `simnibs_python -m tit.analyzer config.json` | `tit.analyzer.config.AnalyzerConfig` (not the `Analyzer` class) |
| `simnibs_python -m tit.stats config.json` | `GroupComparisonConfig` or `CorrelationConfig`, chosen by the `_type` that `write_config_json` writes (an older `"mode": "correlation"` still works) |
| `simnibs_python -m tit.stats.nifti_average config.json` | `tit.stats.nifti_average_config.NiftiAverageConfig` |
| `simnibs_python -m tit.plotting.nilearn config.json` | `tit.plotting.nilearn.config.NilearnConfig` |
| `simnibs_python -m tit.source config.json` | `tit.source.config.SourceConfig` |
| `simnibs_python -m tit.blender config.json` | `MontageConfig`, `VectorConfig`, `RegionConfig` or `SubcorticalConfig` from `tit.blender.config` |
| `simnibs_python -m tit.project_init config.json` | Only `project_dir`: creates the project's folder structure |

## AI coding agents

Full guide: [AI Assistant]({{ site.baseurl }}/wiki/ai-assistant/).

If you write scripts with an AI assistant, install the
[TI-Toolbox agent plugin](https://github.com/idossha/TI-Toolbox/tree/main/agent-plugin): it gives
the assistant this wiki, the `tit` source and a read-only view of your project through an MCP
server, so it stops guessing API fields. A second server, `ti-toolbox-jobs`, lets it run jobs
through the app you have open: it proposes a plan, you approve it in the app, and the app runs it.
In Claude Code: `/plugin marketplace add idossha/TI-Toolbox` then
`/plugin install ti-toolbox@ti-toolbox`.
