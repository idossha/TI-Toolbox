---
layout: wiki
title: Analyzer Module
permalink: /wiki/analyzer/
---

The Analyzer module provides analysis capabilities for TI simulation results, supporting both mesh-based and voxel-based data analysis. It provides descriptive statistics and visualization for understanding field distributions in the brain as a whole and specific regions of interest.

## Quantities of Interest

TI stimulation drives two (or more) electrode pairs at slightly different kHz frequencies. Neither carrier modulates neurons on its own; the quantity the TI community cares about is the **amplitude of the low-frequency beat** their sum produces where they overlap. Everything the analyzer reports is a spatial statistic of that one quantity, so it helps to see it once in the time domain and once in the spatial domain.

### Time domain: what a single value of `TI_max` is

<div style="max-width: 800px; margin: 0 auto;">
  <video controls muted playsinline style="width: 100%;" preload="metadata">
    <source src="{{ site.baseurl }}/assets/videos/TI_timeDomain.mp4" type="video/mp4">
  </video>
</div>
<em>Two kHz carriers, each too fast to modulate neurons on its own, sum where they overlap into a field whose amplitude beats at the difference frequency. The peak-to-trough swing of that envelope is the modulation depth -- the single number <code>TI_max</code> stores at every mesh node or voxel.</em>

- **`TI_max`** (V/m) -- the modulation depth of the beat envelope, maximised over direction at every mesh node or voxel. It is the default field of every simulation and of every analysis, and what "TImax" / "TInorm" mean in papers and in this toolbox's optimizers. For two pairs it is the closed form $$2\min(\lVert \mathbf{E}_1 \rVert, \lVert \mathbf{E}_2 \rVert)$$ when the fields are near-aligned, and smaller otherwise (Grossman et al. 2017; exact form on the [mTI page]({{ site.baseurl }}/wiki/mti/#field-math-and-critical-values)).
- **`TI_normal`** (V/m, mesh only) -- the same envelope measured along the local cortical surface normal, i.e. the component that runs along the apical dendrites of pyramidal cells. It is always $$\le$$ `TI_max`, can be much smaller where the field is tangential to the cortex (see below), and is only written for standard 2-pair TI runs.
<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/analyzer/analyzer_fig4c_ti_normal.png" alt="TI_normal as the projection of TI_max onto the surface normal" style="width: 100%; max-width: 700px;">
  <em>At each surface node, <code>TI_normal</code> is the component of the <code>TI_max</code> envelope along the local surface normal $$\hat{n}$$: where the field runs along $$\hat{n}$$ (left) the two are nearly equal, and where it runs tangential to the cortex (right) <code>TI_normal</code> collapses even though <code>TI_max</code> is unchanged. Figure 4C from <a href="https://www.brainstimjrnl.com/article/S1935-861X(25)00418-8/fulltext">Haber et al. 2026</a>.</em>
</div>

