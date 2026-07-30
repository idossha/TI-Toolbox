#!/usr/bin/env simnibs_python
"""Deep-vs-superficial focality comparison on the SimNIBS ``ernie`` head model.

Runs flex-search four times -- {superficial, deep} target x {ROC ``focality``,
threshold-free ``focality_integral``} -- and records each run's per-evaluation
objective trajectory plus its best value into ``results.json``. Feed that file
to :mod:`make_report` to render the comparison figure and HTML report.

The scientific point: at a **deep** target the ROC objective becomes flat
(both thresholds jointly infeasible -> constant objective -> no gradient for
differential evolution), while integral focality stays smooth and optimizable.
The figure makes this visible as a flat trajectory in the deep/ROC cell only.

Usage
-----
    OUT_DIR=/path/to/out PROJECT_DIR=/path/to/bids \\
        simnibs_python run_comparison.py [--maxiter N] [--popsize N] [--cpus N]

``PROJECT_DIR`` must be a BIDS project whose
``derivatives/SimNIBS/sub-ernie/m2m_ernie`` head model exists. Outputs are
written under ``OUT_DIR`` (never into the source dataset). Budgets are kept
small by default; larger budgets converge better but reach the same conclusion.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

from tit.paths import get_path_manager
from tit.opt import FlexConfig, run_flex_search

# --- Targets (MNI coordinates) --------------------------------------------
# Superficial: left primary motor cortex (hand knob). Deep: left hippocampus,
# evaluated volumetrically so the ROI captures the structure, not overlying
# cortex.
SUPERFICIAL_ROI = dict(x=-37, y=-21, z=58, radius=10.0, use_mni=True)
DEEP_ROI = dict(x=-28, y=-20, z=-16, radius=8.0, use_mni=True, volumetric=True)

# ROC thresholds (V/m): non-ROI max, ROI min. Chosen so a superficial target can
# plausibly reach the ROI threshold while a deep target cannot -> flat ROC.
ROC_THRESHOLDS = "0.1,0.2"

# Match only *evaluated* candidates -- those with an "(n_sim: N" suffix. Bare
# "Goal (...): 2.0" lines are SimNIBS's overlap penalty for electrode positions
# that were rejected before any FEM solve, so they are not real objective values.
_GOAL_RE = re.compile(
    r"Goal \(.*?\):\s*([-+]?[\d.]+(?:[eE][-+]?\d+)?)\s*\(n_sim:"
)


def _parse_trajectory(log_path: Path) -> list[float]:
    """Extract the per-evaluation objective values from a flex-search log."""
    if not log_path.is_file():
        return []
    values: list[float] = []
    for line in log_path.read_text(errors="ignore").splitlines():
        m = _GOAL_RE.search(line)
        if m:
            try:
                values.append(float(m.group(1)))
            except ValueError:
                continue
    return values


def _newest_log(logs_dir: Path) -> Path | None:
    logs = sorted(logs_dir.glob("flex_search_*.log"))
    return logs[-1] if logs else None


def _run_one(subject, roi_kwargs, goal, out_dir, thresholds, budget) -> dict:
    """Run a single flex config and return its summary dict."""
    pm = get_path_manager()
    cfg = FlexConfig(
        subject_id=subject,
        goal=goal,
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(**roi_kwargs),
        non_roi_method="everything_else",
        thresholds=thresholds if goal == "focality" else None,
        output_folder=str(out_dir),
        max_iterations=budget["maxiter"],
        population_size=budget["popsize"],
        n_multistart=1,
        cpus=budget["cpus"],
    )
    t0 = time.time()
    result = run_flex_search(cfg)
    elapsed = time.time() - t0

    log = _newest_log(Path(pm.logs(subject)))
    trajectory = _parse_trajectory(log) if log else []
    return {
        "goal": goal,
        "roi": roi_kwargs,
        "success": bool(result.success),
        "best_value": None if result.best_value in (None, float("inf")) else float(result.best_value),
        "trajectory": trajectory,
        "n_evaluations": len(trajectory),
        "elapsed_sec": round(elapsed, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maxiter", type=int, default=3)
    parser.add_argument("--popsize", type=int, default=4)
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--subject", default="ernie")
    args = parser.parse_args()

    project_dir = os.environ.get("PROJECT_DIR", "/Users/idohaber/datasets/000")
    out_root = Path(os.environ.get("OUT_DIR", "./focality_integral_ernie_out"))
    out_root.mkdir(parents=True, exist_ok=True)

    get_path_manager(project_dir)
    budget = {"maxiter": args.maxiter, "popsize": args.popsize, "cpus": args.cpus}

    matrix = [
        ("superficial", SUPERFICIAL_ROI, "focality"),
        ("superficial", SUPERFICIAL_ROI, "focality_integral"),
        ("deep", DEEP_ROI, "focality"),
        ("deep", DEEP_ROI, "focality_integral"),
    ]

    results = {"subject": args.subject, "budget": budget, "cells": []}
    results_path = out_root / "results.json"
    for depth, roi, goal in matrix:
        print(f"\n=== {depth} x {goal} ===", flush=True)
        out_dir = out_root / f"{depth}_{goal}"
        try:
            cell = _run_one(args.subject, roi, goal, out_dir, ROC_THRESHOLDS, budget)
        except Exception as exc:  # keep partial results on failure
            cell = {"goal": goal, "roi": roi, "success": False, "error": repr(exc),
                    "trajectory": [], "n_evaluations": 0, "elapsed_sec": None}
            print(f"  FAILED: {exc!r}", flush=True)
        cell["depth"] = depth
        results["cells"].append(cell)
        spread = (max(cell["trajectory"]) - min(cell["trajectory"])) if cell["trajectory"] else 0.0
        print(f"  evals={cell['n_evaluations']} best={cell.get('best_value')} "
              f"spread={spread:.4g} elapsed={cell.get('elapsed_sec')}s", flush=True)
        # Persist after every cell so partial runs are never lost.
        results_path.write_text(json.dumps(results, indent=2))

    print(f"\nWrote {results_path}")


if __name__ == "__main__":
    main()
