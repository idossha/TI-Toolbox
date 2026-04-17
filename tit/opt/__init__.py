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
    SecondaryExConfig,
    SecondaryExResult,
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
from tit.opt.secondary import (
    BaseMontageSpec,
    BaseSimulationFields,
    load_base_montage,
    load_base_simulation_fields,
)
from tit.opt.secondary_ex import run_secondary_ex_search

__all__ = [
    # Config classes
    "FlexConfig",
    "FlexElectrodeConfig",
    "FlexResult",
    "ExConfig",
    "ExCurrentConfig",
    "ExResult",
    "SecondaryExConfig",
    "SecondaryExResult",
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
    "run_secondary_ex_search",
    "BaseMontageSpec",
    "load_base_montage",
    "BaseSimulationFields",
    "load_base_simulation_fields",
]
