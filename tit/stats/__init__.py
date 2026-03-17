"""Cluster-based permutation testing for TI-Toolbox.

Public API
----------
- ``run_group_comparison(config) -> GroupComparisonResult``
- ``run_correlation(config) -> CorrelationResult``
"""

from tit.stats.config import (
    CorrelationConfig,
    CorrelationResult,
    GroupComparisonConfig,
    GroupComparisonResult,
)
from tit.stats.permutation import run_correlation, run_group_comparison

__all__ = [
    "run_group_comparison",
    "run_correlation",
    "GroupComparisonConfig",
    "GroupComparisonResult",
    "CorrelationConfig",
    "CorrelationResult",
]
