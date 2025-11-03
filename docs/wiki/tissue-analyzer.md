---
layout: wiki
title: Tissue Analyzer
permalink: /wiki/tissue-analyzer/
---

The Tissue Analyzer extension provides volumetric assessment f different tissue types from segmented NIfTI data. This tool supports analysis of cerebrospinal fluid (CSF), bone, and skin tissues with automated volume and thickness calculations.

## Key Features

- **Multi-Tissue Support**: Analyze CSF, bone, and skin tissues. 
- **Volume Calculations**: Automatic volume measurements based on labeled voxel data in subject space
- **3D Thickness Analysis**: Distance transform-based thickness calculations with statistical summaries (experimental)
- **Publication-Quality Visualizations**: High-resolution figures for axial, coronal, and sagittal views

## Supported Tissue Types

### Cerebrospinal Fluid (CSF)
- **Labels**: Ventricles and cortical CSF regions (4, 5, 14, 15, 43, 44, 72, 24, 520)
- **Color Scheme**: Blues
- **Analysis Focus**: CSF spaces around brain regions

### Bone Tissue
- **Labels**: Cortical and cancellous bone (515, 516)
- **Color Scheme**: Heat map
- **Analysis Focus**: Skull bone thickness and volume

### Skin Tissue
- **Labels**: Skin surface (511)
- **Color Scheme**: Viridis
- **Analysis Focus**: Skin thickness and coverage

## Usage Workflow

### Command Line Usage

```bash
# Basic CSF analysis
python tissue_analyzer.py /path/to/segmented.nii.gz -t csf

# Bone analysis with custom output directory
python tissue_analyzer.py /path/to/segmented.nii.gz -t bone -o bone_results

# Skin analysis with custom labels
python tissue_analyzer.py /path/to/segmented.nii.gz -t skin -l 511 512
```

## Analysis Pipeline

### 1. Tissue Identification
- Load segmented NIfTI data from SimNIBS derivatives
- Extract tissue masks using configured label numbers
- Load label names from labeling_LUT.txt for human-readable output

### 2. Spatial Filtering
- Identify brain reference regions (cortex and brainstem)
- Apply 3D bounding box with configurable padding
- Filter out lower anatomy using Z-coordinate thresholds
- Focus analysis on relevant anatomical regions

### 3. Volume Analysis
- Calculate total tissue volume
- Account for voxel dimensions from NIfTI header
- Provide voxel count statistics

### 4. Thickness Analysis
- Use 3D distance transform algorithm
- Calculate thickness as twice the distance to nearest boundary
- Generate statistical summaries (mean, std, min, max)
- Create thickness distribution visualizations

### 5. Visualization and Reporting
- Generate publication-quality figures
- Create comprehensive analysis reports
- Export results in multiple formats (PNG, PDF, text)

## Output Files

### Analysis Results
```
output_directory/
├── csf_analysis_summary.txt          # Comprehensive analysis report
├── csf_thickness_analysis.png        # Thickness visualization (PNG)
├── csf_thickness_analysis.pdf        # Thickness visualization (PDF)
├── csf_extraction_methodology.png    # Methodology illustration (PNG)
├── csf_extraction_methodology.pdf    # Methodology illustration (PDF)
├── csf_combined_publication_figure.png  # Combined analysis figure (PNG)
└── csf_combined_publication_figure.pdf  # Combined analysis figure (PDF)
```

## Data Requirements

### Input NIfTI Files
- **Format**: NIfTI (.nii or .nii.gz)
- **Segmentation**: Tissue labels from SimNIBS segmentation
- **Coordinate System**: SimNIBS coordinate system (millimeters)

### Label Mapping
- **File**: labeling_LUT.txt (optional but recommended)
- **Location**: Same directory as NIfTI, or parent directories
- **Format**: Tab-separated values with label numbers and names
- **Purpose**: Human-readable label names in output

### Directory Structure
```
derivatives/
└── SimNIBS/
    └── sub-XX/
        └── m2m_sub-XX/
            ├── segmentation/
            │   ├── segmented.nii.gz     # Input segmentation
            │   └── labeling_LUT.txt     # Label mapping (optional)
            └── ...
```

## Configuration Options

### Tissue-Specific Parameters
```python
TISSUE_CONFIGS = {
    'csf': {
        'name': 'CSF',
        'labels': [4, 5, 14, 15, 43, 44, 72, 24, 520],
        'padding': 40,           # voxels
        'color_scheme': 'Blues',
        'tissue_color': [0, 0, 1],
        'brain_labels': [3, 42, 16]
    },
    # ... additional tissue configurations
}
```

### Custom Label Names
```python
# Override or add label names manually
custom_labels = {
    4: "Left-Lateral-Ventricle",
    5: "Left-Inf-Lat-Vent",
    511: "Skin"
}
analyzer.set_label_names(custom_labels)
```

## Visualization Features

### Combined Publication Figure
- **3×4 Layout**: Identification, extraction, and thickness panels
- **Three Views**: Axial, coronal, and sagittal slices
- **Color Coding**: Tissue-specific color schemes
- **Statistical Overlays**: Thickness statistics and distributions

### Methodology Illustrations
- **Step-by-Step**: Brain reference identification and tissue extraction
- **Color Legends**: Clear indication of included/excluded regions
- **Reference Lines**: Z-cutoff and bounding box visualizations

### Thickness Distributions
- **Histogram Plots**: Probability density distributions
- **Statistical Lines**: Mean, standard deviation, and percentiles
- **Publication Style**: High-resolution output for manuscripts

## Integration Notes

### TI-Toolbox Structure
- **Output Organization**: Results organized under `derivatives/ti-toolbox/{tissue}_analysis/`
- **Logging Integration**: Compatible with shared TI-toolbox logging utilities
- **Error Handling**: Comprehensive error handling with detailed logging
