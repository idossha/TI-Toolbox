---
layout: wiki
title: Flex Search Electrode Optimization
permalink: /wiki/flex-search/
---

# Flex Search Electrode Optimization

The Flex Search module provides advanced electrode optimization for temporal interference (TI) stimulation, allowing users to find optimal electrode positions for targeting specific regions of interest (ROIs) while maximizing different components of the TI field.

## Overview

Flex Search uses differential evolution optimization to determine the best electrode positions for TI stimulation based on:
- **Optimization Goals**: Maximize mean field, peak field, or focality in target ROI
- **Post-processing Methods**: Optimize for maximum TI field, normal component, or tangential component
- **ROI Definition**: Spherical coordinates, cortical atlas regions, or subcortical structures

## User Interface

![Flex Search Interface]({{ site.baseurl }}/wiki/assets/flex-search/flex-search_UI.png)

The interface provides comprehensive controls for:
- **Basic Parameters**: Subject selection, optimization goal, and post-processing method
- **Electrode Parameters**: Radius and current settings
- **ROI Definition**: Multiple methods for defining target regions
- **Stability Options**: Iteration limits, population size, and CPU utilization
- **Mapping Options**: EEG net electrode mapping capabilities

## Example: TI Field Optimization Comparison

We demonstrate the effectiveness of flex-search by optimizing electrode positions for the same target ROI using different post-processing methods. The target was the left insula (region 35 of the DK40 atlas) with the goal of maximizing the mean TI field.

### Optimization Setup
- **Subject**: 102
- **Target ROI**: Left insula (DK40 atlas, region 35)
- **Goal**: Maximize mean field in ROI
- **Electrode**: 4mm radius, 8mA current
- **Comparison**: Maximum TI field vs Normal vs Tangential TI field components

### Results: Maximum TI Field Optimization

**Field Distribution:**
![Maximum TI Field]({{ site.baseurl }}/wiki/assets/flex-search/max_TI_field.png)
![Maximum TI ROI Targeting]({{ site.baseurl }}/wiki/assets/flex-search/max_TI_ROI.png)

**Optimization Summary:**

| Metric | Value |
|--------|--------|
| Function Evaluations | 4,080 (1,492 FEM evaluations) |
| Final Goal Value | -2.320 |
| Duration | 25.1 minutes |
| Peak Field (99.9%) | 4.17 V/m |
| Median ROI Field | 2.21 V/m |
| Focality (75% threshold) | 3,250 mm² |

### Results: Normal Component Optimization

**Field Distribution:**
![Normal TI Field]({{ site.baseurl }}/wiki/assets/flex-search/Normal_field.png)
![Normal ROI Targeting]({{ site.baseurl }}/wiki/assets/flex-search/normal_ROI.png)

**Optimization Summary:**

| Metric | Value |
|--------|--------|
| Function Evaluations | 4,080 (1,708 FEM evaluations) |
| Final Goal Value | -1.627 |
| Duration | 25.8 minutes |
| Peak Field (99.9%) | 3.15 V/m |
| Median ROI Field | 1.79 V/m |
| Focality (75% threshold) | 1,850 mm² |

### Results: Tangential Component Optimization

**Field Distribution:**
![Tangential TI Field]({{ site.baseurl }}/wiki/assets/flex-search/tangent_field.png)
![Tangential ROI Targeting]({{ site.baseurl }}/wiki/assets/flex-search/tangent_ROI.png)

**Optimization Summary:**

| Metric | Value |
|--------|--------|
| Function Evaluations | 4,320 (1,587 FEM evaluations) |
| Final Goal Value | -1.762 |
| Duration | 24.8 minutes |
| Peak Field (99.9%) | 3.27 V/m |
| Median ROI Field | 1.82 V/m |
| Focality (75% threshold) | 4,140 mm² |

## Key Findings

### Post-Processing Method Comparison
The optimization results demonstrate distinct characteristics for each TI field analysis method:

- **Maximum TI Field**: Achieved the highest field intensities (4.17 V/m peak, 2.21 V/m median ROI) and best optimization score (-2.320)
- **Normal Component**: Provided the most focused targeting with highest spatial precision (1,850 mm² focality area)
- **Tangential Component**: Generated broader spatial distribution (4,140 mm² focality area) with moderate field intensities

### Directional Sensitivity
The optimization successfully distinguished between different field analysis approaches:
- **Non-directional (max_TI)**: Optimized for overall field strength without cortical orientation constraints
- **Normal Component**: Specifically targeted fields perpendicular to cortical surface
- **Tangential Component**: Focused on fields parallel to cortical surface
- **Consistent ROI Targeting**: All methods effectively targeted the left insula while optimizing for different field characteristics

### Practical Implications
- **Method Selection**: max_TI provides highest overall field strength, while directional methods offer cortical orientation control
- **Application-Specific Optimization**: Different post-processing methods suit different stimulation goals and neural targeting requirements

### Field Analysis
- **Post-processing**: Multiple field analysis methods (max_TI, dir_TI_normal, dir_TI_tangential)
- **Metrics**: Field percentiles, focality measures, and ROI-specific statistics
- **Visualization**: Comprehensive field distribution plots and ROI analysis
