---
layout: home
---

<div class="hero" style="display: flex; align-items: center; gap: 2rem;">
  <img src="{{ site.baseurl }}/assets/imgs/icon.png" alt="TI Toolbox Icon" style="width:80px;height:80px;flex-shrink:0;">
  <div>
    <h1>Temporal Interference Toolbox</h1>
    <p>A comprehensive toolbox for temporal interference stimulation research, providing end-to-end neuroimaging and simulation capabilities.</p>
  </div>
</div>

<div class="features">
  <!-- ... existing code ... -->
</div>


1. **Install Dependencies** Docker required for running the toolbox environment and optional X11 server.
2. **Install TI-Toolbox:**<br>
  A. Desktop Executable:
   Download and run the executable version of the latest release [here](https://github.com/idossha/TI-toolbox/releases/latest).<br>
  B. CLI Entry:
    Download the two files below to a designated directory.
   - **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)** - Main launch script
   - **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)** - Docker configuration
   ```bash
   bash loader.sh
   ```
  3. **Set up your BIDS project directory**
   - Use our example dataset to get familiar with the software or organize your data in BIDS format.<br> `{project-name}/sourcedata/sub-{subjectID}/T1w/dicom/` 

<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_vectors_close.png" alt="Vector Field Visualization">
        <p>High-resolution electric field vector visualization showing direction and magnitude</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/blender/blender_closeup.png" alt="3D Blender Visualization">
        <p>Advanced 3D visualization of temporal interference fields using Blender integration</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/development/testing_graphical_abstract_revised.png" alt="TI-Toolbox Tech Stack">
        <p>Complete TI-Toolbox technology stack: BIDS-compatible, Docker-based, end-to-end pipeline</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/ex-search/ex-search_ex-search_selection.png" alt="Electrode Selection">
        <p>Exhaustive search for optimal electrode placement across standard EEG montages</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/flex-search/flex-search_mapping.png" alt="Flex-Search Mapping">
        <p>Flexible search extension mapping genetic algorithm output to registered EEG positions</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/UI/UI_sim.png" alt="Simulation GUI">
        <p>User-friendly GUI for configuring and running temporal interference simulations</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/stats/stats_permutation_null_dist.png" alt="Cluster-Based Permutation Testing">
        <p>Statistical analysis with cluster-based permutation testing for group-level inference</p>
      </div>
    </div>
    <button class="carousel-btn prev" onclick="changeSlide(this, -1)">&#10094;</button>
    <button class="carousel-btn next" onclick="changeSlide(this, 1)">&#10095;</button>
    <div class="carousel-dots">
      <span class="dot active" onclick="currentSlide(this, 0)"></span>
      <span class="dot" onclick="currentSlide(this, 1)"></span>
      <span class="dot" onclick="currentSlide(this, 2)"></span>
      <span class="dot" onclick="currentSlide(this, 3)"></span>
      <span class="dot" onclick="currentSlide(this, 4)"></span>
      <span class="dot" onclick="currentSlide(this, 5)"></span>
      <span class="dot" onclick="currentSlide(this, 6)"></span>
    </div>
  </div>
</div>




