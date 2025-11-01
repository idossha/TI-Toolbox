#!/usr/bin/env simnibs_python
"""ROI (Region of Interest) configuration module for flex-search.

This module handles ROI setup for different methods:
- Spherical ROIs with optional MNI coordinate transformation
- Atlas-based cortical ROIs
- Subcortical volume ROIs
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from simnibs import mni2subject_coords
from simnibs.mesh_tools.mesh_io import ElementTags

if TYPE_CHECKING:
    import argparse
    from simnibs import opt_struct

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


def roi_dirname(args: argparse.Namespace) -> str:
    """Generate output directory name following the naming convention.
    
    Naming conventions:
    - Atlas: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
    - Spherical: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
    - Subcortical: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Directory name string
    """
    # Convert postproc to shorter format
    postproc_map = {
        "max_TI": "maxTI",
        "dir_TI_normal": "normalTI", 
        "dir_TI_tangential": "tangentialTI"
    }
    postproc_short = postproc_map.get(args.postproc, args.postproc)
    
    if args.roi_method == "spherical":
        # Format: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
        roi_x = os.getenv('ROI_X', '0')
        roi_y = os.getenv('ROI_Y', '0') 
        roi_z = os.getenv('ROI_Z', '0')
        roi_radius = os.getenv('ROI_RADIUS', '10')
        base = f"sphere_x{roi_x}y{roi_y}z{roi_z}r{roi_radius}"
    elif args.roi_method == "atlas":
        # Format: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
        atlas_path = os.getenv("ATLAS_PATH", "")
        hemisphere = os.getenv("SELECTED_HEMISPHERE", "lh")
        roi_label = os.getenv("ROI_LABEL", "0")
        
        # Extract atlas name from path (e.g., lh.101_DK40.annot -> DK40)
        if atlas_path:
            atlas_filename = os.path.basename(atlas_path)
            # Remove hemisphere prefix and .annot suffix, then extract atlas name
            # e.g., lh.101_DK40.annot -> 101_DK40 -> DK40
            atlas_with_subject = atlas_filename.replace(f"{hemisphere}.", "").replace(".annot", "")
            atlas_name = atlas_with_subject.split("_", 1)[-1] if "_" in atlas_with_subject else atlas_with_subject
        else:
            atlas_name = "atlas"
        
        base = f"{hemisphere}_{atlas_name}_{roi_label}"
    else:  # subcortical
        # Format: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
        volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
        roi_label = os.getenv("VOLUME_ROI_LABEL", "0")
        
        if volume_atlas_path:
            volume_atlas = os.path.basename(volume_atlas_path)
            # Remove file extensions
            if volume_atlas.endswith('.nii.gz'):
                volume_atlas = volume_atlas[:-7]
            elif volume_atlas.endswith('.mgz'):
                volume_atlas = volume_atlas[:-4]
            elif volume_atlas.endswith('.nii'):
                volume_atlas = volume_atlas[:-4]
        else:
            volume_atlas = "volume"
        
        base = f"subcortical_{volume_atlas}_{roi_label}"
    
    return f"{base}_{args.goal}_{postproc_short}"


def configure_spherical_roi(
    opt: opt_struct.TesFlexOptimization,
    args: argparse.Namespace
) -> None:
    """Configure spherical ROI with optional MNI coordinate transformation.
    
    Args:
        opt: SimNIBS optimization object
        args: Parsed command line arguments
    """
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    roi.roi_sphere_center_space = "subject"
    
    # Get coordinates from environment variables with proper defaults
    roi_x = float(os.getenv("ROI_X", "0"))
    roi_y = float(os.getenv("ROI_Y", "0"))
    roi_z = float(os.getenv("ROI_Z", "0"))
    radius = float(os.getenv("ROI_RADIUS", "10"))
    
    # Check if MNI coordinates should be used (for multiple subjects)
    use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
    
    if use_mni_coords:
        # Transform MNI coordinates to subject space
        print(f"[flex-search] Transforming MNI coordinates [{roi_x}, {roi_y}, {roi_z}] to subject space")
        try:
            # Use simnibs.mni2subject_coords to transform coordinates
            m2m_path = opt.subpath
            subject_coords = mni2subject_coords([roi_x, roi_y, roi_z], m2m_path)
            roi.roi_sphere_center = subject_coords
            print(f"[flex-search] Transformed coordinates: {subject_coords}")
        except Exception as e:
            print(f"[flex-search] ERROR: Failed to transform MNI coordinates to subject space: {e}")
            raise SystemExit(f"MNI coordinate transformation failed: {e}")
    else:
        # Use coordinates as-is (subject space)
        roi.roi_sphere_center = [roi_x, roi_y, roi_z]
    
    roi.roi_sphere_radius = radius

    # Add non-ROI if focality optimisation is requested
    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if args.non_roi_method == "everything_else":
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_center = roi.roi_sphere_center
            non_roi.roi_sphere_radius = radius
            non_roi.roi_sphere_operator = ["difference"]
            non_roi.weight = -1
        else:  # specific non-ROI defined via env vars
            # Get non-ROI coordinates with proper defaults
            nx = float(os.getenv("NON_ROI_X", "0"))
            ny = float(os.getenv("NON_ROI_Y", "0"))
            nz = float(os.getenv("NON_ROI_Z", "0"))
            nr = float(os.getenv("NON_ROI_RADIUS", "10"))
            
            # Check if non-ROI coordinates are also MNI
            use_mni_coords_non_roi = os.getenv("USE_MNI_COORDS_NON_ROI", "false").lower() == "true"
            
            if use_mni_coords_non_roi:
                # Transform non-ROI MNI coordinates to subject space
                print(f"[flex-search] Transforming non-ROI MNI coordinates [{nx}, {ny}, {nz}] to subject space")
                try:
                    m2m_path = opt.subpath
                    non_roi_subject_coords = mni2subject_coords([nx, ny, nz], m2m_path)
                    non_roi.roi_sphere_center = non_roi_subject_coords
                    print(f"[flex-search] Transformed non-ROI coordinates: {non_roi_subject_coords}")
                except Exception as e:
                    print(f"[flex-search] ERROR: Failed to transform non-ROI MNI coordinates to subject space: {e}")
                    raise SystemExit(f"Non-ROI MNI coordinate transformation failed: {e}")
            else:
                # Use non-ROI coordinates as-is (subject space)
                non_roi.roi_sphere_center = [nx, ny, nz]
            
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_radius = nr
            non_roi.weight = -1


def configure_atlas_roi(
    opt: opt_struct.TesFlexOptimization,
    args: argparse.Namespace
) -> None:
    """Configure cortical atlas-based ROI.
    
    Args:
        opt: SimNIBS optimization object
        args: Parsed command line arguments
    """
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    hemi = os.getenv("SELECTED_HEMISPHERE", "lh")
    roi.mask_space = [f"subject_{hemi}"]
    roi.mask_path = [os.getenv("ATLAS_PATH", "")]
    label_val = int(os.getenv("ROI_LABEL", "1"))
    roi.mask_value = [label_val]

    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if args.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]
            non_roi.weight = -1
        else:
            non_roi_label = int(os.getenv("NON_ROI_LABEL", "1"))
            non_roi_atlas_path = os.getenv("NON_ROI_ATLAS_PATH", "")
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = [non_roi_atlas_path]
            non_roi.mask_value = [non_roi_label]
            non_roi.weight = -1


def configure_subcortical_roi(
    opt: opt_struct.TesFlexOptimization,
    args: argparse.Namespace
) -> None:
    """Configure subcortical volume-based ROI.
    
    Args:
        opt: SimNIBS optimization object
        args: Parsed command line arguments
    """
    volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
    label_val = int(os.getenv("VOLUME_ROI_LABEL", "10"))
    
    # Validate that the volume atlas file exists
    if not volume_atlas_path or not os.path.isfile(volume_atlas_path):
        raise SystemExit(f"Volume atlas file not found: {volume_atlas_path}")
    
    roi = opt.add_roi()
    roi.method = "volume"
    roi.mask_space = ["subject"]
    roi.mask_path = [volume_atlas_path]
    roi.mask_value = [label_val]
    
    # Add some additional properties that might help with volume ROI processing
    roi.tissues = [ElementTags.GM]  # Gray matter tissue for volume ROI

    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "volume"

        if args.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]
            non_roi.weight = -1
            non_roi.tissues = [ElementTags.GM]  # Gray matter
        else:
            non_roi_label = int(os.getenv("VOLUME_NON_ROI_LABEL", "10"))
            non_roi_atlas_path = os.getenv("VOLUME_NON_ROI_ATLAS_PATH", "")
            if not non_roi_atlas_path or not os.path.isfile(non_roi_atlas_path):
                raise SystemExit(f"Non-ROI volume atlas file not found: {non_roi_atlas_path}")
            non_roi.mask_space = ["subject"]
            non_roi.mask_path = [non_roi_atlas_path]
            non_roi.mask_value = [non_roi_label]
            non_roi.weight = -1
            non_roi.tissues = [ElementTags.GM]  # Gray matter


def configure_roi(
    opt: opt_struct.TesFlexOptimization,
    args: argparse.Namespace
) -> None:
    """Configure ROI based on the specified method.
    
    This is the main entry point for ROI configuration that delegates to
    the appropriate method-specific function.
    
    Args:
        opt: SimNIBS optimization object
        args: Parsed command line arguments
    """
    if args.roi_method == "spherical":
        configure_spherical_roi(opt, args)
    elif args.roi_method == "atlas":
        configure_atlas_roi(opt, args)
    else:  # subcortical
        configure_subcortical_roi(opt, args)

