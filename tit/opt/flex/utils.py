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
from pathlib import Path

log = logging.getLogger(__name__)

from tit.opt.config import FlexConfig, _as_list

_VOLUME_MASK_SPACES = {"subject", "mni"}


def _broadcast(value, n: int) -> list:
    """Normalise *value* to a list of length *n*.

    A scalar (or single-element list) is repeated to length *n*; a list that
    already has *n* elements is passed through.  Used to align a shared ROI
    field (e.g. one atlas path or radius) with a list of labels/centers.
    """
    values = _as_list(value)
    if len(values) == 1 and n != 1:
        return values * n
    return values


def _fmt_num(value):
    """Render a coordinate/radius as an int when it has no fractional part."""
    return int(value) if value == int(value) else value


def _union_operators(n: int) -> list[str]:
    """Operator sequence that unions *n* regions on SimNIBS' all-True base.

    SimNIBS seeds the working mask all-True and folds each region with its
    operator, so the first fold must ``intersection`` (selecting region 1) and
    the rest ``union`` on.  An all-``union`` sequence would select the whole
    brain.
    """
    return ["intersection"] + ["union"] * (n - 1)


def eeg_net_csv_path(eeg_positions_dir: str, eeg_net: str) -> Path:
    """Resolve an EEG net name or filename inside a subject EEG directory."""
    filename = Path(eeg_net).name
    if not filename:
        raise ValueError("enable_mapping requires an EEG net name.")
    if Path(filename).suffix.lower() != ".csv":
        filename = f"{filename}.csv"
    return Path(eeg_positions_dir) / filename


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
        xs, ys, zs = _as_list(roi.x), _as_list(roi.y), _as_list(roi.z)
        radii = _broadcast(roi.radius, len(xs))
        roi_str = "+".join(
            f"sphere({_fmt_num(x)},{_fmt_num(y)},{_fmt_num(z)})r{_fmt_num(r)}"
            for x, y, z, r in zip(xs, ys, zs, radii)
        )
    elif isinstance(roi, FlexConfig.AtlasROI):
        labels = _as_list(roi.label)
        hemis = _broadcast(roi.hemisphere, len(labels))
        paths = _broadcast(roi.atlas_path, len(labels))
        hemi = "+".join(dict.fromkeys(hemis))
        first_path = paths[0] if paths else None
        atlas = (
            os.path.basename(first_path).replace(".annot", "").split(".")[-1]
            if first_path
            else "atlas"
        )
        roi_str = f"{hemi}-{atlas}-{'+'.join(str(v) for v in labels)}"
    elif isinstance(roi, FlexConfig.SubcorticalROI):
        labels = _as_list(roi.label)
        paths = _broadcast(roi.atlas_path, len(labels))
        first_path = paths[0] if paths else None
        atlas = os.path.basename(first_path) if first_path else "volume"
        for ext in (".nii.gz", ".nii", ".mgz"):
            if atlas.endswith(ext):
                atlas = atlas[: -len(ext)]
                break
        roi_str = f"subcortical-{atlas}-{'+'.join(str(v) for v in labels)}"
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


def _apply_spheres(roi_obj, centers, radii, space, *, complement: bool) -> None:
    """Write sphere geometry onto a SimNIBS ROI object.

    For a single sphere the scalar/flat form is used (``roi_sphere_center =
    [x, y, z]``, ``roi_sphere_radius = r``, ``roi_sphere_center_space = space``)
    so single-region behaviour is byte-identical to the pre-union code.  For a
    union of *N* spheres the list form is used with an explicit operator
    sequence.  When *complement* is True (focality "everything else") every
    sphere is subtracted from the all-True base (``["difference"] * N``);
    otherwise the union sequence is used.
    """
    n = len(centers)
    operators = ["difference"] * n if complement else _union_operators(n)
    if n == 1:
        roi_obj.roi_sphere_center_space = space
        roi_obj.roi_sphere_center = centers[0]
        roi_obj.roi_sphere_radius = radii[0]
        # A single non-complement sphere leaves the operator unset (SimNIBS
        # defaults to "intersection") to stay byte-identical with prior output.
        if complement:
            roi_obj.roi_sphere_operator = operators
    else:
        roi_obj.roi_sphere_center_space = [space] * n
        roi_obj.roi_sphere_center = centers
        roi_obj.roi_sphere_radius = list(radii)
        roi_obj.roi_sphere_operator = operators


def _spheres_from_spec(roi_spec: FlexConfig.SphericalROI):
    """Return ``(centers, radii, space)`` lists for a (possibly multi) sphere."""
    xs, ys, zs = _as_list(roi_spec.x), _as_list(roi_spec.y), _as_list(roi_spec.z)
    radii = _broadcast(roi_spec.radius, len(xs))
    centers = [[x, y, z] for x, y, z in zip(xs, ys, zs)]
    return centers, radii, _sphere_center_space(roi_spec)


def _sphere_center_space(roi_spec: FlexConfig.SphericalROI) -> str:
    return "mni" if roi_spec.use_mni else "subject"


def _volume_mask_space(roi_spec: FlexConfig.SubcorticalROI) -> str:
    if roi_spec.atlas_space not in _VOLUME_MASK_SPACES:
        raise ValueError(
            f"atlas_space must be one of {sorted(_VOLUME_MASK_SPACES)} "
            f"(was {roi_spec.atlas_space!r})"
        )
    return roi_spec.atlas_space


