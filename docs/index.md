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
**Install Docker Desktop.** It is the only prerequisite. No X11 server, no XQuartz, no VcXsrv — v3 removed all of it.
</li>
<li markdown="1">
**Install the TI-Toolbox desktop app.**<br>
Download the installer for your platform from the [latest release](https://github.com/idossha/TI-toolbox/releases/latest) — `.dmg` (macOS), `.exe` (Windows), `.AppImage` or `.deb` (Linux). On first launch it pulls the toolbox image and starts the container for you.<br>
Prefer the command line? `loader.py` + `docker-compose.yml` still start the same stack — see [Bash/CLI Usage]({{ site.baseurl }}/installation/bash-cli/).
</li>
<li markdown="1">
**Point it at a project folder.**
Any [BIDS](https://bids.neuroimaging.io/) directory. The [Overview]({{ site.baseurl }}/wiki/overview/) page then tells you what each subject already has and what it is ready for. Example data ships with the toolbox, so you can get familiar with the software right away.
</li>
<li markdown="1">
**Optional: connect your AI assistant** — install the [TI-Toolbox plugin]({{ site.baseurl }}/wiki/ai-assistant/) so Claude Code, Codex or Cursor can answer questions from the wiki, write scripts, and troubleshoot your project.
</li>
</ol>
</section>

<section>
<p class="home-section__title">Highlights</p>
<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/v3/overview.png" alt="The Overview page">
        <p>Overview: what every subject in the project has, and what it is ready for</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/simulator.png" alt="The Simulator page">
        <p>Simulator: one row per job, with the montage drawn on the head beside it</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/viewer.png" alt="The Viewer showing a TI field in Tetravox">
        <p>The viewer is Tetravox, shipped in the image and drawn in the app window — no install, no X11</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/optimizer.png" alt="The Optimizer page with an interactive atlas">
        <p>Optimizer: flex and exhaustive electrode search, with the atlas you are targeting in front of you</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/pipeline.png" alt="The Pipeline canvas">
        <p>Pipeline: wire the steps into a graph, run it as one job group, or export it as a notebook</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/notebooks.png" alt="A notebook with a plotted field and tables">
        <p>Notebooks: Jupyter on the container&#39;s SimNIBS Python, with your project already resolved</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/jobs.png" alt="The Jobs page">
        <p>Jobs: every run recorded — state, stage, logs, artifacts, cancel and rerun</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/blender/visual_exporter_vectors_close.png" alt="Vector Field Visualization">
        <p>High-resolution electric field vector visualization showing direction and magnitude</p>
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
      <span class="dot" onclick="currentSlide(this, 7)"></span>
      <span class="dot" onclick="currentSlide(this, 8)"></span>
    </div>
  </div>
</div>
</section>
</div>
