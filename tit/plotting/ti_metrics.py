"""
Simple TI-Toolbox metric visualizations (matplotlib).

Centralizes plots that were previously implemented in optimizer/analyzer modules.
"""

from pathlib import Path
from typing import Sequence

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


# ── Electrode-map figures (ported from Larissa Albantakis's branch) ──────────
#
# Both maps draw on a 2-D electrode layout resolved by ``_resolve_layout``:
# known template nets (GSN, 10-10 families) use the bundled head template
# image + pixel coordinates in ``resources/amv``; any other EEG-position CSV
# is drawn as a plain x/y (SimNIBS RAS) scatter.  A montage record is a dict
# with ``electrodes`` (4 or 8 labels, consecutive pairs) and the metrics
# ``composite``, ``timean``, ``focality``.

_AMV_DIR = Path(__file__).resolve().parents[2] / "resources" / "amv"
_TEMPLATE_COORD_FILES = {
    "GSN-HydroCel-185": "GSN-256.csv",
    "GSN-HydroCel-256": "GSN-256.csv",
    "GSN-256": "GSN-256.csv",
    "EEG10-10_UI_Jurak_2007": "10-10.csv",
    "EEG10-10_Cutini_2011": "10-10.csv",
    "EEG10-20_Okamoto_2004": "10-10.csv",
    "EEG10-10_Neuroelectrics": "10-10.csv",
    "10-10": "10-10.csv",
}
_TEMPLATE_IMAGE = "GSN-256.png"
_MONTAGE_KEYS = ("e1_plus", "e1_minus", "e2_plus", "e2_minus")


def _montage_electrodes(item: dict) -> list[str]:
    """Electrode labels of a montage record (``electrodes`` or ``e1_plus``...)."""
    electrodes = item.get("electrodes")
    if electrodes:
        return [str(e) for e in electrodes]
    return [item[key] for key in _MONTAGE_KEYS if key in item]


def _montage_pairs(electrodes: Sequence[str]) -> list[tuple[str, str]]:
    return [(electrodes[i], electrodes[i + 1]) for i in range(0, len(electrodes) - 1, 2)]


def _load_eeg_position_csv(path: str) -> dict[str, tuple[float, ...]]:
    """Read ``label -> (x, y[, z])`` from any supported EEG-position CSV layout."""
    from tit.opt.ex.buckets import _read_eeg_positions

    return _read_eeg_positions(path)


def _load_template_projection(path: str) -> dict | None:
    """Template pixel coordinates + head image for known net names, else None."""
    name = Path(path).name
    coord_file = _TEMPLATE_COORD_FILES.get(name) or _TEMPLATE_COORD_FILES.get(
        Path(name).stem
    )
    if coord_file is None:
        return None
    coord_path = _AMV_DIR / coord_file
    template_path = _AMV_DIR / _TEMPLATE_IMAGE
    if not coord_path.is_file() or not template_path.is_file():
        return None
    positions = {
        label: (xy[0], xy[1]) for label, xy in _load_eeg_position_csv(str(coord_path)).items()
    }
    return {"positions": positions, "template_path": template_path, "eeg_net_name": name}


def _resolve_layout(eeg_positions_csv: str) -> dict:
    """Return ``{"positions", "template_path" (or None), "eeg_net_name"}``."""
    template = _load_template_projection(eeg_positions_csv)
    if template:
        return template
    positions = {
        label: (xyz[0], xyz[1])
        for label, xyz in _load_eeg_position_csv(eeg_positions_csv).items()
    }
    return {
        "positions": positions,
        "template_path": None,
        "eeg_net_name": Path(eeg_positions_csv).name,
    }


def _rank_plottable_montages(
    *,
    montage_scores: Sequence[dict],
    positions: dict,
    metric_key: str,
    top_n: int,
) -> list[dict]:
    plottable = []
    for item in montage_scores:
        electrodes = _montage_electrodes(item)
        if len(electrodes) < 2 or not all(e in positions for e in electrodes):
            continue
        try:
            float(item[metric_key])
        except (KeyError, TypeError, ValueError):
            continue
        plottable.append(item)
    return sorted(plottable, key=lambda item: float(item[metric_key]), reverse=True)[
        :top_n
    ]


