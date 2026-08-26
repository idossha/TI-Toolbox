---
layout: wiki
title: Analyzer Module
permalink: /wiki/analyzer/
---

The Analyzer module provides analysis capabilities for TI simulation results, supporting both mesh-based and voxel-based data analysis. It provides descriptive statistics and visualization for understanding field distributions in the brain as a whole and specific regions of interest.

## Important Quantities of Interest to Recognize

- **A. Mean TImax (TInorm) Intensity in ROI**: Maximal modulation depth.
- **B. Mean TImax (TInorm) Intensity in non-ROI**: Could be defined as entire cortex or a specific avoidance target.
- **C. Focality**: Ratio between A/B
- **D. TInormal**: Normal component of TImax with respect to fifth layer of the cortex.

---

## Overview

The Analyzer module provides a single unified `Analyzer` class that handles both mesh and voxel analysis, plus a `run_group_analysis()` function for multi-subject comparison:

- **Analyzer**: Unified class that dispatches spherical and cortical ROI analyses to the appropriate mesh- or voxel-based implementation, returning a typed `AnalysisResult` dataclass
- **Group Analysis**: Batch processing for multiple subjects via `run_group_analysis()`

<img src="{{ site.baseurl }}/assets/imgs/UI/UI_ana.png" alt="Analyzer User Interface" style="width: 100%; max-width: 600px;">

## Key Features

**Spherical ROI Analysis**

- Analyze field data within spherical regions of interest
- Customizable center coordinates and radius
- Multi-sphere table: each row (`x,y,z,r`) runs as its own separate analysis — N rows produce N independent result sets, not a union of the spheres. Group analysis supports only one sphere row and rejects extra rows with a warning.
- Support for subject-space and MNI coordinates (automatic transformation)
- Dual-field analysis: TI_max and TI_normal components (mesh space)
- Statistical metrics: mean, max, min, focality, percentiles, and area-based focality

**Cortical Analysis (Region Union)**

- Analyze one or more atlas regions as a single combined ROI — passing more than one region name unions their masks into one target, and the result's region name is the selected names joined with `+`
- In mesh space, a bare region name (e.g. `cuneus`) expands to both hemispheres (`lh.cuneus` + `rh.cuneus`)
- Mesh atlases: `DK40`, `a2009s`, `HCP_MMP1`. Voxel atlases: `aparc.DKTatlas+aseg.mgz`, `aparc.a2009s+aseg.mgz`, `lh.hippoAmygLabels-T1.v22.mgz`, `rh.hippoAmygLabels-T1.v22.mgz`, `ThalamicNuclei.v13.T1.mgz`, plus the subject's own `segmentation/labeling.nii.gz`
- The four bundled MNI atlases (used elsewhere for subcortical ROI targeting) are not offered by the analyzer
- Detailed regional statistics and visualizations

**Tissue Selection**

- A Tissue selector (Gray Matter / White Matter / GM + WM) applies to **voxel space only** — it is disabled and forced to GM whenever Space is set to Mesh
- In voxel mode, the tissue choice selects which field file is loaded by filename prefix (`grey_` for GM, `white_` for WM, no prefix for GM + WM) and builds the corresponding tissue mask

**Unified Mesh + Voxel Handling**

- Single `Analyzer` class automatically dispatches to mesh or voxel implementation based on the `space` parameter
- Mesh analysis: area-weighted statistics on cortical surface meshes
- Voxel analysis: volumetric statistics on NIfTI data with FreeSurfer atlas integration

---

## Mesh-Based Analysis

When `space="mesh"`, the `Analyzer` works with SimNIBS mesh files and provides high-resolution analysis of field data on brain surfaces.

### Features

- **Surface Mesh Generation**: Automatic creation of gray matter surface meshes via `msh2cortex` (cached per instance)
- **Atlas Integration**: Support for SimNIBS native atlases (DK40, a2009s, HCP_MMP1)
- **Field Extraction**: Analysis of TI_max and TI_normal fields
- **3D Visualization**: Generation of mesh files for 3D viewing

### Cortical ROI Analysis

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_TI_max.png" alt="TI Max Field in ROI">
    <em>TInorm field distribution in ROI (Left Insula)</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_TI_normal.png" alt="TI Normal Field in ROI">
    <em>TInormal field distribution in ROI (Left Insula)</em>
  </div>
</div>

### Spherical ROI Analysis

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_sphere_max.png" alt="Spherical TI_max Analysis">
    <em>Spherical ROI analysis showing TI_max field distribution within a 10mm radius sphere at coordinates (-31.3, 24.0, -37.0)</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_sphere_normal.png" alt="Spherical TI_normal Analysis">
    <em>Spherical ROI analysis showing TI_normal field distribution for the same target region, demonstrating directional field components</em>
  </div>
</div>

---

## Voxel-Based Analysis

When `space="voxel"`, the `Analyzer` handles NIfTI format files and integrates with FreeSurfer atlases for detailed volumetric analysis.

