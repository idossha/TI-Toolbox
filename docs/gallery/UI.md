---
layout: gallery
title: UI Gallery
permalink: /gallery/UI/
---

<link rel="stylesheet" href="{{ '/assets/css/lightbox.css' | relative_url }}">

<div class="gallery-section">
  <h3>TI-Toolbox User Interface</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/UI/pre-process.png" alt="Pre-Processing UI" onclick="openLightbox(this)" />
      <p>Pre-Processing interface for DICOM to NIfTI conversion and FreeSurfer segmentation.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/UI/flex.png" alt="Flex-Search UI" onclick="openLightbox(this)" />
      <p>Flex-Search interface for evolutionary electrode optimization.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/UI/ex.png" alt="Ex-Search UI" onclick="openLightbox(this)" />
      <p>Ex-Search interface for exhaustive electrode combination search.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/UI/sim.png" alt="Simulations UI" onclick="openLightbox(this)" />
      <p>Simulations interface for temporal interference field analysis.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/UI/ana.png" alt="Analysis UI" onclick="openLightbox(this)" />
      <p>Analysis interface for comprehensive results visualization.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/UI/nifti.png" alt="NIfTI UI" onclick="openLightbox(this)" />
      <p>NIfTI file processing and visualization interface.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/UI/monitor.png" alt="System Monitor UI" onclick="openLightbox(this)" />
      <p>System monitoring interface for tracking toolbox processes.</p>
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