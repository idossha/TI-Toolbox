---
layout: wiki
title: Viewer
permalink: /wiki/visualizers/
---

TI-Toolbox does not render 3-D results itself. It hands them to
**[TetraVox](https://github.com/idossha/tetravox)**, a separate desktop viewer.
Your job in TI-Toolbox is simple: pick what to look at. TetraVox does the rest.

<!-- Images: TetraVox docs screenshots (MIT, same author), https://github.com/idossha/tetravox docs/screenshots/2026-08-29/brain/ -->
<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/v3/viewer/brain-mesh-ti-max-2x2.webp" alt="TI_max on the grey-matter mesh, cut by the slices in 2D and whole in 3D">
        <p>TI_max on the grey-matter mesh, cut by the slices in 2D and whole in 3D</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/viewer/brain-mesh-tdcs-magne-2x2.webp" alt="A head mesh's cross-section in the slice panes, filled by its field (magnE) with the tissue boundaries outlined">
        <p>A head mesh's cross-section in the slice panes, filled by its field (magnE) with the tissue boundaries outlined</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/viewer/brain-mesh-e-glyphs-2x2.webp" alt="Electric-field vectors drawn as arrows in the 3D pane of a 2x2">
        <p>Electric-field vectors drawn as arrows in the 3D pane of a 2x2</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/viewer/brain-mesh-e-glyphs-3d.webp" alt="The same arrows filling a single 3D pane">
        <p>The same arrows filling a single 3D pane</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/v3/viewer/brain-tissues-2x2.webp" alt="A head mesh: its tissue cross-section in the slice panes and the scalp surface in 3D">
        <p>A head mesh: its tissue cross-section in the slice panes and the scalp surface in 3D</p>
      </div>
    <button class="carousel-btn prev" onclick="changeSlide(this, -1)">&#10094;</button>
    <button class="carousel-btn next" onclick="changeSlide(this, 1)">&#10095;</button>
    </div>
    <div class="carousel-dots">
      <span class="dot active" onclick="currentSlide(this, 0)"></span>
      <span class="dot" onclick="currentSlide(this, 1)"></span>
      <span class="dot" onclick="currentSlide(this, 2)"></span>
      <span class="dot" onclick="currentSlide(this, 3)"></span>
      <span class="dot" onclick="currentSlide(this, 4)"></span>
    </div>
  </div>
</div>

## Setup

Nothing to do: the desktop app installs its own TetraVox on first launch (one download, needs
internet). **Settings ▸ Viewer** shows the version, offers **Retry setup** if that download failed,
and **Update to X** when a newer release exists. TI-Toolbox only ever launches this copy, not one
you installed yourself.

## Open a result

1. On the **Viewer** page, pick a **subject** and a **space** (subject or MNI).
2. Tick the files you want: anatomy, simulation fields, analysis outputs.
   Everything the subject has is listed. Greyed rows tell you what is missing and why.
3. Check the **What will open** list. Drag to reorder layers, remove what you don't need.
4. Click **Open in viewer**. TetraVox opens with your scene.

<img src="{{ site.baseurl }}/assets/imgs/v3/viewer-compose.png" alt="The Viewer page: tick files under Compose, check the What will open list, then Open in viewer; saved scenes are listed on the right" style="width: 100%; max-width: 1000px;">
<em>The Viewer page. Compose on the left, the launch button and saved scenes on the right.</em>

Results and jobs pages also have a direct open button, so you rarely need to build a scene by hand.
A simulation opens on its field mesh shown as grey matter only (the other tissues are hidden, one
tick away in TetraVox's tissue list), coloured by `TI_max` (`mTI_max` for mTI, `hf_peak` for a
carrier-only control) and windowed from its grey-matter values; every other field the simulation
saved is on the same mesh, one field switch away, under its display name (TI<sub>max</sub>,
HF<sub>peak</sub>, …) and units. A simulation that wrote NIfTI volumes opens them too.

A few things to know:

- **One subject per scene.** Switching subjects clears the previous one's files.
- **Nothing loads until you click Open.** Ticking boxes is free.
- **Meshes are big** (up to a few hundred MB). They take a moment to open.

## Scenes

A scene is a small file that lists which datasets to show, in what order. It points at your data
instead of copying it, so keep the data next to it if you move or archive it.

- **Save scene** snapshots the live TetraVox scene, including camera and appearance changes, into
  `code/ti-toolbox/viewer/scenes/` in your project. It is listed under **Saved scenes** on the
  right; click one to reopen it.
- Opening a scene while TetraVox is already running asks before replacing its current view, so
  save any changes in TetraVox first.
- A browser session cannot start TetraVox; it offers a **Download prepared scene for TetraVox**
  link instead.

Scene files live under `code/ti-toolbox/viewer/` in your project.

## Updating

Two ways, same result — TI-Toolbox always does the install:

- **Settings ▸ Viewer** shows the newest release beside yours; click **Update to X** (close
  TetraVox first), or **Check for updates** to ask again.
- Inside TetraVox, a **Software Update** window appears when a newer release exists (or use its
  **Check for Updates…** menu item). **Update to X** closes TetraVox; TI-Toolbox downloads and
  verifies the release, then reopens TetraVox with your last scene. **Skip This Version** stops the
  reminder for that version.

## Troubleshooting

- **Blank or "no WebGL2" message**: your graphics driver does not support WebGL2. The rest of
  TI-Toolbox keeps working.
- **A layer is missing**: the file is not on disk. Check that the simulation or analysis finished
  and produced that output.
- **TetraVox does not open**: check **Settings ▸ Viewer** shows an installed version.
