---
layout: page
title: Documentation
permalink: /documentation/
---

# TI-CSC Documentation

Welcome to the TI-CSC documentation. This guide will help you get started with the Temporal Interference - Computational Stimulation Core toolbox.

<div class="doc-content">
  <div class="toc">
    <h3>Table of Contents</h3>
    <ul>
      <li><a href="#getting-started">Getting Started</a></li>
      <li><a href="#installation">Installation</a></li>
      <li><a href="#project-structure">Project Structure</a></li>
      <li><a href="#workflow-overview">Workflow Overview</a></li>
      <li><a href="#cli-commands">CLI Commands</a></li>
      <li><a href="#gui-interface">GUI Interface</a></li>
      <li><a href="#preprocessing">Pre-processing Pipeline</a></li>
      <li><a href="#simulation">TI Simulation</a></li>
      <li><a href="#optimization">Optimization</a></li>
      <li><a href="#analysis">Analysis Tools</a></li>
      <li><a href="#visualization">Visualization</a></li>
      <li><a href="#troubleshooting">Troubleshooting</a></li>
    </ul>
  </div>
</div>

## Getting Started

TI-CSC is a comprehensive toolbox for temporal interference brain stimulation research. It provides a complete pipeline from raw imaging data to optimized stimulation parameters.

### Prerequisites

