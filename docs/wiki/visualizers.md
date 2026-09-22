---
layout: wiki
title: Viewer
permalink: /wiki/visualizers/
---

TI-Toolbox does not render 3-D results itself. It hands them to
**[TetraVox](https://github.com/idossha/tetravox)**, a separate desktop viewer.
Your job in TI-Toolbox is simple: pick what to look at. TetraVox does the rest.

<div class="image-container">
  <img src="{{ site.baseurl }}/assets/imgs/v3/viewer.png" alt="A TI electric field displayed in TetraVox">
</div>

## Setup

Nothing to do: the desktop app installs its own TetraVox on first launch (one download, needs
internet). **Settings → Viewer** shows the version, offers **Retry setup** if that download failed,
and **Update** to move to the newest release. TI-Toolbox only ever launches this copy, not one you
installed yourself.

## Open a result

1. On the **Viewer** page, pick a **subject** and a **space** (subject or MNI).
2. Tick the files you want: anatomy, simulation fields, analysis outputs.
   Everything the subject has is listed. Greyed rows tell you what is missing and why.
3. Check the **What will open** list. Drag to reorder layers, remove what you don't need.
4. Click **Open in viewer**. TetraVox opens with your scene.

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

**Settings → Viewer → Check for updates** fetches the newest TetraVox release. Update from here,
not from TetraVox's own menu, so TI-Toolbox keeps track of the version.

## Troubleshooting

- **Blank or "no WebGL2" message**: your graphics driver does not support WebGL2. The rest of
  TI-Toolbox keeps working.
- **A layer is missing**: the file is not on disk. Check that the simulation or analysis finished
  and produced that output.
- **TetraVox does not open**: check **Settings → Viewer** shows an installed version.
