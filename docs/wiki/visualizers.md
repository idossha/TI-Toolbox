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
4. **Select Analysis**: Choose the specific analysis (e.g., "E", "normE", "E_diff")
5. **Launch Gmsh**: Click the **"Launch Gmsh"** button

The system will automatically:
- Locate the appropriate .msh file in your project's `Analyses/Mesh/` directory
- Launch Gmsh with the correct file path
- Display the mesh with electric field data

### Gmsh Tips

- **Navigation**: Use mouse to rotate, zoom, and pan the 3D view
- **Field Visualization**: Electric field magnitude is typically displayed as surface colors
- **Mesh Quality**: You can inspect mesh element quality and density
- **Export**: Gmsh allows exporting images and animations for reports

## Freeview NIfTI Visualizer

Freeview is used to visualize volumetric NIfTI files (.nii/.nii.gz) and provides comprehensive brain imaging capabilities including:
- Anatomical MRI visualization
- Electric field overlays on brain anatomy
- Atlas-based region of interest (ROI) visualization
- Multi-subject comparison views
- Statistical overlay maps

### How to Use Freeview

1. **Navigate to NIfTI Viewer**: Click on the **"NIfTI Viewer"** tab in the main TI-Toolbox GUI
2. **Select Visualization Mode**:
   - **Single Subject**: Visualize one subject at a time
   - **Group Mode**: Compare multiple subjects simultaneously

#### Single Subject Mode

1. **Select Subject**: Choose from available subjects
2. **Select Simulation**: Choose the simulation to visualize
3. **Select Analysis**: Choose the analysis type (e.g., E-field magnitude)
4. **Configure Visualization**:
   - **Colormap**: Choose color scheme (e.g., heat, jet, plasma)
   - **Thresholds**: Set minimum and maximum values for display
   - **Opacity**: Control overlay transparency
   - **Atlas Overlay**: Add anatomical atlas labels
5. **Launch Freeview**: Click **"Launch Freeview"**

#### Group Mode

1. **Add Subjects**: Click **"Add Subject"** to include multiple subjects
2. **Configure Each Subject**: Set visualization parameters for each
3. **Launch Freeview**: Click **"Launch Freeview"** to view all subjects simultaneously

### Freeview Tips

- **Navigation**: Use mouse controls to navigate 3D brain space
- **Slices**: Toggle between axial, coronal, and sagittal views
- **ROI Analysis**: Use atlas overlays to identify brain regions
- **Measurements**: Freeview provides tools for measuring distances and volumes
- **Screenshots**: Capture images for documentation and reports

## File Formats and Locations

### Mesh Files (.msh)
- **Location**: `project_dir/subjects/sub-{ID}/simulations/{sim_name}/Analyses/Mesh/{analysis_name}/`
- **Content**: Tetrahedral mesh with embedded field data
- **Visualizer**: Gmsh

### NIfTI Files (.nii/.nii.gz)
- **Location**: `project_dir/subjects/sub-{ID}/simulations/{sim_name}/Analyses/Voxel/{analysis_name}/`
- **Content**: Volumetric data in standard neuroimaging format
- **Visualizer**: Freeview

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

## Gallery

For visual examples of Gmsh and Freeview outputs, see the [Gmsh Freeview Gallery](/gallery/gmsh-freeview/) page.

---

*Note: Both Gmsh and Freeview are external applications that must be installed separately from the TI-Toolbox. The toolbox provides convenient launchers but does not include the visualization software itself.*
