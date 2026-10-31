---
layout: wiki
title: Cluster-Based Permutation Testing
permalink: /wiki/cluster-permutation-testing/
---

The Cluster-Based Permutation Testing extension performs non-parametric statistical analysis to identify brain regions with significant relationships between temporal interference (TI) stimulation fields and behavioral/clinical outcomes. This method provides robust control of family-wise error rates for both **group comparison** (binary outcomes) and **correlation analysis** (continuous outcomes).

## Before you start

- **Turn the panel on.** Enable **Cluster permutation** in **Settings ▸ Extensions** and reload
  the app; a panel toggle takes effect only after a reload. It then appears under **Extensions**
  in the navigation rail.
- **MNI-space NIfTIs are written when needed.** In the default **Space**, **MNI volume**, every
  subject's simulation is read as its MNI-space field NIfTI. A simulation writes one only when
  **Simulator ▸ Job settings ▸ Output files ▸ Also in MNI space** is ticked; otherwise the job
  writes it from the simulation's field mesh the first time it is needed, says so in its output,
  and keeps it ([Fields computed on demand]({{ site.baseurl }}/wiki/simulator/#fields-computed-on-demand)). A simulation that cannot provide it
  (its channel meshes are gone) is refused before the job starts, naming what is missing.
- **mTI simulations work too.** They are read from the simulation's `mTI/niftis/` folder
  (`grey_<sim>_mTI_MNI_MNI_mTI_max.nii.gz`); a **NIfTI file pattern** typed in the TI spelling
  (`_TI_`) is read as `_mTI_`.
- The **fsaverage surface** space needs each simulation's fsaverage projection instead; see
  [Analysis Space](#analysis-space).

## Import and export participant rows

Use **Import CSV/TSV**, **Export CSV**, or **Export TSV** below the Subjects header.
Export the current table for an editable template. The required header and an example CSV row are:

```csv
subject_id,simulation_name,response,effect_size,weight
101,L_Insula,1,,1
```

For TSV, use tabs instead of commas. Columns may be reordered, but all headers must be present
with exactly these names. Subject IDs omit `sub-`; simulation names match the project catalog.
`response` is 0 or 1. `effect_size` may be blank or a finite number; `weight` may be blank or a positive finite number. Quoted fields, embedded separators, UTF-8 BOM and Windows line endings are supported.
An import replaces the table only after every row validates. A malformed file leaves existing
rows unchanged. Import checks table structure and values; dataset files are checked by the job workflow.


## Key Features

- **Dual Analysis Modes**: Group comparison (responders vs non-responders) and correlation analysis (continuous outcomes)
- **Non-parametric Statistics**: No assumptions about data distribution
- **Family-wise Error Control**: Cluster-level correction for multiple comparisons
- **BIDS Integration**: Automatic data discovery and organization
- **Flexible Study Designs**: Binary classification or dose-response relationships
- **Parallel Processing**: Multi-core support for fast computation
- **Comprehensive Output**: Statistical maps, cluster analysis, and detailed reports

## Theoretical Background

### Why Cluster-Based Permutation Testing?

Traditional voxelwise statistical tests performed at each brain voxel create a massive multiple comparisons problem. With ~1,000,000 voxels in a typical brain analysis, even a 5% false positive rate would yield 50,000 false discoveries.

Cluster-based permutation testing addresses this by:
1. Performing voxelwise statistics (t-values or correlations)
2. Forming clusters of adjacent significant voxels **of the same sign**
3. Using cluster statistics (mass or size) instead of individual voxels
4. Building null distributions through data permutations
5. Controlling family-wise error at the cluster level

### Analysis Methods

#### Group Comparison (Binary Outcomes)
**Traditional Approach**: Compare electric field distributions between responders and non-responders.

- **Statistical Test**: Two-sample t-test at each voxel
- **Permutation Strategy**: Randomly reassign subjects to responder/non-responder groups
- **Null Hypothesis**: No difference in electric field strength between groups
- **Use Case**: Clinical trials with binary outcomes (response vs non-response)

#### Correlation Analysis (Continuous Outcomes)
**ACES Approach**: Identify brain regions where electric field strength correlates with continuous outcome measures.

- **Statistical Test**: Pearson/Spearman correlation at each voxel
- **Permutation Strategy**: Randomly shuffle outcome measures across subjects
- **Null Hypothesis**: No association between electric field strength and outcome
- **Use Case**: Dose-response studies with continuous measures (effect sizes, behavioral scores)

### Method Implementation

Both methods follow the Maris & Oostenveld (2007) framework and differ only in the voxelwise test
and in what a permutation shuffles:

1. **Voxelwise Testing**: t-statistics comparing the group means (group comparison), or the correlation between E-field and outcome (correlation)
2. **Cluster Formation**: Threshold at p < cluster_threshold to form clusters
3. **Cluster Statistics**: Calculate mass (signed sum of t-values within a sign-homogeneous cluster) or size (voxel count)
4. **Permutation Testing**: Randomly reassign subjects to groups (group comparison), or shuffle the outcome measures across subjects (correlation), 1,000+ times
5. **Null Distribution**: Build distribution of maximum cluster statistics under null
6. **Significance Testing**: Compare observed clusters to null distribution

## User Interface

### Analysis Mode Selection

**Analysis type** at the top of the panel picks the analysis:

- **Classification**: Binary group comparison (responders vs non-responders)
- **Correlation**: Continuous outcome analysis (dose-response relationships)

### Subject Configuration

Each participant row is a subject and one of its simulations (import and export: [above](#import-and-export-participant-rows)).
**Classification** adds a **Response** column (Responder / Non-responder); **Correlation** adds
**Effect size** and an optional **Weight** (e.g. a sample size).

### Statistical Parameters

#### Classification Mode
- **Analysis ▸ Test type**: Unpaired (independent groups) or Paired (repeated measures)
- **Analysis ▸ Alternative**: Two-sided, Greater or Less
- **Analysis ▸ Group 1 name** / **Group 2 name**: labels for the two groups (defaults `Responders` / `Non-Responders`)

#### Correlation Mode
- **Analysis ▸ Correlation type**: Pearson (parametric) or Spearman (non-parametric)
- **Analysis ▸ Apply per-subject weights**: weighted correlation using the **Weight** column

#### Both modes
- **Advanced ▸ Cluster threshold**: p-value for initial cluster formation (default: 0.05)
- **Advanced ▸ Cluster statistic**: Mass (sum of t-values) or Size (voxel count)
- **Advanced ▸ Permutations**: `n_permutations` (default: 1000)
- **Advanced ▸ Alpha**: cutoff for the permutation null distribution (default: 0.05)
- **Advanced ▸ Parallel workers**: `n_jobs` (default: -1, the global CPU limit from Settings; larger values are capped at it)
- **Advanced ▸ Tissue**: Grey matter, White matter or All tissue — which of each simulation's MNI NIfTIs is read (`grey_…`, `white_…`, or the unprefixed all-tissue file)
- **Advanced ▸ NIfTI file pattern**: leave blank to derive it from **Tissue**
- **Advanced ▸ Space**: MNI volume or fsaverage surface (below)
- **Advanced ▸ Atlas files** (optional, MNI volume): comma-separated file names of atlases shipped with TI-Toolbox (e.g. `HarvardOxford-sub-maxprob-thr25-1mm.nii.gz`); `analysis_summary.txt` then lists how many significant voxels fall in each of their regions

#### Analysis Space
Both modes accept `space = "mni"` (**MNI volume**, the default) or `"fsaverage"` (**fsaverage surface**, using the per-simulation fsaverage projections; `fsaverage_field` default `TI_max`, `fsaverage_spacing` default 5). Each subject needs its `fsaverage/sub-<id>_sim-<sim>_space-fsaverage<N>_fields.msh`; if one is missing the run stops before it starts and names the file — re-run that simulation with **Simulator ▸ Job settings ▸ Standard-space outputs ▸ Map fields to fsaverage** ticked. Projections written by versions before the `.msh` format are not read; re-run the projection for those simulations.

## Workflow Examples

### Classification Analysis: Responder vs Non-Responder

1. **Open tool**: **Extensions ▸ Cluster permutation** in the navigation rail (see [Before you start](#before-you-start))
2. **Select Mode**: **Analysis type ▸ Classification**
3. **Configure Subjects**:
   - Subject 001: Simulation "HIPP_L", Responder
   - Subject 002: Simulation "HIPP_L", Non-Responder
   - ... (10+ subjects total)
4. **Set Parameters**:
   - Test type: Unpaired
   - Permutations: 1,000
   - Cluster statistic: Mass
5. **Run Analysis**: Processing time depends on dataset size, permutations, and CPU cores

### Correlation Analysis: Dose-Response Relationship

1. **Open tool**: **Extensions ▸ Cluster permutation** in the navigation rail (see [Before you start](#before-you-start))
2. **Select Mode**: **Analysis type ▸ Correlation**
3. **Configure Subjects**:
   - Subject 001: Simulation "HIPP_L", Effect Size: 0.85
   - Subject 002: Simulation "HIPP_L", Effect Size: 0.72
   - ... (10+ subjects with continuous outcome measures)
4. **Set Parameters**:
   - Correlation type: Pearson
   - Use weights: Enabled (if applicable)
   - Permutations: 1,000
   - Cluster statistic: Mass
5. **Run Analysis**: Processing time depends on dataset size, permutations, and CPU cores

### Output Structure

Results are saved to `derivatives/ti-toolbox/stats/{analysis_type}/{analysis_name}/`:

#### Classification Output
```
group_comparison/hippocampus_responders_vs_nonresponders/
├── significant_voxels_mask.nii.gz          # Binary mask of significant voxels
├── pvalues_map.nii.gz                      # Uncorrected p-value map (-log10 scale)
├── average_responders.nii.gz               # Group average for responders
├── average_non_responders.nii.gz           # Group average for non-responders
├── difference_map.nii.gz                   # Responders - Non-responders
├── permutation_null_distribution.pdf       # Null distribution visualization
├── cluster_size_mass_correlation.pdf       # Cluster statistics
├── analysis_summary.txt                    # Complete statistical report
├── permutation_details.txt                 # Each permutation's group assignment and max cluster statistic
└── group_comparison_analysis_TIMESTAMP.log # Processing log
```

#### Correlation Output
```
correlation/hippocampus_effect_size_correlation/
├── significant_voxels_mask.nii.gz          # Binary mask of significant voxels
├── pvalues_map.nii.gz                      # Uncorrected p-value map (-log10 scale)
├── correlation_map.nii.gz                  # Correlation coefficient (r) map
├── t_statistics_map.nii.gz                 # T-statistic map
├── correlation_map_thresholded.nii.gz      # r inside significant clusters, 0 elsewhere
├── average_efield.nii.gz                   # Mean field over all subjects
├── permutation_null_distribution.pdf       # Null distribution visualization
├── cluster_size_mass_correlation.pdf       # Cluster statistics (only when clusters formed)
├── analysis_summary.txt                    # Complete statistical report
├── permutation_details.txt                 # Each permutation's effect-size shuffle and max cluster statistic
└── correlation_analysis_TIMESTAMP.log      # Processing log
```

#### fsaverage surface output
With `analysis_space = "fsaverage"` the run writes a surface map and tables instead of NIfTIs:
```
correlation/insula_dose_response/
├── surface_stats.msh             # fsaverage surface (lh, then rh) with node fields:
│                                 #   t, p, sig_mask, cluster_id, r (correlation only),
│                                 #   mean_field (correlation) or mean_responders /
│                                 #   mean_non_responders (classification)
├── surface_stats.msh.opt         # Gmsh view settings
├── surface_stats.json            # analysis type and name, field, spacing, subjects
│                                 #   (per group), permutations, alpha, threshold, statistic
├── significant_clusters.csv      # one row per significant cluster (id, size, stat, p, r)
├── null_distribution.csv         # max cluster statistic of each permutation
├── cluster_subject_values.csv    # subject_id, simulation, group|response, cluster_id,
│                                 #   mean_field — each subject's mean field in each cluster
└── *_analysis_TIMESTAMP.log
```
`cluster_id` is 0 outside clusters and otherwise the `id` in `significant_clusters.csv`.
Open `surface_stats.msh` in the Viewer (**Open in Tetravox** on the job) or Gmsh, and take
`cluster_subject_values.csv` to R or a spreadsheet for follow-up statistics and plots. To
paint the effect and cluster maps on the inflated cortex as PDFs, run
`tit.plotting.nilearn.render_surface_stats_result("…/surface_stats.msh", out_dir)` under
`simnibs_python`.

**Example classification findings (illustrative):**
- Significant cluster in left hippocampus (p = 0.008, 1,245 voxels)
- Significant cluster in right hippocampus (p = 0.012, 987 voxels)
- Trend-level cluster in left entorhinal cortex (p = 0.067, 615 voxels)

**Example correlation findings (illustrative):**
- Significant cluster in left hippocampus (r = 0.72, p = 0.003, 1,156 voxels)
- Significant cluster in right hippocampus (r = 0.68, p = 0.007, 892 voxels)
- Dose-response relationship between E-field strength and clinical improvement


<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/stats/stats_permutation_null_dist.png" alt="Permutation Null Distribution" style="width: 80%; max-width: 700px;">
</div>

### Example MNI-space output

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/stats/stats_efield_avg_with_cluster_MNI.png" alt="Cohort-average TI field with a significant cluster in MNI space" style="width: 100%; max-width: 850px;">
  <em>MNI T1 template with a cohort-level <code>TI_max</code> field average and a significant cluster from cluster-based permutation testing.</em>
</div>

## Technical Details

### Data Requirements

- **File Format**: NIfTI files in MNI space, written by the simulation (**Also in MNI space**) or by the job itself when the simulation did not ([Before you start](#before-you-start))
- **File Pattern**: Default `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz` (from **Tissue**), read from `TI/niftis/`, or as `grey_{simulation_name}_mTI_MNI_MNI_mTI_max.nii.gz` from `mTI/niftis/` for an mTI simulation
- **Data Type**: Electric field magnitude values
- **Analysis Types**: Both classification and correlation approaches supported

### How many subjects you need

A permutation test can only be as fine-grained as the number of ways the labels can be
rearranged, and with a handful of subjects that number is tiny. In a group comparison with
**three subjects** split 2-vs-1 there are exactly `C(3,1) = 3` relabellings, so the null
distribution has three members — one of which is your own data. The smallest cluster
p-value the design can ever produce is therefore `1/3` (about `0.33`), and the estimator the
toolbox actually uses is one notch more conservative still. No cluster can clear
`p < 0.05`, whatever the effect size.

So **zero significant clusters from three subjects is the correct answer, not a failure.**
The run is still worth doing — the uncorrected `pvalues_map.nii.gz` and the effect map
(`difference_map.nii.gz` for a group comparison, `correlation_map.nii.gz` and
`t_statistics_map.nii.gz` for a correlation) are real and show you where and how large the effect is — but cluster-level inference needs more subjects. As a
rule of thumb, a two-sided test at `α = 0.05` needs at least `1/0.05 = 20` distinct
relabellings, which a balanced group comparison first reaches at **three per group**
(`C(6,3) = 20`); six or more per group is where the null becomes finely enough resolved to
be informative.

### CSV files for Python scripts

The panel's **Import CSV/TSV** needs all five columns ([above](#import-and-export-participant-rows)).
The Python loaders `GroupComparisonConfig.load_subjects` and `CorrelationConfig.load_subjects`
(see [Scripting]({{ site.baseurl }}/wiki/scripting/#group-statistics)) read these shorter files.

#### Classification Mode CSV
Create `subjects_classification.csv`:

```csv
subject_id,simulation_name,response
001,HIPP_L,1
002,HIPP_L,0
003,HIPP_R,1
004,HIPP_R,0
```

- `response`: 1 = Responder, 0 = Non-Responder

#### Correlation Mode CSV
Create `subjects_correlation.csv`:

```csv
subject_id,simulation_name,effect_size,weight
001,HIPP_L,0.85,1.0
002,HIPP_L,0.72,0.8
003,HIPP_R,0.91,1.0
004,HIPP_R,0.65,1.2
```

- `effect_size`: Continuous outcome measure (e.g., effect size, % improvement)
- `weight`: Optional subject-specific weight (e.g., sample size, reliability measure)

### Statistical Implementation

#### Classification Analysis
- **Test**: Two-sample t-test (paired or unpaired)
- **Permutations**: Random group reassignment
- **Cluster Correction**: Family-wise error control at cluster level

#### Correlation Analysis
- **Test**: Pearson or Spearman correlation
- **Permutations**: Random outcome measure shuffling
- **Cluster Correction**: Family-wise error control at cluster level
- **Weights**: Optional weighted correlation analysis


## References

### General Methodology
- **Maris, E., & Oostenveld, R.** (2007). Nonparametric statistical testing of EEG-and MEG-data. *Journal of Neuroscience Methods*, 164(1), 177-190.
- **Nichols, T. E., & Holmes, A. P.** (2002). Nonparametric permutation tests for functional neuroimaging: a primer with examples. *Human Brain Mapping*, 15(1), 1-25.
- **Winkler, A. M., et al.** (2014). Permutation inference for the general linear model. *NeuroImage*, 92, 381-397.

### Group Comparison (Classification)
- **Bullmore, E. T., et al.** (1999). Global, voxel, and cluster tests, by theory and permutation, for a difference between two groups of structural MR images of the brain. *IEEE Transactions on Medical Imaging*, 18(1), 32-42.

### Correlation Analysis (ACES)
- **Baetens, K., Van Hoornweder, S., Berger, T. A., & Wischnewski, M.** (2024). ACES: Automated Correlation of Electric field strength and Stimulation effects for non-invasive brain stimulation. *Brain Stimulation*, 17(2), 473-475. doi:10.1016/j.brs.2024.04.003
- **Huang, Y., Liu, A. A., Lafon, B., Friedman, D., Dayan, M., Wang, X., Bikson, M., Doyle, W. K., Devinsky, O., & Parra, L. C.** (2017). Measurements and models of electric fields in the in vivo human brain during transcranial electric stimulation. *eLife*, 6, e18834. doi:10.7554/eLife.18834
