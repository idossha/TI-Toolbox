---
layout: wiki
title: Wiki
permalink: /wiki/
---

Welcome to the Temporal Interference Toolbox Wiki. Here you'll find detailed guides and documentation for all aspects of the toolbox. Check out our [Video Tutorials](video-tutorials) for step-by-step visual guides. Something broken? Start at the **[Troubleshooting Archive](troubleshooting)** — the maintainer-verified list of known problems and fixes.


### The application

The v3 desktop app is one window with a workflow-ordered rail. These pages describe what each row
of that rail does; see [Desktop Application](desktop-app) for how the app, the container and the
server fit together.

- **[Overview](overview)** - Welcome, project opening and switching, then the project at a glance
- **[Pre-Processing](pre-processing)** - Structural MRI preparation and head-model generation
- **[Diffusion Processing](diffusion-processing)** - QSIPrep/QSIRecon integration for DTI-based anisotropic simulations
- **[Simulator](simulator)** - One row per simulation job, with free-hand electrode placement on the subject's own scalp
- **[Flex Search](flex-search)** - The Optimizer's *Flex* method: differential-evolution electrode optimization
- **[Ex Search](ex-search)** - The Optimizer's *Ex* method: exhaustive search over a leadfield matrix
- **[Analyzer](analyzer)** - Field analysis in mesh and voxel space, one target per job row
- **[Pipeline](pipelines)** - Wire the steps into a graph and run the whole thing as one job group
- **[Notebooks](notebooks)** - Jupyter on the container's SimNIBS Python, inside the app
- **[Results](results)** - Every output a subject has, with reports rendered in place
- **[Viewer](visualizers)** - Tetravox, shipped in the image and drawn in the app window
- **[Jobs](jobs)** - Every run: state, logs, artifacts, cancel and rerun
- **[Scripting](scripting)** - CLI commands, JSON config entry points, and the Python scripting API
- **[Example Notebook](example-notebook)** - Executed Jupyter walkthrough of the Python API on Dataset 000, with real outputs and a downloadable `.ipynb`
- **[AI Assistant](ai-assistant)** - Plugin that teaches Claude Code, Codex, Cursor and other MCP clients how to use TI-Toolbox

### Embedded Tools
- **[Reports](reports)** - Understanding HTML simulation reports and results
- **[Logging](logging)** - Comprehensive logging system documentation
- **[Brain Atlases](atlases)** - The MNI-space atlases shipped with TI-Toolbox, the subject-space parcellations built during pre-processing, and atlas resampling
- **[Montage Visualizer](montage_visualizer)** - Electrode montage visualization on head
- **[Electrode Mapping](electrode-mapping)** - Optimal electrode position mapping to EEG nets

### Extensions
- **[Optional Tools](extension)** - The panels you switch on in **Settings > Optional tools**
- **[3D Visual Exporter](blender)** - PLY/GLB/Blender exports of regions, vectors and montages
- **[Free Electrode Placement](electrode-placement)** - Clicking electrodes onto the scalp, now part of the Simulator
- **[Nilearn Visuals](nilearn-visuals)** - Publication-ready brain visualizations
- **[Cluster-Based Permutation Testing](cluster-permutation-testing)** - Non-parametric statistical analysis (the *Permutation Analysis* extension)
- **[Quick Notes](quick-notes)** - An autosaving project notepad with optional timestamps
- **[NIfTI Group Averaging](nifti-group-averaging)** - Group analysis and comparison tools
- **[Tissue Analyzer](tissue-analyzer)** - Volume and thickness assessment for CSF, bone, and skin (part of pre-processing)

### Development & Testing (v3)
- **[Testing guide]({{ site.baseurl }}/wiki/development/)** - Current test strategy, commands, fixtures, and verification limits
- **[Python Environment](python_env)** - Managing the SimNIBS Python environment and dependencies
- **[Desktop Application](desktop-app)** - Electron app, container lifecycle and the server it talks to
- **[Agent Plugin Internals](agent-plugin)** - Skills, MCP server architecture, and tests behind the AI assistant integration
- **[API Reference](../api/)** - Complete Python API documentation (auto-generated from docstrings)

### V2 (deprecated): Development & Testing

These guides are preserved for developers maintaining v2 installations. Their Qt APIs and CI setup are historical and do not describe v3.

- **[V2 Development Archive](v2-development)** - Entry point for legacy developer references
- **[V2 Testing Pipeline](testing-pipeline)** - Archived pytest and CircleCI workflow
- **[V2 PyQt GUI](gui)** - The tabbed Qt interface removed in v3.0.0
- **[V2 Qt Extension API](extension/#architecture-historical)** - Legacy extension discovery and development
- **[V2 Gallery](../gallery/v2/)** - Screenshots of the legacy interface

## Support

For additional help, installation instructions, and development resources, check the links in the sidebar or visit our [GitHub repository](https://github.com/idossha/TI-Toolbox). 
