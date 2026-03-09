"""Cluster-based permutation testing for TI-Toolbox.

Public API
----------
- ``run_group_comparison(config) -> GroupComparisonResult``
- ``run_correlation(config) -> CorrelationResult``
"""

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
from tit.stats.permutation import run_correlation, run_group_comparison

__all__ = [
    # Run functions
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
