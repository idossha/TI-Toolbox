---
layout: home
---

<section class="hero">
  <p class="hero__tagline">A comprehensive toolbox for temporal interference stimulation research, providing end-to-end neuroimaging and simulation capabilities.</p>
</section>

<div class="home-grid">
<section>
<p class="home-section__title">Quick start</p>
<ol class="quickstart" markdown="1">
<li markdown="1">
**Install Docker.** Install and start [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine on Linux).
</li>
<li markdown="1">
**Load TI-Toolbox.** Follow the [installation guide]({{ site.baseurl }}/installation/) to load the matching image and launch the toolbox.
</li>
<li markdown="1">
**Start working.** Open your project, then simulate, optimize and explore your results. The [wiki]({{ site.baseurl }}/wiki/) walks you through each tool.
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

<section class="stack">
<h2 class="stack__heading">One command, and the whole stack is running</h2>
<p class="stack__lede">The interface runs on your machine, the science runs in one published container, and both work on the project directory you point them at.</p>

<div class="stack__row">
  <div class="stack__card">
    <p class="stack__eyebrow">01 / Loader</p>
    <p class="stack__title">One command</p>
    <p class="stack__body"><code>loader.sh</code> starts the container and, on first run, downloads and checksum-verifies the desktop app. Docker is the only prerequisite.</p>
  </div>
  <div class="stack__card">
    <p class="stack__eyebrow">02 / Desktop app</p>
    <p class="stack__title">The interface</p>
    <p class="stack__body">A native Electron app on the host. <code>--browser</code> serves the same interface in a browser tab as a fallback.</p>
  </div>
  <div class="stack__card">
    <p class="stack__eyebrow">03 / Container</p>
    <p class="stack__title">SimNIBS, server and jobs</p>
    <p class="stack__body">One published image runs the job server; each job is a <code>simnibs_python -m tit.&lt;kind&gt;</code> process beside it. FreeSurfer and QSIPrep run as sibling containers.</p>
  </div>
  <div class="stack__card">
    <p class="stack__eyebrow">04 / Your project</p>
    <p class="stack__title">A BIDS directory</p>
    <p class="stack__body">Your project folder is bind-mounted at <code>/mnt/&lt;name&gt;</code>, and it is the only host directory the container is given. Every result lands under <code>derivatives/</code>.</p>
  </div>
  <div class="stack__card">
    <p class="stack__eyebrow">05 / Tetravox</p>
    <p class="stack__title">Native 3D viewer</p>
    <p class="stack__body">A separate viewer app that TI-Toolbox installs and keeps up to date. Scenes are handed over as <code>.tetravox.json</code> files.</p>
  </div>
</div>

<div class="stack__callout">
  <span class="stack__callout-title">Know your data boundary</span>
  <p class="stack__callout-body">Your data stays on your machine: it lives in your own BIDS project directory, and results are written back beside it under <code>derivatives/</code>. The job server is published on loopback only (<code>127.0.0.1:8765</code>) and every request is authenticated with a per-session token.</p>
</div>
</section>
