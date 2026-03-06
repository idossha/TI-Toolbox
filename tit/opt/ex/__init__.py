"""TI Exhaustive Search Module.

Both ``run_ex_search`` and ``ExSearchEngine`` require SimNIBS (``engine.py``
imports it at module level) and are loaded lazily.
"""

from __future__ import annotations

from typing import Any

__all__ = ["run_ex_search", "ExSearchEngine"]


def __getattr__(name: str) -> Any:
    if name == "run_ex_search":
        from tit.opt.ex.ex import run_ex_search

        return run_ex_search
    if name == "ExSearchEngine":
        from tit.opt.ex.engine import ExSearchEngine

        return ExSearchEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
