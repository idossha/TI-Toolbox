"""TI-Toolbox analyzer — unified field analysis for mesh and voxel spaces."""

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
