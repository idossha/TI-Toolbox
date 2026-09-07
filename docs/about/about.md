---
layout: about
title: About
permalink: /about/
---

The Temporal Interference Toolbox (TI-Toolbox) started as a side project in early 2024 and has since matured into an end-to-end platform for temporal interference (TI) stimulation research. It lets both newcomers and experienced modelers go from raw imaging data to simulated, optimized, and analyzed TI fields, using either standardized head models or fully personalized ones built from a participant's own MRI.

### What it does

The toolbox covers the full modeling pipeline in one place:

- **Preprocessing** — DICOM/NIfTI ingestion, cortical reconstruction, head-model generation, and optional diffusion processing for anisotropic conductivity.
- **Simulation** — finite-element modeling of two-pair TI and multi-pair (mTI) montages, producing volumetric and surface field maps.
- **Optimization** — evolutionary (flex) and exhaustive electrode searches that target cortical, subcortical, spherical, or custom regions of interest.
- **Analysis and statistics** — ROI extraction, focality and safety metrics, group-level comparisons, and permutation testing.
- **Reporting and visualization** — HTML reports, 3D renders, and fsaverage/MNI projections for cross-subject comparison.
- **Pipelines and notebooks** — wire the steps into a graph and run it as one job, or drive the same API from a Jupyter notebook running on the container's own Python.

Everything ships inside one Docker image, driven by a desktop application, so a full research stack
runs identically on macOS, Linux, and Windows without manual environment setup.

### Requirements & what's inside

The only thing you install is the desktop app and **Docker Desktop** (or a Docker Engine). Everything
scientific lives in one image, `idossha/ti-toolbox:<version>`, which the app pulls and runs for you.
Step-by-step instructions per platform are in the
[Installation guide]({{ site.baseurl }}/installation/) and
[Dependencies]({{ site.baseurl }}/installation/dependencies/).

**On your machine**

| | |
|---|---|
| **Docker** | Docker Desktop (macOS, Windows) or Docker Engine (Linux). The app talks to it over its API — you never type a `docker` command. |
| **The app** | `.dmg` (macOS, Apple Silicon and Intel), `.exe` (Windows x64), `.AppImage` or `.deb` (Linux x64) |
| **Graphics** | A GPU/driver combination with **WebGL2**, for the viewer and the 3-D panes. If it is missing, the app says so explicitly and every choice a pane offers is still available from the form beside it. |
| **Disk** | ≈ 2.3 GB to download, ≈ 9 GB unpacked on disk, plus your project |
| **A GPU** | **Not required.** Everything ships CPU-only; the sole GPU switch anywhere is an optional QSIRecon setting, off by default. |
| **X11** | **Not required, and not used.** No XQuartz, no VcXsrv, no `DISPLAY`. |

**Inside the image** (≈ 2.3 GB to download; ≈ 9 GB unpacked on disk, which is the figure
`docker images` prints)

| | |
|---|---|
| **SimNIBS** | 4.6, with the toolbox's patches applied at build time |
| **Python** | 3.11 — SimNIBS's own environment, which is also the Notebooks kernel |
| **FastSurfer** | 2.5.4, CPU-only, `--seg_only`, with its checkpoints pre-downloaded |
| **Tetravox Embed** | The viewer, served by the container and drawn on your machine's GPU |
| **`tit` + `tit.server`** | The scientific package and the API the app talks to |
| **Not included** | Gmsh, Qt/PyQt5, any X server, FreeSurfer `recon-all`, the MATLAB Runtime |

The image is **amd64**; on Apple Silicon it runs under emulation, which is correct but slower.
The server listens on `127.0.0.1` only, and the app authenticates to it with a per-container token.

### Philosophy

