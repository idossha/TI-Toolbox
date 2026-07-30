#!/usr/bin/env simnibs_python
"""Render comparison panels for the focality study (3-arm or variant).

Arm-agnostic: reads the arm set from results.json, so it works for both the
3-arm comparison and the improved-integral variant study. Writes a common-metric
progress plot, per-target ROC curves, ROI/non-ROI distributions, a summary bar,
plus per-condition electrodes-on-scalp and field-on-T1 renders.

Usage:  PROJECT_DIR=/path/bids simnibs_python make_report.py results.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from examples.focality_integral_ernie import t1_overlay

_PALETTE = ["#b11226", "#0353a4", "#e08a2e", "#2a9d8f", "#7b2cbf", "#1d3557", "#e76f51"]


def arms(results):
    seen = []
    for c in results["cells"]:
        if c.get("arm") not in seen:
            seen.append(c.get("arm"))
    return seen


def color(results, arm):
    return _PALETTE[arms(results).index(arm) % len(_PALETTE)]


def targets(results):
    out = []
    for c in results["cells"]:
        if c.get("target") not in out:
            out.append(c.get("target"))
    return out


def cell(results, t, a):
    return next((c for c in results["cells"] if c.get("target") == t and c.get("arm") == a), {})


def label(results, a):
    return next((c["arm_label"] for c in results["cells"] if c.get("arm") == a and c.get("arm_label")), a)


def fields(c):
    p = c.get("arrays_npz")
    if not p or not Path(p).is_file():
        return None, None
    z = np.load(p)
    return z["e_roi"], z["e_nonroi"]


def roc_curve(e1, e2, n=200):
    emax = max(float(e1.max()), float(e2.max()), 1e-12)
    thr = np.linspace(0, emax, n)
    sens = np.array([(e1 >= t).mean() for t in thr])
    fpr = np.array([(e2 >= t).mean() for t in thr])
    o = np.argsort(fpr)
    tz = getattr(np, "trapezoid", np.trapz)
    return fpr[o], sens[o], float(tz(sens[o], fpr[o]))


def fig_progress(results, path):
    tg, ar = targets(results), arms(results)
    fig, axes = plt.subplots(1, len(tg), figsize=(6.2 * len(tg), 4.8),
                             constrained_layout=True, squeeze=False)
    fig.suptitle("Optimization progress — focality of the current-best montage "
                 "(common metric, comparable across arms)", fontweight="bold")
    for ax, t in zip(axes[0], tg):
        for a in ar:
            rp = cell(results, t, a).get("ratio_progress", [])
            if rp:
                ax.plot(range(1, len(rp) + 1), rp, "-", lw=1.8, color=color(results, a),
                        label=label(results, a))
        ax.set_title(f"{t} target", fontsize=11)
        ax.set_xlabel("valid evaluation #"); ax.set_ylabel("best mean ROI / non-ROI so far")
        ax.legend(fontsize=7.5); ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


def fig_roc(results, path):
    tg, ar = targets(results), arms(results)
    fig, axes = plt.subplots(1, len(tg), figsize=(6.2 * len(tg), 5.0),
                             constrained_layout=True, squeeze=False)
    fig.suptitle("ROC of the optimized montage: ROI sensitivity vs non-ROI 1−specificity",
                 fontweight="bold")
    for ax, t in zip(axes[0], tg):
        ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.5)
        for a in ar:
            e1, e2 = fields(cell(results, t, a))
            if e1 is None:
                continue
            fpr, sens, auc = roc_curve(e1, e2)
            ax.plot(fpr, sens, "-", lw=1.8, color=color(results, a),
                    label=f"{label(results, a)} — AUC {auc:.3f}")
        ax.set_title(f"{t} target", fontsize=11)
        ax.set_xlabel("1 − specificity"); ax.set_ylabel("sensitivity")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        if ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=7.5, loc="lower right")
        ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


def fig_distributions(results, path):
    tg, ar = targets(results), arms(results)
    fig, axes = plt.subplots(len(tg), len(ar), figsize=(2.9 * len(ar), 3.2 * len(tg)),
                             constrained_layout=True, squeeze=False)
    fig.suptitle("Field distributions (ROI vs non-ROI, Fernández-Corazza-style)",
                 fontweight="bold")
    for i, t in enumerate(tg):
        for j, a in enumerate(ar):
            ax = axes[i][j]
            e1, e2 = fields(cell(results, t, a))
            if e1 is None:
                ax.set_title(f"{t}·{a}\n(no data)", fontsize=8); continue
            hi = max(float(np.percentile(e1, 99)), float(np.percentile(e2, 99)), 1e-6)
            bins = np.linspace(0, hi, 45)
            ax.hist(e2, bins=bins, density=True, color="#8d99ae", alpha=0.6, label="non-ROI")
            ax.hist(e1, bins=bins, density=True, color=color(results, a), alpha=0.75, label="ROI")
            ratio = float(e1.mean()) / max(float(e2.mean()), 1e-9)
            ax.set_title(f"{t} · {a}\nROI/nonROI={ratio:.2f}", fontsize=8)
            ax.set_xlabel("TI (V/m)"); ax.legend(fontsize=6.5); ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


def fig_summary(results, path):
    tg, ar = targets(results), arms(results)
    x = np.arange(len(tg)); w = 0.8 / max(len(ar), 1)
    fig, ax = plt.subplots(figsize=(2.5 + 3.0 * len(tg), 4.6), constrained_layout=True)
    for k, a in enumerate(ar):
        vals = [cell(results, t, a).get("best_ratio", 0.0) or 0.0 for t in tg]
        ax.bar(x + (k - (len(ar) - 1) / 2) * w, vals, w, color=color(results, a),
               label=label(results, a))
    ax.set_xticks(x); ax.set_xticklabels(tg)
    ax.set_ylabel("best mean ROI / non-ROI")
    ax.set_title("Focality contrast achieved", fontweight="bold")
    ax.legend(fontsize=7.5); ax.grid(True, axis="y", alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


def _views():
    return [("top", 0, 1, lambda p: np.ones(len(p), bool)),
            ("left", 1, 2, lambda p: p[:, 0] <= 0),
            ("front", 0, 2, lambda p: p[:, 1] >= 0)]


def fig_scalp(c, meshes, path):
    if not meshes:
        return False
    skin = meshes[0].crop_mesh(tags=[1005])
    pts = skin.nodes.node_coord
    if pts.shape[0] > 80000:
        pts = pts[np.linspace(0, pts.shape[0] - 1, 80000).astype(int)]
    epos = []
    for m in meshes:
        bary = m.elements_baricenters().value
        for t in sorted(set(m.elm.tag1.tolist())):
            if 500 <= t < 600:
                epos.append(bary[m.elm.tag1 == t].mean(axis=0))
    epos = np.array(epos) if epos else None
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), constrained_layout=True)
    fig.suptitle(f"Optimized electrodes on scalp — {c['target']} · {c.get('arm_label','')}",
                 fontweight="bold", fontsize=11)
    for ax, (title, xi, yi, mfn) in zip(axes, _views()):
        vm = mfn(pts)
        ax.scatter(pts[vm, xi], pts[vm, yi], c="#cbd5e1", s=0.4, alpha=0.6, rasterized=True)
        if epos is not None and epos.size:
            evm = mfn(epos)
            ax.scatter(epos[evm, xi], epos[evm, yi], c="#d00000", s=110,
                       edgecolors="k", linewidths=0.7, zorder=5)
        ax.set_title(title, fontsize=9); ax.set_aspect("equal"); ax.axis("off")
    fig.savefig(path, dpi=130); plt.close(fig)
    return True


def main():
    results_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results.json")
    results = json.loads(results_path.read_text())
    out = results_path.parent
    subject = results.get("subject", "ernie")
    from tit.paths import get_path_manager
    project_dir = os.environ.get("PROJECT_DIR")
    try:
        pm = get_path_manager(project_dir) if project_dir else get_path_manager()
        m2m = str(Path(pm.m2m(subject)))
        if not Path(m2m, "T1.nii.gz").is_file():
            print(f"  note: no T1 at {m2m} — skipping on-T1 overlays"); m2m = None
    except Exception as exc:
        print(f"  note: could not resolve m2m ({exc!r}) — skipping on-T1 overlays"); m2m = None

    fig_progress(results, out / "progress.png")
    fig_roc(results, out / "roc.png")
    fig_distributions(results, out / "distributions.png")
    fig_summary(results, out / "summary.png")

    import simnibs
    for c in results["cells"]:
        key = f"{c.get('target')}_{c.get('arm')}"
        mp = [p for p in (c.get("final_meshes") or []) if Path(p).is_file()][:2]
        if mp and m2m and c.get("roi"):
            r = c["roi"]
            try:
                t1_overlay.render_overlay_from_meshes(
                    mp, [r["x"], r["y"], r["z"]], r.get("radius", 8.0), m2m,
                    str(out / f"t1_{key}.png"), f"{c['target']} · {c.get('arm_label','')}")
            except Exception as exc:
                print(f"  t1 overlay failed {key}: {exc!r}")
        if mp:
            try:
                loaded = [simnibs.read_msh(p) for p in mp]
                fig_scalp(c, loaded, out / f"scalp_{key}.png"); del loaded
            except Exception as exc:
                print(f"  scalp failed {key}: {exc!r}")
    print(f"Wrote panels to {out}")


if __name__ == "__main__":
    main()
