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

- **[Overview](overview)** - The project at a glance: what every subject has, and what it is ready for
- **[Pre-Processing](pre-processing)** - Structural MRI preparation and head-model generation
- **[Diffusion Processing](diffusion-processing)** - QSIPrep/QSIRecon integration for DTI-based anisotropic simulations
- **[Simulator](simulator)** - One row per simulation job, with free-hand electrode placement on the subject's own scalp
- **[Flex Search](flex-search)** - The Optimizer's *Flex* method: differential-evolution electrode optimization
- **[Ex Search](ex-search)** - The Optimizer's *Ex* method: exhaustive search over a leadfield matrix
- **[Multipolar TI (mTI)](mti)** - Multi-channel TI simulation with 4+ electrode pairs, and multipolar exhaustive search
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
- **[Brain Atlases](atlases)** - The four MNI-space atlases shipped with TI-Toolbox
- **[Atlas Resampling](atlas-resampling)** - Working with brain atlases and resampling
- **[Montage Visualizer](montage_visualizer)** - Electrode montage visualization on head
- **[Electrode Mapping](electrode-mapping)** - Optimal electrode position mapping to EEG nets

### Extensions
- **[Optional Tools](extension)** - The panels you switch on in **Settings > Optional tools**
- **[3D Visual Exporter](blender)** - PLY/GLB/Blender exports: PLY/GLB/Blender exports of regions, vectors and montages
- **[Free Electrode Placement](electrode-placement)** - Clicking electrodes onto the scalp, now part of the Simulator
- **[Nilearn Visuals](nilearn-visuals)** - Publication-ready brain visualizations
- **[Cluster-Based Permutation Testing](cluster-permutation-testing)** - Non-parametric statistical analysis (the *Permutation Analysis* extension)
- **[Quick Notes](quick-notes)** - Timestamped note-taking during analysis sessions
- **[NIfTI Group Averaging](nifti-group-averaging)** - Group analysis and comparison tools
- **[Tissue Analyzer](tissue-analyzer)** - Volume and thickness assessment for CSF, bone, and skin (part of pre-processing)

### Development & Testing
- **[Testing Pipeline](testing-pipeline)** - Comprehensive CI/CD testing pipeline with CircleCI integration
- **[Python Environment](python_env)** - Managing the SimNIBS Python environment and dependencies
- **[Desktop Application](desktop-app)** - Electron app, container lifecycle and the server it talks to
- **[Agent Plugin Internals](agent-plugin)** - Skills, MCP server architecture, and tests behind the AI assistant integration
- **[API Reference](../api/)** - Complete Python API documentation (auto-generated from docstrings)
- **[PyQt GUI (historical)](gui)** - The v2 tabbed Qt interface, removed in v3.0.0 and kept for reference

## Support

For additional help, installation instructions, and development resources, check the links in the sidebar or visit our [GitHub repository](https://github.com/idossha/TI-Toolbox). 
