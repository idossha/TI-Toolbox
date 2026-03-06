"""TI-Toolbox optimization package.

Public API
----------
- ``run_flex_search(config) -> FlexResult``  — differential-evolution optimization
- ``run_ex_search(config) -> ExResult``      — exhaustive / grid search

``run_flex_search`` is imported eagerly (its SimNIBS deps are inside function
bodies). ``run_ex_search`` is lazy because ``ex/engine.py`` imports SimNIBS at
module level.
"""

from __future__ import annotations

from typing import Any

from tit.opt.config import (
    FlexConfig,
    FlexElectrodeConfig,
    FlexResult,
    ExConfig,
    ExCurrentConfig,
    ExResult,
    SphericalROI,
    AtlasROI,
    SubcorticalROI,
    BucketElectrodes,
    PoolElectrodes,
    OptGoal,
    FieldPostproc,
    NonROIMethod,
)
from tit.opt.flex.flex import run_flex_search

__all__ = [
    # Config classes
    "FlexConfig",
    "FlexElectrodeConfig",
    "FlexResult",
    "ExConfig",
    "ExCurrentConfig",
    "ExResult",
    # ROI types
    "SphericalROI",
    "AtlasROI",
    "SubcorticalROI",
    # Electrode types
    "BucketElectrodes",
    "PoolElectrodes",
    # Enums
    "OptGoal",
    "FieldPostproc",
    "NonROIMethod",
    # Functions
    "run_flex_search",
    "run_ex_search",
]


def __getattr__(name: str) -> Any:
    """Lazy-load run_ex_search (ex/engine.py imports SimNIBS at module level)."""
    if name == "run_ex_search":
        from tit.opt.ex.ex import run_ex_search

        return run_ex_search
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
