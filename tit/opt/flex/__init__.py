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
    SimNIBS object construction and HTML report generation.
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

from tit.opt.flex.flex import run_flex_search

__all__ = ["run_flex_search"]