1. **Docker Desktop** - Download and install from [docker.com](https://www.docker.com/products/docker-desktop)
2. **TI-CSC Launcher** - Download from our [downloads page](/downloads)
3. **BIDS Dataset** - Your data should be organized in BIDS format

### Quick Start Guide

1. Launch the TI-CSC application
2. Select your BIDS-compliant project directory
3. Click "Start Docker Containers" and wait for initialization
4. Choose CLI or GUI interface based on your preference

## Installation

### System Requirements

- **Operating System**: macOS 10.14+, Ubuntu 18.04+, Windows 10+
- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 50GB for Docker images + space for your data
- **GPU**: NVIDIA GPU with CUDA support (optional, for acceleration)

### Platform-Specific Instructions

#### macOS
- Install Docker Desktop
- Install XQuartz 2.7.7 or 2.8.0 (for GUI support)
- Download and run TI-CSC launcher

#### Linux
- Install Docker Desktop or Docker Engine
- Ensure X11 forwarding is enabled
- Download and run AppImage

#### Windows
- Install Docker Desktop with WSL2
- Install VcXsrv or similar X server (for GUI)
- Download and run installer

## Project Structure

TI-CSC expects a BIDS-compliant directory structure:

```
your_project/
├── sub-01/
│   ├── anat/
│   │   ├── sub-01_T1w.nii.gz
│   │   └── sub-01_T2w.nii.gz
│   └── ses-01/
│       └── anat/
├── sub-02/
│   └── ...
├── derivatives/
│   ├── freesurfer/
│   ├── simnibs/
│   └── ti_csc/
└── participants.tsv
```

## Workflow Overview

The typical TI-CSC workflow consists of:

1. **Data Import** - Convert DICOM to NIfTI (if needed)
2. **Pre-processing** - FreeSurfer reconstruction and SimNIBS head modeling
3. **Simulation Setup** - Define electrode positions and parameters
4. **Field Calculation** - Compute TI fields using FEM
5. **Optimization** - Find optimal electrode configurations
6. **Analysis** - Evaluate results using ROI tools
7. **Visualization** - View and export results

## CLI Commands

The command-line interface provides full access to all TI-CSC functions:

### Basic Commands

```bash
# Show help
ti-csc --help

# Process a subject
ti-csc preprocess --subject sub-01

# Run simulation
ti-csc simulate --subject sub-01 --config simulation.json

# Optimize parameters
ti-csc optimize --subject sub-01 --target ROI_name
```

### Pre-processing Commands

```bash
# Run FreeSurfer
ti-csc freesurfer --subject sub-01

# Create head model
ti-csc headmodel --subject sub-01 --type simnibs

# Convert DICOM to NIfTI
ti-csc dicom2nifti --input /path/to/dicoms --output /path/to/nifti
```

### Simulation Commands

```bash
# Basic TI simulation
ti-csc simulate --subject sub-01 \
  --freq1 1000 --freq2 1010 \
  --amp1 1.0 --amp2 1.0

# With custom electrode positions
ti-csc simulate --subject sub-01 \
  --electrodes electrodes.csv \
  --config advanced_params.json
```

## GUI Interface

The graphical interface provides an intuitive way to work with TI-CSC:

### Main Features

- **Project Manager** - Organize subjects and sessions
- **3D Viewer** - Interactive brain and field visualization
- **Electrode Editor** - Place and adjust electrodes visually
- **Parameter Controls** - Real-time parameter adjustment
- **Result Browser** - Compare different simulations

### GUI Workflow

1. Launch GUI from the Docker launcher
2. Open or create a project
3. Select a subject
4. Place electrodes using the 3D editor
5. Set simulation parameters
6. Run simulation
7. Visualize results

## Pre-processing Pipeline

### FreeSurfer Processing

TI-CSC uses FreeSurfer for cortical reconstruction:

```bash
# Standard processing
ti-csc freesurfer --subject sub-01

# With custom options
ti-csc freesurfer --subject sub-01 \
  --parallel --threads 8 \
  --hires
```

### Head Model Creation

SimNIBS is used to create FEM head models:

```bash
# Create head model
ti-csc headmodel --subject sub-01

# With custom tissue conductivities
ti-csc headmodel --subject sub-01 \
  --skin 0.465 --skull 0.010 \
  --csf 1.654 --gm 0.276 --wm 0.126
```

## TI Simulation

### Basic Parameters

- **Frequencies**: f1 and f2 (typically 1000-3000 Hz)
- **Amplitudes**: Current amplitudes for each channel
- **Electrode Positions**: 10-20 system or MNI coordinates

### Advanced Options

```json
{
  "simulation": {
    "mesh_resolution": "high",
    "solver": "gmres",
    "tolerance": 1e-6,
    "max_iterations": 1000
  },
  "electrodes": {
    "type": "circular",
    "diameter": 50,
    "thickness": 2
  }
}
```

## Optimization

### Evolution Algorithm

```bash
# Optimize for maximum field in target
ti-csc optimize --subject sub-01 \
  --algorithm evolution \
  --target "left_motor_cortex" \
  --generations 100 \
  --population 50
```

### Exhaustive Search

```bash
# Search all 10-20 positions
ti-csc optimize --subject sub-01 \
  --algorithm exhaustive \
  --positions 10-20 \
  --target ROI.nii.gz
```

## Analysis Tools

### ROI Analysis

```bash
# Analyze field in ROI
ti-csc analyze --subject sub-01 \
  --simulation sim_001 \
  --roi hippocampus.nii.gz \
  --metrics "mean,max,focality"
```

### Atlas-based Analysis

```bash
# Use brain atlas
ti-csc analyze --subject sub-01 \
  --simulation sim_001 \
  --atlas AAL3 \
  --output results.csv
```

## Visualization

### Command Line

```bash
# Generate field maps
ti-csc visualize --subject sub-01 \
  --simulation sim_001 \
  --type field \
  --output field_map.png

# Create 3D rendering
ti-csc visualize --subject sub-01 \
  --simulation sim_001 \
  --type 3d \
  --view lateral
```

### GUI Visualization

- Real-time 3D rendering
- Slice viewers (axial, sagittal, coronal)
- Field intensity overlays
- Electrode visualization
- Animation of interference patterns

## Troubleshooting

### Common Issues

#### Docker won't start
- Ensure Docker Desktop is running
- Check system resources (RAM, disk space)
- Restart Docker Desktop

#### GUI doesn't appear (macOS)
- Install XQuartz 2.7.7 or 2.8.0
- Enable "Allow connections from network clients" in XQuartz
- Restart XQuartz and try again

#### Out of memory errors
- Increase Docker memory limit in Docker Desktop settings
- Reduce mesh resolution in simulation parameters
- Process subjects individually

#### Slow performance
- Enable GPU support if available
- Reduce simulation resolution
- Use parallel processing options

### Getting Help

- Check the [Wiki](/wiki) for detailed guides
- Search [existing issues](https://github.com/idossha/TI-CSC-2.0/issues)
- Ask in [Discussions](https://github.com/idossha/TI-CSC-2.0/discussions)
- Contact support at support@ti-csc.org

## Advanced Topics

For advanced usage, custom extensions, and development guides, visit our [Wiki](/wiki). 