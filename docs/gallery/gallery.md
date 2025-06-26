---
layout: page
title: Gallery
permalink: /gallery/
---

# TI-Toolbox Gallery

Explore visual examples of the Temporal Interference Toolbox capabilities, from preprocessing to simulation and analysis.

## Preprocessing Pipeline

<div class="gallery-section">
  <h3>DICOM to NIfTI Conversion & FreeSurfer Segmentation</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/co-registration.png" alt="Preprocessing Pipeline" />
      <p>Complete preprocessing workflow showing DICOM conversion, FreeSurfer segmentation, and SimNIBS head modeling.</p>
    </div>
  </div>
</div>

## Electrode Optimization

<div class="gallery-section">
  <h3>Flex-Search Optimization</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/flex-search.png" alt="Flex-Search Optimization" />
      <p>Evolutionary algorithm optimization showing electrode placement convergence for targeted stimulation.</p>
    </div>
  </div>
</div>

<div class="gallery-section">
  <h3>Ex-Search Results</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/ex-search_selection.png" alt="Ex-Search Selection" />
      <p>Ex-search interface showing electrode selection and optimization parameters.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/ex-search_combos.png" alt="Ex-Search Combinations" />
      <p>Exhaustive search results showing different electrode combinations and their effectiveness.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/mapping.png" alt="Electrode Mapping" />
      <p>3D visualization of electrode placement and mapping on head model.</p>
    </div>
  </div>
</div>

## Temporal Interference Simulation

<div class="gallery-section">
  <h3>TI Field Analysis</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/MRI_ROI_field.png" alt="MRI ROI Field Analysis" />
      <p>MRI-based region of interest analysis with temporal interference field distribution.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/MRI_ROI.png" alt="MRI ROI Analysis" />
      <p>Region of interest analysis showing precise targeting of brain structures.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analysis_visual.png" alt="Analysis Visualization" />
      <p>Comprehensive visualization of simulation results and field analysis.</p>
    </div>
  </div>
</div>

## Atlas-Based Analysis

<div class="gallery-section">
  <h3>Atlas Alignment & Field Visualization</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/MRI_atlas.png" alt="MRI Atlas" />
      <p>Brain atlas visualization with anatomical structures and regions clearly defined.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/MRI_atlas_field.png" alt="Atlas with Field" />
      <p>Atlas overlay with electric field distribution for anatomical reference and targeting.</p>
    </div>
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/atlas.png" alt="Comprehensive Atlas View" />
      <p>Detailed atlas visualization showing multiple brain regions and their relationships.</p>
    </div>
  </div>
</div>

## Analysis & Results

<div class="gallery-section">
  <h3>Simulation Analysis</h3>
  <div class="gallery-grid">
    <div class="gallery-item">
      <img src="{{ site.baseurl }}/gallery/assets/analysis_plot.png" alt="Analysis Plots" />
      <p>Comprehensive analysis plots showing field strength, distribution, and statistical results.</p>
    </div>
  </div>
</div>

<style>
.gallery-section {
  margin: 2rem 0;
  padding: 1rem;
  border-left: 4px solid #0074D9;
  background-color: #f8f9fa;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
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

.gallery-item img {
  width: 100%;
  height: auto;
  border-radius: 4px;
  margin-bottom: 0.5rem;
}

.gallery-item p {
  margin: 0;
  font-size: 0.9rem;
  color: #666;
  line-height: 1.4;
}

.gallery-item a {
  text-decoration: none;
  color: inherit;
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
}
</style> 