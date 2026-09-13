---
layout: wiki
title: Viewer
permalink: /wiki/visualizers/
---

TI-Toolbox uses **[TetraVox](https://github.com/idossha/tetravox)** for full viewing in a separate
native host window. Install the pinned viewer from **Settings → Viewer**. The Docker container
prepares scenes; the native application reads their datasets from the host filesystem.

The Simulator, Optimizer and Analyzer retain the toolbox's own WebGL2 surface panes. Volume,
target and segmentation previews provide an explicit native-opening action. Guide anatomy remains
reference anatomy: subject-space placement must use the selected subject's geometry.

Opening a changed selection replaces the scene in TetraVox. Camera and appearance edits happen
in that window and are saved with TetraVox's own scene controls.

## How to open a result

Use **Viewer → Menu** to prepare a scene. The **Tetravox** sub-page offers native installation
and opening controls. You can also open native TetraVox without a prepared scene and drag files
into its own window; those files are not imported into the project.

1. On **Menu**, pick a **subject** and a **space** (subject or MNI). Below them the page draws a
   tree of everything that subject has, in three branches:

   - **Anatomy** — grouped by what each file *is*: **Volumes** (T1, T2), **Label volumes
     (atlases)**, **Surfaces** and **Meshes**.
   - **Simulations** — one row per simulation; expand one to see its fields (TI_max, TI_normal,
     the high-frequency magnitudes…), its surfaces, its meshes and its electrode overlay.
   - **Analyses** — the analyzer runs under the simulations you have expanded, and their outputs.

   Every row wears a chip saying which of those it is, because **a mesh and a surface are not the
   same thing**:

   - **MESH** is a tetrahedral finite-element mesh (`.msh`) — the volume SimNIBS actually solved
     the field on, 24–420 MB. Opening one takes a moment.
   - **SURFACE** is a triangulated 2-D sheet (`.gii`, or a FreeSurfer `lh.pial`-style file) — the
     cortical ribbon, a few MB, and no field data of its own.
   - **VOLUME** is a NIfTI/MGZ grid of numbers; **LABELS** is one whose numbers are region ids,
     drawn through a lookup table.

   A **surface** expands to show the things you can hang on it — the `.annot` parcellations
   SimNIBS wrote for it, morphometry curves like `lh.thickness`, and per-vertex data GIfTIs —
   matched to it by hemisphere. Tick one and the surface is coloured by it; a parcellation wins
   over a curve if you tick both, and the curve stays attached for you to switch to inside
   TetraVox. The pinned native **0.4.0** release supports these surface attachments.

   Tick whatever belongs in the scene. You can tick outputs from **more than one simulation** —
   ticking a branch's own box takes the whole branch on or off, and a half-filled box means part of
   it is in the scene. Anything that is not on disk is shown greyed with the reason rather than
   hidden, so a missing mesh is a question you can answer instead of a row that never appears.

   **One subject per scene.** Changing the subject drops any rows belonging to the previous one
   and tells you how many went; shared files (the MNI template, the bundled atlases) stay. A scene
   mixing two subjects is refused outright, because one person's field over another's anatomy
   renders as a perfectly ordinary-looking picture.
2. Nothing loads while you are choosing — the **"What will open"** list below the tree is the scene,
   in order, with each file's size, and it is the same list the tick boxes drive. Edit it directly
   too: remove a file, add one from any path in the project, drag to reorder (that is the layer
   order). **Reset** puts the source's own set back. The chip beside it says the window the field
   overlay will open at, so you can see the defaults before opening anything.
3. Press **Open in viewer** to prepare the scene and open the native TetraVox window. If it is
   not installed, use the installation control or **Settings → Viewer**, then open the scene.

Return to **Menu** to change the selection. The **Tetravox** sub-page can reopen the prepared
scene; subsequent opens replace the native window's current scene. In a narrow window, use the
command palette to reach `Viewer · Menu` or `Viewer · Tetravox`.

Layer visibility and opacity, the shared 3-D cursor, the slice/3-D layouts, screenshots and saving a
modified scene are all the viewer's own controls, in its own panels. TI-Toolbox's side of the
boundary ends at deciding which files belong together.

## The scene file

Opening also writes the scene into your project at `code/ti-toolbox/viewer/<type>.tetravox.json`.
It is an ordinary file — a few kilobytes, because every layer refers to a dataset by its path
rather than copying it — in `ViewSpec` v2, Tetravox's own format; TI-Toolbox invents no scene format
of its own. Keep it, archive it with the results it describes, or hand it to a Tetravox desktop
application through **File ▸ Open Scene…**. Dataset paths must resolve on that host machine.

## Saving what you chose, and saving what you saw

Two different things are worth keeping, and the Viewer keeps them separately because they answer
different questions.

**Save selection…** (under the list) writes a *composition* to
`code/ti-toolbox/viewer/compositions/<name>.json`: the subject, the space, and the inputs you
ticked, recorded by file name. It is small and readable, and it does not freeze the data — loading
it next month re-resolves those same choices against whatever is in the project then, and tells you
what has since gone missing rather than failing. Use it when the question is *"show me the same
thing, from the current data"* — the reproducibility artefact you would put next to a manuscript.

**Save scene** (in the **Tetravox** sub-page) writes the prepared composition to
`code/ti-toolbox/viewer/scenes/<name>.tetravox.json`. **Saved scenes** reopens these project files.
This action does not capture the camera or appearance edits made afterward in the native window,
and it does not capture a thumbnail from that window.

To preserve the view you adjusted, use **Save Scene** in native TetraVox and choose a location
inside the project. Scene files reference datasets rather than copying them, so keep the data
alongside the scene when archiving or moving it.

## Installing and updating the viewer

**Settings → Viewer** shows installation state and provides **Install TetraVox** and **Open
TetraVox**. TI-Toolbox installs the official **0.4.0** platform package in its per-user runtime
directory after SHA256 verification. The first installation needs network access; later launches
use the installed copy. There is no viewer bundle in the Docker image.

The pinned release predates TetraVox's new externally managed updater protection. Keep this copy
at TI-Toolbox's pinned version rather than updating it from TetraVox's own menu. See
[Desktop Application]({{ site.baseurl }}/wiki/desktop-app/#installing-and-managing-the-viewer)
for platform support, host permissions and browser-only operation.

## No-WebGL2 state

Both the run pages' pane and the viewer need WebGL2. On a host GPU/driver combination without it,
each says so explicitly rather than showing a blank canvas — on the run pages the rest of the page
keeps working, and every choice the pane offers (electrodes, atlas regions) is also available from
the form beside it. This is a host capability check, not a container one: it depends on what the
Electron renderer's GPU process can do on your machine. Native TetraVox reports its own GPU
availability separately; launching natively does not guarantee WebGL2 support on every driver.

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

- **Location**: `derivatives/SimNIBS/sub-{ID}/Simulations/{sim_name}/Analyses/Mesh/{analysis_name}/`,
  and the head model itself at `derivatives/SimNIBS/sub-{ID}/m2m_{ID}/{ID}.msh`
- **Content**: Tetrahedral mesh with embedded field data — the FEM domain, 24–420 MB

### Surface Files (.gii, FreeSurfer binaries)

- **Location**: `derivatives/SimNIBS/sub-{ID}/m2m_{ID}/surfaces/` (`lh.central.gii`, `lh.pial.gii`,
  `lh.white.gii` and the right-hemisphere pair), and `derivatives/freesurfer/sub-{ID}/surf/`
- **Content**: A triangulated 2-D sheet — vertices and faces, and nothing else. Not a mesh: there
  are no tetrahedra and no field on it.

### Surface Attachments (.annot, morph curves, data GIfTI)

- **Location**: `derivatives/SimNIBS/sub-{ID}/m2m_{ID}/segmentation/` (`lh.{ID}_DK40.annot`,
  `lh.{ID}_HCP_MMP1.annot`, `lh.{ID}_a2009s.annot` and their right-hemisphere pairs), and
  `derivatives/freesurfer/sub-{ID}/surf/` (`lh.thickness`, `lh.curv`, `lh.sulc`, `lh.area`)
- **Content**: One value per vertex of the surfaces of the same hemisphere — a region id for an
  `.annot`, a number for a morph curve. They carry no geometry, so they are only ever opened
  *attached to* a surface, never on their own.

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
