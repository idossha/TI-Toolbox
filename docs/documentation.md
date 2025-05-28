---
layout: page
title: Documentation
permalink: /documentation/
---

# Documentation

Welcome to the Temporal Interference Toolbox documentation. This guide will help you get started with the Temporal Interference Toolbox.

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

Temporal Interference Toolbox is a comprehensive toolbox for temporal interference brain stimulation research. It provides a complete pipeline from raw imaging data to optimized stimulation parameters.

### Prerequisites

1. **Docker Desktop** - Download and install from [docker.com](https://www.docker.com/products/docker-desktop)
2. **Temporal Interference Toolbox** - Download the latest release for your platform from the [releases page](/releases)
3. **BIDS Dataset** - Your data should be organized in BIDS format

### Quick Start Guide

1. Set up your BIDS-compliant project directory. Place DICOM files in `sourcedata/sub-<subject>/T1w/dicom/` (and optionally T2w).
2. Install Docker Desktop and ensure it is running.
3. Download and launch the toolbox from the [releases page](/releases).
4. Start the toolbox environment (Docker containers will be managed automatically).
5. Pre-process your data (DICOM to NIfTI, FreeSurfer, SimNIBS head model).
6. Optimize electrode placement (flex-search or ex-search).
7. Simulate TI fields.
8. Analyze and visualize results.

## Installation

### System Requirements

- **Operating System**: macOS 10.14+, Ubuntu 18.04+, Windows 10+
- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 50GB for Docker images + space for your data
- **GPU**: NVIDIA GPU with CUDA support (optional, for acceleration)

### Platform-Specific Instructions

#### macOS
- Install Docker Desktop
- Install XQuartz (for GUI support)
- Download and run the launcher from the [releases page](/releases)

#### Linux
- Install Docker Desktop or Docker Engine
- Ensure X11 forwarding is enabled (for GUI)
- Download and run AppImage from the [releases page](/releases)

#### Windows
- Install Docker Desktop with WSL2
- Install VcXsrv or similar X server (for GUI)
- Download and run the installer from the [releases page](/releases)

## Project Structure

Temporal Interference Toolbox expects a BIDS-compliant directory structure:

```
your_project/
├── sourcedata/
│   └── sub-01/
│       └── T1w/
│           └── dicom/
├── sub-01/
│   └── anat/
│       ├── sub-01_T1w.nii.gz
│       └── sub-01_T2w.nii.gz
├── derivatives/
│   ├── freesurfer/
│   ├── simnibs/
│   └── ti_csc/
└── participants.tsv
```

## Workflow Overview

The typical workflow consists of:

1. **Set up BIDS directory**
2. **Pre-process** (DICOM to NIfTI, FreeSurfer, SimNIBS)
3. **Optimize** (flex-search or ex-search)
4. **Simulate** (TI/mTI field solvers)
5. **Analyze** (ROI/atlas-based tools)
6. **Visualize** (NIfTI/mesh viewers, report generator)

For more details on each step, see the sections below or the [wiki](/wiki).

## CLI Commands

The command-line interface provides full access to all toolbox functions. See the [wiki](/wiki) for detailed usage and examples.

## GUI Interface

The graphical interface provides an intuitive way to work with the toolbox, including project management, 3D visualization, and parameter controls.

## Pre-processing Pipeline

- DICOM to NIfTI conversion
- FreeSurfer cortical reconstruction
- SimNIBS head modeling

## Optimization

- **flex-search**: Evolutionary optimization for electrode placement
- **ex-search**: Exhaustive search for parameter sweeps

## Simulation

- FEM-based TI/mTI field calculations
- Supports custom montages and parameters

## Analysis Tools

- ROI-based and atlas-based analysis
- Spherical and cortical region analysis

## Visualization

- NIfTI and mesh viewers
- Overlay and 3D rendering tools
- Report generator for results

## Troubleshooting

See the [wiki](/wiki) or open an [issue](https://github.com/idossha/TI-Toolbox/issues) for help.

## Need Help?

- [Releases](/releases)
- [Documentation](/documentation)
- [Wiki](/wiki)
- [Issue Tracker](https://github.com/idossha/TI-Toolbox/issues)
- [Discussions](https://github.com/idossha/TI-Toolbox/discussions) 