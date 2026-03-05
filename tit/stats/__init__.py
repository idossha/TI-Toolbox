"""Cluster-based permutation testing for TI-Toolbox.

Heavy dependencies (nibabel, scipy, numpy) are loaded lazily — only when
``run_group_comparison`` or ``run_correlation`` are called.
"""

from __future__ import annotations

import importlib
from typing import Any

from tit.stats.config import (
    Alternative,
    ClusterStat,
    CorrelationConfig,
    CorrelationResult,
    CorrelationSubject,
    CorrelationType,
    GroupComparisonConfig,
    GroupComparisonResult,
    GroupSubject,
    TestType,
    TissueType,
    load_correlation_subjects,
    load_group_subjects,
)

__all__ = [
    # Run functions (lazy)
    "run_group_comparison",
    "run_correlation",
    # Configs
    "GroupComparisonConfig",
    "CorrelationConfig",
    # Results
    "GroupComparisonResult",
    "CorrelationResult",
    # Subject types
    "GroupSubject",
    "CorrelationSubject",
    # Enums
    "TissueType",
    "ClusterStat",
    "TestType",
    "Alternative",
    "CorrelationType",
    # CSV loaders
    "load_group_subjects",
    "load_correlation_subjects",
]


def __getattr__(name: str) -> Any:
    if name in ("run_group_comparison", "run_correlation"):
        mod = importlib.import_module(".permutation", __name__)
        return getattr(mod, name)
    if name == "nifti":
        return importlib.import_module(".nifti", __name__)
    raise AttributeError(name)
