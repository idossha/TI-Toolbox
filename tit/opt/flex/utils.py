#!/usr/bin/env simnibs_python
"""ROI configuration and output naming for flex-search."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

from tit.opt.config import (
    AtlasROI,
    FlexConfig,
    SphericalROI,
    SubcorticalROI,
)

# ---------------------------------------------------------------------------
# Output directory naming
# ---------------------------------------------------------------------------


def roi_dirname(config: FlexConfig) -> str:
    """Generate output directory name following the naming convention.

    Naming conventions:
    - Atlas: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
    - Spherical: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
    - Subcortical: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}

    Args:
        config: Flex-search configuration object.

    Returns:
        Directory name string.
    """
    postproc_map = {
        "max_TI": "maxTI",
        "dir_TI_normal": "normalTI",
        "dir_TI_tangential": "tangentialTI",
    }
    postproc_short = postproc_map.get(config.postproc, config.postproc)

    roi = config.roi
    if isinstance(roi, SphericalROI):
        x = _num_str(roi.x)
        y = _num_str(roi.y)
        z = _num_str(roi.z)
        r = _num_str(roi.radius)
        base = f"sphere_x{x}y{y}z{z}r{r}"
    elif isinstance(roi, AtlasROI):
        atlas_path = roi.atlas_path
        hemisphere = roi.hemisphere

        if atlas_path:
            atlas_filename = os.path.basename(atlas_path)
            atlas_with_subject = atlas_filename.replace(f"{hemisphere}.", "").replace(
                ".annot", ""
            )
            atlas_name = (
                atlas_with_subject.split("_", 1)[-1]
                if "_" in atlas_with_subject
                else atlas_with_subject
            )
        else:
            atlas_name = "atlas"

        base = f"{hemisphere}_{atlas_name}_{roi.label}"
    elif isinstance(roi, SubcorticalROI):
        volume_atlas_path = roi.atlas_path

        if volume_atlas_path:
            volume_atlas = os.path.basename(volume_atlas_path)
            if volume_atlas.endswith(".nii.gz"):
                volume_atlas = volume_atlas[:-7]
            elif volume_atlas.endswith(".mgz"):
                volume_atlas = volume_atlas[:-4]
            elif volume_atlas.endswith(".nii"):
                volume_atlas = volume_atlas[:-4]
        else:
            volume_atlas = "volume"

        base = f"subcortical_{volume_atlas}_{roi.label}"
    else:
        raise ValueError(f"Unknown ROI type: {type(roi)}")

    return f"{base}_{config.goal}_{postproc_short}"


def _num_str(v: float) -> str:
    """Format a number as its shortest string representation.

    Produces integer-style strings for whole numbers (e.g. ``-50``, ``0``)
    and decimal strings otherwise (e.g. ``3.5``).
    """
    return str(int(v)) if v == int(v) else str(v)


# ---------------------------------------------------------------------------
# ROI configuration on SimNIBS optimization objects
# ---------------------------------------------------------------------------


def configure_roi(opt, config: FlexConfig) -> None:
    """Configure ROI based on the config's ROI specification.

    This is the main entry point for ROI configuration that delegates to
    the appropriate method-specific function.

    Args:
        opt: SimNIBS ``TesFlexOptimization`` object.
        config: Flex-search configuration with ROI spec.
    """
    if isinstance(config.roi, SphericalROI):
        _configure_spherical_roi(opt, config)
    elif isinstance(config.roi, AtlasROI):
        _configure_atlas_roi(opt, config)
    elif isinstance(config.roi, SubcorticalROI):
        _configure_subcortical_roi(opt, config)
    else:
        raise ValueError(f"Unknown ROI type: {type(config.roi)}")


def _configure_spherical_roi(opt, config: FlexConfig) -> None:
    """Configure spherical ROI with optional MNI coordinate transformation.

    Args:
        opt: SimNIBS optimization object.
        config: Flex-search configuration with SphericalROI spec.
    """
    from simnibs import mni2subject_coords

    roi_spec: SphericalROI = config.roi  # type: ignore[assignment]

    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    roi.roi_sphere_center_space = "subject"

    roi_x = roi_spec.x
    roi_y = roi_spec.y
    roi_z = roi_spec.z
    radius = roi_spec.radius

    if roi_x == 0.0 and roi_y == 0.0 and roi_z == 0.0 and not roi_spec.use_mni:
        log.warning(
            "ROI center coordinates are (0, 0, 0) in subject space. "
            "This position is typically outside the brain mesh and the optimization will fail. "
            "Set ROI coordinates to valid brain coordinates, or enable MNI coordinate mode."
        )

    if roi_spec.use_mni:
        log.info(
            f"Transforming MNI coordinates [{roi_x}, {roi_y}, {roi_z}] to subject space"
        )
        try:
            m2m_path = opt.subpath
            subject_coords = mni2subject_coords([roi_x, roi_y, roi_z], m2m_path)
            roi.roi_sphere_center = subject_coords
            log.info(f"Transformed coordinates: {subject_coords}")
        except Exception as e:
            log.error(f"Failed to transform MNI coordinates to subject space: {e}")
            raise SystemExit(f"MNI coordinate transformation failed: {e}")
    else:
        roi.roi_sphere_center = [roi_x, roi_y, roi_z]

    roi.roi_sphere_radius = radius

    # Add non-ROI if focality optimisation is requested
    if config.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if config.non_roi_method == "everything_else":
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_center = roi.roi_sphere_center
            non_roi.roi_sphere_radius = radius
            non_roi.roi_sphere_operator = ["difference"]
            non_roi.weight = -1
        else:
            # Specific non-ROI from config.non_roi (unified ROISpec type)
            non_roi_spec: SphericalROI = config.non_roi  # type: ignore[assignment]
            nx = non_roi_spec.x
            ny = non_roi_spec.y
            nz = non_roi_spec.z
            nr = non_roi_spec.radius

            if non_roi_spec.use_mni:
                log.info(
                    f"Transforming non-ROI MNI coordinates [{nx}, {ny}, {nz}] to subject space"
                )
                try:
                    m2m_path = opt.subpath
                    non_roi_subject_coords = mni2subject_coords([nx, ny, nz], m2m_path)
                    non_roi.roi_sphere_center = non_roi_subject_coords
                    log.info(
                        f"Transformed non-ROI coordinates: {non_roi_subject_coords}"
                    )
                except Exception as e:
                    log.error(
                        f"Failed to transform non-ROI MNI coordinates to subject space: {e}"
                    )
                    raise SystemExit(
                        f"Non-ROI MNI coordinate transformation failed: {e}"
                    )
            else:
                non_roi.roi_sphere_center = [nx, ny, nz]

            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_radius = nr
            non_roi.weight = -1


def _configure_atlas_roi(opt, config: FlexConfig) -> None:
    """Configure cortical atlas-based ROI.

    Args:
        opt: SimNIBS optimization object.
        config: Flex-search configuration with AtlasROI spec.
    """
    roi_spec: AtlasROI = config.roi  # type: ignore[assignment]

    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    hemi = roi_spec.hemisphere
    roi.mask_space = [f"subject_{hemi}"]
    roi.mask_path = [roi_spec.atlas_path]
    roi.mask_value = [roi_spec.label]

    if config.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if config.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]
            non_roi.weight = -1
        else:
            non_roi_spec: AtlasROI = config.non_roi  # type: ignore[assignment]
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = [non_roi_spec.atlas_path]
            non_roi.mask_value = [non_roi_spec.label]
            non_roi.weight = -1


def _resolve_roi_tissues(config: FlexConfig) -> list:
    """Resolve tissue tags from the ROI specification.

    Reads the ``tissues`` field from a SubcorticalROI config.
    Defaults to Gray Matter only when unset or unrecognised.

    Args:
        config: Flex-search configuration with SubcorticalROI spec.

    Returns:
        List of ElementTags values to assign to ``roi.tissues``.
    """
    from simnibs.mesh_tools.mesh_io import ElementTags

    roi_spec: SubcorticalROI = config.roi  # type: ignore[assignment]
    value = roi_spec.tissues.strip().upper()
    if value == "WM":
        return [ElementTags.WM]
    if value == "BOTH":
        return [ElementTags.WM, ElementTags.GM]
    return [ElementTags.GM]


def _configure_subcortical_roi(opt, config: FlexConfig) -> None:
    """Configure subcortical volume-based ROI.

    Args:
        opt: SimNIBS optimization object.
        config: Flex-search configuration with SubcorticalROI spec.
    """
    roi_spec: SubcorticalROI = config.roi  # type: ignore[assignment]

    volume_atlas_path = roi_spec.atlas_path
    label_val = roi_spec.label

    if not volume_atlas_path or not os.path.isfile(volume_atlas_path):
        raise SystemExit(f"Volume atlas file not found: {volume_atlas_path}")

    tissues = _resolve_roi_tissues(config)

    roi = opt.add_roi()
    roi.method = "volume"
    roi.mask_space = ["subject"]
    roi.mask_path = [volume_atlas_path]
    roi.mask_value = [label_val]
    roi.tissues = tissues

    if config.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "volume"

        if config.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]
            non_roi.weight = -1
            non_roi.tissues = tissues
        else:
            non_roi_spec: SubcorticalROI = config.non_roi  # type: ignore[assignment]
            if not non_roi_spec.atlas_path or not os.path.isfile(
                non_roi_spec.atlas_path
            ):
                raise SystemExit(
                    f"Non-ROI volume atlas file not found: {non_roi_spec.atlas_path}"
                )
            non_roi.mask_space = ["subject"]
            non_roi.mask_path = [non_roi_spec.atlas_path]
            non_roi.mask_value = [non_roi_spec.label]
            non_roi.weight = -1
            non_roi.tissues = tissues


# ---------------------------------------------------------------------------
# Atlas discovery (used by GUI -- signature unchanged)
# ---------------------------------------------------------------------------


def find_subject_atlases(
    subject_id: str, hemisphere: str, project_dir: str = None
) -> Dict[str, str]:
    """Find available atlas files for a subject and return atlas_name -> file_path mapping.

    Args:
        subject_id: Subject ID (e.g., '001')
        hemisphere: Hemisphere ('lh' or 'rh')
        project_dir: Project directory path (defaults to PathManager)

    Returns:
        Dictionary mapping atlas names (e.g., 'DK40') to file paths
    """
    if project_dir is None:
        from tit.core import get_path_manager

        pm = get_path_manager()
        project_dir = pm.project_dir
    if not project_dir:
        raise ValueError(
            "Project directory is not set. Set PROJECT_DIR or PROJECT_DIR_NAME."
        )

    atlas_map = {}

    # Primary: SimNIBS segmentation directory (same as GUI)
    seg_dir = (
        Path(project_dir)
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / f"m2m_{subject_id}"
        / "segmentation"
    )
    if seg_dir.is_dir():
        # Look for files with hemisphere prefix: lh.atlas_name.annot, rh.atlas_name.annot
        pattern = f"{hemisphere}.*.annot"
        for atlas_file in seg_dir.glob(pattern):
            fname = atlas_file.name
            # Extract atlas name from filename (e.g., lh.101_DK40.annot -> DK40)
            parts = fname.split(".")
            if len(parts) == 3 and parts[2] == "annot":
                atlas_full = parts[1]  # e.g., 101_DK40
                # Remove subjectID prefix for display
                atlas_display = (
                    atlas_full.split("_", 1)[-1] if "_" in atlas_full else atlas_full
                )
                atlas_map[atlas_display] = str(atlas_file)

    # Fallback: project-level bundled atlases
    atlas_dir = Path(project_dir) / "resources" / "atlas"
    if atlas_dir.is_dir():
        for atlas_file in atlas_dir.glob("*.annot"):
            atlas_name = atlas_file.stem  # Remove .annot extension
            if atlas_name not in atlas_map:  # Don't overwrite subject-specific atlases
                atlas_map[atlas_name] = str(atlas_file)

    return atlas_map


def list_atlas_regions(annot_path: str) -> List[Tuple[int, str]]:
    """List all regions in an atlas file.

    Args:
        annot_path: Path to the .annot file

    Returns:
        List of (region_index, region_name) tuples
    """
    import nibabel.freesurfer.io as fsio

    try:
        labels, ctab, names = fsio.read_annot(annot_path)
        regions = []
        for i, name in enumerate(names):
            region_name = name.decode("utf-8") if isinstance(name, bytes) else str(name)
            regions.append((i, region_name))
        return regions
    except Exception as e:
        raise RuntimeError(f"Failed to read atlas file {annot_path}: {e}")
