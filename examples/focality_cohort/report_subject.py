#!/usr/bin/env simnibs_python
"""Single-subject report for the cohort focality study.

Renders whatever cells have completed for one subject: a metrics table (all
arms × targets), per-target ROC curves and ROI/non-ROI distributions, and
field-on-T1 overlays with the **atlas ROI contour** (the real anatomical region).

Usage:
    PROJECT_DIR=/Volumes/IDO2/000_TISSR simnibs_python report_subject.py <sub_dir> [out.html]
"""
import base64
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

ARM_ORDER = ["roc_lo", "roc_hi", "auc", "tail", "composite"]
ARM_COLOR = {"roc_lo": "#e08a2e", "roc_hi": "#b11226", "auc": "#7b2cbf",
             "tail": "#0353a4", "composite": "#2a9d8f"}
PROJECT = os.environ.get("PROJECT_DIR", "/Volumes/IDO2/000_TISSR")
FS_ATLAS = (PROJECT + "/derivatives/freesurfer/sub-{s}/mri/"
            "aparc.DKTatlas+aseg_resampled_240x512x512.mgz")
M2M = PROJECT + "/derivatives/SimNIBS/sub-{s}/m2m_{s}"


def roc_curve(e1, e2, n=200):
    emax = max(float(e1.max()), float(e2.max()), 1e-12)
    thr = np.linspace(0, emax, n)
    s = np.array([(e1 >= t).mean() for t in thr]); f = np.array([(e2 >= t).mean() for t in thr])
    o = np.argsort(f); tz = getattr(np, "trapezoid", np.trapz)
    return f[o], s[o], float(tz(s[o], f[o]))


def fields(cell):
    p = cell.get("arrays_npz")
    if not p or not Path(p).is_file():
        return None, None
    z = np.load(p); return z["e_roi"], z["e_nonroi"]


def fig_roc(cells_by_arm, target, path):
    fig, ax = plt.subplots(figsize=(5.6, 5.2), constrained_layout=True)
    ax.plot([0, 1], [0, 1], "k--", lw=0.8, alpha=0.5)
    for arm in ARM_ORDER:
        c = cells_by_arm.get(arm)
        if not c:
            continue
        e1, e2 = fields(c)
        if e1 is None:
            continue
        f, s, auc = roc_curve(e1, e2)
        ax.plot(f, s, "-", lw=2, color=ARM_COLOR[arm], label=f"{c['arm_label']} — AUC {auc:.3f}")
    ax.set_title(f"{target} — ROC", fontweight="bold")
    ax.set_xlabel("1 − specificity (non-ROI ≥ thr)"); ax.set_ylabel("sensitivity (ROI ≥ thr)")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=130); plt.close(fig)


def fig_dist(cells_by_arm, target, path):
    arms = [a for a in ARM_ORDER if cells_by_arm.get(a) and fields(cells_by_arm[a])[0] is not None]
    if not arms:
        return False
    fig, axes = plt.subplots(1, len(arms), figsize=(2.9 * len(arms), 3.2),
                             constrained_layout=True, squeeze=False)
    for ax, arm in zip(axes[0], arms):
        e1, e2 = fields(cells_by_arm[arm])
        hi = max(float(np.percentile(e1, 99)), float(np.percentile(e2, 99)), 1e-6)
        b = np.linspace(0, hi, 45)
        ax.hist(e2, bins=b, density=True, color="#8d99ae", alpha=0.6, label="non-ROI")
        ax.hist(e1, bins=b, density=True, color=ARM_COLOR[arm], alpha=0.75, label="ROI")
        ax.set_title(cells_by_arm[arm]["arm_label"], fontsize=8)
        ax.set_xlabel("TI (V/m)"); ax.legend(fontsize=6.5); ax.grid(True, alpha=0.3)
    fig.suptitle(f"{target} — ROI vs non-ROI field distributions", fontweight="bold", fontsize=10)
    fig.savefig(path, dpi=130); plt.close(fig)
    return True


def b64(p):
    return ("data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()
            ) if Path(p).is_file() else None


def img(p, cap=""):
    s = b64(p); return f'<figure class="dark"><img src="{s}"><figcaption>{cap}</figcaption></figure>' if s else ""


