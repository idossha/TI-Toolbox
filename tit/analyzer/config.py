"""Configuration dataclass for the analyzer runner.

Pure Python -- no SimNIBS, numpy, nibabel, or other heavy dependencies.
Mirrors the ``tit.opt.config`` / ``tit.sim.config`` pattern: a thin, typed
wrapper around the dict keys :mod:`tit.analyzer.__main__` already reads (both
its ``"single"`` and ``"group"`` dispatch branches), so :mod:`tit.config_io`
can generate a JSON Schema for it and the desktop UI can validate a form
against that schema before submitting the job.

This module does not change ``tit.analyzer.__main__`` in any way -- it is a
read of what that entry point already accepts (see its docstring and the
``_run_single`` / ``_run_group`` dict lookups), not a new contract the
runner must adopt. See ``AnalyzerConfig``'s "Notes" for the one runner
behavior this dataclass does not express.

See Also
--------
tit.analyzer.__main__ : Reads the exact dict keys this dataclass mirrors.
tit.analyzer.group.run_group_analysis : Consumed by the ``"group"`` branch.
tit.analyzer.analyzer.Analyzer : Consumed by the ``"single"`` branch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum


def _finite_number(value) -> bool:
    """A real number (not a bool) that is neither NaN nor infinite."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class AnalysisMode(StrEnum):
    """Which entry-point branch handles this config.

    Attributes
    ----------
    SINGLE : str
        One subject, via :class:`tit.analyzer.Analyzer`.
    GROUP : str
        Multiple subjects, via :func:`tit.analyzer.run_group_analysis`.
    """

    SINGLE = "single"
    GROUP = "group"


class AnalyzerSpace(StrEnum):
    """Where the field is read from.

    Attributes
    ----------
    MESH : str
        SimNIBS surface/volume mesh.
    VOXEL : str
        MNI-space NIfTI volume.
    """

    MESH = "mesh"
    VOXEL = "voxel"


class AnalysisType(StrEnum):
    """Region-of-interest shape.

    Attributes
    ----------
    SPHERICAL : str
        A sphere at *center* with radius *radius*.
    CORTICAL : str
        An atlas *region* on *atlas*.
    SUBCORTICAL : str
        Label(s) *region* of the volume atlas *atlas*, in *coordinate_space*
        (a subject atlas, or a shipped MNI atlas warped to the subject).
    MASK : str
        The positive voxels of the NIfTI *mask_path*.
    """

    SPHERICAL = "spherical"
    CORTICAL = "cortical"
    SUBCORTICAL = "subcortical"
    MASK = "mask"


class AnalyzerCoordinateSpace(StrEnum):
    """Space of *center* for a spherical ROI.

    Attributes
    ----------
    SUBJECT : str
        Native subject-space coordinates (mm).
    MNI : str
        MNI coordinates, transformed to subject space before analysis.
    """

    SUBJECT = "subject"
    MNI = "mni"


