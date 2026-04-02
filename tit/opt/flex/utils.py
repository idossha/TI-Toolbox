#!/usr/bin/env simnibs_python
"""ROI configuration and output naming for flex-search.

Provides helper functions for directory naming, human-readable labelling,
SimNIBS log parsing, and ROI setup on ``TesFlexOptimization`` objects.

Public API
----------
generate_run_dirname
    Create a datetime-stamped directory name for a run.
generate_label
    Build a human-readable label string for a flex-search run.
parse_optimization_output
    Extract the goal-function value from a SimNIBS log line.
configure_roi
    Set up ROI(s) on a SimNIBS optimization object.

See Also
--------
tit.opt.flex.flex : Main flex-search orchestrator.
"""

import logging
import os

log = logging.getLogger(__name__)

from tit.opt.config import FlexConfig

# ---------------------------------------------------------------------------
# Output directory naming
# ---------------------------------------------------------------------------


def generate_run_dirname(base_path: str) -> str:
    """Generate a datetime-stamped directory name for a flex-search run.

    Format is ``YYYYMMDD_HHMMSS``.  When a collision exists, ``_1``,
    ``_2``, etc. are appended.

    Parameters
    ----------
    base_path : str
        Parent directory (e.g. ``flex-search/``) to check for
        collisions.

    Returns
    -------
    str
        Directory name string (not the full path).
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

    The label is stored in ``flex_meta.json`` for GUI display and is
    **not** used for folder naming or machine parsing.

    Parameters
    ----------
    config : FlexConfig
        Flex-search configuration instance.
    pareto : bool, optional
        When *True* the goal component is replaced by ``"pareto"``.

    Returns
    -------
    str
        Label string, e.g. ``"mean_maxTI_sphere(-42,-20,55)r10"``.
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
    """Extract the goal-function value from a SimNIBS log line.

    Recognises three patterns:

    * ``"Final goal function value:   -42.123"``
    * ``"Goal function value<anything>:  -42.123"``
    * Table row with a ``max_TI`` column (optionally in scientific
      notation)

    Parameters
    ----------
    line : str
        A single line of SimNIBS stdout / stderr.

    Returns
    -------
    float or None
        The extracted function value, or *None* when the line does not
        match any known pattern.
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
    """Configure ROI(s) on a SimNIBS optimization object.

    Delegates to the appropriate private helper based on the ROI type
    stored in ``config.roi`` (spherical, atlas, or subcortical).

    Parameters
    ----------
    opt : simnibs.optimization.TesFlexOptimization
        SimNIBS optimization object to configure.
    config : FlexConfig
        Flex-search configuration containing the ROI specification.

    Raises
    ------
    ValueError
        If the ROI type is not recognised.
    """
    if isinstance(config.roi, FlexConfig.SphericalROI):
        _configure_spherical_roi(opt, config)
    elif isinstance(config.roi, FlexConfig.AtlasROI):
        _configure_atlas_roi(opt, config)
    elif isinstance(config.roi, FlexConfig.SubcorticalROI):
        _configure_subcortical_roi(opt, config)
    else:
        raise ValueError(f"Unknown ROI type: {type(config.roi)}")


def _resolve_tissues(tissues_str: str) -> list:
    """Map a ``"GM"``/``"WM"``/``"both"`` string to SimNIBS ``ElementTags``."""
    from simnibs.mesh_tools.mesh_io import ElementTags

    value = tissues_str.strip().upper()
    if value == "WM":
        return [ElementTags.WM]
    if value == "BOTH":
        return [ElementTags.WM, ElementTags.GM]
    return [ElementTags.GM]


def _resolve_sphere_center(roi_spec, opt):
    """Return ``[x, y, z]`` in subject space, transforming from MNI if needed."""
    from simnibs import mni2subject_coords

    x, y, z = roi_spec.x, roi_spec.y, roi_spec.z
    if roi_spec.use_mni:
        log.info(f"Transforming MNI coordinates [{x}, {y}, {z}] to subject space")
        coords = mni2subject_coords([x, y, z], opt.subpath)
        log.info(f"Transformed coordinates: {coords}")
        return coords
    return [x, y, z]


def _configure_spherical_roi(opt, config: FlexConfig) -> None:
    """Set up a spherical ROI (surface or volumetric) with optional MNI transform."""
    roi_spec: FlexConfig.SphericalROI = config.roi  # type: ignore[assignment]

    center = _resolve_sphere_center(roi_spec, opt)
    radius = roi_spec.radius

    roi = opt.add_roi()
    if roi_spec.volumetric:
        log.info(
            f"Using volumetric sphere (tissues={roi_spec.tissues}) "
            f"at {center} r={radius}"
        )
        roi.method = "volume"
        roi.tissues = _resolve_tissues(roi_spec.tissues)
    else:
        roi.method = "surface"
        roi.surface_type = "central"

    roi.roi_sphere_center_space = "subject"
    roi.roi_sphere_center = center
    roi.roi_sphere_radius = radius

    # Add non-ROI if focality optimisation is requested
    if config.goal == "focality":
        non_roi = opt.add_roi()
        if roi_spec.volumetric:
            non_roi.method = "volume"
            non_roi.tissues = roi.tissues
        else:
            non_roi.method = "surface"
            non_roi.surface_type = "central"

        if config.non_roi_method == "everything_else":
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_center = center
            non_roi.roi_sphere_radius = radius
            non_roi.roi_sphere_operator = ["difference"]
            non_roi.weight = -1
        else:
            # Specific non-ROI from config.non_roi (unified ROISpec type)
            non_roi_spec: FlexConfig.SphericalROI = config.non_roi  # type: ignore[assignment]
            non_roi.roi_sphere_center = _resolve_sphere_center(non_roi_spec, opt)
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_radius = non_roi_spec.radius
            non_roi.weight = -1


def _configure_atlas_roi(opt, config: FlexConfig) -> None:
    """Set up a cortical atlas-based ROI on the central surface."""
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
    """Read the ``tissues`` field from a SubcorticalROI and resolve to ``ElementTags``."""
    roi_spec: FlexConfig.SubcorticalROI = config.roi  # type: ignore[assignment]
    return _resolve_tissues(roi_spec.tissues)


def _configure_subcortical_roi(opt, config: FlexConfig) -> None:
    """Set up a subcortical volume-based ROI from a label atlas."""
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
