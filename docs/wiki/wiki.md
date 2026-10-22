---
layout: wiki
title: Wiki
permalink: /wiki/
---

Welcome to the Temporal Interference Toolbox Wiki. Here you'll find detailed guides and documentation for all aspects of the toolbox. The [Video Tutorials]({{ site.baseurl }}/wiki/video-tutorials/) were recorded with v2, so the interface differs from v3. Something broken? Start at **[Troubleshooting]({{ site.baseurl }}/wiki/troubleshooting/)** — the maintainer-verified list of known problems and fixes.


### The application

The v3 desktop app is one window with a workflow-ordered rail. These pages describe what each row
of that rail does; see [Desktop Application]({{ site.baseurl }}/wiki/desktop-app/) for how the app, the container and the
server fit together.

- **[Overview]({{ site.baseurl }}/wiki/overview/)** - Welcome, project opening and switching, then the project at a glance
- **[Pre-processing]({{ site.baseurl }}/wiki/pre-processing/)** - Structural MRI preparation and head-model generation
  - **[FastSurfer / FreeSurfer]({{ site.baseurl }}/wiki/fastsurfer/)** - Segmentation, reconstruction and GPU setup
  - **[QSIPrep / QSIRecon]({{ site.baseurl }}/wiki/diffusion-processing/)** - Diffusion processing and conductivity tensors
- **[Simulator]({{ site.baseurl }}/wiki/simulator/)** - One row per simulation job, with free-hand electrode placement on the subject's own scalp
- **[Flex Search]({{ site.baseurl }}/wiki/flex-search/)** - The Optimizer's *Flex* method: differential-evolution electrode optimization
- **[Ex Search]({{ site.baseurl }}/wiki/ex-search/)** - The Optimizer's *Ex* method: exhaustive search over a leadfield matrix
- **[Analyzer]({{ site.baseurl }}/wiki/analyzer/)** - Field analysis in mesh and voxel space, one target per job row
- **[Notebooks]({{ site.baseurl }}/wiki/notebooks/)** - Jupyter on the container's SimNIBS Python, inside the app
- **[Results]({{ site.baseurl }}/wiki/results/)** - Every output a subject has, with reports rendered in place
- **[Viewer]({{ site.baseurl }}/wiki/visualizers/)** - Opens your project's scenes in the separate TetraVox desktop app, which TI-Toolbox installs and manages
- **[Jobs]({{ site.baseurl }}/wiki/jobs/)** - Every run: state, logs, artifacts, cancel and rerun
- **[Scripting]({{ site.baseurl }}/wiki/scripting/)** - CLI commands, JSON config entry points, and the Python scripting API
- **[Example Data]({{ site.baseurl }}/wiki/example-data/)** - Public example heads (raw scans and ready-made head models) to try every page
- **[AI Assistant]({{ site.baseurl }}/wiki/ai-assistant/)** - Plugin that teaches Claude Code, Codex, Cursor and other MCP clients how to use TI-Toolbox
- **[Telemetry & Privacy]({{ site.baseurl }}/wiki/telemetry/)** - What opt-in usage telemetry sends, and how to control it

### Embedded Tools
- **[Reports]({{ site.baseurl }}/wiki/reports/)** - The HTML report each head model, DTI step, simulation and search writes
- **[Logging]({{ site.baseurl }}/wiki/logging/)** - Comprehensive logging system documentation
- **[Brain Atlases]({{ site.baseurl }}/wiki/atlases/)** - The MNI-space atlases shipped with TI-Toolbox, the subject-space parcellations built during pre-processing, and atlas resampling
- **[Montage Visualizer]({{ site.baseurl }}/wiki/montage_visualizer/)** - Electrode montage visualization on head
- **[Electrode Mapping]({{ site.baseurl }}/wiki/electrode-mapping/)** - Optimal electrode position mapping to EEG nets

### Optional Tools
- **[Optional Tools]({{ site.baseurl }}/wiki/extension/)** - The panels you switch on in **Settings ▸ Extensions**
- **[3D Visual Exporter]({{ site.baseurl }}/wiki/blender/)** - PLY/GLB/Blender exports of regions, vectors and montages
- **[Free Electrode Placement]({{ site.baseurl }}/wiki/electrode-placement/)** - Clicking electrodes onto the scalp, now part of the Simulator
- **[Nilearn Visuals]({{ site.baseurl }}/wiki/nilearn-visuals/)** - Publication-ready brain visualizations
- **[EEG Caps]({{ site.baseurl }}/wiki/eeg-caps/)** - Apply MNI electrode caps to an existing head model and inspect nets on the scalp
- **[Cluster-Based Permutation Testing]({{ site.baseurl }}/wiki/cluster-permutation-testing/)** - Non-parametric statistical analysis (the *Permutation Analysis* extension)
- **[Quick Notes]({{ site.baseurl }}/wiki/quick-notes/)** - An autosaving project notepad with optional timestamps
- **[NIfTI Group Averaging]({{ site.baseurl }}/wiki/nifti-group-averaging/)** - Group analysis and comparison tools
- **[Tissue Analyzer]({{ site.baseurl }}/wiki/tissue-analyzer/)** - Volume and thickness assessment for CSF, bone, and skin (part of pre-processing)

### Development & Testing
- **[Development & Testing]({{ site.baseurl }}/wiki/development/)** - Current test strategy, commands, fixtures, and verification limits
- **[Python Environment]({{ site.baseurl }}/wiki/python_env/)** - Managing the SimNIBS Python environment and dependencies
- **[Desktop Application]({{ site.baseurl }}/wiki/desktop-app/)** - Electron app, container lifecycle and the server it talks to
- **[Agent Plugin Internals]({{ site.baseurl }}/wiki/agent-plugin/)** - Skills, MCP server architecture, and tests behind the AI assistant integration
- **[API Reference]({{ site.baseurl }}/api/)** - Complete Python API documentation (auto-generated from docstrings)

### Legacy versions

Still using v2? See the brief [legacy-version notice]({{ site.baseurl }}/wiki/legacy-v2/)
for version-specific documentation and migration information.
