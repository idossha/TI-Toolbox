---
layout: wiki
title: Ex-Search TI Optimization Pipeline
permalink: /wiki/ex-search/
---

The Ex-Search module provides a high-performance, exhaustive search approach for Temporal Interference (TI) simulations. The system features unified logging, multiple EEG net support, flexible leadfield management, and optimized computational efficiency.

## Overview

Ex-Search implements a true **exhaustive search** approach for Temporal Interference (TI) optimization, systematically evaluating all possible electrode combinations within user-defined constraints. Unlike sampling-based methods, ex-search guarantees finding the globally optimal montage configuration.

**Key Features:**
- **True Exhaustive Search**: Evaluates all N⁴ electrode combinations × current ratios (where N = electrodes per channel)
- **Multiple EEG Nets**: Support for high-density (10:10) and 10-20 nets with automatic co-registration
- **ROI Analysis**: Spherical ROI definition with configurable radius specification (default 3mm)
- **Current Ratio Optimization**: Systematic testing of current ratios respecting channel limits
- **High-Performance Processing**: Memory-efficient in-memory calculations with real-time progress tracking
- **Comprehensive Metrics**: TImax, TImean, Focality analysis with automatic visualization



## User Interface

<img src="{{ site.baseurl }}/assets/imgs/gallery/UI_ex.png" alt="Flex Search Interface" style="width: 80%; max-width: 700px;">

The interface provides controls for:
- **Subject Selection**: Choose from available subjects with automatic leadfield scanning
- **Leadfield Management**: View existing leadfields, create new ones, and show electrode configurations
- **ROI Configuration**: Add target regions with coordinates and manage multiple ROIs
- **Electrode Setup**: Configure E1+, E1-, E2+, E2- with support for both GSN and 10-20 formats
- **Execution Control**: Run optimization with real-time progress tracking

---

## Supported EEG Nets

Ex-Search automatically detects and supports multiple EEG electrode configurations:  
(EEG nets autoamtically co-registered during pre-processing)

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/wiki/ex-search/ex-search_EEG10-20_Okamoto_2004_net.png" alt="EEG 10-20 Network">
    <em>EGI 10-20 Okamoto 2004 electrode configuration - widely used standard with 32 electrodes</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/wiki/ex-search/ex-search_GSN256_net.png" alt="GSN 256 Network">
    <em>GSN-HydroCel 256 electrode configuration - high-density net for precise targeting</em>
  </div>
</div>

---

**Example Results:**

| Montage | TImax_ROI | TImean_ROI | TImean_GM | Focality |
|---------|------------|------------|-----------|----------|
| Fp1_Pz <> C3_C4 | 0.1748 | 0.1418 | 0.1595 | 0.8892 |
| Fp1_Pz <> C3_F4 | 0.2321 | 0.1480 | 0.1723 | 0.8587 |
| Fp1_Pz <> C3_P4 | 0.1632 | 0.1150 | 0.1637 | 0.7025 |
| Fp1_Pz <> F3_C4 | 0.1884 | 0.1558 | 0.1803 | 0.8643 |



![Ex-Search Distribution Analysis]({{ site.baseurl }}/assets/imgs/wiki/ex-search/ex-search_distribution.png)

---

## Pipeline Workflow

### 1. EEG Net Selection
```
[INFO] Scanning available EEG nets for subject 101...
  1. EGI10-10_Cutini_2011.csv
  2. EGI10-10_UI_Jurak_2007.csv
  3. EGI10-20_Okamoto_2004.csv
  4. GSN-HydroCel-185.csv        # Default selection
  5. GSN-HydroCel-256.csv
  6. easycap_BC_TMS64_X21.csv
```

### 2. Leadfield Management
- **Intelligent Detection**: Automatic scanning of existing leadfields with HDF5 validation
- **Flexible Creation**: Generate leadfields for any supported EEG net with automated naming
- **Performance Optimization**: Efficient loading of large matrices (2-20GB) with memory monitoring

### 3. Current Ratio Optimization
The optimization systematically tests current ratios respecting channel limits:
```
For total_current=2.0mA, step=0.2mA, limit=1.6mA:
  (1.6, 0.4), (1.4, 0.6), (1.2, 0.8), (1.0, 1.0),
  (0.8, 1.2), (0.6, 1.4), (0.4, 1.6)
```

### 4. Exhaustive Search Algorithm
- **Electrode Combinations**: N⁴ combinations where N is electrodes per channel group
- **Current Ratios**: Systematic testing across user-defined current steps
- **Total Combinations**: `electrode_combinations × current_ratios`
- **In-Memory Processing**: No intermediate mesh files, direct field extraction
- **Progress Tracking**: Real-time monitoring with ETA calculations

### 5. Analysis & Visualization Pipeline
- **Run Time**: From minutes to hours depending on leadfield size and electrode combinations
- **Metrics Calculation**: TImax_ROI, TImean_ROI, TImean_GM, Focality (TImean_ROI/TImean_GM)
- **Visualization**: Automatic histogram generation (TImax, TImean, Focality distributions)
- **Output Formats**: JSON results, CSV summaries, PNG histograms

## Technical Implementation

### Optimized Processing Architecture
The ex-search implementation features several performance optimizations:

- **Memory-Efficient Design**: In-memory field calculations eliminate intermediate file I/O
- **Itertools Integration**: Uses `itertools.product()` for efficient combination generation instead of nested loops

### Algorithm Efficiency
```
for processed, (e1_plus, e1_minus, e2_plus, e2_minus, current_ratio) in \
        enumerate(product(E1_plus, E1_minus, E2_plus, E2_minus, ratios), 1):
    # Process combination
```

### Performance Characteristics
- **Scalability**: Handles large electrode combinations (1000+ montages) efficiently
- **Memory Usage**: Constant memory footprint regardless of combination count
- **Progress Tracking**: Real-time ETA calculation with rate monitoring
- **Error Resilience**: Individual combination failures don't halt entire optimization