def _get_montage_metric_cmap(plt, mpl, cmap_name: str | tuple[str, str]):
    if isinstance(cmap_name, tuple):
        return mpl.colors.LinearSegmentedColormap.from_list(
            "montage_metric_cmap", list(cmap_name)
        )
    return plt.get_cmap(cmap_name)


def _draw_layout_background(ax, layout: dict, mpimg) -> float:
    """Draw the template head image or a grey electrode scatter.

    Returns the label offset (in data units) appropriate for the layout.
    """
    positions = layout["positions"]
    if layout["template_path"] is not None:
        ax.imshow(mpimg.imread(layout["template_path"]), cmap="gray", vmin=0, vmax=1, zorder=0)
        ax.set_axis_off()
        return 18.0
    xs = [xy[0] for xy in positions.values()]
    ys = [xy[1] for xy in positions.values()]
    ax.scatter(xs, ys, s=8, color="#d0d0d0", edgecolors="none", zorder=1)
    ax.set_xlabel("Left / Right (SimNIBS RAS x)")
    ax.set_ylabel("Posterior / Anterior (SimNIBS RAS y)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.15)
    return 2.0


def _draw_pair_curve(ax, start, end, *, color, alpha, linewidth, curve_side, mpl):
    """Draw one electrode pair as a quadratic curve bowed to ``curve_side``."""
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    dist = (dx**2 + dy**2) ** 0.5
    if dist == 0:
        return
    bow = min(dist * 0.22, 55)
    control = (
        (x1 + x2) / 2 + curve_side * (-dy / dist) * bow,
        (y1 + y2) / 2 + curve_side * (dx / dist) * bow,
    )
    path_cls = mpl.path.Path
    path = path_cls(
        [(x1, y1), control, (x2, y2)],
        [path_cls.MOVETO, path_cls.CURVE3, path_cls.CURVE3],
    )
    ax.add_patch(
        mpl.patches.PathPatch(
            path,
            facecolor="none",
            edgecolor=color,
            linewidth=linewidth,
            alpha=alpha,
            capstyle="round",
            joinstyle="round",
            zorder=3,
        )
    )


def plot_montage_score_map(
    *,
    eeg_positions_csv: str,
    montage_scores: Sequence[dict],
    output_file: str,
    top_n: int = 50,
    dpi: int = 300,
    metric_key: str = "composite",
    metric_label: str = "Composite Index (TImean_ROI x Focality)",
    title_metric: str = "Composite Score",
    cmap_name: str | tuple[str, str] = "cividis",
    title_prefix: str = "Ex-Search",
) -> str | None:
    """Draw the top-``top_n`` montages as electrode-pair curves on the EEG layout.

    Every ``montage_scores`` record needs ``electrodes`` (4 or 8 labels as
    consecutive pairs; the legacy ``e1_plus``..``e2_minus`` keys are also
    accepted) and the requested ``metric_key``.  Curves are coloured by the
    metric; the best montage's electrodes are highlighted and labelled.
    """
    layout = _resolve_layout(eeg_positions_csv)
    positions = layout["positions"]
    if not positions or not montage_scores:
        return None
    ranked = _rank_plottable_montages(
        montage_scores=montage_scores,
        positions=positions,
        metric_key=metric_key,
        top_n=top_n,
    )
    if not ranked:
        return None

    ensure_headless_matplotlib_backend()
    import matplotlib as mpl
    import matplotlib.image as mpimg
    import matplotlib.patches  # noqa: F401  (attribute access below)
    import matplotlib.path  # noqa: F401
    import matplotlib.pyplot as plt

    values = [float(item[metric_key]) for item in ranked]
    vmin, vmax = min(values), max(values)
    if vmin == vmax:
        vmax = vmin + 1e-12
    norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
    cmap = _get_montage_metric_cmap(plt, mpl, cmap_name)

    fig, ax = plt.subplots(figsize=(11, 9))
    label_offset = _draw_layout_background(ax, layout, mpimg)

    for rank, item in enumerate(reversed(ranked), 1):
        color = cmap(norm(float(item[metric_key])))
        alpha = 0.18 + 0.62 * rank / len(ranked)
        linewidth = 1.0 + 3.0 * rank / len(ranked)
        for pair_idx, (a, b) in enumerate(_montage_pairs(_montage_electrodes(item))):
            _draw_pair_curve(
                ax,
                positions[a],
                positions[b],
                color=color,
                alpha=alpha,
                linewidth=linewidth,
                curve_side=1 if pair_idx % 2 == 0 else -1,
                mpl=mpl,
            )

    best = ranked[0]
    for label in _montage_electrodes(best):
        x, y = positions[label]
        ax.scatter(
            [x], [y], s=430, facecolors="none", edgecolors="#ffea00", linewidths=4, zorder=5
        )
        ax.text(
            x + label_offset,
            y - label_offset,
            label,
            color="black",
            fontsize=11,
            weight="bold",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1},
            zorder=6,
        )

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.01).set_label(metric_label)
    ax.set_title(
        f"Top {len(ranked)} {title_prefix} Montages by {title_metric} "
        f"({layout['eeg_net_name']})",
        fontsize=16,
        pad=12,
    )
    fig.tight_layout()
    return savefig_close(fig, output_file, opts=SaveFigOptions(dpi=dpi))


