"""Unified field analysis for mesh and voxel spaces.

Provides single-subject ROI analysis (spherical and cortical), multi-subject
group analysis with summary statistics, and automatic field file selection
for TI and mTI simulations.

Public API
----------
Analyzer
    Single-subject field analyzer for mesh and voxel spaces.
AnalysisResult
    Typed container for per-subject ROI statistics.
GroupResult
    Container for multi-subject group analysis outcomes.
run_group_analysis
    Run the same ROI analysis across multiple subjects and summarise.
select_field_file
    Resolve the correct field file path for a given subject/simulation/space.

See Also
--------
tit.stats : Cluster-based permutation testing for group-level inference.
tit.sim : TI/mTI simulation engine that produces the field files analyzed here.
"""

from tit.analyzer.analyzer import Analyzer, AnalysisResult
from tit.analyzer.field_selector import select_field_file
from tit.analyzer.group import GroupResult, run_group_analysis

__all__ = [
    "Analyzer",
    "AnalysisResult",
    "GroupResult",
    "run_group_analysis",
    "select_field_file",
]
