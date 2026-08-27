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
      <p>All electrode combinations to be searched through \(n^4\) combinations.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_distribution.png" alt="Ex-Search Distribution" onclick="openLightbox(this)" />
      <p>Distribution of TImax, TImean and focality over 16,807 evaluations (2,401 montages × 7 current splits) of a sub-ernie run (v2.4.0).</p>
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
      <p>ROI intensity versus focality for the same run, coloured by Composite_Index; the Pareto front forms along the upper-right edge.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>EEG Cap Result Maps</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/electrode_score_heatmap.png" alt="Electrode contribution heatmap" onclick="openLightbox(this)" />
      <p><code>electrode_score_heatmap.png</code>: electrode participation across the top-50 montages &mdash; colour is the summed Composite Index, marker size the frequency with which the electrode appears.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/montage_strength_map.png" alt="Montage strength map" onclick="openLightbox(this)" />
      <p><code>montage_strength_map.png</code>: the top-150 montages drawn as arcs on the EEG cap, coloured by <code>TImean_ROI</code>, with the best montage highlighted.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Symmetric (Hemisphere-Mirrored) Search</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/symmetric_montage_strength_map.png" alt="Symmetric ex-search montage strength map" onclick="openLightbox(this)" />
      <p>Montage strength map for a symmetric run, where every electrode is paired with its contralateral mirror &mdash; the arcs stay bilaterally balanced by construction.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/ex-search/symmetric_scatter.png" alt="Symmetric ex-search intensity vs focality" onclick="openLightbox(this)" />
      <p>Intensity versus focality for the same symmetric run; the mirrored constraint shrinks the candidate set and shifts the Pareto front relative to the unconstrained search.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Multipolar Exhaustive Search (mex-search)</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/mti/mex_electrode_score_heatmap.png" alt="mex-search electrode contribution heatmap" onclick="openLightbox(this)" />
      <p>Electrode contributions across the best 4-channel mTI montages, scored the same way as the 2-channel heatmap.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/mti/mex_montage_strength_map.png" alt="mex-search montage strength map" onclick="openLightbox(this)" />
      <p>Top mex-search montages drawn on the cap; each montage contributes four arcs, one per channel.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/mti/mex_scatter_large.png" alt="mex-search intensity vs focality, 576 candidates" onclick="openLightbox(this)" />
      <p>Intensity versus focality over 576 mex-search candidates &mdash; the largest of the example runs.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/mti/mex_scatter_symmetric.png" alt="Symmetric mex-search intensity vs focality" onclick="openLightbox(this)" />
      <p>The same plot for a symmetric mex-search, with all four channels mirrored across the midline.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/mti/mex_scatter_independent.png" alt="mex-search, independent channels" onclick="openLightbox(this)" />
      <p>A 16-candidate run with four independent carriers, one per channel.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/mti/mex_scatter_twocarrier.png" alt="mex-search, two carriers" onclick="openLightbox(this)" />
      <p>The same 16 candidates wired as two carriers shared across four channels, for comparison against the independent wiring.</p>
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