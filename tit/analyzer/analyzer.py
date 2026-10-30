"""Unified field analyzer for mesh and voxel spaces.

Provides a single ``Analyzer`` class that dispatches spherical and cortical
ROI analyses to the appropriate mesh- or voxel-based implementation, returning
a typed ``AnalysisResult`` dataclass.

Public API
----------
Analyzer
    Single-subject field analyzer dispatching to mesh or voxel backends.
AnalysisResult
    Immutable container for ROI analysis statistics.

See Also
--------
tit.analyzer.group : Multi-subject group analysis.
tit.analyzer.field_selector : Automatic field file resolution.
"""

import hashlib
import logging
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from tit import constants as const
from tit.analyzer.field_selector import default_field, select_field_file
from tit.analyzer.masks import analysis_region_key
from tit.atlas.segstats import compute_segstats, resolve_lut_for_atlas
from tit.analyzer.visualizer import (
    save_analysis_metadata,
    save_histogram,
    save_mesh_roi_overlay,
    save_nifti_roi_overlay,
    save_results_csv,
)
from tit.logger import add_file_handler
from tit.paths import get_path_manager

logger = logging.getLogger(__name__)


def voxel_volume_mm3(affine: np.ndarray) -> float:
    """Volume of one voxel in mm^3 from the image affine.

    ``|det(A)|`` of the 3x3 direction block is the exact volume of the
    parallelepiped one voxel maps to.  The header zooms are the *column norms*
    of ``A``; their product equals ``|det(A)|`` only when the voxel axes are
    mutually orthogonal in world space, and overestimates the volume for any
    sheared (non-orthogonal) affine.
    """
    return float(abs(np.linalg.det(np.asarray(affine, dtype=np.float64)[:3, :3])))


def _world_distance_grid(
    affine: np.ndarray,
    voxel_center: np.ndarray,
    shape: tuple[int, int, int],
) -> np.ndarray:
    """Euclidean world-space distance (mm) from *voxel_center* to every voxel.

    The correct metric is ``||A (v - c)||`` with ``A = affine[:3, :3]``, not
    ``sqrt(sum_k (zoom_k * (v_k - c_k))^2)``: the latter assumes the voxel axes
    are orthogonal in world space and is wrong for any sheared affine, so a
    "spherical" ROI came out as the wrong ellipsoid.
    """
    a = np.asarray(affine, dtype=np.float64)[:3, :3]
    grids = np.ogrid[: shape[0], : shape[1], : shape[2]]
    deltas = [g - c for g, c in zip(grids, np.asarray(voxel_center, dtype=np.float64))]
    dist_sq = 0.0
    for row in a:  # each world axis is a linear combination of voxel deltas
        component = row[0] * deltas[0] + row[1] * deltas[1] + row[2] * deltas[2]
        dist_sq = dist_sq + component**2
    return np.sqrt(dist_sq)


def weighted_percentiles(
    values: np.ndarray, weights: np.ndarray, percentiles
) -> list[float]:
    """Area/volume-weighted percentiles, the rule ``results.csv`` reports them by.

    Each percentile is the smallest value whose cumulative weight (values sorted
    ascending) reaches that fraction of the total weight -- no interpolation, so it is
    always one of *values*. The histogram draws its focality cutoffs from the same
    function, so the figure and the table cannot disagree.

    Args:
        values: Finite field values.
        weights: One non-negative weight per value (node area or voxel volume).
        percentiles: Percentiles in ``[0, 100]``.

    Returns:
        One value per entry of *percentiles*, in their order.
    """
    order = np.argsort(values)
    data_sorted = values[order]
    cumulative = np.cumsum(weights[order])
    normalised = cumulative / cumulative[-1]
    return [
        float(
            data_sorted[
                min(int(np.searchsorted(normalised, pct / 100.0)), len(data_sorted) - 1)
            ]
        )
        for pct in percentiles
    ]


def carrier_nifti(field_path: Path, field_name: str, carrier: str) -> Path | None:
    """The *carrier* NIfTI beside the analysed one: the same mesh's file, field suffix swapped.

    mesh2nii names every field of one mesh ``<mesh stem>_<field>.nii.gz`` in one folder, so it
    is on the same grid. ``None`` when *field_path* is not named ``<mesh>_<field_name>.nii[.gz]``.
    """
    name = Path(field_path).name
    for ext in (".nii.gz", ".nii"):
        suffix = f"_{field_name}{ext}"
        if name.endswith(suffix):
            return Path(field_path).with_name(f"{name[: -len(suffix)]}_{carrier}{ext}")
    return None


#: The modulation (envelope) fields: an analysis of one of them also reports the carrier
#: metrics (``hf_peak_focality``, ``hf_rms_focality``, ``ti_selectivity``, ``hf_peak_focality_*_area``).
MODULATION_FIELDS = const.get_field_names(const.FIELD_KIND_FUNCTIONAL)

