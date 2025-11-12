---
layout: wiki
title: Ex-Search TI Optimization Pipeline
permalink: /wiki/ex-search/
---

The Ex-Search module provides a semi-exaustive search approach for Temporal Interference (TI) simulations. The system features unified logging, multiple EEG net support, flexible leadfield management.

## Overview

Ex-Search utilizes leadfield-based optimization to determine optimal electrode configurations for TI stimulation based on:
- **Multiple EEG Nets**: Support for high-density (10:10) and 10-20 nets
- **ROI Analysis**: spherical only ROI definition with flexible radius specification



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
- **Intelligent Detection**: Automatic scanning of existing leadfields
- **Flexible Creation**: Generate leadfields for any supported EEG net
- **Performance Optimization**: Efficient loading of large matrices (2-20GB)

### 3. Optimization & Analysis Pipeline
- **Selection of Candidate Electrodes**: X electrodes per group, depending on search space
- **Run Time**: From minutes to hours, depending on leadfield size and number of candidates selected
- **Analysis & Visualization**: Automatic histogram generation with professional formatting