- **`TI_avg`, `hf_peak`, `hf_sar`** -- optional extra fields (direction-averaged envelope; carrier-exposure safety metrics). They are defined and discussed on the [mTI page]({{ site.baseurl }}/wiki/mti/#safety-metrics); the analyzer treats them as any other field, each in its own units.

### Spatial domain: how the analyzer summarises a field

Once `TI_max` exists at every node or voxel, an analysis reduces it to a handful of spatial statistics -- intensity inside the target, intensity everywhere else, and how concentrated the hot spot is:

| Quantity | `AnalysisResult` field | What it tells you |
|---|---|---|
| **Intensity in the ROI** | `roi_mean` (also `roi_max`, `roi_min`) | Area/volume-weighted mean `TI_max` inside the target. The number to compare against dose thresholds and between montages. |
| **Intensity outside the ROI** | `gm_mean` (also `gm_max`) | Mean over the **entire grey matter**. This is the analyzer's fixed non-ROI; the optimizers additionally accept a user-defined avoidance region. |
| **Focality** | `roi_focality` | `roi_mean / gm_mean`. 1 means the target is no hotter than the average cortex; higher is more selective. Same definition as ex-search's `Focality`. |
| **Normal component** | `normal_mean`, `normal_max`, `normal_focality` | The three statistics above recomputed on `TI_normal` (mesh, 2-pair TI only). |
| **Hot-spot level** | `percentile_95`, `percentile_99`, `percentile_99_9` | Field value below which 95 / 99 / 99.9 % of the grey-matter area lies. `percentile_99_9` is a robust "peak" that ignores single outlier elements. |
| **Hot-spot size** | `focality_50_area` ... `focality_95_area` | Grey-matter area ($$\mathrm{cm}^2$$; volume for voxel analysis) at or above 50 / 75 / 90 / 95 % of `percentile_99_9`. A small `focality_50_area` means a compact hot spot; a large one means the field is spread out, regardless of where the ROI is. |

Two things trip people up: the percentile and area metrics are whole-cortex descriptors and do not depend on the ROI at all, and every statistic is computed on whichever field you selected, in that field's units -- selecting `hf_sar` gives you means of a power-like quantity in $$(\mathrm{V/m})^2$$, not a field strength.

---

## Overview

The Analyzer module provides a single unified `Analyzer` class that handles both mesh and voxel analysis, plus a `run_group_analysis()` function for multi-subject comparison:

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/UI/UI_ana.png" alt="Analyzer User Interface" style="width: 100%; max-width: 600px;">
  <em>The Analyzer tab: pick a subject and simulation, choose mesh or voxel analysis, and define the target as a spherical, cortical, or subcortical ROI</em>
</div>

## Key Features

**Spherical ROI Analysis**

- Analyze field data within spherical regions of interest
- Customizable center coordinates and radius
- Multiple spheres: type `x,y,z,r` and press Enter / **Add Sphere** — each sphere becomes a removable chip. By default every sphere runs as its own separate analysis — N spheres produce N independent result sets
- **Combine spheres into one ROI**: tick this and the spheres are unioned into a single ROI, giving one analysis and one result set for all of them (overlapping spheres are not double-counted). The output folder is named `spheres<N>_...`, and long unions are shortened to the first sphere plus a hash
- Group analysis runs one ROI across all subjects: several spheres are accepted only when they are combined, otherwise extra spheres are rejected with a warning
- Support for subject-space and MNI coordinates (automatic transformation)
- Dual-field analysis: TI_max and TI_normal components (mesh space)
- Statistical metrics: mean, max, min, focality, percentiles, and area-based focality

**Cortical Analysis (Region Union)**

- Analyze one or more atlas regions as a single combined ROI — passing more than one region name unions their masks into one target, and the result's region name is the selected names joined with `+`
- **Combine regions into one ROI** (GUI, on by default): untick it to run one separate analysis per selected region instead of a union. Group analysis requires the combined form when more than one region is selected
- In mesh space, a bare region name (e.g. `cuneus`) expands to both hemispheres (`lh.cuneus` + `rh.cuneus`)
- Mesh atlases: `DK40`, `a2009s`, `HCP_MMP1`. Voxel atlases: `aparc.DKTatlas+aseg.mgz`, `aparc.a2009s+aseg.mgz`, `lh.hippoAmygLabels-T1.v22.mgz`, `rh.hippoAmygLabels-T1.v22.mgz`, `ThalamicNuclei.v13.T1.mgz`, plus the subject's own `segmentation/labeling.nii.gz`
- The four bundled MNI atlases (used elsewhere for subcortical ROI targeting) are not offered by the analyzer
- Detailed regional statistics and visualizations

**Tissue Selection**

- A Tissue selector (Gray Matter / White Matter / GM + WM) applies to **voxel space only** — it is disabled and forced to GM whenever Space is set to Mesh
- In voxel mode, the tissue choice selects which field file is loaded by filename prefix (`grey_` for GM, `white_` for WM, no prefix for GM + WM) and builds the corresponding tissue mask

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

All analysis calls return an `AnalysisResult` dataclass with the following fields (what each quantity means is explained in [Quantities of Interest](#quantities-of-interest)):

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

The analyzer handles multipolar (mTI) simulations with the same `Analyzer` class, the same `analyze_sphere` / `analyze_cortex` / `analyze_spheres` calls, and the same ROI types — there is no mTI mode to select. The only signal it uses is whether `{simulation}/mTI/mesh/` exists on disk.

### What it reads

| Space | mTI source | 2-pair TI source |
|---|---|---|
| Mesh | `mTI/mesh/surfaces/{sim}_mTI_central.msh` (field values) | `TI/mesh/surfaces/{sim}_TI_central.msh` |
| Voxel | `mTI/niftis/` (`grey_` / `white_` prefix per tissue) | `TI/niftis/` |

An mTI run also writes the intermediate per-dyad envelopes (`TI_AB`, `TI_CD`, ...) into `TI/mesh/`. Those are **not** what the analyzer reads and are not the mTI result — each is only the two-pair envelope of one dyad.

### What `mTI_max` means for the statistics

`mTI_max` is the joint $$K$$-pair modulation depth over **all** carriers at once, maximised over direction -- the same "beat envelope" quantity as `TI_max`, just with more carriers in the sum. The math, the deprecated recursive TI-of-TI form, carrier wiring and the safety metrics are all documented on the [mTI page]({{ site.baseurl }}/wiki/mti/#field-math-and-critical-values); what matters for analysis is:

- `TI_max` and `mTI_max` are aliases. Whichever spelling is requested, the analyzer resolves it to the on-disk name the detected simulation type actually wrote, so the Field selector lists it once.
- ROI statistics carried over from outputs produced by the deprecated `get_nTI_vectors` form are inflated (signed mean +38.6% at $$N = 4$$) and should be regenerated rather than compared.
- `mTI_max` depends on the [carrier wiring]({{ site.baseurl }}/wiki/mti/#carrier-wiring-channels) of the run, and the wiring is **not recorded** in the analysis output. Compare ROI numbers only across runs known to share one. `hf_peak`/`hf_sar` sum over all carriers regardless of wiring, so they stay comparable.
- `TI_avg`, `hf_peak` and `hf_sar` can be selected when the run wrote them and go through the identical ROI machinery, each in its own units (see [Quantities of Interest](#quantities-of-interest)).

### TI_normal

`TI_normal` is not computed for mTI — no normal-component mesh is written. Requesting it raises `FileNotFoundError` ("TI_normal is only computed for standard 2-pair TI simulations"), and `normal_mean`, `normal_max`, and `normal_focality` are always `None` in mTI results.

See [mTI]({{ site.baseurl }}/wiki/mti/) for the full description of mTI simulation, the envelope math, and multipolar search.

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
