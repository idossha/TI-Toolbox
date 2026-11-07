"""Flex-search optimization subpackage.

Provides differential-evolution (DE) electrode placement optimization
via SimNIBS ``TesFlexOptimization``.  The optimizer finds continuous
electrode positions on the scalp that maximize field strength, peak
intensity, or focality in a target ROI.

Public API
----------
run_flex_search
    Main entry point -- accepts a :class:`~tit.opt.config.FlexConfig`
    and returns a :class:`~tit.opt.config.FlexResult`.

Submodules
----------
builder
    SimNIBS object construction.
manifest
    Read/write ``flex_meta.json`` run manifests.
pareto
    Pareto-front sweep over focality threshold grids.
utils
    ROI configuration, output naming, and log-line parsing.

See Also
--------
tit.opt.config.FlexConfig : Configuration dataclass for flex-search.
tit.opt.config.FlexResult : Result container.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # static analysers see the lazily loaded runner for hover/completion
    from tit.opt.flex.flex import run_flex_search


def __getattr__(name: str):
    """Load the runner only when called for, not for reading a run's manifest."""
    if name == "run_flex_search":
        from tit.opt.flex.flex import run_flex_search

        return run_flex_search
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["run_flex_search"]
