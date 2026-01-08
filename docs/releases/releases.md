---
layout: releases
title: Latest Release
permalink: /releases/
---

### v2.2.3 (Latest Release)

**Release Date**: January 07, 2026

#### Additions
- **New Blender Tool for Full Blend File Creation**: Complete Blender integration with automated blend file generation, electrode positioning, and visualization setup. Streamlined workflow for creating publication-ready 4D visualizations directly from simulation results.
- **New Correlation Mode for Cluster-Based Permutation Testing**: Enhanced statistical analysis capabilities with correlation-based cluster permutation testing, providing more robust statistical inference for connectivity and relationship analyses.
- **Unified Command-Line Experience**: All CLI tools now support both interactive mode (run without arguments) and direct mode (with flags). Consistent colored output, clear prompts, and intelligent option discovery across all commands.
- **Multi-Processing Simulator**: Parallel processing capabilities for faster simulation runs, optimized resource utilization, and scalable performance across different hardware configurations.
- **Enhanced Testing Suite Coverage**: Comprehensive test coverage expansion including simulator workflows, statistical analysis pipelines, and integration testing for improved reliability and stability.
- **Improved Security CI/CD Pipeline**: Strengthened GitHub Actions workflows with enhanced security scanning, automated vulnerability detection, and improved code quality gates throughout the development pipeline.

#### Fixes
- **Experimental Movea Tool**: Temporarily removed the experimental movea tool to focus development efforts on core functionality and stability.
- **Bug Fixes & Reliability**: Fixed GUI crashes and timeout issues. Improved path handling and import reliability. Updated electrode templates for better compatibility. Enhanced security scanning and CI/CD workflows.
- **Documentation Updates**: New CLI and GUI documentation pages. Improved Blender integration instructions. Added visualizer documentation. Better organization of documentation images.

#### Download Links

**Desktop App (latest):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.2.3-x64.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.2.3-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.2.3-Setup.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/latest/download/TI-Toolbox-2.2.3.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/latest/download/ti-toolbox-2.2.3.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:latest`

For installation instructions, see the [Installation Guide]({{ site.baseurl }}/installation/).

---

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/installation/#troubleshooting) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)

