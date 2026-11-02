---
layout: wiki
title: Scripting
permalink: /wiki/scripting/
---

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

Everything else is in the [API reference]({{ site.baseurl }}/api/); a runnable copy of this
workflow is on the [Notebooks]({{ site.baseurl }}/wiki/notebooks/) page.
