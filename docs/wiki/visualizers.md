---
layout: wiki
title: Visualizers
permalink: /wiki/visualizers/
---

The TI-Toolbox provides integrated visualization tools for examining simulation results in both mesh and NIfTI formats. Two primary visualization applications are available: **Gmsh** for mesh visualization and **Freeview** for NIfTI volume visualization.

## Gmsh Mesh Visualizer

Gmsh is used to visualize tetrahedral mesh files (.msh) generated during finite element simulations. It provides 3D visualization of:

- Mesh geometry and tetrahedral elements
- Electric field distributions on mesh surfaces
- Tissue boundaries and material interfaces
- Electrode positions and configurations

### How to Use Gmsh

1. **From the Analyzer Tab**: Navigate to the **Analyzer** tab in the main TI-Toolbox GUI
2. **Select Subject**: Choose the subject you want to visualize from the dropdown
3. **Select Simulation**: Choose the simulation containing the analysis results
4. **Select Analysis**: Choose the specific analysis
5. **Launch Gmsh**: Click the **"Launch Gmsh"** button

The system will automatically:

- Locate the .msh file under `derivatives/SimNIBS/sub-{ID}/Simulations/{sim}/Analyses/Mesh/{analysis}/`
- Launch Gmsh with the correct file path
- Display the mesh with electric field data

![Gmsh Launching]({{ site.baseurl }}/assets/imgs/visualizers/gmsh_launching.png)
\_Gmsh launching with mesh visualization*

### Gmsh Interface and Tools

Gmsh provides several menu options for enhanced visualization:
![Gmsh Tools Menu]({{ site.baseurl }}/assets/imgs/visualizers/gmsh_tools_menu.png)
\_Gmsh tools menu. Useful for clipping mesh, changing visibility of elements and manipulating general options.*

![Gmsh Options Menu]({{ site.baseurl }}/assets/imgs/visualizers/gmsh_options_menu.png)
\_Gmsh options menu for view controls. Useful for changing color schemes, visualization cutoffs, mesh settings and more*

### Gmsh Tips

- **Navigation**: Use mouse to rotate, zoom, and pan the 3D view
- **Field Visualization**: Electric field magnitude is typically displayed as surface colors
- **Mesh Quality**: You can inspect mesh element quality and density
- **Export**: Gmsh allows exporting images and animations for reports

For more information please visit the following resources:

