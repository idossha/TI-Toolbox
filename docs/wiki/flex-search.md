---
layout: wiki
title: Flex Search Electrode Optimization
permalink: /wiki/flex-search/
---

**References:**
- [Original Paper: Weise K, Madsen KH, Worbs T, Knösche TR, Korshøj A, Thielscher A. A Leadfield-Free Optimization Framework for Transcranially Applied Electric Currents](https://www.sciencedirect.com/science/article/pii/S0010482525009990)

- [SimNIBS Implementation: Leadfield-free TES Optimization Tutorial](https://simnibs.github.io/simnibs/build/html/tutorial/tes_flex_opt.html#tes-flex-opt)

- [Data Source: Haber I, et al. Quantitative evaluation of transcranial electrical stimulation optimization methods](https://www.biorxiv.org/content/10.1101/2025.10.06.680781v3)


## Overview

Flex Search uses differential evolution optimization to determine the best electrode positions for TI stimulation based on:
- **Optimization Goals**: Maximize mean field, peak field, or focality (field in ROI / field in non-ROI)
- **Post-processing Methods**: Optimize for maximum TI field, normal component, or tangential component
- **ROI Definition**: Spherical coordinates, cortical atlas regions, or subcortical structures
- **Multi-start Optimization**: Run multiple optimization iterations to ensure robust results

## User Interface


<img src="{{ site.baseurl }}/assets/imgs/gallery/UI_flex.png" alt="Flex Search Interface" style="width: 80%; max-width: 700px;">

The interface provides comprehensive controls for:
- **Basic Parameters**: Subject selection, optimization goal, and post-processing method
- **Electrode Parameters**: Radius and current settings
- **ROI Definition**: Multiple methods for defining target regions
- **Stability Options**: Iteration limits, population size, and CPU utilization
- **Mapping Options**: EEG net electrode mapping capabilities

## Mean TI Field Optimization Demonstration

We demonstrate the effectiveness of flex-search by optimizing electrode positions for the same target ROI using different post-processing methods. The target was the left insula (region 35 of the DK40 atlas) with the goal of maximizing the mean TI field.

### Optimization Setup
- **Subject**: 102
- **Target ROI**: Left insula (DK40 atlas, region 35)
- **Goal**: Maximize mean field in ROI
- **Electrode**: 4mm radius, 8mA current

### Results: Maximum TI Field Optimization

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/wiki/flex-search/flex-search_max_TI_field.png" alt="Maximum TI Field">
    <em>Maximum TI field distribution showing optimization results</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/wiki/flex-search/flex-search_max_TI_ROI.png" alt="Maximum TI ROI Targeting">
    <em>ROI targeting analysis for maximum TI field optimization</em>
  </div>
</div>

**Optimization Summary:**

| Metric | Value |
|--------|--------|
| Final Goal Value | -2.320 |
| Duration | 25.1 minutes |
| Peak Field (99.9%) | 4.17 V/m |
| Median ROI Field | 2.21 V/m |

## Focality Optimization with Dynamic Thresholding

The focality optimization goal is a multi-objective function balancing ROI targeting with out-of-ROI field minimization:

### Non-ROI Definition Methods
- **Everything Else**: Uses the complement of the ROI (everything outside the target region)
- **Specific Region**: Define a custom non-ROI using the same methods as ROI definition (spherical, atlas, subcortical)

### Focality Thresholds - Critical for Optimization Success

As described in the [original paper](https://www.sciencedirect.com/science/article/pii/S0010482525009990), focality optimization is fundamentally a **constrained multi-objective problem** where:

- **Target Region (ROI)**: Field strength must exceed specified thresholds
- **Avoidance Region (Non-ROI)**: Field strength must remain below specified thresholds
- **Optimization Goal**: Maximize field intensity in ROI while minimizing field spread outside ROI

#### Threshold Configuration Options

- **Single Threshold**: Binary classification where field must be below threshold in non-ROI and above threshold in ROI
- **Dual Thresholds**: Independent thresholds for each region, allowing asymmetric optimization constraints
- **Dynamic Adaptation**: Thresholds automatically adjust based on field distribution characteristics during optimization

<img src="{{ site.baseurl }}/assets/imgs/wiki/flex-search/focality_thresholds.png" alt="Focality Threshold Analysis" style="width: 70%; max-width: 400px;">

**Focality optimization analysis**: Comparative evaluation of threshold strategies reveals critical insights: threshold selection profoundly impacts results, with relative thresholds (50% of peak) yielding 75% higher focality than fixed thresholds, while 80% thresholds reduce focality by 37%, compared to fixed thresholds (0.1V/m and 0.3V/m) highlighting the importance of threshold optimization for precise neuromodulation. Dynamic % based thresholds were derived automatically from an intial pass of mean TImax search and applied to the upper bound only. The lower bound was kept at 20% from that value. *Data regarding focality thresholds and optimization performance comes from the supplementary information of Haber et al. 2025.*

## Multi-Start Optimization

Flex Search supports multi-start optimization to ensure robust and reliable results by running multiple optimization iterations and selecting the best solution:

- **Multiple Runs**: Configure the number of optimization runs (default: 1, recommended: 3-5 for critical applications)
- **Best Solution Selection**: Automatically selects the optimization run with the lowest function value
- **Comprehensive Reporting**: Generates multi-start summary files with run-by-run analysis

<img src="{{ site.baseurl }}/assets/imgs/wiki/flex-search/multi-start.png" alt="Multi-Start Optimization Strategy" style="width: 50%; max-width: 400px;">

**Multi-start optimization validation**: Analysis demonstrates that running multiple independent optimizations with different random seeds yields superior solutions compared to single runs; 4.18% improvement in mean TImax. While statistically significant, the modest gains should be weighed against the increased computational cost. *Data regarding multi-start optimization performance comes from the supplementary information of Haber et al. 2025.*

## Electrode Mapping and Target Accessibility

The transition from unconstrained optimization solutions to practical electrode montages represents a critical step in clinical translation. While genetic algorithms can identify theoretically optimal electrode positions anywhere on the scalp, its transition to clinical application may be difficult. Our electrode mapping algorithm bridges this gap by finding the best approximation of optimized positions using available electrode sites. For this study, we utilized the inner 185 electrodes of the GSN-HydroCel-256 system (EGI/Philips), which provides high-density coverage. A combinatorial optimization method that solves the assignment problem in polynomial time. By minimizing the total Euclidean distance between optimized and standard positions, this approach ensures good representation of the intended field distribution while maintaining practical feasibility.

<img src="{{ site.baseurl }}/assets/imgs/wiki/flex-search/mapping_distance.png" alt="Electrode Mapping Distance Analysis" style="width: 70%; max-width: 600px;">

**Electrode mapping challenges**: Analysis of optimized electrode positions reveals depth-dependent mapping distances across anatomical targets, with subcortical structures like the hippocampus requiring significantly larger electrode separations (11.74 ± 5.33 mm) compared to cortical regions like the insula (7.30 ± 1.38 mm) or spherical ROIs (8.01 ± 1.43 mm). This pattern reflects the fundamental challenge of targeting deep brain structures with scalp electrodes, where optimal montages often requires large distances between electrodes which may be positioned on the lower scalp that does not have dense electrode coverage. *Data regarding electrode mapping distances comes from the supplementary information of Haber et al. 2025.* 
