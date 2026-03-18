---
layout: releases
title: Latest Release
permalink: /releases/
---

### v2.3.0 (Latest Release)

**Release Date**: March 17, 2026

This is a major release that introduces a number of new features, but mainly a massive change to internal modernization of the codebase. Plus, we are now wrapping SimNIBS 4.6.0.

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

**Desktop App (latest):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.3.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.3.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox.Setup.2.3.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.3.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/latest/download/ti-toolbox_2.3.0_amd64.deb)

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

