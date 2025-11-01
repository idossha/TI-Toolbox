---
layout: wiki
title: Nilearn Visuals
permalink: /wiki/nilearn-visuals/
---

The Nilearn Visuals extension creates publication-ready visualizations of temporal interference (TI) stimulation fields using the Nilearn neuroimaging library. This tool generates high-quality brain images with multiple anatomical views, atlas contours, and customizable thresholds for scientific publications and presentations.

## Overview

Nilearn Visuals provides an intuitive interface for creating professional brain visualizations from group-averaged TI field data. The extension automatically handles data loading, averaging across subjects, and generates multiple visualization formats suitable for publication.

## Key Features

- **Group Averaging**: Automatically compute averages across multiple subjects/simulations
- **Multiple View Types**: Sagittal, coronal, axial, and glass brain projections
- **Atlas Integration**: Overlay anatomical atlas contours for anatomical reference
- **Flexible Thresholding**: Support for both absolute values and percentile-based cutoffs
- **High-Resolution Output**: Generate publication-quality PDF files
- **Batch Processing**: Process multiple subject-simulation pairs simultaneously

## User Interface

The extension provides a comprehensive GUI for configuring visualization parameters:

### Subject-Simulation Selection

Configure which subjects and simulations to include in the group average:

- **Add Individual Pairs**: Manually select subject-simulation combinations
- **Quick Add**: Batch-add the same simulation across multiple subjects
- **Import/Export**: CSV-based configuration management for reproducibility

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
   - Sub-directory: `hippocampus_stimulation`
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
- Automatically calculates thresholds based on data distribution
- Useful for comparing relative field strengths across different datasets
- Example: 95th-99.9th percentile captures the strongest 5% of field values

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

### Hippocampal Stimulation Group Average

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/wiki/assets/nilearn_visuals/hippocampus_group_average.png" alt="Hippocampal TI Field Group Average">
    <em>Group-averaged TI field distribution for hippocampal stimulation across 5 subjects</em>
  </div>
</div>

**Visualization Parameters:**
- Subjects: 5 (bilateral hippocampal targeting)
- Atlas: Harvard-Oxford Subcortical
- Threshold: 95th-99.9th percentile
- Views: Sagittal, coronal, axial slices

**Analysis Summary:**
- Peak field intensity: 4.2 V/m (99.9th percentile)
- Field focality: Concentrated in bilateral hippocampus
- Inter-subject consistency: High (coefficient of variation < 15%)

## Advanced Usage

### Custom Atlas Regions

Focus visualization on specific brain regions:

```python
# Extension automatically handles region selection
selected_regions = [35, 36]  # Left and right hippocampus
atlas_name = "harvard_oxford_sub"
```

### Large-Scale Group Analysis

For studies with many subjects:

1. **CSV Import**: Prepare subject-simulation configurations in CSV format
2. **Batch Processing**: Process all subjects simultaneously
3. **Memory Management**: Automatic memory optimization for large datasets

### Integration with Other Tools

Nilearn Visuals complements other TI-Toolbox components:

- **Flex Search**: Visualize optimized electrode configurations
- **Ex Search**: Display leadfield-based optimization results
- **Analyzer**: Create statistical maps of field distributions
- **Group Averaging**: Prepare data for visualization

## Troubleshooting

### Common Issues

**"No non-zero field values found"**
- Check that simulation files exist and contain valid TI field data
- Verify NIfTI file pattern matches your data structure
- Ensure simulations completed successfully

**Memory errors with large datasets**
- Process fewer subjects at once
- Use absolute thresholds instead of percentiles
- Consider subsetting data to regions of interest

**Atlas loading failures**
- Verify Nilearn installation: `pip install nilearn`
- Check network connectivity for atlas downloads
- Use local atlas files if available

### File Format Requirements

- **NIfTI Files**: Must be in MNI space with `.nii.gz` extension
- **File Pattern**: Default expects `grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz`
- **Data Type**: Floating-point values representing field intensity in V/m

## Performance Considerations

- **Processing Time**: ~2-5 minutes for 10 subjects (depends on system)
- **Memory Usage**: ~2-4 GB RAM for typical group sizes
- **Output Size**: PDF files are typically 5-20 MB each
- **Parallel Processing**: Single-threaded (future versions may add parallelization)

## Future Developments

Planned enhancements include:

- **Interactive Viewing**: Web-based interactive visualizations
- **Additional Atlases**: Support for custom atlas files
- **Statistical Overlays**: Integration with statistical analysis results
- **Animation Support**: Time-series visualization for dynamic fields
- **3D Rendering**: Advanced surface-based visualizations
