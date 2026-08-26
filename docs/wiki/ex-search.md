---
layout: wiki
title: Ex-Search TI Optimization Pipeline
permalink: /wiki/ex-search/
---

The Ex-Search module provides a high-performance, exhaustive search approach for Temporal Interference (TI) simulations. The public API is `run_ex_search(config: ExConfig) -> ExResult`.

## Overview

Ex-Search implements a true **exhaustive search** approach for Temporal Interference (TI) optimization, systematically evaluating all possible electrode combinations within user-defined constraints. Unlike sampling-based methods, ex-search guarantees finding the globally optimal montage configuration.

The implementation uses a single `ExSearchEngine` class that owns the full pipeline: leadfield loading, ROI resolution, TI field computation, and the simulation loop.

**Key Features:**
- **True Exhaustive Search**: Evaluates all electrode combinations x current ratios
- **Multiple EEG Nets**: Support for high-density (10:10) and 10-20 nets with automatic co-registration
- **ROI Analysis**: Spherical ROI definition (CSV centers, default radius 3mm) in subject or MNI coordinate space (`roi_coordinate_space`), plus volumetric atlas-region ROIs (`ExConfig.roi_atlas`) that can stand alone via an explicit empty `roi_names=[]`
- **Current Ratio Optimization**: Systematic testing of current ratios respecting channel limits
- **High-Performance Processing**: Memory-efficient in-memory calculations with real-time progress tracking
- **Comprehensive Metrics**: TImax, TImean, Focality analysis with automatic visualization
- **Proper Error Handling**: Custom exceptions instead of SystemExit for better integration

## Search Modes

Ex-Search supports two electrode assignment strategies:

### Bucketed Mode (Original)
Electrodes are pre-assigned to specific channels:
- **E1+**: Electrodes for positive channel 1
- **E1-**: Electrodes for negative channel 1
- **E2+**: Electrodes for positive channel 2
- **E2-**: Electrodes for negative channel 2

**Combinations**: $$N_1 \times N_2 \times N_3 \times N_4$$, where $$N_i$$ is the number of electrodes in bucket $$i$$.

### Pooled Mode (New)
All electrodes are pooled together and can be assigned to any channel position, with the constraint that each electrode is used only once per montage.

**Combinations**: $$\binom{N}{4} \times 4!$$, where $$N$$ is the total number of electrodes -- every 4-electrode subset in every channel assignment.

**Trade-off**: Larger search space and longer compute time but with absolute certainty to find optimal solution with given electrode space.

## User Interface

<img src="{{ site.baseurl }}/assets/imgs/UI/UI_ex.png" alt="Flex Search Interface" style="width: 80%; max-width: 700px;">

The interface provides controls for:
- **Subject Selection**: Choose from available subjects with automatic leadfield scanning
- **Leadfield Management**: View existing leadfields, create new ones, and show electrode configurations
- **ROI Selection**: A ROI Type toggle picks between two alternative targeting mechanisms, not companions -- **Sphere** (default) uses one or more spherical ROI CSVs sized by ROI Radius, with a Coordinate Space toggle (Subject / MNI, MNI space asks for confirmation before the run) and a "Combine selected ROIs into one target" checkbox that unions the selected ROIs into a single search (output named by joining the ROI names with `+`); **Atlas** targets a volumetric subcortical atlas region on its own page, backed by the same ROI picker widget used elsewhere in the GUI, restricted to its subcortical mode. Choosing Atlas mode drops the spherical ROI entirely (`roi_names=[]`); choosing Sphere mode drops the atlas target entirely (`roi_atlas=None`)
- **Electrode Setup**: Configure E1+, E1-, E2+, E2- with support for both GSN and 10-20 formats
- **Execution Control**: Run optimization with real-time progress tracking

Atlas ROI targets are always resolved in the subject's own space -- the picker has no MNI option here, because `ExConfig.AtlasROI` has no `atlas_space` field and the engine tests element barycenters against the mask directly. `roi_name` is required even in Atlas-only mode: it is the metric-key prefix and (with the net name) part of the output-directory label, so the GUI synthesizes one from the selected atlas label(s), e.g. `atlas_17` for a single region or `atlas_17_53` when more than one is selected.

---

## Multipolar (mTI) Mode

A Search Mode combo (TI (2-pair) / mTI (4-pair)) on the tab switches the whole run from `ExConfig`/`tit.opt.ex` to `MExConfig`/`tit.opt.mex`. Both ROI Types are available in mTI mode: `MExConfig` carries `roi_names` and `roi_atlas` just as `ExConfig` does, so an mTI run can target a spherical center, a volumetric atlas region, or an atlas region alone (`roi_names=[]`, leaving `roi_name` as a naming label that is never opened). Only the Combine ROIs checkbox is disabled under mTI -- the multipolar run path processes selected spheres one at a time. See [mTI]({{ site.baseurl }}/wiki/mti/) for the full mTI optimization workflow.

---

## Supported EEG Nets

Ex-Search automatically detects and supports multiple EEG electrode configurations:  
(EEG nets autoamtically co-registered during pre-processing)

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_EEG10-20_Okamoto_2004_net.png" alt="EEG 10-20 Network">
    <em>EEG 10-20 Okamoto 2004 electrode configuration - widely used standard with 32 electrodes</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_GSN256_net.png" alt="GSN 256 Network">
    <em>GSN-HydroCel 256 electrode configuration - high-density net for precise targeting</em>
  </div>
</div>

---

**Example Results** (`final_output.csv`, top 5 of 108 candidates by `Composite_Index`; sub-ernie, EEG10-10 Jurak leadfield, 5 mm spherical ROI at MNI (−38, 5, 0), total 2 mA in 0.5 mA steps, TI-Toolbox v2.4.0):

