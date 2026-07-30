#!/usr/bin/env simnibs_python
"""Render the deep-vs-superficial focality comparison report.

Reads ``results.json`` (+ per-cell ``fields.npz`` and final-simulation meshes)
produced by :mod:`run_comparison` and writes a set of PNG panels plus a
self-contained ``report.html`` beside it:

* ``progress.png``       -- DE best-so-far convergence per condition.
* ``roc.png``            -- ROC curves (Weise-style), superficial vs deep.
* ``distributions.png``  -- ROI vs non-ROI field histograms (Fernandez-Corazza).
* ``summary.png``        -- best focality / objective across conditions.
* ``field_<cell>.png``   -- TI-field distribution on the cortex (if mesh present).
* ``scalp_<cell>.png``   -- optimized electrode positions on the scalp.

Usage
-----
    simnibs_python make_report.py [results.json]
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEPTHS = ["superficial", "deep"]
GOALS = ["focality", "focality_integral"]
GOAL_LABEL = {"focality": "ROC (threshold)", "focality_integral": "Integral (threshold-free)"}
GOAL_COLOR = {"focality": "#c1121f", "focality_integral": "#0353a4"}


# --------------------------------------------------------------------------
# data access
# --------------------------------------------------------------------------
def _cell(results, depth, goal):
    for c in results["cells"]:
        if c.get("depth") == depth and c.get("goal") == goal:
            return c
    return {}


def _load_fields(cell):
    p = cell.get("arrays_npz")
    if not p or not Path(p).is_file():
        return None, None
    z = np.load(p)
    return z["e_roi"], z["e_nonroi"]


def _best_so_far(traj):
    out, cur = [], float("inf")
    for v in traj:
        cur = min(cur, v)
        out.append(cur)
    return out


def _roc_curve(e1, e2, n=200):
    """Sensitivity vs 1-specificity over a threshold sweep (Weise/SimNIBS AUC)."""
    emax = max(float(np.max(e1)), float(np.max(e2)), 1e-12)
    thr = np.linspace(0.0, emax, n)
    sens = np.array([(e1 >= t).mean() for t in thr])
    fpr = np.array([(e2 >= t).mean() for t in thr])  # 1 - specificity
    order = np.argsort(fpr)
    fpr, sens = fpr[order], sens[order]
    trapz = getattr(np, "trapezoid", np.trapz)
    auc = float(trapz(sens, fpr))
    return fpr, sens, auc


# --------------------------------------------------------------------------
# array-based panels
# --------------------------------------------------------------------------
def fig_progress(results, path):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
    fig.suptitle("Differential-evolution progress (best objective so far)",
                 fontweight="bold")
    for i, depth in enumerate(DEPTHS):
        for j, goal in enumerate(GOALS):
            ax = axes[i][j]
            c = _cell(results, depth, goal)
            traj = c.get("trajectory", [])
            if traj:
                bsf = _best_so_far(traj)
                ax.plot(range(1, len(traj) + 1), traj, ".", ms=3, alpha=0.35,
                        color=GOAL_COLOR[goal], label="candidate")
                ax.plot(range(1, len(bsf) + 1), bsf, "-", lw=2,
                        color=GOAL_COLOR[goal], label="best so far")
                sp = max(traj) - min(traj)
                ax.set_title(f"{depth} x {GOAL_LABEL[goal]}   (spread={sp:.3g})",
                             fontsize=10)
                if sp < 1e-6:
                    ax.text(0.5, 0.5, "FLAT — no gradient", transform=ax.transAxes,
                            ha="center", va="center", color="crimson",
                            fontsize=13, fontweight="bold", alpha=0.7)
                ax.legend(fontsize=8)
            else:
                ax.set_title(f"{depth} x {GOAL_LABEL[goal]} (no data)", fontsize=10)
            ax.set_xlabel("valid evaluation #")
            ax.set_ylabel("objective (minimized)")
            ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_roc(results, path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), constrained_layout=True)
    fig.suptitle("ROC of the optimized montage (Weise-style): "
                 "ROI sensitivity vs non-ROI 1-specificity", fontweight="bold")
    for k, depth in enumerate(DEPTHS):
        ax = axes[k]
        ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.5)
        for goal in GOALS:
            e1, e2 = _load_fields(_cell(results, depth, goal))
            if e1 is None:
                continue
            fpr, sens, auc = _roc_curve(e1, e2)
            ax.plot(fpr, sens, "-", lw=2, color=GOAL_COLOR[goal],
                    label=f"{GOAL_LABEL[goal]} (AUC={auc:.3f})")
        ax.set_title(f"{depth} target", fontsize=11)
        ax.set_xlabel("1 - specificity (non-ROI above threshold)")
        ax.set_ylabel("sensitivity (ROI above threshold)")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        if ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_distributions(results, path):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
    fig.suptitle("Field distributions of the optimized montage "
                 "(ROI vs non-ROI, Fernandez-Corazza-style)", fontweight="bold")
    for i, depth in enumerate(DEPTHS):
        for j, goal in enumerate(GOALS):
            ax = axes[i][j]
            e1, e2 = _load_fields(_cell(results, depth, goal))
            if e1 is None:
                ax.set_title(f"{depth} x {GOAL_LABEL[goal]} (no data)", fontsize=10)
                continue
            hi = max(float(np.percentile(e1, 99)), float(np.percentile(e2, 99)), 1e-6)
            bins = np.linspace(0, hi, 60)
            ax.hist(e2, bins=bins, density=True, color="#8d99ae", alpha=0.6,
                    label="non-ROI")
            ax.hist(e1, bins=bins, density=True, color=GOAL_COLOR[goal], alpha=0.7,
                    label="ROI")
            ax.axvline(np.mean(e1), color=GOAL_COLOR[goal], ls="--", lw=1.2)
            ax.axvline(np.mean(e2), color="#8d99ae", ls="--", lw=1.2)
            ratio = float(np.mean(e1)) / max(float(np.mean(e2)), 1e-9)
            ax.set_title(f"{depth} x {GOAL_LABEL[goal]}   "
                         f"(mean ROI/non-ROI={ratio:.2f})", fontsize=9.5)
            ax.set_xlabel("TI field (V/m)"); ax.set_ylabel("density")
            ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def fig_summary(results, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), constrained_layout=True)
    x = np.arange(len(DEPTHS)); w = 0.36
    # Left: integral focality achieved (mean ROI / mean non-ROI) per goal.
    ax = axes[0]
    for gi, goal in enumerate(GOALS):
        vals = []
        for depth in DEPTHS:
            e1, e2 = _load_fields(_cell(results, depth, goal))
            vals.append(float(np.mean(e1)) / max(float(np.mean(e2)), 1e-9)
                        if e1 is not None else 0.0)
        ax.bar(x + (gi - 0.5) * w, vals, w, color=GOAL_COLOR[goal],
               label=GOAL_LABEL[goal])
    ax.set_xticks(x); ax.set_xticklabels(DEPTHS)
    ax.set_ylabel("mean ROI / mean non-ROI"); ax.set_title("Focality contrast achieved")
    ax.legend(fontsize=9); ax.grid(True, axis="y", alpha=0.3)
    # Right: best objective value (as returned) per goal — different scales, so
    # annotate rather than compare heights across goals.
    ax = axes[1]
    for gi, goal in enumerate(GOALS):
        vals = [(_cell(results, d, goal).get("best_value") or 0.0) for d in DEPTHS]
        bars = ax.bar(x + (gi - 0.5) * w, vals, w, color=GOAL_COLOR[goal],
                      label=GOAL_LABEL[goal])
        for b, v in zip(bars, vals):
            ax.annotate(f"{v:.2f}", (b.get_x() + b.get_width() / 2, v),
                        ha="center", va="bottom" if v >= 0 else "top", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(DEPTHS)
    ax.set_ylabel("best objective (minimized)")
    ax.set_title("Best objective (per-goal scale)")
    ax.legend(fontsize=9); ax.grid(True, axis="y", alpha=0.3)
    fig.savefig(path, dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------
# mesh-based panels (field distribution + electrodes on scalp)
# --------------------------------------------------------------------------
# Tissue tags kept when combining channels (mirrors tit/sim/TI.py); excludes
# electrode tags (100/500/2100...), aligning the two channel meshes.
try:
    from tit import constants as _const
    _TAGS_KEEP = np.hstack([np.arange(lo, hi) for lo, hi in _const.BRAIN_TISSUE_TAG_RANGES])
except Exception:
    _TAGS_KEEP = np.hstack([np.arange(1, 100), np.arange(1001, 1100)])


def _project_views():
    # (title, x-index, y-index, view-mask-fn)
    return [
        ("top (x-y)", 0, 1, lambda p: np.ones(len(p), bool)),
        ("left (y-z)", 1, 2, lambda p: p[:, 0] <= 0),
        ("front (x-z)", 0, 2, lambda p: p[:, 1] >= 0),
    ]


def _load_channels(cell):
    """Load the two per-channel final-simulation meshes (raw)."""
    paths = cell.get("final_meshes") or []
    paths = [p for p in paths if Path(p).is_file()][:2]
    if len(paths) < 2:
        return []
    import simnibs
    return [simnibs.read_msh(p) for p in paths]


def _electrode_centroids(meshes):
    """Cartesian electrode centres from the gel tags (500-599) of each channel."""
    pts = []
    for m in meshes:
        bary = m.elements_baricenters().value
        for t in sorted(set(m.elm.tag1.tolist())):
            if 500 <= t < 600:
                pts.append(bary[m.elm.tag1 == t].mean(axis=0))
    return np.array(pts) if pts else None


def fig_field(cell, meshes, path):
    """TI-field distribution on gray matter, combined from the two channels."""
    if len(meshes) < 2:
        return False
    from simnibs.utils import TI_utils
    m1 = meshes[0].crop_mesh(tags=_TAGS_KEEP)
    m2 = meshes[1].crop_mesh(tags=_TAGS_KEEP)
    ti = np.asarray(TI_utils.get_maxTI(m1.field["E"].value, m2.field["E"].value)).ravel()
    gm = m1.elm.tag1 == 2  # gray-matter volume
    if not gm.any():
        gm = np.ones(m1.elm.nr, bool)
    centers = m1.elements_baricenters().value[gm]
    vals = ti[gm]
    if centers.shape[0] > 60000:
        idx = np.linspace(0, centers.shape[0] - 1, 60000).astype(int)
        centers, vals = centers[idx], vals[idx]
    vmax = float(np.percentile(vals, 99)) or 1.0
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), constrained_layout=True)
    fig.suptitle(f"TI field on gray matter (V/m) — {cell['depth']} x "
                 f"{GOAL_LABEL[cell['goal']]}", fontweight="bold")
    sc = None
    for ax, (title, xi, yi, mfn) in zip(axes, _project_views()):
        vm = mfn(centers)
        sc = ax.scatter(centers[vm, xi], centers[vm, yi], c=vals[vm], s=1.5,
                        cmap="hot", vmin=0, vmax=vmax, rasterized=True)
        ax.set_title(title, fontsize=10); ax.set_aspect("equal"); ax.axis("off")
    fig.colorbar(sc, ax=axes.ravel().tolist(), shrink=0.7, label="TI_max (V/m)")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return True


def fig_scalp(cell, meshes, path):
    """Optimized electrode positions on the scalp (from the flex output mesh)."""
    if not meshes:
        return False
    skin = meshes[0].crop_mesh(tags=[1005])
    pts = skin.nodes.node_coord
    if pts.shape[0] > 80000:
        idx = np.linspace(0, pts.shape[0] - 1, 80000).astype(int)
        pts = pts[idx]
    epos = _electrode_centroids(meshes)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), constrained_layout=True)
    fig.suptitle(f"Optimized electrodes on scalp — {cell['depth']} x "
                 f"{GOAL_LABEL[cell['goal']]}", fontweight="bold")
    for ax, (title, xi, yi, mfn) in zip(axes, _project_views()):
        vm = mfn(pts)
        ax.scatter(pts[vm, xi], pts[vm, yi], c="#cbd5e1", s=0.4, alpha=0.6,
                   rasterized=True)
        if epos is not None and epos.size:
            evm = mfn(epos)
            ax.scatter(epos[evm, xi], epos[evm, yi], c="#d00000", s=110,
                       edgecolors="k", linewidths=0.7, zorder=5)
        ax.set_title(title, fontsize=10); ax.set_aspect("equal"); ax.axis("off")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return True


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------
def _img(path: Path) -> str:
    if not path.is_file():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b64}" alt="{path.stem}">'


def main() -> None:
    results_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results.json")
    results = json.loads(results_path.read_text())
    out = results_path.parent
    subject = results.get("subject", "?")

    fig_progress(results, out / "progress.png")
    fig_roc(results, out / "roc.png")
    fig_distributions(results, out / "distributions.png")
    fig_summary(results, out / "summary.png")

    # mesh-based renders (best-effort; skipped if a cell's meshes are missing).
    # Load each cell's two channel meshes once and reuse for both panels.
    field_imgs, scalp_imgs = [], []
    for c in results["cells"]:
        key = f"{c.get('depth')}_{c.get('goal')}"
        try:
            meshes = _load_channels(c)
        except Exception as exc:
            print(f"  mesh load failed for {key}: {exc!r}")
            meshes = []
        if not meshes:
            continue
        fp = out / f"field_{key}.png"
        if fig_field(c, meshes, fp):
            field_imgs.append(fp)
        sp = out / f"scalp_{key}.png"
        if fig_scalp(c, meshes, sp):
            scalp_imgs.append(sp)
        del meshes  # free before the next cell

    sections = [
        ("Optimization progress", "progress.png"),
        ("ROC curves (Weise-style)", "roc.png"),
        ("Field distributions (Fernandez-Corazza-style)", "distributions.png"),
        ("Summary", "summary.png"),
    ]
    body = []
    for title, png in sections:
        body.append(f"<h2>{title}</h2>\n{_img(out / png)}")
    if field_imgs:
        body.append("<h2>TI field distribution</h2>\n"
                    + "\n".join(_img(p) for p in field_imgs))
    if scalp_imgs:
        body.append("<h2>Electrode positions on scalp</h2>\n"
                    + "\n".join(_img(p) for p in scalp_imgs))

    html = f"""<!doctype html><meta charset="utf-8">
<title>Integral vs ROC focality — {subject}</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1040px;margin:2rem auto;padding:0 1rem;line-height:1.5}}
 img{{max-width:100%;border:1px solid #ddd;border-radius:6px;margin:.4rem 0}}
 h2{{border-bottom:1px solid #eee;padding-bottom:.2rem;margin-top:2rem}}
 code{{background:#f4f4f4;padding:.1rem .3rem;border-radius:3px}}
</style>
<h1>Deep vs superficial focality: integral vs ROC ({subject})</h1>
<p>Budget: {results.get('budget')}. Each condition optimizes electrode placement
for a {DEPTHS[0]} and a {DEPTHS[1]} target using the ROC (threshold-based) and the
integral (threshold-free) focality goals.</p>
{''.join(body)}
<p style="color:#666;font-size:.85rem">Generated by
<code>examples/focality_integral_ernie/make_report.py</code>.</p>
"""
    (out / "report.html").write_text(html)
    print(f"Wrote {out/'report.html'} and PNG panels")


if __name__ == "__main__":
    main()
