---
layout: wiki
title: Notebooks
permalink: /wiki/notebooks/
---

**Notebooks** (⌘7) is a Jupyter environment inside the app, running on the container's own
Python interpreter (SimNIBS + TI-Toolbox), so nothing needs installing.

Notebooks are ordinary `.ipynb` files in your project, under
`<project>/code/ti-toolbox/notebooks/`. Saving round-trips the document, so a notebook edited here
and a notebook edited in Jupyter Lab produce the same file.

<img src="{{ site.baseurl }}/assets/imgs/v3/notebooks-example.png" alt="The example_workflow notebook, TI-Toolbox in eight cells, open in the Notebooks page: the first cell has run and listed the project's subjects, on the SimNIBS + TI-Toolbox kernel" style="width: 100%; max-width: 1000px;">
<em>The seeded worked example, run against a real project. Each cell makes the same call as one page of the app.</em>

## Example workflow

Example workflow on the freely available subject `ernie`.

### 1. Load

Point at a project folder; `fetch_ernie` downloads the example subject into it.

```python
from tit import get_path_manager
from tit.examples import fetch_ernie
from tit.pre import discover_subjects

PROJECT = "/path/to/your/project"
SUBJECT = "ernie"

pm = get_path_manager(PROJECT)
fetch_ernie(PROJECT)
print(discover_subjects(PROJECT))
```

### 2. Pre-process

Build the head model with charm. Ernie ships with one, so this is skipped there.

```python
from tit.pre import run_pipeline, check_m2m_exists

if not check_m2m_exists(PROJECT, SUBJECT):
    run_pipeline([SUBJECT], convert_dicom=True, create_m2m=True)
```

### 3. Optimise

Flex-search for electrode positions that drive a 10 mm sphere at an MNI coordinate.

```python
from tit.opt import FlexConfig, run_flex_search

flex = FlexConfig(
    subject_id=SUBJECT,
    goal="mean",
    postproc="max_TI",
    current_mA=1.0,
    electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
    roi=FlexConfig.SphericalROI(x=-37.0, y=-21.0, z=58.0, radius=10.0, use_mni=True),
)
result = run_flex_search(flex)
print(result.best_value, result.output_folder)
```

### 4. Simulate

Save a montage by name, then simulate it.

```python
from tit.sim import upsert_montage, load_montages, SimulationConfig, run_simulation

NET = "EEG10-10_UI_Jurak_2007.csv"
MONTAGE = "L_Insula"
upsert_montage(eeg_net=NET, montage_name=MONTAGE, mode="U",
               electrode_pairs=[["F7", "TP7"], ["FT7", "P7"]])

sim = SimulationConfig(
    subject_id=SUBJECT,
    montages=load_montages(montage_names=[MONTAGE], eeg_net=NET),
    intensities=[1.0, 1.0],
)
run_simulation(sim, overwrite=True)
```

### 5. Analyse

Read the field in a cortical region.

```python
from tit.analyzer import Analyzer

analyzer = Analyzer(subject_id=SUBJECT, simulation=MONTAGE, space="mesh")
roi = analyzer.analyze_cortex(atlas="DK40", region="lh.insula")
print(roi.roi_mean, roi.roi_max, roi.roi_focality)
```

Everything else is in the [API reference]({{ site.baseurl }}/api/). A runnable copy of this workflow is the example notebook below.

## The example notebook

Every project gets one seeded notebook the first time you open the page,
`examples/example_workflow.ipynb`. It walks the app page by page — project, pre-processing,
Optimizer, Simulator, Analyzer, results — one cell per page, showing the single `tit` API call
each page's **Run** button makes. Cell 1 fetches the `ernie` example subject
([Example Data]({{ site.baseurl }}/wiki/example-data/)), so it runs without your own data.
The same calls are walked through in [The workflow in code](#example-workflow) above.

<a href="{{ site.baseurl }}/assets/notebooks/example_workflow.ipynb" download>&#11015; Download example_workflow.ipynb</a>
&nbsp;&nbsp;
<a href="https://github.com/idossha/TI-Toolbox/blob/main/tit/server/examples/example_workflow.ipynb">View on GitHub</a>

When a TI-Toolbox update ships a newer version, your copy is refreshed only if you never edited
it; an edited copy is yours. Deleting it is permanent; there is no "restore example".
