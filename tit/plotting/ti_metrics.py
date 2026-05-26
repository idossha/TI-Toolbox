"""Simple TI-Toolbox metric visualizations (matplotlib)."""

import csv
from pathlib import Path
from typing import Sequence

from ._common import SaveFigOptions, ensure_headless_matplotlib_backend, savefig_close

_AMV_DIR = Path(__file__).resolve().parents[2] / "resources" / "amv"
_TEMPLATE_COORD_FILES = {
    "GSN-HydroCel-185.csv": "GSN-256.csv",
    "GSN-HydroCel-256.csv": "GSN-256.csv",
    "GSN-HydroCel-185": "GSN-256.csv",
    "GSN-HydroCel-256": "GSN-256.csv",
    "EEG10-10_UI_Jurak_2007.csv": "10-10.csv",
    "EEG10-10_Cutini_2011.csv": "10-10.csv",
    "EEG10-20_Okamoto_2004.csv": "10-10.csv",
    "EEG10-10_Neuroelectrics.csv": "10-10.csv",
}


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
) -> str | None:
    """Plot top montage electrode-pair lines on a 2D EEG-net projection.

    ``montage_scores`` entries must contain ``e1_plus``, ``e1_minus``,
    ``e2_plus``, ``e2_minus``, and the requested ``metric_key``.
    """
    template = _load_template_projection(eeg_positions_csv)
    if template:
        return _plot_template_montage_score_map(
            template_path=template["template_path"],
            positions=template["positions"],
            eeg_net_name=template["eeg_net_name"],
            montage_scores=montage_scores,
            output_file=output_file,
            top_n=top_n,
            dpi=dpi,
            metric_key=metric_key,
            metric_label=metric_label,
            title_metric=title_metric,
            cmap_name=cmap_name,
        )

    positions = _load_eeg_position_csv(eeg_positions_csv)
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
    import matplotlib.pyplot as plt

    xs = [xyz[0] for xyz in positions.values()]
    ys = [xyz[1] for xyz in positions.values()]
    values = [float(item[metric_key]) for item in ranked]
    vmin, vmax = min(values), max(values)
    if vmin == vmax:
        vmax = vmin + 1e-12
    norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
    cmap = _get_montage_metric_cmap(plt, mpl, cmap_name)

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(xs, ys, s=8, color="#d0d0d0", edgecolors="none", zorder=1)

    for rank, item in enumerate(reversed(ranked), 1):
        color = cmap(norm(float(item[metric_key])))
        alpha = 0.25 + 0.65 * rank / len(ranked)
        linewidth = 0.8 + 2.2 * rank / len(ranked)
        _draw_pair_line(
            ax,
            positions[item["e1_plus"]],
            positions[item["e1_minus"]],
            color=color,
            alpha=alpha,
            linewidth=linewidth,
        )
        _draw_pair_line(
            ax,
            positions[item["e2_plus"]],
            positions[item["e2_minus"]],
            color=color,
            alpha=alpha,
            linewidth=linewidth,
        )

    best = ranked[0]
    for key in ("e1_plus", "e1_minus", "e2_plus", "e2_minus"):
        label = best[key]
        x, y, _z = positions[label]
        ax.scatter([x], [y], s=80, color="#ffea00", edgecolors="black", zorder=4)
        ax.text(x, y, f" {label}", fontsize=8, weight="bold", zorder=5)

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.045, pad=0.03)
    cbar.set_label(metric_label)

    ax.set_title(f"Top {len(ranked)} Ex-Search Montages by {title_metric}")
    ax.set_xlabel("Left / Right (SimNIBS RAS x)")
    ax.set_ylabel("Posterior / Anterior (SimNIBS RAS y)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.15)
    ax.text(
        0.02,
        0.02,
        f"EEG net: {Path(eeg_positions_csv).name}\n"
        "Each montage contributes two electrode-pair lines.",
        transform=ax.transAxes,
        fontsize=8,
        color="#444444",
        va="bottom",
    )
    fig.tight_layout()
    return savefig_close(fig, output_file, opts=SaveFigOptions(dpi=dpi))


def _plot_template_montage_score_map(
    *,
    template_path: Path,
    positions: dict[str, tuple[float, float]],
    eeg_net_name: str,
    montage_scores: Sequence[dict],
    output_file: str,
    top_n: int,
    dpi: int,
    metric_key: str,
    metric_label: str,
    title_metric: str,
    cmap_name: str | tuple[str, str],
) -> str | None:
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
    import matplotlib.pyplot as plt
    from matplotlib.path import Path as MplPath
    from matplotlib.patches import PathPatch

    image = mpimg.imread(template_path)
    values = [float(item[metric_key]) for item in ranked]
    vmin, vmax = min(values), max(values)
    if vmin == vmax:
        vmax = vmin + 1e-12
    norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
    cmap = _get_montage_metric_cmap(plt, mpl, cmap_name)

    fig, ax = plt.subplots(figsize=(11, 9))
    ax.imshow(image, cmap="gray", vmin=0, vmax=1, zorder=0)
    ax.set_axis_off()

    for rank, item in enumerate(reversed(ranked), 1):
        color = cmap(norm(float(item[metric_key])))
        alpha = 0.18 + 0.62 * rank / len(ranked)
        linewidth = 1.0 + 3.0 * rank / len(ranked)
        _draw_template_pair_curve(
            ax,
            positions[item["e1_plus"]],
            positions[item["e1_minus"]],
            color=color,
            alpha=alpha,
            linewidth=linewidth,
            path_cls=MplPath,
            patch_cls=PathPatch,
            curve_side=1,
        )
        _draw_template_pair_curve(
            ax,
            positions[item["e2_plus"]],
            positions[item["e2_minus"]],
            color=color,
            alpha=alpha,
            linewidth=linewidth,
            path_cls=MplPath,
            patch_cls=PathPatch,
            curve_side=-1,
        )

    best = ranked[0]
    for key in ("e1_plus", "e1_minus", "e2_plus", "e2_minus"):
        label = best[key]
        x, y = positions[label]
        ax.scatter(
            [x],
            [y],
            s=430,
            facecolors="none",
            edgecolors="#ffea00",
            linewidths=4,
            zorder=5,
        )
        ax.text(
            x + 18,
            y - 16,
            label,
            color="black",
            fontsize=11,
            weight="bold",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1},
            zorder=6,
        )

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.01)
    cbar.set_label(metric_label)
    ax.set_title(
        f"Top {len(ranked)} Ex-Search Montages by {title_metric} ({eeg_net_name})",
        fontsize=16,
        pad=12,
    )
    fig.tight_layout()
    return savefig_close(fig, output_file, opts=SaveFigOptions(dpi=dpi))


