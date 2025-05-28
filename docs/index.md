---
layout: home
---

<div class="hero">
  <h1>Temporal Interference Toolbox</h1>
  <p>Advanced Brain Stimulation Simulation Platform</p>
  <p>A comprehensive toolbox for temporal interference stimulation research, providing end-to-end neuroimaging and simulation capabilities.</p>
  <div class="hero-buttons">
    <a href="/releases" class="btn">View Releases</a>
    <a href="/documentation" class="btn btn-secondary">Get Started</a>
  </div>
</div>

<div class="features">
  <div class="feature-card">
    <div class="feature-icon">🧠</div>
    <h3>Pre-processing Pipeline</h3>
    <p>DICOM to NIfTI conversion, FreeSurfer cortical reconstruction, and SimNIBS head modeling</p>
  </div>
  <div class="feature-card">
    <div class="feature-icon">⚡</div>
    <h3>TI Field Simulation</h3>
    <p>FEM-based temporal interference field calculations with flexible simulation parameters</p>
  </div>
  <div class="feature-card">
    <div class="feature-icon">🎯</div>
    <h3>Optimization Algorithms</h3>
    <p>Flexible (flex-search) and exhaustive (ex-search) algorithms for optimal electrode placement and stimulation</p>
  </div>
  <div class="feature-card">
    <div class="feature-icon">📊</div>
    <h3>Comprehensive Analysis</h3>
    <p>Atlas-based and custom ROI analysis tools for detailed stimulation effect evaluation</p>
  </div>
  <div class="feature-card">
    <div class="feature-icon">🖼️</div>
    <h3>Interactive Visualization</h3>
    <p>NIfTI and mesh viewers, overlay tools, and real-time 3D rendering</p>
  </div>
  <div class="feature-card">
    <div class="feature-icon">🐳</div>
    <h3>Docker-based</h3>
    <p>Containerized environment for reproducibility and easy deployment</p>
  </div>
</div>

## Quick Start Workflow

1. **Set up your BIDS project directory**
   - Organize your data in BIDS format. Place DICOM files in `sourcedata/sub-<subject>/T1w/dicom/` (and optionally T2w).
2. **Install Docker Desktop**
   - Required for running the toolbox environment.
3. **Get the Latest Release**
   - Download the launcher or CLI from the <a href="/releases">Releases page</a>.
4. **Pre-process your data**
   - Convert DICOM to NIfTI, run FreeSurfer, and create SimNIBS head models using the pre-processing pipeline.
5. **Optimize electrode placement**
   - Use <b>flex-search</b> (evolutionary) or <b>ex-search</b> (exhaustive) tools to find optimal stimulation parameters.
6. **Simulate TI fields**
   - Run FEM-based simulations for your selected montages and parameters.
7. **Analyze and visualize results**
   - Use the analyzer and visualization tools for ROI-based and atlas-based analysis, and to generate figures and reports.

For more details, see the <a href="/documentation">Documentation</a>.

## Key Tools

- **Pre-processing**: DICOM to NIfTI, FreeSurfer, SimNIBS
- **Optimization**: flex-search, ex-search
- **Simulation**: TI/mTI field solvers
- **Analysis**: ROI/atlas-based tools
- **Visualization**: NIfTI/mesh viewers, report generator

## System Requirements

- **OS**: macOS 10.14+, Ubuntu 18.04+, Windows 10+
- **Docker Desktop**: Latest version
- **RAM**: 16GB (32GB recommended)
- **Storage**: 50GB free space
- **GPU**: NVIDIA CUDA (optional)

## Latest Release

See the <a href="/releases">Releases page</a> for the latest version and change log.

## Community

- [GitHub Repository](https://github.com/idossha/TI-Toolbox)
- [Issue Tracker](https://github.com/idossha/TI-Toolbox/issues)
- [Discussions](https://github.com/idossha/TI-Toolbox/discussions)

## Citation

If you use the Temporal Interference Toolbox in your research, please cite:

```bibtex
@software{temporalinterference2024,
  title = {Temporal Interference Toolbox},
  author = {Your Name and Contributors},
  year = {2024},
  version = {2.0.1},
  url = {https://github.com/idossha/TI-Toolbox}
}
``` 