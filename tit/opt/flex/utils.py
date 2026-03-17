#!/usr/bin/env simnibs_python
"""ROI configuration and output naming for flex-search."""

import logging
import os

log = logging.getLogger(__name__)

from tit.opt.config import FlexConfig

# ---------------------------------------------------------------------------
# Output directory naming
# ---------------------------------------------------------------------------


def generate_run_dirname(base_path: str) -> str:
    """Generate a datetime-based directory name for a flex-search run.

    Format: YYYYMMDD_HHMMSS. Appends _1, _2, etc. if the folder already exists.

    Args:
        base_path: Parent directory (e.g. flex-search/) to check for collisions.

    Returns:
        Directory name string (not full path).
    """
    from datetime import datetime

    name = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not os.path.exists(os.path.join(base_path, name)):
        return name
    suffix = 1
    while os.path.exists(os.path.join(base_path, f"{name}_{suffix}")):
        suffix += 1
    return f"{name}_{suffix}"


def generate_label(config, pareto: bool = False) -> str:
    """Build a human-readable label for a flex-search run.

    This label is stored in flex_meta.json for GUI display purposes.
    It is NOT used for folder naming or machine parsing.

    Args:
        config: FlexConfig instance.
        pareto: True if this is a pareto sweep run.

    Returns:
        Label string like "mean_maxTI_sphere(-42,-20,55)r10".
    """
    postproc_short = {
        "max_TI": "maxTI",
        "dir_TI_normal": "normalTI",
        "dir_TI_tangential": "tangentialTI",
    }
    pp = postproc_short.get(
        (
            config.postproc.value
            if hasattr(config.postproc, "value")
            else str(config.postproc)
        ),
        str(config.postproc),
    )

    goal_str = (
        "pareto"
        if pareto
        else (config.goal.value if hasattr(config.goal, "value") else str(config.goal))
    )

    roi = config.roi
    if isinstance(roi, FlexConfig.SphericalROI):
        x = int(roi.x) if roi.x == int(roi.x) else roi.x
        y = int(roi.y) if roi.y == int(roi.y) else roi.y
        z = int(roi.z) if roi.z == int(roi.z) else roi.z
        r = int(roi.radius) if roi.radius == int(roi.radius) else roi.radius
        roi_str = f"sphere({x},{y},{z})r{r}"
    elif isinstance(roi, FlexConfig.AtlasROI):
        hemi = roi.hemisphere
        atlas = (
            os.path.basename(roi.atlas_path).replace(".annot", "").split(".")[-1]
            if roi.atlas_path
            else "atlas"
        )
        roi_str = f"{hemi}-{atlas}-{roi.label}"
    elif isinstance(roi, FlexConfig.SubcorticalROI):
        atlas = os.path.basename(roi.atlas_path) if roi.atlas_path else "volume"
        for ext in (".nii.gz", ".nii", ".mgz"):
            if atlas.endswith(ext):
                atlas = atlas[: -len(ext)]
                break
        roi_str = f"subcortical-{atlas}-{roi.label}"
    else:
        roi_str = "unknown"

    return f"{goal_str}_{pp}_{roi_str}"


def parse_optimization_output(line: str) -> float | None:
    """Extract the optimization function value from a SimNIBS log line.

    Handles patterns:
        - "Final goal function value:   -42.123"
        - "Goal function value.*:  -42.123"
        - Table row with max_TI column (scientific notation)

    Args:
        line: A single line of SimNIBS stdout/stderr.

    Returns:
        The function value as a float, or None if the line does not match.
    """
    import re

    # Primary: "Final goal function value: <number>"
    m = re.search(
        r"Final goal function value:\s*([+-]?[\d.eE+-]+)", line, re.IGNORECASE
    )
    if m:
        return float(m.group(1))

    # Secondary: "Goal function value<anything>: <number>"
    m = re.search(r"Goal function value[^:]*:\s*([+-]?[\d.eE+-]+)", line, re.IGNORECASE)
    if m:
        return float(m.group(1))

    # Table row: "|max_TI | 0.025" or "max_TI | 0.025e-03"
    m = re.search(r"\|?\s*max_TI\s+\|\s*([\d.+-]+)(?:e([+-]?\d+))?", line)
    if m:
        base = float(m.group(1))
        exp = int(m.group(2)) if m.group(2) else 0
        val = base * (10**exp)
        if val > 0:
            return val

    return None


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
    if isinstance(config.roi, FlexConfig.SphericalROI):
        _configure_spherical_roi(opt, config)
    elif isinstance(config.roi, FlexConfig.AtlasROI):
        _configure_atlas_roi(opt, config)
    elif isinstance(config.roi, FlexConfig.SubcorticalROI):
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

    roi_spec: FlexConfig.SphericalROI = config.roi  # type: ignore[assignment]

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
        subject_coords = mni2subject_coords([roi_x, roi_y, roi_z], opt.subpath)
        roi.roi_sphere_center = subject_coords
        log.info(f"Transformed coordinates: {subject_coords}")
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
            non_roi_spec: FlexConfig.SphericalROI = config.non_roi  # type: ignore[assignment]
            nx = non_roi_spec.x
            ny = non_roi_spec.y
            nz = non_roi_spec.z
            nr = non_roi_spec.radius

            if non_roi_spec.use_mni:
                log.info(
                    f"Transforming non-ROI MNI coordinates [{nx}, {ny}, {nz}] to subject space"
                )
                non_roi_subject_coords = mni2subject_coords([nx, ny, nz], opt.subpath)
                non_roi.roi_sphere_center = non_roi_subject_coords
                log.info(f"Transformed non-ROI coordinates: {non_roi_subject_coords}")
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
    roi_spec: FlexConfig.AtlasROI = config.roi  # type: ignore[assignment]

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
            non_roi_spec: FlexConfig.AtlasROI = config.non_roi  # type: ignore[assignment]
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

    roi_spec: FlexConfig.SubcorticalROI = config.roi  # type: ignore[assignment]
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
    roi_spec: FlexConfig.SubcorticalROI = config.roi  # type: ignore[assignment]

    volume_atlas_path = roi_spec.atlas_path
    label_val = roi_spec.label

    if not volume_atlas_path or not os.path.isfile(volume_atlas_path):
        raise FileNotFoundError(f"Volume atlas file not found: {volume_atlas_path}")

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
            non_roi_spec: FlexConfig.SubcorticalROI = config.non_roi  # type: ignore[assignment]
            if not non_roi_spec.atlas_path or not os.path.isfile(
                non_roi_spec.atlas_path
            ):
                raise FileNotFoundError(
                    f"Non-ROI volume atlas not found: {non_roi_spec.atlas_path}"
                )
            non_roi.mask_space = ["subject"]
            non_roi.mask_path = [non_roi_spec.atlas_path]
            non_roi.mask_value = [non_roi_spec.label]
            non_roi.weight = -1
            non_roi.tissues = tissues
