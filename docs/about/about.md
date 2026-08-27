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

Everything ships inside Docker containers, with a desktop launcher and a GUI, so a full research stack runs identically on macOS, Linux, and Windows without manual environment setup.

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

    <!-- Larissa Albantakis Profile -->
    <div class="contributor-card">
      <div class="contributor-avatar">
        <img src="{{ site.baseurl }}/assets/imgs/about/larissa_profile.jpg" alt="Larissa Albantakis" 
             onerror="this.src='{{ site.baseurl }}/assets/imgs/default-avatar.png'">
      </div>
      <div class="contributor-info">
        <h3>Larissa Albantakis</h3>
        <p class="contributor-role">Core Contributor</p>
        <p class="contributor-description">
          Larissa Albantakis, PhD is a computational neuroscientist and Assistant Professor of Computational Psychiatry.
        </p>
        <ul class="contributor-list">
          <li>Multipolar TI field math: the K&ge;2 modulation envelope, Fibonacci-sphere direction sampling, and the magnitude-AM measure (2.5)</li>
          <li>Corrected peak high-frequency field calculation (2.5)</li>
          <li>Multipolar exhaustive search and the generalized electrode-bucket loader (2.5)</li>
          <li>Symmetric bucket search (2.5)</li>
          <li>Ex/mex-search electrode-map visuals: participation heatmap and montage strength/focality maps (2.5)</li>
          <li>Subject-space ROIs from local MNI masks, incl. functional thalamus ROIs (2.5)</li>
          <li>Subject ROI masks in the analyzer and the subcortical picker (2.5)</li>
          <li>NIfTI viewer: ROI overlay selector, colormap and percentile defaults (2.4)</li>
        </ul>
        <div class="contributor-links">
          <a href="mailto:albantakis@wisc.edu" target="_blank">📧 Email</a>
          <a href="https://github.com/Albantakis" target="_blank">🔗 GitHub</a>
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
          Undergraduate Research Assistant and software developer focused on computational modeling, visualization, and analysis of electric field distributions.
        </p>
        <ul class="contributor-list">
          <li>Main author of the analyzer: mesh and voxel ROI extraction, spherical, cortical and whole-head modes, and its GUI tab (2.0)</li>
          <li>Analyzer visualizations: scatter plots and cortex/whole-brain overlays (2.0)</li>
          <li>Group analyzer CLI (2.1)</li>
          <li>Central logging utility used across every pipeline (2.0)</li>
          <li>BIDS project layout and automatic <code>dataset_description.json</code> initialization (2.1)</li>
          <li>Debug mode for the simulator, analyzer, pre-processing, and both searches (2.1)</li>
          <li>Combined pre-processing report and CSF analysis (2.1)</li>
          <li>Atlas resampling optimization and the GUI console deadlock fix (2.0)</li>
        </ul>
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
- [**SimNIBS**:](https://simnibs.github.io/simnibs/build/html/index.html) A simulation environment for transcranial brain stimulation, enabling electric field modeling.
- [**FreeSurfer**:](https://surfer.nmr.mgh.harvard.edu/) A software suite for the analysis and visualization of structural and functional neuroimaging data.
- [**Gmsh**:](http://gmsh.info/) A three-dimensional finite element mesh generator with a built-in CAD engine and post-processor.  
- [**FSL**:](https://fsl.fmrib.ox.ac.uk/fsl/) A comprehensive library of tools for analysis of functional and structural brain imaging data.
- [**dcm2niix**](https://github.com/rordenlab/dcm2niix): A tool for converting DICOM images to NIfTI format
- [**BIDS**](https://bids.neuroimaging.io/): A standardized way to organize and describe neuroimaging data.
- [**QSIPrep**](https://qsiprep.readthedocs.io/) / [**QSIRecon**](https://qsirecon.readthedocs.io/): Preprocessing and reconstruction pipelines for diffusion MRI, used to derive anisotropic conductivity tensors.
- [**Blender**](https://www.blender.org/): An open-source 3D creation suite, used for rendering head models, electrodes, and field distributions.
- **Python ecosystem**: [NumPy](https://numpy.org/), [SciPy](https://scipy.org/), [nibabel](https://nipy.org/nibabel/), [matplotlib](https://matplotlib.org/), [pandas](https://pandas.pydata.org/), [nilearn](https://nilearn.github.io/), [MNE-Python](https://mne.tools/), [PyQt5](https://www.riverbankcomputing.com/software/pyqt/), and [Jupyter](https://jupyter.org/).



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

.contributor-list {
  color: #495057;
  line-height: 1.5;
  font-size: 0.95rem;
  text-align: left;
  margin: 0.5rem 0 1rem;
  padding-left: 1.1rem;
}

.contributor-list li {
  margin-bottom: 0.35rem;
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
