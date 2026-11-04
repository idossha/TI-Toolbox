"""The connectome figure of a tract run: a region x region matrix and its strongest edges.

Reads ``connectome_<metric>.npz`` (a square ``matrix`` and its ``labels``; see
:mod:`tit.blender.tract_data`). The matrix is ordered left hemisphere, right hemisphere, then
anything else, with a rule between them; the bar chart lists the ``k`` largest edges. Values
are field descriptors of the applied field on the fibres joining two regions.
"""

from __future__ import annotations

import numpy as np

from tit.blender import tract_data as td


def hemisphere(label: str) -> int:
    """0 left, 1 right, 2 neither, from the common prefixes (``lh.``, ``ctx-lh-``, ``Left-``)."""
    low = label.lower()
    if low.startswith(
        ("lh.", "lh_", "lh-", "ctx-lh-", "ctx_lh_", "left-", "left_", "l_")
    ):
        return 0
    if low.startswith(
        ("rh.", "rh_", "rh-", "ctx-rh-", "ctx_rh_", "right-", "right_", "r_")
    ):
        return 1
    return 2


def hemisphere_order(labels: list[str]) -> np.ndarray:
    """Indices putting left labels first, then right, then the rest, each in input order."""
    return np.array(
        sorted(range(len(labels)), key=lambda i: hemisphere(labels[i])), dtype=int
    )


def top_edges(
    matrix: np.ndarray, labels: list[str], k: int = 15
) -> list[tuple[str, str, float]]:
    """The *k* largest finite, non-zero upper-triangle entries, largest first."""
    i, j = np.triu_indices(len(labels), k=1)
    values = np.asarray(matrix, dtype=np.float64)[i, j]
    ok = np.isfinite(values) & (values != 0)
    order = np.argsort(-values[ok], kind="stable")[:k]
    return [
        (labels[a], labels[b], float(v))
        for a, b, v in zip(i[ok][order], j[ok][order], values[ok][order])
    ]


def metric_units(metric: str) -> str:
    """Units of a connectome metric named in its file: V/m for field values."""
    low = metric.lower()
    if "count" in low or "n_streamlines" in low:
        return "streamlines"
    if "ratio" in low or "fraction" in low or "align" in low:
        return "1"
    if low.startswith(("ti", "e1", "e2", "e_")) or "_par" in low:
        return "V/m"
    return ""


def plot_connectome(
    npz_path: str, png_path: str, *, title: str = "", k: int = 15
) -> str:
    """Write the two-panel connectome figure for *npz_path* to *png_path*."""
    from pathlib import Path

    from tit.plotting._common import (
        ensure_headless_matplotlib_backend,
        savefig_close,
        SaveFigOptions,
    )

    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt

    matrix, labels = td.read_connectome(npz_path)
    metric = Path(npz_path).stem.removeprefix("connectome_")
    units = metric_units(metric)
    unit_text = f" ({units})" if units else ""
    order = hemisphere_order(labels)
    m = matrix[np.ix_(order, order)]
    names = [labels[i] for i in order]
    edges = top_edges(matrix, labels, k)

    fig, (ax_m, ax_b) = plt.subplots(
        1,
        2,
        figsize=(13, 6.2),
        gridspec_kw={"width_ratios": [1.05, 1.0]},
        constrained_layout=True,
    )
    shown = np.ma.masked_where(~np.isfinite(m) | (m == 0), m)
    cmap = plt.get_cmap("plasma").copy()
    cmap.set_bad("#f2f2f2")
    image = ax_m.imshow(shown, cmap=cmap, interpolation="nearest")
    bar = fig.colorbar(image, ax=ax_m, fraction=0.046, pad=0.02)
    bar.set_label(metric + unit_text)
    sides = [hemisphere(n) for n in names]
    for edge in np.flatnonzero(np.diff(sides)) + 0.5:
        ax_m.axhline(edge, color="0.2", lw=0.8)
        ax_m.axvline(edge, color="0.2", lw=0.8)
    if len(names) <= 70:
        ax_m.set_xticks(range(len(names)), names, rotation=90, fontsize=6)
        ax_m.set_yticks(range(len(names)), names, fontsize=6)
    else:  # too many to read: name the hemisphere blocks instead
        blocks = [
            (s, np.flatnonzero(np.asarray(sides) == s)) for s in sorted(set(sides))
        ]
        ticks = [float(ix.mean()) for _s, ix in blocks]
        text = [("left", "right", "other")[s] for s, _ix in blocks]
        ax_m.set_xticks(ticks, text)
        ax_m.set_yticks(ticks, text)
    ax_m.set_title("Region x region, left then right hemisphere", fontsize=11)

    if edges:
        y = np.arange(len(edges))[::-1]
        ax_b.barh(
            y, [e[2] for e in edges], color=plt.get_cmap("plasma")(0.62), height=0.7
        )
        ax_b.set_yticks(y, [f"{a} – {b}" for a, b, _v in edges], fontsize=8)
        ax_b.set_xlabel(metric + unit_text)
        ax_b.spines[["top", "right"]].set_visible(False)
        ax_b.set_title(f"Top {len(edges)} edges", fontsize=11)
    else:
        ax_b.text(
            0.5,
            0.5,
            "No non-zero edges",
            ha="center",
            va="center",
            transform=ax_b.transAxes,
        )
        ax_b.set_axis_off()
    if title:
        fig.suptitle(title, fontsize=12)
    return savefig_close(fig, png_path, opts=SaveFigOptions(dpi=200))
