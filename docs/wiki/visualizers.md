---
layout: wiki
title: Viewer
permalink: /wiki/visualizers/
---

TI-Toolbox does not ship a viewer. Full 3-D viewing of mesh (`.msh`) and volumetric
(`.nii`/`.nii.gz`) results is **[Tetravox](https://github.com/idossha/tetravox)**, a separate
desktop application you install on your own machine. TI-Toolbox's **Viewer** page chooses *what*
to look at and opens it there. There is no Freeview and no Gmsh in TI-Toolbox v3, and no X11.

The run pages (Simulator, Optimizer, Analyzer) have their own small 3-D pane for placing
electrodes and picking atlas regions. That pane is part of the toolbox, needs nothing installed,
and is not a viewer — it draws packaged reference anatomy, never your subject's.

## Installing Tetravox

Download the signed build for your platform from
[the Tetravox releases page](https://github.com/idossha/tetravox/releases/latest) and install it
as you would any application. It updates itself; its releases are not tied to TI-Toolbox's.

**Settings ▸ Viewer** shows whether TI-Toolbox found it, where, and which version. It looks in the
conventional places (`/Applications/Tetravox.app` and `~/Applications` on macOS, `tetravox` on
`PATH` on Linux, `%LOCALAPPDATA%\Programs\Tetravox\Tetravox.exe` on Windows). If yours is
somewhere else — an AppImage, a second copy — set the path there. If it is not installed, the
Viewer page says so and offers the download link instead of failing on click.

## How to open a result

1. On the **Viewer** page, choose what to look at: the type (simulation, analysis, atlas overlay,
   a custom path), then the subject, simulation, field and space it takes.
2. Nothing happens while you are choosing — the page shows a **"What will open"** list of the
   layers it would build, with each one's colormap.
3. Press **Open in Tetravox**. TI-Toolbox writes a scene document into your project at
   `code/ti-toolbox/viewer/<type>.tetravox.json` and hands that file to the app.

Pressing Open again does not start a second copy: Tetravox loads the new scene into the window
already on screen. Results pages carry the same button for a single result.

The scene file is an ordinary file in your project. You can open it later by double-clicking it,
or from Tetravox's own **File ▸ Open Scene…** — it is `ViewSpec` v2, Tetravox's own format, and
TI-Toolbox invents no scene format of its own. Every layer refers to a dataset by its path on your
machine, so nothing is copied and the file stays a few kilobytes.

### Without the desktop app

If you are running the toolbox in a browser rather than the desktop shell, there is no way for the
page to start an application. The button reads **Download scene** instead: save the file, then open
it in Tetravox with File ▸ Open Scene…. The file is the whole interface, so this is a complete
answer, not a degraded one.

## What Tetravox shows

Everything the toolbox used to draw in an inspector belongs to the app now — layer visibility and
opacity, the shared 3-D cursor and the slice/3-D layouts, screenshots and saving a modified scene.
See Tetravox's own documentation for those; TI-Toolbox's side of the boundary ends at the scene
file.

## No-WebGL2 state

The run pages' 3-D pane needs WebGL2. On a host GPU/driver combination without it, the pane says
so explicitly rather than showing a blank canvas — the rest of the page keeps working, and every
choice the pane offers (electrodes, atlas regions) is also available from the form beside it. This
is a host capability check, not a container one: it depends on what the Electron renderer's GPU
process can do on your machine. Tetravox itself makes the same check on its own.

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
