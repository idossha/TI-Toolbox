"""TI-Toolbox optimizer public API."""

from tit.opt.config import (
    # Enums
    OptGoal,
    FieldPostproc,
    NonROIMethod,
    # Flex-search
    FlexConfig,
    FlexElectrodeConfig,
    FlexResult,
    SphericalROI,
    AtlasROI,
    SubcorticalROI,
    # Exhaustive search
    ExConfig,
    ExResult,
    BucketElectrodes,
    PoolElectrodes,
    ExCurrentConfig,
)
from tit.opt.flex.flex import run_flex_search
from tit.opt.ex.ex import run_ex_search

__all__ = [
    # Enums
    "OptGoal",
    "FieldPostproc",
    "NonROIMethod",
    # Flex-search
    "FlexConfig",
    "FlexElectrodeConfig",
    "FlexResult",
    "SphericalROI",
    "AtlasROI",
    "SubcorticalROI",
    "run_flex_search",
    # Exhaustive search
    "ExConfig",
    "ExResult",
    "BucketElectrodes",
    "PoolElectrodes",
    "ExCurrentConfig",
    "run_ex_search",
]