def plot_electrode_score_heatmap(
    *,
    eeg_positions_csv: str,
    montage_scores: Sequence[dict],
    output_file: str,
    top_n: int = 50,
    dpi: int = 300,
    title_prefix: str = "Ex-Search",
) -> str | None:
    """Plot electrode participation in the top-``top_n`` montages.

    Each electrode receives the sum of the composite index of the top
    montages it appears in (colour) and its frequency (marker size); the
    12 highest-scoring electrodes are labelled.
    """
    layout = _resolve_layout(eeg_positions_csv)
    positions = layout["positions"]
    if not positions or not montage_scores:
        return None

    ranked = _rank_plottable_montages(
        montage_scores=montage_scores,
        positions=positions,
        metric_key="composite",
        top_n=top_n,
    )
    if not ranked:
        return None

    scores = {label: 0.0 for label in positions}
    counts = {label: 0 for label in positions}
    for item in ranked:
        composite = float(item["composite"])
        for label in _montage_electrodes(item):
            scores[label] += composite
            counts[label] += 1
    active = [label for label, count in counts.items() if count > 0]

    ensure_headless_matplotlib_backend()
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 9))
    label_offset = _draw_layout_background(ax, layout, mpimg)
    if layout["template_path"] is not None:
        inactive = [label for label in positions if label not in active]
        ax.scatter(
            [positions[label][0] for label in inactive],
            [positions[label][1] for label in inactive],
            s=12,
            color="#b0b0b0",
            edgecolors="none",
            zorder=1,
        )

    size_scale = 60 if layout["template_path"] is not None else 22
    sc = ax.scatter(
        [positions[label][0] for label in active],
        [positions[label][1] for label in active],
        c=[scores[label] for label in active],
        s=[60 + size_scale * counts[label] for label in active],
        cmap="inferno",
        edgecolors="black",
        linewidths=0.5,
        zorder=3,
    )
    for label in sorted(active, key=lambda lb: scores[lb], reverse=True)[:12]:
        x, y = positions[label]
        ax.text(
            x + label_offset,
            y - label_offset,
            label,
            fontsize=10,
            weight="bold",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1},
            zorder=4,
        )

    fig.colorbar(sc, ax=ax, fraction=0.035, pad=0.01).set_label(
        "Summed Composite Index Across Top Montages"
    )
    ax.set_title(
        f"{title_prefix} Electrode Contribution (Top {len(ranked)} Montages, "
        f"{layout['eeg_net_name']})",
        fontsize=16,
        pad=12,
    )

    freq = [counts[label] for label in active]
    ax.text(
        0.02,
        0.02,
        "Color = summed composite index; marker size = frequency in the top "
        f"montages ({min(freq)}-{max(freq)} of {len(ranked)}).",
        transform=ax.transAxes,
        fontsize=9,
        color="#444444",
        va="bottom",
    )
    fig.tight_layout()
    return savefig_close(fig, output_file, opts=SaveFigOptions(dpi=dpi))
