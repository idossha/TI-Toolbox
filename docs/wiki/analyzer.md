---
layout: wiki
title: Analyzer Module
permalink: /wiki/analyzer/
---

# Analyzer Module

The Analyzer module provides comprehensive analysis capabilities for TI (Temporal Interference) simulation results, supporting both mesh-based and voxel-based data analysis. It enables statistical analysis, visualization, and region-of-interest (ROI) studies for understanding field distributions and their effects.

## Overview

The Analyzer module consists of three main components:

- **MeshAnalyzer**: Analyzes SimNIBS mesh files (.msh) containing field data
- **VoxelAnalyzer**: Analyzes NIfTI files (.nii, .nii.gz, .mgz) containing field data  
- **Group Analyzer**: Batch processing for multiple subjects and comparative analysis

![TI Max Field Analysis]({{ site.baseurl }}/wiki/assets/analyzer/TI_max.png)
*Maximum TI field distribution showing peak intensity areas and spatial localization patterns*

## Key Features

### 🎯 Analysis Types

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

### 📊 Output Metrics

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

### Example Usage

```python
# Initialize mesh analyzer
analyzer = MeshAnalyzer(
    field_mesh_path="/path/to/field.msh",
    field_name="TI_max", 
    subject_dir="/path/to/m2m_subject",
    output_dir="/path/to/output"
)

# Analyze a cortical region
results = analyzer.analyze_cortex(
    atlas_type="DK40",
    target_region="superiorfrontal",
    visualize=True
)

# Analyze whole head
whole_head_results = analyzer.analyze_whole_head(
    atlas_type="DK40",
    visualize=True
)
```

![TI Field Components]({{ site.baseurl }}/wiki/assets/analyzer/TI_max_all.png)
*Comprehensive view of all TI field components including individual frequency contributions*

## Voxel-Based Analysis

The VoxelAnalyzer handles NIfTI format files and integrates with FreeSurfer atlases for detailed volumetric analysis.

### Features

- **NIfTI Support**: Direct analysis of .nii, .nii.gz, .mgz files
- **FreeSurfer Integration**: Automatic atlas region extraction
- **4D Data Handling**: Support for multi-volume datasets
- **Visualization Overlays**: Generation of ROI-specific NIfTI overlays

### Example Usage

```python
# Initialize voxel analyzer
analyzer = VoxelAnalyzer(
    field_nifti="/path/to/field.nii.gz",
    subject_dir="/path/to/subject",
    output_dir="/path/to/output"
)

# Analyze a spherical ROI
sphere_results = analyzer.analyze_sphere(
    center_coordinates=[10, 20, 30],
    radius=5,
    visualize=True
)

# Analyze a cortical region
cortex_results = analyzer.analyze_cortex(
    atlas_file="/path/to/atlas.mgz",
    target_region="Left-Hippocampus",
    visualize=True
)
```

![Normalized TI Field]({{ site.baseurl }}/wiki/assets/analyzer/TI_normal.png)
*Normalized TI field distribution highlighting relative field strength variations*

### Spherical ROI Analysis

The Analyzer provides comprehensive spherical ROI analysis with dual-field visualization capabilities, enabling precise targeting of specific brain regions with both TI_max and TI_normal field components.

#### TI_max Field Visualization

![Spherical TI_max Analysis]({{ site.baseurl }}/wiki/assets/analyzer/sphere_max.png)
*Spherical ROI analysis showing TI_max field distribution within a 10mm radius sphere at coordinates (-31.3, 24.0, -37.0)*

#### TI_normal Field Visualization

![Spherical TI_normal Analysis]({{ site.baseurl }}/wiki/assets/analyzer/sphere_normal.png)
*Spherical ROI analysis showing TI_normal field distribution for the same target region, demonstrating directional field components*

## Group Analysis

The Group Analyzer enables batch processing of multiple subjects for comparative studies and population-level analysis.

### Features

- **Batch Processing**: Analyze multiple subjects simultaneously
- **Centralized Logging**: Unified logging across all subjects
- **Comparative Analysis**: Cross-subject comparisons and summaries
- **Parallel Processing**: Efficient handling of large datasets

### Command Line Usage

