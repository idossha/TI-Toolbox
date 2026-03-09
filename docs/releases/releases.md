---
layout: releases
title: Latest Release
permalink: /releases/
---

### v2.3.0 (Latest Release)

**Release Date**: March 2026

#### Additions
- **Anisotropy Support**: Flex-search now supports 4 conductivity models (isotropic, volume-normalized, direct, multi-conductivity) via GUI dropdown and `FlexConfig.anisotropy_type` parameter.
- **Optimization Output Manifest**: Flex-search outputs `manifest.json` tracking generated files, best run metadata, and parameter log for reproducibility.
- **Unified Analyzer**: Single `Analyzer` class replaces the old mesh/voxel split. Unified sphere and cortex ROI handling. New `run_group_analysis()` for multi-subject comparisons.
- **Clean Python API**: One-liner imports across all modules — `from tit.sim import SimulationConfig, run_simulation`, `from tit.opt import FlexConfig, run_flex_search`, etc.
- **JSON Config Entrypoints**: All modules support `simnibs_python -m tit.<module> config.json` for programmatic and GUI-driven invocation. New `tit/config_io.py` handles typed serialization.
- **Rebuilt Test Suite**: 132 pytest tests covering all modules with comprehensive mocking. Runs in 0.28s.
- **Reusable GUI Components**: Extracted `ROIPickerWidget`, `ElectrodeConfigWidget`, `SolverParamsWidget` for cross-tab reuse.

#### Refactors & Improvements
- **PathManager Rewrite**: Replaced 930-line template engine with 180-line direct-method API. IDE autocompletion now works.
- **Module Reorganization**: Dissolved `tit/core/` — modules moved to `tit/paths`, `tit/constants`, `tit/calc`.
- **Logger Simplification**: Removed ~750 lines of custom handler/wrapper code. File-only logging with Qt bridge for GUI.
- **GUI Threading**: Eliminated all blocking `.wait()` calls. Signal-based completion.

#### Fixes
- GUI no longer freezes during long-running operations.
- Montage visualizer CSV header parsing corrected.
- Bare `except:` clauses replaced with `except Exception:`.

#### Breaking Changes
- `tit.core.*` imports no longer work — use `tit.paths`, `tit.constants`, `tit.calc` directly.
- `PathManager.path("key")` template API removed — use direct methods (`pm.m2m(sid)`).
- `MeshAnalyzer` and `VoxelAnalyzer` classes deleted — use unified `Analyzer`.

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

