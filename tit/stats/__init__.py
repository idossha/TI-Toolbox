"""Cluster-based permutation testing for TI-Toolbox.

Public API
----------
- ``run_group_comparison(config) -> GroupComparisonResult``
- ``run_correlation(config) -> CorrelationResult``

Heavy dependencies (nibabel, scipy) are loaded lazily — ``permutation.py``
imports nibabel at module level, so ``run_group_comparison`` and
``run_correlation`` are resolved via ``__getattr__`` to avoid pulling in
nibabel on ``import tit.stats``.
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
    # Run functions (lazy — nibabel at module level in permutation.py)
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
    """Lazy-load run functions to avoid importing nibabel eagerly."""
    if name in ("run_group_comparison", "run_correlation"):
        mod = importlib.import_module(".permutation", __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
