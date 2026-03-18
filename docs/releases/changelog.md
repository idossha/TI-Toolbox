---
layout: releases
title: Changelog
permalink: /releases/changelog/
---

Complete changelog for all versions of the Temporal Interference Toolbox.


---
### v2.3.0 (Latest Release)

**Release Date**: March 17, 2026

This is a major release that introduces a number of new features, but mainly a massive change to internal modernization of the codebase. Plus, we are now wrapping SimNIBS 4.6.0.

---

#### New Features

- **Combined ROI Analysis**: You can now select multiple atlas regions to analyze as a single combined ROI. Pass a list of region names (e.g., `["precentral", "postcentral"]`) and they are unioned before analysis. Output directories and file names use a `+`-joined convention (e.g., `precentral+postcentral/`).
- **Anisotropy Support in Flex-Search**: The flex-search optimizer now supports all 4 SimNIBS conductivity models: isotropic (scalar), volume-normalized (vn), direct (dir), and multi-conductivity (mc). A dropdown in the GUI and `FlexConfig.anisotropy_type` parameter in the API control this.
- **Anisotropy Tuning Parameters**: New `aniso_maxratio` and `aniso_maxcond` parameters on simulation and optimization configs let you control eigenvalue clamping for anisotropic simulations (defaults match SimNIBS: 10.0 and 2.0 S/m respectively).
- **Optimization Output Manifest**: Every flex-search run now writes a `flex_meta.json` manifest alongside its results, recording the full configuration, best result, multi-start history, and a human-readable label. The simulator reads this manifest directly instead of parsing folder names.
- **Comprehensive Test Suite**: 545 pytest tests running in 0.55 seconds, covering all core modules. Key coverage: calc 100%, paths 98%, sim/TI 87%, sim/mTI 90%, analyzer 82%, stats/config 95%, pre/structural 99%, opt/config 99%.
- **JSON Config Entry Points**: All modules support `simnibs_python -m tit.<module> config.json` for programmatic and GUI-driven invocation. New `tit/config_io.py` handles typed serialization with `_type` discriminators.

#### Refactors & Improvements

- **Logger Simplification**: Removed ~750 lines of custom handler/wrapper code. Two functions: `setup_logging()` and `add_file_handler()`. File-only logging with Qt bridge for GUI. Debug-mode checkboxes removed from all GUI tabs.
- **Module Reorganization**: Dissolved `tit/core/` -- modules moved to `tit/paths`, `tit/constants`, `tit/calc`. NIfTI utilities moved to `tit/stats/nifti`. Mesh utilities moved to `tit/tools/gmsh_opt`.
- **Unified Analyzer**: Single `Analyzer` class replaces the old `MeshAnalyzer`/`VoxelAnalyzer` split. Sphere and cortex ROI handling are unified. New `run_group_analysis()` function for multi-subject comparisons.
- **Simplified Python API**: All modules now support clean one-liner imports:
  - `from tit.sim import SimulationConfig, Montage, MontageMode, run_simulation`
  - `from tit.opt import FlexConfig, run_flex_search`
  - `from tit.opt import ExConfig, run_ex_search`
  - `from tit.analyzer import Analyzer, run_group_analysis`
  - `from tit.stats import run_group_comparison, GroupComparisonConfig`
- **Flat Simulation Config**: The simulation API was simplified from 5+ wrapper classes to 2 dataclasses. `LabelMontage`/`XYZMontage` replaced by a single `Montage` class with a `MontageMode` enum. `ElectrodeConfig`, `IntensityConfig`, and `ConductivityType` fields inlined directly into `SimulationConfig`.
- **Flat Optimization Configs**: Flex-search ROI types, enums, and electrode config are now nested inside `FlexConfig` (e.g., `FlexConfig.SphericalROI`, `FlexConfig.OptGoal`). Ex-search current parameters inlined into `ExConfig`. Electrode classes accessed as `ExConfig.PoolElectrodes` and `ExConfig.BucketElectrodes`.
- **PathManager Rewrite**: Replaced 930-line template engine with 180-line direct-method API (`pm.m2m(sid)`, `pm.simulation(sid, sim)`). IDE autocompletion now works; typos caught at import time.
- **GUI Threading**: Eliminated all blocking `.wait()` calls. Signal-based completion. Consistent subprocess pattern (config -> JSON -> subprocess) across all tabs.
- **Statistics Engine Refactor**: Introduced `PermutationEngine` class that absorbs all control parameters, cutting internal function signatures from 16-17 arguments to 5-7. Dead code removed from I/O utilities. Public API (`run_group_comparison`, `run_correlation`) unchanged.
- **Blender Module Modernization**: Typed config dataclasses (`MontagePublicationConfig`, `VectorFieldConfig`, `RegionExportConfig`), consolidated I/O utilities, `__main__.py` entry point, and deduplicated STL/PLY code.
- **Codebase Modernization**: 657 type hint replacements across 55 files (modern `list[X]`, `X | None` syntax). 27 dead constants removed. 16 overly broad exception handlers tightened. GUI color constants centralized in `style.py`.
- **CI/CD Improvements**: Fixed Codecov upload in CircleCI. Added GitHub Actions workflow for MkDocs auto-deployment. Docker layer caching enabled. Codecov CLI cached between runs.
- **Reusable GUI Components**: Extracted `ROIPickerWidget`, `ElectrodeConfigWidget`, `SolverParamsWidget` for cross-tab reuse. Three identical floating window classes consolidated into one generic class.

