---
name: ti-scripting
description: Python scripting API of TI-Toolbox (`tit` package) — SimulationConfig, FlexConfig, ExConfig, Analyzer, run_group_comparison, run_pipeline, JSON config runners. Use when writing or debugging scripts or notebooks that drive TI-Toolbox, or converting a GUI workflow to code.
user-invocable: false
---

# TI-Toolbox Scripting Reference

Full page: MCP `read_wiki_page("scripting")` (or /wiki/scripting/). This is the
condensed version; **verify field names against `read_source_file` before
emitting code** — `tit/sim/config.py`, `tit/opt/config.py`, `tit/analyzer/analyzer.py`,
`tit/stats/config.py`, `tit/pre/`.

## Where code runs

Inside the SimNIBS container: `docker exec -it simnibs_container bash`, then
`simnibs_python my_script.py`, JupyterLab (`NOTEBOOK`, http://localhost:8888, kernel
"SimNIBS + TI-Toolbox"), or Neovim with LSP. `tit` modules auto-initialise logging and
paths on import; the project root is discovered from the mount (`/mnt/<project>`).

## Imports

```python
from tit import get_path_manager
from tit.sim import SimulationConfig, Montage, run_simulation, load_montages
from tit.opt import FlexConfig, run_flex_search, ExConfig, run_ex_search
from tit.analyzer import Analyzer, run_group_analysis
from tit.stats import run_group_comparison, GroupComparisonConfig
from tit.pre import run_pipeline
```

## Preprocessing
```python
run_pipeline(subject_ids=["101"], convert_dicom=True, run_recon=True,
             create_m2m=True, parallel_recon=True)
```

## Simulation
```python
montages = load_montages(montage_names=["L_Insula"], eeg_net="GSN-HydroCel-185.csv")
# or explicit:
Montage(name="Custom", mode=Montage.Mode.NET,
        electrode_pairs=[("E010","E011"),("E012","E013")], eeg_net="GSN-HydroCel-185.csv")
cfg = SimulationConfig(subject_id="101", montages=montages,
        conductivity="scalar",            # scalar | vn | dir | mc  (vn/dir/mc need DTI)
        intensities=[1.0, 1.0],           # mA per pair
        electrode_shape="ellipse", electrode_dimensions=[8.0, 8.0],
        gel_thickness=4.0, rubber_thickness=2.0,
        output_fields=["TI_max"])         # + "TI_avg", "hf_peak", "hf_sar"
run_simulation(cfg)
```
2 pairs → TI, 4+ pairs → mTI (auto). Outputs: `Simulations/<name>/TI/{mesh,niftis}`,
plus MNI-space NIfTIs and an fsaverage projection.

## Flex-search (differential evolution)
```python
cfg = FlexConfig(subject_id="101", goal="mean",       # mean | max | focality | focality_tf
      postproc="max_TI",                              # max_TI | dir_TI_normal | dir_TI_tangential
      current_mA=2.0,
      electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8,8], gel_thickness=4),
      roi=FlexConfig.SphericalROI(x=-35, y=5, z=5, radius=10, use_mni=True),
      n_multistart=3, min_electrode_distance=5.0)
res = run_flex_search(cfg); res.best_value; res.output_folder
```
ROIs: `SphericalROI(..., volumetric=, tissues=)`, `AtlasROI(atlas_path, label, hemisphere)`,
`SubcorticalROI(atlas_path, label, tissues, atlas_space)`. Scalar fields accept lists to
union several regions. `focality_tf` = threshold-free focality (mean_ROI^(1+w)/p95_nonROI).

## Ex-search (exhaustive over leadfield)
```python
cfg = ExConfig(subject_id="101", leadfield_hdf="101_leadfield_EEG10-20_Okamoto_2004.hdf5",
      roi_name="L-Insula.csv",
      electrodes=ExConfig.PoolElectrodes(electrodes=["Fp1","Fp2","C3","C4","Cz","Pz","T7","T8"]),
      # or ExConfig.BucketElectrodes(e1_plus=[...], e1_minus=[...], e2_plus=[...], e2_minus=[...])
      total_current=2.0, current_step=0.2, channel_limit=1.2)
run_ex_search(cfg)
```
`roi_names=[...]` unions spherical CSVs; `roi_atlas=[ExConfig.AtlasROI(atlas_path, label)]`
adds volumetric regions (always subject space); `roi_coordinate_space="subject"|"mni"`.

## Analysis
```python
a = Analyzer(subject_id="101", simulation="L_Insula", space="voxel")   # voxel | mesh
r = a.analyze_sphere(center=(-35,5,5), radius=10, coordinate_space="MNI", visualize=True)
r = a.analyze_cortex(atlas="DK40", region="superiorfrontal", visualize=True)
run_group_analysis(subject_ids=[...], simulation="L_Insula", space="voxel",
                   analysis_type="spherical", center=..., radius=..., coordinate_space="MNI")
```

## Statistics (cluster-based permutation)
```python
subjects = GroupComparisonConfig.load_subjects("subjects.csv")
cfg = GroupComparisonConfig(analysis_name="active_vs_sham", subjects=subjects,
      test_type=GroupComparisonConfig.TestType.UNPAIRED,
      alternative=GroupComparisonConfig.Alternative.TWO_SIDED,
      cluster_stat=GroupComparisonConfig.ClusterStat.MASS,
      n_permutations=1000, tissue_type=GroupComparisonConfig.TissueType.GREY)
res = run_group_comparison(cfg)
```

## JSON config runners (what the GUI does)
`simnibs_python -m tit.<sim|opt.flex|opt.ex|opt.mex|analyzer|stats|pre> config.json`.
Configs are serialised dataclasses (`tit/config_io.py`, `_type` discriminators). The
easiest way to get a valid JSON is to run the GUI once and copy the file it wrote from
the run's output folder / logs.

## Example scripts in the repo
`scripts/preprocess.py`, `scripts/simulator.py`, `scripts/flex.py`, `scripts/ex.py`,
`scripts/analyzer.py`, `scripts/cluster_permutation.py` — read them with
`read_source_file("scripts/<name>.py")`.