#: The ``AnalysisResult`` fields :meth:`Analyzer._carrier_metrics` fills.
CARRIER_RESULT_KEYS = (
    "hf_peak_roi_mean",
    "hf_peak_gm_mean",
    "hf_peak_focality",
    "hf_rms_roi_mean",
    "hf_rms_gm_mean",
    "hf_rms_focality",
    "ti_selectivity",
    "hf_peak_focality_50_area",
    "hf_peak_focality_75_area",
    "hf_peak_focality_90_area",
    "hf_peak_focality_95_area",
    "carrier_note",
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AnalysisResult:
    """Immutable container for ROI analysis statistics.

    Returned by :meth:`Analyzer.analyze_sphere` and
    :meth:`Analyzer.analyze_cortex`.

    Attributes
    ----------
    field_name : str
        Name of the field that was analyzed (e.g. ``"TI_max"``).
    region_name : str
        Human-readable ROI label.
    space : str
        ``"mesh"`` or ``"voxel"``.
    analysis_type : str
        ``"spherical"``, ``"cortical"`` or ``"mask"``.
    roi_mean : float
        Area/volume-weighted mean field value inside the ROI.
    roi_max : float
        Maximum field value inside the ROI.
    roi_min : float
        Minimum field value inside the ROI.
    roi_focality : float
        Ratio of ROI mean to whole-GM mean (> 1 means the ROI is stronger
        than the GM average).
    gm_mean : float
        Mean field value across all positive GM elements.
    gm_max : float
        Maximum field value across all GM elements.
    normal_mean : float or None
        Weighted mean of the normal-component field in the ROI (mesh only;
        ``None`` when unavailable).
    normal_max : float or None
        Maximum normal-component field in the ROI.
    normal_focality : float or None
        Normal-component focality ratio.
    percentile_95 : float or None
        95th percentile of the whole-GM field distribution.
    percentile_99 : float or None
        99th percentile of the whole-GM field distribution.
    percentile_99_9 : float or None
        99.9th percentile of the whole-GM field distribution.
    focality_50_area : float or None
        Area/volume where the field exceeds 50 % of the 99.9th percentile
        value -- **cm^2 in mesh space, cm^3 in voxel space** (the ``_area``
        name is kept for both spaces).
    focality_75_area : float or None
        Same for 75 % threshold.
    focality_90_area : float or None
        Same for 90 % threshold.
    focality_95_area : float or None
        Same for 95 % threshold.
    n_elements : int
        Number of ROI mesh nodes or voxels with a positive field value -- the
        elements every ``roi_*`` statistic and ``total_area_or_volume`` describe,
        defined identically in both spaces.
    total_area_or_volume : float
        Total surface area (mm^2) or volume (mm^3) of positive-valued ROI
        elements.
    hf_peak_roi_mean, hf_peak_gm_mean : float or None
        Area/volume-weighted mean ``hf_peak`` (peak carrier field, V/m) over
        the same ROI and GM elements as ``roi_mean`` / ``gm_mean``.
    hf_peak_focality : float or None
        ``hf_peak_roi_mean / hf_peak_gm_mean``: focality of the stimulation (carrier)
        intensity, the carrier counterpart of ``roi_focality``.
    hf_rms_roi_mean, hf_rms_gm_mean : float or None
        Weighted mean of the saved ``hf_rms`` field (RMS carrier field over time,
        ``sqrt(hf_power)``, V/m) over the same elements.
    hf_rms_focality : float or None
        ``hf_rms_roi_mean / hf_rms_gm_mean``.
    ti_selectivity : float or None
        ``roi_focality / hf_peak_focality``: above 1 the modulation is more focal
        than the stimulation, at or below 1 a plain kHz field targets as well.
    hf_peak_focality_50_area ... hf_peak_focality_95_area : float or None
        ``focality_*_area`` computed on ``hf_peak`` (same units, same
        99.9th-percentile convention, same GM elements).
    carrier_note : str or None
        Why a carrier metric is ``None``: the analysed field is itself a
        carrier field, or a carrier field has no usable values on the
        analysed elements. ``None`` when every carrier metric is present.
    on_demand_note : str or None
        What this analysis produced because the simulation had not saved it
        (a field computed from the channel meshes, a NIfTI written from the
        field mesh), in the words it logged; ``None`` when everything was
        saved. What it produced stays in the simulation's outputs.

    See Also
    --------
    Analyzer : Single-subject field analyzer.
    GroupResult : Container for multi-subject group analysis.
    """

    field_name: str
    region_name: str
    space: str  # "mesh" or "voxel"
    analysis_type: str  # "spherical" or "cortical"
    roi_mean: float
    roi_max: float
    roi_min: float
    roi_focality: float  # TImean_ROI / TImean_GM
    gm_mean: float
    gm_max: float
    normal_mean: float | None = None
    normal_max: float | None = None
    normal_focality: float | None = None
    percentile_95: float | None = None
    percentile_99: float | None = None
    percentile_99_9: float | None = None
    focality_50_area: float | None = None
    focality_75_area: float | None = None
    focality_90_area: float | None = None
    focality_95_area: float | None = None
    n_elements: int = 0
    total_area_or_volume: float = 0.0
    hf_peak_roi_mean: float | None = None
    hf_peak_gm_mean: float | None = None
    hf_peak_focality: float | None = None  # hf_peak mean ROI / mean GM
    hf_rms_roi_mean: float | None = None
    hf_rms_gm_mean: float | None = None
    hf_rms_focality: float | None = None  # hf_rms mean ROI / mean GM
    ti_selectivity: float | None = None  # roi_focality / hf_peak_focality
    hf_peak_focality_50_area: float | None = None
    hf_peak_focality_75_area: float | None = None
    hf_peak_focality_90_area: float | None = None
    hf_peak_focality_95_area: float | None = None
    carrier_note: str | None = None
    on_demand_note: str | None = None


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class Analyzer:
    """Unified analyzer for mesh and voxel field data.

    Lazily loads the field file on first analysis call. All coordinate
    transforms and ROI masking are handled internally.

    Parameters
    ----------
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    simulation : str
        Simulation (montage) folder name.
    space : str, optional
        ``"mesh"`` or ``"voxel"``. Default ``"mesh"``.
    tissue_type : str, optional
        ``"GM"``, ``"WM"``, or ``"both"``. Only affects voxel analyses;
        mesh analyses always use the GM cortical surface. Default ``"GM"``.
    output_dir : str or None, optional
        Override output directory. If ``None``, derived from PathManager.
    field : str or None, optional
        Field to analyze, from ``constants.FIELD_REGISTRY`` (e.g.
        ``"hf_peak"``, ``"TI_normal"``). Default ``None`` resolves the
        TI_max/mTI_max envelope. See :func:`select_field_file`. A volume
        field the simulation did not save -- the analysed field, or the
        ``hf_peak`` / ``hf_rms`` a modulation field's carrier metrics read --
        is produced first, from the simulation's channel meshes, and saved
        into its outputs (:mod:`tit.volume_fields`); so is the NIfTI a voxel
        analysis reads. ``on_demand_note`` on the result says what was.

    Attributes
    ----------
    subject_id : str
        Subject identifier.
    simulation : str
        Simulation folder name.
    space : str
        Analysis space (``"mesh"`` or ``"voxel"``).
    tissue_type : str
        Normalised tissue selection (``"GM"``, ``"WM"``, or ``"BOTH"``).
    field_path : pathlib.Path
        Resolved path to the field file.
    field_name : str
        Short name of the field (e.g. ``"TI_max"``).
    m2m_path : str
        Path to the subject's ``m2m_*`` directory.
    output_dir : str or None
        Output directory override, or ``None``.

    Raises
    ------
    FileNotFoundError
        If no field file exists for *subject_id*/*simulation* in *space*
        (run the simulation first), or a field it needs was not saved and
        cannot be produced (:class:`tit.volume_fields.FieldUnavailableError`,
        naming what is missing).
    ValueError
        If *space* is not ``"mesh"``/``"voxel"`` or *field* is not a known
        field name.

    Examples
    --------
    >>> from tit.analyzer import Analyzer
    >>> analyzer = Analyzer("ernie", "L_Insula", space="voxel")  # doctest: +SKIP
    >>> result = analyzer.analyze_sphere(
    ...     center=(-35.0, 5.0, 5.0), radius=10.0, coordinate_space="MNI",
    ... )  # doctest: +SKIP
    >>> result.roi_mean, result.roi_focality  # doctest: +SKIP
    (0.21, 1.8)
    >>> cortex = Analyzer("ernie", "L_Insula", space="mesh").analyze_cortex(
    ...     atlas="DK40", region="lh.insula", visualize=True)  # doctest: +SKIP
    >>> cortex.analysis_type, cortex.focality_50_area  # doctest: +SKIP
    ('cortical', 42.1)

    See Also
    --------
    AnalysisResult : Container for single-subject analysis outputs.
    run_group_analysis : Multi-subject group analysis.
    """

    #: What :meth:`_produce_missing_fields` produced (its notices); none until it runs.
    _on_demand: tuple[str, ...] = ()
    #: Why a carrier field could not be produced, by field; replaced, never mutated.
    _carrier_reasons: dict[str, str] = {}
    #: The central surface :meth:`_load_surface_mesh` read; ``None`` until it has.
    _surface_mesh_path: Path | None = None

    def __init__(
        self,
        subject_id: str,
        simulation: str,
        space: str = "mesh",
        tissue_type: str = "GM",
        output_dir: str | None = None,
        field: str | None = None,
    ) -> None:
        self.subject_id = subject_id
        self.simulation = simulation
        self.space = space
        self.tissue_type = self._normalize_tissue_type(tissue_type)
        if self.space == "mesh":
            self.tissue_type = "GM"

        pm = get_path_manager()
        self.m2m_path = pm.m2m(subject_id)
        self.output_dir = output_dir
        self._pm = pm

        # Attach a file handler so every log message is persisted to disk, the notices of
        # what is produced on demand below included.
        logs_dir = pm.logs(subject_id)
        pm.ensure(logs_dir)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file = Path(logs_dir) / f"analyzer_{simulation}_{timestamp}.log"
        self._log_handler = add_file_handler(log_file)

        try:
            self._on_demand = tuple(self._produce_missing_fields(field))
            field_path, field_name = select_field_file(
                subject_id,
                simulation,
                space,
                tissue_type=self.tissue_type,
                field=field,
            )
        except BaseException:
            logging.getLogger("tit").removeHandler(self._log_handler)
            self._log_handler.close()
            raise
        self.field_path = field_path
        self.field_name = field_name
        # mTI outputs live under <simulation>/mTI/; TI outputs under <simulation>/TI/.
        self._is_mti = "mTI" in Path(field_path).parts

        logger.info(
            "Analyzer initialised: subject=%s sim=%s space=%s tissue=%s field=%s",
            subject_id,
            simulation,
            space,
            self.tissue_type,
            field_name,
        )

        # Cached lazily
        self._surface_mesh = None
        self._surface_mesh_path: Path | None = None

    @staticmethod
    def volume_fields_read(space: str, field: str | None) -> list[str]:
        """The volume fields an analysis of *field* in *space* reads (job preflight asks too).

        The analysed field itself (not ``TI_normal``, a surface field) and, for a modulation
        field, the ``hf_peak`` / ``hf_rms`` its carrier metrics read. A request
        :func:`select_field_file` will refuse (unknown field or space, ``TI_normal`` in voxel
        space) reads none.
        """
        name = field or const.FIELD_TI_MAX
        if space not in ("mesh", "voxel") or name not in const.get_field_names():
            return []
        if space == "voxel" and name == const.FIELD_TI_NORMAL:
            return []
        needed = [] if name == const.FIELD_TI_NORMAL else [name]
        if name in MODULATION_FIELDS:
            needed += [const.FIELD_HF_PEAK, const.FIELD_HF_RMS]
        return needed

    def _produce_missing_fields(self, field: str | None) -> list[str]:
        """Produce what this analysis reads and the simulation did not save; the notices said.

        :meth:`volume_fields_read`, into the field mesh and central surface (mesh space), or as
        the tissue's subject-space NIfTIs (voxel space). In voxel space the field selector is
        asked first: a NIfTI it finds (an older or renamed one included) is analysed as it is,
        and only its missing carrier siblings are produced. The analysed field must be saved
        or producible (else :class:`~tit.volume_fields.FieldUnavailableError`); carriers that
        cannot be produced (a NIfTI-only archive, deleted channel meshes) leave the carrier
        metrics empty with that reason in ``carrier_note``.
        """
        from tit.volume_fields import (
            FieldUnavailableError,
            ensure_mesh_fields,
            ensure_niftis,
        )

        sid, sim = self.subject_id, self.simulation
        name = field or default_field(sid, sim)
        needed = self.volume_fields_read(self.space, name)
        analysed = [] if name == const.FIELD_TI_NORMAL else needed[:1]
        carriers = needed[len(analysed) :]
        notices: list[str] = []
        if self.space == "mesh":
            if analysed:
                notices += ensure_mesh_fields(sid, sim, analysed, say=logger.info)

            def produce_carriers():
                return ensure_mesh_fields(sid, sim, carriers, say=logger.info)

        else:
            tissue = {"GM": "grey", "WM": "white", "BOTH": None}[self.tissue_type]
            try:
                found, found_name = select_field_file(
                    sid, sim, "voxel", tissue_type=self.tissue_type, field=field
                )
            except FileNotFoundError:
                found = None
            if found is None and analysed:
                notices += ensure_niftis(
                    sid, sim, analysed, tissue=tissue, say=logger.info
                )[1]
            elif found is not None:
                carriers = [
                    c
                    for c in carriers
                    if not (carrier_nifti(found, found_name, c) or found).is_file()
                ]

            def produce_carriers():
                return ensure_niftis(
                    sid, sim, carriers, tissue=tissue, say=logger.info
                )[1]

        if carriers:
            try:
                notices += produce_carriers()
            except FieldUnavailableError as exc:
                self._carrier_reasons = {c: str(exc) for c in carriers}
        return notices

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_sphere(
        self,
        center: tuple[float, float, float],
        radius: float,
        coordinate_space: str = "subject",
        visualize: bool = False,
    ) -> AnalysisResult:
        """Analyze a spherical ROI.

        Parameters
        ----------
        center : tuple of float
            ``(x, y, z)`` coordinates of the sphere centre.
        radius : float
            Radius in mm.
        coordinate_space : str, optional
            ``"subject"`` (default) or ``"MNI"``. When ``"MNI"``,
            coordinates are transformed to subject space via SimNIBS
            ``mni2subject_coords``.
        visualize : bool, optional
            Also write the ROI overlay, its scene and ``histogram.png``
            (``results.csv`` and ``analysis.json`` are written either way).

        Returns
        -------
        AnalysisResult
            ROI and whole-GM statistics for the spherical region.

        Raises
        ------
        FileNotFoundError
            If the required field or surface mesh file does not exist.
        ValueError
            If *center* is not three finite numbers or *radius* is not a positive
            finite number, or if the sphere holds no positive field value (an
            empty ROI has no statistics).

        See Also
        --------
        analyze_cortex : Atlas-based cortical ROI analysis.
        """
        from tit.telemetry import track_operation
        from tit import constants as const

        spheres = self._checked_spheres([(*center, radius)])
        with track_operation(const.TELEMETRY_OP_ANALYSIS):
            dispatch = {"mesh": self._sphere_mesh, "voxel": self._sphere_voxel}
            return dispatch[self.space](spheres, coordinate_space, visualize)

    def analyze_spheres(
        self,
        spheres,
        coordinate_space: str = "subject",
        visualize: bool = False,
    ) -> AnalysisResult:
        """Analyze several spherical ROIs unioned into a single ROI.

        The spheres are combined with a logical OR before any statistic is
        computed, so the result describes one ROI covering all of them --
        overlapping spheres are not double-counted. Passing a single sphere
        is equivalent to :meth:`analyze_sphere`.

        Parameters
        ----------
        spheres : sequence of tuple of float
            One ``(x, y, z, r)`` per sphere.
        coordinate_space : str, optional
            ``"subject"`` (default) or ``"MNI"``, applied to every sphere.
        visualize : bool, optional
            Also write the ROI overlay, its scene and ``histogram.png``
            (``results.csv`` and ``analysis.json`` are written either way).

        Returns
        -------
        AnalysisResult
            ROI and whole-GM statistics for the combined region.

        Raises
        ------
        ValueError
            If *spheres* is empty, a sphere lacks a finite centre or a positive
            finite radius, or their union holds no positive field value.

        See Also
        --------
        analyze_sphere : Single spherical ROI analysis.
        """
        from tit.telemetry import track_operation
        from tit import constants as const

        spheres = self._checked_spheres(spheres)
        if not spheres:
            raise ValueError("analyze_spheres requires at least one sphere.")

        with track_operation(const.TELEMETRY_OP_ANALYSIS):
            dispatch = {"mesh": self._sphere_mesh, "voxel": self._sphere_voxel}
            return dispatch[self.space](spheres, coordinate_space, visualize)

    def analyze_cortex(
        self,
        atlas: str,
        region: str | list[str],
        visualize: bool = False,
    ) -> AnalysisResult:
        """Analyze a cortical atlas region.

        Parameters
        ----------
        atlas : str
            Atlas name recognised by SimNIBS (e.g. ``"DK40"``,
            ``"HCP_MMP1"``), or an absolute path to an atlas NIfTI
            (voxel mode only).
        region : str or list of str
            Region name within the atlas (e.g. ``"lh.cuneus"``), or a
            list of region names whose masks are unioned into a single
            combined ROI. Bare names like ``"cuneus"`` expand to both
            hemispheres in mesh mode.
        visualize : bool, optional
            Also write the ROI overlay, its scene and ``histogram.png``
            (``results.csv`` and ``analysis.json`` are written either way).

        Returns
        -------
        AnalysisResult
            ROI and whole-GM statistics for the cortical region.

        Raises
        ------
        KeyError
            If a region name cannot be resolved in the atlas.
        FileNotFoundError
            If the atlas or field file does not exist.

        See Also
        --------
        analyze_sphere : Spherical ROI analysis.
        """
        from tit.telemetry import track_operation
        from tit import constants as const

        with track_operation(const.TELEMETRY_OP_ANALYSIS):
            dispatch = {"mesh": self._cortex_mesh, "voxel": self._cortex_voxel}
            return dispatch[self.space](atlas, region, visualize)

    def analyze_mask(
        self,
        mask_path: str,
        coordinate_space: str = "subject",
        visualize: bool = False,
    ) -> AnalysisResult:
        """Analyze positive NIfTI voxels sampled onto subject geometry.

        MNI masks use the optimizer's nonlinear m2m registration. Nearest-neighbour
        sampling preserves binary membership; mesh results remain GM surface-area
        statistics and voxel results retain the selected tissue and volume units.

        Parameters
        ----------
        mask_path : str
            Path to a 3-D NIfTI mask (``.nii``/``.nii.gz``); voxels ``> 0``
            form the ROI.
        coordinate_space : str, optional
            ``"subject"`` (default) or ``"mni"`` (case-insensitive).
        visualize : bool, optional
            Also write the ROI overlay, its scene and ``histogram.png``
            (``results.csv`` and ``analysis.json`` are written either way).

        Returns
        -------
        AnalysisResult
            ROI and whole-GM statistics for the mask region, with
            ``analysis_type="mask"``.

        Raises
        ------
        ValueError
            If *coordinate_space* is not ``"subject"``/``"mni"``, the file is
            not a readable finite 3-D NIfTI, or (mesh mode) the mask does not
            overlap the grey-matter surface.

        See Also
        --------
        analyze_sphere : Spherical ROI analysis.
        analyze_cortex : Atlas-based cortical ROI analysis.
        """
        from tit.analyzer.masks import mask_region_name

        coordinate_space = coordinate_space.lower()
        return self._analyze_mask_file(
            mask_path,
            coordinate_space,
            visualize,
            region_name=mask_region_name(mask_path, coordinate_space),
            analysis_type="mask",
            what="Mask",
        )

    def analyze_subcortical(
        self,
        atlas: str,
        region: str | list[str],
        coordinate_space: str = "subject",
        visualize: bool = False,
    ) -> AnalysisResult:
        """Analyze regions of a volumetric (label) atlas, in subject or MNI space.

        The selected labels (islands removed, as for every volumetric ROI) become one
        binary mask in the atlas's own space, which is then measured exactly as
        :meth:`analyze_mask` measures a mask: an MNI atlas goes through the subject's
        nonlinear m2m registration, a mesh analysis samples the mask onto the GM
        surface, a voxel analysis onto the field grid within the selected tissue.

        Parameters
        ----------
        atlas : str
            Subject space: an atlas name the catalog lists for the subject
            (``"labeling.nii.gz"``, a FreeSurfer volume such as
            ``"aparc.DKTatlas+aseg.mgz"``, ``"masks/<file>"``) or a file path.
            MNI space: a shipped MNI atlas id (its file name) or a file path.
        region : str or list of str
            Region name(s) or integer label(s); several are unioned into one ROI.
        coordinate_space : str, optional
            ``"subject"`` (default) or ``"mni"`` -- the space *atlas* is in.
        visualize : bool, optional
            Also write the ROI overlay, its scene and ``histogram.png``
            (``results.csv`` and ``analysis.json`` are written either way).

        Returns
        -------
        AnalysisResult
            ROI statistics with ``analysis_type="subcortical"``.

        Raises
        ------
        FileNotFoundError
            If the atlas cannot be found.
        ValueError
            If a region is not in the atlas, or the ROI does not overlap the GM
            surface (mesh; a deep structure has none) or the selected tissue (voxel).
        """
        import tempfile
        import nibabel as nib
        from tit.atlas.islands import keep_main_components

        space = coordinate_space.lower()
        atlas_path = (
            self._resolve_mni_atlas(atlas)
            if space == "mni"
            else self._resolve_voxel_atlas(atlas)
        )
        atlas_img = nib.load(str(atlas_path))
        labels = self._squeeze_4d(np.asanyarray(atlas_img.dataobj))
        regions = [str(r) for r in (region if isinstance(region, list) else [region])]
        if not any(r.strip() for r in regions):
            raise ValueError("A subcortical analysis needs at least one region")
        roi = np.zeros(labels.shape, dtype=bool)
        for name in regions:
            rid = self._find_voxel_region_id(atlas_path, name)
            one, _, _ = keep_main_components(labels == rid, what=name)
            self._require_label_voxels(one, name, rid, atlas_path)
            roi |= one
        region_name = analysis_region_key(regions)
        with tempfile.TemporaryDirectory() as scratch:
            mask_path = str(Path(scratch) / "subcortical_roi.nii")
            nib.save(nib.Nifti1Image(roi.astype(np.uint8), atlas_img.affine), mask_path)
            return self._analyze_mask_file(
                mask_path,
                space,
                visualize,
                region_name=region_name,
                analysis_type="subcortical",
                what=f"{region_name} ({Path(str(atlas)).name})",
                atlas=atlas,
                region_labels=regions,
                coordinate_space=space,
            )

    def _analyze_mask_file(
        self,
        mask_path: str,
        mask_space: str,
        visualize: bool,
        *,
        region_name: str,
        analysis_type: str,
        what: str,
        **kwargs,
    ) -> AnalysisResult:
        """Measure the positive voxels of *mask_path* (shared by mask and subcortical)."""
        import tempfile
        import nibabel as nib
        from nibabel.processing import resample_from_to
        from scipy.ndimage import map_coordinates
        from tit.opt.masks import prepare_mask
        from tit import constants as const
        from tit.telemetry import track_operation

        with (
            track_operation(const.TELEMETRY_OP_ANALYSIS),
            tempfile.TemporaryDirectory() as scratch,
        ):
            prepared = prepare_mask(
                mask_path, mask_space, str(self.m2m_path), scratch, binary=True
            )
            mask_img = nib.load(prepared)
            if self.space == "mesh":
                surface = self._load_surface_mesh()
                coords = nib.affines.apply_affine(
                    np.linalg.inv(mask_img.affine), surface.nodes.node_coord
                )
                mask = (
                    map_coordinates(
                        mask_img.get_fdata(), coords.T, order=0, mode="constant", cval=0
                    )
                    > 0
                )
                if not mask.any():
                    raise ValueError(
                        f"{what} does not overlap the gray-matter surface; "
                        "analyze it in voxel space instead"
                    )
                result = self._analyze_mesh_roi(
                    surface,
                    self._field_values(surface),
                    self._node_areas(surface),
                    mask,
                    region_name=region_name,
                    analysis_type=analysis_type,
                    visualize=visualize,
                    **kwargs,
                )
                return result
            img = nib.load(str(self.field_path))
            field_arr = self._squeeze_4d(img.get_fdata())
            sampled = (
                resample_from_to(
                    mask_img,
                    (field_arr.shape[:3], img.affine),
                    order=0,
                    mode="constant",
                    cval=0,
                ).get_fdata()
                > 0
            )
            analysis_mask = (field_arr > 0) & self._voxel_tissue_mask(
                field_arr.shape[:3], img.affine
            )
            roi_mask = sampled & analysis_mask
            if not roi_mask.any():
                raise ValueError(
                    f"{what} does not overlap positive field values in the selected tissue"
                )
            result = self._analyze_voxel_roi(
                field_arr,
                roi_mask,
                analysis_mask,
                img.affine,
                region_name=region_name,
                analysis_type=analysis_type,
                visualize=visualize,
                **kwargs,
            )
            return result

    # ------------------------------------------------------------------
    # Mesh: spherical
    # ------------------------------------------------------------------

    def _sphere_mesh(
        self,
        spheres: list[tuple[float, float, float, float]],
        coordinate_space: str,
        visualize: bool,
    ) -> AnalysisResult:
        surface = self._load_surface_mesh()
        values = self._field_values(surface)
        coords = surface.nodes.node_coord
        node_areas = self._node_areas(surface)

        mask = np.zeros(len(coords), dtype=bool)
        for x, y, z, radius in spheres:
            center_arr = self._maybe_transform_coords((x, y, z), coordinate_space)
            mask |= np.linalg.norm(coords - center_arr, axis=1) <= radius

        if len(spheres) > 1:
            logger.info(
                "Spherical ROI: union of %d spheres, mask=%d/%d nodes",
                len(spheres),
                int(mask.sum()),
                len(mask),
            )

        return self._analyze_mesh_roi(
            surface,
            values,
            node_areas,
            mask,
            region_name=self._sphere_region_name(spheres),
            analysis_type="spherical",
            spheres=spheres,
            coordinate_space=coordinate_space,
            visualize=visualize,
        )

    # ------------------------------------------------------------------
    # Mesh: cortical
    # ------------------------------------------------------------------

    def _cortex_mesh(
        self,
        atlas: str,
        region: str | list[str],
        visualize: bool,
    ) -> AnalysisResult:
        from simnibs.utils.transformations import atlas2subject

        surface = self._load_surface_mesh()
        values = self._field_values(surface)
        node_areas = self._node_areas(surface)

        # The joined central surface has lh nodes first, then rh.
        # Pad per-hemisphere masks to full length and prefix keys with
        # "lh."/"rh." so bare names (e.g. DK40 "cuneus") don't collide.
        atlas_raw = atlas2subject(self.m2m_path, atlas, split_labels=True)
        lh_labels = atlas_raw.get("lh", {})
        rh_labels = atlas_raw.get("rh", {})
        n_lh = len(next(iter(lh_labels.values()))) if lh_labels else 0
        n_rh = len(next(iter(rh_labels.values()))) if rh_labels else 0

        atlas_map = {}
        for name, mask in lh_labels.items():
            key = name if name.startswith("lh.") else f"lh.{name}"
            atlas_map[key] = np.concatenate([mask, np.zeros(n_rh, dtype=bool)])
        for name, mask in rh_labels.items():
            key = name if name.startswith("rh.") else f"rh.{name}"
            atlas_map[key] = np.concatenate([np.zeros(n_lh, dtype=bool), mask])

        regions = region if isinstance(region, list) else [region]

        # Resolve user-facing names to atlas keys ("lh.cuneus", or bare
        # "cuneus" → both hemispheres).
        atlas_keys = []
        seen = set()
        for r in regions:
            for k in self._resolve_mesh_region(r, atlas_map):
                if k not in seen:
                    seen.add(k)
                    atlas_keys.append(k)

        masks = [np.asarray(atlas_map[k], dtype=bool) for k in atlas_keys]
        mask = masks[0]
        for m in masks[1:]:
            mask = mask | m
        region_name = "+".join(atlas_keys)
        region_labels = list(atlas_keys)

        logger.info(
            "Cortical ROI: atlas=%s regions=%s mask=%d/%d nodes",
            atlas,
            atlas_keys,
            int(mask.sum()),
            len(mask),
        )

        return self._analyze_mesh_roi(
            surface,
            values,
            node_areas,
            mask,
            region_name=region_name,
            analysis_type="cortical",
            atlas=atlas,
            region_labels=region_labels,
            region_key=analysis_region_key(regions),
            visualize=visualize,
        )

    # ------------------------------------------------------------------
    # Voxel: spherical
    # ------------------------------------------------------------------

    def _sphere_voxel(
        self,
        spheres: list[tuple[float, float, float, float]],
        coordinate_space: str,
        visualize: bool,
    ) -> AnalysisResult:
        import nibabel as nib

        img = nib.load(str(self.field_path))
        field_arr = self._squeeze_4d(img.get_fdata())
        affine = img.affine

        shape = field_arr.shape
        inv_affine = np.linalg.inv(affine)

        # Union of the requested spheres. The distance metric is world-space
        # ||A (v - c)|| (SCI-05): the header-zoom form assumes orthogonal voxel
        # axes and yields the wrong ellipsoid for any sheared affine.
        sphere_mask = np.zeros(shape[:3], dtype=bool)
        for cx, cy, cz, radius in spheres:
            center_arr = self._maybe_transform_coords((cx, cy, cz), coordinate_space)
            voxel_center = np.dot(inv_affine, np.append(center_arr, 1))[:3]
            sphere_mask |= _world_distance_grid(affine, voxel_center, shape) <= radius

        if len(spheres) > 1:
            logger.info(
                "Spherical ROI: union of %d spheres, mask=%d voxels",
                len(spheres),
                int(sphere_mask.sum()),
            )

        positive_mask = field_arr > 0
        tissue_mask = self._voxel_tissue_mask(field_arr.shape[:3], affine)
        analysis_mask = positive_mask & tissue_mask
        roi_mask = sphere_mask & analysis_mask

        return self._analyze_voxel_roi(
            field_arr,
            roi_mask,
            analysis_mask,
            affine,
            region_name=self._sphere_region_name(spheres),
            analysis_type="spherical",
            spheres=spheres,
            coordinate_space=coordinate_space,
            visualize=visualize,
        )

    # ------------------------------------------------------------------
    # Voxel: cortical
    # ------------------------------------------------------------------

    def _cortex_voxel(
        self,
        atlas: str,
        region: str | list[str],
        visualize: bool,
    ) -> AnalysisResult:
        import nibabel as nib

        img = nib.load(str(self.field_path))
        field_arr = self._squeeze_4d(img.get_fdata())
        affine = img.affine

        atlas_path = self._resolve_voxel_atlas(atlas)
        atlas_img = nib.load(str(atlas_path))
        atlas_arr = atlas_img.get_fdata()

        atlas_arr = self._resample_if_needed(
            atlas_img,
            atlas_arr,
            field_arr.shape[:3],
            affine,
            atlas_path,
        )

        regions = region if isinstance(region, list) else [region]
        ids = [self._find_voxel_region_id(atlas_path, r) for r in regions]
        from tit.atlas.islands import keep_main_components

        region_mask_raw = np.zeros_like(atlas_arr, dtype=bool)
        # One value per region, so the plate can colour and count them apart.
        region_values = np.zeros(atlas_arr.shape, dtype=np.int16)
        for index, (rid, name) in enumerate(zip(ids, regions), start=1):
            # Per label, not on the union: a union of two structures is legitimately
            # disconnected, and each of them separately is what has islands.
            one, _, _ = keep_main_components(atlas_arr == rid, what=str(name))
            self._require_label_voxels(one, name, rid, atlas_path)
            region_mask_raw = region_mask_raw | one
            region_values[one & (region_values == 0)] = index
        region_name = analysis_region_key(regions)
        region_labels = list(regions)

        positive_mask = field_arr > 0
        tissue_mask = self._voxel_tissue_mask(field_arr.shape[:3], affine)
        analysis_mask = positive_mask & tissue_mask
        roi_mask = region_mask_raw & analysis_mask

        return self._analyze_voxel_roi(
            field_arr,
            roi_mask,
            analysis_mask,
            affine,
            region_name=region_name,
            analysis_type="cortical",
            atlas=atlas,
            region_labels=region_labels,
            visualize=visualize,
        )

    # ------------------------------------------------------------------
    # Shared mesh analysis
    # ------------------------------------------------------------------

    def _analyze_mesh_roi(
        self,
        surface,
        values: np.ndarray,
        node_areas: np.ndarray,
        roi_mask: np.ndarray,
        *,
        region_name: str,
        analysis_type: str,
        visualize: bool = False,
        **kwargs,
    ) -> AnalysisResult:
        roi_values = values[roi_mask]
        pos_within_roi = roi_values > 0
        roi_pos = roi_values[pos_within_roi]
        roi_areas = node_areas[roi_mask][pos_within_roi]

        if roi_pos.size == 0:
            # Raised before the output folder exists: an empty ROI has no statistics, and a
            # results.csv of zeros (gm_mean = 0 included) would read as a measurement.
            raise ValueError(
                f"{region_name} does not overlap positive {self.field_name} values on "
                f"the gray-matter surface (mesh space): it holds {int(np.sum(roi_mask))} "
                "surface node(s), none with a positive value. Check the target's position "
                "and size, or analyze it in voxel space."
            )

        surface_pos_mask = values > 0
        surface_pos = values[surface_pos_mask]
        surface_areas = node_areas[surface_pos_mask]

        roi_mean = float(np.average(roi_pos, weights=roi_areas))
        roi_max = float(np.max(roi_pos))
        roi_min = float(np.min(roi_pos))
        surface_mean = float(np.average(surface_pos, weights=surface_areas))
        surface_max = float(np.max(surface_pos))
        roi_focality = roi_mean / surface_mean

        focality = self._compute_focality_metrics(surface_pos, surface_areas)
        normal = self._get_normal_stats(roi_mask, node_areas)
        carrier = self._carrier_metrics(
            roi_focality,
            self._mesh_carriers(surface),
            roi_mask & (values > 0),
            surface_pos_mask,
            roi_areas,
            surface_areas,
        )

        out_dir = self._resolve_output_dir(
            analysis_type=analysis_type,
            region_name=region_name,
            **kwargs,
        )

        result = AnalysisResult(
            field_name=self.field_name,
            region_name=region_name,
            space="mesh",
            analysis_type=analysis_type,
            roi_mean=roi_mean,
            roi_max=roi_max,
            roi_min=roi_min,
            roi_focality=roi_focality,
            gm_mean=surface_mean,
            gm_max=surface_max,
            normal_mean=normal.get("mean") if normal else None,
            normal_max=normal.get("max") if normal else None,
            normal_focality=normal.get("focality") if normal else None,
            n_elements=int(roi_pos.size),
            total_area_or_volume=float(np.sum(roi_areas)),
            **focality,
            **carrier,
            on_demand_note=" ".join(self._on_demand) or None,
        )

        if visualize:
            self._visualize_mesh(
                surface,
                values,
                roi_mask,
                out_dir,
                result,
                surface_pos,
                surface_areas,
                roi_pos,
                roi_areas,
                analysis_type=analysis_type,
            )

        save_results_csv(asdict(result), Path(out_dir))
        self._save_metadata(out_dir, "mesh", analysis_type, kwargs)
        logger.info("Analysis complete for %s (%s)", region_name, analysis_type)
        return result

    # ------------------------------------------------------------------
    # Shared voxel analysis
    # ------------------------------------------------------------------

    def _analyze_voxel_roi(
        self,
        field_arr: np.ndarray,
        roi_mask: np.ndarray,
        analysis_mask: np.ndarray,
        affine: np.ndarray,
        *,
        region_name: str,
        analysis_type: str,
        visualize: bool = False,
        **kwargs,
    ) -> AnalysisResult:
        roi_values = field_arr[roi_mask]
        tissue_values = field_arr[analysis_mask]
        voxel_vol = voxel_volume_mm3(affine)

        if roi_values.size == 0:
            tissue = "+".join(self._tissue_type_list())
            raise ValueError(
                f"{region_name} does not overlap positive {self.field_name} values in "
                f"the selected tissue ({tissue}, voxel space). Check the target's position "
                "and size, or choose another tissue."
            )

        roi_mean = float(np.mean(roi_values))
        roi_max = float(np.max(roi_values))
        roi_min = float(np.min(roi_values))
        tissue_mean = float(np.mean(tissue_values))
        tissue_max = float(np.max(tissue_values))
        roi_focality = roi_mean / tissue_mean

        tissue_weights = np.full(len(tissue_values), voxel_vol)
        # Voxel weights are mm^3, so the cm^3 divisor is 1000 (a mesh ROI
        # weights by mm^2 and divides by 100).  v2.x used 100 for both, making
        # every voxel focality volume 10x too large.
        focality = self._compute_focality_metrics(
            tissue_values, tissue_weights, weight_to_cm=1000.0
        )
        carrier = self._carrier_metrics(
            roi_focality,
            self._voxel_carriers(field_arr.shape, affine),
            roi_mask,
            analysis_mask,
            np.full(roi_values.size, voxel_vol),
            tissue_weights,
            weight_to_cm=1000.0,
        )

        out_dir = self._resolve_output_dir(
            analysis_type=analysis_type,
            region_name=region_name,
            **kwargs,
        )

        result = AnalysisResult(
            field_name=self.field_name,
            region_name=region_name,
            space="voxel",
            analysis_type=analysis_type,
            roi_mean=roi_mean,
            roi_max=roi_max,
            roi_min=roi_min,
            roi_focality=roi_focality,
            gm_mean=tissue_mean,
            gm_max=tissue_max,
            n_elements=int(np.sum(roi_mask)),
            total_area_or_volume=float(np.sum(roi_mask)) * voxel_vol,
            **focality,
            **carrier,
            on_demand_note=" ".join(self._on_demand) or None,
        )

        if visualize:
            self._visualize_voxel(
                field_arr,
                roi_mask,
                analysis_mask,
                affine,
                out_dir,
                result,
                analysis_type=analysis_type,
            )

        save_results_csv(asdict(result), Path(out_dir))
        self._save_metadata(out_dir, "voxel", analysis_type, kwargs)
        logger.info("Analysis complete for %s (%s)", region_name, analysis_type)
        return result

    def _save_metadata(
        self, out_dir, space: str, analysis_type: str, kwargs: dict
    ) -> None:
        """Write ``analysis.json`` for this run, beside its ``results.csv``.

        Every run writes it, visualized or not: the catalog lists a folder only when it holds
        both files, and a folder re-used by a later run must not keep an earlier run's field
        next to the new numbers.
        """
        spheres = kwargs.get("spheres")
        metadata = {
            "analysis_type": analysis_type,
            "space": space,
            "field_name": self.field_name,
        }
        if space == "voxel":
            metadata["tissue_types"] = self._tissue_type_list()
        metadata.update(
            {
                "atlas": kwargs.get("atlas"),
                "regions": kwargs.get("region_labels"),
                "center": list(spheres[0][:3]) if spheres else None,
                "radius": spheres[0][3] if spheres else None,
                "spheres": [list(sp) for sp in spheres] if spheres else None,
                "coordinate_space": kwargs.get("coordinate_space"),
            }
        )
        save_analysis_metadata(Path(out_dir), metadata)

    # ------------------------------------------------------------------
    # Surface mesh loading (lazy, cached)
    # ------------------------------------------------------------------

    def _load_surface_mesh(self):
        """Load the cortical surface mesh, cached on instance."""
        if self._surface_mesh is not None:
            return self._surface_mesh

        import simnibs

        # mTI runs write their central surface under mTI/mesh/surfaces/; only
        # 2-pair TI runs populate TI/mesh/surfaces/ (an mTI run's TI/mesh/
        # holds the intermediate per-dyad envelopes, with no surface).
        if self._is_mti:
            surface_path = Path(
                self._pm.mti_central_surface(self.subject_id, self.simulation)
            )
        else:
            surface_path = Path(
                self._pm.ti_central_surface(self.subject_id, self.simulation)
            )
        if not surface_path.exists():
            raise FileNotFoundError(
                f"Central surface not found at {surface_path}. Run simulation first."
            )
        self._surface_mesh = simnibs.read_msh(str(surface_path))
        self._surface_mesh_path = surface_path
        logger.info("Loaded surface mesh: %s", surface_path)
        return self._surface_mesh

    # ------------------------------------------------------------------
    # Normal field extraction (mesh only)
    # ------------------------------------------------------------------

    def _get_normal_stats(
        self,
        roi_mask: np.ndarray,
        node_areas: np.ndarray,
    ) -> dict | None:
        """Load the normal mesh and compute weighted ROI stats."""
        normal_path = self._normal_mesh_path()
        if normal_path is None or not normal_path.exists():
            logger.debug("Normal mesh not found, skipping normal stats")
            return None

        import simnibs

        normal_mesh = simnibs.read_msh(str(normal_path))
        if "TI_normal" not in normal_mesh.field:
            return None

        nf = normal_mesh.field["TI_normal"].value
        roi_nf = nf[roi_mask]
        pos = roi_nf > 0
        if not np.any(pos):
            return None

        areas = node_areas[roi_mask][pos]
        mean = float(np.average(roi_nf[pos], weights=areas))
        mx = float(np.max(roi_nf[pos]))

        gm_pos = nf > 0
        gm_areas_raw = self._node_areas(normal_mesh)
        gm_mean = float(np.average(nf[gm_pos], weights=gm_areas_raw[gm_pos]))
        focality = mean / gm_mean

        return {"mean": mean, "max": mx, "focality": focality}

    def _normal_mesh_path(self) -> Path | None:
        """Derive the normal mesh path from the field mesh path."""
        name = self.field_path.name
        replacements = {
            "_mTI.msh": "_mTI_normal.msh",
            "_TI.msh": "_normal.msh",
        }
        for suffix, replacement in replacements.items():
            if name.endswith(suffix):
                return self.field_path.parent / name.replace(suffix, replacement)
        return None

    # ------------------------------------------------------------------
    # Focality metrics
    # ------------------------------------------------------------------

    def _compute_focality_metrics(
        self,
        values: np.ndarray,
        weights: np.ndarray,
        weight_to_cm: float = 100.0,
    ) -> dict:
        """Compute percentile and area/volume focality metrics.

        Returns a dict with keys matching the optional fields on
        ``AnalysisResult``: ``percentile_95``, ``percentile_99``,
        ``percentile_99_9``, ``focality_50_area`` ... ``focality_95_area``.

        Parameters
        ----------
        weight_to_cm : float
            Divisor converting the summed *weights* to centimetre units:
            ``100`` for mesh node areas (mm^2 -> cm^2) and ``1000`` for voxel
            volumes (mm^3 -> cm^3).  It must track the unit of *weights*; v2.x
            hard-coded ``100`` and so reported voxel focality volumes 10x too
            large.
        """
        # NaN and +/-inf are not field values: an inf would become the 99.9th
        # percentile and zero every focality area.
        valid = np.isfinite(values)
        data = values[valid]
        sizes = weights[valid]

        pct_values = weighted_percentiles(data, sizes, (95, 99, 99.9))

        # Area/volume above X% of the 99.9th percentile value
        ref = pct_values[2]  # 99.9th percentile
        focality_cutoffs = [50, 75, 90, 95]
        foc_values = []
        for cutoff in focality_cutoffs:
            threshold = (cutoff / 100.0) * ref
            above = data >= threshold
            area = float(np.sum(sizes[above])) / weight_to_cm
            foc_values.append(area)

        return {
            "percentile_95": pct_values[0],
            "percentile_99": pct_values[1],
            "percentile_99_9": pct_values[2],
            "focality_50_area": foc_values[0],
            "focality_75_area": foc_values[1],
            "focality_90_area": foc_values[2],
            "focality_95_area": foc_values[3],
        }

    # ------------------------------------------------------------------
    # Carrier (stimulation-intensity) metrics
    # ------------------------------------------------------------------

    def _mesh_carriers(self, surface) -> dict | None:
        """``hf_peak`` / ``hf_rms`` node values on the central surface, or why there are none.

        Read from the surface the analysed field is on: ``msh2cortex`` maps every field of
        the TI/mTI mesh onto it, so the carrier fields went through the same interpolation as
        the modulation field. Both are there once :meth:`_produce_missing_fields` ran. Returns
        ``None`` when the analysed field is not a modulation field.
        """
        if self.field_name not in MODULATION_FIELDS:
            return None
        return {
            name: (
                np.asarray(surface.field[name].value, dtype=np.float64)
                if name in surface.field
                else self._carrier_reasons.get(name)
                or f"the central surface {self._surface_mesh_path} carries no {name}"
            )
            for name in (const.FIELD_HF_PEAK, const.FIELD_HF_RMS)
        }

    def _voxel_carriers(self, shape: tuple, affine: np.ndarray) -> dict | None:
        """``hf_peak`` / ``hf_rms`` on the analysed field's grid: an array, or the reason it
        cannot be used (both are written once :meth:`_produce_missing_fields` ran).

        mesh2nii names every field of one mesh ``<mesh stem>_<field>.nii.gz`` in one folder,
        so the carrier NIfTI of the same tissue is the analysed file with its field suffix
        swapped -- the same grid, written by the same conversion; a file on another grid
        (shape or affine) is refused by name. Returns ``None`` when the analysed field is not
        a modulation field.
        """
        if self.field_name not in MODULATION_FIELDS:
            return None
        import nibabel as nib

        name = self.field_path.name
        out: dict = {}
        for carrier in (const.FIELD_HF_PEAK, const.FIELD_HF_RMS):
            path = carrier_nifti(self.field_path, self.field_name, carrier)
            if path is None:
                out[carrier] = (
                    f"{name} is not named <mesh>_{self.field_name}.nii.gz, so its "
                    f"{carrier} NIfTI cannot be identified"
                )
                continue
            if not path.is_file():
                out[carrier] = self._carrier_reasons.get(
                    carrier, f"{path.name} is not in {path.parent}"
                )
                continue
            img = nib.load(str(path))
            arr = self._squeeze_4d(np.asarray(img.get_fdata()))
            if arr.shape[:3] != tuple(shape[:3]) or not np.allclose(
                np.asarray(img.affine, dtype=np.float64), affine
            ):
                out[carrier] = (
                    f"{path.name} is not on the grid of {name} (shape {arr.shape[:3]} "
                    f"vs {tuple(shape[:3])}, or another affine)"
                )
                continue
            out[carrier] = arr
        return out

    def _carrier_metrics(
        self,
        roi_focality: float,
        carriers: dict | None,
        roi_sel: np.ndarray,
        gm_sel: np.ndarray,
        roi_weights: np.ndarray,
        gm_weights: np.ndarray,
        weight_to_cm: float = 100.0,
    ) -> dict:
        """The carrier metrics of :class:`AnalysisResult`, on the modulation statistics' elements.

        *roi_sel* / *gm_sel* select the same elements ``roi_mean`` / ``gm_mean`` averaged
        (ROI and GM where the analysed field is positive), in the same order as
        *roi_weights* / *gm_weights*, so each carrier ratio is taken over exactly the
        elements of ``roi_focality``. ``hf_rms`` is used for the RMS ratio, not ``hf_power``:
        a ratio of mean squares would be a ratio of squared fields, not comparable with the
        linear ``roi_focality``. *carriers* maps ``hf_peak`` / ``hf_rms`` to their values or
        the reason they cannot be used (:meth:`_mesh_carriers`, :meth:`_voxel_carriers`);
        *carriers* ``None`` means the analysed field is a carrier field itself. A carrier with
        non-finite values on those elements, or a reference mean <= 0, has no focality. Every
        metric that cannot be computed is ``None``, ``carrier_note`` says why, and one warning
        per analysis says so; the modulation statistics are never affected.
        """
        out: dict = dict.fromkeys(CARRIER_RESULT_KEYS)
        if carriers is None:
            out["carrier_note"] = (
                f"{self.field_name} is not a modulation field; the carrier metrics are "
                f"reported for {', '.join(MODULATION_FIELDS)} analyses"
            )
            return out

        problems: list[str] = []

        def means(label: str, values: np.ndarray) -> tuple[float, float, float] | None:
            roi_values, gm_values = values[roi_sel], values[gm_sel]
            if not (np.isfinite(roi_values).all() and np.isfinite(gm_values).all()):
                problems.append(
                    f"{label} has NaN or inf values on the analysed elements"
                )
                return None
            gm = float(np.average(gm_values, weights=gm_weights))
            if gm <= 0:
                problems.append(
                    f"{label}'s mean over the reference elements is {gm:g}, so its "
                    "focality is undefined"
                )
                return None
            roi = float(np.average(roi_values, weights=roi_weights))
            return roi, gm, roi / gm

        peak = carriers[const.FIELD_HF_PEAK]
        if isinstance(peak, str):
            problems.append(peak)
        elif (stats := means(const.FIELD_HF_PEAK, peak)) is not None:
            roi, gm, hf_peak_focality = stats
            areas = self._compute_focality_metrics(
                peak[gm_sel], gm_weights, weight_to_cm
            )
            out.update(
                hf_peak_roi_mean=roi,
                hf_peak_gm_mean=gm,
                hf_peak_focality=hf_peak_focality,
                ti_selectivity=roi_focality / hf_peak_focality,
                **{
                    f"hf_peak_{key}": areas[key]
                    for key in (
                        "focality_50_area",
                        "focality_75_area",
                        "focality_90_area",
                        "focality_95_area",
                    )
                },
            )
        rms = carriers[const.FIELD_HF_RMS]
        if isinstance(rms, str):
            problems.append(rms)
        elif (stats := means(const.FIELD_HF_RMS, rms)) is not None:
            roi, gm, hf_rms_focality = stats
            out.update(
                hf_rms_roi_mean=roi, hf_rms_gm_mean=gm, hf_rms_focality=hf_rms_focality
            )
        if problems:
            out["carrier_note"] = "; ".join(problems) + "."
            logger.warning("Carrier metrics incomplete: %s", out["carrier_note"])
        return out

    # ------------------------------------------------------------------
    # Visualization helpers
    # ------------------------------------------------------------------

    def _visualize_mesh(
        self,
        surface,
        values,
        roi_mask,
        out_dir,
        result,
        gm_values,
        gm_areas,
        roi_values,
        roi_areas,
        *,
        analysis_type: str = "cortical",
    ) -> None:
        from tit.analyzer.scene import write_mesh_scene

        out = Path(out_dir)
        overlay = save_mesh_roi_overlay(
            surface_mesh_path=self._surface_mesh_path,
            field_values=values,
            roi_mask=roi_mask,
            field_name=self.field_name,
            output_dir=out,
            normal_mesh_path=self._normal_mesh_path(),
        )
        write_mesh_scene(
            out_dir=str(out),
            mesh=str(overlay),
            roi_coords=surface.nodes.node_coord[roi_mask],
            node_coords=surface.nodes.node_coord,
            roi_values=values[roi_mask],
            field_name=self.field_name,
            region_name=result.region_name,
            normal_max=result.normal_max,
            meta={
                "roi": result.region_name,
                "space": "mesh",
                "analysis_type": analysis_type,
            },
        )
        save_histogram(
            whole_head_values=gm_values,
            roi_values=roi_values,
            output_dir=out,
            whole_head_weights=gm_areas,
            roi_weights=roi_areas,
            roi_mean=result.roi_mean,
            region_name=result.region_name,
            unit_label="Area (mm\u00b2)",
            field_name=self.field_name,
        )

    def _visualize_voxel(
        self,
        field_arr,
        roi_mask,
        analysis_mask,
        affine,
        out_dir,
        result,
        *,
        analysis_type: str = "cortical",
    ) -> None:
        from tit.analyzer.scene import write_voxel_scene

        out = Path(out_dir)
        overlay = save_nifti_roi_overlay(
            field_data=field_arr,
            roi_mask=roi_mask,
            output_dir=out,
            affine=affine,
        )
        write_voxel_scene(
            out_dir=str(out),
            anatomy=str(Path(self.m2m_path) / "T1.nii.gz"),
            overlay=str(overlay),
            roi_mask=roi_mask,
            affine=affine,
            roi_values=field_arr[roi_mask],
            field_name=self.field_name,
            region_name=result.region_name,
            meta={
                "roi": result.region_name,
                "space": "voxel",
                "analysis_type": analysis_type,
            },
        )
        voxel_vol = voxel_volume_mm3(affine)
        tissue_values = field_arr[analysis_mask]
        roi_values = field_arr[roi_mask]
        save_histogram(
            whole_head_values=tissue_values,
            roi_values=roi_values,
            output_dir=out,
            whole_head_weights=np.full(tissue_values.shape, voxel_vol),
            roi_weights=np.full(roi_values.shape, voxel_vol),
            roi_mean=result.roi_mean,
            region_name=result.region_name,
            unit_label="Volume (mm\u00b3)",
            field_name=self.field_name,
        )

    # ------------------------------------------------------------------
    # Output directory resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _checked_spheres(spheres) -> list[tuple[float, float, float, float]]:
        """``(x, y, z, r)`` floats: a finite centre and a positive, finite radius (mm)."""
        checked = []
        for sphere in spheres:
            values = tuple(float(v) for v in sphere)
            if len(values) != 4 or not np.all(np.isfinite(values)) or values[3] <= 0:
                raise ValueError(
                    "A sphere needs a finite centre (x, y, z) and a positive, finite "
                    f"radius in mm; got {tuple(sphere)!r}"
                )
            checked.append(values)
        return checked

    @staticmethod
    def _sphere_region_name(spheres) -> str:
        """Name a spherical ROI: one sphere keeps the classic name."""
        parts = [f"sphere_x{x:.2f}_y{y:.2f}_z{z:.2f}_r{r}" for x, y, z, r in spheres]
        return "+".join(parts)

    def _resolve_output_dir(
        self,
        *,
        analysis_type: str,
        region_name: str,
        **kwargs,
    ) -> str:
        if self.output_dir is not None:
            self._pm.ensure(self.output_dir)
            return self.output_dir

        # The field and tissue are part of the folder's identity: TI_max and hf_peak (or GM
        # and WM) of one ROI are two analyses, not one that the second run replaces.
        pm_kwargs: dict = {
            "sid": self.subject_id,
            "sim": self.simulation,
            "space": self.space,
            "analysis_type": analysis_type,
            "field": self.field_name,
            "tissue": self.tissue_type,
        }

        if analysis_type == "spherical":
            spheres = kwargs.get("spheres") or [
                tuple(kwargs.get("center", (0, 0, 0))) + (kwargs.get("radius", 0),)
            ]
            pm_kwargs["coordinates"] = list(spheres[0][:3])
            pm_kwargs["radius"] = spheres[0][3]
            pm_kwargs["coordinate_space"] = kwargs.get("coordinate_space", "subject")
            if len(spheres) > 1:
                pm_kwargs["spheres"] = spheres
        else:
            # A mesh atlas analysis names its folder by the request (``region_key``), not
            # by the hemisphere keys a bare name resolved to: the plan cannot read the atlas.
            pm_kwargs["region"] = kwargs.get("region_key") or region_name
            pm_kwargs["atlas_name"] = kwargs.get("atlas")

        out = self._pm.analysis_output_dir(**pm_kwargs)
        self._pm.ensure(out)
        return out

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_mesh_region(name: str, atlas_map) -> list[str]:
        """Resolve a region name to atlas key(s).

        - Direct match: ``"lh.cuneus"`` → ``["lh.cuneus"]``
        - Bare name: ``"cuneus"`` → ``["lh.cuneus", "rh.cuneus"]`` (both hemis)
        """
        if name in atlas_map:
            return [name]

        # Bare name → expand to both hemispheres
        found = [f"{h}.{name}" for h in ("lh", "rh") if f"{h}.{name}" in atlas_map]
        if found:
            return found

        raise KeyError(f"Region {name!r} not found in atlas.")

    def _maybe_transform_coords(
        self,
        center: tuple[float, float, float],
        coordinate_space: str,
    ) -> np.ndarray:
        """Return *center* in subject space, transforming from MNI if needed."""
        arr = np.array([list(center)], dtype=float)
        if coordinate_space.upper() == "MNI":
            from simnibs import mni2subject_coords

            arr = mni2subject_coords(arr, str(self.m2m_path))
            arr = np.atleast_2d(arr)
        return arr[0]

    # ------------------------------------------------------------------
    # Field / mesh helpers
    # ------------------------------------------------------------------

    def _field_values(self, surface) -> np.ndarray:
        """Extract the named field from the surface mesh.

        If the field is a vector (N x 3), the magnitude is returned. ``TI_normal`` is not on
        the central surface (``msh2cortex`` maps the TI mesh's fields only); it is read from
        the normal mesh :func:`select_field_file` resolved, which is node data on the same
        central-surface nodes.

        Raises
        ------
        ValueError
            If the field is on neither, naming the fields the surface does carry.
        """
        try:
            v = surface.field[self.field_name].value
        except KeyError:
            if self.field_name != const.FIELD_TI_NORMAL:
                carried = ", ".join(sorted(surface.field)) or "no fields"
                raise ValueError(
                    f"Field {self.field_name!r} is not on the central surface "
                    f"{self._surface_mesh_path} (it carries: {carried}). Re-run the "
                    f"simulation with {self.field_name} among its output fields, or "
                    "analyze it in voxel space."
                ) from None
            v = self._normal_mesh_values(surface)
        if v.ndim == 2:
            return np.linalg.norm(v, axis=1)
        return v

    def _normal_mesh_values(self, surface) -> np.ndarray:
        """``TI_normal`` node data from the normal mesh, checked against *surface*'s nodes."""
        import simnibs

        normal_mesh = simnibs.read_msh(str(self.field_path))
        try:
            values = np.asarray(normal_mesh.field[const.FIELD_TI_NORMAL].value)
        except KeyError:
            raise ValueError(
                f"{self.field_path} carries no {const.FIELD_TI_NORMAL} field"
            ) from None
        n_nodes = len(surface.nodes.node_coord)
        if len(values) != n_nodes:
            raise ValueError(
                f"{self.field_path} has {len(values)} {const.FIELD_TI_NORMAL} values but "
                f"the central surface {self._surface_mesh_path} has {n_nodes} nodes; "
                "re-run the simulation so both come from the same surface."
            )
        return values

    @staticmethod
    def _node_areas(surface) -> np.ndarray:
        """Return per-node areas as a plain ndarray."""
        areas = surface.nodes_areas()
        if hasattr(areas, "value"):
            areas = areas.value
        return np.asarray(areas)

    @staticmethod
    def _require_label_voxels(mask: np.ndarray, name, rid: int, atlas_path) -> None:
        """Refuse a region whose label has no voxel in the atlas (on the grid read)."""
        if not np.any(mask):
            raise ValueError(
                f"Region {str(name)!r} (label {rid}) has no voxels in atlas {atlas_path}"
            )

    @staticmethod
    def _squeeze_4d(arr: np.ndarray) -> np.ndarray:
        """Collapse a 4-D array to 3-D by taking the first volume."""
        if arr.ndim == 4:
            return arr[:, :, :, 0]
        return arr

    @staticmethod
    def _normalize_tissue_type(tissue_type: str) -> str:
        normalized = str(tissue_type or "GM").strip().upper()
        if normalized not in {"GM", "WM", "BOTH"}:
            raise ValueError(
                f"Unsupported tissue_type: {tissue_type!r} (expected 'GM', 'WM', or 'both')"
            )
        return normalized

    def _tissue_type_list(self) -> list[str]:
        """Return tissue selection as a list of tissue names."""
        if self.tissue_type == "BOTH":
            return ["GM", "WM"]
        return [self.tissue_type]

    def _voxel_tissue_mask(
        self,
        target_shape: tuple[int, int, int],
        target_affine: np.ndarray,
    ) -> np.ndarray:
        """Return a voxel mask for the configured tissue selection.

        Mesh analysis is always GM surface-based; tissue selection only applies to voxel
        analyses. ``GM`` and ``WM`` can use the tissue-specific field NIfTIs directly.
        ``BOTH`` requires an explicit GM|WM union mask so that non-brain voxels from the
        full-field NIfTI are excluded.
        """
        if self.tissue_type == "GM" and self.field_path.name.startswith("grey_"):
            return np.ones(target_shape[:3], dtype=bool)
        if self.tissue_type == "WM" and self.field_path.name.startswith("white_"):
            return np.ones(target_shape[:3], dtype=bool)

        base_name = self.field_path.name
        for prefix in ("grey_", "white_"):
            if base_name.startswith(prefix):
                base_name = base_name[len(prefix) :]
                break

        prefixes = (
            ("grey_", "white_")
            if self.tissue_type == "BOTH"
            else ("grey_",) if self.tissue_type == "GM" else ("white_",)
        )

        import nibabel as nib

        mask = np.zeros(target_shape[:3], dtype=bool)
        for prefix in prefixes:
            tissue_path = self.field_path.parent / f"{prefix}{base_name}"
            if not tissue_path.exists():
                logger.warning("Tissue mask NIfTI not found: %s", tissue_path)
                continue

            tissue_img = nib.load(str(tissue_path))
            tissue_arr = self._squeeze_4d(tissue_img.get_fdata())
            tissue_arr = self._resample_if_needed(
                tissue_img,
                tissue_arr,
                target_shape,
                target_affine,
                tissue_path,
            )
            mask |= tissue_arr > 0

        return mask

    # ------------------------------------------------------------------
    # Voxel atlas helpers
    # ------------------------------------------------------------------

    # SimNIBS surface atlas id -> the FreeSurfer/FastSurfer volume parcellation
    # carrying the same regions, in search order. The desktop's cortical picker
    # names the atlas by its surface id in every space, so a voxel analysis of
    # "DK40" reads the DKT volume. HCP_MMP1 has no volume counterpart.
    _SURFACE_ATLAS_VOLUMES = {
        "DK40": (
            "aparc.DKTatlas+aseg.deep.mgz",
            "aparc.DKTatlas+aseg.deep.nii.gz",
            "aparc.DKTatlas+aseg.mgz",
        ),
        "a2009s": ("aparc.a2009s+aseg.mgz",),
    }

    @classmethod
    def voxel_atlas_candidates(cls, pm, sid: str, atlas: str) -> list[Path]:
        """Every path :meth:`_resolve_voxel_atlas` tries for *atlas* name, in search order.

        Shared with :mod:`tit.jobs.preflight`, so the submit-time check and the runner
        cannot disagree about where a subject's volume atlas lives.
        """
        fs_mri = Path(pm.fastsurfer_mri(sid))
        legacy_mri = Path(pm.freesurfer_mri(sid))
        seg_dir = Path(pm.segmentation(sid))
        if atlas in cls._SURFACE_ATLAS_VOLUMES:
            return [
                mri / name
                for name in cls._SURFACE_ATLAS_VOLUMES[atlas]
                for mri in (fs_mri, legacy_mri)
            ]
        return [
            fs_mri / atlas,
            legacy_mri / atlas,
            seg_dir / atlas,
            fs_mri / f"{atlas}.mgz",
            fs_mri / f"{atlas}.nii.gz",
            fs_mri / f"{atlas}.nii",
            legacy_mri / f"{atlas}.mgz",
            legacy_mri / f"{atlas}.nii.gz",
            legacy_mri / f"{atlas}.nii",
            seg_dir / f"{atlas}.nii.gz",
            seg_dir / f"{atlas}.nii",
            # The catalog lists a custom label volume as "masks/<file>" (VoxelAtlasManager).
            Path(pm.masks(sid)).parent / atlas,
        ]

    def _resolve_voxel_atlas(self, atlas: str) -> Path:
        """Find the atlas NIfTI/MGZ file for voxel-space analysis."""
        if Path(atlas).is_file():
            return Path(atlas)

        for path in self.voxel_atlas_candidates(self._pm, self.subject_id, atlas):
            if path.exists():
                return path
        fs_mri = Path(self._pm.fastsurfer_mri(self.subject_id))
        legacy_mri = Path(self._pm.freesurfer_mri(self.subject_id))
        seg_dir = Path(self._pm.segmentation(self.subject_id))
        if atlas in self._SURFACE_ATLAS_VOLUMES:
            raise FileNotFoundError(
                f"Atlas {atlas!r} has no volume parcellation for subject "
                f"{self.subject_id}: none of "
                f"{', '.join(self._SURFACE_ATLAS_VOLUMES[atlas])} found in "
                f"{fs_mri} or {legacy_mri}. Run FastSurfer/recon-all for this "
                "subject or analyze in mesh space."
            )
        raise FileNotFoundError(
            f"Atlas {atlas!r} not found in {fs_mri}, {legacy_mri}, or {seg_dir}"
        )

    @staticmethod
    def _resolve_mni_atlas(atlas: str) -> Path:
        """A shipped MNI atlas by its id (file name), or an MNI atlas file path."""
        from tit.atlas.manifest import check_shipped, mni_atlas_entry

        check_shipped(atlas)
        entry = mni_atlas_entry(Path(atlas).name)
        if entry is not None:
            return Path(entry["path"])
        if Path(atlas).is_file():
            return Path(atlas)
        raise FileNotFoundError(
            f"MNI atlas {atlas!r} is not one of the shipped MNI atlases "
            "(resources/atlas/manifest.json) and is not a file"
        )

    @staticmethod
    def _resample_if_needed(
        src_img,
        src_arr: np.ndarray,
        target_shape: tuple,
        target_affine: np.ndarray,
        src_path: Path,
    ) -> np.ndarray:
        """Resample a label/mask volume onto the target voxel grid.

        Used for both atlas parcellations and tissue masks. Both carry
        *discrete* values -- region ids and 0/1 flags -- so resampling is
        nearest-neighbour (``order=0``); any interpolating order would invent
        region ids that exist in neither the source nor the lookup table.
        Voxels falling outside the source field of view become 0 (background).

        A volume is left untouched only when it already shares the target's
        shape *and* affine. Shape alone is not sufficient: two volumes can
        agree on shape while sampling entirely different anatomy.

        The result is cached next to *src_path*, keyed by the target grid, so
        repeated analyses on the same grid pay the cost once. Caching is
        best-effort -- an unwritable cache location degrades to recomputing
        in memory rather than failing the analysis.
        """
        import nibabel as nib
        from nibabel.processing import resample_from_to

        src_arr = np.asanyarray(src_arr)
        target_shape = tuple(int(n) for n in target_shape[:3])
        target_affine = np.asarray(target_affine, dtype=float)

        if src_arr.shape[:3] == target_shape and np.allclose(
            src_img.affine, target_affine, atol=1e-5
        ):
            return src_arr

        src_path = Path(src_path)
        cached_path = src_path.parent / Analyzer._resampled_name(
            src_path, target_shape, target_affine
        )

        cached = Analyzer._load_cached_resample(cached_path, target_shape)
        if cached is not None:
            return cached

        logger.info(
            "Resampling %s: %s -> %s (nearest-neighbour)",
            src_path.name,
            src_arr.shape[:3],
            target_shape,
        )

        # Rebuild the source image from the array actually passed in: the
        # caller may have squeezed a trailing singleton axis off a 4D volume,
        # so src_img.dataobj is not necessarily what we want to resample.
        source = nib.Nifti1Image(src_arr, src_img.affine)
        resampled = np.asanyarray(
            resample_from_to(source, (target_shape, target_affine), order=0).dataobj
        )

        Analyzer._cache_resample(resampled, target_affine, cached_path)
        return resampled

    @staticmethod
    def _resampled_name(
        src_path: Path, target_shape: tuple, target_affine: np.ndarray
    ) -> str:
        """Cache filename encoding the full target grid, not just its shape.

        The affine is part of the key because shape alone does not identify a
        grid -- a cache keyed on shape would hand back a volume resampled to a
        different anatomy whenever two grids happen to share dimensions.

        The stem keeps every dotted component of the filename except the image
        extension. Truncating at the first dot would collapse
        ``aparc.DKTatlas+aseg`` and ``aparc.a2009s+aseg`` onto one key, so an
        analysis of either atlas could be served the other's labels.

        The source's size and modification time are part of the key too: the
        cache sits beside a subject's FastSurfer/FreeSurfer outputs, which a
        sub-region re-run or a recon outside the app rewrites in place, and a
        key of the grid alone kept serving the old labels.
        """
        sx, sy, sz = target_shape
        try:
            stat = Path(src_path).stat()
            source = f"{stat.st_size}:{stat.st_mtime_ns}".encode()
        except OSError:
            source = b""
        # blake2b, not sha1: this is a cache key, never a security boundary,
        # and blake2b takes the digest length directly.
        digest = hashlib.blake2b(
            np.round(target_affine, 5).astype(np.float64).tobytes() + source,
            digest_size=4,
        ).hexdigest()
        name = src_path.name
        for ext in (".nii.gz", ".nii", ".mgz", ".mgh"):
            if name.lower().endswith(ext):
                name = name[: -len(ext)]
                break
        stem = name.replace(".", "_")
        return f"{stem}_resampled_{sx}x{sy}x{sz}_{digest}.nii.gz"

    @staticmethod
    def _load_cached_resample(cached_path: Path, target_shape: tuple):
        """Return the cached resample, or None if absent/unusable.

        A truncated or corrupt cache file is treated as a cache miss rather
        than an error: it is a derived artefact and is safe to regenerate.
        """
        cached_path = Path(cached_path)
        if not cached_path.exists():
            return None

        import nibabel as nib
        from nibabel.processing import resample_from_to

        try:
            arr = np.asanyarray(nib.load(str(cached_path)).dataobj)
        except Exception as exc:  # noqa: BLE001 - any read failure is a miss
            logger.warning(
                "Ignoring unreadable resample cache %s (%s); regenerating.",
                cached_path,
                exc,
            )
            return None

        if arr.shape[:3] != target_shape:
            logger.warning(
                "Resample cache %s has shape %s, expected %s; regenerating.",
                cached_path,
                arr.shape[:3],
                target_shape,
            )
            return None

        logger.debug("Reusing cached resample: %s", cached_path)
        return arr

    @staticmethod
    def _cache_resample(arr: np.ndarray, affine: np.ndarray, cached_path: Path) -> None:
        """Write the resample cache; never raise.

        Written via a temporary directory and copied into place: nibabel's
        gzip writer is unreliable directly on Docker bind mounts, and the copy
        keeps a reader from ever seeing a half-written file.
        """
        import gzip
        import shutil

        import nibabel as nib

        cached_path = Path(cached_path)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_nii = Path(tmpdir) / "resampled.nii"
                tmp_gz = Path(tmpdir) / "resampled.nii.gz"
                nib.save(nib.Nifti1Image(arr, affine), str(tmp_nii))
                with open(tmp_nii, "rb") as f_in, gzip.open(str(tmp_gz), "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                shutil.copy2(str(tmp_gz), str(cached_path))
            logger.debug("Cached resample: %s", cached_path)
        except OSError as exc:
            logger.warning(
                "Could not cache resample to %s (%s); continuing in memory.",
                cached_path,
                exc,
            )

    #: DK40 surface regions the DKT volume parcellation (``aparc.DKTatlas+aseg``, FastSurfer's
    #: and recon-all's) does not carry: the DKT protocol dropped the banks of the superior
    #: temporal sulcus, the frontal and temporal poles and the corpus callosum (Klein &
    #: Tourville 2012). A voxel DK40 analysis of one cannot be measured.
    DKT_VOLUME_LACKS = frozenset(
        {"bankssts", "corpuscallosum", "frontalpole", "temporalpole"}
    )

    @classmethod
    def surface_regions_without_volume(cls, atlas: str, regions) -> list[str]:
        """The names in *regions* a voxel analysis of surface atlas *atlas* cannot measure.

        Shared with :mod:`tit.jobs.preflight`, so such a region is refused at submit, not
        after the job started. Only ``DK40`` (read from the DKT volume) has any.
        """
        if atlas != "DK40":
            return []
        return [
            str(r)
            for r in regions
            if re.sub(r"^(lh|rh)[._-]", "", str(r).strip().lower())
            in cls.DKT_VOLUME_LACKS
        ]

    @staticmethod
    def _find_voxel_region_id(
        atlas_path: Path,
        region: str,
    ) -> int:
        """Resolve a region name to its integer label in the atlas volume.

        Pure-Python replacement for shelling out to ``mri_segstats``: labels
        actually present in the volume (:func:`~tit.atlas.segstats.compute_segstats`)
        are named via :func:`~tit.atlas.segstats.resolve_lut_for_atlas`. The exact
        name, or a surface-style hemisphere name's volume spelling, names one label;
        otherwise the one label whose name contains *region*. A name contained in
        several labels' names (a bare ``"insula"`` is in ``ctx-lh-insula`` and
        ``ctx-rh-insula``) is refused rather than resolved to the lowest id, which
        measured the left hemisphere only while a mesh analysis of the same name
        measures both.

        Raises:
            ValueError: *region* names no label present in the volume, or several.
        """
        region_stripped = region.strip()
        if region_stripped.isdigit():
            return int(region_stripped)

        lut = resolve_lut_for_atlas(str(atlas_path))
        stats = compute_segstats(str(atlas_path), lut)
        labels = [(stat.seg_id, stat.name) for stat in stats]
        hits = Analyzer._region_label_matches(region_stripped, labels)
        if len(hits) > 1:
            names = ", ".join(f"{name} ({rid})" for rid, name in hits[:6])
            more = f" and {len(hits) - 6} more" if len(hits) > 6 else ""
            raise ValueError(
                f"Region '{region}' matches {len(hits)} labels in atlas {atlas_path}: "
                f"{names}{more}. Name one exactly (e.g. 'lh.insula' or "
                "'Left-Thalamus'), or list each region to analyze their union."
            )
        if not hits:
            bare = re.sub(r"^(lh|rh)[._-]", "", region_stripped.lower())
            if bare in Analyzer.DKT_VOLUME_LACKS:
                raise ValueError(
                    f"Region '{region}' is a DK40 surface region the DKT volume "
                    f"parcellation {atlas_path} does not have; analyze it in mesh space."
                )
            raise ValueError(f"Region '{region}' not found in atlas {atlas_path}")
        return hits[0][0]

    @staticmethod
    def _region_label_matches(region: str, labels) -> list[tuple[int, str]]:
        """``(id, name)`` of the labels *region* names: one exact match, or every substring hit.

        The exact name (any case) wins, then a surface-style hemisphere name's volume
        spelling; only without either are the names containing *region* returned, in
        *labels*' order.
        """
        region_lower = region.strip().lower()
        # The exact name wins over a longer one containing it: hippocampal subfields list
        # "parasubiculum" (203) before "subiculum" (205).
        for rid, name in labels:
            if name.lower() == region_lower:
                return [(rid, name)]
        # A surface-style name ("lh.insula") is spelled "ctx-lh-insula" in the
        # DKT volume and "ctx_lh_G_insular_short" in the a2009s one; try the
        # exact volume spellings before falling back to substring matching.
        hemi_match = re.fullmatch(r"(lh|rh)[._-](.+)", region_lower)
        if hemi_match:
            hemi, hemi_name = hemi_match.groups()
            exact = {f"ctx-{hemi}-{hemi_name}", f"ctx_{hemi}_{hemi_name}"}
            for rid, name in labels:
                if name.lower() in exact:
                    return [(rid, name)]
        return [(rid, name) for rid, name in labels if region_lower in name.lower()]

    @staticmethod
    def match_region_label(region: str, labels) -> int | None:
        """The label id whose name *region* names, or ``None``.

        *labels* is ``(id, name)`` pairs in ascending id order. The exact name (any case)
        wins, then a surface-style hemisphere name's volume spelling, then the first name
        containing *region*. Shared with :mod:`tit.jobs.preflight`, which matches against
        the atlas's whole lookup table -- names the volume may not carry -- so it only
        asks whether *region* names anything; the runner
        (:meth:`_find_voxel_region_id`) refuses a name several present labels contain.
        """
        hits = Analyzer._region_label_matches(region, labels)
        return hits[0][0] if hits else None