def _rank_plottable_montages(
    *,
    montage_scores: Sequence[dict],
    positions: dict,
    metric_key: str,
    top_n: int,
) -> list[dict]:
    plottable = []
    for item in montage_scores:
        if not all(
            item.get(key) in positions
            for key in ("e1_plus", "e1_minus", "e2_plus", "e2_minus")
        ):
            continue
        try:
            float(item[metric_key])
        except (KeyError, TypeError, ValueError):
            continue
        plottable.append(item)
    return sorted(
        plottable,
        key=lambda item: float(item[metric_key]),
        reverse=True,
    )[:top_n]


def _get_montage_metric_cmap(plt, mpl, cmap_name: str | tuple[str, str]):
    if isinstance(cmap_name, tuple):
        return mpl.colors.LinearSegmentedColormap.from_list(
            "montage_metric_cmap",
            list(cmap_name),
        )
    return plt.get_cmap(cmap_name)


def _draw_template_pair_curve(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    color,
    alpha: float,
    linewidth: float,
    path_cls,
    patch_cls,
    curve_side: int,
) -> None:
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    dist = (dx**2 + dy**2) ** 0.5
    if dist == 0:
        return
    control = (
        (x1 + x2) / 2 + curve_side * (-dy / dist) * min(dist * 0.22, 55),
        (y1 + y2) / 2 + curve_side * (dx / dist) * min(dist * 0.22, 55),
    )
    path = path_cls(
        [(x1, y1), control, (x2, y2)],
        [path_cls.MOVETO, path_cls.CURVE3, path_cls.CURVE3],
    )
    patch = patch_cls(
        path,
        facecolor="none",
        edgecolor=color,
        linewidth=linewidth,
        alpha=alpha,
        capstyle="round",
        joinstyle="round",
        zorder=3,
    )
    ax.add_patch(patch)


