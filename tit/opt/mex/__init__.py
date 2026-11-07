"""TI Multipolar (4-pair) Exhaustive Search Module."""

from typing import TYPE_CHECKING

from tit.opt.config import MExConfig, MExResult

if TYPE_CHECKING:  # static analysers see the lazily loaded names for hover/completion
    from tit.opt.mex.engine import MExSearchEngine
    from tit.opt.mex.mex import run_m_ex_search


def __getattr__(name: str):
    """Load SimNIBS only for a search, not for counting a plan (``tit.opt.mex.logic``)."""
    if name == "MExSearchEngine":
        from tit.opt.mex.engine import MExSearchEngine

        return MExSearchEngine
    if name == "run_m_ex_search":
        from tit.opt.mex.mex import run_m_ex_search

        return run_m_ex_search
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MExConfig",
    "MExResult",
    "MExSearchEngine",
    "run_m_ex_search",
]
