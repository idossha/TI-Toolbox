"""Configuration dataclasses for TI optimization.

Pure Python — no SimNIBS, numpy, or heavy dependencies.
Mirrors the tit.sim.config pattern.
"""

from dataclasses import dataclass, field
from enum import StrEnum

# ── Flex-search config ───────────────────────────────────────────────────────


@dataclass
class FlexConfig:
    """Full configuration for flex-search optimization."""

    # ── Nested enums ──────────────────────────────────────────────────

    class OptGoal(StrEnum):
        """Optimization goal."""

        MEAN = "mean"
        MAX = "max"
        FOCALITY = "focality"

    class FieldPostproc(StrEnum):
        """Field post-processing method."""

        MAX_TI = "max_TI"
        DIR_TI_NORMAL = "dir_TI_normal"
        DIR_TI_TANGENTIAL = "dir_TI_tangential"

    class NonROIMethod(StrEnum):
        """Non-ROI specification method for focality optimization."""

        EVERYTHING_ELSE = "everything_else"
        SPECIFIC = "specific"

    # ── Nested ROI types ──────────────────────────────────────────────

    @dataclass
    class SphericalROI:
        """Spherical region of interest defined by center + radius."""

        x: float
        y: float
        z: float
        radius: float = 10.0
        use_mni: bool = False

    @dataclass
    class AtlasROI:
        """Cortical surface ROI from a FreeSurfer annotation atlas."""

        atlas_path: str
        label: int
        hemisphere: str = "lh"

    @dataclass
    class SubcorticalROI:
        """Subcortical volume ROI from a volumetric atlas."""

        atlas_path: str
        label: int
        tissues: str = "GM"  # "GM", "WM", or "both"

    # ── Nested electrode config ───────────────────────────────────────

    @dataclass
    class ElectrodeConfig:
        """Electrode geometry for flex-search.

        Only gel_thickness is needed here — the optimization leadfield uses
        point electrodes; gel_thickness is recorded in the manifest for
        downstream simulation.
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
    visualize_valid_skin_region: bool = False
    skin_visualization_net: str | None = None

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


@dataclass
class FlexResult:
    """Result from a flex-search optimization run."""

    success: bool
    output_folder: str
    function_values: list[float]
    best_value: float
    best_run_index: int


# ── Exhaustive search config ─────────────────────────────────────────────────


@dataclass
class ExConfig:
    """Full configuration for exhaustive search optimization."""

    # ── Nested electrode types ─────────────────────────────────────────
    @dataclass
    class BucketElectrodes:
        """Separate electrode lists for each bipolar channel position."""

        e1_plus: list[str]
        e1_minus: list[str]
        e2_plus: list[str]
        e2_minus: list[str]

    @dataclass
    class PoolElectrodes:
        """Single electrode pool — all positions draw from the same set."""

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
    """Result from an exhaustive search run."""

    success: bool
    output_dir: str
    n_combinations: int
    results_csv: str | None = None
    config_json: str | None = None