TI-Toolbox is developed openly on [GitHub](https://github.com/idossha/TI-toolbox) and follows the [BIDS](https://bids.neuroimaging.io/) standard for data organization, so outputs are reproducible and interoperable with the wider neuroimaging ecosystem. We aim for defaults that are safe and sensible for common studies while keeping every parameter accessible to power users. Bug reports, feature requests, and contributions are welcome through the issue tracker.

### Contributors

<div class="contributors-section">
  <div class="contributor-grid">
    
    <!-- Ido Haber Profile -->
    <div class="contributor-card">
      <div class="contributor-avatar">
        <img src="{{ site.baseurl }}/assets/imgs/about/ido_profile.png" alt="Ido Haber" 
             onerror="this.src='{{ site.baseurl }}/assets/imgs/default-avatar.png'">
      </div>
      <div class="contributor-info">
        <h3>Ido Haber</h3>
        <p class="contributor-role">Lead Developer & Project Founder</p>
        <p class="contributor-description">
          PhD Research Assistant and software developer specializing in computational neurostimulation. 
          Developed the idea and architecture for the TI-Toolbox.<br>
        </p>
        <div class="contributor-links">
          <a href="mailto:ihaber@wisc.edu" target="_blank">📧 Email</a>
          <a href="https://github.com/idossha" target="_blank">🔗 GitHub</a>
        </div>
      </div>
    </div>

  </div>
</div>

### Past Contributors

<div class="contributors-section">
  <div class="contributor-grid">

    <!-- Aksel Profile -->
    <div class="contributor-card">
      <div class="contributor-avatar">
        <img src="{{ site.baseurl }}/assets/imgs/about/aksel_profile.png" alt="Aksel" 
             onerror="this.src='{{ site.baseurl }}/assets/imgs/default-avatar.png'">
      </div>
      <div class="contributor-info">
        <h3>Aksel Jackson</h3>
        <p class="contributor-role">Core Contributor</p>
        <p class="contributor-description">
          Undergraduate Research Assistant and software developer focused on computational modeling, visualization, and analysis of electric field distribution. <br>
        </p>
        <div class="contributor-links">
          <a href="mailto:awjackson2@wisc.edu" target="_blank">📧 Email</a>
          <a href="https://github.com/awjackson2" target="_blank">🔗 GitHub</a>
        </div>
      </div>
    </div>

  </div>
</div>

## Acknowledgments

TI-Toolbox stands on the shoulders of many open-source projects. We extend our gratitude to the developers and contributors of the tools it integrates, and we ask that users cite the underlying tools (in particular SimNIBS and FreeSurfer) alongside TI-Toolbox in publications.

- [**Docker**](https://www.docker.com): A containerization platform for developing, shipping, and running distributed applications.
- [**Electron**](https://electronjs.org): A framework for building cross-platform desktop applications using web technologies.
- [**FastSurfer**](https://github.com/Deep-MI/FastSurfer): A fast, deep-learning based neuroimaging pipeline for whole-brain segmentation, used in place of FreeSurfer `recon-all`.
- [**Tetravox**](https://github.com/idossha/tetravox): The WebGL2 viewer that draws meshes and volumes inside the application window.
- [**SimNIBS**:](https://simnibs.github.io/simnibs/build/html/index.html) A simulation environment for transcranial brain stimulation, enabling electric field modeling.
- [**FreeSurfer**:](https://surfer.nmr.mgh.harvard.edu/) A software suite for the analysis and visualization of structural and functional neuroimaging data.
- [**Gmsh**:](http://gmsh.info/) A three-dimensional finite element mesh generator. The `.msh` format TI-Toolbox writes is Gmsh's; the program itself is no longer bundled (v3 views results with Tetravox).
- [**FSL**:](https://fsl.fmrib.ox.ac.uk/fsl/) A comprehensive library of tools for analysis of functional and structural brain imaging data.
- [**dcm2niix**](https://github.com/rordenlab/dcm2niix): A tool for converting DICOM images to NIfTI format
- [**BIDS**](https://bids.neuroimaging.io/): A standardized way to organize and describe neuroimaging data.
- [**QSIPrep**](https://qsiprep.readthedocs.io/) / [**QSIRecon**](https://qsirecon.readthedocs.io/): Preprocessing and reconstruction pipelines for diffusion MRI, used to derive anisotropic conductivity tensors.
- [**Blender**](https://www.blender.org/): An open-source 3D creation suite, used for rendering head models, electrodes, and field distributions.
- **Python ecosystem**: [NumPy](https://numpy.org/), [SciPy](https://scipy.org/), [nibabel](https://nipy.org/nibabel/), [matplotlib](https://matplotlib.org/), [pandas](https://pandas.pydata.org/), [nilearn](https://nilearn.github.io/), [MNE-Python](https://mne.tools/), and [Jupyter](https://jupyter.org/).



<style>
.contributors-section {
  margin: 1rem 0 2rem;
}

.contributor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 420px));
  gap: 1.5rem;
  margin-top: 1rem;
}

.contributor-card {
  background: #f8f9fa;
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.contributor-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.contributor-avatar {
  width: 80px;
  height: 80px;
  margin: 0 auto 1rem;
  border-radius: 50%;
  overflow: hidden;
  background-color: #e9ecef;
}

.contributor-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.contributor-info {
  text-align: center;
}

.contributor-info h3 {
  margin: 0 0 0.25rem;
  font-size: 1.25rem;
}

.contributor-role {
  color: #6c757d;
  font-weight: 600;
  margin: 0 0 0.75rem;
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.contributor-description {
  color: #495057;
  line-height: 1.5;
  margin-bottom: 1rem;
  font-size: 0.95rem;
  text-align: Left;
}

.contributor-links {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.contributor-links a {
  background: grey;
  color: white;
  padding: 0.4rem 0.8rem;
  border-radius: 20px;
  text-decoration: none;
  font-size: 0.85rem;
  transition: background-color 0.2s ease;
}

.contributor-links a:hover {
  background: #0056b3;
}

@media (max-width: 768px) {
  .contributor-grid {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }
  
  .contributor-card {
    padding: 1rem;
  }
  
  .contributor-avatar {
    width: 60px;
    height: 60px;
  }
}
</style> 
