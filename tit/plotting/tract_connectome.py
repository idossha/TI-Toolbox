"""Figures of a tract run: the connectome, and a bundle-targeting montage ranking.

:func:`plot_connectome` reads ``connectome_<metric>.npz`` (a square ``matrix`` and its
``labels``; see :mod:`tit.blender.tract_data`): the matrix ordered left hemisphere, right
hemisphere, then anything else, and the ``k`` largest edges. :func:`plot_target_ranking` reads a
``tractography/target_<bundle>.json`` ranking and sets the montage with the highest mean TI_max
on the bundle beside the one with the highest mean ti_along. Values are field descriptors of the
applied field on the fibres, not predictions of activation.
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
    matrix: np.ndarray,
    labels: list[str],
    k: int = 15,
    counts: np.ndarray | None = None,
    min_count: int = 1,
) -> list[tuple[str, str, float]]:
    """The *k* largest finite, non-zero upper-triangle entries, largest first.

    With *counts* (the run's streamline-count matrix), edges carried by fewer than
    *min_count* streamlines are left out: a maximum over one or two fibres is not an edge.
    """
    i, j = np.triu_indices(len(labels), k=1)
    values = np.asarray(matrix, dtype=np.float64)[i, j]
    ok = np.isfinite(values) & (values != 0)
    if counts is not None:
        ok &= np.asarray(counts)[i, j] >= min_count
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
    npz_path: str, png_path: str, *, title: str = "", k: int = 15, min_count: int = 10
) -> str:
    """Write the two-panel connectome figure for *npz_path* to *png_path*.

    The top-edge list keeps edges of at least *min_count* streamlines when a
    ``connectome_count.npz`` sits beside *npz_path*, and prints each edge's count.
    """
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
    count_path = Path(npz_path).with_name("connectome_count.npz")
    counts = None
    if count_path.is_file() and count_path != Path(npz_path):
        counts, count_labels = td.read_connectome(str(count_path))
        if count_labels != labels:
            counts = None  # a count matrix of other regions says nothing about these
    edges = top_edges(matrix, labels, k, counts, min_count)
    n_of = {name: i for i, name in enumerate(labels)}

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
    bar = fig.colorbar(image, ax=ax_m, fraction=0.046, pad=0.03)
    bar.set_label(metric + unit_text, labelpad=8)
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
        names_b = [
            f"{a} – {b}"
            + (f"  (n={int(counts[n_of[a], n_of[b]])})" if counts is not None else "")
            for a, b, _v in edges
        ]
        ax_b.set_yticks(y, names_b, fontsize=8)
        ax_b.set_xlabel(metric + unit_text)
        ax_b.spines[["top", "right"]].set_visible(False)
        floor = f" with ≥ {min_count} streamlines" if counts is not None else ""
        ax_b.set_title(f"Top {len(edges)} edges{floor}", fontsize=11)
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


def montage_label(montage: list[str]) -> str:
    """``"T8–C3 + C4–CP5"`` for ``["T8", "C3", "C4", "CP5"]`` (one channel per pair)."""
    pairs = [f"{a}–{b}" for a, b in zip(montage[::2], montage[1::2])]
    return " + ".join(pairs)


def ranking_winners(rows: list[dict]) -> tuple[dict, dict]:
    """``(best by mean ti_max, best by mean ti_along)`` of a ``target_*.json`` ranking."""
    by_max = min(rows, key=lambda r: r["rank_by_ti_max"])
    by_along = min(rows, key=lambda r: r["rank_by_ti_along"])
    return by_max, by_along


def plot_target_ranking(target_json: str, png_path: str, *, title: str = "") -> str:
    """Scatter of every ranked montage plus the two winners side by side, to *png_path*."""
    import json

    from tit.plotting._common import (
        SaveFigOptions,
        ensure_headless_matplotlib_backend,
        savefig_close,
    )

    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt

    with open(target_json, encoding="utf-8") as stream:
        target = json.load(stream)
    rows = target["ranking"]["montages"]
    by_max, by_along = ranking_winners(rows)
    gain = by_along["mean_ti_along"] / by_max["mean_ti_along"] - 1.0
    colours = {"max": "#e8833a", "along": "#2a9d8f"}

    fig, (ax_s, ax_b) = plt.subplots(
        1,
        2,
        figsize=(11.5, 4.6),
        gridspec_kw={"width_ratios": [1.15, 1.0]},
        constrained_layout=True,
    )
    ax_s.scatter(
        [r["mean_ti_max"] for r in rows],
        [r["mean_ti_along"] for r in rows],
        s=9,
        c="0.7",
        lw=0,
    )
    for row, key, text in (
        (by_max, "max", "highest mean TI_max"),
        (by_along, "along", "highest mean ti_along"),
    ):
        ax_s.scatter(
            row["mean_ti_max"],
            row["mean_ti_along"],
            s=70,
            c=colours[key],
            zorder=3,
            ec="k",
            lw=0.6,
        )
        ax_s.annotate(
            f"{montage_label(row['montage'])}\n{text}",
            (row["mean_ti_max"], row["mean_ti_along"]),
            xytext=(8, -4 if key == "max" else 6),
            textcoords="offset points",
            fontsize=8,
            color=colours[key],
        )
    ax_s.set_xlabel("Mean TI_max on the bundle (V/m)")
    ax_s.set_ylabel("Mean TI envelope along the fibres (V/m)")
    ax_s.set_title(f"{len(rows)} montages ranked", fontsize=10)
    ax_s.spines[["top", "right"]].set_visible(False)

    metrics = [("mean_ti_along", "ti_along"), ("mean_ti_max", "TI_max")]
    x = np.arange(len(metrics))
    for i, (row, key) in enumerate(((by_max, "max"), (by_along, "along"))):
        values = [row[m] for m, _ in metrics]
        bars = ax_b.bar(
            x + (i - 0.5) * 0.38,
            values,
            0.36,
            color=colours[key],
            label=montage_label(row["montage"]),
        )
        for bar, value in zip(bars, values):
            ax_b.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.3f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    ax_b.set_xticks(x, [label for _m, label in metrics])
    ax_b.set_ylabel("Mean on the bundle (V/m)")
    ax_b.set_title(
        f"ti_along {gain:+.0%}; alignment {by_max['mean_align']:.2f} vs {by_along['mean_align']:.2f}",
        fontsize=10,
    )
    ax_b.legend(frameon=False, fontsize=8)
    ax_b.spines[["top", "right"]].set_visible(False)
    selection = target.get("selection", {})
    fig.suptitle(
        title
        or f"{selection.get('name', 'bundle')}: {' – '.join(selection.get('regions', []))} "
        f"({target.get('n_streamlines', '?')} streamlines)",
        fontsize=11,
    )
    return savefig_close(fig, png_path, opts=SaveFigOptions(dpi=200))


if (
    __name__ == "__main__"
):  # python -m tit.plotting.tract_connectome <npz|target json> <png>
    import sys

    source, out = sys.argv[1:3]
    draw = plot_target_ranking if source.endswith(".json") else plot_connectome
    print(draw(source, out))
