---
layout: wiki
title: Cluster-Based Permutation Testing
permalink: /wiki/cluster-permutation-testing/
---

The Cluster-Based Permutation Testing extension performs non-parametric statistical analysis to identify brain regions with significant differences in temporal interference (TI) stimulation fields between experimental groups. This method provides robust control of family-wise error rates when performing voxelwise comparisons across the brain.

## Key Features

- **Non-parametric Statistics**: No assumptions about data distribution
- **Family-wise Error Control**: Cluster-level correction for multiple comparisons
- **BIDS Integration**: Automatic data discovery and organization
- **Flexible Group Comparisons**: Responder vs non-responder, treatment vs control
- **Parallel Processing**: Multi-core support for fast computation
- **Comprehensive Output**: Statistical maps, cluster analysis, and detailed reports

## Theoretical Background

### Why Cluster-Based Permutation Testing?

Traditional voxelwise statistical tests (like t-tests) performed at each brain voxel create a massive multiple comparisons problem. With ~1,000,000 voxels in a typical brain analysis, even a 5% false positive rate would yield 50,000 false discoveries.

Cluster-based permutation testing addresses this by:
1. Performing voxelwise statistics (t-values)
2. Forming clusters of adjacent significant voxels
3. Using cluster statistics (mass or size) instead of individual voxels
4. Building null distributions through random group permutations
5. Controlling family-wise error at the cluster level

### Method Implementation

The analysis follows the Maris & Oostenveld (2007) framework:

1. **Voxelwise Testing**: Compute t-statistics at each voxel
2. **Cluster Formation**: Threshold at p < cluster_threshold to form clusters
3. **Cluster Statistics**: Calculate mass (sum of t-values) or size (voxel count)
4. **Permutation Testing**: Randomly reassign subjects to groups 1,000+ times
5. **Null Distribution**: Build distribution of maximum cluster statistics under null
6. **Significance Testing**: Compare observed clusters to null distribution

## User Interface

### Subject Configuration

Configure experimental groups through an intuitive interface:

- **Subject-Simulation Pairs**: Link each subject to their TI simulation
- **Group Classification**: Assign subjects as "Responder" or "Non-Responder"
- **CSV Import/Export**: Batch configuration management for reproducibility

### Statistical Parameters

#### Test Configuration
- **Test Type**: Unpaired (independent groups) or paired (repeated measures)
- **Alternative Hypothesis**: Two-sided, greater than, or less than
- **Cluster Threshold**: p-value for initial cluster formation (default: 0.05)
- **Cluster Statistic**: "Mass" (t-value sum) or "Size" (voxel count)
- **Significance Level**: cutoff for the permutation null distribution (default: 0.05)

## Workflow Example

### Responder vs Non-Responder Analysis

1. **Launch Extension**: Settings → Extensions → "Cluster-Based Permutation Testing"
2. **Configure Subjects**:
   - Subject 001: Simulation "HIPP_L", Responder
   - Subject 002: Simulation "HIPP_L", Non-Responder
   - ... (10+ subjects total)
3. **Set Parameters**:
   - Test type: Unpaired
   - Permutations: 1,000
   - Cluster statistic: Mass
4. **Run Analysis**: This cann take a while depending on dataset size, number of permutations, and number of cores assigned

### Output Structure

Results are saved to `derivatives/ti-toolbox/stats/{analysis_name}/`:

```
hippocampus_responders_vs_nonresponders/
├── significant_voxels_mask.nii.gz          # Binary mask of significant voxels
├── pvalues_map.nii.gz                      # P-value map (-log10 scale)
├── average_responders.nii.gz               # Group average for responders
├── average_non_responders.nii.gz           # Group average for non-responders
├── difference_map.nii.gz                   # Responders - Non-responders
├── permutation_null_distribution.pdf       # Null distribution visualization
├── cluster_size_mass_correlation.pdf       # Cluster statistics
├── analysis_summary.txt                    # Complete statistical report
├── permutation_details.txt                 # Detailed permutation log
├── analysis_TIMESTAMP.log                  # Processing log
└── config.json                             # Analysis configuration
```


**Key Findings:**
- Significant cluster in left hippocampus (p = 0.008, 1,245 voxels)
- Significant cluster in right hippocampus (p = 0.012, 987 voxels)
- Trend-level cluster in left entorhinal cortex (p = 0.067, 615 voxels)


![Permutation Null Distribution]({{ site.baseurl }}/assets/imgs/wiki_stats_permutation_null_dist.png)

## Technical Details

### Data Requirements

- **File Format**: NIfTI files in MNI space
- **File Pattern**: Default `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`
- **Data Type**: Field intensity values in V/m


#### CSV-Based Configuration

Create `subjects.csv`:

```csv
subject_id,simulation_name,response
001,HIPP_L,1
002,HIPP_L,0
003,HIPP_R,1
004,HIPP_R,0
```


## References

- **Maris, E., & Oostenveld, R.** (2007). Nonparametric statistical testing of EEG-and MEG-data. *Journal of Neuroscience Methods*, 164(1), 177-190.
- **Nichols, T. E., & Holmes, A. P.** (2002). Nonparametric permutation tests for functional neuroimaging: a primer with examples. *Human Brain Mapping*, 15(1), 1-25.
- **Winkler, A. M., et al.** (2014). Permutation inference for the general linear model. *NeuroImage*, 92, 381-397.
