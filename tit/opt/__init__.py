"""TI-Toolbox optimization package.

Public API
----------
- ``run_flex_search(config) -> FlexResult``  -- differential-evolution optimization
- ``run_ex_search(config) -> ExResult``      -- exhaustive / grid search
"""

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
from tit.opt.ex.ex import run_ex_search
from tit.opt.flex.flex import run_flex_search
from tit.opt.secondary import BaseSimulationFields, load_base_simulation_fields

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
    "BaseSimulationFields",
    "load_base_simulation_fields",
]
