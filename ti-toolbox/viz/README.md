# TI-Toolbox Visualization Tools

This directory contains the main visualization scripts for creating publication-ready images and interactive HTML reports from TES simulation results.

## Scripts

### `img_slices.py`
Creates publication-ready PDF visualizations with multiple surface views and atlas contours.

**Usage:**
```bash
python img_slices.py --subject 001 --simulation montage1
python img_slices.py --subject 001 --simulation montage1 --cutoff 0.5 --atlas aal
```

**Options:**
- `--subject, -s`: Subject ID (required)
- `--simulation, -sim`: Simulation name (required)
- `--cutoff, -c`: Minimum cutoff for visualization in V/m (default: 0.3)
- `--atlas, -a`: Atlas for contour overlay (default: harvard_oxford_sub)
  - Choices: harvard_oxford, harvard_oxford_sub, aal, schaefer_2018

**Output:**
- PDF file saved to `derivatives/nilearn_visuals/`
- Multiple surface views (sagittal, coronal, axial) with atlas contours
- Colorbar showing electric field intensity range

### `html_report.py`
Creates interactive HTML visualizations for 3D exploration.

**Usage:**
```bash
python html_report.py --subject 001 --simulation montage1
python html_report.py --subject 001 --simulation montage1 --cutoff 0.5
```

**Options:**
- `--subject, -s`: Subject ID (required)
- `--simulation, -sim`: Simulation name (required)
- `--cutoff, -c`: Minimum cutoff for visualization in V/m (default: 0.3)

**Output:**
- Interactive HTML file saved to `derivatives/nilearn_visuals/`
- 3D surface visualization with plotly
- Zoomable and rotatable views

## GUI Integration

Both visualization tools are also available through the TI-Toolbox GUI via the "Publication Image Generator" extension in the Extensions tab.

## Requirements

- Nilearn
- NiBabel
- Matplotlib
- Plotly (for HTML reports)
- NumPy

## Architecture

- `core/viz.py`: Contains the `NilearnVisualizer` class with core visualization methods
- `viz/img_slices.py`: PDF publication script (calls core methods)
- `viz/html_report.py`: HTML interactive report script (calls core methods)
- `gui/extensions/publication_img.py`: GUI extension for both visualization types

## File Organization

Visualizations are automatically saved to:
```
project/
├── derivatives/
│   └── nilearn_visuals/
│       ├── {subject}_{simulation}_multiple_views.pdf
│       └── {subject}_{simulation}_interactive.html
```

## Atlas Options

- `harvard_oxford_sub`: Harvard Oxford Subcortical Atlas (recommended)
- `harvard_oxford`: Harvard Oxford Cortical Atlas
- `aal`: Automated Anatomical Labeling Atlas
- `schaefer_2018`: Schaefer 2018 Atlas (100 regions)
