---
layout: wiki
title: Analyzer Module
permalink: /wiki/analyzer/
---

The Analyzer module provides analysis capabilities for TI simulation results, supporting both mesh-based and voxel-based data analysis. It provides descriptive statistics and visualization for understanding field distributions in the brain as a whole and specific region of interests.

## Important Quantities of Interest to Recognize
- [ ] **A. Mean TInorm Intensity in ROI**: Maximal modulation depth (aka TImax).
- [ ] **B. Mean TInorm Intensity in non-ROI**: Could be defind as entire cortex or a specific avoidance target.
- [ ] **C. Focality**: Ratio between A/B
- [ ] **D. TInormal**: Normal compoent of TInorm with respect to fifth layer of the cortex.

## Overview

The Analyzer module consists of three main components:

- **MeshAnalyzer**: Analyzes SimNIBS mesh files (.msh) containing field data
- **VoxelAnalyzer**: Analyzes NIfTI files (.nii, .nii.gz, .mgz) containing field data  
- **Group Analyzer**: Batch processing for multiple subjects and comparative analysis


## Key Features

**Spherical ROI Analysis**
- Analyze field data within spherical regions of interest
- Customizable center coordinates and radius
- Dual-field analysis: TI_max and TI_normal components
- Statistical metrics: mean, max, min, focality for both field types

**Cortical Analysis (Single Region)**
- Analyze specific brain regions using atlas parcellation
- Support for various atlases (DK40, HCP_MMP1, FreeSurfer)
- Detailed regional statistics and visualizations

**Whole Head Analysis**
- Comprehensive analysis across all brain regions
- Batch processing of all atlas regions
- Comparative analysis and ranking

### Output Metrics

For each analysis, the module provides comprehensive dual-field metrics:

**TI_max Field Analysis:**
- **Mean Value**: Average TI_max field strength in the ROI
- **Maximum Value**: Peak TI_max field intensity 
- **Minimum Value**: Lowest TI_max field intensity
- **Focality**: ROI average / whole brain average (selectivity measure)

**TI_normal Field Analysis:**
- **Normal Mean Value**: Average TI_normal field strength (directional component)
- **Normal Maximum Value**: Peak TI_normal field intensity
- **Normal Minimum Value**: Lowest TI_normal field intensity
- **Normal Focality**: TI_normal ROI average / whole brain average

**Additional Metrics:**
- **Element Count**: Number of voxels/nodes in the ROI
- **Visualization Files**: 3D mesh files with dual-field overlays

## Mesh-Based Analysis

The MeshAnalyzer works with SimNIBS mesh files and provides high-resolution analysis of field data on brain surfaces.

### Features

- **Surface Mesh Generation**: Automatic creation of gray matter surface meshes
- **Atlas Integration**: Support for SimNIBS native atlases (DK40, HCP_MMP1)
- **Field Extraction**: Analysis of TI_max and TI_normal fields
- **3D Visualization**: Generation of mesh files for 3D viewing

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/wiki/assets/analyzer/TI_max.png" alt="TI Max Field in ROI">
    <em>TInorm field distribution in ROI (Left Insula)</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/wiki/assets/analyzer/TI_normal.png" alt="TI Normal Field in ROI">
    <em>TInormal field distribution in ROI (Left Insula)</em>
  </div>
</div>

## Voxel-Based Analysis

The VoxelAnalyzer handles NIfTI format files and integrates with FreeSurfer atlases for detailed volumetric analysis.

### Features

- **NIfTI Support**: Direct analysis of .nii, .nii.gz, .mgz files
- **FreeSurfer Integration**: Automatic atlas region extraction
- **4D Data Handling**: Support for multi-volume datasets
- **Visualization Overlays**: Generation of ROI-specific NIfTI overlays


### Spherical ROI Analysis

The Analyzer provides comprehensive spherical ROI analysis with dual-field visualization capabilities, enabling precise targeting of specific brain regions with both TI_max and TI_normal field components.

