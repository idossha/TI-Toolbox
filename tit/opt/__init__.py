"""
TI-Toolbox optimization package
"""

from __future__ import annotations

# NOTE:
# Keep this package import lightweight. Some optimization submodules (e.g. flex)
# depend on optional scientific/GUI stacks that aren't available in all
# environments (unit tests, minimal installs, etc.).
#
# Access `tit.opt.flex` via attribute access (lazy import) instead of importing
# it unconditionally here.

import importlib
from typing import Any

from tit.opt.config import ExConfig, ExResult
from tit.opt.ex.ex import run_ex_search

__all__ = ["flex", "run_ex_search", "ExConfig", "ExResult"]


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name == "flex":
        return importlib.import_module(".flex", __name__)
    raise AttributeError(name)
