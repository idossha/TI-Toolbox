---
layout: wiki
title: Viewer
permalink: /wiki/visualizers/
---

TI-Toolbox's viewer is **[Tetravox](https://github.com/idossha/tetravox)**, and it ships with the
toolbox: a browser build of the Tetravox engine (the "embed") lives inside the Docker image, is
served by the container, and draws on your own machine's GPU inside the app window. **You install
nothing.** Full 3-D viewing of mesh (`.msh`) and volumetric (`.nii`/`.nii.gz`) results happens on
the **Viewer** page. There is no Freeview and no Gmsh in TI-Toolbox v3, and no X11.

The run pages (Simulator, Optimizer, Analyzer) have their own small 3-D pane for placing electrodes
and picking atlas regions. That pane is part of the toolbox, is drawn by the toolbox's own renderer
rather than by Tetravox, and is not a viewer — it draws packaged reference anatomy, never your
subject's.

<img src="{{ site.baseurl }}/assets/imgs/v3/viewer.png" alt="A TI field open in the Tetravox viewer inside the app" style="width: 100%; max-width: 1000px;">
<em>A simulation open on the <strong>Tetravox</strong> sub-page: layers and appearance on the left, the cursor read-out on the right, all inside the app window.</em>

## How to open a result

The **Viewer** entry in the left rail has two rows indented under it, **Menu** and **Tetravox**.
Clicking Viewer itself opens Menu.

1. On **Menu**, choose what to look at: the type (simulation, analysis, atlas overlay, a custom
   path), then the subject, simulation, field and space it takes.
2. Nothing loads while you are choosing — the page shows a **"What will open"** list of the files
   it would open, in order, with each one's size. Edit it: remove a file, add another from
   everything the subject offers or from any path in the project, reorder it.
3. Press **Open in viewer**. You are moved to **Tetravox**, and the scene is drawn there
   full-bleed.

The Tetravox row's strip carries the scene's name and **Reload**, which re-sends the scene it is
showing. To go back, click **Menu** in the rail — the picture is kept, so you can change the list,
press Open again, and the new scene replaces the old one.

If the window is narrow (below 1440 px) the rail shows icons only and the two sub-rows are hidden;
open the command palette and pick `Viewer · Menu` or `Viewer · Tetravox` instead.

Layer visibility and opacity, the shared 3-D cursor, the slice/3-D layouts, screenshots and saving a
modified scene are all the viewer's own controls, in its own panels. TI-Toolbox's side of the
boundary ends at deciding which files belong together.

## The scene file

Opening also writes the scene into your project at `code/ti-toolbox/viewer/<type>.tetravox.json`.
It is an ordinary file — a few kilobytes, because every layer refers to a dataset by its path
rather than copying it — in `ViewSpec` v2, Tetravox's own format; TI-Toolbox invents no scene format
of its own. Keep it, archive it with the results it describes, or hand it to a Tetravox desktop
application if you have one installed (**File ▸ Open Scene…**). Nothing in TI-Toolbox requires you
to.

## Saving what you chose, and saving what you saw

Two different things are worth keeping, and the Viewer keeps them separately because they answer
different questions.

**Save selection…** writes a *composition* to
`code/ti-toolbox/viewer/compositions/<name>.json`: the subject, the space, and the inputs you
ticked, recorded by file name. It is small and readable, and it does not freeze the data — loading
it next month re-resolves those same choices against whatever is in the project then, and tells you
what has since gone missing rather than failing. Use it when the question is *"show me the same
thing, from the current data"* — the reproducibility artefact you would put next to a manuscript.

**Save scene** (in the **Tetravox** sub-page, once something is open) writes what you are actually
looking at to `code/ti-toolbox/viewer/scenes/<name>.tetravox.json`: the camera, the layout, and
every layer's window, threshold, colormap and opacity, exactly as you left them after adjusting
them in the viewer. A PNG thumbnail is written beside it, which is what the **Saved scenes** list
in the Menu shows, so you can pick a picture out of a list rather than a filename. Use it when the
question is *"show me exactly this picture again"* — a figure you have finished composing.

Scene names default to `<subject>_<simulation>_<field>_<date>`, and both kinds of file live inside
the project, so they travel with it when you copy or archive it. A saved scene is an ordinary
Tetravox scene: a standalone Tetravox desktop application opens it directly.

## Keeping the viewer current

The viewer can be updated without updating the toolbox. **Settings ▸ Viewer** shows which bundle is
active, its version and protocol, and whether it came from the image or was installed later. Updates
are checked in the background at most once a day (you can turn that off), every download is verified
against its published sha256 before it is unpacked, and rolling back to the version baked into the
image is one click — nothing is deleted to go back. An offline or air-gapped machine keeps the
bundle the image shipped and needs no network at all.

## No-WebGL2 state

Both the run pages' pane and the viewer need WebGL2. On a host GPU/driver combination without it,
each says so explicitly rather than showing a blank canvas — on the run pages the rest of the page
keeps working, and every choice the pane offers (electrodes, atlas regions) is also available from
the form beside it. This is a host capability check, not a container one: it depends on what the
Electron renderer's GPU process can do on your machine. Chromium 137 removed the automatic software
fallback, so there is nothing to switch on.

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
