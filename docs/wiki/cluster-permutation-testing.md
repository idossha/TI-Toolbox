---
layout: wiki
title: Cluster-Based Permutation Testing
permalink: /wiki/cluster-permutation-testing/
---

The Cluster-Based Permutation Testing extension performs non-parametric statistical analysis to identify brain regions with significant differences in temporal interference (TI) stimulation fields between experimental groups. This method provides robust control of family-wise error rates when performing voxelwise comparisons across the brain.

## Overview

Cluster-based permutation testing (CBP) is a powerful statistical approach for neuroimaging that addresses the multiple comparisons problem inherent in voxelwise statistical tests. The TI-Toolbox implementation automatically handles BIDS-compliant data organization and provides both GUI and programmatic interfaces for comprehensive statistical analysis.

## Key Features

- **Non-parametric Statistics**: No assumptions about data distribution
- **Family-wise Error Control**: Cluster-level correction for multiple comparisons
- **BIDS Integration**: Automatic data discovery and organization
- **Flexible Group Comparisons**: Responder vs non-responder, treatment vs control
- **Parallel Processing**: Multi-core support for fast computation
- **Comprehensive Output**: Statistical maps, cluster analysis, and detailed reports

## Theoretical Background

### Why Cluster-Based Permutation Testing?

Traditional voxelwise statistical tests (like t-tests) performed at each brain voxel create a massive multiple comparisons problem. With ~100,000 voxels in a typical brain analysis, even a 5% false positive rate would yield 5,000 false discoveries.

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

#### Computational Settings
- **Number of Permutations**: 1,000-10,000 (more = more accurate p-values)
- **Significance Level**: Family-wise error rate (default: 0.05)
- **Parallel Jobs**: CPU cores for parallel processing (default: all available)

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
4. **Run Analysis**: Process takes ~5-30 minutes depending on dataset size

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

## Statistical Interpretation

### Understanding Results

#### Significant Clusters
- **Cluster Mask**: Voxels that survive cluster-level correction
- **P-values**: Cluster-level significance (not voxel-level)
- **Cluster Statistics**: Mass/size values for each significant cluster

#### Effect Size Maps
- **Difference Map**: Raw group differences (Responders - Non-responders)
- **T-value Map**: Statistical strength at each voxel
- **Percentile Maps**: Relative field strength distributions

### Example Results

**Hippocampal Stimulation Response Analysis:**

| Metric | Value |
|--------|--------|
| Total subjects | 24 (12 responders, 12 non-responders) |
| Significant clusters | 3 |
| Largest cluster size | 2,847 voxels |
| Peak t-value | 4.32 |
| Analysis time | 12.5 minutes |
| Permutations | 1,000 |

**Key Findings:**
- Significant cluster in left hippocampus (p = 0.008, 1,245 voxels)
- Significant cluster in right hippocampus (p = 0.012, 987 voxels)
- Trend-level cluster in left entorhinal cortex (p = 0.067, 615 voxels)

## Technical Details

### Data Requirements

- **File Format**: NIfTI files in MNI space
- **File Pattern**: Default `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`
- **Data Type**: Field intensity values in V/m
- **Group Balance**: At least 1 subject per group (recommended: 8+ per group)

### Performance Optimization

- **Memory Usage**: ~4-8 GB RAM for typical datasets
- **Processing Time**: Scales with permutations × voxels × subjects
- **Parallel Speedup**: Near-linear scaling with CPU cores
- **Disk I/O**: Efficient streaming for large datasets

### Statistical Power

Power depends on:
- **Effect Size**: Larger differences → higher power
- **Sample Size**: More subjects → higher power
- **Spatial Extent**: Larger true effects → higher power
- **Permutations**: More permutations → more precise p-values

## Advanced Usage

### Custom Analysis Configurations

#### Programmatic Interface

```python
from stats import cluster_permutation

# Define subject configurations
subject_configs = [
    {'subject_id': '001', 'simulation_name': 'HIPP_L', 'response': 1},
    {'subject_id': '002', 'simulation_name': 'HIPP_L', 'response': 0},
    # ... more subjects
]

# Configure analysis
config = {
    'test_type': 'unpaired',
    'alternative': 'two-sided',
    'cluster_threshold': 0.05,
    'cluster_stat': 'mass',
    'n_permutations': 1000,
    'alpha': 0.05,
    'n_jobs': -1
}

# Run analysis
results = cluster_permutation.run_analysis(
    subject_configs=subject_configs,
    analysis_name='hippocampus_response_analysis',
    config=config
)
```

#### CSV-Based Configuration

Create `subjects.csv`:

```csv
subject_id,simulation_name,response
001,HIPP_L,1
002,HIPP_L,0
003,HIPP_R,1
004,HIPP_R,0
```

### Multiple Comparison Correction

The method controls family-wise error rate (FWER) at the cluster level:
- **FWER**: Probability of at least one false positive across all tests
- **Cluster-level**: Correction applied to clusters, not individual voxels
- **Permutation-based**: Exact control without parametric assumptions

### Effect Size Considerations

- **Mass vs Size**: Mass is more sensitive to strong, focal effects; size to diffuse effects
- **Threshold Selection**: More liberal thresholds (0.01) for exploratory; conservative (0.001) for confirmatory
- **Permutation Count**: 1,000 minimum; 5,000+ for publication-quality precision

## Troubleshooting

### Common Issues

**"Need at least one responder and one non-responder"**
- Ensure subjects are properly classified in the group assignment
- Check that response values are 0 (non-responder) or 1 (responder)
- Verify CSV import parsed classifications correctly

**Memory exhaustion**
- Reduce `n_jobs` to use fewer CPU cores
- Decrease number of permutations temporarily
- Process subsets of subjects if dataset is very large

**No significant clusters found**
- Check effect sizes in difference maps
- Consider more liberal cluster threshold (0.01 instead of 0.05)
- Verify groups are truly different (inspect average maps)
- Increase statistical power with more subjects

### Data Validation

**Check Input Files:**
- Verify NIfTI files exist in expected locations
- Confirm files contain valid floating-point data
- Check coordinate systems are consistent (MNI space)

**Validate Group Assignments:**
- Ensure balanced group sizes when possible
- Check for outliers that might affect results
- Verify no subject appears in multiple groups

## Integration with Other Tools

### Analysis Pipeline Integration

1. **Simulation**: Generate TI fields with SimNIBS
2. **Flex/Ex Search**: Optimize electrode positions
3. **Analyzer**: Extract field metrics and statistics
4. **CBP Testing**: Identify significant group differences
5. **Nilearn Visuals**: Create publication figures

### Statistical Reporting

The extension generates comprehensive reports suitable for:
- **Methods Sections**: Detailed statistical parameters
- **Results Sections**: Cluster statistics and significance levels
- **Supplementary Materials**: Complete permutation details

## References

- **Maris, E., & Oostenveld, R.** (2007). Nonparametric statistical testing of EEG-and MEG-data. *Journal of Neuroscience Methods*, 164(1), 177-190.
- **Nichols, T. E., & Holmes, A. P.** (2002). Nonparametric permutation tests for functional neuroimaging: a primer with examples. *Human Brain Mapping*, 15(1), 1-25.
- **Winkler, A. M., et al.** (2014). Permutation inference for the general linear model. *NeuroImage*, 92, 381-397.
