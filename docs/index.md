---
layout: home
---

<div class="hero">
  <h1>Temporal Interference Toolbox</h1>
</div>

## Overview

The **TI-Toolbox** designed for end-to-end workflows simulating Temporal Interference (TI). It integrates several open-source applications along with custom in-house scripts, providing a robust platform for academic research. 

## Features

- **SimNIBS**: A simulation environment for transcranial brain stimulation, enabling electric field modeling.
- **FSL**: A comprehensive library of tools for analysis of functional and structural brain imaging data.
- **FreeSurfer**: A software suite for the analysis and visualization of structural and functional neuroimaging data.
- **Gmsh**: A three-dimensional finite element mesh generator with a built-in CAD engine and post-processor.
- **Custom Scripts**: In-house developed scripts optimized for specific tasks within the TI-Toolbox pipeline, including mesh processing, NIfTI conversion, and ROI management.

### Citation and Recognition

TI-toolbox uses the following open-source tools:

- **SimNIBS**: [SimNIBS Citation](https://simnibs.github.io/simnibs/build/html/publications.html)
- **FSL**: [FSL Citation](https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/RecommendedPapers)
- **FreeSurfer**: [FreeSurfer Citation](https://surfer.nmr.mgh.harvard.edu/fswiki/FreeSurferMethodsCitation)
- **Gmsh**: [Gmsh Citation](http://gmsh.info/#Acknowledging)





## Quick Start Workflow

1. **Set up your BIDS project directory**
   - Organize your data in BIDS format. Place DICOM files in `sourcedata/sub-<subject>/T1w/dicom/` (and optionally T2w).
2. **Install Docker Desktop**
   - Required for running the toolbox environment.
3. **Get the Latest Release**
   - Download the latest version (2.x.x or newer) from the <a href="/releases">Releases page</a>. See the <a href="/installation">Installation Guide</a> for platform-specific instructions. Note: Versions 1.x.x are no longer supported.

For more details, see the <a href="{{ site.baseurl }}/wiki">Wiki</a>.

## System Requirements

- **OS**: macOS 10.14+, Ubuntu 18.04+, Windows 10+
- **Docker Desktop**: Latest version
- **RAM**: 16GB (32GB recommended for full functionality)
- **Storage**: 50GB free space

## Version Support

We actively support and maintain versions 2.x.x and newer of the Temporal Interference Toolbox. Versions 1.x.x are no longer supported. For the latest version and changelog, please see the <a href="/releases">Releases page</a>.


## Acknowledgments

We extend our gratitude to the developers and contributors of the open-source tools integrated into the TI-Toolbox. Their work has been instrumental in advancing research in the field of neurostimulation.

## Community

- [GitHub Repository](https://github.com/idossha/TI-Toolbox)
- [Issue Tracker](https://github.com/idossha/TI-Toolbox/issues)
- [Discussions](https://github.com/idossha/TI-Toolbox/discussions)

