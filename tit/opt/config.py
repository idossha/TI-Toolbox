"""Configuration dataclasses for TI optimization.

Pure Python — no SimNIBS, numpy, or heavy dependencies.
Mirrors the tit.sim.config pattern.
"""

from dataclasses import dataclass, field
from enum import StrEnum

# ── Flex-search config ───────────────────────────────────────────────────────


@dataclass
class FlexConfig:
    """Full configuration for flex-search optimization.

    Attributes:
        subject_id: Subject identifier matching the m2m directory name.
        goal: Optimization objective (mean, max, or focality).
        postproc: Field post-processing method (max_TI, dir_TI_normal,
            or dir_TI_tangential).
        current_mA: Total injected current in milliamps.
        electrode: Electrode geometry configuration.
        roi: Target region of interest (spherical, atlas-based, or
            subcortical).
        n_pairs: Number of electrode pairs. 2 for standard TI, 4 for mTI,
            6/8 for extended multi-polar.
        anisotropy_type: Conductivity tensor type ("scalar" or "vn").
        aniso_maxratio: Maximum anisotropy eigenvalue ratio.
        aniso_maxcond: Maximum anisotropic conductivity (S/m).
        non_roi_method: How to define the non-ROI region for focality
            optimization. None when goal is not focality.
        non_roi: Explicit non-ROI region when non_roi_method is "specific".
        thresholds: Comma-separated focality threshold values (e.g. "0.1,0.2").
        eeg_net: EEG net filename (e.g. "GSN-HydroCel-185.csv") for
            electrode-name mapping. None to use raw electrode indices.
        enable_mapping: If True, map optimal indices to named EEG positions.
        disable_mapping_simulation: If True, skip the final named-electrode
            simulation after mapping.
        output_folder: Override for the output directory path. Defaults to
            an auto-generated timestamped folder.
        run_final_electrode_simulation: If True, run a full SimNIBS
            simulation with the winning electrode configuration.
        n_multistart: Number of independent DE restarts. Higher values
            reduce sensitivity to local optima.
        max_iterations: Maximum DE generations per restart. None for solver
            default.
        population_size: DE population size. None for solver default.
        tolerance: Convergence tolerance for DE. None for solver default.
        mutation: DE mutation strategy string. None for solver default.
        recombination: DE crossover probability. None for solver default.
        cpus: Number of parallel workers. None for auto-detect.
        min_electrode_distance: Minimum geodesic distance (mm) between any
            two electrodes.
        detailed_results: If True, save per-restart detailed output.
        visualize_valid_skin_region: If True, save a mesh showing the valid
            electrode placement region.
        skin_visualization_net: EEG net to overlay on the skin visualization.
    """

    # ── Nested enums ──────────────────────────────────────────────────

    class OptGoal(StrEnum):
        """Optimization goal.

        Attributes:
            MEAN: Maximize mean field intensity in the ROI.
            MAX: Maximize peak field intensity in the ROI.
            FOCALITY: Maximize ROI-to-non-ROI intensity ratio.
        """

        MEAN = "mean"
        MAX = "max"
        FOCALITY = "focality"

    class FieldPostproc(StrEnum):
        """Field post-processing method applied to the TI envelope.

        Attributes:
            MAX_TI: Maximum TI amplitude (direction-independent).
            DIR_TI_NORMAL: TI component normal to the cortical surface.
            DIR_TI_TANGENTIAL: TI component tangential to the cortical surface.
        """

        MAX_TI = "max_TI"
        DIR_TI_NORMAL = "dir_TI_normal"
        DIR_TI_TANGENTIAL = "dir_TI_tangential"

    class NonROIMethod(StrEnum):
        """Non-ROI specification method for focality optimization.

        Attributes:
            EVERYTHING_ELSE: Use all mesh elements outside the ROI.
            SPECIFIC: Use an explicitly defined non-ROI region.
        """

        EVERYTHING_ELSE = "everything_else"
        SPECIFIC = "specific"

    # ── Nested ROI types ──────────────────────────────────────────────

    @dataclass
    class SphericalROI:
        """Spherical region of interest defined by center + radius.

        By default the sphere is evaluated on the cortical surface
        (``volumetric=False``).  Set ``volumetric=True`` to evaluate on
        volume tetrahedra instead -- useful for deep/subcortical targets
        like the amygdala or hippocampus where surface-only evaluation
        would capture overlying cortex rather than the target structure.

        When ``volumetric=True``, the ``tissues`` field controls which
        tissue compartments are included (same semantics as
        ``SubcorticalROI.tissues``).

        Attributes:
            x: Center x-coordinate (mm).
            y: Center y-coordinate (mm).
            z: Center z-coordinate (mm).
            radius: Sphere radius in mm.
            use_mni: If True, coordinates are in MNI space and will be
                transformed to subject space automatically.
            volumetric: If True, evaluate on volume tetrahedra instead of
                the cortical surface.
            tissues: Tissue compartments to include when volumetric is True.
                One of "GM", "WM", or "both".
        """

        x: float
        y: float
        z: float
        radius: float = 10.0
        use_mni: bool = False
        volumetric: bool = False
        tissues: str = "GM"  # "GM", "WM", or "both" — only used when volumetric=True

    @dataclass
    class AtlasROI:
        """Cortical surface ROI from a FreeSurfer annotation atlas.

        Attributes:
            atlas_path: Path to the FreeSurfer .annot annotation file.
            label: Integer label index within the annotation atlas.
            hemisphere: Hemisphere to use ("lh" or "rh").
        """

        atlas_path: str
        label: int
        hemisphere: str = "lh"

    @dataclass
    class SubcorticalROI:
        """Subcortical volume ROI from a volumetric atlas.

        Attributes:
            atlas_path: Path to the volumetric atlas NIfTI file.
            label: Integer label index within the volumetric atlas.
            tissues: Tissue compartments to include. One of "GM", "WM",
                or "both".
        """

        atlas_path: str
        label: int
        tissues: str = "GM"  # "GM", "WM", or "both"

    # ── Nested electrode config ───────────────────────────────────────

    @dataclass
    class ElectrodeConfig:
        """Electrode geometry for flex-search.

        Only gel_thickness is needed here -- the optimization leadfield uses
        point electrodes; gel_thickness is recorded in the manifest for
        downstream simulation.

        Attributes:
            shape: Electrode shape ("ellipse" or "rect").
            dimensions: Electrode dimensions in mm ([width, height]).
            gel_thickness: Conductive gel thickness in mm.
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
    visualize_valid_skin_region: bool = False
    skin_visualization_net: str | None = None

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


@dataclass
class FlexResult:
    """Result from a flex-search optimization run.

    Attributes:
        success: True if the optimization completed without error.
        output_folder: Absolute path to the output directory containing
            manifests, logs, and optional simulation results.
        function_values: Objective function value for each multistart run.
        best_value: Best (highest) objective value across all restarts.
        best_run_index: Zero-based index of the restart that produced
            the best result.
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

    Attributes:
        subject_id: Subject identifier matching the m2m directory name.
        leadfield_hdf: Path to the precomputed leadfield HDF5 file.
        roi_name: ROI CSV filename (e.g. "target.csv"). The ".csv"
            suffix is appended automatically if missing.
        electrodes: Electrode specification, either a single shared pool
            (PoolElectrodes) or separate per-channel buckets
            (BucketElectrodes). A plain dict is auto-converted in
            __post_init__.
        total_current: Total injected current in mA, split across
            channels.
        current_step: Current amplitude step size in mA for the sweep.
        channel_limit: Maximum current per channel in mA. None for no
            per-channel limit.
        roi_radius: Spherical ROI radius in mm for the target region.
        run_name: Optional name for this run. Defaults to a datetime
            stamp.
    """

    # ── Nested electrode types ─────────────────────────────────────────
    @dataclass
    class BucketElectrodes:
        """Separate electrode lists for each bipolar channel position.

        Attributes:
            e1_plus: Candidate electrodes for channel 1 anode.
            e1_minus: Candidate electrodes for channel 1 cathode.
            e2_plus: Candidate electrodes for channel 2 anode.
            e2_minus: Candidate electrodes for channel 2 cathode.
        """

        e1_plus: list[str]
        e1_minus: list[str]
        e2_plus: list[str]
        e2_minus: list[str]

    @dataclass
    class PoolElectrodes:
        """Single electrode pool -- all positions draw from the same set.

        Attributes:
            electrodes: List of electrode names available for any channel
                position.
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

    Attributes:
        success: True if the search completed without error.
        output_dir: Absolute path to the output directory.
        n_combinations: Total number of electrode/current combinations
            evaluated.
        results_csv: Path to the CSV file containing ranked results.
            None if the run failed before writing results.
        config_json: Path to the saved configuration JSON. None if the
            run failed before writing config.
    """

    success: bool
    output_dir: str
    n_combinations: int
    results_csv: str | None = None
    config_json: str | None = None


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
