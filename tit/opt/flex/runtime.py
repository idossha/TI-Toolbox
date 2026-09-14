"""Resolve the Flex integration belonging to the running TI-Toolbox code."""

from functools import lru_cache
import importlib.util
import logging
from pathlib import Path
import sys
from types import ModuleType

logger = logging.getLogger(__name__)
_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "resources/map-electrodes/tes_flex_optimization.py"
)
_MODULE = "simnibs.optimization.tes_flex_optimization.tit_checkout"


@lru_cache(maxsize=1)
def integration_module() -> ModuleType:
    """Use the checkout's patch without rewriting the installed SimNIBS package.

    Wheel installations without the resource use the image-provided integration;
    the builder still verifies its required capability. Import failures propagate
    rather than silently running a different scientific implementation.
    """
    if not _SOURCE.is_file():
        from simnibs.optimization.tes_flex_optimization import tes_flex_optimization

        return tes_flex_optimization
    spec = importlib.util.spec_from_file_location(_MODULE, _SOURCE)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load the TI-Toolbox Flex integration: {_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_MODULE, None)
        raise
    logger.info("Using TI-Toolbox Flex integration from %s", _SOURCE)
    return module


def optimization_class() -> type:
    """Return the optimizer from the selected integration."""
    return integration_module().TesFlexOptimization
