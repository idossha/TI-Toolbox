"""Standalone utilities for mesh, field, and electrode manipulation.

This package collects lightweight helper scripts that are typically
invoked from the command line or called by higher-level pipeline
stages.  Heavy dependencies (SimNIBS, nibabel, scipy) are imported
lazily inside each module so that ``import tit.tools`` remains fast.

Modules
-------
check_for_update
    Query the GitHub API for new TI-Toolbox releases.
extract_labels
    Extract specific label values from a NIfTI segmentation.
field_extract
    Crop grey- and white-matter meshes from a SimNIBS head mesh.
gmsh_opt
    Generate Gmsh ``.opt`` visualization option files.
map_electrodes
    Map optimised electrode positions to the nearest EEG net electrodes.
mesh2nii
    Convert SimNIBS meshes to subject- and MNI-space NIfTI volumes.
montage_visualizer
    Render PNG images of electrode montages on an EEG cap template.
nifti_to_mesh
    Convert a NIfTI segmentation/mask to an STL or Gmsh surface mesh.
read_annot
    Read and display FreeSurfer ``.annot`` annotation files.
"""
