---
layout: wiki
title: Extension System
permalink: /wiki/extension/
---

Optional tools are **panels** you switch on per project in **Settings &#9656; Optional tools**.
An enabled panel gets its own row under Extensions in the nav rail. Quick notes is a global drawer opened from the command palette or its shortcut.

<img src="{{ site.baseurl }}/assets/imgs/v3/settings.png" alt="Settings, with the Optional tools card" style="width: 100%; max-width: 1000px;">
<em>Settings (&#8984;,). Optional tools is a checkbox per panel; the Viewer engine card below it updates Tetravox without updating the toolbox.</em>

The panels are [Source]({{ site.baseurl }}/wiki/extension/), [Cluster
permutation]({{ site.baseurl }}/wiki/cluster-permutation-testing/), [NIfTI group
averaging]({{ site.baseurl }}/wiki/nifti-group-averaging/), [Nilearn
visuals]({{ site.baseurl }}/wiki/nilearn-visuals/) and the [3D visual
exporter]({{ site.baseurl }}/wiki/blender/).

Computational tools use the same layout as the main run pages: **inputs on the left**, with
the **plan and live terminal on the right**. Submitted jobs remain available in that terminal
after completion and when you return to the page. Source builds EEG forward solutions. Field mapping is an opt-in in each Simulator job’s settings. [Quick notes]({{ site.baseurl }}/wiki/quick-notes/) remains an autosaving note drawer, not a job runner.

The 3D visual exporter adds **Scene / Terminal** tabs. Its scene follows the selected export
type; see the [export preview guide]({{ site.baseurl }}/wiki/blender/#preview-and-export).

### Map existing fields from a notebook or terminal

In the supplied Jupyter environment, initialize the project and use the existing Python API:

```python
from tit import get_path_manager
from tit.source.config import FsavgMapConfig
from tit.source.fsaverage import project_fields_to_fsaverage

get_path_manager("/data/my-project")  # Use your project's path inside the container.
results = project_fields_to_fsaverage(
    [("101", "L_Insula")],
    FsavgMapConfig(fields=("TI_max", "TI_normal"), fsaverage_spacing=5),
)
```

For a terminal run, save that code as a script and run `simnibs_python map_fields.py`.
This maps existing outputs without rerunning simulation. For new simulations, enable
**Map fields to fsaverage** in the job’s settings before running it.

Two former extensions no longer exist as panels: **Electrode Placement** is now the Simulator's
[free-hand mode]({{ site.baseurl }}/wiki/electrode-placement/), and **Subject Info** is the
[Overview]({{ site.baseurl }}/wiki/overview/) page.

