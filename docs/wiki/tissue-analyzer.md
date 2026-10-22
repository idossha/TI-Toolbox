---
layout: wiki
title: Tissue Analyzer
permalink: /wiki/tissue-analyzer/
---

Tissue analysis is a step of the pre-processing pipeline (`tit.pre.tissue_analyzer`), not an extension: tick **Pre-processing ▸ Structural ▸ Tissue analyzer** (off by default) and it runs in the same pre-processing run, after charm. It provides volumetric assessment of different tissue types from the CHARM segmentation. This tool supports analysis of cerebrospinal fluid (CSF), bone, and skin tissues with automated volume and thickness calculations.

## Key Features

- **Multi-Tissue Support**: Analyze CSF, bone, and skin tissues. 
- **Volume Calculations**: Automatic volume measurements based on labeled voxel data in subject space
- **3D Thickness Analysis**: Distance transform-based thickness calculations with statistical summaries (experimental)
- **Figures**: a thickness figure (axial, coronal and sagittal cuts through the tissue's centre of mass, coloured by thickness, plus a histogram) and a methodology figure, as PNG and PDF

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/tissue-analyzer/ernie-bone-thickness.png" alt="The bone thickness figure for subject ernie: axial, coronal and sagittal cuts through the skull coloured by its thickness, and a histogram of the thickness values with the statistics beside it" style="width: 100%; max-width: 1000px;">
  <em>The bone thickness figure the analyzer writes for subject ernie (<code>bone_thickness.png</code>). The three views cut through the centre of mass of the analysed bone (positions and axes in mm along the image grid). Every bone voxel of a cut takes the thickness measured at the nearest point of the bone's medial surface, from dark blue (2 mm) to yellow (12.8 mm): in the axial cut the skull is about 4 mm thick at the sides, 6 mm at the front and 8 mm at the back. The histogram (D) has one bar for each thickness the 1 mm grid can measure (2√k mm) and pools every medial voxel: mean 5.0 ± 2.2 mm over 389 cm³ of bone. The statistics and the legend sit beside it.</em>
</div>

## Analysis Pipeline

### 1. Tissue Identification
- Load segmented NIfTI data from SimNIBS derivatives
- Extract tissue masks using configured label numbers
- Load label names from labeling_LUT.txt for human-readable output

### 2. Spatial Filtering
- Identify brain reference regions (cortex and brainstem)
- Apply a 3D bounding box with a fixed per-tissue padding
- Filter out lower anatomy using Z-coordinate thresholds
- Focus analysis on relevant anatomical regions

### 3. Analysis
- Calculate total tissue volume / thickness (experimental)
- Account for voxel dimensions from NIfTI header
- Provide voxel count statistics

### 4. Visualization and Reporting
- Draw the thickness figure and the methodology figure (brain reference regions and the Z cutoff)
- Write a text report
- Save the figures as PNG and PDF

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
2. **Medial surface**: keep the voxels whose $$d$$ no neighbour exceeds, the middle of the tissue.
3. **Thickness**: $$t = 2d$$ on those medial voxels.

The algorithm uses scipy's `distance_transform_edt()` with voxel spacing sampling to account for anisotropic voxel dimensions. On the medial surface, $$d$$ is the radius of the largest ball that fits inside the tissue there, so twice it is the full thickness of the tissue at that location; the statistics and the histogram pool these medial voxels. On a 1 mm grid the distances can only be $$\sqrt{k}$$ mm for whole numbers $$k$$, so the thickness takes the values $$2\sqrt{k}$$ mm (2, 2.83, 3.46, 4, ...), and the histogram gives each of them its own bar.


## Output Files

### Analysis Results

Results are written to `derivatives/ti-toolbox/tissue_analysis/sub-<id>/`, one folder per tissue.
They do not appear on the **Results** page or among the job's artifacts; open the folder on disk.

```
derivatives/ti-toolbox/tissue_analysis/sub-<id>/
├── bone_analysis/
│   ├── bone_analysis.txt           # Volume (cm³), thickness statistics, labels analyzed
│   ├── bone_thickness.png          # Thickness in three views plus a histogram (PNG)
│   ├── bone_thickness.pdf          # Same figure (PDF)
│   ├── bone_methodology.png        # Brain reference regions and Z cutoff (PNG)
│   └── bone_methodology.pdf        # Same figure (PDF)
├── csf_analysis/                   # The same five files, csf_*
└── skin_analysis/                  # The same five files, skin_*
```


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
        └── m2m_XX/
            ├── segmentation/
            │   ├── labeling.nii.gz      # Input segmentation (CHARM output)
            │   └── labeling_LUT.txt     # Label mapping (optional)
            └── ...
```


## Usage Workflow

### Python Usage

There is no standalone command; run it through the pre-processing pipeline (`run_tissue_analysis=True` in the JSON config for `simnibs_python -m tit.pre`, or **Pre-processing ▸ Structural ▸ Tissue analyzer** in the app) or call it directly:

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

The label numbers and padding of each tissue are fixed in `TISSUE_CONFIGS` in
`tit/pre/tissue_analyzer.py`; the app offers no settings, and `run_tissue_analysis(tissues=...)`
only chooses which of `bone`, `csf` and `skin` to analyze.


## Integration Notes

### TI-Toolbox Structure
- **Output Organization**: Results organized under `derivatives/ti-toolbox/tissue_analysis/sub-<id>/<tissue>_analysis/`
- **Logging Integration**: Compatible with shared TI-toolbox logging utilities