### Features

- **NIfTI Support**: Direct analysis of .nii, .nii.gz, .mgz files
- **FreeSurfer Integration**: Automatic atlas region extraction and resampling
- **Visualization Overlays**: Generation of ROI-specific NIfTI overlays

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_voxel_montage_1.png" alt="Spherical TI_max Analysis">
    <em>Right Hippocampus ROI analysis showing TI_max field distribution given a 1mA:1mA stimualtion</em>
  </div>
</div>

---

### Statistical Analysis Visualization

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_lh.insula_whole_head_roi_histogram.png" alt="ROI Histogram">
    <em>Region-of-interest histogram analysis for left hemisphere insula showing field distribution within target areas</em>
  </div>
</div>

### AnalysisResult Fields

All analysis calls return an `AnalysisResult` dataclass with the following fields:

**Core Identifiers:**

- `field_name`: Name of the field analyzed (e.g. "TI_max")
- `region_name`: Name of the ROI
- `space`: "mesh" or "voxel"
- `analysis_type`: "spherical" or "cortical"

**TI_max Field Metrics:**

- `roi_mean`: Area/volume-weighted average TI_max in the ROI
- `roi_max`: Peak TI_max field intensity in the ROI
- `roi_min`: Minimum TI_max field intensity in the ROI
- `roi_focality`: ROI mean / GM mean (selectivity measure)
- `gm_mean`: Area/volume-weighted average across entire grey matter
- `gm_max`: Maximum TI_max value across entire GM

**TI_normal Field Metrics (mesh only):**

- `normal_mean`: Average TI_normal field strength in the ROI
- `normal_max`: Peak TI_normal field intensity in the ROI
- `normal_focality`: TI_normal ROI mean / TI_normal GM mean
- Absent (`None`) for mTI simulations — see [mTI Analyses](#mti-analyses) below

**Percentile Metrics:**

- `percentile_95`, `percentile_99`, `percentile_99_9`: Field value at each percentile

**Focality Area Metrics:**

- `focality_50_area`, `focality_75_area`, `focality_90_area`, `focality_95_area`: Area/volume above $$X\%$$ of the 99.9th percentile value (in $$\mathrm{cm}^2$$)

**Size Information:**

- `n_elements`: Number of mesh nodes or voxels in the ROI
- `total_area_or_volume`: Total area (mesh, $$\mathrm{mm}^2$$) or volume (voxel, $$\mathrm{mm}^3$$) of the ROI

---

## mTI Analyses

The analyzer detects an mTI (4-pair) simulation automatically — the only signal it checks is whether `{simulation}/mTI/mesh/` exists. There is no separate mode to select; the same `Analyzer` class and the same `analyze_sphere` / `analyze_cortex` calls are used for TI and mTI.

- `TI_max` and `mTI_max` are treated as aliases for the same quantity — the analyzer resolves whichever spelling the detected simulation type actually wrote to disk, regardless of which alias is requested
- `TI_normal` is not computed for mTI simulations, so it cannot be selected as a field, and `normal_mean`, `normal_max`, and `normal_focality` are always absent (`None`) from mTI results

See [mTI]({{ site.baseurl }}/wiki/mti/) for the full description of mTI simulation and search.

---

## Group Analysis

The `run_group_analysis()` function enables batch processing and comparative analysis across multiple subjects and montages, returning a `GroupResult` object.

### Flexible Group Combinations

Group analysis supports **arbitrary combinations** of subjects and montages:

- **Same subject x Multiple different montages**: Compare different stimulation configurations within the same individual
- **Multiple subjects x Same montage**: Assess inter-subject variability for a specific stimulation protocol
- **Multiple subjects x Different montages**: Full factorial design comparing both subject variability and montage effects

### Features

- **MNI Coordinate Support**: Automatically transform MNI coordinates to each subject's native space
- **Comprehensive Comparisons**: Automatic generation of statistical comparisons, rankings, and visualizations
- **Centralized Logging**: Consolidated logging across all subjects and analyses
- **Progress Tracking**: Real-time progress monitoring with timing information

---

## Mesh Analysis Quick Inspection with Gmsh Integration

The analyzer now includes **direct Gmsh integration** for easy visualization and inspection of mesh analysis results.

### Features

- **One-Click Launch**: Directly launch Gmsh from the GUI to inspect mesh analysis results
- **Automatic Mesh Detection**: Automatically finds and loads mesh files (.msh) from completed analyses
- **Subject/Simulation Selection**: Dropdown selectors for choosing specific subjects, simulations, and analysis types

### Supported Analysis Types

The Gmsh integration works with the analyzer's two mesh-based analysis types:

- Spherical ROI analyses with generated mesh overlays
- Cortical region analyses with atlas-based parcellations

There is no separate "whole head" analysis type — the Analyzer supports only `analysis_type` `spherical` and `cortical`. A whole-head field-distribution histogram is generated as a by-product of every analysis (mesh or voxel), alongside the ROI-specific outputs.
