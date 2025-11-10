---
layout: wiki
title: Simulator
permalink: /wiki/simulator/
---

The Simulator module provides temporal interference (TI) simulation capabilities within the TI-Toolbox GUI, supporting multiple montage sources, electrode configurations, and simulation parameters.


## Montage Sources

The simulator supports three primary montage source types:

### 1. Montage List
Pre-defined electrode configurations organized by EEG net and stimulation mode:
- **Unipolar Montages**: The traditiona two pairs electrode montage
- **Multipolar Montages**: Multiple (currently only supporting four) pairs for higher focality 
- **EEG Net Compatibility**: Automatically filtered based on selected electrode configuration
- **Management**: Add, remove, and refresh montage collections

### 2. Flex Mode
Automatic integration with the flex-search optimizer.
- **Optimize**: Start by running the optimizer based on your needs
- **Simulate**: Move to the simulator and use the automatic montage available from the flex-search
- **Mapping**: Make sure to enable the mapping function in the flex-search to have it available 

### 3. Free-Hand
Mode that allows exploration of untraditional montages
- **Flexible Positioning**: Manual electrode placement for specialized protocols
- **Extension**: Open up the `electrode placement` extension to freely place electrodes on subjects

---

## Simulation Modes

<img src="{{ site.baseurl }}/assets/imgs/wiki/simulator/uTI_mTI.png" alt="Unipolar TI" style="width: 80%; max-width: 300px;">
<em>Left column unipolar (two channels) right column multipolar (four channels). Panels A,D: target and electrode montage. Panels B,E: high frequency fields. Panels C,F: modulation fields.</em>

### Unipolar Mode
- **Configuration**: Single active electrode with dedicated return path
- **Current Settings**: Two current inputs (active and return electrodes)
- **Applications**: Focal stimulation with clear current flow direction
- **Montage Compatibility**: Works with unipolar montage collections

### Multipolar Mode
- **Configuration**: Multiple active electrodes (up to 4 channels)
- **Current Settings**: Four current inputs for complex stimulation patterns
- **Applications**: Distributed stimulation, field steering, and complex targeting
- **Montage Compatibility**: Works with multipolar montage collections

---

## Available EEG Nets

The simulator automatically detects and supports various electrode configurations:

### Standard EEG Nets
- **10-10 System**: High-density electrode placement (64+ electrodes)
- **10-20 System**: Standard clinical electrode placement (32 electrodes)
- **GSN-HydroCel-256**: High-density research net (256 electrodes)
- **GSN-HydroCel-185**: Research-grade net (185 electrodes)

### Specialized Nets
- **EGI Systems**: Multiple EGI electrode configurations
- **EasyCap**: TMS-compatible electrode layouts
- **Custom Nets**: User-defined electrode positions via CSV files

### Net Detection
- **Automatic Scanning**: Searches `eeg_positions/` directories for available nets
- **Dynamic Updates**: Montage lists refresh based on selected EEG net
- **Compatibility Filtering**: Only compatible montages shown for selected net

---

## Anisotropy

The simulator supports different tissue conductivity models:

### Isotropic Model
- **Description**: Uniform conductivity in all directions
- **Applications**: Simplified modeling, faster computation
- **Limitations**: May not accurately represent white matter anisotropy

### Anisotropic Model
- **Description**: Direction-dependent conductivity based on DTI data
- **Requirements**: Diffusion tensor imaging (DTI) scans
- **Applications**: More realistic modeling of white matter tracts
- **Processing**: Accounts for fiber orientation in field calculations

---

## Coordinate Spaces

### Subject Space
- **Definition**: Coordinates relative to individual subject anatomy
- **Origin**: Centered on subject's brain anatomy
- **Applications**: Subject-specific targeting and analysis
- **File Format**: Native FreeSurfer subject space coordinates

### MNI Space
- **Definition**: Standardized coordinate system (MNI152 template)
- **Origin**: Based on Montreal Neurological Institute template
- **Applications**: Cross-subject comparisons and group analysis
- **Transformations**: Automatic conversion between subject and MNI space

### Space Transformations
- **Automatic Conversion**: Built-in coordinate transformation utilities
- **ROI Mapping**: Support for both subject and MNI coordinate inputs
- **Visualization**: Compatible with both coordinate systems for analysis

---

## User Interface

<img src="{{ site.baseurl }}/assets/imgs/wiki/simulator/UI_sim.png" alt="Simulator User Interface" style="width: 100%; max-width: 600px;">

The simulator GUI provides intuitive controls for all simulation parameters:

### Main Controls
- **Subject Selection**: Choose from available pre-processed subjects
- **Montage Source**: Radio buttons for montage list, flex mode, and free-hand
- **Simulation Mode**: Unipolar/multipolar selection with current inputs
- **EEG Net**: Dropdown selection of available electrode configurations

### Advanced Options
- **Conductivity Model**: Isotropic/anisotropic tissue modeling
- **Current Configuration**: Individual electrode current settings
- **Batch Processing**: Multiple subject simulation queues

### Output Management
- **Real-time Logging**: Simulation progress and status updates
- **Result Visualization**: Automatic generation of field maps and statistics
- **Data Export**: NIfTI files, electrode positions, and analysis reports