def main():
    sub_dir = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else sub_dir / "report.html"
    subj = sub_dir.name.replace("sub-", "")
    cells = json.loads((sub_dir / "metrics.json").read_text())
    done = [c for c in cells if c.get("metrics")]
    targets = []
    for c in done:
        if c["target"] not in targets:
            targets.append(c["target"])

    # metrics table
    rows = ""
    for t in targets:
        for arm in ARM_ORDER:
            c = next((x for x in done if x["target"] == t and x["arm"] == arm), None)
            if not c:
                continue
            m = c["metrics"]
            rows += (f"<tr><td>{t}</td><td style='color:{ARM_COLOR[arm]};font-weight:600'>{c['arm_label']}</td>"
                     f"<td class='num'>{m['focality_ratio']:.2f}</td><td class='num'>{m['roi_mean']:.3f}</td>"
                     f"<td class='num'>{m['nonroi_mean']:.3f}</td><td class='num'>{m['composite']:.3f}</td>"
                     f"<td class='num'>{m['auc']:.3f}</td><td class='num'>{m['roc_distance']:.3f}</td>"
                     f"<td class='num'>{m['v_off_pct']:.1f}</td></tr>")

    # per-target figures
    sections = ""
    atlas = FS_ATLAS.format(s=subj); m2m = M2M.format(s=subj)
    for t in targets:
        cba = {c["arm"]: c for c in done if c["target"] == t}
        fig_roc(cba, t, sub_dir / f"_roc_{t}.png")
        fig_dist(cba, t, sub_dir / f"_dist_{t}.png")
        overlays = ""
        for arm in ARM_ORDER:
            c = cba.get(arm)
            if not c or not c.get("final_meshes"):
                continue
            png = sub_dir / f"_t1_{t}_{arm}.png"
            try:
                if t1_overlay.render_overlay_atlas(c["final_meshes"], atlas, c["atlas_label"],
                                                   m2m, str(png), f"{t} · {c['arm_label']}"):
                    overlays += img(png)
            except Exception as exc:
                print(f"  overlay failed {t}/{arm}: {exc!r}")
        sections += (f"<h2>{t}</h2><div class='row'>{img(sub_dir/f'_roc_{t}.png')}"
                     f"{img(sub_dir/f'_dist_{t}.png')}</div>"
                     f"<h3>Field on T1 (green contour = atlas ROI)</h3>{overlays}")

    pending = 15 - len(done)
    html = f"""<style>
:root{{--g:#f6f7f9;--p:#fff;--ink:#1a1f2b;--mut:#5a6472;--line:#e2e6ec;--acc:#0f766e}}
@media(prefers-color-scheme:dark){{:root{{--g:#0f1319;--p:#161b23;--ink:#e6e9ef;--mut:#98a2b3;--line:#262d38;--acc:#4fd1c5}}}}
:root[data-theme=dark]{{--g:#0f1319;--p:#161b23;--ink:#e6e9ef;--mut:#98a2b3;--line:#262d38;--acc:#4fd1c5}}
:root[data-theme=light]{{--g:#f6f7f9;--p:#fff;--ink:#1a1f2b;--mut:#5a6472;--line:#e2e6ec;--acc:#0f766e}}
*{{box-sizing:border-box}}.wrap{{max-width:1040px;margin:0 auto;padding:2.2rem 1.2rem 4rem;background:var(--g);color:var(--ink);font-family:ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5}}
h1{{font-size:1.6rem;margin:.2rem 0 .4rem}}h2{{font-size:1.2rem;margin:2.2rem 0 .8rem;border-bottom:1px solid var(--line);padding-bottom:.3rem}}h3{{font-size:1rem;color:var(--mut);margin:1.4rem 0 .6rem}}
.eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:.72rem;font-weight:600;color:var(--acc)}}
.lede{{color:var(--mut)}} .status{{margin:1rem 0;padding:.7rem 1rem;border:1px solid var(--line);border-left:3px solid var(--acc);border-radius:8px;background:var(--p);font-size:.9rem}}
table{{width:100%;border-collapse:collapse;margin:1rem 0;font-size:.86rem}}th,td{{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--line)}}th{{color:var(--mut);font-size:.72rem;text-transform:uppercase;letter-spacing:.04em}}
.num{{font-family:ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}}
.row{{display:flex;flex-wrap:wrap;gap:1rem}}.row figure{{flex:1;min-width:320px}}
figure{{margin:0 0 1rem;background:var(--p);border:1px solid var(--line);border-radius:10px;padding:.6rem}}figure.dark{{background:#0d0d0f}}figure img{{display:block;width:100%;border-radius:6px}}figcaption{{color:var(--mut);font-size:.8rem;margin-top:.4rem}}
.foot{{margin-top:2.5rem;color:var(--mut);font-size:.8rem;border-top:1px solid var(--line);padding-top:1rem}}code{{font-family:ui-monospace,Menlo,monospace;font-size:.85em;background:var(--p);border:1px solid var(--line);padding:.05rem .3rem;border-radius:4px}}
</style>
<div class="wrap">
<p class="eyebrow">TI-Toolbox · cohort focality study</p>
<h1>Subject <code>{subj}</code> — 5 focality objectives on atlas targets</h1>
<p class="lede">Five flex-search objectives (two ROC thresholds, direct-AUC, tail, composite)
on anatomical atlas ROIs at SimNIBS default budget, Ø8 mm electrodes, 2 mA. Metrics are
measured on each optimized montage's exact ROI/non-ROI fields.</p>
<div class="status">{len(done)}/15 cells complete{f' — {pending} still running (thalamus/insula fill in as they finish)' if pending else ''}.</div>
<h2>Metrics</h2>
<table><thead><tr><th>Target</th><th>Arm</th><th>Focality<br>ROI/nonROI</th><th>ROI mean</th>
<th>non-ROI mean</th><th>Composite</th><th>AUC</th><th>ROC-dist<br>(Weise)</th><th>V_off%<br>(Ghanem)</th></tr></thead>
<tbody>{rows}</tbody></table>
{sections}
<p class="foot">Real flex-search runs, subject {subj}. Field/electrodes from flex-output meshes;
ROI contour is the DKT atlas region ({', '.join(targets)}). AUC/ROC-distance/V_off use the exact
optimized-montage fields.</p>
</div>"""
    out.write_text(html)
    print("wrote", out)


if __name__ == "__main__":
    main()
