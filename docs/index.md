---
layout: home
---

<section class="hero">
  <p class="hero__tagline">A comprehensive toolbox for temporal interference stimulation research, providing end-to-end neuroimaging and simulation capabilities.</p>
</section>

<div class="home-grid">
<section>
<p class="home-section__title">How it works</p>
<ol class="flow">
  <li class="flow__step">
    <p class="flow__eyebrow">01 / Entry point</p>
    <p class="flow__title">A desktop app or a single script</p>
    <p class="flow__body">Open the desktop app, or run the loader script from a terminal. Docker is the only prerequisite; everything else is fetched on first run.</p>
    <a class="flow__link" href="{{ site.baseurl }}/installation/">Installation guide</a>
  </li>
  <li class="flow__step">
    <p class="flow__eyebrow">02 / Container</p>
    <p class="flow__title">A reproducible environment</p>
    <p class="flow__body">Every simulation, optimization and analysis runs inside one published Docker image, so results are the same on any machine.</p>
    <a class="flow__link" href="{{ site.baseurl }}/wiki/desktop-app/">How the app and container fit together</a>
  </li>
  <li class="flow__step">
    <p class="flow__eyebrow">03 / Your data</p>
    <p class="flow__title">One BIDS folder on your machine</p>
    <p class="flow__body">Your project is a BIDS directory on your own disk, mounted into the container. Nothing leaves your machine.</p>
    <a class="flow__link" href="{{ site.baseurl }}/wiki/pre-processing/#required-input-data-structure">Expected project layout</a>
  </li>
  <li class="flow__step">
    <p class="flow__eyebrow">04 / Extensions</p>
    <p class="flow__title">BIDS-friendly apps alongside</p>
    <p class="flow__body">FastSurfer, QSIPrep, QSIRecon and Tetravox run beside the toolbox on the same project, and so can other BIDS Apps or Neurodesk containers.</p>
    <p class="flow__links">
      <a class="flow__link" href="{{ site.baseurl }}/wiki/fastsurfer/">FastSurfer</a>
      <a class="flow__link" href="{{ site.baseurl }}/wiki/diffusion-processing/">QSIPrep / QSIRecon</a>
      <a class="flow__link" href="{{ site.baseurl }}/wiki/visualizers/">Tetravox</a>
    </p>
  </li>
</ol>
</section>

<section>
<p class="home-section__title">Explore TI-Toolbox</p>
<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/v3/simulator.png" alt="The Simulator page with a montage preview">
        <p>Simulator: configure simulations and preview your electrode montage</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/optimizer.png" alt="The Optimizer page with an interactive atlas">
        <p>Optimizer: search electrode configurations with your target atlas in view</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/viewer.png" alt="A TI electric field displayed in Tetravox">
        <p>Tetravox: explore anatomy and electric fields in the integrated 3D viewer</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/notebooks.png" alt="A notebook with a plotted field and tables">
        <p>Notebooks: work interactively with your project and SimNIBS Python</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_vectors_close.png" alt="A close-up of electric field vectors showing direction and magnitude">
        <p>High-resolution electric field visualization showing direction and magnitude</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/blender/blender_closeup.png" alt="A detailed close-up of a Blender visualization">
        <p>Blender: a detailed close-up of the visualization</p>
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
</section>
</div>

