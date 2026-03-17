"""TI-Toolbox optimization package.

Public API
----------
- ``run_flex_search(config) -> FlexResult``  -- differential-evolution optimization
- ``run_ex_search(config) -> ExResult``      -- exhaustive / grid search
"""

from tit.opt.config import (
    FlexConfig,
    FlexResult,
    ExConfig,
    ExResult,
)
from tit.opt.ex.ex import run_ex_search
from tit.opt.flex.flex import run_flex_search

__all__ = [
    # Config classes
    "FlexConfig",
    "FlexResult",
    "ExConfig",
    "ExResult",
    # Functions
    "run_flex_search",
    "run_ex_search",
]
