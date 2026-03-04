"""TI Exhaustive Search Module."""

from __future__ import annotations


# Lazy import to avoid SimNIBS at import time
def run_ex_search(config, logger=None):
    from .ex import run_ex_search as _run

    return _run(config, logger=logger)


__all__ = ["run_ex_search"]
