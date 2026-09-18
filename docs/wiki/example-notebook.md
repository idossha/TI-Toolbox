---
layout: wiki
title: Example Notebook
permalink: /wiki/example-notebook/
---

<p>
<a href="{{ site.baseurl }}/assets/notebooks/example_workflow.ipynb" download>&#11015; Download example_workflow.ipynb</a>
&nbsp;&nbsp;
<a href="https://github.com/idossha/TI-Toolbox/blob/main/tit/server/examples/example_workflow.ipynb">View on GitHub</a>
</p>

This page mirrors the downloadable notebook cell for cell. To run it: open your project, go to
the app's [Notebooks]({{ site.baseurl }}/wiki/notebooks/) page, choose **Import .ipynb**, and pick
the *SimNIBS + TI-Toolbox* kernel — the kernel is the container's SimNIBS Python, so nothing needs
installing. You do not need your own data: cell 1 fetches the SimNIBS example subject into
whatever project folder you point `PROJECT` at. The notebook lives at
[`tit/server/examples/`](https://github.com/idossha/TI-Toolbox/tree/main/tit/server/examples) in the
repository and is also seeded into every project as `examples/example_workflow.ipynb` on the
Notebooks page.

<!-- generated from tit/server/examples/example_workflow.ipynb by dev/render_example_notebook.py; do not edit below -->

# TI-Toolbox in eight cells

Everything the app does, it does by calling the `tit` Python API. This notebook walks the app
page by page — Project, Pre-processing, Optimizer, Simulator, Analyzer — and shows the one call
each page's **Run** button makes. Nothing here is a helper we wrote for the notebook; every line
is the public API.

It runs against the SimNIBS example subject `ernie`, fetched into your own project by cell 1, inside the TI-Toolbox container.

## 1. Pick the project (app ▸ the project you opened)

Opening a project in the app sets the project root. In code, `get_path_manager` does the same:
it is the single object that knows where everything in a BIDS project lives.

**Edit one line:** set `PROJECT` below to a folder on your machine (any empty folder works), or
export `TIT_PROJECT_DIR` before starting the kernel. Everything else in the notebook derives
from it.

`fetch_ernie` downloads both parts of the `ernie` example dataset once — its raw T1/T2
(`ernie/nifti`) and its finished head model (`ernie/headmodel`), about 630 MB together, GPL-3.0 — so
every later cell has a head model. Each part is skipped if already present. Same as ticking them in
the app's *Add example data?* chooser.

```python
import os
from tit import get_path_manager
from tit.examples import fetch_ernie
from tit.pre import discover_subjects

PROJECT = os.environ.get("TIT_PROJECT_DIR") or "/path/to/your/project"   # <-- edit me (or set TIT_PROJECT_DIR)
SUBJECT = "ernie"

pm = get_path_manager(PROJECT)
fetch_ernie(PROJECT)

print(discover_subjects(PROJECT))
```

## 2. Pre-processing (app ▸ Pre-processing ▸ Run)

The Pre-processing page's checkboxes — *Convert DICOMs*, *Create head model (charm)* — are the
keyword arguments of `run_pipeline`. It takes hours, and the example subject fetched above already
ships with a finished head model, so the `if` below skips it. On your own subjects this is the
call that builds `m2m_<subject>`.

```python
from tit.pre import run_pipeline, check_m2m_exists

if not check_m2m_exists(PROJECT, SUBJECT):
    run_pipeline([SUBJECT], convert_dicom=True, create_m2m=True)
else:
    print("head model already exists:", pm.m2m(SUBJECT))
```

## 3. Optimizer (app ▸ Optimizer ▸ Flex ▸ Run)

Flex-search searches electrode positions freely on the scalp. The form fields on the Optimizer
page map one-to-one onto `FlexConfig`: the goal dropdown, the current in mA, the electrode
geometry, and the target ROI — here a 10 mm sphere at an MNI coordinate, so no atlas file is
needed. The solver settings are **reduced for the example** (one restart, a handful of generations) so the
cell finishes in minutes; leave them out for the app's defaults. Every run lands in a new folder
under `flex-search/`, so re-running never overwrites an earlier search.

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

## 4. Choose a montage (app ▸ Simulator ▸ the montage list)

The Simulator page's montage dropdown is the project's own montage list, `montage_list.json`,
which starts empty in a new project. The page's **Add montage** button is `upsert_montage`; it
writes the montage under an EEG net and is safe to re-run. The net must be one of the caps in the
head model's `eeg_positions/` — the example head ships the standard 10-10 cap, so the four electrodes
below are 10-10 names. `list_montage_names` reads the file back and `load_montages` turns a chosen
name into the object the simulator takes.

```python
from tit.sim import upsert_montage, list_montage_names, load_montages

NET = "EEG10-10_UI_Jurak_2007.csv"
MONTAGE = "L_Insula"

upsert_montage(eeg_net=NET, montage_name=MONTAGE, mode="U",
               electrode_pairs=[["F7", "TP7"], ["FT7", "P7"]])
print(list_montage_names(NET, mode="U"))

montages = load_montages(montage_names=[MONTAGE], eeg_net=NET, include_flex=False)
print(montages[0].name, montages[0].electrode_pairs)
```

## 5. Simulate (app ▸ Simulator ▸ Run)

Two electrode pairs means a TI simulation; four or more means mTI, and the API picks for you.
Every other field on the page — conductivity, current per pair, electrode shape and size — is a
field of `SimulationConfig`. `overwrite=True` replaces an earlier run of the same montage, so the
cell can be run again. A single FEM solve takes a few minutes.

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

print(pm.simulation(SUBJECT, MONTAGE))
```

## 6. Analyze (app ▸ Analyzer ▸ Run)

The Analyzer page asks for a simulation, a space (mesh or voxel) and a region. `analyze_cortex`
takes an atlas name and a region name and returns the numbers the page's results table shows.
Cortical region names carry the hemisphere (`lh.insula`, `rh.insula`); a bare name is both. Mesh
space needs only the head model; voxel space additionally needs the subject's FastSurfer volume
parcellation, which the example head does not ship.

```python
from tit.analyzer import Analyzer

analyzer = Analyzer(subject_id=SUBJECT, simulation=MONTAGE, space="mesh")
roi = analyzer.analyze_cortex(atlas="DK40", region="lh.insula")

print(roi.region_name, roi.roi_mean, roi.roi_max, roi.roi_focality)
```

## 7. Group statistics (app ▸ Statistics)

The example project has one subject, so there is no group to compare here. With several subjects, the
Statistics page calls `tit.stats.run_group_comparison` on a `GroupComparisonConfig` — see the
[Scripting](https://idossha.github.io/TI-Toolbox/wiki/scripting/) page for that one snippet.

## 8. Where the results land

Every path below is derived from the project root by `pm`; nothing is typed by hand.

```python
print("head model      ", pm.m2m(SUBJECT))
print("simulations     ", pm.simulations(SUBJECT))
print("this simulation ", pm.simulation(SUBJECT, MONTAGE))
print("flex-search     ", pm.flex_search(SUBJECT))
print("analyses        ", pm.analysis_dir(SUBJECT, MONTAGE, "mesh"))
print("logs            ", pm.logs(SUBJECT))
```
