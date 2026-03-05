"""Multi-subject group analysis.

Runs per-subject ROI analyses in-process via :class:`Analyzer`, aggregates the
results into a summary CSV with an AVERAGE row, and produces a 2x2 comparison
bar-chart saved as PDF.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from tit.analyzer.analyzer import Analyzer, AnalysisResult
from tit.logger import add_file_handler
from tit.paths import get_path_manager

logger = logging.getLogger(__name__)

_NUMERIC_COLS = [
    "ROI_Mean",
    "ROI_Max",
    "ROI_Min",
    "ROI_Focality",
    "GM_Mean",
    "GM_Max",
    "Normal_Mean",
    "Normal_Max",
    "Normal_Focality",
]


@dataclass
class GroupResult:
    """Outcome of a multi-subject group analysis."""

    subject_results: dict[str, AnalysisResult]
    summary_csv_path: Path
    comparison_plot_path: Path | None


def run_group_analysis(
    subject_ids: list[str],
    simulation: str,
    space: str = "mesh",
    analysis_type: str = "spherical",
    center: tuple[float, float, float] | None = None,
    radius: float | None = None,
    coordinate_space: str = "subject",
    atlas: str | None = None,
    region: str | None = None,
    visualize: bool = False,
    output_dir: str | Path | None = None,
) -> GroupResult:
    """Run the same ROI analysis across *subject_ids* and summarise.

    Dispatches to ``analyze_sphere`` or ``analyze_cortex`` on each subject,
    builds a summary CSV (with an AVERAGE row), and generates a 2x2
    comparison bar-chart PDF.  Returns a :class:`GroupResult`.
    """
    out = _resolve_output_dir(output_dir)

    # File handler so group analysis logs are persisted
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = out / f"group_analysis_{timestamp}.log"
    add_file_handler(log_file)

    logger.info(
        "Group analysis started: %d subjects, space=%s, type=%s",
        len(subject_ids),
        space,
        analysis_type,
    )

    dispatch: dict[str, callable] = {
        "spherical": lambda a: a.analyze_sphere(
            center=center,
            radius=radius,
            coordinate_space=coordinate_space,
            visualize=visualize,
        ),
        "cortical": lambda a: a.analyze_cortex(
            atlas=atlas,
            region=region,
            visualize=visualize,
        ),
    }
    analyze_fn = dispatch[analysis_type]

    results: dict[str, AnalysisResult] = {}
    for sid in subject_ids:
        logger.info("Analyzing subject %s", sid)
        results[sid] = analyze_fn(Analyzer(sid, simulation, space))

    df = _build_summary_df(results)
    csv_path = out / "group_summary.csv"
    df.to_csv(csv_path, index=False, float_format="%.3f")
    logger.info("Summary CSV written to %s", csv_path)

    plot_path = _generate_comparison_plot(df, out)
    logger.info("Comparison plot written to %s", plot_path)

    return GroupResult(
        subject_results=results,
        summary_csv_path=csv_path,
        comparison_plot_path=plot_path,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_output_dir(output_dir: str | Path | None) -> Path:
    """Return (and create) the output directory."""
    pm = get_path_manager()
    path = Path(output_dir) if output_dir else Path(pm.logs_group())
    return Path(pm.ensure(str(path)))


def _build_summary_df(results: dict[str, AnalysisResult]) -> pd.DataFrame:
    """One row per subject plus an AVERAGE row at the bottom."""
    rows = [
        {
            "Subject": sid,
            "ROI_Mean": r.roi_mean,
            "ROI_Max": r.roi_max,
            "ROI_Min": r.roi_min,
            "ROI_Focality": r.roi_focality,
            "GM_Mean": r.gm_mean,
            "GM_Max": r.gm_max,
            "Normal_Mean": r.normal_mean or 0.0,
            "Normal_Max": r.normal_max or 0.0,
            "Normal_Focality": r.normal_focality or 0.0,
        }
        for sid, r in results.items()
    ]
    df = pd.DataFrame(rows)
    avg = {"Subject": "AVERAGE", **df[_NUMERIC_COLS].mean().to_dict()}
    return pd.concat([df, pd.DataFrame([avg])], ignore_index=True)


def _generate_comparison_plot(df: pd.DataFrame, output_dir: Path) -> Path:
    """2x2 bar chart: Mean, Max, Focality, Normal_Mean per subject."""
    subject_df = df[df["Subject"] != "AVERAGE"]
    metrics = ["ROI_Mean", "ROI_Max", "ROI_Focality", "Normal_Mean"]
    labels = ["Mean (V/m)", "Max (V/m)", "Focality", "Normal Mean (V/m)"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("Group Field Value Comparison", fontsize=16, fontweight="bold")
    subjects = subject_df["Subject"].tolist()
    x_pos = np.arange(len(subjects))

    for ax, metric, label, color in zip(axes.flat, metrics, labels, colors):
        values = subject_df[metric].values.astype(float)
        mean_val = float(np.mean(values))
        std_val = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0

        bars = ax.bar(x_pos, values, color=color, alpha=0.7)
        for bar, val in zip(bars, values):
            bar.set_alpha(0.8 if val >= mean_val else 0.4)

        ax.axhline(
            y=mean_val,
            color="black",
            linestyle="-",
            linewidth=2,
            alpha=0.8,
            label=f"Mean ({mean_val:.3f})",
        )
        _add_std_lines(ax, mean_val, std_val)
        ax.set_title(f"ROI {label}", fontweight="bold")
        ax.set_ylabel(label)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(subjects, ha="right", rotation=45)
        ax.grid(True, alpha=0.3)

    fig.legend(
        handles=[
            Line2D(
                [0], [0], color="black", linestyle="-", linewidth=2, label="Group Mean"
            ),
            Line2D([0], [0], color="gray", linestyle="--", label="\u00b11 Std Dev"),
            Line2D([0], [0], color="red", linestyle="--", label="\u00b12 Std Dev"),
        ],
        loc="upper right",
        bbox_to_anchor=(0.98, 0.95),
    )
    plt.tight_layout()
    plt.subplots_adjust(top=0.93)

    plot_path = output_dir / "group_comparison.pdf"
    plt.savefig(plot_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return plot_path


def _add_std_lines(ax, mean_val: float, std_val: float) -> None:
    """Draw +/-1 sigma and +/-2 sigma reference lines."""
    if std_val <= 0:
        return
    for mult, color in [(1, "gray"), (2, "red")]:
        ax.axhline(
            y=mean_val + mult * std_val,
            color=color,
            linestyle="--",
            linewidth=1,
            alpha=0.6,
        )
        ax.axhline(
            y=mean_val - mult * std_val,
            color=color,
            linestyle="--",
            linewidth=1,
            alpha=0.6,
        )
