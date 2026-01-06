---
layout: gallery
title: Ex-Search Gallery
permalink: /gallery/ex-search/
---

<link rel="stylesheet" href="{{ '/assets/css/lightbox.css' | relative_url }}">

<div class="gallery-section">
  <h3>Exhaustive Search Results</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_ex-search_selection.png" alt="Ex-Search Selection" onclick="openLightbox(this)" />
      <p>Electrode selection interface required for exhaustive search optimization.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_ex-search_combos.png" alt="Ex-Search Combinations" onclick="openLightbox(this)" />
      <p>All electrode combinations to be searched through n^4 combinations.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_distribution.png" alt="Ex-Search Distribution" onclick="openLightbox(this)" />
      <p>Distribution analysis of exhaustive search optimization results.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_EEG10-20_Okamoto_2004_net.png" alt="EEG 10-20 Network" onclick="openLightbox(this)" />
      <p>EEG electrode placement using the 10-20 Okamoto 2004 standard.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_GSN256_net.png" alt="GSN 256 Network" onclick="openLightbox(this)" />
      <p>High-density GSN 256 electrode network configuration.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_field_msh.png" alt="Field Mesh Visualization" onclick="openLightbox(this)" />
      <p>Electric field distribution visualization on tetrahedral mesh.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/intensity_vs_focality_scatter.png" alt="Intensity vs Focality" onclick="openLightbox(this)" />
      <p>Scatter plot analysis of field intensity versus focality metrics.</p>
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