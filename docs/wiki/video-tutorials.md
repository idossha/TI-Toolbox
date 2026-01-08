---
layout: wiki
title: Video Tutorials
permalink: /wiki/video-tutorials/
---

Welcome to our collection of video tutorials for the TI-Toolbox. These videos provide step-by-step guidance on using various features and workflows.

## Getting Started

<div class="video-tutorial">
  <h3 class="video-title">Installation and Updates</h3>
  <div class="video-container">
    <iframe src="" title="Electrode Placement Optimization" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
  </div>
  <p class="video-description">
    placeholder to be uploaded within the next couple of days.
  </p>
</div>

---

## Advanced Topics

<div class="video-tutorial">
  <h3 class="video-title">Blender Integration: Creating Publication-Ready Visualizations</h3>
  <div class="video-container">
    <iframe src="https://www.youtube.com/embed/0c3J79PEe-M?vq=highres" title="Temporal Interference Toolbox Tutorial" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
  </div>
  <p class="video-description">
    Learn how to create 3D visualizations for your temporal interference research using TI-Toolbox's Blender integration. This tutorial covers the 3D visualizer's four main modes, with a focus on the montage visualizer for electrode geometry manipulation. You'll learn to export web-friendly GLB files, import brain regions of interest (like thalamus), and render publication-quality images with proper lighting and camera angles. Includes both GUI and command-line workflows, plus some tips. Prerequisites: TI-Toolbox, Docker, Blender and basic familiarity with the TI-Toolbox.
  </p>
</div>


<style>
.video-tutorial {
  margin-bottom: 2rem;
  text-align: center;
}

.video-title {
  margin-top: 0;
  margin-bottom: 1rem;
  font-size: 1.3em;
  font-weight: 600;
  color: #2c3e50;
  text-align: center;
}

.video-container {
  position: relative;
  width: 100%;
  max-width: 560px;
  margin: 0 auto;
  /* Modern CSS aspect ratio (16:9) */
  aspect-ratio: 16 / 9;
  /* Fallback for older browsers */
  padding-bottom: 56.25%; /* 9/16 * 100% = 56.25% */
  height: 0;
  overflow: hidden;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.video-container iframe {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border: none;
  border-radius: 8px;
}

.video-description {
  margin-top: 1rem;
  padding: 1rem;
  background-color: #f8f9fa;
  border-radius: 8px;
  text-align: left;
  border: 1px solid #e9ecef;
}

.video-description strong {
  font-weight: 600;
  color: #2c3e50;
}

/* Responsive adjustments */
@media (max-width: 600px) {
  .video-container {
    max-width: 100%;
  }

  .video-description {
    margin-top: 1rem;
    padding: 0.75rem;
  }
}
</style>