---
layout: gallery
title: Flex-Search Gallery
permalink: /gallery/flex-search/
---

<link rel="stylesheet" href="{{ '/assets/css/lightbox.css' | relative_url }}">

<div class="gallery-section">
  <h3>Evolutionary Electrode Optimization</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
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

<div class="gallery-section">
  <h3>Optimization Goals & the Focality Study</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/focality-study_summary.png" alt="Optimization goal comparison" onclick="openLightbox(this)" />
      <p>Goal comparison across a 75-run mini-study: separation (AUC) plotted against the on-target field it was achieved on &mdash; a high ratio score on almost no field is the failure mode to watch for.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/focality-study_roc.png" alt="Group ROC curves per deep target" onclick="openLightbox(this)" />
      <p>Group ROC curves for each deep target across all five optimization goals.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/focality-study_dist.png" alt="Pooled TI envelope field distributions" onclick="openLightbox(this)" />
      <p>Pooled TI envelope field distributions by target and goal, showing where each goal puts the field it produces.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_current-ratio.png" alt="Current ratio effect on the TI envelope" onclick="openLightbox(this)" />
      <p>Effect of the inter-channel current split on the TI envelope: the split both scales the envelope (the ceiling follows the weaker channel) and steers it toward that channel.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Scalp Constraints & Net Density</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/flex-search/valid_skin_region_margin_landmark_guarded.png" alt="Valid skin region margin comparison" onclick="openLightbox(this)" />
      <p>Valid-skin margins with <code>avoid_landmark_regions=True</code>: fiducial-derived ear and orbital exclusion zones stay invalid, using scalp landmarks (<code>Nz</code>, <code>LPA</code>, <code>RPA</code>) only.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/other/net_density_impact.png" alt="EEG net density impact on TImax" onclick="openLightbox(this)" />
      <p>Effect of EEG net density on achievable TImax after mapping optimized positions onto a discrete net.</p>
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