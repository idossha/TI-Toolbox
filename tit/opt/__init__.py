"""TI-Toolbox optimization package.

Public API
----------
- ``run_flex_search(config) -> FlexResult``  -- differential-evolution optimization
- ``run_ex_search(config) -> ExResult``      -- exhaustive / grid search
- ``run_mp_search(config) -> MultiPolarResult`` -- multi-polar leadfield DE search
"""

from tit.opt.config import (
    ExConfig,
    ExResult,
    FlexConfig,
    FlexResult,
    MultiPolarConfig,
    MultiPolarResult,
)
from tit.opt.ex.ex import run_ex_search
from tit.opt.flex.flex import run_flex_search
from tit.opt.mp import run_mp_search

__all__ = [
    # Config classes
    "FlexConfig",
    "FlexResult",
    "ExConfig",
    "ExResult",
    "MultiPolarConfig",
    "MultiPolarResult",
    # Functions
    "run_flex_search",
    "run_ex_search",
    "run_mp_search",
]
