---
layout: wiki
title: Optional Tools
permalink: /wiki/extension/
---

Optional tools are **panels** you switch on per project in **Settings &#9656; Extensions**.
An enabled panel gets its own row under Extensions in the nav rail. Quick notes is not a panel: it is always available, as a global drawer opened from the command palette or its shortcut.

<img src="{{ site.baseurl }}/assets/imgs/v3/settings-extensions.png" alt="Settings, Extensions tab: a checkbox per feature panel, with every panel listed under Extensions in the sidebar" style="width: 100%; max-width: 1000px;">
<em>Settings (&#8984;,) &#9656; Extensions. One checkbox per panel; enabled panels appear under Extensions in the sidebar.</em>

The panels are [Source](#source-eeg-forward-model), [Cluster
permutation]({{ site.baseurl }}/wiki/cluster-permutation-testing/), [NIfTI group
averaging]({{ site.baseurl }}/wiki/nifti-group-averaging/), [Nilearn
visuals]({{ site.baseurl }}/wiki/nilearn-visuals/), the [3D visual
exporter]({{ site.baseurl }}/wiki/blender/) and [EEG caps]({{ site.baseurl }}/wiki/eeg-caps/).

Computational tools use the same layout as the main run pages: **inputs on the left**, with
the **plan and live terminal on the right**. Submitted jobs remain available in that terminal
after completion and when you return to the page. [Quick notes]({{ site.baseurl }}/wiki/quick-notes/) remains an autosaving note drawer, not a job runner.

The 3D visual exporter adds **Scene / Terminal** tabs. Its scene follows the selected export
type; see the [export preview guide]({{ site.baseurl }}/wiki/blender/#preview-and-export).

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/v3/extension-visual-exporter.png" alt="The 3D visual exporter panel: subject and simulation, the four export modes, and the cortical-regions options">
    <em>The 3D visual exporter covers cortical regions, field vectors, montages and sub-cortical structures.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/v3/extension-cluster-permutation.png" alt="The Cluster permutation panel: classification or correlation, a subject table with responses, and the test and cluster settings">
    <em>Cluster permutation provides non-parametric group-level statistics.</em>
  </div>
</div>

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/v3/extension-source.png" alt="The Source panel: a subject table showing which subjects have a head model, and the forward-solution settings" style="width: 100%; max-width: 1000px;">
  <em>Source builds EEG forward models for the selected subjects.</em>
</div>

## Source (EEG forward model)

**Source** builds an MNE-compatible EEG forward model from a subject's SimNIBS head model, for
EEG source reconstruction. Pick subjects that have a head model (`m2m_<id>`), an EEG net and the
fsaverage source spacing (5, 6 or 7). Each subject gets, under
`derivatives/SimNIBS/sub-<id>/forward/`:

- `sub-<id>_net-<net>-fwd.fif` — the forward solution (gain matrix);
- `sub-<id>_net-<net>-src.fif` — the cortical source space;
- `sub-<id>_net-<net>-morph.h5` — a source morph onto fsaverage;

plus the point-electrode leadfield (`*_leadfield.hdf5`) and the head↔MRI transform (`*-trans.fif`)
they are built from. The FEM leadfield is computed once per subject and net; a re-run reuses it.
Source needs MNE-Python, which the Docker image includes.

## fsaverage mapping (Simulator and API)

Mapping simulation fields to fsaverage is not an extension: for new simulations, enable **Map
fields to fsaverage** in a Simulator job's settings before running it. To map outputs that already
exist, without rerunning the simulation, use the Python API from a notebook or terminal:

```python
from tit import get_path_manager
from tit.source.config import FsavgMapConfig
from tit.source.fsaverage import project_fields_to_fsaverage

get_path_manager()  # auto-detects the project inside the container (/mnt/<name>)
results = project_fields_to_fsaverage(
    [("101", "L_Insula")],
    FsavgMapConfig(fields=("TI_max", "TI_normal"), fsaverage_spacing=5),
)
```

For a terminal run, save that code as a script and run `simnibs_python map_fields.py`. An explicit
path must exist: `get_path_manager("/mnt/<name>")` raises for a directory that does not.

Each projection is written beside its simulation as
`Simulations/<sim>/fsaverage/sub-<id>_sim-<sim>_space-fsaverage<N>_fields.msh`: the fsaverage
central surfaces (left hemisphere, then right) with each field as a node field, the layout
SimNIBS uses for its own `fsavg_overlays`. Open it in the Viewer (an MNI-space scene lists it
under the simulation's meshes) or in Gmsh, which picks up the `.msh.opt` view file beside it. A
`.json` sidecar with the same name records the subject, simulation, fields and whether the run
was a carrier-only control. To read the values in a script, run it with `simnibs_python`:

```python
from simnibs.mesh_tools import mesh_io

mesh = mesh_io.read_msh(path)
ti_max = mesh.field["TI_max"].value  # one value per fsaverage vertex, lh then rh
```

Electrode placement is the Simulator's
[free-hand mode]({{ site.baseurl }}/wiki/electrode-placement/), and subject information is the
[Overview]({{ site.baseurl }}/wiki/overview/) page; neither is an extension panel.