def plot_electrode_score_heatmap(
    *,
    eeg_positions_csv: str,
    montage_scores: Sequence[dict],
    output_file: str,
    top_n: int = 50,
    dpi: int = 300,
) -> str | None:
    """Plot electrode participation in the top-scoring montages.

    Each electrode receives the sum of composite scores from the top ``N``
    montages in which it appears. This emphasizes electrodes that are both
    frequent and part of high-scoring montages.
    """
    positions = _load_eeg_position_csv(eeg_positions_csv)
    if not positions or not montage_scores:
        return None

    ranked = sorted(
        montage_scores,
        key=lambda item: float(item.get("composite", 0.0)),
        reverse=True,
    )[:top_n]
    scores = {label: 0.0 for label in positions}
    counts = {label: 0 for label in positions}
    for item in ranked:
        composite = float(item.get("composite", 0.0))
        for key in ("e1_plus", "e1_minus", "e2_plus", "e2_minus"):
            label = item.get(key)
            if label in scores:
                scores[label] += composite
                counts[label] += 1

    active = [label for label, count in counts.items() if count > 0]
    if not active:
        return None

    ensure_headless_matplotlib_backend()
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 8))
    inactive = [label for label in positions if label not in active]
    ax.scatter(
        [positions[label][0] for label in inactive],
        [positions[label][1] for label in inactive],
        s=8,
        color="#d0d0d0",
        edgecolors="none",
        zorder=1,
    )

    active_values = [scores[label] for label in active]
    sizes = [40 + 22 * counts[label] for label in active]
    sc = ax.scatter(
        [positions[label][0] for label in active],
        [positions[label][1] for label in active],
        c=active_values,
        s=sizes,
        cmap="inferno",
        edgecolors="black",
        linewidths=0.5,
        zorder=3,
    )

    top_labels = sorted(active, key=lambda label: scores[label], reverse=True)[:12]
    for label in top_labels:
        x, y, _z = positions[label]
        ax.text(x, y, f" {label}", fontsize=8, weight="bold", zorder=4)

    cbar = fig.colorbar(sc, ax=ax, fraction=0.045, pad=0.03)
    cbar.set_label("Summed Composite Index Across Top Montages")

    ax.set_title(f"Electrode Contribution Heatmap (Top {len(ranked)} Montages)")
    ax.set_xlabel("Left / Right (SimNIBS RAS x)")
    ax.set_ylabel("Posterior / Anterior (SimNIBS RAS y)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.15)

    legend_counts = sorted({counts[label] for label in active})
    legend_counts = [legend_counts[0], legend_counts[-1]] if len(legend_counts) > 1 else legend_counts
    handles = [
        ax.scatter(
            [],
            [],
            s=40 + 22 * count,
            color="#777777",
            edgecolors="black",
            linewidths=0.5,
            label=f"{count} montage(s)",
        )
        for count in legend_counts
    ]
    if handles:
        ax.legend(handles=handles, title="Frequency", loc="upper left")

    ax.text(
        0.02,
        0.02,
        f"EEG net: {Path(eeg_positions_csv).name}\n"
        "Color = summed composite score; size = frequency in top montages.",
        transform=ax.transAxes,
        fontsize=8,
        color="#444444",
        va="bottom",
    )
    fig.tight_layout()
    return savefig_close(fig, output_file, opts=SaveFigOptions(dpi=dpi))


def _load_eeg_position_csv(path: str) -> dict[str, tuple[float, float, float]]:
    positions = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 5 or row[0].strip().lower() != "electrode":
                continue
            try:
                positions[row[4].strip()] = (
                    float(row[1]),
                    float(row[2]),
                    float(row[3]),
                )
            except ValueError:
                continue
    return positions


def _load_template_projection(path: str) -> dict | None:
    eeg_net_name = Path(path).name
    coord_file = _TEMPLATE_COORD_FILES.get(eeg_net_name)
    if coord_file is None:
        coord_file = _TEMPLATE_COORD_FILES.get(Path(eeg_net_name).stem)
    if coord_file is None:
        return None

    coord_path = _AMV_DIR / coord_file
    template_path = _AMV_DIR / "GSN-256.png"
    if not coord_path.is_file() or not template_path.is_file():
        return None

    positions: dict[str, tuple[float, float]] = {}
    with open(coord_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 3 or row[0].strip().lower() == "electrode_name":
                continue
            try:
                positions[row[0].strip()] = (float(row[1]), float(row[2]))
            except ValueError:
                continue

    return {
        "positions": positions,
        "template_path": template_path,
        "eeg_net_name": eeg_net_name,
    }


def _draw_pair_line(ax, start, end, *, color, alpha: float, linewidth: float) -> None:
    x1, y1, _z1 = start
    x2, y2, _z2 = end
    ax.plot(
        [x1, x2],
        [y1, y2],
        color=color,
        alpha=alpha,
        linewidth=linewidth,
        solid_capstyle="round",
        zorder=2,
    )
