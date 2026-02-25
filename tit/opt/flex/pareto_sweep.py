"""Pareto sweep module for focality threshold grid optimization.

This module provides the data structures and functions needed to run a
Cartesian-product sweep over (ROI%, non-ROI%) threshold combinations for
TI stimulation focality optimization. After all combinations are run, the
results are saved as JSON, a PNG scatter plot, and an ASCII summary table.

All thresholds are expressed as percentages of ``achievable_ROI_mean`` —
the mean field in the target ROI at the mean-optimal electrode configuration
obtained in step 1 of the adaptive workflow.
"""

from __future__ import annotations

import json
import os
import re
from collections import deque
from dataclasses import dataclass, field
from itertools import product
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SweepPoint:
    """One (roi_pct, nonroi_pct) combination in the sweep grid.

    Attributes:
        roi_pct: ROI threshold expressed as a percentage (e.g. 80.0).
        nonroi_pct: Non-ROI threshold expressed as a percentage (e.g. 20.0).
        roi_threshold: Absolute ROI threshold in V/m
            (= roi_pct / 100 * achievable_ROI_mean).
        nonroi_threshold: Absolute non-ROI threshold in V/m.
        run_index: 0-based index; determines the subfolder name.
        output_folder: Absolute path to this run's output directory.
        focality_score: optim_funvalue returned by SimNIBS (negative float;
            values closer to 0 are better focality).  ``None`` until the run
            completes successfully.
        status: One of ``"pending"``, ``"running"``, ``"done"``, ``"failed"``.
    """

    roi_pct: float
    nonroi_pct: float
    roi_threshold: float
    nonroi_threshold: float
    run_index: int
    output_folder: str
    focality_score: Optional[float] = None
    status: str = "pending"


@dataclass
class ParetoSweepConfig:
    """Configuration for a full Pareto threshold sweep.

    Attributes:
        roi_pcts: List of ROI% values to sweep (e.g. [80.0, 70.0]).
        nonroi_pcts: List of non-ROI% values to sweep (e.g. [20.0, 30.0, 40.0]).
        achievable_roi_mean: Mean field strength in V/m from step-1 mean opt.
        base_output_folder: Parent directory for all sweep run subdirectories.
    """

    roi_pcts: list
    nonroi_pcts: list
    achievable_roi_mean: float
    base_output_folder: str


@dataclass
class ParetoSweepResult:
    """Result container for a completed (or in-progress) Pareto sweep.

    Attributes:
        config: The configuration used for this sweep.
        points: Ordered list of :class:`SweepPoint` objects (one per combo).
    """

    config: ParetoSweepConfig
    points: list


# ---------------------------------------------------------------------------
# Grid computation
# ---------------------------------------------------------------------------


def compute_sweep_grid(
    roi_pcts: list,
    nonroi_pcts: list,
    achievable_roi_mean: float,
    base_output_folder: str,
) -> list:
    """Return the Cartesian product of (roi_pct, nonroi_pct) as SweepPoints.

    Ordering: ``roi_pcts`` outer loop, ``nonroi_pcts`` inner loop.

    Invalid combinations (``nonroi_pct >= roi_pct``) are *included* here;
    call :func:`validate_grid` before starting any runs to reject them early.

    Args:
        roi_pcts: Sequence of ROI threshold percentages.
        nonroi_pcts: Sequence of non-ROI threshold percentages.
        achievable_roi_mean: Mean field strength (V/m) from step-1 mean opt.
        base_output_folder: Parent directory; each point gets a numbered
            subdirectory named ``{idx+1:02d}_roi{roi_pct}_nonroi{nonroi_pct}``.

    Returns:
        List of :class:`SweepPoint` objects, one per combination.
    """
    points = []
    for idx, (roi_pct, nonroi_pct) in enumerate(product(roi_pcts, nonroi_pcts)):
        roi_thr = (roi_pct / 100.0) * achievable_roi_mean
        nonroi_thr = (nonroi_pct / 100.0) * achievable_roi_mean
        folder_name = f"{idx + 1:02d}_roi{int(roi_pct)}_nonroi{int(nonroi_pct)}"
        points.append(
            SweepPoint(
                roi_pct=float(roi_pct),
                nonroi_pct=float(nonroi_pct),
                roi_threshold=roi_thr,
                nonroi_threshold=nonroi_thr,
                run_index=idx,
                output_folder=os.path.join(base_output_folder, folder_name),
            )
        )
    return points


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_grid(roi_pcts: list, nonroi_pcts: list) -> None:
    """Raise ``ValueError`` if any combination has ``nonroi_pct >= roi_pct``.

    Rejects the *entire* grid rather than silently skipping bad rows, so the
    user is aware of all problematic combinations before any subprocess starts.

    Args:
        roi_pcts: Sequence of ROI threshold percentages.
        nonroi_pcts: Sequence of non-ROI threshold percentages.

    Raises:
        ValueError: Lists all invalid (roi_pct, nonroi_pct) pairs.
    """
    bad = [(r, n) for r, n in product(roi_pcts, nonroi_pcts) if n >= r]
    if bad:
        raise ValueError(
            "Non-ROI % must be strictly less than ROI % for all combinations. "
            f"Invalid pairs: {bad}"
        )


# ---------------------------------------------------------------------------
# Command building
# ---------------------------------------------------------------------------


def build_focality_cmd(base_cmd: list, point: SweepPoint) -> list:
    """Append focality goal and threshold args to ``base_cmd`` for one point.

    Does **not** mutate ``base_cmd``; returns a new list.

    The SimNIBS ``--thresholds`` format is ``nonroi_threshold,roi_threshold``
    (non-ROI first).

    Args:
        base_cmd: Existing command list (subject, postproc, electrodes, etc.).
        point: The sweep point whose thresholds should be used.

    Returns:
        New list with ``--goal focality --thresholds <nonroi>,<roi>`` appended.
    """
    thresholds_str = f"{point.nonroi_threshold:.4f},{point.roi_threshold:.4f}"
    return base_cmd + [
        "--goal",
        "focality",
        "--thresholds",
        thresholds_str,
    ]


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------