| Montage | Current_Ch1_mA | Current_Ch2_mA | TImax_ROI | TImean_ROI | TImean_GM | Focality | Composite_Index |
|---------|---------------|---------------|-----------|------------|-----------|----------|-----------------|
| F7_TP7 <> F5_CP3 | 1.0 | 1.0 | 0.3477 | 0.2173 | 0.1029 | 2.1115 | 0.4589 |
| F7_P7 <> F5_CP3 | 1.0 | 1.0 | 0.3540 | 0.2288 | 0.1161 | 1.9712 | 0.4510 |
| F7_P7 <> F5_P5 | 1.0 | 1.0 | 0.4015 | 0.2443 | 0.1323 | 1.8458 | 0.4509 |
| FT7_P7 <> F5_CP3 | 1.0 | 1.0 | 0.3304 | 0.2083 | 0.0994 | 2.0947 | 0.4363 |
| FT7_P7 <> FC5_CP3 | 1.0 | 1.0 | 0.3453 | 0.1979 | 0.0908 | 2.1800 | 0.4315 |

`Focality = TImean_ROI / TImean_GM` and `Composite_Index = TImean_ROI × Focality`. The `Montage` column in the CSV also carries the current split as a suffix (e.g. `F7_TP7 <> F5_CP3_I1-1.0mA_I2-1.0mA`).

![Ex-Search Distribution Analysis]({{ site.baseurl }}/assets/imgs/ex-search/ex-search_distribution.png)

*`montage_distributions.png` from the same run: TImax, TImean and focality across all 108 evaluated montages.*

![Ex-Search Intensity vs Focality]({{ site.baseurl }}/assets/imgs/ex-search/intensity_vs_focality_scatter.png)

*`intensity_vs_focality_scatter.png`: every candidate plotted as ROI mean intensity against focality, coloured by `Composite_Index`. The 1.0/1.0 mA splits form the high-intensity cluster on the right; unequal splits trade intensity for little focality gain.*

---

## Pipeline Workflow

### 1. EEG Net Selection
```
[INFO] Scanning available EEG nets for subject 101...
  1. BioSemi-64-10-10.csv
  2. BioSemi-128-A1.csv
  3. BioSemi-256-A1.csv
  4. EEG10-10_Cutini_2011.csv
  5. EEG10-10_UI_Jurak_2007.csv
  6. EEG10-20_Okamoto_2004.csv
  7. GSN-HydroCel-128.csv
  8. GSN-HydroCel-185.csv        # Default selection
  9. GSN-HydroCel-256.csv
 10. easycap_BC_TMS64_X21.csv
```

### 2. Leadfield Management
- **Intelligent Detection**: Automatic scanning of existing leadfields with HDF5 validation
- **Flexible Creation**: Generate leadfields for any supported EEG net with automated naming
- **Performance Optimization**: Efficient loading of large matrices (2-20GB) with memory monitoring

### 3. Current Ratio Optimization
The optimization systematically tests current ratios respecting channel limits:
```
Example (non-default; defaults are total_current=2.0 mA, current_step=0.5 mA, no channel_limit):
For total_current=2.0mA, step=0.2mA, limit=1.6mA:
  (1.6, 0.4), (1.4, 0.6), (1.2, 0.8), (1.0, 1.0),
  (0.8, 1.2), (0.6, 1.4), (0.4, 1.6)
```

### 4. Exhaustive Search Algorithm
- **Electrode Combinations**: $$N^4$$ combinations, where $$N$$ is the number of electrodes per channel group
- **Current Ratios**: Systematic testing across user-defined current steps
- **Total Combinations**: $$N_{\text{electrode combinations}} \times N_{\text{current ratios}}$$
- **In-Memory Processing**: No intermediate mesh files, direct field extraction
- **Progress Tracking**: Real-time monitoring with ETA calculations

### 5. Analysis & Visualization Pipeline
- **Run Time**: From minutes to hours depending on leadfield size and electrode combinations
- **Metrics Calculation**: `TImax_ROI`, `TImean_ROI`, `TImean_GM`, `Focality` (`TImean_ROI`/`TImean_GM`), and `n_elements` (ROI element count). The ROI mask itself is not restricted by tissue -- it is tested against all leadfield mesh elements, and leadfields are generated with `tissues=[1, 2]` (white + grey matter), so an ROI can include WM elements. Only the focality denominator, `TImean_GM`, is filtered to grey matter (mesh element tag `2`)
- **Visualization**: Automatic histogram generation (TImax, TImean, Focality distributions)
- **Output Formats**: JSON results, CSV summaries, PNG histograms

## Technical Implementation

### Architecture

The ex-search engine is built around a single `ExSearchEngine` class that consolidates what was previously split across multiple classes (`LeadfieldAlgorithms`, `LeadfieldProcessor`, `TIAlgorithms`, `TISimulator`). This class owns the full pipeline:

1. **Leadfield loading** via SimNIBS `TI_utils`
2. **ROI resolution**: OR-folds a mixed list of CSV centers, whole NIfTI/MGZ masks (voxel value > 0), and `(path, label)` atlas-region selections (voxel value == label) into a single region
3. **GM element identification** by tissue tag
4. **TI field computation** per montage combination
5. **Metric extraction** (TImax, TImean, Focality)

### Performance Characteristics
- **Scalability**: Handles large electrode combinations (1000+ montages) efficiently
- **Memory Usage**: Constant memory footprint regardless of combination count -- all computation is in-memory with no intermediate file I/O
- **Progress Tracking**: Real-time ETA calculation with rate monitoring
- **Graceful Interruption**: Signal handling (SIGINT/SIGTERM) for clean shutdown
