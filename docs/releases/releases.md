---
layout: releases
title: Latest Release
permalink: /releases/
---

For headless server useage, see the [Bash Script & Compose YAML](https://github.com/idossha/TI-Toolbox/tree/main/launcher/bash).

---

### v2.1.3 (Latest Release)

**Release Date**: October 08, 2025

#### Additions
- - **Executable Launcher**: pre-flight check for existing containers to avoid start conflicts.
- - **Executable Launcher**: validation of path input (for mannual inputs)
- - **Flex-search**: dynamic focality thresholding for better output
- - **Development**: Added a watchdog for easier GUI development
- - **Analyzer**: Added `labeling.nii.gz` as an option for voxel analysis w/o need for recon-all

#### Fixes
- - **General**: Removed env limits for flex-search, cleaned up GUI tabs, fixed Gmsh GUI lauchner with analysis visuals, fixed example data (ernie, MNI152) mounting in executable mode, clean up of executable console output.
- - **Critical**: Batch processing of sub-cortical targets in flex-search mode. Previous, `labeling.nii.gz` was no updating between subjects, causing incorrect optimization targeting.

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

For installation instructions, see the [Installation Guide]({ site.baseurl }/installation/).

---

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)

