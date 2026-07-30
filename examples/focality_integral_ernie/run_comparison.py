#!/usr/bin/env simnibs_python
"""Three-arm focality comparison on deep targets (ernie).

For each deep target (thalamus, hippocampus) runs flex-search under three arms:

  * ROC focality at a **conservative** threshold,
  * ROC focality at an **aggressive** threshold,
  * threshold-free **integral** focality,

and captures, per run: the objective trajectory, a *common* focality metric
(best mean ROI/non-ROI contrast so far — comparable across arms despite the two
objectives living on different scales), the best-montage ROI/non-ROI E-field
arrays, and the per-channel final-simulation meshes (for the on-T1 field render
and electrode positions). Feed `results.json` to make_report.py / make_artifact.py.

Both goals run through the production build path
(`tit.opt.flex.builder.build_optimization`); the goal callable is wrapped with a
plain-function recorder (a `types.FunctionType`, as SimNIBS's callable-goal path
requires) that never changes the objective value. The ROC objective is reproduced
faithfully via SimNIBS's own `measures.ROC`.

Usage
-----
    OUT_DIR=/path/out PROJECT_DIR=/path/bids \\
        simnibs_python run_comparison.py [--default | --maxiter N --popsize N] \\
        [--cpus N] [--only thalamus_integral]
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

# --- Deep targets (MNI) ----------------------------------------------------
TARGETS = [
    {"key": "thalamus", "roi": dict(x=-10, y=-19, z=8, radius=6.0,
                                     use_mni=True, volumetric=True)},
    {"key": "hippocampus", "roi": dict(x=-28, y=-20, z=-16, radius=8.0,
                                        use_mni=True, volumetric=True)},
]

# --- Three arms: two ROC thresholds (V/m: nonROImax,ROImin) + threshold-free
ARMS = [
    {"key": "roc_lo", "goal": "focality", "thr": "0.1,0.2", "label": "ROC (0.1/0.2 V/m)"},
    {"key": "roc_hi", "goal": "focality", "thr": "0.2,0.4", "label": "ROC (0.2/0.4 V/m)"},
    {"key": "integral", "goal": "focality_integral", "thr": None, "label": "Integral (threshold-free)"},
]

_MAX_NONROI = 40000


def _roc_inner(threshold):
    from simnibs.optimization.tes_flex_optimization.measures import ROC
    thr = [float(v) for v in threshold.split(",")]

    def roc(e_pp):
        vals = []
        for chan in e_pp:
            r = ROC(e1=np.asarray(chan[0]), e2=np.asarray(chan[1]), threshold=thr, focal=True)
            vals.append(-100.0 * (np.sqrt(2) - r))
        return float(np.mean(vals))

    return roc


def _make_recording_goal(inner, opt, store):
    """Wrap *inner* in a plain function that records best-so-far state + a common
    focality metric (ROI/non-ROI mean contrast of the current best montage)."""

    def goal(e_pp):
        value = inner(e_pp)
        e1 = np.asarray(e_pp[0][0], dtype=float)
        e2 = np.asarray(e_pp[0][1], dtype=float)
        ratio = float(e1.mean()) / max(float(e2.mean()), 1e-9)
        store["trajectory"].append(value)
        if value < store["best_value"]:
            store["best_value"] = value
            store["best_ratio"] = ratio
            store["e_roi"] = e1.copy()
            store["e_nonroi"] = e2.copy()
            try:
                store["electrode_pos"] = [
                    [None if p is None else np.asarray(p, float).tolist() for p in arr]
                    for arr in opt.electrode_pos
                ]
            except Exception:
                store["electrode_pos"] = None
        # common metric: focality of the montage currently considered best
        store["ratio_progress"].append(store["best_ratio"])
        return value

    return goal


def _final_meshes(out_dir: Path):
    meshes = sorted(str(p) for p in out_dir.glob("final_sim_*/*.msh"))
    return meshes or None


def _subsample(a, n):
    if a.size <= n:
        return a
    return a[np.linspace(0, a.size - 1, n).astype(int)]


def _run_one(subject, roi_kwargs, arm, out_dir: Path, budget, final_sim=True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = FlexConfig(
        subject_id=subject,
        goal=arm["goal"],
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(**roi_kwargs),
        non_roi_method="everything_else",
        thresholds=arm["thr"],
        output_folder=str(out_dir),
        max_iterations=budget["maxiter"],
        population_size=budget["popsize"],
        tolerance=budget["tol"],
        n_multistart=1,
        run_final_electrode_simulation=final_sim,
    )
    opt = builder.build_optimization(cfg)
    builder.configure_optimizer_options(opt, cfg, logger)

    inner = opt.goal[0] if arm["goal"] == "focality_integral" else _roc_inner(arm["thr"])
    store = {"trajectory": [], "ratio_progress": [], "best_value": float("inf"),
             "best_ratio": 0.0, "e_roi": None, "e_nonroi": None, "electrode_pos": None}
    opt.goal = [_make_recording_goal(inner, opt, store)]

    t0 = time.time()
    opt.run(cpus=budget["cpus"])
    elapsed = time.time() - t0

    arrays_path = out_dir / "fields.npz"
    if store["e_roi"] is not None:
        np.savez_compressed(arrays_path, e_roi=store["e_roi"],
                            e_nonroi=_subsample(store["e_nonroi"], _MAX_NONROI))
    return {
        "arm": arm["key"], "arm_label": arm["label"], "goal": arm["goal"],
        "thresholds": arm["thr"], "roi": roi_kwargs,
        "best_value": None if store["best_value"] == float("inf") else store["best_value"],
        "best_ratio": store["best_ratio"],
        "trajectory": store["trajectory"], "ratio_progress": store["ratio_progress"],
        "n_evaluations": len(store["trajectory"]),
        "electrode_pos": store["electrode_pos"],
        "arrays_npz": str(arrays_path) if store["e_roi"] is not None else None,
        "final_meshes": _final_meshes(out_dir),
        "elapsed_sec": round(elapsed, 1),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--default", action="store_true",
                   help="Use SimNIBS default optimizer settings (popsize 13, maxiter 1000, tol 0.1)")
    p.add_argument("--maxiter", type=int, default=15)
    p.add_argument("--popsize", type=int, default=6)
    p.add_argument("--tol", type=float, default=None)
    p.add_argument("--cpus", type=int, default=4)
    p.add_argument("--subject", default="ernie")
    p.add_argument("--only", default=None, help="Run a single cell, e.g. 'thalamus_integral'")
    p.add_argument("--no-final-sim", action="store_true")
    args = p.parse_args()

    if args.default:
        budget = {"maxiter": None, "popsize": None, "tol": None, "cpus": args.cpus}
    else:
        budget = {"maxiter": args.maxiter, "popsize": args.popsize,
                  "tol": args.tol, "cpus": args.cpus}

    project_dir = os.environ.get("PROJECT_DIR", "/Users/idohaber/datasets/000")
    out_root = Path(os.environ.get("OUT_DIR", "./focality_3arm_out"))
    out_root.mkdir(parents=True, exist_ok=True)
    get_path_manager(project_dir)

    matrix = [(t, a) for t in TARGETS for a in ARMS]
    if args.only:
        matrix = [(t, a) for t, a in matrix if f"{t['key']}_{a['key']}" == args.only]

    results = {"subject": args.subject,
               "budget": ("SimNIBS default (popsize 13, maxiter 1000, tol 0.1)"
                          if args.default else budget),
               "cells": []}
    results_path = out_root / "results.json"
    for target, arm in matrix:
        key = f"{target['key']}_{arm['key']}"
        print(f"\n=== {key} ===", flush=True)
        try:
            cell = _run_one(args.subject, target["roi"], arm, out_root / key, budget,
                            final_sim=not args.no_final_sim)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            cell = {"arm": arm["key"], "goal": arm["goal"], "error": repr(exc),
                    "trajectory": [], "ratio_progress": [], "n_evaluations": 0}
        cell["target"] = target["key"]
        results["cells"].append(cell)
        print(f"  evals={cell.get('n_evaluations')} best_ratio={cell.get('best_ratio')} "
              f"mesh={'yes' if cell.get('final_meshes') else 'no'} "
              f"elapsed={cell.get('elapsed_sec')}s", flush=True)
        results_path.write_text(json.dumps(results, indent=2))

    print(f"\nWrote {results_path}")


if __name__ == "__main__":
    main()
