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
MExConfig
    Full configuration for multipolar (4-pair) exhaustive search.
MExResult
    Result container for a completed multipolar exhaustive search run.

See Also
--------
tit.opt.flex.flex.run_flex_search : Consumes :class:`FlexConfig`.
tit.opt.ex.ex.run_ex_search : Consumes :class:`ExConfig`.
tit.opt.mex.mex.run_m_ex_search : Consumes :class:`MExConfig`.
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


#: Threshold specifications that mean "let SimNIBS choose" rather than naming an
#: explicit numeric threshold.  The empty string is included so a blank GUI field
#: is treated the same as an unset one.
_THRESHOLD_PLACEHOLDERS = frozenset({"", "dynamic", "auto"})


def _has_usable_thresholds(thresholds) -> bool:
    """True when *thresholds* names explicit numeric focality thresholds.

    ``None`` and the placeholders in :data:`_THRESHOLD_PLACEHOLDERS` both mean
    "let SimNIBS pick".  SimNIBS's built-in ROC goal supplies its own defaults in
    that case, but a Python-side ROC objective (as used by the current-ratio
    search) has nothing to fall back on.
    """
    if thresholds is None:
        return False
    return str(thresholds).strip().lower() not in _THRESHOLD_PLACEHOLDERS


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
        Optimization objective (``"mean"``, ``"max"``, ``"focality"``, or
        ``"focality_tf"``).
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
        Only used by the ROC-based ``"focality"`` goal.  ``None`` (or a
        placeholder such as ``"dynamic"``) lets SimNIBS supply its own
        defaults -- but that fallback exists only inside SimNIBS, so
        combining ``goal="focality"`` with *optimize_current_ratio* makes
        explicit numeric thresholds **required**: the ratio search scores
        candidates with its own ROC objective, which has no defaults.
    intensity_weight : float
        Weight ``w`` in ``[0, 1]`` trading ROI intensity against focality
        for the ``"focality_tf"`` goal.  ``0.0`` gives the balanced form,
        ``1.0`` weights raw ROI intensity most heavily.  Ignored by the
        other goals.
    optimize_current_ratio : bool
        If True, jointly search the electrode placement **and** the
        current split between the two channels instead of fixing it at
        1:1.  Applies to any goal.  Scoring then happens in a Python
        callable rather than in SimNIBS, which has two consequences:
        ``goal="focality"`` requires explicit *thresholds*, and
        *detailed_results* cannot be used.
    ratio_total_mA : float or None
        Total current (mA) shared by the two channels during the ratio
        search.  ``None`` uses ``2 * current_mA``, i.e. the 1:1 split is
        contained in the search range.  When set explicitly it must be
        greater than zero.
    ratio_levels : int
        Number of discrete current splits evaluated per candidate
        placement.  Must be at least 2 when *optimize_current_ratio* is
        True.
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
        If True, save per-restart detailed output.  Incompatible with any
        configuration whose goal is a Python callable -- ``"focality_tf"``
        or *optimize_current_ratio* -- because SimNIBS writes ``opt.goal``
        into the detailed-results HDF5 file and h5py cannot serialise a
        function.  The combination is rejected at config time rather than
        after the (potentially hours-long) optimization has finished.
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
        but *non_roi* is ``None``, if *thresholds* contains non-numeric
        values, if *intensity_weight* falls outside ``[0, 1]``, if
        *ratio_levels* is below 2 while *optimize_current_ratio* is True,
        if *ratio_total_mA* is set but not positive, if
        *optimize_current_ratio* is combined with ``goal="focality"``
        without explicit *thresholds*, or if *detailed_results* is
        combined with a callable-goal configuration
        (``goal="focality_tf"`` or *optimize_current_ratio*).

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
            Maximize ROI-to-non-ROI focality via SimNIBS's threshold-based
            ROC measure (``measures.ROC``).
        FOCALITY_TF : str
            Maximize a threshold-free focality contrast,
            ``mean(E_ROI) ** (1 + w) / p95(E_nonROI)``.  Because it needs no
            thresholds it avoids the threshold-selection failure mode of the
            ROC goal, whose landscape flattens when the requested ROI and
            non-ROI thresholds are jointly infeasible (as happens at deep
            targets).  The weight ``w`` is
            :attr:`FlexConfig.intensity_weight`.
        """

        MEAN = "mean"
        MAX = "max"
        FOCALITY = "focality"
        FOCALITY_TF = "focality_tf"

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
    intensity_weight: float = 0.0

    # ── current-ratio search ──
    optimize_current_ratio: bool = False
    ratio_total_mA: float | None = None
    ratio_levels: int = 21

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
        # Any focality goal (ROC or threshold-free) needs a non-ROI region; default to
        # "everything else" so a config that omits the method still runs.
        if self.is_focality and self.non_roi_method is None:
            self.non_roi_method = FlexConfig.NonROIMethod.EVERYTHING_ELSE
        if (
            self.is_focality
            and self.non_roi_method is FlexConfig.NonROIMethod.SPECIFIC
            and self.non_roi is None
        ):
            raise ValueError(
                f"goal='{self.goal.value}' with method='specific' requires a "
                "non_roi specification"
            )
        # The ratio search scores candidates itself, so the ROC goal can no
        # longer lean on the thresholds SimNIBS would have supplied. Catch it
        # here: otherwise it surfaces as a ValueError raised deep inside the
        # `simnibs_python -m tit.opt.flex` child process, long after launch.
        if (
            self.optimize_current_ratio
            and self.goal is FlexConfig.OptGoal.FOCALITY
            and not _has_usable_thresholds(self.thresholds)
        ):
            raise ValueError(
                "optimize_current_ratio=True with goal='focality' requires "
                "explicit numeric thresholds, because the current-ratio "
                "search scores candidates with its own ROC objective and "
                "cannot fall back on the thresholds SimNIBS would supply "
                f"(thresholds={self.thresholds!r}). Set thresholds (e.g. "
                "'0.1,0.2'), use goal='focality_tf' which needs none, or "
                "set optimize_current_ratio=False."
            )
        if self.thresholds is not None:
            for part in self.thresholds.split(","):
                float(part.strip())
        self.intensity_weight = float(self.intensity_weight)
        if not 0.0 <= self.intensity_weight <= 1.0:
            raise ValueError(
                f"intensity_weight must be in [0, 1] (was {self.intensity_weight})"
            )
        self.ratio_levels = int(self.ratio_levels)
        if self.optimize_current_ratio and self.ratio_levels < 2:
            raise ValueError(
                f"ratio_levels must be >= 2 when optimize_current_ratio is "
                f"enabled (was {self.ratio_levels})"
            )
        if self.ratio_total_mA is not None:
            self.ratio_total_mA = float(self.ratio_total_mA)
            if self.ratio_total_mA <= 0.0:
                raise ValueError(
                    f"ratio_total_mA must be > 0 when set (was "
                    f"{self.ratio_total_mA}); leave it None to use "
                    f"2 * current_mA"
                )
        # SimNIBS serialises opt.goal into the detailed-results HDF5 file, and
        # h5py cannot store a Python function. That failure fires only after the
        # optimization completes, so reject the combination up front.
        if self.detailed_results and (
            self.goal is FlexConfig.OptGoal.FOCALITY_TF or self.optimize_current_ratio
        ):
            trigger = (
                "goal='focality_tf'"
                if self.goal is FlexConfig.OptGoal.FOCALITY_TF
                else "optimize_current_ratio=True"
            )
            raise ValueError(
                f"detailed_results=True is not supported with {trigger}: that "
                "configuration scores candidates with a Python callable goal, "
                "and SimNIBS writes opt.goal into its detailed-results HDF5 "
                "file, where h5py rejects a callable: TypeError: Object dtype "
                "dtype('O') has no native HDF5 equivalent. The error is "
                "raised only after the optimization finishes, discarding the "
                "whole run. Set detailed_results=False."
            )
        self.skin_region_margin_mm = float(self.skin_region_margin_mm)

    @property
    def is_focality(self) -> bool:
        """True for any focality goal (ROC-based or threshold-free).

        Focality goals share the same ROI/non-ROI setup (a target ROI plus a
        non-ROI region), so callers use this to gate non-ROI construction and
        reporting. Threshold-specific logic keeps comparing against
        ``OptGoal.FOCALITY`` directly, since only the ROC goal uses thresholds.
        """
        return self.goal in (
            FlexConfig.OptGoal.FOCALITY,
            FlexConfig.OptGoal.FOCALITY_TF,
        )


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


# ── Multipolar exhaustive search config ──────────────────────────────────────


@dataclass
class MExConfig:
    """Full configuration for multipolar (4-pair, 8-electrode) exhaustive search.

    Evaluates every valid combination of four bipolar electrode pairs from
    a user-defined pool or bucket set, at one fixed current per pair, and
    scores each candidate with the verified N>2 mTI envelope
    (:func:`tit.calc.get_mTI_vectors`).

    Attributes
    ----------
    subject_id : str
        Subject identifier matching the m2m directory name.
    leadfield_hdf : str
        Path to the precomputed leadfield HDF5 file.
    roi_name : str
        ROI CSV filename (e.g. ``"target.csv"``).  The ``".csv"`` suffix
        is appended automatically if missing.
    electrodes : BucketElectrodes or PoolElectrodes
        Electrode specification, either a single shared pool
        (:class:`PoolElectrodes`) or four separate per-pair buckets
        (:class:`BucketElectrodes`).  A plain dict is auto-converted in
        ``__post_init__``.
    current_mA : float
        Current in mA delivered by each of the four pairs.
    channels : list of (list of int, list of int), or None
        Carrier grouping passed to :func:`tit.calc.get_mTI_vectors`.
        ``None`` treats the four pairs as two independent TI channels
        (equivalent to ``[([0], [1]), ([2], [3])]``); an explicit grouping
        such as ``[([0, 2], [1, 3])]`` instead treats all four pairs as
        one channel sharing two carriers (Lee et al. 2022).  These give
        materially different fields, so the grouping must be chosen
        deliberately -- the quasi-static field solve has no frequency
        term, so this grouping is the only place carrier assignment is
        expressed.
    roi_radius : float
        Spherical ROI radius in mm for the target region.
    run_name : str or None
        Optional name for this run.  Defaults to a datetime stamp.
    symmetric_bucket : bool
        When True in bucket mode, evaluate only left/right mirrored
        electrode pairs (see :func:`tit.opt.ex.buckets.build_electrode_mirror_map`).
    symmetry_eeg_csv : str or None
        EEG-position CSV used to derive mirrored electrode pairs.  If
        unset, it is inferred from the leadfield's net name.
    symmetry_pairing : str
        Symmetry interpretation for bucket mode when *symmetric_bucket*
        is True.  ``"within_pairs"`` mirrors each pair's plus/minus
        electrodes independently; ``"cross_pairs"`` additionally mirrors
        pair 1<->3 and pair 2<->4.

    Raises
    ------
    ValueError
        If *current_mA* is non-positive, if *symmetric_bucket* is set
        with pool electrodes, or if *symmetry_pairing* is not one of
        ``"within_pairs"``/``"cross_pairs"``.

    See Also
    --------
    MExResult : Result container returned by :func:`~tit.opt.mex.mex.run_m_ex_search`.
    tit.opt.mex.mex.run_m_ex_search : Consumes this config.
    tit.calc.get_mTI_vectors : Modulation-amplitude envelope; consumes *channels*.
    """

    # ── Nested electrode types ─────────────────────────────────────────
    @dataclass
    class BucketElectrodes:
        """Separate electrode lists for each of the four bipolar pairs.

        Attributes
        ----------
        e1_plus, e1_minus, e2_plus, e2_minus, e3_plus, e3_minus, e4_plus, e4_minus : list of str
            Candidate electrodes for each pair's anode/cathode position.
        """

        e1_plus: list[str]
        e1_minus: list[str]
        e2_plus: list[str]
        e2_minus: list[str]
        e3_plus: list[str]
        e3_minus: list[str]
        e4_plus: list[str]
        e4_minus: list[str]

    @dataclass
    class PoolElectrodes:
        """Single electrode pool -- all eight positions draw from the same set.

        Attributes
        ----------
        electrodes : list of str
            List of electrode names available for any pair position.
        """

        electrodes: list[str]

    # ── Required fields ────────────────────────────────────────────────
    subject_id: str
    leadfield_hdf: str
    roi_name: str
    electrodes: "MExConfig.BucketElectrodes | MExConfig.PoolElectrodes"

    # ── Current and carrier grouping ────────────────────────────────────
    current_mA: float = 2.0
    channels: list[tuple[list[int], list[int]]] | None = None

    # ── ROI ────────────────────────────────────────────────────────────
    roi_radius: float = 3.0

    # ── Output naming (defaults to datetime stamp) ─────────────────────
    run_name: str | None = None

    # ── Symmetric bucket search ─────────────────────────────────────────
    symmetric_bucket: bool = False
    symmetry_eeg_csv: str | None = None
    symmetry_pairing: str = "within_pairs"

    def __post_init__(self):
        if isinstance(self.electrodes, dict):
            if "electrodes" in self.electrodes:
                self.electrodes = MExConfig.PoolElectrodes(**self.electrodes)
            else:
                self.electrodes = MExConfig.BucketElectrodes(**self.electrodes)
        if not self.roi_name.endswith(".csv"):
            self.roi_name += ".csv"

        if self.current_mA <= 0:
            raise ValueError("current_mA must be positive")
        if self.symmetric_bucket and isinstance(
            self.electrodes, MExConfig.PoolElectrodes
        ):
            raise ValueError("symmetric_bucket is only supported for bucket electrodes")
        if self.symmetry_pairing not in ("within_pairs", "cross_pairs"):
            raise ValueError("symmetry_pairing must be 'within_pairs' or 'cross_pairs'")


@dataclass
class MExResult:
    """Result from a multipolar exhaustive search run.

    Attributes
    ----------
    success : bool
        True if the search completed without error.
    output_dir : str
        Absolute path to the output directory.
    n_combinations : int
        Total number of eight-electrode combinations evaluated.
    results_csv : str or None
        Path to the CSV file containing ranked results.  ``None`` if the
        run failed before writing results.
    config_json : str or None
        Path to the saved configuration JSON.  ``None`` if the run failed
        before writing config.

    See Also
    --------
    MExConfig : Configuration consumed by :func:`~tit.opt.mex.mex.run_m_ex_search`.
    tit.opt.mex.mex.run_m_ex_search : Returns this result.
    """

    success: bool
    output_dir: str
    n_combinations: int
    results_csv: str | None = None
    config_json: str | None = None


#: Exhaustive-search modes. ``TI`` searches two bipolar pairs, ``mTI`` four.
SEARCH_MODE_TI = "TI"
SEARCH_MODE_MTI = "mTI"

#: Carrier wiring for a four-pair montage, as (label, ``channels`` value).
#: Four pairs can be two independent TI channels -- consecutive pairing, the
#: default -- or four pairs sharing two carriers, where same-carrier fields
#: superpose before the envelope is taken (Lee et al. 2022). The two give
#: materially different fields, so it is a real choice rather than a detail.
MTI_CHANNEL_ARCHITECTURES = [
    ("Two independent channels", None),
    ("Four pairs, two carriers", [([0, 2], [1, 3])]),
]


def search_backend_for_mode(mode):
    """Return ``(module path, config class)`` for an exhaustive-search mode.

    Args:
        mode: :data:`SEARCH_MODE_TI` or :data:`SEARCH_MODE_MTI`.

    Returns:
        ``(module_path, config_class)``; *module_path* is passed to
        ``simnibs_python -m <module_path>`` and *config_class* is the
        dataclass to build for that mode.

    Raises:
        ValueError: If *mode* is not a known search mode.
    """
    if mode == SEARCH_MODE_TI:
        return "tit.opt.ex", ExConfig
    if mode == SEARCH_MODE_MTI:
        return "tit.opt.mex", MExConfig
    raise ValueError(f"Unknown search mode: {mode!r}")
