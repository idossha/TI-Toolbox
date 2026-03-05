"""Configuration dataclasses for cluster-based permutation testing.

Pure Python — no numpy, nibabel, or heavy dependencies.
Mirrors the tit.opt.config / tit.sim.config pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

# ── Enums ──────────────────────────────────────────────────────────────────


class TissueType(str, Enum):
    GREY = "grey"
    WHITE = "white"
    ALL = "all"


class ClusterStat(str, Enum):
    MASS = "mass"
    SIZE = "size"


class TestType(str, Enum):
    UNPAIRED = "unpaired"
    PAIRED = "paired"


class Alternative(str, Enum):
    TWO_SIDED = "two-sided"
    GREATER = "greater"
    LESS = "less"


class CorrelationType(str, Enum):
    PEARSON = "pearson"
    SPEARMAN = "spearman"


# ── Subject entries ────────────────────────────────────────────────────────


@dataclass
class GroupSubject:
    """A single subject in a group comparison analysis."""

    subject_id: str
    simulation_name: str
    response: int  # 0 or 1


@dataclass
class CorrelationSubject:
    """A single subject in a correlation analysis."""

    subject_id: str
    simulation_name: str
    effect_size: float
    weight: float = 1.0


# ── Configs ────────────────────────────────────────────────────────────────


def _nifti_pattern_for_tissue(tissue: TissueType) -> str:
    if tissue == TissueType.GREY:
        return "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
    elif tissue == TissueType.WHITE:
        return "white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
    else:
        return "{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"


@dataclass
class GroupComparisonConfig:
    """Configuration for group comparison permutation testing."""

    project_dir: str
    analysis_name: str
    subjects: List[GroupSubject]

    # Statistical parameters
    test_type: TestType = TestType.UNPAIRED
    alternative: Alternative = Alternative.TWO_SIDED
    cluster_threshold: float = 0.05
    cluster_stat: ClusterStat = ClusterStat.MASS
    n_permutations: int = 1000
    alpha: float = 0.05
    n_jobs: int = -1

    # Data selection
    tissue_type: TissueType = TissueType.GREY
    nifti_file_pattern: Optional[str] = None

    # Labels
    group1_name: str = "Responders"
    group2_name: str = "Non-Responders"
    value_metric: str = "Current Intensity"

    # Atlas
    atlas_files: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.nifti_file_pattern is None:
            self.nifti_file_pattern = _nifti_pattern_for_tissue(self.tissue_type)

        responders = [s for s in self.subjects if s.response == 1]
        non_responders = [s for s in self.subjects if s.response == 0]
        if len(responders) == 0 or len(non_responders) == 0:
            raise ValueError("Need at least one responder and one non-responder")


@dataclass
class CorrelationConfig:
    """Configuration for correlation-based permutation testing."""

    project_dir: str
    analysis_name: str
    subjects: List[CorrelationSubject]

    # Statistical parameters
    correlation_type: CorrelationType = CorrelationType.PEARSON
    cluster_threshold: float = 0.05
    cluster_stat: ClusterStat = ClusterStat.MASS
    n_permutations: int = 1000
    alpha: float = 0.05
    n_jobs: int = -1
    use_weights: bool = True

    # Data selection
    tissue_type: TissueType = TissueType.GREY
    nifti_file_pattern: Optional[str] = None

    # Labels
    effect_metric: str = "Effect Size"
    field_metric: str = "Electric Field Magnitude"

    # Atlas
    atlas_files: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.nifti_file_pattern is None:
            self.nifti_file_pattern = _nifti_pattern_for_tissue(self.tissue_type)

        if len(self.subjects) < 3:
            raise ValueError(
                f"Need at least 3 subjects for correlation, got {len(self.subjects)}"
            )


# ── Results ────────────────────────────────────────────────────────────────


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


# ── CSV loading utilities ──────────────────────────────────────────────────


def load_group_subjects(csv_path: str) -> List[GroupSubject]:
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
            GroupSubject(
                subject_id=sid,
                simulation_name=str(row["simulation_name"]),
                response=int(row["response"]),
            )
        )
    return subjects


def load_correlation_subjects(csv_path: str) -> List[CorrelationSubject]:
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
            float(row["weight"]) if has_weights and pd.notna(row.get("weight")) else 1.0
        )
        subjects.append(
            CorrelationSubject(
                subject_id=sid,
                simulation_name=str(row["simulation_name"]),
                effect_size=float(row["effect_size"]),
                weight=weight,
            )
        )

    if not subjects:
        raise ValueError("No valid subjects found in CSV")
    return subjects
