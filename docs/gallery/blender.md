---
layout: gallery
title: Blender Gallery
permalink: /gallery/blender/
---

<link rel="stylesheet" href="{{ '/assets/css/lightbox.css' | relative_url }}">

<div class="gallery-section">
  <h3>Blender Montage Creation & Visualization</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/blender_overview.png" alt="Blender Overview" onclick="openLightbox(this)" />
      <p>Overview of Blender montage creation and visualization capabilities.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/blender_closeup.png" alt="Blender Closeup" onclick="openLightbox(this)" />
      <p>Detailed closeup view of Blender visualization elements.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/blender_HF_side.png" alt="Blender HF Side View" onclick="openLightbox(this)" />
      <p>Side view of high-frequency field visualization in Blender.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/blender_HF_top.png" alt="Blender HF Top View" onclick="openLightbox(this)" />
      <p>Top view of high-frequency field visualization in Blender.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_ply_sample_2.png" alt="PLY Export Sample 2" onclick="openLightbox(this)" />
      <p>Example of PLY mesh export from visual exporter showing DKT atlas + left insula.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_rgb_vectors.png" alt="RGB Vector Visualization" onclick="openLightbox(this)" />
      <p>RGB color-coded vector field visualization.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_vectors_close.png" alt="Close-up Vector Fields" onclick="openLightbox(this)" />
      <p>Detailed close-up view of vector field visualization.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_vectors.png" alt="Vector Field Visualization" onclick="openLightbox(this)" />
      <p>Comprehensive vector field visualization in Blender.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/4_channel_HF_high_vector_density.png" alt="4-Channel individual HF vector field" onclick="openLightbox(this)" />
      <p>Four-channel individual high-frequency field vector visualization</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/4_channel_mTI_field.png" alt="4-Channel mTI Field" onclick="openLightbox(this)" />
      <p>Four-channel mTI field vector visualization</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Mesh Exports</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_ply_sample.png" alt="PLY export sample" onclick="openLightbox(this)" />
      <p>PLY mesh export from the 3D Visual Exporter, carrying per-vertex colour attributes.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_stl_sample.png" alt="STL export sample" onclick="openLightbox(this)" />
      <p>STL mesh export, geometry only, for tools that do not read vertex colours.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_electrodes_subcortical.png" alt="Electrodes with sub-cortical structures" onclick="openLightbox(this)" />
      <p>Electrode placement rendered together with sub-cortical structures for anatomical context.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Importing an Export into Blender</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_blender_1.png" alt="Import PLY file" onclick="openLightbox(this)" />
      <p>Step 1 &mdash; import the exported PLY; the mesh appears in the viewport and may need rescaling.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_blender_2.png" alt="Material Preview mode" onclick="openLightbox(this)" />
      <p>Step 2 &mdash; switch to Material Preview to see materials under basic lighting.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_blender_3.png" alt="Adding a material" onclick="openLightbox(this)" />
      <p>Step 3 &mdash; add a material, which is assigned to the selected object automatically.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_blender_4.png" alt="Setting the colour attribute" onclick="openLightbox(this)" />
      <p>Step 4 &mdash; add an Attribute node pointing at the exported colour attribute.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_blender_5.png" alt="Connected shader" onclick="openLightbox(this)" />
      <p>Step 5 &mdash; connect the Attribute node into the shader so the exported colours render.</p>
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
