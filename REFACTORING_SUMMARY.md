# Codebase Refactoring Summary

## Overview
This document summarizes the structural changes made to the TI-Toolbox codebase after directory and file renaming operations.

## Structural Changes

### 1. Directory Renaming
- `assets/` → `resources/`
- `CLI/` → `cli/`
- `GUI/` → `gui/`
- `MOVEA/` → `movea/`

### 2. Codebase Location
- All code moved from project root to `ti-toolbox/` subdirectory

## Files Updated

### Configuration and Loader Scripts
- `loader.sh` - Updated 4 references from `assets/` to `resources/`
- `dev/update/update_version.py` - Updated dataset descriptions directory path
- `dev/bash_dev/loader_dev.sh` - Updated 4 references from `assets/` to `resources/`

### Docker and Container Files
- `container/blueprint/Dockerfile.simnibs` - Updated paths for:
  - ElectrodeCaps_MNI directory
  - tes_flex_optimization.py extension
  - CLI scripts directory
- `container/blueprint/entrypoint.sh` - Updated CLI paths and aliases

### Test Files
- `tests/run_tests.sh` - Updated:
  - CLI directory references
  - ElectrodeCaps_MNI path
  - tes_flex_optimization.py path
- `tests/test_simulator_runner.sh` - Updated simulator script paths
- `tests/test_analyzer_runner.sh` - Updated analyzer script paths

### CLI Scripts
- `ti-toolbox/cli/GUI.sh` - Updated main.py path from `GUI/` to `gui/`
- `ti-toolbox/cli/movea.sh` - Updated:
  - MOVEA directory reference
  - Python import statements
  - ElectrodeCaps_MNI path

### Pre-processing Scripts
- `ti-toolbox/pre-process/structural.sh` - Updated dataset descriptions path
- `ti-toolbox/pre-process/dicom2nifti.sh` - Updated dataset descriptions path
- `ti-toolbox/pre-process/charm.sh` - Updated dataset descriptions path
- `ti-toolbox/pre-process/recon-all.sh` - Updated dataset descriptions path

### GUI Components
- `ti-toolbox/gui/main.py` - Fixed version.py import path (now goes up two levels to project root)
- `ti-toolbox/gui/analyzer_tab.py` - Updated MNI152 template error message
- `ti-toolbox/gui/flex_search_tab.py` - Updated MNI152 template error message
- `ti-toolbox/gui/electrode_placement_gui.py` - Updated import from `GUI.components` to `gui.components`
- `ti-toolbox/gui/movea_tab.py` - Updated:
  - Import statement from `MOVEA` to `movea`
  - Presets.json path reference
  - MOVEA directory references
- `ti-toolbox/gui/gui_dev/QUICK_START_DEV.md` - Updated GUI directory paths in documentation

### MOVEA Module
- `ti-toolbox/movea/leadfield_script.py` - Updated import from `MOVEA` to `movea`
- `ti-toolbox/movea/README.md` - Updated import examples from `MOVEA` to `movea`

### Tools
- `ti-toolbox/tools/visualize-montage.sh` - Updated AMV resource paths

## Import Statement Changes

### Python Imports
All Python import statements were updated to use lowercase module names:
- `from MOVEA import ...` → `from movea import ...`
- `from GUI.components import ...` → `from gui.components import ...`

## Path Reference Changes

### Resource Paths
All references to the `assets/` directory were updated to `resources/`:
- Dataset description templates
- ElectrodeCaps_MNI files
- Atlas files (MNI152 templates)
- AMV coordinate files
- Map-electrodes optimization extensions

### CLI Paths
All references to `CLI/` were updated to `cli/`:
- Script execution paths
- Bash aliases
- Docker entrypoint configurations

### GUI Paths
All references to `GUI/` were updated to `gui/`:
- Main GUI launcher
- Import statements
- Development documentation

## Summary Statistics
- **Total files modified**: 24
- **Directory renames**: 4 (assets, CLI, GUI, MOVEA)
- **Import statements updated**: 6
- **Path references updated**: ~50+

## Notes
- Documentation files in `docs/` were not modified as they contain historical references
- All changes maintain backward compatibility where possible
- No functional code changes were made, only structural/naming updates