@dataclass
class AnalyzerConfig:
    """Configuration for one analyzer run (single subject or group).

    Attributes
    ----------
    mode : AnalysisMode
        ``"single"`` (one subject, *subject_id*) or ``"group"`` (multiple
        subjects, *subject_ids*).
    subject_id : str or None
        Subject identifier. Required when *mode* is ``"single"``.
    subject_ids : list of str
        Subject identifiers. Required (non-empty) when *mode* is
        ``"group"``.
    simulation : str
        Simulation (montage) folder name.
    space : AnalyzerSpace
        ``"mesh"`` or ``"voxel"``.
    tissue_type : str
        ``"GM"``, ``"WM"``, or ``"both"`` (voxel space only).
    analysis_type : AnalysisType
        ROI shape; see :class:`AnalysisType`.
    field : str or None
        Field to analyze (a name from ``constants.FIELD_REGISTRY``).
        ``None`` resolves the TI_max/mTI_max envelope automatically.
    center : list of float or None
        ``[x, y, z]`` sphere center in mm. Required for
        ``analysis_type="spherical"``.
    radius : float or None
        Sphere radius in mm. Required for ``analysis_type="spherical"``.
    coordinate_space : AnalyzerCoordinateSpace
        Space of *center* (spherical), of the volume *atlas* (subcortical) or
        of *mask_path* (mask).
    atlas : str or None
        Atlas name. Required for ``analysis_type="cortical"`` and
        ``"subcortical"``.
    region : str or list of str or None
        Region name(s) within *atlas* (cortical, subcortical).
    mask_path : str or None
        NIfTI mask; positive voxels select the ROI in *coordinate_space*.
    output_dir : str or None
        Override output directory. ``None`` derives it from PathManager.
    visualize : bool
        Generate visualization artifacts.

    Raises
    ------
    ValueError
        If *mode* is ``"single"`` without *subject_id*, ``"group"`` without
        *subject_ids*, if *analysis_type* is ``"spherical"`` without a
        *center* of three finite numbers and a positive finite *radius*, or
        ``"cortical"``/``"subcortical"`` without *atlas*.

    Notes
    -----
    ``region`` is a single canonical field here; the runner reads
    ``data.get("regions") or data.get("region")`` (two keys, ``"regions"``
    preferred). Serializing this dataclass writes only ``"region"``, which
    the runner already falls back to, so single-region submissions work
    unchanged; only the plural alias is not reproduced.

    See Also
    --------
    tit.analyzer.__main__ : The entry point whose accepted keys this
        dataclass mirrors.
    """

    mode: AnalysisMode = AnalysisMode.SINGLE
    subject_id: str | None = None
    subject_ids: list[str] = field(default_factory=list)
    simulation: str = ""
    space: AnalyzerSpace = AnalyzerSpace.MESH
    tissue_type: str = "GM"
    analysis_type: AnalysisType = AnalysisType.SPHERICAL
    field: str | None = None
    center: list[float] | None = None
    radius: float | None = None
    coordinate_space: AnalyzerCoordinateSpace = AnalyzerCoordinateSpace.SUBJECT
    atlas: str | None = None
    region: str | list[str] | None = None
    output_dir: str | None = None
    visualize: bool = True
    mask_path: str | None = None

    def __post_init__(self) -> None:
        self.mode = AnalysisMode(self.mode)
        self.space = AnalyzerSpace(self.space)
        self.analysis_type = AnalysisType(self.analysis_type)
        self.coordinate_space = AnalyzerCoordinateSpace(self.coordinate_space)

        if self.mode is AnalysisMode.SINGLE and not self.subject_id:
            raise ValueError("subject_id is required when mode='single'")
        if self.mode is AnalysisMode.GROUP and not self.subject_ids:
            raise ValueError("subject_ids must be non-empty when mode='group'")
        if self.analysis_type is AnalysisType.SPHERICAL:
            if self.center is None or self.radius is None:
                raise ValueError(
                    "center and radius are required for analysis_type='spherical'"
                )
            # Messages name only the offending field: the validate route maps the
            # first field name in the sentence to the form input it flags.
            if not isinstance(self.center, (list, tuple)) or len(self.center) != 3:
                raise ValueError(
                    f"center must be three numbers [x, y, z] in mm; got {self.center!r}"
                )
            if not all(_finite_number(v) for v in self.center):
                raise ValueError(
                    f"center must be three finite numbers in mm; got {self.center!r}"
                )
            if not _finite_number(self.radius) or self.radius <= 0:
                raise ValueError(
                    f"radius must be a positive, finite number of mm; got {self.radius!r}"
                )
        if self.analysis_type is AnalysisType.MASK:
            if not self.mask_path or not self.mask_path.lower().endswith(
                (".nii", ".nii.gz")
            ):
                raise ValueError(
                    "mask_path must name a .nii or .nii.gz file for analysis_type='mask'"
                )
            if (
                self.mode is AnalysisMode.GROUP
                and self.coordinate_space is not AnalyzerCoordinateSpace.MNI
            ):
                raise ValueError("Group mask analysis requires an MNI-space mask")
        if (
            self.analysis_type in (AnalysisType.CORTICAL, AnalysisType.SUBCORTICAL)
            and not self.atlas
        ):
            raise ValueError(
                f"atlas is required for analysis_type='{self.analysis_type.value}'"
            )
