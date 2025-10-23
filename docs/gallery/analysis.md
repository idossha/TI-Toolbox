---
layout: gallery
title: Analysis Gallery
permalink: /gallery/analysis/
---

<link rel="stylesheet" href="{{ '/assets/css/lightbox.css' | relative_url }}">

Comprehensive analysis and visualization of TI simulation results, field distributions, and statistical metrics.

<div class="gallery-section">
  <h3>Field Analysis & Visualization in mesh space (Gmsh Integration)</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analyzer/TI_max.png" alt="Maximum TI Field" onclick="openLightbox(this)" />
      <p>TInorm field distribution showing intensity map in the cortical ROI (Left Insula).</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analyzer/TI_normal.png" alt="Normalized TI Field" onclick="openLightbox(this)" />
      <p>Normal component of the TInorm field distribution showing intensity map in the cortical ROI (Left Insula)</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analyzer/TI_max_all.png" alt="All TI Field Components" onclick="openLightbox(this)" />
      <p>TInorm field distribution showing intensity map across the entire brain.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Field Analysis & Visualization in voxel space (Freesurfer Integration)</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analyzer/voxel_montage_1.png" alt="TInorm field in ROI (Right Hippocampus)" onclick="openLightbox(this)" />
      <p>Montage A: TInorm field distribution showing intensity map in the sub-cortical ROI (Right Hippocampus).</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analyzer/voxel_montage_2.png" alt="TInormal field in ROI (Right Hippocampus)" onclick="openLightbox(this)" />
      <p>Montage B: TInorm field distribution showing intensity map in the sub-cortical ROI (Right Hippocampus).</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analyzer/TI_max_all.png" alt="TInorm field in cortex" onclick="openLightbox(this)" />
      <p>TInorm field distribution showing intensity map across the entire brain.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Statistical Analysis & Metrics</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analyzer/analysis_plot.png" alt="Analysis Plots" onclick="openLightbox(this)" />
      <p>field strength distribution in the ROI.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analyzer/lh.insula_whole_head_roi_histogram.png" alt="ROI Histogram Analysis" onclick="openLightbox(this)" />
      <p>Histrogram showing focality, intensity cutoffs, and relationship to ROI</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/ex-search/ex-search_analysis_values.png" alt="Ex-Search Quantitative Values" onclick="openLightbox(this)" />
      <p>Quantitative values corresponding to histrogram plot.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Comparative Analysis</h3>
  <div class="gallery-grid">
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
  margin: 3rem 0;
  padding: 1.5rem;
  background-color: #f8f9fa;
  border-radius: 8px;
}

.gallery-section h3 {
  color: #2c3e50;
  margin-bottom: 1.5rem;
  font-size: 1.4rem;
  font-weight: 600;
  border-bottom: 2px solid #3498db;
  padding-bottom: 0.5rem;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
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
  cursor: pointer !important;
  loading: lazy;
}

.gallery-item p {
  margin: 0;
  font-size: 0.9rem;
  color: #666;
  line-height: 1.4;
  text-align: left;
}

@media (max-width: 768px) {
  .gallery-grid {
    grid-template-columns: 1fr;
    gap: 1rem;
  }
  
  .gallery-section {
    margin: 1rem 0;
    padding: 1rem;
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
</style> 
