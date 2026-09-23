---
layout: wiki
title: Viewer
permalink: /wiki/visualizers/
---

TI-Toolbox does not render 3-D results itself. It hands them to
**[TetraVox](https://github.com/idossha/tetravox)**, a separate desktop viewer.
Your job in TI-Toolbox is simple: pick what to look at. TetraVox does the rest.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/v3/tetravox-dti-tensors.jpg" alt="TetraVox showing diffusion tensors over a T1 in axial, coronal, sagittal and 3-D views">
</div>

## Setup

Nothing to do: the desktop app installs its own TetraVox on first launch (one download, needs
internet). **Settings → Viewer** shows the version, offers **Retry setup** if that download failed,
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

A few things to know:

- **One subject per scene.** Switching subjects clears the previous one's files.
- **Nothing loads until you click Open.** Ticking boxes is free.
- **Meshes are big** (up to a few hundred MB). They take a moment to open.

## Scenes

A scene is a small file that lists which datasets to show, in what order. It points at your data
instead of copying it, so keep the data next to it if you move or archive it.

- **Save selection…** keeps your subject, space and ticked files. Reload it later and it
  re-finds the same files in the current project, and tells you if any are gone.
- **Save scene** keeps a ready-to-open scene in **Saved scenes** on the right. Click one to reopen it.
- Camera, colours, opacity and screenshots live in TetraVox. To keep those, use
  **Save Scene** inside TetraVox and put the file in your project.

Scene files live under `code/ti-toolbox/viewer/` in your project.

## Updating

Two ways, same result — TI-Toolbox always does the install:

- **Settings → Viewer** shows the newest release beside yours; click **Update to X** (close
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
- **TetraVox does not open**: check **Settings → Viewer** shows an installed version.
