"""TI-Toolbox optimization package.

Provides two electrode-placement optimization strategies for temporal
interference (TI) brain stimulation:

* **Flex-search** -- differential-evolution (DE) optimization via SimNIBS
  ``TesFlexOptimization``.  Finds continuous electrode positions on the
  scalp that maximize field strength, peak intensity, or focality in a
  user-defined ROI.
* **Exhaustive search** -- brute-force grid evaluation over a discrete
  electrode pool, sweeping current amplitudes at fixed step sizes.
* **Multi-polar leadfield search** -- differential-evolution optimization
  over a precomputed leadfield matrix for N-pair multipolar (mTI) montages.

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
MultiPolarConfig
    Configuration dataclass for multi-polar leadfield search.
MultiPolarResult
    Result container returned by :func:`run_mp_search`.
MTIFrequencyPlan
    Per-pair carrier/phase assignment for a multipolar (mTI) montage.
run_flex_search
    Run differential-evolution electrode placement optimization.
run_ex_search
    Run exhaustive grid search over electrode combinations.
run_mp_search
    Run differential-evolution multi-polar leadfield search.
validate_band_separation
    Validate carrier-band separation for an :class:`MTIFrequencyPlan`.

See Also
--------
tit.opt.flex : Flex-search subpackage with builder, manifest, and pareto utilities.
tit.opt.ex : Exhaustive-search subpackage with engine and result handling.
tit.opt.mp : Multi-polar leadfield search subpackage.
tit.opt.leadfield : Leadfield matrix generation via SimNIBS.
"""

from tit.opt.config import (
    ExConfig,
    ExResult,
    FlexConfig,
    FlexResult,
    MTIFrequencyPlan,
    MultiPolarConfig,
    MultiPolarResult,
    validate_band_separation,
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
    "MTIFrequencyPlan",
    # Functions
    "run_flex_search",
    "run_ex_search",
    "run_mp_search",
    "validate_band_separation",
]
