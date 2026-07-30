#!/usr/bin/env simnibs_python
"""Deep-vs-superficial focality comparison on the SimNIBS ``ernie`` head model.

Runs flex-search for {superficial, deep} target x {ROC ``focality``, threshold-
free ``focality_integral``} and captures, for each run: the objective trajectory,
the best-montage ROI / non-ROI E-field arrays, the optimized electrode positions,
and the final-simulation TI-field mesh. :mod:`make_report` turns the resulting
``results.json`` (+ ``*.npz`` arrays) into the comparison report:

* DE progress / convergence curves,
* ROC curves (Weise-style) and ROI/non-ROI field distributions
  (Fernandez-Corazza-style),
* electrode positions on the scalp and the TI field distribution.

Both goals are run through the production build path
(:func:`tit.opt.flex.builder.build_optimization`); the goal callable is wrapped
with a plain-function recorder (a ``types.FunctionType``, as SimNIBS's callable-
goal path requires) that stores the best-so-far fields without changing the
objective value. The ROC objective is reproduced faithfully via SimNIBS's own
``measures.ROC``.

Usage
-----
    OUT_DIR=/path/out PROJECT_DIR=/path/bids \\
        simnibs_python run_comparison.py [--maxiter N] [--popsize N] [--cpus N] \\
        [--only superficial_focality_integral]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

import numpy as np

from tit.paths import get_path_manager
from tit.opt.config import FlexConfig
from tit.opt.flex import builder

logger = logging.getLogger("focality_compare")

# --- Targets (MNI coordinates) --------------------------------------------
SUPERFICIAL_ROI = dict(x=-37, y=-21, z=58, radius=10.0, use_mni=True)
DEEP_ROI = dict(x=-28, y=-20, z=-16, radius=8.0, use_mni=True, volumetric=True)
# ROC thresholds (V/m): non-ROI max, ROI min.
ROC_THRESHOLDS = "0.1,0.2"
# Cap on how many non-ROI samples to persist (whole-brain non-ROI is large).
_MAX_NONROI = 40000


def _roc_inner(threshold):
    """Faithful reproduction of SimNIBS's native ROC objective as a callable."""
    from simnibs.optimization.tes_flex_optimization.measures import ROC

    thr = [float(v) for v in threshold.split(",")]

    def roc(e_pp):
        vals = []
        for chan in e_pp:
            r = ROC(e1=np.asarray(chan[0]), e2=np.asarray(chan[1]),
                    threshold=thr, focal=True)
            vals.append(-100.0 * (np.sqrt(2) - r))
        return float(np.mean(vals))

    return roc


def _make_recording_goal(inner, opt, store):
    """Wrap *inner* in a plain function that records the best-so-far state.

    Returned object is a ``types.FunctionType`` (SimNIBS requires this for a
    callable goal). It never alters the objective value.
    """

    def goal(e_pp):
        value = inner(e_pp)
        store["trajectory"].append(value)
        if value < store["best_value"]:
            store["best_value"] = value
            store["e_roi"] = np.asarray(e_pp[0][0], dtype=float).copy()
            store["e_nonroi"] = np.asarray(e_pp[0][1], dtype=float).copy()
            try:
                store["electrode_pos"] = [
                    [None if p is None else np.asarray(p, dtype=float).tolist()
                     for p in arr]
                    for arr in opt.electrode_pos
                ]
            except Exception:
                store["electrode_pos"] = None
        return value

    return goal


def _final_meshes(out_dir: Path):
    """Per-channel final-simulation E-field meshes (one per TI pair).

    flex writes ``final_sim_<k>/<subject>_TDCS_*.msh`` per channel; the report
    combines the two channels' E-fields into the TI envelope.
    """
    meshes = sorted(str(p) for p in out_dir.glob("final_sim_*/*.msh"))
    return meshes or None


def _subsample(a: np.ndarray, n: int) -> np.ndarray:
    if a.size <= n:
        return a
    idx = np.linspace(0, a.size - 1, n).astype(int)
    return a[idx]


def _run_one(subject, roi_kwargs, goal, out_dir: Path, thresholds, budget) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
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
        run_final_electrode_simulation=True,  # produce final TI-field mesh
    )

    opt = builder.build_optimization(cfg)
    builder.configure_optimizer_options(opt, cfg, logger)

    # Wrap the goal to record best-so-far fields. For integral, opt.goal[0] is
    # the production closure; for ROC we supply a faithful native-ROC callable.
    inner = opt.goal[0] if goal == "focality_integral" else _roc_inner(thresholds)
    store = {"trajectory": [], "best_value": float("inf"),
             "e_roi": None, "e_nonroi": None, "electrode_pos": None}
    opt.goal = [_make_recording_goal(inner, opt, store)]

    t0 = time.time()
    opt.run(cpus=budget["cpus"])
    elapsed = time.time() - t0

    arrays_path = out_dir / "fields.npz"
    if store["e_roi"] is not None:
        np.savez_compressed(
            arrays_path,
            e_roi=store["e_roi"],
            e_nonroi=_subsample(store["e_nonroi"], _MAX_NONROI),
        )
    return {
        "goal": goal,
        "roi": roi_kwargs,
        "best_value": None if store["best_value"] == float("inf") else store["best_value"],
        "trajectory": store["trajectory"],
        "n_evaluations": len(store["trajectory"]),
        "electrode_pos": store["electrode_pos"],
        "arrays_npz": str(arrays_path) if store["e_roi"] is not None else None,
        "final_meshes": _final_meshes(out_dir),
        "elapsed_sec": round(elapsed, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maxiter", type=int, default=3)
    parser.add_argument("--popsize", type=int, default=4)
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--subject", default="ernie")
    parser.add_argument("--only", default=None,
                        help="Run a single cell, e.g. 'deep_focality'")
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
    if args.only:
        matrix = [c for c in matrix if f"{c[0]}_{c[2]}" == args.only]

    results = {"subject": args.subject, "budget": budget, "cells": []}
    results_path = out_root / "results.json"
    for depth, roi, goal in matrix:
        print(f"\n=== {depth} x {goal} ===", flush=True)
        out_dir = out_root / f"{depth}_{goal}"
        try:
            cell = _run_one(args.subject, roi, goal, out_dir, ROC_THRESHOLDS, budget)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            cell = {"goal": goal, "roi": roi, "error": repr(exc),
                    "trajectory": [], "n_evaluations": 0}
        cell["depth"] = depth
        results["cells"].append(cell)
        sp = (max(cell["trajectory"]) - min(cell["trajectory"])) if cell["trajectory"] else 0.0
        print(f"  evals={cell.get('n_evaluations')} best={cell.get('best_value')} "
              f"spread={sp:.4g} mesh={'yes' if cell.get('final_mesh') else 'no'} "
              f"elapsed={cell.get('elapsed_sec')}s", flush=True)
        results_path.write_text(json.dumps(results, indent=2))

    print(f"\nWrote {results_path}")


if __name__ == "__main__":
    main()
