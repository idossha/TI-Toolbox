---
name: ti-scripting
description: Python scripting API of TI-Toolbox (`tit` package) — SimulationConfig, FlexConfig, ExConfig, Analyzer, run_group_comparison, run_pipeline, the tit.calc envelope functions, JSON config runners. Use when writing or debugging scripts or notebooks that drive TI-Toolbox, or converting a UI workflow to code.
user-invocable: false
---

# TI-Toolbox Scripting Reference

Full page: MCP `read_wiki_page("scripting")` (or /wiki/scripting/); a runnable tour
is `read_wiki_page("example-notebook")`. This is the condensed version; **verify
field names against `read_source_file` before emitting code** — `tit/sim/config.py`,
`tit/opt/config.py`, `tit/analyzer/analyzer.py`, `tit/stats/config.py`, `tit/pre/`.

## Where code runs

Everything runs **inside the container** (`idossha/ti-toolbox`: SimNIBS 4.x,
Python 3.11, numpy 1.26; no FSL, no ANTs, no X11, no FreeSurfer). Three ways in:

- **Notebooks in the app** — the Notebooks page (⌘6). A notebook is an `.ipynb`
  under `<project>/code/ti-toolbox/notebooks/`, executed by a Jupyter kernel the
  server owns *in* the container. The kernelspec is the same environment every job
  runs in, so `from tit import get_path_manager` works with nothing installed. A
  seeded tour lives at `code/ti-toolbox/notebooks/examples/getting-started.ipynb`.
  At most 2 kernels, 30-minute idle timeout. **There is no sandbox** — a kernel
  runs arbitrary code as the container's user.
- **A shell in the container** — `docker exec -it <container> bash`, then
  `simnibs_python my_script.py`. Use `simnibs_python`, never the host `python`.
- **The JSON runners** — `simnibs_python -m tit.<module> config.json`.

`tit` auto-initialises logging on import; the project root is discovered from the
mount (`/mnt/<project>`) or `PROJECT_DIR`.

## Starting the toolbox itself

```bash
./loader.sh   --project ~/datasets/000     # bootstrap; also finds a usable Python
python loader.py --project ~/datasets/000  # bootstrap from a checkout
tit launch    --project ~/datasets/000     # the installed form (tit/cli.py)
tit launch --status | --logs [--follow] | --stop
```
All three are the same thing: thin wrappers over `tit/launch.py`, which owns the
one run spec (root `docker-compose.yml`). Flags: `--project --port --image
--no-open --timeout --stop --status --logs --follow`. The host needs CPython ≥ 3.11
and the `docker` CLI — not SimNIBS, Node or Electron. The server comes up at
`http://127.0.0.1:8765`; `GET /api/health` returns `{"status": "ok"}`.

## Imports

```python
from tit import get_path_manager
from tit.sim import SimulationConfig, Montage, MontageMode, run_simulation, load_montages
from tit.opt import (FlexConfig, run_flex_search,
                     ExConfig, run_ex_search,
                     MExConfig, run_m_ex_search)
from tit.analyzer import Analyzer, run_group_analysis, select_field_file
from tit.stats import run_group_comparison, GroupComparisonConfig, run_correlation
from tit.pre import run_pipeline
from tit.calc import get_TI_vectors, get_TI_avg, get_TI_dir
from tit.fields import hf_peak, hf_sar
```

## The envelope API — exactly three functions

`tit.calc` was consolidated in v2.5.0 to **three** public functions. Each takes a
**list** of `2K` arrays of shape `(N, 3)`, **paired positionally**: each two
consecutive fields are the two channels sharing one carrier.

```python
get_TI_vectors(fields, psi=None)             # (N,3) modulation-amplitude vectors
get_TI_avg(fields, psi=None)                 # (N,)  direction-averaged envelope
get_TI_dir(fields, directions, psi=None)     # (N,)  envelope along given directions

get_TI_vectors([E1, E2])                     # K = 1: the exact closed form
get_TI_vectors([E1a, E1b, E2a, E2b])         # K = 2 carriers (mTI)
```
`psi` is a per-carrier envelope phase offset of shape `(K,)` in radians; `None`
means phase-aligned, and it is ignored at `K = 1`.

