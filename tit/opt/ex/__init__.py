"""TI Exhaustive Search Module."""

from typing import TYPE_CHECKING

from tit.opt.config import ExConfig, ExResult

if TYPE_CHECKING:  # static analysers see the lazily loaded names for hover/completion
    from tit.opt.ex.engine import ExSearchEngine
    from tit.opt.ex.ex import run_ex_search


def __getattr__(name: str):
    """Load SimNIBS only for a search, not for listing saved ROIs (``tit.opt.ex.roi``)."""
    if name == "ExSearchEngine":
        from tit.opt.ex.engine import ExSearchEngine

        return ExSearchEngine
    if name == "run_ex_search":
        from tit.opt.ex.ex import run_ex_search

        return run_ex_search
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ExConfig",
    "ExResult",
    "ExSearchEngine",
    "run_ex_search",
]
