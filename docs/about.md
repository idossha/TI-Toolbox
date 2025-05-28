---
layout: page
title: About
permalink: /about/
---

# About Temporal Interference Toolbox

The Temporal Interference Toolbox is an open-source platform for advanced brain stimulation research. It provides a complete pipeline for temporal interference (TI) stimulation, from raw neuroimaging data to simulation, optimization, analysis, and visualization.

## Key Features

- **BIDS-compliant**: Organize your data using the Brain Imaging Data Structure
- **Pre-processing**: DICOM to NIfTI, FreeSurfer, SimNIBS head modeling
- **Optimization**: flex-search (evolutionary) and ex-search (exhaustive) algorithms
- **Simulation**: FEM-based TI/mTI field solvers
- **Analysis**: ROI and atlas-based tools
- **Visualization**: NIfTI/mesh viewers, report generator
- **Docker-based**: Fully containerized for reproducibility and easy deployment

## Workflow Overview

1. Set up your BIDS project directory
2. Install Docker Desktop
3. Download the latest release (2.x.x or newer) from the [releases page](/releases). Note: Versions 1.x.x are no longer supported.
4. Pre-process your data
5. Optimize electrode placement
6. Simulate TI fields
7. Analyze and visualize results

For more details, see the [documentation](/documentation) or [wiki](/wiki).

## Community & Support

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
  version = {2.2.4},
  url = {https://github.com/idossha/TI-Toolbox}
}
```

## Get Involved

### For Researchers
- Use Temporal Interference Toolbox in your research
- Share your results and feedback
- Contribute to validation studies

### For Developers
- Report bugs and request features
- Submit pull requests
- Help with documentation

### For Everyone
- Join our community discussions
- Spread the word about Temporal Interference Toolbox
- Attend our workshops and webinars

## Acknowledgments

We thank all contributors, users, and supporters who have helped make Temporal Interference Toolbox a valuable resource for the brain stimulation research community. 