---
layout: releases
title: Latest Release
permalink: /releases/
---

Moved to support bash entrypoint only, see the [Bash Script & Compose YAML](https://github.com/idossha/TI-Toolbox/tree/main/launcher/bash).

---

### v2.2.0 (Latest Release)

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
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/).

---

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)

