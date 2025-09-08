---
layout: releases
title: Latest Release
permalink: /releases/
---

For headless server useage, see the [Bash Script & Compose YAML](https://github.com/idossha/TI-Toolbox/tree/main/launcher/bash).

---

### v2.1.2 (Latest Release)

**Release Date**: September 07, 2025

#### Additions
- **Example Dataset**: Toolbox now ships with Ernie & MNI152 MRI scans for quick start & learning purposes.
- **Tissue Analyzer**: Added skin thickness and volume analysis

#### Fixes
- **Various bug fixes**: charm, ex-search, flex-search

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

For installation instructions, see the [Installation Guide]({ site.baseurl }/installation/).
#### Additions
- N/A

#### Fixes
- **ex-search**: fixed final.csv output
- **flex-search**: fixed cleanup of directory if users choose a single start

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

For installation instructions, see the [Installation Guide]({ site.baseurl }/installation/).
#### Additions
- **Improved BIDS formatting:** Enhanced Brain Imaging Data Structure (BIDS) compliance and formatting for better data - organization and compatibility
- **Debug mode for console output:** Introduced comprehensive debug mode with detailed console logging for troubleshooting and development
- **Inter-individual variability assessment:** New bone analyzer tool integrated into pre-processing pipeline for assessing anatomical variations between subjects
- **Multi-start approach for flex-search optimization:** Implemented multi-start optimization strategy to counter local maxima issues in electrode placement optimization

#### Fixes
- **Removed MATLAB runtime dependency:** Eliminated MATLAB runtime requirement, making the toolbox fully independent and easier to deploy
- **mTI bug fixes and upstream integration:** Resolved critical bugs in mTI (multi-channel Temporal Interference) functionality and improved integration with upstream SimNIBS components
- **Enhanced X11 handling for macOS:** Improved X11 server integration and display management for better GUI - functionality on macOS systems
- **Official rebranding:** Complete renaming from TI-CSC to TI-Toolbox across all components, documentation, and user interfaces

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

For installation instructions, see the [Installation Guide]({ site.baseurl }/installation/).

---

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)