**Removed — do not emit these.** `get_nTI_vectors`, `get_mTI_vectors`,
`get_mTI_dir`, `get_magnitude_am`, the positional `get_TI_vectors(E1, E2)` form
(pass a list), and the `channels=` carrier-regrouping parameter. There is no
`montage.channels`: **wiring is positional — one field is one carrier**, which is
also how `hf_peak(*fields)` and `hf_sar(*fields)` in `tit.fields` read their input.

**Pair count**: an even number of electrode pairs, at least two —
2 = TI, 4 or more (even) = mTI (`tit.constants.is_valid_pair_count`).

## Preprocessing

```python
run_pipeline(subject_ids=["101"], convert_dicom=True, run_recon=True,
             create_m2m=True, parallel_recon=True)
```

## Simulation

```python
montages = load_montages(montage_names=["L_Insula"], eeg_net="GSN-HydroCel-185.csv")
# or explicit:
Montage(name="Custom", mode=MontageMode.NET,
        electrode_pairs=[("E010", "E011"), ("E012", "E013")],
        eeg_net="GSN-HydroCel-185.csv")

cfg = SimulationConfig(
    subject_id="101", montages=montages,
    conductivity="scalar",              # scalar | vn | dir | mc  (vn/dir/mc need DTI)
    intensities=[1.0, 1.0],             # mA per pair
    electrode_shape="ellipse", electrode_dimensions=[8.0, 8.0],
    gel_thickness=4.0, rubber_thickness=2.0,
    map_to_surf=True,                   # required — TI_normal needs surface overlays
    map_to_fsavg=True,
    output_fields=["TI_max"])           # + "TI_avg", "hf_peak", "hf_sar"
run_simulation(cfg)
```
2 pairs → TI, 4+ (even) → mTI, detected automatically. Outputs:
`Simulations/<name>/TI/{mesh,niftis}` plus MNI-space NIfTIs. `TI_normal` is written
to `<montage>_mTI_normal.msh` for mTI runs (via `get_TI_dir` along the cortical
normals) and is **mesh-only** — asking for it in voxel space is an error by design.

Free-hand montages come from `m2m_<id>/stim_configs/*.json`
(`{"name", "type": "U"|"M", "electrode_positions": {label: [x, y, z]}}`, subject-RAS
millimetres); `tit.sim.montage_sources.resolve_freehand_montage` uses only the first
four coordinates, so an mTI free-hand config is not resolvable by it.

## Flex-search (differential evolution — a *local* optimum)

```python
cfg = FlexConfig(
    subject_id="101",
    goal="mean",                       # mean | max | focality | focality_tf
    postproc="max_TI",                 # max_TI | dir_TI_normal | dir_TI_tangential
    electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8, 8],
                                         gel_thickness=4),
    roi=FlexConfig.SphericalROI(x=-35, y=5, z=5, radius=10, use_mni=True),
    n_multistart=3, min_electrode_distance=5.0)
res = run_flex_search(cfg)
res.success, res.best_value, res.output_folder, res.function_values
```
ROIs: `SphericalROI(..., volumetric=, tissues=)`, `AtlasROI(atlas_path, label,
hemisphere)`, `SubcorticalROI(atlas_path, label, tissues, atlas_space)`. Scalar
fields accept lists to union several regions. `focality_tf` = threshold-free
focality (`mean_ROI^(1+w) / p95_nonROI`). `cpus` does **not** parallelise the
search itself — only the multi-start restarts benefit.

## Ex-search (exhaustive over a leadfield — global within its discretisation)

