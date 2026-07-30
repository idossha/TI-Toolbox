#!/usr/bin/env simnibs_python
"""Cohort focality study — 5 objectives x 3 atlas targets, per TISSR subject.

Compares five flex-search focality objectives on three anatomically-defined
(atlas, not spherical) deep targets, at SimNIBS default budget, single-start,
for a cohort of subjects. Every individual's full flex output is retained;
per-run metrics (the study's focality/intensity/composite plus Weise's
ROC-distance and Ghanem's V_off, for cross-paper comparison) are captured from
the exact best-montage ROI / non-ROI fields.

Atlas ROIs use each subject's FreeSurfer aparc.DKTatlas+aseg resampled into the
m2m/T1 grid (already mesh-aligned): L-hippocampus=17, R-thalamus=49,
L-insula=1035, selected as GM tetrahedra inside the label mask.

Held constant + logged per run (flex_meta.json + metrics.json): head model,
current, electrode geometry, envelope method, DE hyperparameters, thresholds.
Only the arm's objective varies.

Usage
-----
    OUT_DIR=~/Desktop/focality_cohort PROJECT_DIR=/Volumes/IDO2/000_TISSR \\
        simnibs_python run_study.py [--subjects 101 102 ...] [--only sub_target_arm]
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

logger = logging.getLogger("focality_cohort")

FS_ATLAS = ("/Volumes/IDO2/000_TISSR/derivatives/freesurfer/sub-{s}/mri/"
            "aparc.DKTatlas+aseg_resampled_240x512x512.mgz")
SUBJECTS = ["101", "102", "103", "106", "107"]

TARGETS = [
    {"key": "L-hippocampus", "label": 17},
    {"key": "R-thalamus", "label": 49},
    {"key": "L-insula", "label": 1035},
]

ARMS = [
    {"key": "roc_lo", "kind": "roc", "thr": "0.1,0.2", "label": "ROC 0.2/0.1"},
    {"key": "roc_hi", "kind": "roc", "thr": "0.2,0.4", "label": "ROC 0.4/0.2"},
    {"key": "auc", "kind": "auc", "thr": None, "label": "direct-AUC"},
    {"key": "tail", "kind": "tail", "thr": None, "label": "tail mean/p95"},
    {"key": "composite", "kind": "composite", "thr": None, "label": "composite mean^2/mean"},
]

# Fixed, logged experiment constants.
CURRENT_MA = 2.0
ELECTRODE_DIM = [22.0, 22.0]   # circular Ø22 mm (Weise TIS spec)
ROC_WEISE = (0.2, 0.1)         # (t_ROI, t_nonROI) V/m for the Weise ROC-distance metric
E_TH = 0.2                     # V/m, Ghanem V_off threshold
_MAX_NONROI = 60000


# --------------------------------------------------------------------------
# objectives (the arm's optimized measure; the recorder negates for DE)
# --------------------------------------------------------------------------
def _roc_inner(threshold):
    from simnibs.optimization.tes_flex_optimization.measures import ROC
    thr = [float(v) for v in threshold.split(",")]

    def roc(e_pp):
        return float(np.mean([
            -100.0 * (np.sqrt(2) - ROC(e1=np.asarray(c[0]), e2=np.asarray(c[1]),
                                       threshold=thr, focal=True))
            for c in e_pp]))
    return roc


def _variant_inner(kind):
    from simnibs.optimization.tes_flex_optimization.measures import AUC

    def f(e_pp):
        vals = []
        for c in e_pp:
            e1 = np.asarray(c[0], float); e2 = np.asarray(c[1], float)
            m1, m2 = float(e1.mean()), float(e2.mean())
            p95 = float(np.percentile(e2, 95))
            if kind == "tail":
                v = m1 / max(p95, 1e-9)
            elif kind == "auc":
                v = float(AUC(e1=e1, e2=e2))
            elif kind == "composite":          # mean(E_ROI)^2 / mean(E_nonROI)
                v = (m1 * m1) / max(m2, 1e-9)
            else:
                v = m1 / np.sqrt(max(m2, 1e-9))
            vals.append(v)
        s = float(np.mean(vals))
        return -s if np.isfinite(s) else 1e3
    return f


def _recording_goal(inner, opt, store):
    def goal(e_pp):
        value = inner(e_pp)
        e1 = np.asarray(e_pp[0][0], float); e2 = np.asarray(e_pp[0][1], float)
        ratio = float(e1.mean()) / max(float(e2.mean()), 1e-9)
        store["trajectory"].append(value)
        if value < store["best_value"]:
            store.update(best_value=value, best_ratio=ratio,
                         e_roi=e1.copy(), e_nonroi=e2.copy())
            try:
                store["electrode_pos"] = [
                    [None if p is None else np.asarray(p, float).tolist() for p in arr]
                    for arr in opt.electrode_pos]
            except Exception:
                store["electrode_pos"] = None
        store["ratio_progress"].append(store["best_ratio"])
        return value
    return goal


# --------------------------------------------------------------------------
# metrics computed post-hoc from the best-montage ROI / non-ROI fields
# --------------------------------------------------------------------------
def _metrics(e1, e2):
    m1, m2 = float(e1.mean()), float(e2.mean())
    # Weise ROC-distance at (t_ROI, t_nonROI)
    tR, tN = ROC_WEISE
    sens = float((e1 >= tR).mean()); spec = float((e2 < tN).mean())
    roc_dist = float(np.hypot(1 - sens, 1 - spec))
    # AUC (threshold-free)
    emax = max(float(e1.max()), float(e2.max()), 1e-12)
    thr = np.linspace(0, emax, 200)
    s = np.array([(e1 >= t).mean() for t in thr]); f = np.array([(e2 >= t).mean() for t in thr])
    o = np.argsort(f); tz = getattr(np, "trapezoid", np.trapz)
    auc = float(tz(s[o], f[o]))
    return {
        "roi_mean": m1, "nonroi_mean": m2,
        "focality_ratio": m1 / max(m2, 1e-9),
        "composite": (m1 * m1) / max(m2, 1e-9),
        "roc_distance": roc_dist,          # Weise (lower = better)
        "v_off_pct": float((e2 >= E_TH).mean()) * 100.0,             # Ghanem, as-optimized
        "v_off_norm_pct": float((e2 >= m1).mean()) * 100.0,          # Ghanem at E_ROI=0.2 norm
        "auc": auc,
    }


def _final_meshes(out_dir: Path):
    return sorted(str(p) for p in out_dir.glob("final_sim_*/*.msh")) or None


def _run_cell(subject, atlas, target, arm, out_dir: Path, budget) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = arm["kind"]
    cfg_goal = "focality" if kind == "roc" else "focality_integral"
    cfg = FlexConfig(
        subject_id=subject,
        goal=cfg_goal,
        postproc="max_TI",
        current_mA=CURRENT_MA,
        electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=list(ELECTRODE_DIM)),
        roi=FlexConfig.SubcorticalROI(atlas_path=atlas, label=target["label"],
                                      tissues="GM", atlas_space="subject"),
        non_roi_method="everything_else",
        thresholds=arm.get("thr"),
        output_folder=str(out_dir),
        max_iterations=budget[0],
        population_size=budget[1],
        n_multistart=1,
        run_final_electrode_simulation=budget[2],
    )
    opt = builder.build_optimization(cfg)
    builder.configure_optimizer_options(opt, cfg, logger)
    inner = (opt.goal[0] if kind == "integral"
             else _roc_inner(arm["thr"]) if kind == "roc" else _variant_inner(kind))
    store = {"trajectory": [], "ratio_progress": [], "best_value": float("inf"),
             "best_ratio": 0.0, "e_roi": None, "e_nonroi": None, "electrode_pos": None}
    opt.goal = [_recording_goal(inner, opt, store)]

    t0 = time.time()
    opt.run(cpus=int(os.environ.get("CPUS", "4")))
    elapsed = time.time() - t0

    cell = {"subject": subject, "target": target["key"], "arm": arm["key"],
            "arm_label": arm["label"], "kind": kind, "thresholds": arm.get("thr"),
            "atlas_label": target["label"], "n_evaluations": len(store["trajectory"]),
            "elapsed_sec": round(elapsed, 1), "electrode_pos": store["electrode_pos"],
            "final_meshes": _final_meshes(out_dir)}
    if store["e_roi"] is not None:
        e1, e2 = store["e_roi"], store["e_nonroi"]
        cell["metrics"] = _metrics(e1, e2)
        npz = out_dir / "fields.npz"
        idx = (np.linspace(0, e2.size - 1, _MAX_NONROI).astype(int) if e2.size > _MAX_NONROI
               else slice(None))
        np.savez_compressed(npz, e_roi=e1, e_nonroi=e2[idx])
        cell["arrays_npz"] = str(npz)
    return cell


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--subjects", nargs="*", default=SUBJECTS)
    p.add_argument("--only", default=None, help="single cell 'subj_target_arm'")
    p.add_argument("--maxiter", type=int, default=None, help="override (default=SimNIBS default)")
    p.add_argument("--popsize", type=int, default=None)
    p.add_argument("--no-final-sim", action="store_true", help="smoke test: skip final sim")
    args = p.parse_args()
    budget = (args.maxiter, args.popsize, not args.no_final_sim)

    project_dir = os.environ.get("PROJECT_DIR", "/Volumes/IDO2/000_TISSR")
    out_root = Path(os.path.expanduser(os.environ.get(
        "OUT_DIR", "~/Desktop/focality_cohort")))
    out_root.mkdir(parents=True, exist_ok=True)
    get_path_manager(project_dir)

    manifest = {"current_mA": CURRENT_MA, "electrode_dim_mm": ELECTRODE_DIM,
                "envelope": "max_TI (free direction)", "non_roi": "everything_else",
                "budget": "SimNIBS default (popsize 13, maxiter 1000, tol 0.1)"
                if args.maxiter is None else {"maxiter": args.maxiter, "popsize": args.popsize},
                "roc_weise_thresholds": ROC_WEISE, "v_off_threshold": E_TH,
                "seeds": 1, "targets": TARGETS, "arms": ARMS}
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2))

    for subject in args.subjects:
        atlas = FS_ATLAS.format(s=subject)
        if not Path(atlas).is_file():
            print(f"!! sub-{subject}: atlas missing {atlas}"); continue
        subj_dir = out_root / f"sub-{subject}"
        subj_dir.mkdir(parents=True, exist_ok=True)
        cells = []
        results_path = subj_dir / "metrics.json"
        for target in TARGETS:
            for arm in ARMS:
                key = f"{subject}_{target['key']}_{arm['key']}"
                if args.only and key != args.only:
                    continue
                print(f"\n=== {key} ===", flush=True)
                try:
                    cell = _run_cell(subject, atlas, target, arm,
                                     subj_dir / f"{target['key']}_{arm['key']}", budget)
                except Exception as exc:
                    import traceback; traceback.print_exc()
                    cell = {"subject": subject, "target": target["key"], "arm": arm["key"],
                            "error": repr(exc)}
                cells.append(cell)
                m = cell.get("metrics", {})
                print(f"  focality={m.get('focality_ratio')} roi={m.get('roi_mean')} "
                      f"auc={m.get('auc')} v_off={m.get('v_off_pct')} "
                      f"elapsed={cell.get('elapsed_sec')}s", flush=True)
                results_path.write_text(json.dumps(cells, indent=2))
        print(f"\n-- sub-{subject} done: {results_path}")

    print(f"\nAll requested subjects done under {out_root}")


if __name__ == "__main__":
    main()
