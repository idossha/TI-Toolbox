#!/usr/bin/env simnibs_python
"""Render comparison panels for the 3-arm focality study.

Reads results.json (+ per-cell fields.npz and final-sim meshes) and writes PNG
panels: a common-metric progress plot, per-target ROC curves, ROI/non-ROI
distributions, a summary bar, plus per-condition electrodes-on-scalp and
field-on-T1 renders. make_artifact.py assembles these into report.html.

Usage:  simnibs_python make_report.py results.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from examples.focality_integral_ernie import t1_overlay

ARMS = ["roc_lo", "roc_hi", "integral"]
ARM_COLOR = {"roc_lo": "#e08a2e", "roc_hi": "#b11226", "integral": "#0353a4"}


def _targets(results):
    out = []
    for c in results["cells"]:
        if c.get("target") not in out:
            out.append(c.get("target"))
    return out


def _cell(results, target, arm):
    for c in results["cells"]:
        if c.get("target") == target and c.get("arm") == arm:
            return c
    return {}


def _label(results, arm):
    for c in results["cells"]:
        if c.get("arm") == arm and c.get("arm_label"):
            return c["arm_label"]
    return arm


def _fields(cell):
    p = cell.get("arrays_npz")
    if not p or not Path(p).is_file():
        return None, None
    z = np.load(p)
    return z["e_roi"], z["e_nonroi"]


def _roc(e1, e2, n=200):
    emax = max(float(e1.max()), float(e2.max()), 1e-12)
    thr = np.linspace(0, emax, n)
    sens = np.array([(e1 >= t).mean() for t in thr])
    fpr = np.array([(e2 >= t).mean() for t in thr])
    o = np.argsort(fpr)
    trapz = getattr(np, "trapezoid", np.trapz)
    return fpr[o], sens[o], float(trapz(sens[o], fpr[o]))


def fig_progress(results, path):
    """Common metric: best ROI/non-ROI contrast so far — comparable across arms."""
    tg = _targets(results)
    fig, axes = plt.subplots(1, len(tg), figsize=(6 * len(tg), 4.6),
                             constrained_layout=True, squeeze=False)
    fig.suptitle("Optimization progress — focality of the current-best montage "
                 "(common metric, comparable across arms)", fontweight="bold")
    for ax, target in zip(axes[0], tg):
        for arm in ARMS:
            c = _cell(results, target, arm)
            rp = c.get("ratio_progress", [])
            if rp:
                ax.plot(range(1, len(rp) + 1), rp, "-", lw=2, color=ARM_COLOR[arm],
                        label=_label(results, arm))
        ax.set_title(f"{target} target", fontsize=11)
        ax.set_xlabel("valid evaluation #")
        ax.set_ylabel("best mean ROI / non-ROI so far")
        ax.legend(fontsize=8.5); ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


def fig_roc(results, path):
    tg = _targets(results)
    fig, axes = plt.subplots(1, len(tg), figsize=(6 * len(tg), 5.0),
                             constrained_layout=True, squeeze=False)
    fig.suptitle("ROC of the optimized montage (Weise-style): ROI sensitivity vs "
                 "non-ROI 1−specificity", fontweight="bold")
    for ax, target in zip(axes[0], tg):
        ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.5)
        for arm in ARMS:
            e1, e2 = _fields(_cell(results, target, arm))
            if e1 is None:
                continue
            fpr, sens, auc = _roc(e1, e2)
            ax.plot(fpr, sens, "-", lw=2, color=ARM_COLOR[arm],
                    label=f"{_label(results, arm)} (AUC={auc:.3f})")
        ax.set_title(f"{target} target", fontsize=11)
        ax.set_xlabel("1 − specificity (non-ROI above threshold)")
        ax.set_ylabel("sensitivity (ROI above threshold)")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        if ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=8.5, loc="lower right")
        ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


def fig_distributions(results, path):
    tg = _targets(results)
    fig, axes = plt.subplots(len(tg), len(ARMS), figsize=(4.2 * len(ARMS), 3.4 * len(tg)),
                             constrained_layout=True, squeeze=False)
    fig.suptitle("Field distributions of the optimized montage "
                 "(ROI vs non-ROI, Fernández-Corazza-style)", fontweight="bold")
    for i, target in enumerate(tg):
        for j, arm in enumerate(ARMS):
            ax = axes[i][j]
            e1, e2 = _fields(_cell(results, target, arm))
            if e1 is None:
                ax.set_title(f"{target} · {arm} (no data)", fontsize=9); continue
            hi = max(float(np.percentile(e1, 99)), float(np.percentile(e2, 99)), 1e-6)
            bins = np.linspace(0, hi, 55)
            ax.hist(e2, bins=bins, density=True, color="#8d99ae", alpha=0.6, label="non-ROI")
            ax.hist(e1, bins=bins, density=True, color=ARM_COLOR[arm], alpha=0.75, label="ROI")
            ratio = float(e1.mean()) / max(float(e2.mean()), 1e-9)
            ax.set_title(f"{target} · {_label(results, arm)}\nROI/non-ROI={ratio:.2f}", fontsize=8.5)
            ax.set_xlabel("TI (V/m)"); ax.legend(fontsize=7); ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


def fig_summary(results, path):
    tg = _targets(results)
    x = np.arange(len(tg)); w = 0.26
    fig, ax = plt.subplots(figsize=(1.8 + 2.4 * len(tg), 4.4), constrained_layout=True)
    for k, arm in enumerate(ARMS):
        vals = [_cell(results, t, arm).get("best_ratio", 0.0) or 0.0 for t in tg]
        bars = ax.bar(x + (k - 1) * w, vals, w, color=ARM_COLOR[arm], label=_label(results, arm))
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.2f}", (b.get_x() + b.get_width() / 2, v), ha="center",
                        va="bottom", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(tg)
    ax.set_ylabel("best mean ROI / non-ROI"); ax.set_title("Focality contrast achieved",
                                                           fontweight="bold")
    ax.legend(fontsize=8.5); ax.grid(True, axis="y", alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


# ---- per-condition mesh renders ------------------------------------------
def _project_views():
    return [("top (x-y)", 0, 1, lambda p: np.ones(len(p), bool)),
            ("left (y-z)", 1, 2, lambda p: p[:, 0] <= 0),
            ("front (x-z)", 0, 2, lambda p: p[:, 1] >= 0)]


def fig_scalp(cell, meshes, path):
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
    fig.suptitle(f"Optimized electrodes on scalp — {cell['target']} · {cell.get('arm_label','')}",
                 fontweight="bold")
    for ax, (title, xi, yi, mfn) in zip(axes, _project_views()):
        vm = mfn(pts)
        ax.scatter(pts[vm, xi], pts[vm, yi], c="#cbd5e1", s=0.4, alpha=0.6, rasterized=True)
        if epos is not None and epos.size:
            evm = mfn(epos)
            ax.scatter(epos[evm, xi], epos[evm, yi], c="#d00000", s=110,
                       edgecolors="k", linewidths=0.7, zorder=5)
        ax.set_title(title, fontsize=10); ax.set_aspect("equal"); ax.axis("off")
    fig.savefig(path, dpi=130); plt.close(fig)
    return True


def main():
    results_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results.json")
    results = json.loads(results_path.read_text())
    out = results_path.parent
    subject = results.get("subject", "ernie")
    from tit.paths import get_path_manager
    try:
        m2m = str(Path(get_path_manager().m2m(subject)))
    except Exception:
        m2m = None

    fig_progress(results, out / "progress.png")
    fig_roc(results, out / "roc.png")
    fig_distributions(results, out / "distributions.png")
    fig_summary(results, out / "summary.png")

    import simnibs
    for c in results["cells"]:
        key = f"{c.get('target')}_{c.get('arm')}"
        meshes_paths = [p for p in (c.get("final_meshes") or []) if Path(p).is_file()][:2]
        # field on T1 with ROI contour
        if meshes_paths and m2m and c.get("roi"):
            r = c["roi"]
            try:
                t1_overlay.render_overlay_from_meshes(
                    meshes_paths, [r["x"], r["y"], r["z"]], r.get("radius", 8.0),
                    m2m, str(out / f"t1_{key}.png"),
                    f"{c['target']} · {c.get('arm_label','')}")
            except Exception as exc:
                print(f"  t1 overlay failed {key}: {exc!r}")
        # electrodes on scalp
        if meshes_paths:
            try:
                loaded = [simnibs.read_msh(p) for p in meshes_paths]
                fig_scalp(c, loaded, out / f"scalp_{key}.png")
                del loaded
            except Exception as exc:
                print(f"  scalp failed {key}: {exc!r}")
    print(f"Wrote panels to {out}")


if __name__ == "__main__":
    main()