#### Fixes

- Python 3.9 syntax errors fixed (`str | Path` without `from __future__ import annotations`).
- SimNIBS `S.fname_tensor` now set correctly (was `S.dti_nii` -- silently ignored by SimNIBS).
- SimNIBS `S.map_to_MNI` capitalized correctly (was `S.map_to_mni` -- MNI mapping was silently broken).
- Dead `S.anisotropy_type` assignment on SESSION object removed (was no-op; correctly set on TDCSLIST).

#### Breaking Changes

- **`tit.core.*` imports removed** -- use `tit.paths`, `tit.constants`, `tit.calc` directly.
- **`PathManager.path("key")` template API removed** -- use direct methods (e.g., `pm.m2m(sid)`).
- **`list_subjects()` renamed** to `list_simnibs_subjects()`. `list_all_subjects()` removed entirely.
- **`MeshAnalyzer` and `VoxelAnalyzer` deleted** -- use unified `Analyzer` class.
- **`run_analysis()` removed** -- use `Analyzer.run()` or `run_group_analysis()`.
- **`LabelMontage` and `XYZMontage` deleted** -- use `Montage` with `MontageMode` enum.
- **`ElectrodeConfig`, `IntensityConfig`, `ConductivityType` deleted** -- fields inlined into `SimulationConfig`.
- **`IntensityConfig(pair1=, pair2=)` constructor removed** -- use `intensities=[1.0, 1.0]` list.
- **Standalone `SphericalROI`, `AtlasROI`, `SubcorticalROI` removed from `tit.opt`** -- access via `FlexConfig.SphericalROI`, etc.
- **`OptGoal`, `FieldPostproc`, `NonROIMethod` enums removed from `tit.opt`** -- access via `FlexConfig.OptGoal`, etc.
- **`ExCurrentConfig` deleted** -- current parameters inlined into `ExConfig`.
- **`BucketElectrodes` and `PoolElectrodes` standalone imports removed** -- access via `ExConfig.BucketElectrodes`, etc.
- **`config.eeg_net` removed from `ExConfig`** -- replaced with `config.run_name` (defaults to datetime).
- **`generate_current_ratios()` return type changed** -- now returns `list` instead of `(list, bool)`.
- **Ex-search output JSON changed** -- `analysis_results.json` replaced with `run_config.json`. `n_elements` column removed from CSV.
- **Logger functions `get_logger()`, `build_logger()`, `build_opt_logger()` deleted** -- use `logging.getLogger(__name__)`.
- **`BenchmarkLogger` and `OptimizationLogger` wrapper classes deleted** -- use standard `logging` module.
- **Flex-search output folders** now use datetime naming (e.g., `20260307_143022/`) instead of encoded ROI names. The `flex_meta.json` manifest replaces folder-name parsing.
- **`mesh_utils.py` renamed** to `gmsh_opt.py` in `tit/tools/`.

#### Download Links
**Desktop App (v2.3.0):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox.Setup.2.3.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/ti-toolbox_2.3.0_amd64.deb)
**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.3.0`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.2.4
**Release Date**: January 16, 2026
#### Additions
- N/A
#### Fixes
- **Loader Program**: Fixed example data and initiliazation of the BIDS files. Also, should be handling X11 more gracefully.
#### Download Links
**Desktop App (v2.2.4):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox.Setup.2.2.4.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/ti-toolbox_2.2.4_amd64.deb)
**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.2.4`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.2.3

**Original Release Date**: January 07, 2026
**Effective Release Date**: January 14, 2026 (re-uploaded tag with preprocessing refactored to deal with recon-all problem without releasing and official new image. Should be updated automatically to all users without breaking behavior).

