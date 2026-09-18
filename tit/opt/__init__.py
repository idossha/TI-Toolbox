"""TI-Toolbox optimization package.

Provides two electrode-placement optimization strategies for temporal
interference (TI) brain stimulation:

* **Flex-search** -- differential-evolution (DE) optimization via SimNIBS
  ``TesFlexOptimization``.  Finds continuous electrode positions on the
  scalp that maximize field strength, peak intensity, or focality in a
  user-defined ROI.
* **Exhaustive search** -- brute-force grid evaluation over a discrete
  electrode pool, sweeping current amplitudes at fixed step sizes.
* **Multipolar exhaustive search** -- the same brute-force evaluation
  extended to four bipolar electrode pairs (eight electrodes), scored
  with the N>2 mTI envelope.

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
MExConfig
    Configuration dataclass for multipolar exhaustive search.
MExResult
    Result container returned by :func:`run_m_ex_search`.
run_flex_search
    Run differential-evolution electrode placement optimization.
run_ex_search
    Run exhaustive grid search over electrode combinations.
run_m_ex_search
    Run multipolar exhaustive grid search over four electrode pairs.

See Also
--------
tit.opt.flex : Flex-search subpackage with builder, manifest, and pareto utilities.
tit.opt.ex : Exhaustive-search subpackage with engine and result handling.
tit.opt.mex : Multipolar exhaustive-search subpackage.
tit.opt.leadfield : Leadfield matrix generation via SimNIBS.

Examples
--------
>>> from tit.opt import FlexConfig, run_flex_search
>>> cfg = FlexConfig(
...     subject_id="ernie", goal="mean", postproc="max_TI", current_mA=1.0,
...     electrode=FlexConfig.ElectrodeConfig(),
...     roi=FlexConfig.SphericalROI(x=-35.0, y=5.0, z=5.0, radius=10.0, use_mni=True),
... )
>>> res = run_flex_search(cfg)  # doctest: +SKIP
>>> res.success, res.best_value  # doctest: +SKIP
(True, 0.31)

Notes
-----
``run_flex_search``, ``run_ex_search`` and ``run_m_ex_search`` are loaded
lazily on first attribute access so that importing ``tit.opt`` for its
config classes does not import SimNIBS.
"""

from typing import TYPE_CHECKING

from tit.opt.config import (
    FlexConfig,
    FlexResult,
    ExConfig,
    ExResult,
    MExConfig,
    MExResult,
)

if TYPE_CHECKING:  # static analysers see the lazily loaded runners for hover/completion
    from tit.opt.ex.ex import run_ex_search
    from tit.opt.flex.flex import run_flex_search
    from tit.opt.mex.mex import run_m_ex_search


def __getattr__(name: str):
    """Load scientific runners only when called for, not for config or mask imports."""
    from importlib import import_module

    modules = {
        "run_ex_search": "tit.opt.ex.ex",
        "run_flex_search": "tit.opt.flex.flex",
        "run_m_ex_search": "tit.opt.mex.mex",
    }
    if name not in modules:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(modules[name]), name)
    globals()[name] = value
    return value


__all__ = [
    # Config classes
    "FlexConfig",
    "FlexResult",
    "ExConfig",
    "ExResult",
    "MExConfig",
    "MExResult",
    # Functions
    "run_flex_search",
    "run_ex_search",
    "run_m_ex_search",
]
