"""Cluster-based permutation testing for TI-Toolbox.

Provides group comparison and correlation analyses with cluster-based
permutation correction for multiple comparisons.  Both workflows produce
NIfTI output maps, diagnostic plots, and text summaries written to the
BIDS derivatives tree.

Public API
----------
run_group_comparison
    Two-group voxelwise comparison with cluster-based permutation correction.
run_correlation
    Voxelwise brain-behavior correlation with cluster-based permutation
    correction (ACES-style).
GroupComparisonConfig
    Configuration dataclass for group comparison.
GroupComparisonResult
    Result container for group comparison.
CorrelationConfig
    Configuration dataclass for correlation analysis.
CorrelationResult
    Result container for correlation analysis.

See Also
--------
tit.analyzer : Single-subject ROI-level field analysis.
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