- [SimNIBS Gmsh Explanation](https://simnibs.github.io/simnibs/build/html/tutorial/visualization.html)
- [Gmsh Website](https://gmsh.info/)

---

## Freeview NIfTI Visualizer

Freeview is used to visualize volumetric NIfTI files (.nii/.nii.gz) and provides comprehensive brain imaging capabilities including:

- Anatomical MRI visualization
- Electric field overlays on brain anatomy
- Atlas-based region of interest (ROI) visualization
- Multi-subject comparison views
- Statistical overlay maps

The TI-Toolbox's NIfTI Viewer tab automates multi-layer visualization with sensible defaults including percentile-based thresholding (95th-99.9th percentile), opacity controls (70% default), automatic loading of anatomical atlases, and optional electrode-placement overlays.

### How to Use Freeview

1. **Navigate to NIfTI Viewer**: Click on the **"NIfTI Viewer"** tab in the main TI-Toolbox GUI
2. **Select Visualization Mode**:
   - **Single Subject**: Visualize one subject at a time
   - **Group Mode**: Compare multiple subjects simultaneously in MNI space

#### Single Subject Mode

1. **Select Subject**: Choose from available subjects
2. **Select Simulation**: Choose the simulation to visualize
3. **Select Analysis**: Choose the analysis type (e.g., E-field magnitude)
4. **Configure Visualization**:
   - **Colormap**: Choose color scheme (e.g., heat, jet, plasma)
   - **Thresholds**: Set minimum and maximum values for display
   - **Opacity**: Control overlay transparency
   - **Atlas Overlay**: Add anatomical atlas labels
   - **Electrode Overlay**: Create or load the selected simulation's electrode-placement label mask
5. **Launch Freeview**: Click **"Launch Freeview"**

![Freeview Menu]({{ site.baseurl }}/assets/imgs/visualizers/freeview_menu.png)
\_Freeview menu showing overlay controls and atlas options*

![Freeview Example]({{ site.baseurl }}/assets/imgs/visualizers/freeview_example.png)
\_Freeview displaying E-field overlay on anatomical MRI*

![MRI ROI with Field]({{ site.baseurl }}/assets/imgs/visualizers/visualizer_MRI_ROI_field.png)
\_MRI ROI with field data overlay*

### Freeview Tips

- **Navigation**: Use mouse controls to navigate 3D brain space
- **Slices**: Toggle between axial, coronal, and sagittal views
- **ROI Analysis**: Use atlas overlays to identify brain regions
- **Measurements**: Freeview provides tools for measuring distances and volumes
- **Screenshots**: Capture images for documentation and reports
- **Multi-Layer Control**: Use the overlay panel to toggle visibility and adjust opacity of different data layers

---

### Electrode Placement NIfTI Overlay

The NIfTI Viewer can create a single binary label-mask NIfTI that shows where electrodes were placed on the subject anatomy. The overlay is loaded automatically when it already exists for the selected simulation.

- **UI location**: Single Subject mode, under the atlas controls in the Subject Configuration box.
- **Create/refresh**: Click **Create Electrode Overlay** or **Refresh Electrode Overlay**.
- **Source of truth**: The overlay reads electrode coordinates, channel grouping, dimensions, and simulation mode from the saved simulation config.
- **Coloring**: Labels are channel-based, not electrode-based. Unipolar simulations use two channel colors; multipolar simulations use four channel colors. The color order matches the montage PNG overlay: blue, red, green, purple, then the remaining montage colors if needed.
- **Output path**: `Simulations/{simulation}/TI/montage_imgs/electrode_overlay_subject.nii.gz` for TI/unipolar runs, or `Simulations/{simulation}/mTI/montage_imgs/electrode_overlay_subject.nii.gz` for mTI/multipolar runs.
- **Lookup table**: A matching `electrode_overlay_subject.lut` is saved next to the NIfTI so Freeview can show the channel colors.

---

## File Formats and Locations

### Mesh Files (.msh)

- **Location**: `derivatives/SimNIBS/sub-{ID}/Simulations/{sim_name}/Analyses/Mesh/{analysis_name}/`
- **Content**: Tetrahedral mesh with embedded field data
- **Visualizer**: Gmsh

### NIfTI Files (.nii/.nii.gz)

- **Location**: `derivatives/SimNIBS/sub-{ID}/Simulations/{sim_name}/Analyses/Voxel/{analysis_name}/`
- **Content**: Volumetric data in standard neuroimaging format
- **Visualizer**: Freeview

### Electrode Overlay Files (.nii/.nii.gz + .lut)

- **Location**: `derivatives/SimNIBS/sub-{ID}/Simulations/{sim_name}/{TI|mTI}/montage_imgs/electrode_overlay_subject.nii.gz`
- **Content**: Channel-labeled electrode placement mask plus a Freeview LUT
- **Visualizer**: Freeview

---

## Quick CLI Commands

For users who prefer command-line access or need to integrate visualization into scripts, you can launch the visualizers directly:

### Gmsh CLI

```bash
# Basic mesh visualization
gmsh path/to/your/mesh.msh

# Examples with typical TI-Toolbox paths:
gmsh derivatives/SimNIBS/sub-ernie/Simulations/L_Insula/TI/mesh/L_Insula_TI.msh
gmsh derivatives/SimNIBS/sub-ernie/Simulations/L_Insula/Analyses/Mesh/insula_roi/L_Insula_TI_insula_roi.msh
```

### Freeview CLI

```bash
# Basic NIfTI visualization
freeview path/to/your/file.nii.gz

# Multiple files with overlay options
freeview anatomical.nii.gz field_overlay.nii.gz:colormap=heat:opacity=0.7 atlas.nii.gz:lut=atlas_labels.txt

# Examples with typical TI-Toolbox paths:
freeview derivatives/SimNIBS/sub-ernie/Simulations/L_Insula/TI/niftis/L_Insula_TI_subject_TI_max.nii.gz:colormap=plasma:opacity=0.8
freeview derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz derivatives/SimNIBS/sub-ernie/Simulations/L_Insula/TI/niftis/L_Insula_TI_subject_TI_max.nii.gz:colormap=heat:opacity=0.7:percentile=1
```

**Note**: Freeview supports advanced options like colormaps, opacity, thresholds, and atlas overlays. Use `:colormap=heat`, `:opacity=0.7`, `:percentile=1`, etc.

---

## Troubleshooting

### Gmsh Issues

**No mesh files found**

- Ensure the analysis has been run and completed
- Check that the analysis output includes mesh visualization files

### Freeview Issues

**Empty or incorrect visualization**

- Check that NIfTI files exist in the expected location
- Verify analysis parameters and thresholds are appropriate
- Ensure atlas files are available if using atlas overlays

## Integration with Analysis Pipeline

Both visualizers are designed to work seamlessly with the TI-Toolbox analysis pipeline:

1. **Run Simulations**: Use Flex Search or Ex Search to generate simulation parameters
2. **Execute Analysis**: Run the analyzer to generate field distributions
3. **Visualize Results**: Launch appropriate visualizer based on data type (mesh vs. voxel)
4. **Iterate**: Use visualization insights to refine simulation parameters

---

_Note: Both Gmsh (bundled with SimNIBS) and Freeview (bundled with FreeSurfer) ship inside the TI-Toolbox container; the toolbox launches them for you. If you run the `tit` package outside the container you must install them yourself._
