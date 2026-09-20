---
layout: wiki
title: Legacy v2 users
permalink: /wiki/legacy-v2/
---

TI-Toolbox v2 is deprecated. It used a PyQt desktop interface; the current guides describe the
v3 Electron application and job server. Do not use current setup or extension instructions as
instructions for a v2 installation.

If you still use v2, consult the [documentation saved with v2.5.0](https://github.com/idossha/TI-Toolbox/tree/v2.5.0/docs)
or the source at your installed version's tag. For the transition to v3, see the
[v3 version notes]({{ site.baseurl }}/releases/v3.0.0/).

## Historical Gmsh and Freeview views

The following captures document v2's external viewers. They are retained for identification of
older workflows and results, not as instructions for v3, which uses the native TetraVox application.

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_atlas.png" alt="v2 atlas mesh visualization">
    <em>Atlas meshes in the legacy external-viewer workflow.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_ROI.png" alt="v2 ROI volume visualization">
    <em>An anatomical ROI overlay in the legacy workflow.</em>
  </div>
</div>

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_atlas_field.png" alt="v2 atlas and field visualization">
    <em>An electric-field overlay with an atlas in the legacy workflow.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_ROI_field.png" alt="v2 ROI and field visualization">
    <em>An electric-field overlay restricted to a region of interest.</em>
  </div>
</div>

### Gmsh

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/visualizers/gmsh_launching.png" alt="Launching Gmsh from TI-Toolbox v2">
    <em>v2 launching Gmsh to display a head mesh with electric-field data.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/visualizers/gmsh_tools_menu.png" alt="Gmsh tools menu">
    <em>The Gmsh tools menu used for clipping and element visibility.</em>
  </div>
</div>

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/visualizers/gmsh_options_menu.png" alt="Gmsh display options" style="width: 100%; max-width: 850px;">
  <em>The legacy Gmsh options for colour scales, ranges and general display settings.</em>
</div>

### Freeview

<div class="image-row">
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/visualizers/freeview_menu.png" alt="Freeview overlay menu">
    <em>Freeview overlay controls and atlas options from the v2 workflow.</em>
  </div>
  <div class="image-container">
    <img src="{{ site.baseurl }}/assets/imgs/visualizers/freeview_example.png" alt="Freeview electric-field overlay">
    <em>Freeview displaying an electric-field overlay on anatomical MRI.</em>
  </div>
</div>
