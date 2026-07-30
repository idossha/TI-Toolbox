#!/usr/bin/env simnibs_python
"""Assemble the 3-arm focality report into a self-contained HTML page.

Reads results.json + the PNG panels (from make_report.py) and embeds them, with
per-figure explanations, an objective-functions methods box, and per-condition
metrics. Emits an Artifact-ready HTML body (no doctype/head/body wrappers).

Usage:  simnibs_python make_artifact.py <results_dir> <out.html>
"""
import base64
import json
import sys
from pathlib import Path

import numpy as np

RES = Path(sys.argv[1])
OUT = Path(sys.argv[2])
d = json.loads((RES / "results.json").read_text())
cells = d.get("cells", [])
ARMS = ["roc_lo", "roc_hi", "integral"]
ARM_COLOR = {"roc_lo": "#e08a2e", "roc_hi": "#b11226", "integral": "#0353a4"}


def targets():
    out = []
    for c in cells:
        if c.get("target") not in out:
            out.append(c.get("target"))
    return out


def cell(t, a):
    return next((c for c in cells if c.get("target") == t and c.get("arm") == a), {})


def label(a):
    return next((c["arm_label"] for c in cells if c.get("arm") == a and c.get("arm_label")), a)


def auc_ratio(c):
    p = c.get("arrays_npz")
    if not p or not Path(p).is_file():
        return None, None
    z = np.load(p); e1, e2 = z["e_roi"], z["e_nonroi"]
    emax = max(float(e1.max()), float(e2.max()), 1e-12)
    thr = np.linspace(0, emax, 200)
    s = np.array([(e1 >= t).mean() for t in thr]); f = np.array([(e2 >= t).mean() for t in thr])
    o = np.argsort(f); tz = getattr(np, "trapezoid", np.trapz)
    return float(tz(s[o], f[o])), float(e1.mean()) / max(float(e2.mean()), 1e-9)


