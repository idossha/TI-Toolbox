---
layout: page
title: Releases
permalink: /releases/
---

# Release History

All notable changes and releases for TI-CSC are documented here.

<div class="release">
  <div class="release-header">
    <h2>Version 2.0.0</h2>
    <span class="release-date">December 2024</span>
  </div>
  
  <p><strong>Major Release - Complete Architecture Overhaul</strong></p>
  
  <h3>🎉 New Features</h3>
  <ul>
    <li>Completely new PyQt6-based launcher application</li>
    <li>Automatic Docker container management</li>
    <li>Integrated progress tracking for long operations</li>
    <li>Native executables for macOS, Linux, and Windows</li>
    <li>Improved XQuartz integration for macOS GUI support</li>
    <li>Desktop shortcut creation</li>
    <li>Real-time console output with color coding</li>
  </ul>
  
  <h3>🚀 Improvements</h3>
  <ul>
    <li>30% faster simulation engine</li>
    <li>Reduced Docker image size by 25%</li>
    <li>Better error handling and user feedback</li>
    <li>Streamlined installation process</li>
    <li>Updated to latest SimNIBS 4.0</li>
    <li>FreeSurfer 7.3 integration</li>
  </ul>
  
  <h3>🐛 Bug Fixes</h3>
  <ul>
    <li>Fixed GUI display issues on high-DPI screens</li>
    <li>Resolved Docker path detection on Apple Silicon</li>
    <li>Fixed memory leaks in long-running simulations</li>
    <li>Corrected electrode placement accuracy</li>
  </ul>
  
  <div class="release-downloads">
    <a href="https://github.com/idossha/TI-CSC-2.0/releases/download/v2.0.0/TI-CSC-macOS-universal.dmg">macOS</a>
    <a href="https://github.com/idossha/TI-CSC-2.0/releases/download/v2.0.0/TI-CSC-Linux-x86_64.AppImage">Linux</a>
    <a href="https://github.com/idossha/TI-CSC-2.0/releases/download/v2.0.0/TI-CSC-Windows-x64.exe">Windows</a>
  </div>
</div>

<div class="release">
  <div class="release-header">
    <h2>Version 1.5.2</h2>
    <span class="release-date">October 2024</span>
  </div>
  
  <p><strong>Maintenance Release</strong></p>
  
  <h3>🚀 Improvements</h3>
  <ul>
    <li>Updated dependencies for security</li>
    <li>Performance optimizations for mesh generation</li>
    <li>Improved documentation</li>
  </ul>
  
  <h3>🐛 Bug Fixes</h3>
  <ul>
    <li>Fixed crash when loading corrupted NIfTI files</li>
    <li>Resolved issues with non-standard BIDS structures</li>
    <li>Fixed GUI freezing during long operations</li>
  </ul>
</div>

<div class="release">
  <div class="release-header">
    <h2>Version 1.5.0</h2>
    <span class="release-date">August 2024</span>
  </div>
  
  <p><strong>Feature Release</strong></p>
  
  <h3>🎉 New Features</h3>
  <ul>
    <li>GPU acceleration support for NVIDIA cards</li>
    <li>New optimization algorithms (genetic algorithm, particle swarm)</li>
    <li>Export to common neuroimaging formats</li>
    <li>Batch processing capabilities</li>
    <li>ROI drawing tools in GUI</li>
  </ul>
  
  <h3>🚀 Improvements</h3>
  <ul>
    <li>2x faster electrode optimization</li>
    <li>Reduced memory usage by 40%</li>
    <li>Better multi-core CPU utilization</li>
    <li>Improved GUI responsiveness</li>
  </ul>
  
  <h3>🐛 Bug Fixes</h3>
  <ul>
    <li>Fixed coordinate system misalignment</li>
    <li>Resolved Docker volume mounting issues</li>
    <li>Fixed GUI scaling on 4K displays</li>
  </ul>
</div>

<div class="release">
  <div class="release-header">
    <h2>Version 1.0.0</h2>
    <span class="release-date">January 2024</span>
  </div>
  
  <p><strong>Initial Public Release</strong></p>
  
  <h3>🎉 Features</h3>
  <ul>
    <li>Complete TI simulation pipeline</li>
    <li>FreeSurfer and SimNIBS integration</li>
    <li>Basic optimization algorithms</li>
    <li>Command-line interface</li>
    <li>Basic GUI for visualization</li>
    <li>Docker-based deployment</li>
    <li>BIDS compatibility</li>
  </ul>
</div>

## Version Support

| Version | Status | Support Until |
|---------|--------|---------------|
| 2.0.x   | Active | December 2026 |
| 1.5.x   | Maintenance | December 2025 |
| 1.0.x   | End of Life | June 2024 |

## Upgrade Guide

### From 1.x to 2.0

1. **Backup your data** - Always backup your project directories
2. **Uninstall old version** - Remove the previous installation
3. **Install new launcher** - Download and install the new executable
4. **Update Docker images** - The new launcher will handle this automatically
5. **Migrate projects** - Your existing BIDS directories are compatible

### Breaking Changes in 2.0

- Command-line syntax has changed for some commands
- Configuration file format updated (migration tool available)
- Minimum Docker Desktop version requirement increased
- XQuartz 2.8.1+ no longer supported on macOS (use 2.7.7 or 2.8.0)

## Release Notes Archive

For older releases and detailed changelogs, visit our [GitHub Releases](https://github.com/idossha/TI-CSC-2.0/releases) page.

## Release Schedule

We follow a regular release schedule:

- **Major releases** (x.0.0): Annually in Q4
- **Feature releases** (x.y.0): Quarterly
- **Patch releases** (x.y.z): As needed for critical fixes

## Beta Releases

Interested in testing new features? Join our beta program:

1. Sign up for the [beta mailing list](https://ti-csc.org/beta)
2. Download beta releases from the [beta channel](https://github.com/idossha/TI-CSC-2.0/releases?q=prerelease%3Atrue)
3. Report issues with the `beta` label

## Contributing

Want to contribute to TI-CSC? Check our [contribution guidelines](https://github.com/idossha/TI-CSC-2.0/blob/main/CONTRIBUTING.md). 