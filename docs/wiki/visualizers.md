---
layout: wiki
title: Viewer
permalink: /wiki/visualizers/
---

TI-Toolbox has one built-in viewer, **Tetravox Embed**, for both mesh (`.msh`) and volumetric
(`.nii`/`.nii.gz`) results. It renders inside the same window as the rest of the toolbox — no
separate application, no X11, no host-side install. There is no Freeview or Gmsh in TI-Toolbox
v3: viewing a simulation, an analysis, or an atlas overlay all go through the same embedded
viewer.

## What Tetravox Embed is

Tetravox is a standalone WebGL2 + WASM viewer (its own project, with its own docs). TI-Toolbox
serves a built copy of it from the container at `/tetravox/` and mounts it inside the app's
window as an `<iframe>`. The toolbox UI talks to it with `postMessage`, and everything the
viewer needs — the head mesh, field data, atlas volumes — streams to it from the same
container over `/api/files/raw/...`, so the WebGL2/WASM rendering itself runs on your host's
GPU even though the container did all the computing.

For the full scene format and message protocol, see Tetravox's own **[EMBED.md](https://github.com/idossha/tetravox)**
documentation — TI-Toolbox does not reinvent a scene format of its own. When TI-Toolbox opens
a result in the viewer, it builds a Tetravox `ViewSpec` v2 document server-side (from the
simulation's mesh/NIfTI outputs) and hands it to the embed with a `load` message; the embed
answers `loaded` once it has fetched and rendered every referenced dataset.

## How to open a result

1. **From the Analyzer, Simulator, or Results page**: select a subject, a simulation, and an
   analysis, then choose **View**.
2. The viewer opens in the same window — full-bleed, with an inspector panel alongside it.
3. Use the inspector to toggle layers, move the cursor between slice views and the 3D view,
   change the layout, or take a screenshot.

There is no separate window to manage, no file path to type, and nothing to install — if the
scene fails to load, the most likely cause is listed under "No-WebGL2 state" below.

## The Inspector

The inspector panel alongside the viewer offers:

- **Layers** — toggle visibility and opacity per dataset (anatomical volume, field overlay,
  atlas labels, mesh surfaces), matching what a scene's `ViewSpec` layers describe.
- **Cursor / space** — move the shared 3D cursor and switch between the slice views (axial,
  coronal, sagittal) and the 3D view; a mesh's clip plane follows the cursor automatically for
  simulation scenes.
- **Layout** — switch between the default 2×2 (three slice views + 3D) and other supported
  arrangements.
- **Screenshot** — capture the current view as an image (`postMessage`'s `screenshot`
  round-trip through the embed).
- **Save scene** — export the current `ViewSpec` for reuse or sharing.

## No-WebGL2 state

Tetravox Embed needs WebGL2. On a host GPU/driver combination without it, the viewer reports
this instead of a blank canvas — the toolbox UI shows an explicit "your browser/GPU does not
support WebGL2" state in the viewer pane rather than failing silently. This is a host
capability check, not a container one: it depends on what the Electron renderer's GPU process
can do on your machine.

---

## Electrode Placement Overlay

For simulations with saved electrode coordinates in `documentation/config.json`, pre-processing
can create a single binary label-mask NIfTI that shows where electrodes were placed on the
subject anatomy, and load it as one of the viewer's layers.

- **Source of truth**: The overlay reads electrode coordinates, channel grouping, dimensions, and simulation mode from the saved simulation config.
- **Coloring**: Labels are channel-based, not electrode-based. Unipolar simulations use two channel colors; multipolar simulations use four channel colors. The color order matches the montage PNG overlay: blue, red, green, purple, then the remaining montage colors if needed.
- **Output path**: `Simulations/{simulation}/TI/montage_imgs/electrode_overlay_subject.nii.gz` for TI/unipolar runs, or `Simulations/{simulation}/mTI/montage_imgs/electrode_overlay_subject.nii.gz` for mTI/multipolar runs.

---

## File Formats and Locations

### Mesh Files (.msh)
- **Location**: `derivatives/SimNIBS/sub-{ID}/Simulations/{sim_name}/Analyses/Mesh/{analysis_name}/`
- **Content**: Tetrahedral mesh with embedded field data

### NIfTI Files (.nii/.nii.gz)
- **Location**: `derivatives/SimNIBS/sub-{ID}/Simulations/{sim_name}/Analyses/Voxel/{analysis_name}/`
- **Content**: Volumetric data in standard neuroimaging format

### Electrode Overlay Files (.nii/.nii.gz)
- **Location**: `derivatives/SimNIBS/sub-{ID}/Simulations/{sim_name}/{TI|mTI}/montage_imgs/electrode_overlay_subject.nii.gz`
- **Content**: Channel-labeled electrode placement mask

---

## Troubleshooting

**Scene doesn't load / stays blank**
- Check the "No-WebGL2 state" note above — the viewer reports this explicitly rather than showing a blank canvas.
- Confirm the analysis actually completed and produced the expected mesh/NIfTI outputs.

**Layer missing from the inspector**
- The `ViewSpec` only lists layers for datasets that exist on disk at load time — an analysis that skipped a field (see [Simulator]({{ site.baseurl }}/wiki/simulator/)'s selectable output fields) will not have a layer for it.

## Integration with Analysis Pipeline

1. **Run Simulations**: Use Flex Search or Ex Search to generate simulation parameters
2. **Execute Analysis**: Run the analyzer to generate field distributions
3. **Visualize Results**: Open the result in the viewer directly from the Analyzer/Results page
4. **Iterate**: Use visualization insights to refine simulation parameters
