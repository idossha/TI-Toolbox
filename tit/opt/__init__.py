"""TI-Toolbox optimization package.

Provides two electrode-placement optimization strategies for temporal
interference (TI) brain stimulation:

* **Flex-search** -- differential-evolution (DE) optimization via SimNIBS
  ``TesFlexOptimization``.  Finds continuous electrode positions on the
  scalp that maximize field strength, peak intensity, or focality in a
  user-defined ROI.
* **Exhaustive search** -- brute-force grid evaluation over a discrete
  electrode pool, sweeping current amplitudes at fixed step sizes.

Public API
----------
FlexConfig
    Configuration dataclass for flex-search optimization.
FlexResult
    Result container returned by :func:`run_flex_search`.
ExConfig
    Configuration dataclass for exhaustive search.
ExResult
    Result container returned by :func:`run_ex_search`.
run_flex_search
    Run differential-evolution electrode placement optimization.
run_ex_search
    Run exhaustive grid search over electrode combinations.

See Also
--------
tit.opt.flex : Flex-search subpackage with builder, manifest, and pareto utilities.
tit.opt.ex : Exhaustive-search subpackage with engine and result handling.
tit.opt.leadfield : Leadfield matrix generation via SimNIBS.
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
