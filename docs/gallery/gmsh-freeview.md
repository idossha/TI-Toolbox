---
layout: gallery
title: Gmsh Freeview Gallery
permalink: /gallery/gmsh-freeview/
---

<link rel="stylesheet" href="{{ '/assets/css/lightbox.css' | relative_url }}">

<div class="gallery-section">
  <h3>Gmsh & Freeview Mesh Visualization</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_atlas.png" alt="MRI Atlas Visualization" onclick="openLightbox(this)" />
      <p>3D mesh visualization showing tetrahedral elements and surfaces.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_ROI.png" alt="MRI ROI Visualization" onclick="openLightbox(this)" />
      <p>Freeview visualization with anatomical brain overlays.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_atlas_field.png" alt="Atlas with Field" onclick="openLightbox(this)" />
      <p>Electric field distribution visualization on mesh surfaces.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_ROI_field.png" alt="ROI with Field" onclick="openLightbox(this)" />
      <p>Region of interest selection and highlighting in Freeview.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Gmsh Interface</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/gmsh_launching.png" alt="Gmsh launching" onclick="openLightbox(this)" />
      <p>Launching Gmsh from the toolbox to display the head mesh with electric field data.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/gmsh_tools_menu.png" alt="Gmsh tools menu" onclick="openLightbox(this)" />
      <p>The Gmsh tools menu, used for clipping the mesh and toggling element visibility.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/gmsh_options_menu.png" alt="Gmsh options menu" onclick="openLightbox(this)" />
      <p>The Gmsh options menu for colour scales, ranges, and general display settings.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Freeview Interface</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/freeview_menu.png" alt="Freeview menu" onclick="openLightbox(this)" />
      <p>Freeview overlay controls and atlas options before launching.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/visualizers/freeview_example.png" alt="Freeview example" onclick="openLightbox(this)" />
      <p>Freeview displaying an E-field overlay on the anatomical MRI.</p>
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
