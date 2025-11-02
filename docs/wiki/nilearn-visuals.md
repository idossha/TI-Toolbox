---
layout: wiki
title: Nilearn Visuals
permalink: /wiki/nilearn-visuals/
---

The Nilearn Visuals extension creates publication-ready visualizations of temporal interference (TI) stimulation fields using the Nilearn neuroimaging library. This tool generates high-quality brain images with multiple anatomical views, atlas contours, and customizable thresholds for scientific publications and presentations.

## Key Features

- **Group Averaging**: Automatically compute averages across multiple subjects/simulations
- **Multiple View Types**: Sagittal, coronal, axial, and glass brain projections
- **Atlas Integration**: Overlay anatomical atlas contours for anatomical reference
- **Flexible Thresholding**: Support for both absolute values and percentile-based cutoffs
- **High-Resolution Output**: Generate publication-quality PDF files

## User Interface

The extension provides a comprehensive GUI for configuring visualization parameters:

### Subject-Simulation Selection

Configure which subjects and simulations to include in the group average:

- **Add Individual Pairs**: Manually select subject-simulation combinations
- **Quick Add**: Batch-add the same simulation across multiple subjects

### Visualization Parameters

#### Output Configuration
- **Sub-directory**: Custom output folder within `derivatives/ti-toolbox/nilearn_visuals/`
- **Atlas Selection**: Choose from Harvard-Oxford (subcortical/cortical), AAL, or Schaefer atlases

#### Threshold Settings
- **Cutoff Mode**: Absolute V/m values or percentile-based thresholds
- **Minimum Cutoff**: Lower threshold for field visualization (default: 95th percentile or 0.3 V/m)
- **Maximum Cutoff**: Upper threshold for field visualization (default: 99.9th percentile or 5.0 V/m)

#### Region Selection
- **All Regions**: Visualize fields across the entire brain
- **Specific Regions**: Focus on individual atlas regions for targeted analysis

## Workflow Example

### Basic Group Visualization

1. **Launch Extension**: Settings → Extensions → "Nilearn Visuals"
2. **Configure Subjects**: Add subject-simulation pairs for averaging
3. **Set Parameters**:
   - Output directory: `hippocampus_stimulation`
   - Atlas: `harvard_oxford_sub`
   - Cutoff mode: Percentiles (95% - 99.9%)
4. **Generate Images**: Click "Generate Images" to process

### Output Structure

Results are saved to `derivatives/ti-toolbox/nilearn_visuals/{sub-directory}/`:

```
hippocampus_stimulation/
├── group_averaged_5_subjects.nii.gz          # Averaged NIfTI file
├── group_averaged_5_subjects_parameters.txt  # Complete parameter log
├── group_averaged_5_subjects_multiple_views.pdf    # Main visualization
└── group_averaged_5_subjects_glass_brain.pdf       # Glass brain view
```

## Technical Details

### Data Processing Pipeline

1. **Data Loading**: Load NIfTI files using pattern `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`
2. **Group Averaging**: Compute mean across all subject-simulation pairs
3. **Threshold Application**: Apply min/max cutoffs to field data
4. **Atlas Overlay**: Add anatomical contours using selected atlas
5. **Visualization Generation**: Create multiple view PDFs using Nilearn

### Thresholding Strategies

#### Percentile Mode
- Automatically calculates thresholds based on max value of the field
- Example: 95th-99.9th percentile captures the strongest 5% of field values
- Pro Tip: Never set upper threshold to 100% of max value as this can be an outlier

#### Absolute Mode
- Fixed V/m thresholds for consistent visualization
- Useful for comparing across different studies or protocols
- Example: 0.3-5.0 V/m shows fields above physiological thresholds

### Atlas Options

- **harvard_oxford_sub**: Harvard-Oxford subcortical atlas (9 regions)
- **harvard_oxford**: Full Harvard-Oxford cortical + subcortical atlas (48+ regions)
- **aal**: Automated Anatomical Labeling atlas (116 regions)
- **schaefer_2018**: Schaefer cortical parcellation (100-1000 regions)

## Example Results

### Visualization Types

The extension generates two main types of high-resolution visualizations:

<div class="image-container">
  <img src="{{ site.baseurl }}/wiki/assets/nilearn_visuals/glass_brain.png" alt="Glass Brain View" style="max-width: 50%; height: auto;">
  <em>Glass brain projection showing TI field distribution with transparency for 3D visualization</em>
</div>

<div class="image-container">
  <img src="{{ site.baseurl }}/wiki/assets/nilearn_visuals/sliced_brain.png" alt="Sliced Brain View" style="max-width: 50%; height: auto;">
  <em>Multi-slice anatomical view showing TI field distribution across sagittal, coronal, and axial planes</em>
</div>



### File Format Requirements

- **NIfTI Files**: Must be in MNI space with `.nii.gz` extension
- **File Pattern**: Default expects `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`
- **Data Type**: Floating-point values representing field intensity in V/m
