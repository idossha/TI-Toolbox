---
layout: releases
title: Latest Release
permalink: /releases/
---

### v2.2.3 (Latest Release)

**Release Date**: January 07, 2026

#### Additions
- - **New Blender Tool for Full Blend File Creation**: Complete Blender integration with automated blend file generation, electrode positioning, and visualization setup. Streamlined workflow for creating publication-ready 3D visualizations directly from simulation results.
- - **New Correlation Mode for Cluster-Based Permutation Testing**: Enhanced statistical analysis capabilities with correlation-based cluster permutation testing, providing more robust statistical inference for connectivity and relationship analyses.
- - **Unified Command-Line Experience**: All CLI tools now support both interactive mode (run without arguments) and direct mode (with flags). Consistent colored output, clear prompts, and intelligent option discovery across all commands.
- - **Multi-Processing Simulator**: Parallel processing capabilities for faster simulation runs, optimized resource utilization, and scalable performance across different hardware configurations.
- - **Enhanced Testing Suite Coverage**: Comprehensive test coverage expansion including simulator workflows, statistical analysis pipelines, and integration testing for improved reliability and stability.
- - **Improved Security CI/CD Pipeline**: Strengthened GitHub Actions workflows with enhanced security scanning, automated vulnerability detection, and improved code quality gates throughout the development pipeline.

#### Fixes
- **Experimental Movea Tool**: Temporarily removed the experimental movea tool to focus development efforts on core functionality and stability.
- - **Bug Fixes & Reliability**: Fixed GUI crashes and timeout issues. Improved path handling and import reliability. Updated electrode templates for better compatibility. Enhanced security scanning and CI/CD workflows.
- - **Documentation Updates**: New CLI and GUI documentation pages. Improved Blender integration instructions. Added visualizer documentation. Better organization of documentation images.

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
[Linux deb](https://github.com/idossha/TI-toolbox/releases/latest/download/ti-toolbox.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:latest`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/).
#### Backward compatibility changes to be aware:
- **Electode Mapping**: We changed the mapping functionality from the **flex-seach** to the **simulator**. This to provide a more flexible and dynamic framework. Now, the flex-search outputs the: `electrode_positions.json` file and the mapping functionality happeneds on the simulator side using the new method `ti-toolbox/tools/map_electrodes.py`. Thus, one can use a single flex-search to conveniently map to multiple nets.
- **Package Naming**: The Python package has been renamed from `ti-toolbox` to `tit` for consistency with the internal module structure. All imports should now use `import tit` instead of `import ti_toolbox`. The directory structure has been updated accordingly (`ti-toolbox/` → `tit/`). 

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
[Linux deb](https://github.com/idossha/TI-toolbox/releases/latest/download/ti-toolbox.deb)

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

