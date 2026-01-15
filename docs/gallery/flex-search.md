---
layout: gallery
title: Flex-Search Gallery
permalink: /gallery/flex-search/
---

<link rel="stylesheet" href="{{ '/assets/css/lightbox.css' | relative_url }}">

<div class="gallery-section">
  <h3>Evolutionary Electrode Optimization</h3>
  <div class="gallery-grid">
    <div class="gallery-item">m
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_flex-search.png" alt="Flex-Search Optimization" onclick="openLightbox(this)" />
      <p>Evolutionary optimization showing flexible electrode placement unbound by EEG net discretization.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_mapping.png" alt="Electrode Mapping" onclick="openLightbox(this)" />
      <p>Extension to the flex-search mapping optimized electrodes to nearest available EEG electrodes.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_max_TI_field.png" alt="Maximum TI Field" onclick="openLightbox(this)" />
      <p>TImax visualization across the brain surface.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_max_TI_ROI.png" alt="Maximum TI ROI" onclick="openLightbox(this)" />
      <p>Maximum temporal interference field focused on the region of interest.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_Normal_field.png" alt="Normal Field Component" onclick="openLightbox(this)" />
      <p>Normal component of the electric field showing perpendicular field distribution.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_normal_ROI.png" alt="Normal ROI Component" onclick="openLightbox(this)" />
      <p>Normal component field focused on the target region of interest.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_tangent_field.png" alt="Tangent Field Component" onclick="openLightbox(this)" />
      <p>Tangent component of the electric field showing parallel field distribution.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_tangent_ROI.png" alt="Tangent ROI Component" onclick="openLightbox(this)" />
      <p>Tangent component field focused on the target region of interest.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/focality_thresholds.png" alt="Focality Thresholds" onclick="openLightbox(this)" />
      <p>Analysis of focality thresholds for different field intensity levels.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/mapping_distance.png" alt="Mapping Distance Analysis" onclick="openLightbox(this)" />
      <p>Distance analysis for mapping optimized electrodes to available EEG positions.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/multi-start.png" alt="Multi-Start Optimization" onclick="openLightbox(this)" />
      <p>Multi-start optimization strategy to avoid local minima in electrode placement.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/valid_skin.png" alt="Valid Skin Region" onclick="openLightbox(this)" />
      <p>Visualization of valid skin regions for electrode placement with HD-EEG electrode positions.</p>
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
  grid-template-columns: repeat(3, 1fr);
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
    grid-template-columns: repeat(2, 1fr);
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