def _configure_spherical_roi(opt, config: FlexConfig) -> None:
    """Set up a spherical ROI (surface or volumetric), unioning N spheres."""
    roi_spec: FlexConfig.SphericalROI = config.roi  # type: ignore[assignment]

    centers, radii, center_space = _spheres_from_spec(roi_spec)

    roi = opt.add_roi()
    if roi_spec.volumetric:
        log.info(
            f"Using volumetric sphere(s) (tissues={roi_spec.tissues}) "
            f"at {centers} ({center_space}) r={radii}"
        )
        roi.method = "volume"
        roi.tissues = _resolve_tissues(roi_spec.tissues)
    else:
        roi.method = "surface"
        roi.surface_type = "central"

    _apply_spheres(roi, centers, radii, center_space, complement=False)

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
            _apply_spheres(non_roi, centers, radii, center_space, complement=True)
            non_roi.weight = -1
        else:
            # Specific non-ROI from config.non_roi (unified ROISpec type)
            non_roi_spec: FlexConfig.SphericalROI = config.non_roi  # type: ignore[assignment]
            nr_centers, nr_radii, nr_space = _spheres_from_spec(non_roi_spec)
            _apply_spheres(non_roi, nr_centers, nr_radii, nr_space, complement=False)
            non_roi.weight = -1


def _atlas_mask_lists(roi_spec: FlexConfig.AtlasROI):
    """Return parallel ``(mask_space, mask_path, mask_value)`` lists.

    Each label carries its own hemisphere (``subject_lh`` / ``subject_rh``) and
    atlas path, so a target can span both hemispheres or several atlases.
    """
    labels = _as_list(roi_spec.label)
    n = len(labels)
    hemis = _broadcast(roi_spec.hemisphere, n)
    paths = _broadcast(roi_spec.atlas_path, n)
    mask_space = [f"subject_{h}" for h in hemis]
    return mask_space, list(paths), list(labels)


def _configure_atlas_roi(opt, config: FlexConfig) -> None:
    """Set up a cortical atlas-based ROI (union of N labels) on the surface."""
    roi_spec: FlexConfig.AtlasROI = config.roi  # type: ignore[assignment]

    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    roi.mask_space, roi.mask_path, roi.mask_value = _atlas_mask_lists(roi_spec)
    roi.mask_operator = _union_operators(len(roi.mask_value))

    if config.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if config.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            # Length must match the ROI's mask lists or SimNIBS rejects it.
            non_roi.mask_operator = ["difference"] * len(roi.mask_value)
            non_roi.weight = -1
        else:
            non_roi_spec: FlexConfig.AtlasROI = config.non_roi  # type: ignore[assignment]
            non_roi.mask_space, non_roi.mask_path, non_roi.mask_value = (
                _atlas_mask_lists(non_roi_spec)
            )
            non_roi.mask_operator = _union_operators(len(non_roi.mask_value))
            non_roi.weight = -1


def _resolve_roi_tissues(config: FlexConfig) -> list:
    """Read the ``tissues`` field from a SubcorticalROI and resolve to ``ElementTags``."""
    roi_spec: FlexConfig.SubcorticalROI = config.roi  # type: ignore[assignment]
    return _resolve_tissues(roi_spec.tissues)


def _subcortical_mask_lists(roi_spec: FlexConfig.SubcorticalROI):
    """Return parallel ``(mask_space, mask_path, mask_value)`` lists.

    A single shared *atlas_space* applies to the whole union; *atlas_path* may
    be shared (broadcast) or one path per label.  Every atlas path is verified
    to exist.
    """
    labels = _as_list(roi_spec.label)
    n = len(labels)
    paths = _broadcast(roi_spec.atlas_path, n)
    space = _volume_mask_space(roi_spec)
    for path in paths:
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"Volume atlas file not found: {path}")
    return [space] * n, list(paths), list(labels)


def _configure_subcortical_roi(opt, config: FlexConfig) -> None:
    """Set up a subcortical volume ROI (union of N labels) from a label atlas."""
    roi_spec: FlexConfig.SubcorticalROI = config.roi  # type: ignore[assignment]

    tissues = _resolve_roi_tissues(config)

    roi = opt.add_roi()
    roi.method = "volume"
    roi.mask_space, roi.mask_path, roi.mask_value = _subcortical_mask_lists(roi_spec)
    roi.mask_operator = _union_operators(len(roi.mask_value))
    roi.tissues = tissues

    if config.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "volume"

        if config.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            # Length must match the ROI's mask lists or SimNIBS rejects it.
            non_roi.mask_operator = ["difference"] * len(roi.mask_value)
            non_roi.weight = -1
            non_roi.tissues = tissues
        else:
            non_roi_spec: FlexConfig.SubcorticalROI = config.non_roi  # type: ignore[assignment]
            non_roi.mask_space, non_roi.mask_path, non_roi.mask_value = (
                _subcortical_mask_lists(non_roi_spec)
            )
            non_roi.mask_operator = _union_operators(len(non_roi.mask_value))
            non_roi.weight = -1
            non_roi.tissues = tissues
