"""Configuration dataclasses for TI optimization.

Pure Python -- no SimNIBS, numpy, or heavy dependencies.
Mirrors the ``tit.sim.config`` pattern.

Public API
----------
FlexConfig
    Full configuration for flex-search (differential-evolution) optimization.
FlexResult
    Result container for a completed flex-search run.
ExConfig
    Full configuration for exhaustive (grid) search optimization.
ExResult
    Result container for a completed exhaustive search run.

See Also
--------
tit.opt.flex.flex.run_flex_search : Consumes :class:`FlexConfig`.
tit.opt.ex.ex.run_ex_search : Consumes :class:`ExConfig`.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


def _as_list(value) -> list:
    """Wrap a scalar in a single-element list; pass lists/tuples through.

    Strings are treated as scalars (``"lh"`` -> ``["lh"]``), never iterated
    character-by-character.  Used to normalise ROI fields that accept either a
    single value (one region) or a list (a union of several regions).
    """
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


# ── Flex-search config ───────────────────────────────────────────────────────


@dataclass
class FlexConfig:
    """Full configuration for flex-search optimization.

    Wraps all parameters needed to drive a SimNIBS
    ``TesFlexOptimization`` run, including subject, ROI definition,
    electrode geometry, DE hyperparameters, and output control.

    Attributes
    ----------
    subject_id : str
        Subject identifier matching the m2m directory name.
    goal : OptGoal
        Optimization objective (``"mean"``, ``"max"``, or ``"focality"``).
    postproc : FieldPostproc
        Field post-processing method (``"max_TI"``, ``"dir_TI_normal"``,
        or ``"dir_TI_tangential"``).
    current_mA : float
        Total injected current in milliamps.
    electrode : ElectrodeConfig
        Electrode geometry configuration.
    roi : SphericalROI or AtlasROI or SubcorticalROI
        Target region of interest.
    anisotropy_type : str
        Conductivity tensor type (``"scalar"`` or ``"vn"``).
    aniso_maxratio : float
        Maximum anisotropy eigenvalue ratio.
    aniso_maxcond : float
        Maximum anisotropic conductivity (S/m).
    non_roi_method : NonROIMethod or None
        How to define the non-ROI region for focality optimization.
        ``None`` when goal is not focality.
    non_roi : SphericalROI or AtlasROI or SubcorticalROI or None
        Explicit non-ROI region when *non_roi_method* is ``"specific"``.
    thresholds : str or None
        Comma-separated focality threshold values (e.g. ``"0.1,0.2"``).
    eeg_net : str or None
        EEG net name or filename (e.g. ``"GSN-HydroCel-185"`` or
        ``"GSN-HydroCel-185.csv"``) for electrode-name mapping.
        ``None`` to use raw electrode indices.
    enable_mapping : bool
        If True, map optimal indices to named EEG positions.
    disable_mapping_simulation : bool
        If True, skip the final named-electrode simulation after mapping.
    output_folder : str or None
        Override for the output directory path.  Defaults to an
        auto-generated timestamped folder.
    run_final_electrode_simulation : bool
        If True, run a full SimNIBS simulation with the winning
        electrode configuration.
    n_multistart : int
        Number of independent DE restarts.  Higher values reduce
        sensitivity to local optima.
    max_iterations : int or None
        Maximum DE generations per restart.  ``None`` for solver default.
    population_size : int or None
        DE population size.  ``None`` for solver default.
    tolerance : float or None
        Convergence tolerance for DE.  ``None`` for solver default.
    mutation : str or None
        DE mutation strategy string.  ``None`` for solver default.
    recombination : float or None
        DE crossover probability.  ``None`` for solver default.
    cpus : int or None
        Number of parallel workers.  ``None`` for auto-detect.
    min_electrode_distance : float
        Minimum geodesic distance (mm) between any two electrodes.
    detailed_results : bool
        If True, save per-restart detailed output.
    visualize_valid_skin_region : bool
        If True, save a mesh showing the valid electrode placement region.
    skin_visualization_net : str or None
        EEG net to overlay on the skin visualization.
    skin_region_margin_mm : float
        Signed margin in millimeters applied to the SimNIBS valid-skin
        region. Positive values expand the region, negative values
        constrict it. The default ``0.0`` preserves SimNIBS behavior.
    avoid_landmark_regions : bool
        If True, positive skin-region margins keep fiducial-derived
        ear and orbital exclusion regions invalid.

    Raises
    ------
    ValueError
        If *goal* is ``"focality"`` with *non_roi_method* ``"specific"``
        but *non_roi* is ``None``, or if *thresholds* contains
        non-numeric values.

    See Also
    --------
    FlexResult : Result container returned by :func:`~tit.opt.flex.flex.run_flex_search`.
    tit.opt.flex.flex.run_flex_search : Consumes this config.
    """

    # ── Nested enums ──────────────────────────────────────────────────

    class OptGoal(StrEnum):
        """Optimization goal.

        Attributes
        ----------
        MEAN : str
            Maximize mean field intensity in the ROI.
        MAX : str
            Maximize peak field intensity in the ROI.
        FOCALITY : str
            Maximize ROI-to-non-ROI intensity ratio.
        """

        MEAN = "mean"
        MAX = "max"
        FOCALITY = "focality"

    class FieldPostproc(StrEnum):
        """Field post-processing method applied to the TI envelope.

        Attributes
        ----------
        MAX_TI : str
            Maximum TI amplitude (direction-independent).
        DIR_TI_NORMAL : str
            TI component normal to the cortical surface.
        DIR_TI_TANGENTIAL : str
            TI component tangential to the cortical surface.
        """

        MAX_TI = "max_TI"
        DIR_TI_NORMAL = "dir_TI_normal"
        DIR_TI_TANGENTIAL = "dir_TI_tangential"

    class NonROIMethod(StrEnum):
        """Non-ROI specification method for focality optimization.

        Attributes
        ----------
        EVERYTHING_ELSE : str
            Use all mesh elements outside the ROI.
        SPECIFIC : str
            Use an explicitly defined non-ROI region.
        """

        EVERYTHING_ELSE = "everything_else"
        SPECIFIC = "specific"

    # ── Nested ROI types ──────────────────────────────────────────────

    @dataclass
    class SphericalROI:
        """Spherical region of interest defined by center and radius.

        By default the sphere is evaluated on the cortical surface
        (``volumetric=False``).  Set ``volumetric=True`` to evaluate on
        volume tetrahedra instead -- useful for deep/subcortical targets
        like the amygdala or hippocampus where surface-only evaluation
        would capture overlying cortex rather than the target structure.

        When ``volumetric=True``, the *tissues* field controls which
        tissue compartments are included (same semantics as
        :class:`SubcorticalROI.tissues`).

        Each of *x*, *y*, *z*, *radius* accepts either a single value (one
        sphere) or a list of values (a union of several spheres evaluated as
        one combined target).  The coordinate lists must be non-empty and of
        equal length; *radius* may be a scalar (shared by every sphere) or a
        list matching the number of centers.

        Attributes
        ----------
        x : float or list of float
            Center x-coordinate(s) (mm).
        y : float or list of float
            Center y-coordinate(s) (mm).
        z : float or list of float
            Center z-coordinate(s) (mm).
        radius : float or list of float
            Sphere radius/radii in mm.  A scalar is shared by all spheres.
        use_mni : bool
            If True, coordinates are in MNI space and SimNIBS will transform
            them to subject space during ROI setup.
        volumetric : bool
            If True, evaluate on volume tetrahedra instead of the cortical
            surface.
        tissues : str
            Tissue compartments to include when *volumetric* is True.
            One of ``"GM"``, ``"WM"``, or ``"both"``.

        Raises
        ------
        ValueError
            If *x*/*y*/*z* are empty or unequal length, or *radius* is a list
            whose length neither equals 1 nor the number of centers.
        """

        x: float | list[float]
        y: float | list[float]
        z: float | list[float]
        radius: float | list[float] = 10.0
        use_mni: bool = False
        volumetric: bool = False
        tissues: str = "GM"  # "GM", "WM", or "both" — only used when volumetric=True

        def __post_init__(self):
            xs, ys, zs = _as_list(self.x), _as_list(self.y), _as_list(self.z)
            if not xs or not (len(xs) == len(ys) == len(zs)):
                raise ValueError(
                    "SphericalROI x, y, z must be non-empty and of equal length"
                )
            if len(_as_list(self.radius)) not in (1, len(xs)):
                raise ValueError(
                    "SphericalROI radius must be a scalar or match the number of "
                    "centers"
                )

    @dataclass
    class AtlasROI:
        """Cortical surface ROI from a FreeSurfer annotation atlas.

        Each of *atlas_path*, *label*, *hemisphere* accepts either a single
        value (one region) or a list (a union of several regions evaluated as
        one combined target).  Because ``.annot`` files are per-hemisphere,
        carrying a per-region *hemisphere* (and matching *atlas_path*) allows a
        target that spans **both** hemispheres, or even different atlases.
        Scalars broadcast to the number of labels; lists must match its length.

        Attributes
        ----------
        atlas_path : str or list of str
            Path(s) to the FreeSurfer ``.annot`` annotation file(s).
        label : int or list of int
            Integer label index/indices within the annotation atlas.
        hemisphere : str or list of str
            Hemisphere(s) to use (``"lh"`` or ``"rh"``), one per label.

        Raises
        ------
        ValueError
            If *label* is empty, or *atlas_path*/*hemisphere* is a list whose
            length neither equals 1 nor the number of labels.
        """

        atlas_path: str | list[str]
        label: int | list[int]
        hemisphere: str | list[str] = "lh"

        def __post_init__(self):
            n = len(_as_list(self.label))
            if n == 0:
                raise ValueError("AtlasROI label must be non-empty")
            if len(_as_list(self.atlas_path)) not in (1, n):
                raise ValueError(
                    "AtlasROI atlas_path must be a scalar or match the number "
                    "of labels"
                )
            if len(_as_list(self.hemisphere)) not in (1, n):
                raise ValueError(
                    "AtlasROI hemisphere must be a scalar or match the number "
                    "of labels"
                )

    @dataclass
    class SubcorticalROI:
        """Subcortical volume ROI from a volumetric atlas.

        *label* accepts either a single value (one region) or a list (a union
        of several regions -- e.g. both hippocampi from one ``aseg`` atlas --
        evaluated as one combined target).  *atlas_path* may be a scalar
        (shared by every label) or a list matching the number of labels; a
        single shared *tissues* and *atlas_space* apply to the whole union.

        Attributes
        ----------
        atlas_path : str or list of str
            Path(s) to the volumetric atlas NIfTI file(s).
        label : int or list of int
            Integer label index/indices within the volumetric atlas.
        tissues : str
            Tissue compartments to include.  One of ``"GM"``, ``"WM"``,
            or ``"both"``.
        atlas_space : str
            Space of the atlas NIfTI.  One of ``"subject"`` or ``"mni"``.
            MNI-space masks are transformed by SimNIBS during ROI setup.

        Raises
        ------
        ValueError
            If *label* is empty, or *atlas_path* is a list whose length
            neither equals 1 nor the number of labels.
        """

        atlas_path: str | list[str]
        label: int | list[int]
        tissues: str = "GM"  # "GM", "WM", or "both"
        atlas_space: Literal["subject", "mni"] = "subject"

        def __post_init__(self):
            n = len(_as_list(self.label))
            if n == 0:
                raise ValueError("SubcorticalROI label must be non-empty")
            if len(_as_list(self.atlas_path)) not in (1, n):
                raise ValueError(
                    "SubcorticalROI atlas_path must be a scalar or match the "
                    "number of labels"
                )

    # ── Nested electrode config ───────────────────────────────────────

    @dataclass
    class ElectrodeConfig:
        """Electrode geometry for flex-search.

        Only *gel_thickness* is needed here -- the optimization leadfield
        uses point electrodes; *gel_thickness* is recorded in the manifest
        for downstream simulation.

        Attributes
        ----------
        shape : str
            Electrode shape (``"ellipse"`` or ``"rect"``).
        dimensions : list of float
            Electrode dimensions in mm (``[width, height]``).
        gel_thickness : float
            Conductive gel thickness in mm.
        """

        shape: str = "ellipse"  # "ellipse" or "rect"
        dimensions: list[float] = field(default_factory=lambda: [8.0, 8.0])
        gel_thickness: float = 4.0

    # ── required ──
    subject_id: str
    goal: OptGoal
    postproc: FieldPostproc
    current_mA: float
    electrode: ElectrodeConfig
    roi: "FlexConfig.SphericalROI | FlexConfig.AtlasROI | FlexConfig.SubcorticalROI"

    anisotropy_type: str = "scalar"
    aniso_maxratio: float = 10.0
    aniso_maxcond: float = 2.0

    # ── focality ──
    non_roi_method: NonROIMethod | None = None
    non_roi: "FlexConfig.SphericalROI | FlexConfig.AtlasROI | FlexConfig.SubcorticalROI | None" = (None)
    thresholds: str | None = None

    # ── eeg mapping ──
    eeg_net: str | None = None
    enable_mapping: bool = False
    disable_mapping_simulation: bool = False

    # ── output ──
    output_folder: str | None = None
    run_final_electrode_simulation: bool = False

    # ── solver ──
    n_multistart: int = 1
    max_iterations: int | None = None
    population_size: int | None = None
    tolerance: float | None = None
    mutation: str | None = None
    recombination: float | None = None
    cpus: int | None = None
    min_electrode_distance: float = 5.0

    # ── debug ──
    detailed_results: bool = False
    visualize_valid_skin_region: bool = True
    skin_visualization_net: str | None = None
    skin_region_margin_mm: float = 0.0
    avoid_landmark_regions: bool = True

    def __post_init__(self):
        if isinstance(self.goal, str):
            self.goal = FlexConfig.OptGoal(self.goal)
        if isinstance(self.postproc, str):
            self.postproc = FlexConfig.FieldPostproc(self.postproc)
        if isinstance(self.non_roi_method, str):
            self.non_roi_method = FlexConfig.NonROIMethod(self.non_roi_method)
        if (
            self.goal is FlexConfig.OptGoal.FOCALITY
            and self.non_roi_method is FlexConfig.NonROIMethod.SPECIFIC
            and self.non_roi is None
        ):
            raise ValueError(
                "goal='focality' with method='specific' requires a non_roi specification"
            )
        if self.thresholds is not None:
            for part in self.thresholds.split(","):
                float(part.strip())
        self.skin_region_margin_mm = float(self.skin_region_margin_mm)


@dataclass
class FlexResult:
    """Result from a flex-search optimization run.

    Attributes
    ----------
    success : bool
        True if the optimization completed without error.
    output_folder : str
        Absolute path to the output directory containing manifests, logs,
        and optional simulation results.
    function_values : list of float
        Objective function value for each multistart run.
    best_value : float
        Best (highest) objective value across all restarts.
    best_run_index : int
        Zero-based index of the restart that produced the best result.

    See Also
    --------
    FlexConfig : Configuration consumed by :func:`~tit.opt.flex.flex.run_flex_search`.
    tit.opt.flex.flex.run_flex_search : Returns this result.
    """

    success: bool
    output_folder: str
    function_values: list[float]
    best_value: float
    best_run_index: int


# ── Exhaustive search config ─────────────────────────────────────────────────


@dataclass
class ExConfig:
    """Full configuration for exhaustive search optimization.

    Exhaustive search evaluates every valid electrode combination from
    a user-defined pool or bucket set, sweeping current amplitudes at
    discrete steps.

    Attributes
    ----------
    subject_id : str
        Subject identifier matching the m2m directory name.
    leadfield_hdf : str
        Path to the precomputed leadfield HDF5 file.
    roi_name : str
        ROI CSV filename (e.g. ``"target.csv"``).  The ``".csv"`` suffix
        is appended automatically if missing.  Used as the metric-key
        prefix and (with the net name) the output-directory label.
    roi_names : list of str or None
        Optional list of ROI CSV filenames to **union** into a single
        target.  When provided (combined mode), the spherical masks of
        every listed ROI are OR-folded into one region.  ``None``
        (default) keeps single-ROI behavior driven by *roi_name*.  Each
        entry gets the ``".csv"`` suffix appended if missing.
    electrodes : BucketElectrodes or PoolElectrodes
        Electrode specification, either a single shared pool
        (:class:`PoolElectrodes`) or separate per-channel buckets
        (:class:`BucketElectrodes`).  A plain dict is auto-converted
        in ``__post_init__``.
    total_current : float
        Total injected current in mA, split across channels.
    current_step : float
        Current amplitude step size in mA for the sweep.
    channel_limit : float or None
        Maximum current per channel in mA.  ``None`` for no per-channel
        limit.
    roi_radius : float
        Spherical ROI radius in mm for the target region.
    run_name : str or None
        Optional name for this run.  Defaults to a datetime stamp.

    Raises
    ------
    ValueError
        If *current_step*, *total_current*, or *channel_limit* are
        non-positive.

    See Also
    --------
    ExResult : Result container returned by :func:`~tit.opt.ex.ex.run_ex_search`.
    tit.opt.ex.ex.run_ex_search : Consumes this config.
    """

    # ── Nested electrode types ─────────────────────────────────────────
    @dataclass
    class BucketElectrodes:
        """Separate electrode lists for each bipolar channel position.

        Attributes
        ----------
        e1_plus : list of str
            Candidate electrodes for channel 1 anode.
        e1_minus : list of str
            Candidate electrodes for channel 1 cathode.
        e2_plus : list of str
            Candidate electrodes for channel 2 anode.
        e2_minus : list of str
            Candidate electrodes for channel 2 cathode.
        """

        e1_plus: list[str]
        e1_minus: list[str]
        e2_plus: list[str]
        e2_minus: list[str]

    @dataclass
    class PoolElectrodes:
        """Single electrode pool -- all positions draw from the same set.

        Attributes
        ----------
        electrodes : list of str
            List of electrode names available for any channel position.
        """

        electrodes: list[str]

    # ── Required fields ────────────────────────────────────────────────
    subject_id: str
    leadfield_hdf: str
    roi_name: str
    electrodes: BucketElectrodes | PoolElectrodes

    # ── Current parameters ────────────────────────────────────────────
    total_current: float = 2.0
    current_step: float = 0.5
    channel_limit: float | None = None

    # ── ROI ────────────────────────────────────────────────────────────
    roi_radius: float = 3.0
    roi_names: list[str] | None = None

    # ── Output naming (defaults to datetime stamp) ─────────────────────
    run_name: str | None = None

    def __post_init__(self):
        if isinstance(self.electrodes, dict):
            if "electrodes" in self.electrodes:
                self.electrodes = ExConfig.PoolElectrodes(**self.electrodes)
            else:
                self.electrodes = ExConfig.BucketElectrodes(**self.electrodes)
        if not self.roi_name.endswith(".csv"):
            self.roi_name += ".csv"
        if self.roi_names is not None:
            self.roi_names = [
                n if n.endswith(".csv") else f"{n}.csv" for n in self.roi_names
            ]

        # Validation
        if self.current_step <= 0:
            raise ValueError("current_step must be positive")
        if self.total_current <= 0:
            raise ValueError("total_current must be positive")
        if self.channel_limit is not None and self.channel_limit <= 0:
            raise ValueError("channel_limit must be positive")


@dataclass
class ExResult:
    """Result from an exhaustive search run.

    Attributes
    ----------
    success : bool
        True if the search completed without error.
    output_dir : str
        Absolute path to the output directory.
    n_combinations : int
        Total number of electrode/current combinations evaluated.
    results_csv : str or None
        Path to the CSV file containing ranked results.  ``None`` if the
        run failed before writing results.
    config_json : str or None
        Path to the saved configuration JSON.  ``None`` if the run failed
        before writing config.

    See Also
    --------
    ExConfig : Configuration consumed by :func:`~tit.opt.ex.ex.run_ex_search`.
    tit.opt.ex.ex.run_ex_search : Returns this result.
    """

    success: bool
    output_dir: str
    n_combinations: int
    results_csv: str | None = None
    config_json: str | None = None
