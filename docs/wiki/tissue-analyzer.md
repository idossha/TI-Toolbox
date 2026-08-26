---
layout: wiki
title: Tissue Analyzer
permalink: /wiki/tissue-analyzer/
---

Tissue analysis is part of the pre-processing pipeline (`tit.pre.tissue_analyzer`, enabled with the *Tissue Analysis* option of the Pre-Processing tab). It provides volumetric assessment of different tissue types from the CHARM segmentation. This tool supports analysis of cerebrospinal fluid (CSF), bone, and skin tissues with automated volume and thickness calculations.

## Key Features

- **Multi-Tissue Support**: Analyze CSF, bone, and skin tissues. 
- **Volume Calculations**: Automatic volume measurements based on labeled voxel data in subject space
- **3D Thickness Analysis**: Distance transform-based thickness calculations with statistical summaries (experimental)
- **Publication-Quality Visualizations**: High-resolution figures for axial, coronal, and sagittal views



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

### 3. Analysis
- Calculate total tissue volume / thickness (experimental)
- Account for voxel dimensions from NIfTI header
- Provide voxel count statistics

## Calculation Methodology

**Volume Calculation Methodology**

Volume is calculated by multiplying the number of tissue voxels by the volume of each voxel:

$$
V_{\text{tissue}} \; [\mathrm{mm}^3] = n_{\text{voxels}} \times v_{\text{voxel}}
$$

Where:
- **Number of tissue voxels** $$n_{\text{voxels}}$$: count of all voxels in the filtered tissue mask
- **Voxel volume** $$v_{\text{voxel}}$$: product of the voxel dimensions from the NIfTI header, $$d_x \times d_y \times d_z$$

The voxel dimensions are extracted from the NIfTI header using `header.get_zooms()[:3]`, which provides the spatial resolution in millimeters for each dimension. This ensures accurate volume measurements regardless of the scan resolution.


**Thickness Calculation Methodology**

Thickness is calculated using a 3D Euclidean distance transform:

1. **Distance transform**: calculate the distance $$d$$ from each tissue voxel to the nearest boundary (background).
2. **Thickness**: $$t = 2d$$.

The algorithm uses scipy's `distance_transform_edt()` with voxel spacing sampling to account for anisotropic voxel dimensions. For each voxel within the tissue mask, the distance to the nearest boundary is computed. The thickness at each point is then defined as twice this distance, representing the full thickness of the tissue structure at that location.


### 4. Visualization and Reporting
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

<img src="{{ site.baseurl }}/assets/imgs/tissue-analyzer/bone_combined_publication_figure.png" alt="Bone Analysis Figure" style="width: 80%; max-width: 700px;">


## Data Requirements

### Input NIfTI Files
- **Format**: NIfTI (.nii or .nii.gz)
- **Segmentation**: Tissue labels from SimNIBS segmentation
- **File**: labeling_LUT.txt (optional but recommended)
- **Location**: Same directory as NIfTI, or parent directories

### Directory Structure
```
derivatives/
└── SimNIBS/
    └── sub-XX/
        └── m2m_sub-XX/
            ├── segmentation/
            │   ├── labeling.nii.gz      # Input segmentation (CHARM output)
            │   └── labeling_LUT.txt     # Label mapping (optional)
            └── ...
```


## Usage Workflow

### Python Usage

There is no standalone command; run it through the pre-processing pipeline (`run_tissue_analysis=True` in the JSON config for `simnibs_python -m tit.pre`, or the checkbox in the GUI) or call it directly:

```python
import logging
from tit.pre import run_tissue_analysis

results = run_tissue_analysis(
    "/mnt/my_project", "ernie",
    tissues=("bone", "csf", "skin"),   # DEFAULT_TISSUES
    logger=logging.getLogger("tit.pre"),
)
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
    'bone': {'name': 'Bone', 'labels': [515, 516], 'padding': 30, ...},
    'skin': {'name': 'Skin', 'labels': [511],      'padding': 35, ...},
}
```


## Integration Notes

### TI-Toolbox Structure
- **Output Organization**: Results organized under `derivatives/ti-toolbox/{tissue}_analysis/`
- **Logging Integration**: Compatible with shared TI-toolbox logging utilities