```python
cfg = ExConfig(
    subject_id="101",
    leadfield_hdf="101_leadfield_EEG10-20_Okamoto_2004.hdf5",
    roi_name="L-Insula.csv",
    electrodes=ExConfig.PoolElectrodes(
        electrodes=["Fp1", "Fp2", "C3", "C4", "Cz", "Pz", "T7", "T8"]),
    # or ExConfig.BucketElectrodes(e1_plus=[...], e1_minus=[...],
    #                              e2_plus=[...], e2_minus=[...])
    total_current=2.0, current_step=0.5, channel_limit=1.2)
run_ex_search(cfg)
```
`roi_names=[...]` unions spherical CSVs; `roi_atlas=[ExConfig.AtlasROI(atlas_path,
label)]` adds volumetric regions (always subject space);
`roi_coordinate_space="subject"|"mni"`. `MExConfig` / `run_m_ex_search` is the
multipolar variant (no `total_current` / `current_step` / `channel_limit`).

**The run name is the directory** — a second run under the same `run_name` (or
`output_folder` for flex) overwrites the first in place. Put the ROI in the name
when more than one ROI is queued against one net.

## Analysis

```python
a = Analyzer(subject_id="101", simulation="L_Insula", space="voxel")   # voxel | mesh
r = a.analyze_sphere(center=(-35, 5, 5), radius=10,
                     coordinate_space="MNI", visualize=True)
r = a.analyze_cortex(atlas="DK40", region="superiorfrontal", visualize=True)

run_group_analysis(subject_ids=[...], simulation="L_Insula", space="voxel",
                   analysis_type="spherical", center=..., radius=...,
                   coordinate_space="MNI")
```
**Units:** `focality_50/75/90/95_area` is **cm² in mesh space and cm³ in voxel
space** — the `_area` names are kept for both deliberately, so scripts keep
working. Voxel values from v2.3.0–v2.5.0 are ten times too large; divide by 10 or
re-run. `total_area_or_volume` is mm² / mm³ and was always correct.

## Statistics (cluster-based permutation)

```python
subjects = GroupComparisonConfig.load_subjects("subjects.csv")
cfg = GroupComparisonConfig(
    analysis_name="active_vs_sham", subjects=subjects,
    test_type=GroupComparisonConfig.TestType.UNPAIRED,
    alternative=GroupComparisonConfig.Alternative.TWO_SIDED,
    cluster_stat=GroupComparisonConfig.ClusterStat.MASS,
    n_permutations=1000,
    tissue_type=GroupComparisonConfig.TissueType.GREY)
res = run_group_comparison(cfg)
```
Permutation p-values are `p = (b + 1) / (m + 1)`, so the floor at 1000 permutations
is `1/1001 ≈ 1e-3`, never 0. An old `p = 0.0000` means `p < 1/(m+1)`. All subjects'
NIfTIs must share a grid — a mismatched affine now raises `ValueError` naming the
subject rather than silently stacking different anatomy.

## fsaverage projection

```bash
simnibs_python -m tit.source fsavg_config.json
```
`tit.source.project_fields_to_fsaverage` projects `TI_max`, `TI_normal`, `hf_peak`,
`hf_sar` onto fsaverage post hoc (spacings 5/6/7), writing
`sub-<id>_sim-<sim>_space-fsaverage<spacing>_fields.npz`. Confirm the mTI coverage
against `read_source_file("tit/source/fsaverage.py")` before promising it — the
module and `docs/wiki/simulator.md` disagree today.

## JSON config runners (what the app does)

```bash
simnibs_python -m tit.<sim|opt.flex|opt.ex|opt.mex|analyzer|stats|pre|source> config.json
```
Configs are serialised dataclasses (`tit/config_io.py`, `_type` discriminators).
The easiest way to get a valid JSON is to run the job once from the app and copy
`code/ti-toolbox/jobs/<id>/spec.json` — its `config` object is exactly this file.
That directory also holds `status.json`, `events.jsonl` and `stdout.log` for the run.

## Example scripts in the repo

`scripts/preprocess.py`, `scripts/simulator.py`, `scripts/flex.py`, `scripts/ex.py`,
`scripts/analyzer.py`, `scripts/leadfield.py`, `scripts/pipeline.py`,
`scripts/cluster_permutation.py`, `scripts/blender.py` — read them with
`read_source_file("scripts/<name>.py")`.
