---
layout: gallery
title: UI Gallery
permalink: /gallery/UI/
---

<link rel="stylesheet" href="{{ '/assets/css/lightbox.css' | relative_url }}">

<div class="gallery-section">
  <h3>The TI-Toolbox desktop application (v3)</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/overview.png" alt="The Overview page: what every subject has, and what it is ready for." onclick="openLightbox(this)" />
      <p>The Overview page: what every subject has, and what it is ready for.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/preprocess.png" alt="Pre-processing: pick subjects, tick stages, and the plan says what will run for each one." onclick="openLightbox(this)" />
      <p>Pre-processing: pick subjects, tick stages, and the plan says what will run for each one.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/simulator.png" alt="Simulator: one row per job, with the montage drawn on the selected subject's head." onclick="openLightbox(this)" />
      <p>Simulator: one row per job, with the montage drawn on the selected subject's head.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/simulator-placement.png" alt="Free-hand placement: select a row, click the scalp, and the row takes that point in subject millimetres." onclick="openLightbox(this)" />
      <p>Free-hand placement: select a row, click the scalp, and the row takes that point in subject millimetres.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/optimizer.png" alt="Optimizer: Flex and Ex are two methods in a job row, with the atlas you are targeting in the pane." onclick="openLightbox(this)" />
      <p>Optimizer: Flex and Ex are two methods in a job row, with the atlas you are targeting in the pane.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/analyzer.png" alt="Analyzer: one row per analysis, each row owning its own target." onclick="openLightbox(this)" />
      <p>Analyzer: one row per analysis, each row owning its own target.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/pipeline.png" alt="Pipeline: wire the steps into a graph and run the whole thing as one job group." onclick="openLightbox(this)" />
      <p>Pipeline: wire the steps into a graph and run the whole thing as one job group.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/notebooks.png" alt="Notebooks: Jupyter on the container's SimNIBS Python, with the project already resolved." onclick="openLightbox(this)" />
      <p>Notebooks: Jupyter on the container's SimNIBS Python, with the project already resolved.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/results.png" alt="Results: every output a subject has, with simulation reports rendered in place." onclick="openLightbox(this)" />
      <p>Results: every output a subject has, with simulation reports rendered in place.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/viewer.png" alt="The Viewer: a TI field open in Tetravox, inside the application window." onclick="openLightbox(this)" />
      <p>The Viewer: a TI field open in Tetravox, inside the application window.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/jobs.png" alt="Jobs: every run recorded — state, stage, elapsed time, logs and artifacts." onclick="openLightbox(this)" />
      <p>Jobs: every run recorded — state, stage, elapsed time, logs and artifacts.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/settings.png" alt="Settings: optional tools, the project, telemetry, appearance and the viewer engine." onclick="openLightbox(this)" />
      <p>Settings: optional tools, the project, telemetry, appearance and the viewer engine.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/panel-visual-exporter.png" alt="The 3D visual exporter panel: cortical regions, field vectors, montages and sub-cortical structures." onclick="openLightbox(this)" />
      <p>The 3D visual exporter panel: cortical regions, field vectors, montages and sub-cortical structures.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/panel-cluster-permutation.png" alt="The cluster permutation panel: non-parametric group-level statistics." onclick="openLightbox(this)" />
      <p>The cluster permutation panel: non-parametric group-level statistics.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/panel-source.png" alt="The Source panel: EEG forward modelling and fsaverage projection." onclick="openLightbox(this)" />
      <p>The Source panel: EEG forward modelling and fsaverage projection.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/v3/help.png" alt="Help: the documentation, the citation, and the keyboard map." onclick="openLightbox(this)" />
      <p>Help: the documentation, the citation, and the keyboard map.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>The PyQt interface (v2, historical)</h3>
  <p>These are the tabs of the PyQt5 GUI, removed in v3.0.0 and kept here for reference.</p>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_pre-process.png" alt="Pre-Processing UI" onclick="openLightbox(this)" />
      <p>Pre-Processing interface for DICOM to NIfTI conversion and FreeSurfer segmentation.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_flex.png" alt="Flex-Search UI" onclick="openLightbox(this)" />
      <p>Flex-Search interface for evolutionary electrode optimization.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_ex.png" alt="Ex-Search UI" onclick="openLightbox(this)" />
      <p>Ex-Search interface for exhaustive electrode combination search.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_sim.png" alt="Simulations UI" onclick="openLightbox(this)" />
      <p>Simulations interface for temporal interference field analysis.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_ana.png" alt="Analysis UI" onclick="openLightbox(this)" />
      <p>Analysis interface for comprehensive results visualization.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_nifti.png" alt="NIfTI UI" onclick="openLightbox(this)" />
      <p>NIfTI file processing and visualization interface.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_monitor.png" alt="System Monitor UI" onclick="openLightbox(this)" />
      <p>System monitoring interface for tracking toolbox processes.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_cbpt.png" alt="CBPT UI" onclick="openLightbox(this)" />
      <p>Permutation Analysis (cluster-based permutation testing) interface for group-level statistics.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_extension.png" alt="Extension UI" onclick="openLightbox(this)" />
      <p>Extensions window for launching extensions or adding them as tabs of the main window.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_nifti_group_avg.png" alt="NIfTI Group Average UI" onclick="openLightbox(this)" />
      <p>NIfTI group averaging interface for multi-subject data analysis.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/UI/UI_nilearn_visuals.png" alt="NiLearn Visuals UI" onclick="openLightbox(this)" />
      <p>NiLearn visualization interface for advanced brain imaging plots and graphics.</p>
    </div>
  </div>
</div>

<!-- Lightbox Modal -->
<div id="lightbox" class="lightbox" onclick="closeLightbox()">
  <span class="close" onclick="closeLightbox()">&times;</span>
  <div class="lightbox-content" onclick="event.stopPropagation()">
    <img id="lightbox-img" src="" alt="" />
    <div class="lightbox-nav">
      <button class="nav-btn prev" onclick="changeImage(-1)">&#10094;</button>
      <button class="nav-btn next" onclick="changeImage(1)">&#10095;</button>
    </div>
    <div class="lightbox-caption" id="lightbox-caption"></div>
  </div>
</div>

<script src="{{ '/assets/js/lightbox.js' | relative_url }}"></script>

<style>
.gallery-section {
  margin: 2rem 0;
  padding: 1rem;
  background-color: #f8f9fa;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
  margin-top: 1rem;
}

.gallery-item {
  background: white;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  text-align: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.gallery-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

/* Override wiki.css image styles with more specific selectors and !important */
.wiki-content .gallery-item img,
.gallery-item img {
  width: 100% !important;
  max-width: 500px !important;
  max-height: 400px !important;
  height: auto !important;
  object-fit: contain !important;
  border-radius: 4px !important;
  margin-bottom: 0.5rem !important;
  margin-left: auto !important;
  margin-right: auto !important;
  margin-top: 0 !important;
  display: block !important;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
  loading: lazy;
}

.gallery-item p {
  margin: 0;
  font-size: 0.9rem;
  color: #666;
  line-height: 1.4;
}

@media (max-width: 768px) {
  .gallery-grid {
    grid-template-columns: 1fr;
    gap: 1rem;
  }
  
  .gallery-section {
    margin: 1rem 0;
    padding: 0.5rem;
  }
  
  .wiki-content .gallery-item img,
  .gallery-item img {
    max-width: 100% !important;
    max-height: 300px !important;
  }
}

@media (max-width: 480px) {
  .wiki-content .gallery-item img,
  .gallery-item img {
    max-height: 250px !important;
  }
}
</style> 