#### Additions
- **New Blender Tool for Full Blend File Creation**: Complete Blender integration with automated blend file generation, electrode positioning, and visualization setup. Streamlined workflow for creating publication-ready 3D visualizations directly from simulation results.
- **Ex-search**: Added an option to run the a truly exhaustive search option as all selected electrodes are pooled together instead of placed in stationary buckets. Refer to ex-search wiki tab for more information.
- **New Correlation Mode for Cluster-Based Permutation Testing**: Enhanced statistical analysis capabilities with correlation-based cluster permutation testing, providing more robust statistical inference for connectivity and relationship analyses.
- **Unified Command-Line Experience**: All CLI tools now support both interactive mode (run without arguments) and direct mode (with flags). Consistent colored output, clear prompts, and intelligent option discovery across all commands.
- **Multi-Processing Simulator**: Parallel processing capabilities for faster simulation runs, optimized resource utilization, and scalable performance across different hardware configurations.
- **Enhanced Testing Suite Coverage**: Comprehensive test coverage expansion including simulator workflows, statistical analysis pipelines, and integration testing for improved reliability and stability.
- **Improved Security CI/CD Pipeline**: Strengthened GitHub Actions workflows with enhanced security scanning, automated vulnerability detection, and improved code quality gates throughout the development pipeline.
- **Refactored pre-processing tools**: Removed all bash scripts to improved maintainability and reduce complexity. Updated all relevant benchmarks, tests, and docs. 

#### Fixes
- **Experimental Movea Tool**: Temporarily removed the experimental movea tool to focus development efforts on core functionality and stability.
- **Bug Fixes & Reliability**: Fixed GUI crashes and timeout issues. Improved path handling and import reliability. Updated electrode templates for better compatibility. Enhanced security scanning and CI/CD workflows.
- **Documentation Updates**: New CLI and GUI documentation pages. Improved Blender integration instructions. Added visualizer documentation. Better organization of documentation images.
#### Download Links
**Desktop App (v2.2.3):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox.Setup.2.2.3.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/ti-toolbox_2.2.3_amd64.deb)
**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.2.3`

---

### v2.2.2
**Release Date**: December 25, 2025
#### Additions
- **Simulator Refactoring**: Complete rewrite from bash to Python with modular architecture including progress callbacks, better error handling, and improved logging.
- **Enhanced Cluster Permutation Testing**: New ACES-like correlation investigation, support for continuous variables, enhanced reporting, and improved GUI integration.
- **Comprehensive Testing Infrastructure**: new test files with code coverage integration, headless operation support, and improved CI/CD pipeline.
- **Improved 3D Visualization**: Enhanced visual exporter with automatic electrode placement, metadata extraction, GLB format export, and Docker-based Blender integration.
- **Pythonic CLI Migration**: New Click-based command-line interfaces for simulator and cluster permutation tools with better argument validation.
- **GUI Enhancements**: Improved threading across all tabs with real-time progress updates, better error handling, and enhanced responsiveness.
#### Fixes
- **Various Bug Fixes**: Fixed silent timeout issues in CI, corrected coverage integration, improved error handling in all major modules, better cleanup of temporary files, and enhanced logging.
- **Windows Electron**: A more robust executable delivery on Windows.
#### Download Links
**Desktop App (v2.2.2):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox.Setup.2.2.2.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/ti-toolbox_2.2.2_amd64.deb)
**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.2.2`

---

### v2.2.1

**Release Date**: December 04, 2025

#### Backward compatibility change to be aware:
- **Electode Mapping**: We changed the mapping functionality from the **flex-seach** to the **simulator**. This to provide a more flexible and dynamic framework. Now, the flex-search outputs the: `electrode_positions.json` file and the mapping functionality happeneds on the simulator side using the new method `ti-toolbox/tools/map_electrodes.py`. Thus, one can use a single flex-search to conveniently map to multiple nets. 

#### Additions
- **Desktop App**: Recognizing the importance of Desktop delivery, we redesign our executables with Electron. For more info please see `package`.
- **Benchmarks**: Added benchmarking tool with sensible defaults that users can run on their systems
- **AMV**: Improved automatic montage visualization that now supports all available nets with a higher resolution image.
- **Flex-search**: Added more control over electrode geometry now supporting rectengular and width control.
- **Flex-search**: Exapnded hyper-parameter control. tolerance and mutation rate. 
- **Ex-search**: Enhanced the ex-search with current ratio optimization, enabling more robust optimization process. The exhaustive search now evaluates possible electrode montages and current ratios according to the formula: $N_\text{total} = N_\text{elec}^4 \cdot N_\text{current}$, where $N_\text{current} = \{(I_1,I_2) \mid I_1+I_2=I_\text{total} \wedge I_\text{step} \leq I_1,I_2 \leq I_\text{limit}\}$.