#### Spherical Field Analysis Visualization

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/wiki/assets/analyzer/sphere_max.png" alt="Spherical TI_max Analysis">
    <em>Spherical ROI analysis showing TI_max field distribution within a 10mm radius sphere at coordinates (-31.3, 24.0, -37.0)</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/wiki/assets/analyzer/sphere_normal.png" alt="Spherical TI_normal Analysis">
    <em>Spherical ROI analysis showing TI_normal field distribution for the same target region, demonstrating directional field components</em>
  </div>
</div>

## Group Analysis

The Group Analyzer enables batch processing of multiple subjects for comparative studies and population-level analysis.

### Features

- **Batch Processing**: Analyze multiple subjects simultaneously
- **Centralized Logging**: Unified logging across all subjects
- **Comparative Analysis**: Cross-subject comparisons and summaries


### Statistical Analysis Visualization

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/wiki/assets/analyzer/analysis_plot.png" alt="Analysis Plots">
    <em>Comprehensive analysis plots showing field strength distributions and statistical summaries</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/wiki/assets/analyzer/lh.insula_whole_head_roi_histogram.png" alt="ROI Histogram">
    <em>Region-of-interest histogram analysis for left hemisphere insula showing field distribution within target areas</em>
  </div>
</div>


## Output Structure

The Analyzer generates a structured output directory:

```
analysis_output/
├── [region_name]/
│   ├── [region_name]_value_distribution.png
│   ├── [region_name]_focality_histogram.png
│   ├── [region_name]_ROI.nii.gz (voxel) or .msh (mesh)
│   └── analysis_results.csv
├── cortex_analysis_[atlas].png
├── whole_head_results_[atlas].csv
└── analysis_log.txt
```

### CSV Output Examples

The Analyzer generates comprehensive CSV files containing both TI_max and TI_normal field statistics for detailed quantitative analysis.

#### Spherical Analysis Results

Example output from spherical ROI analysis (10mm radius sphere):

```csv
Metric,Value
mean_value,0.577272543139917
max_value,0.7982711479293491
min_value,0.38333103543123126
focality,2.461358021318228
normal_mean_value,0.2788342877837438
normal_max_value,0.6472740802202535
normal_min_value,4.749416826041464e-05
normal_focality,2.6908262979169675
nodes_in_roi,1016
```

#### Cortical Analysis Results

Example output from cortical region analysis (left insula):

```csv
Metric,Value
mean_value,0.4805476971070656
max_value,0.7982711479293491
min_value,0.31956329890391955
focality,2.0489454122778112
normal_mean_value,0.3230791922418123
normal_max_value,0.6334826739681794
normal_min_value,4.749416826041464e-05
normal_focality,3.1178015935697405
```

### Field Analysis Metrics

**TI_max Field Metrics:**
- `mean_value`: Average TI_max field strength in the ROI
- `max_value`: Peak TI_max field intensity
- `min_value`: Minimum TI_max field intensity
- `focality`: ROI average / whole brain average (selectivity measure)

**TI_normal Field Metrics:**
- `normal_mean_value`: Average TI_normal field strength (directional component)
- `normal_max_value`: Peak TI_normal field intensity
- `normal_min_value`: Minimum TI_normal field intensity
- `normal_focality`: TI_normal ROI average / whole brain average

**Additional Information:**
- `nodes_in_roi`: Number of mesh nodes within the ROI
- `visualization_file`: Path to the generated mesh visualization file

## Integration with TI-Toolbox

- Direct analysis of simulation outputs
- Automatic field file detection
- Integrated workflow processing
- Automatic detection in Nifti Viewer

## Best Practices

### For Mesh Analysis
- Ensure SimNIBS m2m folder is properly configured
- Use appropriate atlas for your research question

### For Voxel Analysis  
- Verify coordinate system alignment between field and atlas
- Check field data units and scaling

### For Group Analysis
- Standardize preprocessing across subjects
- Use consistent atlas and coordinate systems
- Plan adequate computational resources

---

*The Analyzer module is continuously updated to support new analysis methods and visualization techniques. For the latest features and documentation updates, refer to the [TI-Toolbox repository](https://github.com/idossha/TI-toolbox).* 