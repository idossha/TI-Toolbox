"""
Simple TI-Toolbox metric visualizations (matplotlib).

Centralizes plots that were previously implemented in optimizer/analyzer modules.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from ._common import SaveFigOptions, ensure_headless_matplotlib_backend, savefig_close


def plot_montage_distributions(
    *,
    timax_values: Sequence[float],
    timean_values: Sequence[float],
    focality_values: Sequence[float],
    output_file: str,
    dpi: int = 300,
) -> str | None:
    """
    Create 3 side-by-side histograms for TImax, TImean and Focality distributions.
    """
    if (not timax_values) and (not timean_values) and (not focality_values):
        return None

    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    configs = [
        (timax_values, axes[0], "TImax (V/m)", "TImax Distribution", "#2196F3"),
        (timean_values, axes[1], "TImean (V/m)", "TImean Distribution", "#4CAF50"),
        (focality_values, axes[2], "Focality", "Focality Distribution", "#FF9800"),
    ]

    for values, ax, xlabel, title, color in configs:
        if values:
            ax.hist(values, bins=20, color=color, edgecolor="black", alpha=0.7)
            ax.set_xlabel(xlabel, fontsize=12)
            ax.set_ylabel("Frequency", fontsize=12)
            ax.set_title(title, fontsize=14, fontweight="bold")
            ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    return savefig_close(fig, output_file, opts=SaveFigOptions(dpi=dpi))


def plot_intensity_vs_focality(
    *,
    intensity: Sequence[float],
    focality: Sequence[float],
    composite: Sequence[float] | None,
    output_file: str,
    dpi: int = 300,
) -> str | None:
    """
    Scatter plot of intensity vs focality, optionally colored by composite index.
    """
    if (not intensity) or (not focality):
        return None

    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 5))
    if composite and any(c is not None for c in composite):
        sc = ax.scatter(
            intensity,
            focality,
            c=composite,
            cmap="viridis",
            s=40,
            edgecolor="black",
            alpha=0.7,
        )
        fig.colorbar(sc, ax=ax).set_label("Composite Index", fontsize=12)
    else:
        ax.scatter(intensity, focality, s=40, edgecolor="black", alpha=0.7)

    ax.set_xlabel("TImean_ROI (V/m)", fontsize=12)
    ax.set_ylabel("Focality", fontsize=12)
    ax.set_title("Intensity vs Focality", fontsize=14, fontweight="bold")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return savefig_close(fig, output_file, opts=SaveFigOptions(dpi=dpi))