def b64(name):
    p = RES / name
    return ("data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()) if p.is_file() else None


def fig(name, caption, dark=False):
    src = b64(name)
    if not src:
        return ""
    cls = ' class="dark"' if dark else ""
    return f'<figure{cls}><img src="{src}" alt="{name}"><figcaption>{caption}</figcaption></figure>'


metrics = {(c.get("target"), c.get("arm")): auc_ratio(c) for c in cells}


def m(t, a, i):
    v = metrics.get((t, a))
    return v[i] if v and v[i] is not None else None


# metrics table
rows = ""
for t in targets():
    for a in ARMS:
        c = cell(t, a)
        if not c:
            continue
        auc, ratio = metrics.get((t, a), (None, None))
        thr = c.get("thresholds") or "—"
        rows += (f"<tr><td>{t}</td><td style='color:{ARM_COLOR[a]};font-weight:600'>{label(a)}</td>"
                 f"<td class='num'>{thr}</td><td class='num'>{c.get('n_evaluations','–')}</td>"
                 f"<td class='num'>{('%.3f'%auc) if auc is not None else '–'}</td>"
                 f"<td class='num'>{('%.2f'%ratio) if ratio is not None else '–'}</td></tr>")

done = [c for c in cells if c.get("n_evaluations")]
status = ("All six conditions complete." if len(done) >= 6
          else f"{len(done)} of 6 conditions complete — run still in progress.")

# comparative panels with explanatory captions
comparative = "".join([
    fig("progress.png",
        "<b>How it's made:</b> after every field evaluation we record the mean-field "
        "ROI/non-ROI ratio of the montage the search currently considers best, and plot it "
        "vs evaluation number. Because the two objectives use different numeric scales "
        "(see Methods), this shared ratio is what makes the arms comparable. <b>Read it as:</b> "
        "higher = more focal; a curve that climbs sooner converged faster."),
    fig("roc.png",
        "<b>How it's made:</b> sweeping a field threshold, sensitivity = fraction of ROI "
        "nodes above it, 1−specificity = fraction of non-ROI nodes above it; the curve traces "
        "the pair as the threshold varies (SimNIBS's AUC measure), on the optimized montage's "
        "exact fields. <b>Read it as:</b> a curve bowed toward the top-left (higher AUC) means "
        "the ROI stays hotter than the rest of the brain across thresholds — more focal."),
    fig("distributions.png",
        "<b>How it's made:</b> histograms of the TI-field magnitude over ROI nodes (colored) "
        "and non-ROI nodes (grey) for the optimized montage. <b>Read it as:</b> the further the "
        "ROI distribution sits to the right of the non-ROI, the more the field concentrates on target."),
    fig("summary.png",
        "<b>How it's made:</b> the best mean ROI/non-ROI field ratio each arm reached. "
        "<b>Read it as:</b> taller = more focal contrast achieved."),
])

# per-condition renders
detail = ""
for t in targets():
    detail += f"<h3>{t} target</h3><div class='conds'>"
    for a in ARMS:
        c = cell(t, a)
        key = f"{t}_{a}"
        t1 = fig(f"t1_{key}.png", "", dark=True)
        sc = fig(f"scalp_{key}.png", "")
        if t1 or sc:
            detail += (f"<div class='cond'><h4 style='color:{ARM_COLOR[a]}'>{label(a)}</h4>{t1}{sc}</div>")
    detail += "</div>"

html = f"""<style>
:root {{ --ground:#f6f7f9; --panel:#fff; --ink:#1a1f2b; --muted:#5a6472; --line:#e2e6ec; --accent:#0f766e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --ground:#0f1319; --panel:#161b23; --ink:#e6e9ef; --muted:#98a2b3; --line:#262d38; --accent:#4fd1c5; }} }}
:root[data-theme="light"] {{ --ground:#f6f7f9; --panel:#fff; --ink:#1a1f2b; --muted:#5a6472; --line:#e2e6ec; --accent:#0f766e; }}
:root[data-theme="dark"] {{ --ground:#0f1319; --panel:#161b23; --ink:#e6e9ef; --muted:#98a2b3; --line:#262d38; --accent:#4fd1c5; }}
* {{ box-sizing:border-box; }}
.wrap {{ max-width:1040px; margin:0 auto; padding:2.4rem 1.2rem 4rem; background:var(--ground); color:var(--ink); font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; line-height:1.55; }}
.eyebrow {{ text-transform:uppercase; letter-spacing:.12em; font-size:.72rem; font-weight:600; color:var(--accent); margin:0 0 .3rem; }}
h1 {{ font-size:1.9rem; line-height:1.15; margin:.1rem 0 .5rem; text-wrap:balance; }}
h2 {{ font-size:1.25rem; margin:2.6rem 0 1rem; padding-bottom:.35rem; border-bottom:1px solid var(--line); }}
h3 {{ font-size:1.08rem; margin:1.8rem 0 .7rem; }} h4 {{ margin:0 0 .5rem; font-size:.95rem; }}
.lede {{ color:var(--muted); max-width:66ch; }}
.meta {{ display:flex; flex-wrap:wrap; gap:.5rem; margin:1.1rem 0 0; }}
.chip {{ font-family:ui-monospace,Menlo,monospace; font-size:.75rem; padding:.25rem .6rem; border:1px solid var(--line); border-radius:999px; background:var(--panel); color:var(--muted); }}
.status {{ margin:1.3rem 0 0; padding:.7rem 1rem; border-radius:10px; border:1px solid var(--line); border-left:3px solid var(--accent); background:var(--panel); font-size:.92rem; }}
.box {{ margin:1.4rem 0 0; padding:1rem 1.2rem; border-radius:12px; border:1px solid var(--line); background:var(--panel); }}
.box h2 {{ margin:0 0 .5rem; border:0; font-size:1.05rem; }}
.box p {{ margin:.5rem 0; font-size:.9rem; color:var(--muted); }}
.box b {{ color:var(--ink); }}
figure {{ margin:0 0 1.1rem; background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:.7rem; }}
figure.dark {{ background:#0d0d0f; }}
figure img {{ display:block; width:100%; height:auto; border-radius:6px; }}
figcaption {{ color:var(--muted); font-size:.85rem; margin-top:.55rem; }}
.conds {{ display:grid; grid-template-columns:1fr; gap:1rem; }}
.cond {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:.9rem; }}
.cond figure {{ border:0; padding:0; margin:.5rem 0 0; }} .cond figure.dark {{ padding:.3rem; border-radius:8px; }}
table {{ width:100%; border-collapse:collapse; margin-top:1rem; font-size:.9rem; }}
th,td {{ text-align:left; padding:.45rem .7rem; border-bottom:1px solid var(--line); }}
th {{ color:var(--muted); font-weight:600; font-size:.76rem; text-transform:uppercase; letter-spacing:.05em; }}
.num {{ font-family:ui-monospace,Menlo,monospace; font-variant-numeric:tabular-nums; }}
.foot {{ margin-top:3rem; color:var(--muted); font-size:.8rem; border-top:1px solid var(--line); padding-top:1rem; }}
code {{ font-family:ui-monospace,Menlo,monospace; font-size:.85em; background:var(--panel); border:1px solid var(--line); padding:.05rem .35rem; border-radius:4px; }}
</style>
<div class="wrap">
  <p class="eyebrow">TI-Toolbox · flex-search focality</p>
  <h1>Three-arm focality comparison on deep targets (<code>{d.get('subject','ernie')}</code>)</h1>
  <p class="lede">For a thalamus and a hippocampus target, flex-search optimized electrode
  placement under three arms — ROC focality at two thresholds and threshold-free integral
  focality — at SimNIBS's default optimizer budget. Metrics are measured on each optimized
  montage's exact ROI/non-ROI fields.</p>
  <div class="meta">
    <span class="chip">SimNIBS default: popsize 13 · maxiter 1000 · tol 0.1</span>
    <span class="chip">2 mA · max_TI</span>
    <span class="chip">SimNIBS 4.6 · ernie</span>
  </div>
  <div class="status">{status}</div>

  <div class="box"><h2>Methods — the three arms &amp; the two objectives</h2>
    <p><b>Arms.</b> <span style="color:{ARM_COLOR['roc_lo']}">ROC (0.1/0.2&nbsp;V/m)</span> and
    <span style="color:{ARM_COLOR['roc_hi']}">ROC (0.2/0.4&nbsp;V/m)</span> are SimNIBS's
    threshold-based focality at a conservative and an aggressive threshold pair
    (non-ROI&nbsp;max, ROI&nbsp;min); <span style="color:{ARM_COLOR['integral']}">Integral</span>
    is threshold-free. The two ROC arms show how much the result depends on a threshold the user
    must pick — the pitfall integral focality sidesteps.</p>
    <p><b>Objective functions live on different scales</b> (which is why the progress plot uses a
    shared ratio, not the raw objective):</p>
    <p style="margin-left:1rem"><b>ROC arm</b> minimizes <code>−100·(√2 − d)</code>, where
    <code>d</code> is the Euclidean distance of the montage's (1−specificity, sensitivity)
    operating point to the ideal corner (0, 1) at the chosen thresholds. Range ≈ [−141, 0];
    more negative = better.</p>
    <p style="margin-left:1rem"><b>Integral arm</b> minimizes <code>−IF</code>, with
    <code>IF = (mean&nbsp;E<sub>ROI</sub> / V<sub>ROI</sub>) / √(mean&nbsp;E<sub>non-ROI</sub> /
    V<sub>non-ROI</sub>)</code> (Fernández-Corazza 2020, eq. 14). Range ≈ [−5, 0]; more negative = better.</p>
    <p><b>Common yardstick.</b> Because those numbers aren't comparable, every cross-arm plot uses
    the mean-field <b>ROI/non-ROI contrast</b> and the ROC <b>AUC</b>, both computed on the same
    optimized-montage fields for all arms.</p>
  </div>

  <h2>Focality metrics</h2>
  <table><thead><tr><th>Target</th><th>Arm</th><th>Thresholds (V/m)</th><th>Valid evals</th>
    <th>AUC</th><th>Mean ROI/non-ROI</th></tr></thead><tbody>{rows}</tbody></table>

  <h2>Comparative panels</h2>
  {comparative}

  <h2>Per-condition: field on the T1 &amp; electrodes on the scalp</h2>
  <p class="lede" style="margin-bottom:.4rem">TI_max field (Grossman envelope of the two channels)
  scattered onto the subject T1; the <b>white contour marks the target ROI</b>. Electrodes are the
  four optimized channel centres read from the flex-output mesh.</p>
  {detail}

  <p class="foot">Generated from real flex-search runs on the SimNIBS <code>ernie</code> head model.
  Fields, electrode coordinates, and the on-T1 render come from the automatic flex-output meshes;
  ROC/AUC and distributions use each optimized montage's exact ROI/non-ROI fields.</p>
</div>
"""
OUT.write_text(html)
print("wrote", OUT, f"({len(html)} chars)")
