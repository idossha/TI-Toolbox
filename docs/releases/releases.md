---
layout: page
title: Releases
permalink: /releases/
---

### Command-Line and Remote Usage

For headless server useage, see the [Bash Script & Compose YAML](https://github.com/idossha/TI-Toolbox/tree/main/launcher/bash).

<!-- DO NOT MODIFY: Auto-generated release content will be appended here -->

### v2.0.1 (Latest Release)

**Release Date**: June 11, 2025

#### Major Changes
- #### Additions
- new logger and report generators under projectDIR/derivatives/
- sub-cortical atlas based targeting for flex-search (example: thalamus targeting)

#### Fixes
- 2 decimal spherical ROIs
- TI
- py overwrite protection removed
- intenral 185 EGI net (removed 2 missed electrodes)
- added imagemagick for montage visualizer

#### Installation
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

For installation instructions, see the [Installation Guide]({ site.baseurl }/installation/).




### v2.0.0

**Release Date**: May 28, 2025

#### Major Changes
- Complete rewrite of the Temporal Interference Toolbox with major enhancements: Cross-platform support for Windows, macOS, and Linux
- Docker-based containerization for consistent environment and reproducibility
- Dual interface with both GUI and CLI support, enabling local and remote server usage
- Key functionalities include DICOM to NIfTI conversion, FreeSurfer segmentation, SimNIBS head modeling, flexible and exhaustive electrode optimization algorithms, FEM-based temporal interference field calculations, and comprehensive analysis tools with atlas-based ROI evaluation

#### Installation
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

For installation instructions, see the [Installation Guide]({ site.baseurl }/installation/).

  
---

## Version Support

We actively support and maintain versions 2.x.x and newer of the Temporal Interference Toolbox. Versions 1.x.x are no longer supported.


## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)

