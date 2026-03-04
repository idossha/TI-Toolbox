"""Configuration dataclasses for TI optimization.

Pure Python — no SimNIBS, numpy, or heavy dependencies.
Mirrors the tit.sim.config pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Union

# ── Enums ──────────────────────────────────────────────────────────────────


class OptGoal(str, Enum):
    """Optimization goal."""

    MEAN = "mean"
    MAX = "max"
    FOCALITY = "focality"


class FieldPostproc(str, Enum):
    """Field post-processing method."""

    MAX_TI = "max_TI"
    DIR_TI_NORMAL = "dir_TI_normal"
    DIR_TI_TANGENTIAL = "dir_TI_tangential"


class NonROIMethod(str, Enum):
    """Non-ROI specification method for focality optimization."""

    EVERYTHING_ELSE = "everything_else"
    SPECIFIC = "specific"


# ── Flex-search ROI types ────────────────────────────────────────────────────


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


ROISpec = Union[SphericalROI, AtlasROI, SubcorticalROI]


# ── Flex-search config ───────────────────────────────────────────────────────


@dataclass
class FlexElectrodeConfig:
    """Electrode geometry for flex-search."""

    shape: str = "ellipse"  # "ellipse" or "rect"
    dimensions: List[float] = field(default_factory=lambda: [8.0, 8.0])
    thickness: float = 4.0


@dataclass
class FlexConfig:
    """Full configuration for flex-search optimization."""

    # ── required ──
    subject_id: str
    project_dir: str
    goal: OptGoal
    postproc: FieldPostproc
    current_mA: float
    electrode: FlexElectrodeConfig
    roi: ROISpec

    # ── focality ──
    non_roi_method: Optional[NonROIMethod] = None
    non_roi: Optional[ROISpec] = None
    thresholds: Optional[str] = None

    # ── eeg mapping ──
    eeg_net: Optional[str] = None
    enable_mapping: bool = False
    disable_mapping_simulation: bool = False

    # ── output ──
    output_folder: Optional[str] = None
    run_final_electrode_simulation: bool = False

    # ── solver ──
    n_multistart: int = 1
    max_iterations: Optional[int] = None
    population_size: Optional[int] = None
    tolerance: Optional[float] = None
    mutation: Optional[str] = None
    recombination: Optional[float] = None
    cpus: Optional[int] = None

    # ── debug ──
    detailed_results: bool = False
    visualize_valid_skin_region: bool = False
    skin_visualization_net: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.goal, str):
            self.goal = OptGoal(self.goal)
        if isinstance(self.postproc, str):
            self.postproc = FieldPostproc(self.postproc)
        if isinstance(self.non_roi_method, str):
            self.non_roi_method = NonROIMethod(self.non_roi_method)
        if self.goal is OptGoal.FOCALITY and self.non_roi is None:
            raise ValueError("goal='focality' requires a non_roi specification")
        if self.thresholds is not None:
            for part in self.thresholds.split(","):
                float(part.strip())


@dataclass
class FlexResult:
    """Result from a flex-search optimization run."""

    success: bool
    output_folder: str
    function_values: List[float]
    best_value: float
    best_run_index: int


# ── Exhaustive search config ─────────────────────────────────────────────────


@dataclass
class BucketElectrodes:
    """Separate electrode lists for each bipolar channel position."""

    e1_plus: List[str]
    e1_minus: List[str]
    e2_plus: List[str]
    e2_minus: List[str]


@dataclass
class PoolElectrodes:
    """Single electrode pool — all positions draw from the same set."""

    electrodes: List[str]


ElectrodeSpec = Union[BucketElectrodes, PoolElectrodes]


@dataclass
class ExCurrentConfig:
    """Current parameters for exhaustive search."""

    total_current: float = 2.0
    current_step: float = 0.5
    channel_limit: Optional[float] = None


@dataclass
class ExConfig:
    """Full configuration for exhaustive search optimization."""

    subject_id: str
    project_dir: str
    leadfield_hdf: str
    roi_name: str
    electrodes: ElectrodeSpec
    currents: ExCurrentConfig = field(default_factory=ExCurrentConfig)
    roi_radius: float = 3.0
    eeg_net: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.currents, dict):
            self.currents = ExCurrentConfig(**self.currents)
        if isinstance(self.electrodes, dict):
            if "electrodes" in self.electrodes:
                self.electrodes = PoolElectrodes(**self.electrodes)
            else:
                self.electrodes = BucketElectrodes(**self.electrodes)
        if not self.roi_name.endswith(".csv"):
            self.roi_name += ".csv"


@dataclass
class ExResult:
    """Result from an exhaustive search run."""

    success: bool
    output_dir: str
    n_combinations: int
    results_csv: Optional[str] = None
    results_json: Optional[str] = None