#### Fixes
- **Various Bug Fixes**: protection overwrites, documentation, output formatting, UI improvements, parallel processing, electrode management

#### Download Links

**Desktop App (v2.2.1):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox.Setup.2.2.1.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/ti-toolbox_2.2.1_amd64.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.2.1`

---

### v2.2.0

**Release Date**: November 07, 2025

#### Additions
- **Core Infrastructure & Architecture**: The project underwent a complete restructure, removing old launcher directories and consolidating to a unified ti-toolbox structure. A new core module system was introduced in ti-toolbox/core/ with reusable components including paths.py, calc.py, constants.py, errors.py, process.py, utils.py, nifti.py, mesh.py, and viz.py. The project moved away from executable compilation and now focuses exclusively on bash entry point.
- **GUI Extensions System**: A new modular extension system was introduced in ti-toolbox/gui/extensions/ providing several powerful tools. The Cluster-Based Permutation Testing (CBP) extension offers statistical analysis for group comparisons. Nilearn Visuals enables brain visualization using nilearn with glass brain views, surface plots, and slices. The NIfTI Group Averaging tool allows averaging multiple NIfTI files across subjects. The Visual Exporter provides export capabilities to Blender-compatible formats (PLY, STL) with a full tutorial. Additional extensions include Quick Notes for in-app note-taking with persistence, Subject Info Viewer for displaying metadata and processing status, and an Electrode Placement Tool for interactive electrode positioning.
- **3D Visualization & Export**: A 3D Exporter module was added in ti-toolbox/3d_exporter/ containing four specialized tools. TI_quick_volumetric.py provides fast volumetric field exports, cortical_regions_to_ply.py handles region-specific mesh exports, cortical_regions_to_stl.py outputs STL format for 3D printing, and vector_ply.py enables vector field visualization in Blender.
- **MOVEA Optimization**: MOVEA-like integration was implemented for multi-objective optimization of electrode placement. The system now uses a centralized leadfield with unified leadfield target locations across all optimization tools. A complete MOVEA GUI tab provides an interface for optimization workflows.
- **Analysis Tool**: Group Analyzer received significant improvements including enhanced multi-subject analysis capabilities with MNI coordinate support.
- **Statistics Module**: A statistics package was created in ti-toolbox/stats/. The cluster_permutation.py module implements non-parametric cluster-based permutation testing.
- **Simulator Improvements**: The simulator received substantial enhancements including a new free-hand mode that allows direct electrode coordinate input without montage selection. The entire simulator was refactored for a cleaner codebase with better error handling.
- **Optimization Tools**: The flex-search tool was restructured and modularized into ti-toolbox/opt/flex/. A multi-start approach was implemented allowing multiple iterations to find the best solution. The ex-search tool received enhancements for better ROI handling and faster analysis.
- **GUI Enhancements**: Multiple GUI improvements enhance the user experience. A centralized Path Manager handles path operations across all GUI tabs. Console output was standardized for consistent logging and status updates. Confirmation dialogs now appear before long-running processes. A debug mode provides optional verbose output for troubleshooting. An OpenGL fallback system provides automatic compatibility handling for macOS issues.
- **Documentation**: More documentation was added covering new features. New wiki pages document cluster permutation testing, electrode placement, MOVEA optimization, tissue analyzer, visual exporter, nilearn visuals, nifti group averaging, and quick notes. A pipeline flow diagram provides visual representation of the complete workflow. A detailed Blender tutorial offers step-by-step guidance for 3D visualization. Installation documentation was streamlined with updated setup instructions and removal of executable references. The gallery was updated with new screenshots showcasing all GUI features.
- **CI/CD & Testing**: A CI/CD pipeline was implemented with automated testing and Codecov integration for code coverage tracking. The test suite was expanded covering most modules, including new test files for calc, constants, core integration, mesh, errors, ex-analyzer, nifti, paths, process, utils, and MOVEA optimizer with integration tests. CircleCI integration now provides automated testing on every commit with proper permissions and workflows.
- **Development Tools**: Developer experience was improved with enhanced dev environment setup in dev/bash_dev/ for contributors. Version control management was improved for better consistency across all files. The project standardized on the simnibs_python interpreter for all Python operations. Container communication between FreeSurfer and SimNIBS was enhanced for better data sharing.

#### Fixes
- **Bug Fixes & Refinements**: Numerous bug fixes and refinements were implemented including BIDS structure compliance improvements, resolution of deadlock issues in GUI tabs, improved overwrite protection across all tools, fixed electrode naming consistency, better handling of network volumes, X11 and OpenGL fixes for cross-platform compatibility, and reduced console bloat with improved logging throughout the application.
- **Removals & Cleanup**: Significant cleanup was performed removing all executable launcher code (over 7,000 lines), eliminating old MATLAB dependencies, removing outdated documentation and assets, cleaning up redundant development files.

#### Download Links
- Docker Image: `docker pull idossha/simnibs:v2.2.0`
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)** - Main launch script
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)** - Docker configuration

---

### v2.1.3

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

---

### v2.1.2

**Release Date**: September 08, 2025

#### Additions
- Example Dataset: Toolbox now ships with Ernie & MNI152 MRI scans for quick start & learning purposes.
- Tissue Analyzer: Added skin thickness and volume analysis

#### Fixes
- Various bug fixes: charm, ex-search, flex-search

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.1.1

**Release Date**: August 28, 2025

#### Additions
- N/A

#### Fixes
- **ex-search**: fixed final.csv output
- **flex-search**: fixed cleanup of directory if users choose a single start

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.1.0

**Release Date**: August 25, 2025

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

---

### v2.0.5

**Release Date**: July 10, 2025

#### Additions
- **Group Analysis Features**: Group analysis system with GUI interface, comparison capabilities, and logging
- **Focality Measurement**: New focality analysis tools with histogram generation for cortical analysis
- **Normal Component Analysis**: Added normal component matrics and visualization
- **Enhanced Workflow**: Multiple subject selection for flex-search, new naming conventions

#### Fixes
- **GUI Stability**: Multiple bug fixes for group analysis GUI, element resizing, console widget consistency, and special character handling
- **Analysis Accuracy**: Improved histogram generation, ROI comparison plots
- **Visualization**: Fixed mesh visualization and updated mesh visualizer functionality

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.4

**Release Date**: June 26, 2025

#### Additions
- flex-search -> simulator integration. Simulator now recognizes previous flex-searches and allows for simulation of both optimized and mapped electrodes.
- system monitor -> added a GUI tab that allows users monitor the activity of processes hapenning within the toolbox

#### Fixes
- pre-process -> added missing shell for recon-all step
- pre-process -> fixed parallalization problem
- ex-search redesign -> now is not dependent on MATLAB Runtime, but is fully Python implemented
- ex-search -> users can now creat multiple leadfields for the same subject
- flex-search -> post processing method for TI envelope direction is implemented

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.3

**Release Date**: June 20, 2025

#### Additions
- Modified tes_flex_optimization.py to include eeg_net field in the .json
- toggle between "Montage Simulation" (traditional) and "Flex-Search Simulation" with automatic discovery of optimization results and electrode type selection (mapped/optimized/both)
- Modified TI.py and pipeline scripts to handle direct XYZ electrode coordinates instead of just electrode names, enabling optimized electrode positioning from flex-search results

#### Fixes
- N/A

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.2

**Release Date**: June 19, 2025

#### Additions
- Enhanced X11 support for Windows with automatic host IP detection and VcXsrv/Xming configuration guidance
- Created `windows_x11_setup.sh` helper script for simplified Windows X server setup
- Added comprehensive Windows BIDS path guide (`WINDOWS_BIDS_PATH_GUIDE.md`) with troubleshooting tips
- Improved cross-platform X11 configuration with better error handling and user guidance
- Added OpenGL software rendering flags for better GUI compatibility across all platforms

#### Fixes
- Fixed volume mounting in docker-compose.yml - all required volumes now properly mounted to simnibs container
- Fixed Windows path handling - automatic conversion of backslashes to forward slashes for Docker compatibility
- Fixed paths with spaces on Windows - automatic quoting of paths containing spaces
- Fixed X11 socket mounting for macOS XQuartz and Linux compatibility
- Fixed DISPLAY environment variable configuration for Windows, macOS, and Linux
- Fixed MATLAB Runtime library paths in container environment
- Updated XQuartz version warning to reference memory about v2.7.7 compatibility requirement

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.1

**Release Date**: June 11, 2025

#### Additions
- new logger and report generators under 'projectDIR/derivatives/'  
- sub-cortical atlas based targeting for flex-search (example: thalamus targeting)  

#### Fixes
- 2 decimal spherical ROIs  
- 'TI.py' overwrite protection removed  
- intenral 185 EGI net (removed 2 missed electrodes)  
- added imagemagick for montage visualizer  

#### Download Links
- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

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

---

## Version Support

We actively support and maintain versions 2.x.x and newer of the Temporal Interference Toolbox. Versions 1.x.x are no longer supported.

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions) 
