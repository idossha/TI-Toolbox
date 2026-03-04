"""
Shared matplotlib helpers.

Goals:
- Keep plotting code headless-safe (Docker/CI) without forcing backend changes at import-time.
- Avoid importing matplotlib globally when not needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


def suppress_matplotlib_findfont_noise() -> None:
    """
    No-op: matplotlib.font_manager silencing is now handled by tit.logger.setup_logging()
    in its third-party quieting loop.
    """


def ensure_headless_matplotlib_backend(backend: str = "Agg") -> None:
    """
    Best-effort backend setup for headless environments.

    Important:
    - This should be called BEFORE importing matplotlib.pyplot.
    - If a backend is already active, we do not force-change it.
    """
    import os
    import matplotlib

    os.environ.setdefault("MPLBACKEND", backend)

    # Silence noisy `findfont:` chatter (safe even if pyplot was already imported).
    suppress_matplotlib_findfont_noise()

    current = str(matplotlib.get_backend() or "")
    if current and current.lower() != backend.lower():
        # Backend already selected; don't override.
        return

    matplotlib.use(backend)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class SaveFigOptions:
    dpi: int = 600
    bbox_inches: str = "tight"
    facecolor: str = "white"
    edgecolor: str = "none"


def savefig_close(
    fig: Any,
    output_file: str,
    *,
    fmt: Optional[str] = None,
    opts: SaveFigOptions = SaveFigOptions(),
) -> str:
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
    import matplotlib.pyplot as plt

    plt.close(fig)

    return output_file