def parse_sweep_line(line: str, postproc_key: str) -> Optional[float]:
    """Extract the optim_funvalue from a SimNIBS log line.

    Targets the pattern::

        Final goal function value:   -42.123

    as the primary match.  Falls back to::

        Goal function value.*:  -42.123

    Args:
        line: A single line of SimNIBS stdout/stderr.
        postproc_key: Post-processing field key (e.g. ``"max_TI"``).  Not used
            in the regex but kept for API symmetry with the broader flex log
            infrastructure.

    Returns:
        The function value as a float, or ``None`` if the line does not match.
    """
    # Primary pattern
    m = re.search(
        r"Final goal function value:\s*([+-]?[\d.eE+-]+)", line, re.IGNORECASE
    )
    if m:
        return float(m.group(1))
    # Fallback pattern
    m = re.search(r"Goal function value[^:]*:\s*([+-]?[\d.eE+-]+)", line, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------


def generate_pareto_plot(result: ParetoSweepResult, output_path: str) -> None:
    """Save a Pareto trade-off scatter plot as a PNG.

    - x-axis: non-ROI threshold as % of achievable ROI mean
    - y-axis: focality score (optim_funvalue; higher/closer to 0 = better)
    - One line/series per unique ROI% value, coloured by series
    - Each point labelled with ``(roi%, nonroi%)``
    - Points with ``status != "done"`` are skipped

    Args:
        result: The sweep result containing all :class:`SweepPoint` objects.
        output_path: Absolute path where the PNG should be written.
    """
    fig, ax = plt.subplots(figsize=(8, 5))
    roi_pcts_unique = sorted(set(p.roi_pct for p in result.points))
    colors = plt.cm.tab10.colors  # type: ignore[attr-defined]

    for ci, rp in enumerate(roi_pcts_unique):
        pts = [p for p in result.points if p.roi_pct == rp and p.status == "done"]
        if not pts:
            continue
        xs = [p.nonroi_pct for p in pts]
        ys = [p.focality_score for p in pts]
        ax.plot(
            xs,
            ys,
            marker="o",
            color=colors[ci % len(colors)],
            label=f"ROI {int(rp)}%",
            linewidth=1.5,
        )
        for p in pts:
            ax.annotate(
                f"({int(p.roi_pct)}%,{int(p.nonroi_pct)}%)",
                xy=(p.nonroi_pct, p.focality_score),
                fontsize=7,
                ha="left",
                va="bottom",
            )

    ax.set_xlabel("Non-ROI threshold (% of achievable ROI mean)")
    ax.set_ylabel("Focality score (higher = better)")
    ax.set_title("Focality\u2013Threshold Trade-off Sweep")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def generate_summary_text(result: ParetoSweepResult) -> str:
    """Return a formatted ASCII table summarising all sweep points.

    Columns: ROI% | NonROI% | ROI thr (V/m) | NR thr (V/m) | Score | Status

    Args:
        result: The sweep result to summarise.

    Returns:
        Multi-line string ready to write to a text file or print.
    """
    header = (
        f"{'ROI%':>6} {'NonROI%':>8} {'ROI thr(V/m)':>14} "
        f"{'NR thr(V/m)':>12} {'Score':>10} {'Status'}"
    )
    sep = "=" * len(header)
    lines = [sep, header, sep]
    for p in result.points:
        score_str = (
            f"{p.focality_score:.3f}" if p.focality_score is not None else "\u2014"
        )
        lines.append(
            f"{p.roi_pct:>6.0f} {p.nonroi_pct:>8.0f} "
            f"{p.roi_threshold:>14.4f} {p.nonroi_threshold:>12.4f} "
            f"{score_str:>10} {p.status}"
        )
    lines.append(sep)
    return "\n".join(lines)


def save_results(result: ParetoSweepResult, output_folder: str) -> tuple:
    """Persist the sweep results to disk.

    Writes three artefacts:

    * ``pareto_results.json`` — structured data for all sweep points
    * ``pareto_sweep_plot.png`` — matplotlib scatter plot
    * ``pareto_summary.txt`` — ASCII table

    Args:
        result: The completed (or partially completed) sweep result.
        output_folder: Directory where artefacts are written (created if
            necessary).

    Returns:
        ``(json_path, plot_path, txt_path)`` — absolute paths to the three
        written files.
    """
    os.makedirs(output_folder, exist_ok=True)

    json_path = os.path.join(output_folder, "pareto_results.json")
    plot_path = os.path.join(output_folder, "pareto_sweep_plot.png")
    txt_path = os.path.join(output_folder, "pareto_summary.txt")

    data = {
        "achievable_roi_mean_vm": result.config.achievable_roi_mean,
        "roi_pcts": result.config.roi_pcts,
        "nonroi_pcts": result.config.nonroi_pcts,
        "points": [
            {
                "roi_pct": p.roi_pct,
                "nonroi_pct": p.nonroi_pct,
                "roi_threshold_vm": p.roi_threshold,
                "nonroi_threshold_vm": p.nonroi_threshold,
                "focality_score": p.focality_score,
                "status": p.status,
                "output_folder": p.output_folder,
            }
            for p in result.points
        ],
    }
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    generate_pareto_plot(result, plot_path)

    with open(txt_path, "w") as f:
        f.write(generate_summary_text(result))

    return json_path, plot_path, txt_path