```bash
# Group cortical analysis
python group_analyzer.py \
    --subject sub1 /path/to/m2m_sub1 /path/to/field1.msh \
    --subject sub2 /path/to/m2m_sub2 /path/to/field2.msh \
    --space mesh \
    --analysis_type cortical \
    --atlas_name DK40 \
    --whole_head \
    --output_dir /path/to/group_output
```

## Visualization Capabilities

The Analyzer module includes comprehensive visualization tools for interpreting analysis results.

### Statistical Plots

![Analysis Plots]({{ site.baseurl }}/wiki/assets/analyzer/analysis_plot.png)
*Comprehensive analysis plots showing field strength distributions and statistical summaries*

### ROI-Specific Analysis

![ROI Histogram]({{ site.baseurl }}/wiki/assets/analyzer/lh.insula_whole_head_roi_histogram.png)
*Region-of-interest histogram analysis for left hemisphere insula showing field distribution within target areas*

### Generated Visualizations

**Distribution Plots**
- Value distribution histograms for each ROI
- Statistical overlays (mean, std, percentiles)
- Comparison with whole-brain distributions

**Scatter Plots** 
- Cross-regional comparisons
- Sorted by field strength
- Color-coded by element count

**3D Visualizations**
- Mesh overlays for surface data
- NIfTI overlays for volumetric data
- ROI-specific field visualizations

**Focality Histograms**
- Selectivity analysis
- Target vs. off-target comparisons
- Statistical significance testing

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

The Analyzer seamlessly integrates with other TI-Toolbox modules:

**With Simulator**
- Direct analysis of simulation outputs
- Automatic field file detection
- Integrated workflow processing

**With Ex-Search/Flex-Search**
- Analysis of optimized montages
- Comparative evaluation of configurations
- Performance metrics extraction

**With GUI**
- User-friendly parameter selection
- Real-time progress monitoring
- Interactive result exploration

## Best Practices

### For Mesh Analysis
- Ensure SimNIBS m2m folder is properly configured
- Use appropriate atlas for your research question
- Enable visualization for publication-quality figures

### For Voxel Analysis  
- Verify coordinate system alignment between field and atlas
- Check field data units and scaling
- Use appropriate smoothing for noisy data

### For Group Analysis
- Standardize preprocessing across subjects
- Use consistent atlas and coordinate systems
- Plan adequate computational resources

## Troubleshooting

**Common Issues:**

1. **No voxels/nodes found in ROI**: Check coordinate systems and ROI parameters
2. **Atlas loading errors**: Verify atlas file format and path
3. **Memory issues**: Use smaller ROIs or reduce visualization complexity
4. **Field data misalignment**: Check affine transformations and coordinate systems

**Performance Tips:**

- Use spherical ROIs for initial exploration
- Enable visualization selectively for final analyses
- Consider subsampling for very large datasets
- Use group analysis for batch processing

## Command Line Interface

The Analyzer can be run from the command line for integration into analysis pipelines:

```bash
# Mesh-based analysis
python main_analyzer.py \
    --m2m_subject_path /path/to/m2m_folder \
    --montage_name montage_name \
    --space mesh \
    --analysis_type cortical \
    --atlas_name DK40 \
    --region superiorfrontal \
    --visualize

# Voxel-based analysis  
python main_analyzer.py \
    --m2m_subject_path /path/to/m2m_folder \
    --field_path /path/to/field.nii.gz \
    --space voxel \
    --analysis_type spherical \
    --coordinates 10 20 30 \
    --radius 5 \
    --visualize
```

## Related Documentation

- [Simulator Module]({{ site.baseurl }}/wiki/simulator/) - Generate field data for analysis
- [Ex-Search Module]({{ site.baseurl }}/wiki/ex-search/) - Optimization methods
- [Flex-Search Module]({{ site.baseurl }}/wiki/flex-search/) - Flexible electrode placement
- [Atlas Resampling]({{ site.baseurl }}/wiki/atlas-resampling/) - Atlas preparation

---

*The Analyzer module is continuously updated to support new analysis methods and visualization techniques. For the latest features and documentation updates, refer to the [TI-Toolbox repository](https://github.com/idossha/TI-toolbox).* 