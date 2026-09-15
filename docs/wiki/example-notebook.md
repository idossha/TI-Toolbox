---
layout: wiki
title: Example Notebook
permalink: /wiki/example-notebook/
---

<p>
<a href="{{ site.baseurl }}/assets/notebooks/example_workflow.ipynb" download>&#11015; Download example_workflow.ipynb</a>
&nbsp;&nbsp;
<a href="https://github.com/idossha/TI-Toolbox/blob/main/docs/assets/notebooks/example_workflow.ipynb">View on GitHub</a>
</p>

This page mirrors the downloadable notebook cell for cell. To run it: open your project, go to
the app's [Notebooks]({{ site.baseurl }}/wiki/notebooks/) page, choose **Import .ipynb**, and pick
the *SimNIBS + TI-Toolbox* kernel — the kernel is the container's SimNIBS Python, so nothing needs
installing. Change `PROJECT` and `SUBJECT` to match your own data.

# TI-Toolbox in eight cells

Everything the app does, it does by calling the `tit` Python API. This notebook walks the app
page by page — Project, Pre-processing, Optimizer, Simulator, Analyzer — and shows the one call
each page's **Run** button makes. Nothing here is a helper we wrote for the notebook; every line
is the public API.

It runs against the public **Dataset 000**, subject `ernie`, inside the TI-Toolbox container.

## 1. Pick the project (app ▸ the project you opened)

Opening a project in the app sets the project root. In code, `get_path_manager` does the same:
it is the single object that knows where everything in a BIDS project lives.

```python
from tit import get_path_manager
from tit.pre import discover_subjects

PROJECT = "/mnt/000"
pm = get_path_manager(PROJECT)

print(discover_subjects(PROJECT))
```

## 2. Pre-processing (app ▸ Pre-processing ▸ Run)

The Pre-processing page's checkboxes — *Convert DICOMs*, *Create head model (charm)* — are the
keyword arguments of `run_pipeline`. It takes hours, and `sub-ernie` in Dataset 000 already ships
with a finished head model, so the `if` below skips it. On your own subject, remove the guard.

```python
from tit.pre import run_pipeline, check_m2m_exists

SUBJECT = "ernie"

if not check_m2m_exists(PROJECT, SUBJECT):
    run_pipeline([SUBJECT], convert_dicom=True, create_m2m=True)
else:
    print("head model already exists:", pm.m2m(SUBJECT))
```

## 3. Optimizer (app ▸ Optimizer ▸ Flex ▸ Run)

Flex-search searches electrode positions freely on the scalp. The form fields on the Optimizer
page map one-to-one onto `FlexConfig`: the goal dropdown, the current in mA, the electrode
geometry, and the target ROI — here a 10 mm sphere at an MNI coordinate, so no atlas file is
needed. The solver settings are **reduced for the example** so the cell finishes in minutes; leave
them out for the app's defaults.

```python
from tit.opt import FlexConfig, run_flex_search

flex = FlexConfig(
    subject_id=SUBJECT,
    goal="mean",
    postproc="max_TI",
    current_mA=1.0,
    electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
    roi=FlexConfig.SphericalROI(x=-37.0, y=-21.0, z=58.0, radius=10.0, use_mni=True),
    n_multistart=1,
    max_iterations=5,
    population_size=4,
)
result = run_flex_search(flex)

print(result.best_value, result.output_folder)
```

## 4. Choose a montage (app ▸ Simulator ▸ the montage dropdown)

The Simulator page's montage dropdown is the project's montage list. `list_montage_names` reads
exactly that file, and `load_montages` turns a chosen name into the object the simulator takes.

```python
from tit.sim import list_montage_names, load_montages

NET = "GSN-HydroCel-185.csv"
print(list_montage_names(NET, mode="U"))

montages = load_montages(montage_names=["L_Insula"], eeg_net=NET, include_flex=False)
print(montages[0].name, montages[0].electrode_pairs)
```

## 5. Simulate (app ▸ Simulator ▸ Run)

Two electrode pairs means a TI simulation; four or more means mTI, and the API picks for you.
Every other field on the page — conductivity, current per pair, electrode shape and size — is a
field of `SimulationConfig`.

```python
from tit.sim import SimulationConfig, run_simulation

sim = SimulationConfig(
    subject_id=SUBJECT,
    montages=montages,
    conductivity="scalar",
    intensities=[1.0, 1.0],
    electrode_shape="ellipse",
    electrode_dimensions=[8.0, 8.0],
    output_fields=["TI_max"],
)
run_simulation(sim, overwrite=True)

print(pm.simulation(SUBJECT, montages[0].name))
```

## 6. Analyze (app ▸ Analyzer ▸ Run)

The Analyzer page asks for a simulation, a space (mesh or voxel) and a region. `analyze_cortex`
takes an atlas name and a region name and returns the numbers the page's results table shows.

```python
from tit.analyzer import Analyzer

analyzer = Analyzer(subject_id=SUBJECT, simulation="L_Insula", space="mesh")
roi = analyzer.analyze_cortex(atlas="DK40", region="lh.insula")

print(roi.region_name, roi.roi_mean, roi.roi_max, roi.roi_focality)
```

## 7. Group statistics (app ▸ Statistics)

Dataset 000 has one subject, so there is no group to compare here. With several subjects, the
Statistics page calls `tit.stats.run_group_comparison` on a `GroupComparisonConfig` — see the
[Scripting]({{ site.baseurl }}/wiki/scripting/) page for that one snippet.

## 8. Where the results land

Every path below is derived from the project root by `pm`; nothing is typed by hand.

```python
print("head model      ", pm.m2m(SUBJECT))
print("simulations     ", pm.simulations(SUBJECT))
print("this simulation ", pm.simulation(SUBJECT, "L_Insula"))
print("flex-search     ", pm.flex_search(SUBJECT))
print("analyses        ", pm.analysis_dir(SUBJECT, "L_Insula", "mesh"))
print("logs            ", pm.logs(SUBJECT))
```
