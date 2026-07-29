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
MultiPolarConfig
    Configuration for multi-polar leadfield-based DE optimization (N-pair mTI).
MultiPolarResult
    Result container for a completed multi-polar leadfield search run.
MTIFrequencyPlan
    Per-pair carrier/phase assignment for a multipolar (mTI) montage.
validate_band_separation
    Validate that an :class:`MTIFrequencyPlan` has enough carrier-band
    separation for the N>2 envelope closed form to remain valid.

See Also
--------
tit.opt.flex.flex.run_flex_search : Consumes :class:`FlexConfig`.
tit.opt.ex.ex.run_ex_search : Consumes :class:`ExConfig`.
tit.opt.mp.run_mp_search : Consumes :class:`MultiPolarConfig`.
tit.calc.mti_modulation_depth : Consumes an :class:`MTIFrequencyPlan`'s
    per-pair phase offsets (as ``psi``) for the N>2 envelope.
"""

import math
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
    n_pairs : int
        Number of electrode pairs. 2 for standard TI, 4 for mTI, 6/8 for
        extended multi-polar. Must be an even number >= 2.
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
        but *non_roi* is ``None``, if *thresholds* contains non-numeric
        values, or if *n_pairs* is not an even number >= 2.

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

    # ── multi-polar ──
    n_pairs: int = 2  # 2 = standard TI, 4 = mTI, 6/8 = extended multi-polar

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
        if self.n_pairs < 2 or self.n_pairs % 2 != 0:
            raise ValueError(f"n_pairs must be an even number >= 2, got {self.n_pairs}")
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
    metric : str
        Envelope metric used for the primary reported field (``TImax_ROI``
        / ``TImean_ROI`` / ``Focality``). ``"grossman"`` (default) is the
        current, unchanged path -- SimNIBS's ``TI.get_maxTI``, exact for
        the 2-pair case exhaustive search always evaluates.
        ``"mti_modulation_depth"`` instead routes through
        :func:`tit.calc.mti_modulation_depth` (K=1 exact closed form, see
        ``tracks/active/mti-focality-core.md`` Phase 2 finding), which
        lets the two be compared on identical montages. The two should
        agree to floating-point precision for K=1 -- a divergence would
        indicate a bug in one of the two implementations.
    carrier_constraint : float or None
        Maximum acceptable off-target (grey-matter) carrier RMS, in V/m.
        ``None`` (default) disables the constraint entirely -- the carrier
        (the un-modulated high-frequency field) is not neurally inert
        (Opancar 2025, Semenov 2025, Peterchev 2025) and its off-target
        maximum sits under the electrodes, yet no published TI optimizer
        constrains it (finding F4). This is a new scientific claim, not a
        behaviour users asked for, so it ships off by default. Consumed
        together with *carrier_penalty_weight* by
        :func:`tit.opt.carrier.carrier_constraint_penalty`.
    carrier_penalty_weight : float
        Soft-constraint weight applied to the amount by which off-target
        carrier RMS exceeds *carrier_constraint*. ``0.0`` (default)
        disables the penalty even if *carrier_constraint* is set --
        both must be configured for the constraint to have any effect.
        Kept separate from *carrier_constraint* so a constraint can be
        recorded/reported without yet being enforced.

    Raises
    ------
    ValueError
        If *current_step*, *total_current*, or *channel_limit* are
        non-positive, or if *metric* is not a recognized value.

    See Also
    --------
    ExResult : Result container returned by :func:`~tit.opt.ex.ex.run_ex_search`.
    tit.opt.ex.ex.run_ex_search : Consumes this config.
    tit.opt.carrier.carrier_constraint_penalty : Computes the soft-constraint
        penalty from *carrier_constraint* / *carrier_penalty_weight*.
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

    # ── Envelope metric (mti-focality-core Phase 2) ─────────────────────
    metric: Literal["grossman", "mti_modulation_depth"] = "grossman"

    # ── Carrier-exposure constraint (finding F4) -- off by default ──────
    carrier_constraint: float | None = None
    carrier_penalty_weight: float = 0.0

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
        if self.metric not in ("grossman", "mti_modulation_depth"):
            raise ValueError(
                "metric must be 'grossman' or 'mti_modulation_depth', got "
                f"{self.metric!r}"
            )
        if self.carrier_penalty_weight < 0:
            raise ValueError("carrier_penalty_weight must be non-negative")


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


# ── Multipolar (mTI) frequency plan ──────────────────────────────────────────


@dataclass
class MTIFrequencyPlan:
    """Per-pair carrier assignment for a multipolar (mTI) TI montage.

    Records the two carrier frequencies and (optional) hardware phase
    offsets driving each electrode pair. Every pair must share the same
    beat frequency ``delta_f = |f_b - f_a|`` -- that shared beat frequency
    is what the N>2 envelope closed form in
    :func:`tit.calc.mti_modulation_depth` targets. ``phi_b - phi_a`` per
    pair is exactly the ``psi`` array that function accepts.

    Attributes
    ----------
    f_a : list of float
        Carrier frequency (Hz) of sub-channel *a*, one entry per pair.
    f_b : list of float
        Carrier frequency (Hz) of sub-channel *b*, one entry per pair.
        Must have the same length as *f_a*.
    phi_a : list of float
        Hardware phase offset (radians) of sub-channel *a*, one entry per
        pair. Defaults to all zeros.
    phi_b : list of float
        Hardware phase offset (radians) of sub-channel *b*, one entry per
        pair. Defaults to all zeros.

    Raises
    ------
    ValueError
        If *f_a* is empty, if *f_b*/*phi_a*/*phi_b* do not match *f_a* in
        length, if any frequency is non-positive, or if the beat frequency
        ``|f_b - f_a|`` is not the same for every pair.

    See Also
    --------
    validate_band_separation : Validates carrier-band separation between
        pairs (a distinct condition from the shared-beat-frequency check
        here).
    tit.calc.mti_modulation_depth : Consumes ``phi_b - phi_a`` per pair as
        its ``psi`` argument.
    """

    f_a: list[float]
    f_b: list[float]
    phi_a: list[float] = field(default_factory=list)
    phi_b: list[float] = field(default_factory=list)

    def __post_init__(self):
        n = len(self.f_a)
        if n == 0:
            raise ValueError("MTIFrequencyPlan requires at least one pair")
        if len(self.f_b) != n:
            raise ValueError(
                f"f_a and f_b must have equal length, got {n} and {len(self.f_b)}"
            )
        if not self.phi_a:
            self.phi_a = [0.0] * n
        if not self.phi_b:
            self.phi_b = [0.0] * n
        if len(self.phi_a) != n or len(self.phi_b) != n:
            raise ValueError(
                "phi_a and phi_b must have the same length as f_a/f_b "
                f"({n}); got {len(self.phi_a)} and {len(self.phi_b)}"
            )
        if any(f <= 0 for f in self.f_a) or any(f <= 0 for f in self.f_b):
            raise ValueError(
                "All carrier frequencies in MTIFrequencyPlan must be positive"
            )

        delta_fs = [abs(fb - fa) for fa, fb in zip(self.f_a, self.f_b)]
        ref = delta_fs[0]
        for i, df in enumerate(delta_fs[1:], start=1):
            if not math.isclose(df, ref, rel_tol=1e-9, abs_tol=1e-6):
                raise ValueError(
                    "MTIFrequencyPlan requires every pair to share the same "
                    f"beat frequency delta_f; pair 0 has delta_f={ref:.6g} Hz, "
                    f"pair {i} has delta_f={df:.6g} Hz"
                )

    @property
    def delta_f(self) -> float:
        """Shared beat frequency ``|f_b - f_a|`` (Hz), common to every pair."""
        return abs(self.f_b[0] - self.f_a[0])

    @property
    def pair_means(self) -> list[float]:
        """Per-pair mean carrier frequency ``(f_a + f_b) / 2`` (Hz)."""
        return [0.5 * (fa + fb) for fa, fb in zip(self.f_a, self.f_b)]

    @property
    def psi(self) -> list[float]:
        """Per-pair envelope phase offset ``phi_b - phi_a`` (radians).

        Directly consumable as the ``psi`` argument of
        :func:`tit.calc.mti_modulation_depth`.
        """
        return [pb - pa for pa, pb in zip(self.phi_a, self.phi_b)]


def validate_band_separation(plan: MTIFrequencyPlan, f_cutoff: float = 200.0) -> None:
    """Validate carrier-band separation between every pair of mTI pairs.

    The N>2 envelope closed form (:func:`tit.calc.mti_modulation_depth`)
    and physiological specificity both require, for every pair of pairs
    *(i, j)*::

        |mean(f_i) - mean(f_j)| - delta_f  >  f_cutoff

    Below this margin, cross-pair beat products fall inside the
    demodulation passband: the closed form stops being valid, and stray
    low-frequency envelopes appear in off-target tissue. Botzanowski et
    al.'s empirical "at least 1 kHz between pair-mean carrier
    frequencies" is a conservative instance of this condition (with
    ``f_cutoff=200`` Hz and typical ``delta_f`` in the tens-of-Hz range,
    the required gap works out to roughly that order).

    Parameters
    ----------
    plan : MTIFrequencyPlan
        The per-pair carrier assignment to validate.
    f_cutoff : float, default 200.0
        Demodulation low-pass cutoff (Hz) -- the beat frequency band that
        must stay clear of cross-pair carrier-difference products.

    Raises
    ------
    ValueError
        Naming every offending pair of pair-indices, the measured gap, and
        the required margin, if any pair of pairs violates the condition
        above.

    See Also
    --------
    MTIFrequencyPlan : The per-pair carrier/phase assignment validated here.
    tit.calc.mti_modulation_depth : The envelope formula whose validity
        this condition guards.
    """
    means = plan.pair_means
    delta_f = plan.delta_f
    n = len(means)

    violations = []
    for i in range(n):
        for j in range(i + 1, n):
            gap = abs(means[i] - means[j])
            margin = gap - delta_f
            if margin <= f_cutoff:
                violations.append((i, j, gap, margin))

    if violations:
        lines = "\n".join(
            f"  pairs {i} and {j}: carrier-band gap={gap:.1f} Hz, "
            f"delta_f={delta_f:.1f} Hz -> margin={margin:.1f} Hz "
            f"(need > {f_cutoff:.1f} Hz)"
            for i, j, gap, margin in violations
        )
        raise ValueError(
            "Insufficient carrier-band separation between mTI pairs: the "
            "N>2 envelope closed form requires "
            "(carrier-band gap - delta_f) > f_cutoff for every pair of "
            "pairs, or the closed form becomes invalid and stray "
            "low-frequency envelopes appear off-target "
            "(Botzanowski et al. recommend >= 1 kHz between pair-mean "
            "carrier frequencies as a conservative instance of this rule). "
            f"Violations (f_cutoff={f_cutoff:.1f} Hz):\n{lines}"
        )


# ── Multi-polar leadfield DE search config ──────────────────────────────────


@dataclass
class MultiPolarConfig:
    """Configuration for multi-polar leadfield-based DE optimization.

    Uses a precomputed leadfield matrix to optimize electrode placements
    and current weights for multi-channel TI stimulation via differential
    evolution. AtlasROI is not supported; use SphericalROI or
    SubcorticalROI.

    Attributes:
        subject_id: Subject identifier matching the m2m directory name.
        leadfield_hdf: Path to the precomputed leadfield HDF5 file.
        roi: Target region of interest (SphericalROI or SubcorticalROI).
        n_pairs: Number of electrode pairs (must be >= 2).
        current_mA: Total injected current in milliamps.
        non_roi_method: How to define the non-ROI region
            ("everything_else" or "specific").
        non_roi: Explicit non-ROI region when non_roi_method is
            "specific". Required if non_roi_method is "specific".
        max_iterations: Maximum DE generations. None for solver default.
        population_size: DE population size. None for solver default.
        tolerance: Convergence tolerance. None for solver default.
        mutation: DE mutation strategy string. None for solver default.
        recombination: DE crossover probability. None for solver default.
        min_electrode_distance: Minimum distance (mm) between any two
            electrodes.
        n_multistart: Number of independent DE restarts.
        cpus: Number of parallel workers.
        patience: Early-stopping patience (generations without
            improvement).
        top_k: Number of top solutions to retain from each restart.
        output_dir: Override for the output directory path. Defaults to
            an auto-generated path.
    """

    # ── required ──
    subject_id: str
    leadfield_hdf: str
    roi: "FlexConfig.SphericalROI | FlexConfig.SubcorticalROI"

    # ── search ──
    n_pairs: int = 4
    current_mA: float = 2.0
    non_roi_method: str = "everything_else"
    non_roi: "FlexConfig.SphericalROI | FlexConfig.SubcorticalROI | None" = None

    # ── DE parameters ──
    max_iterations: int | None = None
    population_size: int | None = None
    tolerance: float | None = None
    mutation: str | None = None
    recombination: float | None = None

    # ── constraints ──
    min_electrode_distance: float = 0.0
    n_multistart: int = 1
    cpus: int = 1
    patience: int = 50
    top_k: int = 10

    # ── output ──
    output_dir: str | None = None

    def __post_init__(self):
        if self.n_pairs < 2:
            raise ValueError(f"n_pairs must be >= 2, got {self.n_pairs}")
        if hasattr(self.roi, "hemisphere"):
            raise ValueError(
                "AtlasROI not supported for leadfield optimization. "
                "Use SphericalROI or SubcorticalROI instead."
            )
        if self.non_roi_method == "specific" and self.non_roi is None:
            raise ValueError("non_roi_method='specific' requires non_roi config")


@dataclass
class MultiPolarResult:
    """Result from a multi-polar leadfield DE optimization run.

    Attributes:
        success: True if the optimization completed without error.
        output_dir: Absolute path to the output directory.
        best_focality: Best focality score (ROI-to-non-ROI ratio)
            achieved across all restarts.
        best_montage: Winning electrode configuration as a list of
            (anode_name, cathode_name, current_mA) tuples, one per pair.
        n_iterations_run: Total DE generations executed across all
            restarts.
    """

    success: bool
    output_dir: str
    best_focality: float
    best_montage: list[tuple[str, str, float]]
    n_iterations_run: int
