---
layout: releases
title: Latest Release
permalink: /releases/
---

### v2.2.2 (Latest Release)

**Release Date**: December 25, 2025

#### Additions
- - **Simulator Refactoring**: Complete rewrite from bash to Python with modular architecture including progress callbacks, better error handling, and improved logging.
- - **Enhanced Cluster Permutation Testing**: New ACES-like correlation investigation, support for continuous variables, enhanced reporting, and improved GUI integration.
- - **Comprehensive Testing Infrastructure**: new test files with code coverage integration, headless operation support, and improved CI/CD pipeline.
- - **Improved 3D Visualization**: Enhanced visual exporter with automatic electrode placement, metadata extraction, GLB format export, and Docker-based Blender integration.
- - **Pythonic CLI Migration**: New Click-based command-line interfaces for simulator and cluster permutation tools with better argument validation.
- - **GUI Enhancements**: Improved threading across all tabs with real-time progress updates, better error handling, and enhanced responsiveness.

#### Fixes
- - **Various Bug Fixes**: Fixed silent timeout issues in CI, corrected coverage integration, improved error handling in all major modules, better cleanup of temporary files, and enhanced logging.
- - **Windows Electron**: A more robust executable delivery on Windows.

#### Download Links

**Desktop App (latest):**
[macOS Intel](https://github.com/idossha/TI-toolbox/releases/latest/download/TI-Toolbox-x64.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-toolbox/releases/latest/download/TI-Toolbox-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-toolbox/releases/latest/download/TI-Toolbox-Setup.exe) ·
[Linux AppImage](https://github.com/idossha/TI-toolbox/releases/latest/download/TI-Toolbox.AppImage) ·
[Linux deb](https://github.com/idossha/TI-toolbox/releases/latest/download/tit.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:latest`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/).
#### Backward compatibility change to be aware:
- **Electode Mapping**: We changed the mapping functionality from the **flex-seach** to the **simulator**. This to provide a more flexible and dynamic framework. Now, the flex-search outputs the: `electrode_positions.json` file and the mapping functionality happeneds on the simulator side using the new method `tit/tools/map_electrodes.py`. Thus, one can use a single flex-search to conveniently map to multiple nets. 

#### Additions
- **Desktop App**: Recognizing the importance of Desktop delivery, we redesign our executables with Electron. For more info please see `package`.
- **Benchmarks**: Added benchmarking tool with sensible defaults that users can run on their systems
- **AMV**: Improved automatic montage visualization that now supports all available nets with a higher resolution image.
- **Flex-search**: Added more control over electrode geometry now supporting rectengular and width control.
- **Flex-search**: Exapnded hyper-parameter control. tolerance and mutation rate. 
- **Ex-search**: Enhanced the tool with current ratio optimization, enabling more efficient exploration of electrode current distributions. The exhaustive search now evaluates possible electrode montages and current distributions according to the formula: $N_\text{total} = N_\text{elec}^4 \cdot N_\text{current}$, where $N_\text{current} = \{(I_1,I_2) \mid I_1+I_2=I_\text{total} \wedge I_\text{step} \leq I_1,I_2 \leq I_\text{limit}\}$.

#### Fixes
- **Various Bug Fixes**: protection overwrites, documentation, output formatting, UI improvements, parallel processing, electrode management

#### Download Links

**Desktop App (latest):**
[macOS Intel](https://github.com/idossha/TI-toolbox/releases/latest/download/TI-Toolbox-x64.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-toolbox/releases/latest/download/TI-Toolbox-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-toolbox/releases/latest/download/TI-Toolbox-Setup.exe) ·
[Linux AppImage](https://github.com/idossha/TI-toolbox/releases/latest/download/TI-Toolbox.AppImage) ·
[Linux deb](https://github.com/idossha/TI-toolbox/releases/latest/download/tit.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:latest`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/).

---

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)

