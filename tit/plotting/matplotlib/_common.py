"""
Shared matplotlib helpers.

Goals:
- Keep plotting code headless-safe (Docker/CI) without forcing backend changes at import-time.
- Avoid importing matplotlib globally when not needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


def ensure_headless_matplotlib_backend(backend: str = "Agg") -> None:
    """
    Best-effort backend setup for headless environments.

    Important:
    - This should be called BEFORE importing matplotlib.pyplot.
    - If a backend is already active, we do not force-change it.
    """
    try:
        import os

        # If the user already set a backend, respect it.
        os.environ.setdefault("MPLBACKEND", backend)

        import matplotlib

        current = str(matplotlib.get_backend() or "")
        if current and current.lower() != backend.lower():
            # Backend already selected; don't override.
            return

        # If matplotlib is not yet configured, set it.
        try:
            matplotlib.use(backend)  # type: ignore[attr-defined]
        except Exception:
            # Backend may already be set or pyplot already imported.
            return
    except Exception:
        # Matplotlib not installed or failed to configure; callers should handle.
        return


@dataclass(frozen=True)
class SaveFigOptions:
    dpi: int = 300
    bbox_inches: str = "tight"
    facecolor: str = "white"
    edgecolor: str = "none"


def savefig_close(fig: Any, output_file: str, *, fmt: Optional[str] = None, opts: SaveFigOptions = SaveFigOptions()) -> str:
    """
    Save a matplotlib Figure and close it.

    Uses fig.savefig (not plt.savefig) to avoid relying on global pyplot state.
    """
    fig.savefig(
        output_file,
        dpi=opts.dpi,
        bbox_inches=opts.bbox_inches,
        facecolor=opts.facecolor,
        edgecolor=opts.edgecolor,
        format=fmt,
    )
    try:
        import matplotlib.pyplot as plt

        plt.close(fig)
    except Exception:
        pass
    return output_file


