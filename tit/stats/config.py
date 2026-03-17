"""Configuration dataclasses for cluster-based permutation testing.

Pure Python — no numpy, nibabel, or heavy dependencies.
Mirrors the tit.opt.config / tit.sim.config pattern.
"""

from dataclasses import dataclass, field
from enum import StrEnum

# ── Shared enums (private; aliased into both config classes) ──────────────


class _ClusterStat(StrEnum):
    MASS = "mass"
    SIZE = "size"


class _TissueType(StrEnum):
    GREY = "grey"
    WHITE = "white"
    ALL = "all"


# ── Private helper ────────────────────────────────────────────────────────


def _nifti_pattern_for_tissue(tissue: _TissueType) -> str:
    if tissue == _TissueType.GREY:
        return "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
    elif tissue == _TissueType.WHITE:
        return "white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
    else:
        return "{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"


# ── Configs ───────────────────────────────────────────────────────────────


@dataclass
class GroupComparisonConfig:
    """Configuration for group comparison permutation testing."""

    # ── Nested types ──────────────────────────────────────────────────
    ClusterStat = _ClusterStat
    TissueType = _TissueType

    class TestType(StrEnum):
        UNPAIRED = "unpaired"
        PAIRED = "paired"

    class Alternative(StrEnum):
        TWO_SIDED = "two-sided"
        GREATER = "greater"
        LESS = "less"

    @dataclass
    class Subject:
        """A single subject in a group comparison analysis."""

        subject_id: str
        simulation_name: str
        response: int  # 0 or 1

    # ── Fields ────────────────────────────────────────────────────────
    project_dir: str
    analysis_name: str
    subjects: list[Subject]

    # Statistical parameters
    test_type: TestType = TestType.UNPAIRED
    alternative: Alternative = Alternative.TWO_SIDED
    cluster_threshold: float = 0.05
    cluster_stat: ClusterStat = _ClusterStat.MASS
    n_permutations: int = 1000
    alpha: float = 0.05
    n_jobs: int = -1

    # Data selection
    tissue_type: TissueType = _TissueType.GREY
    nifti_file_pattern: str | None = None

    # Labels
    group1_name: str = "Responders"
    group2_name: str = "Non-Responders"
    value_metric: str = "Current Intensity"

    # Atlas
    atlas_files: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.nifti_file_pattern is None:
            self.nifti_file_pattern = _nifti_pattern_for_tissue(self.tissue_type)

        responders = [s for s in self.subjects if s.response == 1]
        non_responders = [s for s in self.subjects if s.response == 0]
        if len(responders) == 0 or len(non_responders) == 0:
            raise ValueError("Need at least one responder and one non-responder")

    # ── CSV loader ────────────────────────────────────────────────────

    @classmethod
    def load_subjects(cls, csv_path: str) -> list["GroupComparisonConfig.Subject"]:
        """Load group comparison subjects from a CSV file.

        Expected columns: subject_id, simulation_name, response (0 or 1).
        """
        import pandas as pd

        df = pd.read_csv(csv_path)
        required = {"subject_id", "simulation_name", "response"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        subjects = []
        for _, row in df.iterrows():
            sid = str(row["subject_id"]).replace("sub-", "")
            if sid.endswith(".0"):
                sid = sid[:-2]
            subjects.append(
                cls.Subject(
                    subject_id=sid,
                    simulation_name=str(row["simulation_name"]),
                    response=int(row["response"]),
                )
            )
        return subjects


@dataclass
class CorrelationConfig:
    """Configuration for correlation-based permutation testing."""

    # ── Nested types ──────────────────────────────────────────────────
    ClusterStat = _ClusterStat
    TissueType = _TissueType

    class CorrelationType(StrEnum):
        PEARSON = "pearson"
        SPEARMAN = "spearman"

    @dataclass
    class Subject:
        """A single subject in a correlation analysis."""

        subject_id: str
        simulation_name: str
        effect_size: float
        weight: float = 1.0

    # ── Fields ────────────────────────────────────────────────────────
    project_dir: str
    analysis_name: str
    subjects: list[Subject]

    # Statistical parameters
    correlation_type: CorrelationType = CorrelationType.PEARSON
    cluster_threshold: float = 0.05
    cluster_stat: ClusterStat = _ClusterStat.MASS
    n_permutations: int = 1000
    alpha: float = 0.05
    n_jobs: int = -1
    use_weights: bool = True

    # Data selection
    tissue_type: TissueType = _TissueType.GREY
    nifti_file_pattern: str | None = None

    # Labels
    effect_metric: str = "Effect Size"
    field_metric: str = "Electric Field Magnitude"

    # Atlas
    atlas_files: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.nifti_file_pattern is None:
            self.nifti_file_pattern = _nifti_pattern_for_tissue(self.tissue_type)

        if len(self.subjects) < 3:
            raise ValueError(
                f"Need at least 3 subjects for correlation, got {len(self.subjects)}"
            )

    # ── CSV loader ────────────────────────────────────────────────────

    @classmethod
    def load_subjects(cls, csv_path: str) -> list["CorrelationConfig.Subject"]:
        """Load correlation subjects from a CSV file.

        Expected columns: subject_id, simulation_name, effect_size.
        Optional column: weight.
        """
        import pandas as pd

        df = pd.read_csv(csv_path)
        required = {"subject_id", "simulation_name", "effect_size"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        has_weights = "weight" in df.columns
        subjects = []
        for _, row in df.iterrows():
            if pd.isna(row["subject_id"]) or pd.isna(row["effect_size"]):
                continue

            sid = row["subject_id"]
            if isinstance(sid, float):
                sid = str(int(sid))
            else:
                sid = str(sid).replace("sub-", "")
                if sid.endswith(".0"):
                    sid = sid[:-2]

            weight = (
                float(row["weight"])
                if has_weights and pd.notna(row.get("weight"))
                else 1.0
            )
            subjects.append(
                cls.Subject(
                    subject_id=sid,
                    simulation_name=str(row["simulation_name"]),
                    effect_size=float(row["effect_size"]),
                    weight=weight,
                )
            )

        if not subjects:
            raise ValueError("No valid subjects found in CSV")
        return subjects


# ── Results ───────────────────────────────────────────────────────────────


@dataclass
class GroupComparisonResult:
    """Result of a group comparison permutation test."""

    success: bool
    output_dir: str
    n_responders: int
    n_non_responders: int
    n_significant_voxels: int
    n_significant_clusters: int
    cluster_threshold: float
    analysis_time: float
    clusters: list
    log_file: str


@dataclass
class CorrelationResult:
    """Result of a correlation permutation test."""

    success: bool
    output_dir: str
    n_subjects: int
    n_significant_voxels: int
    n_significant_clusters: int
    cluster_threshold: float
    analysis_time: float
    clusters: list
    log_file: str
