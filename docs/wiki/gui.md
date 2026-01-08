---
layout: wiki
title: Graphical User Interface
permalink: /wiki/gui/
---

The TI-Toolbox GUI provides a graphical interface for running TI-Toolbox workflows without command-line interaction. Built with PyQt5, it offers an intuitive tabbed interface for all major TI-Toolbox functionalities.

## Overview

The GUI serves as a user-friendly alternative to the CLI, providing visual controls and real-time feedback for TI-Toolbox operations. It's particularly useful for:

- **New users** learning TI-Toolbox workflows
- **Interactive exploration** of parameters and options
- **Visual monitoring** of long-running processes

## Interface Screenshots

### Pre-processing
![TI-Toolbox GUI Main Interface]({{ site.baseurl }}/assets/imgs/UI/UI_pre-process.png)
*Initial tab for pre-processing raw dicoms*

### Optimizer Interface
![Flex Search Optimization]({{ site.baseurl }}/assets/imgs/UI/UI_flex.png)
*Flex Search optimization interface with parameter controls*

### Simulator Tab
![Simulator Tab]({{ site.baseurl }}/assets/imgs/UI/UI_sim.png)
*Simulation controls with parameter settings and progress monitoring*

### Analysis Results
![Analyzer Tab]({{ site.baseurl }}/assets/imgs/UI/UI_ana.png)
*Analysis tab displaying simulation results and statistical outputs*

### System Monitoring
![System Monitor]({{ site.baseurl }}/assets/imgs/UI/UI_monitor.png)
*Real-time system monitoring and resource usage tracking*


## Technical Architecture

The GUI is built on PyQt5 with a modular architecture:

- **Main Window**: Central tabbed interface with extension support
- **Tab System**: Modular tabs for different functionalities
- **Settings System**: Persistent configuration management
- **Extension Framework**: Plugin architecture for expandable features
- **Real-time Monitoring**: Live updates for long-running operations

## Getting Started

To launch the GUI:

```bash
# From within the TI-Toolbox environment
GUI
```

The GUI and CLI share the same underlying TI-Toolbox core.