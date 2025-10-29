# Cluster-Based Permutation Testing for TI-Toolbox

This module performs non-parametric voxelwise statistical analysis to identify brain regions with significantly different current intensity between responders and non-responders using cluster-based permutation correction.

## Overview

Cluster-based permutation testing (CBP) is a powerful non-parametric method for controlling the family-wise error rate (FWER) when performing multiple comparisons across brain voxels. This implementation is fully integrated with the TI-Toolbox BIDS structure.

## Features

- **BIDS-compliant**: Automatically reads simulation data from TI-Toolbox directory structure
- **Flexible input**: Support for both GUI-based configuration and CSV input
- **Parallel processing**: Multi-core support for fast permutation testing
- **Comprehensive output**: Statistical maps, cluster analysis, and detailed reports
- **Atlas integration**: Optional overlap analysis with brain atlases

## Usage

### 1. GUI Interface

The easiest way to use cluster-based permutation testing is through the GUI extension:

1. Open TI-Toolbox GUI
2. Go to **Settings** → **Extensions**
3. Launch **"Cluster-Based Permutation Testing"**
4. Configure subjects and statistical parameters
5. Click **"Run Analysis"**

### 2. Python API

```python
from ti_toolbox.stats import cluster_permutation

# Define subject configurations
subject_configs = [
    {'subject_id': '070', 'simulation_name': 'ICP_RHIPPO', 'response': 1},
    {'subject_id': '071', 'simulation_name': 'ICP_RHIPPO', 'response': 0},
    {'subject_id': '072', 'simulation_name': 'ICP_RHIPPO', 'response': 1},
    {'subject_id': '073', 'simulation_name': 'ICP_RHIPPO', 'response': 0},
]

# Configure analysis
config = {
    'test_type': 'unpaired',           # or 'paired'
    'alternative': 'two-sided',         # 'two-sided', 'greater', 'less'
    'cluster_threshold': 0.05,          # p-value for cluster formation
    'cluster_stat': 'mass',             # 'mass' or 'size'
    'n_permutations': 1000,             # number of permutations
    'alpha': 0.05,                      # cluster-level significance
    'n_jobs': -1,                       # -1 = all cores
}

# Run analysis
results = cluster_permutation.run_analysis(
    subject_configs=subject_configs,
    analysis_name='hippocampus_responders_vs_nonresponders',
    config=config
)

print(f"Found {results['n_significant_clusters']} significant clusters")
print(f"Output directory: {results['output_dir']}")
```

### 3. CSV Input

Create a CSV file with your subject configurations:

```csv
subject_id,simulation_name,response
070,ICP_RHIPPO,1
071,ICP_RHIPPO,0
072,ICP_RHIPPO,1
073,ICP_RHIPPO,0
```

Then load it:

```python
results = cluster_permutation.run_analysis(
    subject_configs='path/to/subjects.csv',
    analysis_name='my_analysis',
    config=config
)
```

## Input Data Structure

The module expects simulation data in the TI-Toolbox BIDS structure:

```
/mnt/PROJECT_DIR/
└── derivatives/
    └── SimNIBS/
        └── sub-XXX/
            └── Simulations/
                └── SIMULATION_NAME/
                    └── TI/
                        └── niftis/
                            └── grey_SIMULATION_NAME_TI_MNI_MNI_TI_max.nii.gz
```

By default, the analysis uses the pattern:
- `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`

This can be customized with the `nifti_file_pattern` parameter:
```python
config = {
    'nifti_file_pattern': 'white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz',
    # ... other parameters
}
```

## Output Structure

Results are saved to:
```
/mnt/PROJECT_DIR/derivatives/ti-toolbox/stats/{analysis_name}/
```

Output files include:

