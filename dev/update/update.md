# Major Changes Since v2.1.3

## Core Infrastructure & Architecture

The project underwent a complete restructure, removing old launcher directories and consolidating to a unified ti-toolbox structure. A new core module system was introduced in ti-toolbox/core/ with reusable components including paths.py, calc.py, constants.py, errors.py, process.py, utils.py, nifti.py, mesh.py, and viz.py. The project moved away from executable compilation and now focuses exclusively on Docker-based distribution. The loader script was completely rewritten with cleaner output and better error handling, while Docker entrypoint improvements enhanced container initialization and environment setup.

## CI/CD & Testing

A complete CI/CD pipeline was implemented with automated testing and Codecov integration for code coverage tracking. The test suite was massively expanded with over 3,000 lines of new tests covering all modules, including new test files for calc, constants, core integration, mesh, errors, ex-analyzer, nifti, paths, process, utils, and MOVEA optimizer with integration tests. CircleCI integration now provides automated testing on every commit with proper permissions and workflows.

## GUI Extensions System

A new modular extension system was introduced in ti-toolbox/gui/extensions/ providing several powerful tools. The Cluster-Based Permutation Testing (CBP) extension offers statistical analysis for group comparisons with seaborn-based visualizations. Nilearn Visuals enables brain visualization using nilearn with glass brain views, surface plots, and statistical maps. The NIfTI Group Averaging tool allows averaging multiple NIfTI files across subjects. The Visual Exporter provides export capabilities to Blender-compatible formats (PLY, STL) with a full tutorial. Additional extensions include Quick Notes for in-app note-taking with persistence, Subject Info Viewer for displaying metadata and processing status, and an Electrode Placement Tool for interactive electrode positioning and validation.

## 3D Visualization & Export

A comprehensive 3D Exporter module was added in ti-toolbox/3d_exporter/ containing four specialized tools. TI_quick_volumetric.py provides fast volumetric field exports, cortical_regions_to_ply.py handles region-specific mesh exports, cortical_regions_to_stl.py outputs STL format for 3D printing, and vector_ply.py enables vector field visualization in Blender. The system now automatically generates .opt files when saving mesh files, creating corresponding Blender options files for seamless workflow integration.

## MOVEA Optimization

Full MOVEA integration was implemented for multi-objective optimization of electrode placement. The system now uses a centralized leadfield with unified leadfield target locations across all optimization tools. A complete MOVEA GUI tab provides an interface for optimization workflows. The code was reorganized into ti-toolbox/opt/movea/ with dedicated optimizer.py and visualizer.py modules for better maintainability.

## Analysis Tools

Several new and improved analysis tools were introduced. The Tissue Analyzer is a new tool for analyzing tissue-specific field distributions across CSF, skin, bone, and other tissue types. Group Analyzer received significant improvements including enhanced multi-subject analysis capabilities with MNI coordinate support. Voxel analysis was updated with better visualization and cortex overlay capabilities. Atlas resampling optimization provides faster and more accurate atlas-based analysis workflows.

## Statistics Module

A comprehensive statistics package was created in ti-toolbox/stats/ with extensive functionality. The cluster_permutation.py module implements non-parametric cluster-based permutation testing. Supporting modules include atlas_utils.py for atlas manipulation, stats_utils.py with over 900 lines of statistical analysis functions, posthoc_atlas_analysis.py for post-hoc ROI analysis, reporting.py for automated statistical reports, and visualization.py for statistical plotting using seaborn.

## Simulator Improvements

The simulator received substantial enhancements including a new free-hand mode that allows direct electrode coordinate input without montage selection. The entire simulator was refactored for a cleaner codebase with better error handling. Enhanced simulation reports now include montage visualization. Dynamic timestep handling improves simulation parameter management, and high-frequency fields are now available as outputs in the NIfTI viewer.

## Optimization Tools

The flex-search tool was restructured and modularized into ti-toolbox/opt/flex/ with proper Python packaging. A multi-start approach was implemented allowing multiple iterations to find the best solution. The ex-search tool received enhancements for better ROI handling and analysis. All optimization tools now share centralized leadfield generation code for consistency and maintainability.

## GUI Enhancements

Multiple GUI improvements enhance the user experience. A centralized Path Manager handles path operations across all GUI tabs. Console output was standardized for consistent logging and status updates. Confirmation dialogs now appear before long-running processes. A debug mode provides optional verbose output for troubleshooting. The System Monitor tab offers resource usage tracking and visualization. Error handling was improved with better crash recovery and user feedback. An OpenGL fallback system provides automatic compatibility handling for macOS issues.

## Documentation

Comprehensive documentation was added covering all new features. New wiki pages document cluster permutation testing, electrode placement, MOVEA optimization, tissue analyzer, visual exporter, nilearn visuals, nifti group averaging, and quick notes. A pipeline flow diagram provides visual representation of the complete workflow. A detailed Blender tutorial offers step-by-step guidance for 3D visualization. Installation documentation was streamlined with updated setup instructions and removal of executable references. The gallery was updated with new screenshots showcasing all GUI features.

## Development Tools

Developer experience was improved with enhanced dev environment setup in dev/bash_dev/ for contributors. Version control management was improved for better consistency across all files. The project standardized on the simnibs_python interpreter for all Python operations. Container communication between FreeSurfer and SimNIBS was enhanced for better data sharing.

## Bug Fixes & Refinements

Numerous bug fixes and refinements were implemented including BIDS structure compliance improvements, resolution of deadlock issues in GUI tabs, improved overwrite protection across all tools, fixed electrode naming consistency, better handling of network volumes, X11 and OpenGL fixes for cross-platform compatibility, and reduced console bloat with improved logging throughout the application.

## Removals & Cleanup

Significant cleanup was performed removing all executable launcher code (over 7,000 lines), eliminating old MATLAB dependencies, removing outdated documentation and assets, cleaning up redundant development files, and removing direct NIfTI visualization code that was replaced with the new extensions system.

## Summary

This release represents approximately 20,000+ lines of new code with major architectural improvements, new features, comprehensive testing coverage, and a shift to a more modular and maintainable codebase. The focus has moved entirely to Docker-based deployment, eliminating the complexity of cross-platform executable compilation while providing more powerful analysis and visualization tools through the new extensions system.