1. **significant_voxels_mask.nii.gz** - Binary mask of significant voxels
2. **pvalues_map.nii.gz** - P-value map (-log10 scale for visualization)
3. **average_responders.nii.gz** - Average current intensity for responders
4. **average_non_responders.nii.gz** - Average current intensity for non-responders
5. **difference_map.nii.gz** - Difference map (responders - non-responders)
6. **permutation_null_distribution.pdf** - Visualization of null distribution
7. **cluster_size_mass_correlation.pdf** - Cluster size vs mass correlation
8. **analysis_summary.txt** - Detailed text report
9. **permutation_details.txt** - Detailed log of each permutation
10. **analysis_TIMESTAMP.log** - Timestamped analysis log

## Statistical Parameters

### Test Type
- **unpaired**: Independent samples t-test (different subjects in each group)
- **paired**: Paired samples t-test (same subjects in both conditions)

### Alternative Hypothesis
- **two-sided**: Test if groups are different (Responders ≠ Non-Responders)
- **greater**: Test if responders > non-responders
- **less**: Test if responders < non-responders

### Cluster Threshold
The p-value threshold for forming clusters. Typical values: 0.01, 0.05

### Cluster Statistic
- **mass**: Sum of t-values in cluster (more sensitive to effect magnitude)
- **size**: Number of voxels in cluster (more sensitive to spatial extent)

### Number of Permutations
Number of random permutations to perform. More permutations = more accurate p-values but longer computation time.
- Minimum: 10 (for quick tests)
- Recommended: 1000 (good balance)

### Alpha Level
Family-wise error rate (FWER) for cluster-level significance. Typical value: 0.05

### Parallel Jobs
Number of CPU cores to use:
- **-1**: Use all available cores (recommended)
- **1**: Sequential processing (slower but uses less memory)
- **N**: Use N cores

## Example Workflows

### Example 1: Basic Comparison

Compare hippocampal targeting between responders and non-responders:

```python
subjects = [
    {'subject_id': '070', 'simulation_name': 'ICP_RHIPPO', 'response': 1},
    {'subject_id': '071', 'simulation_name': 'ICP_RHIPPO', 'response': 0},
    # ... add more subjects
]

results = cluster_permutation.run_analysis(
    subject_configs=subjects,
    analysis_name='hippocampus_responders',
    config={'n_permutations': 1000}
)
```

### Example 2: White Matter Analysis

Analyze white matter instead of grey matter:

```python
config = {
    'nifti_file_pattern': 'white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz',
    'n_permutations': 1000,
}

results = cluster_permutation.run_analysis(
    subject_configs=subjects,
    analysis_name='white_matter_analysis',
    config=config
)
```

## Troubleshooting

### "File not found" errors

Check that:
1. Project directory is correctly set (`PROJECT_DIR_NAME` environment variable)
2. Simulation names match exactly (case-sensitive)
3. NIfTI files exist in the expected location
4. File pattern matches your data (adjust `nifti_file_pattern` if needed)

### "Need at least one responder and one non-responder"

Ensure your subject configurations have both:
- At least one subject with `response: 1` (responder)
- At least one subject with `response: 0` (non-responder)

### Memory errors

If analysis runs out of memory:
1. Reduce `n_jobs` to use fewer cores
2. Reduce `n_permutations` temporarily
3. Check that NIfTI files are not unnecessarily large

### Analysis takes too long

To speed up analysis:
1. Use `n_jobs: -1` to use all cores
2. Start with fewer permutations (e.g., 100) for testing
3. Increase permutations (1000-5000) for final analysis

## Technical Details

### Method

This implementation uses non-parametric cluster-based permutation testing (Maris & Oostenveld, 2007):

1. Perform voxelwise t-tests
2. Threshold at cluster_threshold to form clusters
3. Calculate cluster statistic (mass or size) for each cluster
4. Permute group labels many times
5. Build null distribution of maximum cluster statistics
6. Compare observed clusters to null distribution
7. Report clusters exceeding (1-alpha) percentile

### References

- Maris, E., & Oostenveld, R. (2007). Nonparametric statistical testing of EEG-and MEG-data. Journal of Neuroscience Methods, 164(1), 177-190.
- Nichols, T. E., & Holmes, A. P. (2002). Nonparametric permutation tests for functional neuroimaging: a primer with examples. Human Brain Mapping, 15(1), 1-25.

