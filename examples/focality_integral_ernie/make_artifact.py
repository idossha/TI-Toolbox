#!/usr/bin/env simnibs_python
"""Assemble the focality study into a self-contained HTML report (arm-agnostic).

Works for the 3-arm comparison and the improved-integral variant study. Computes
per-condition AUC, achieved ROI intensity, and the non-ROI hotspot (p95) — the
held-out metrics that expose focality/intensity/safety tradeoffs — embeds the PNG
panels, and adds per-figure explanations + an objectives methods box.

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
_PALETTE = ["#b11226", "#0353a4", "#e08a2e", "#2a9d8f", "#7b2cbf", "#1d3557", "#e76f51"]


def arms():
    seen = []
    for c in cells:
        if c.get("arm") not in seen:
            seen.append(c.get("arm"))
    return seen


def color(a):
    return _PALETTE[arms().index(a) % len(_PALETTE)]


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


def stats(c):
    """(AUC, ROI mean, non-ROI p95, ROI/non-ROI mean ratio)."""
    p = c.get("arrays_npz")
    if not p or not Path(p).is_file():
        return None
    z = np.load(p); e1, e2 = z["e_roi"], z["e_nonroi"]
    emax = max(float(e1.max()), float(e2.max()), 1e-12)
    thr = np.linspace(0, emax, 200)
    s = np.array([(e1 >= t).mean() for t in thr]); f = np.array([(e2 >= t).mean() for t in thr])
    o = np.argsort(f); tz = getattr(np, "trapezoid", np.trapz)
    return (float(tz(s[o], f[o])), float(e1.mean()), float(np.percentile(e2, 95)),
            float(e1.mean()) / max(float(e2.mean()), 1e-9))


ST = {(c.get("target"), c.get("arm")): stats(c) for c in cells}


def b64(name):
    p = RES / name
    return ("data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()) if p.is_file() else None


def fig(name, cap, dark=False):
    src = b64(name)
    if not src:
        return ""
    return f'<figure class="{"dark" if dark else ""}"><img src="{src}"><figcaption>{cap}</figcaption></figure>'


# --- metrics table ---------------------------------------------------------
rows = ""
for t in targets():
    best_auc = max((ST[(t, a)][0] for a in arms() if ST.get((t, a))), default=None)
    for a in arms():
        c = cell(t, a); s = ST.get((t, a))
        if not c:
            continue
        auc, roi, hot, ratio = (s if s else (None, None, None, None))
        star = " ★" if (auc is not None and auc == best_auc) else ""
        rows += (f"<tr><td>{t}</td><td style='color:{color(a)};font-weight:600'>{label(a)}</td>"
                 f"<td class='num'>{c.get('thresholds') or '—'}</td>"
                 f"<td class='num'>{c.get('n_evaluations','–')}</td>"
                 f"<td class='num'><b>{('%.3f'%auc) if auc is not None else '–'}{star}</b></td>"
                 f"<td class='num'>{('%.2f'%roi) if roi is not None else '–'}</td>"
                 f"<td class='num'>{('%.2f'%hot) if hot is not None else '–'}</td>"
                 f"<td class='num'>{('%.2f'%ratio) if ratio is not None else '–'}</td></tr>")

# --- findings: per target, best arm by AUC + whether a variant beats the ROC baseline
fl = []
for t in targets():
    scored = [(a, ST[(t, a)][0]) for a in arms() if ST.get((t, a))]
    if not scored:
        continue
    scored.sort(key=lambda x: -x[1])
    best_a, best_v = scored[0]
    roc = next((v for a, v in scored if cell(t, a).get("kind") == "roc"), None)
    beat = [a for a, v in scored if cell(t, a).get("kind") not in ("roc",) and roc is not None and v >= roc]
    tail = ""
    if roc is not None:
        if beat:
            tail = f" — {len(beat)} threshold-free arm(s) match/beat the ROC baseline ({roc:.3f})."
        else:
            tail = f" — none beat the ROC baseline ({roc:.3f}) here."
    fl.append(f"<li><b>{t}:</b> best AUC = <b style='color:{color(best_a)}'>{best_v:.3f}</b> "
              f"({label(best_a)}){tail}</li>")
findings = "<ul class='findings'>" + "".join(fl) + "</ul>"

done = [c for c in cells if c.get("n_evaluations")]
n_total = len(targets()) * len(arms())
status = (f"All {n_total} conditions complete." if len(done) >= n_total
          else f"{len(done)} of {n_total} conditions complete — run still in progress.")

# objective list for the methods box
OBJ_DESC = {
    "roc": "minimizes <code>−100·(√2 − d)</code>, d = distance of the (1−spec, sens) point to the ideal corner at the chosen thresholds.",
    "integral": "minimizes <code>−mean(E<sub>ROI</sub>)/√(mean(E<sub>non-ROI</sub>))</code> (Fernández-Corazza; the volume terms are a constant).",
    "tail": "<b>A</b> — <code>−mean(E<sub>ROI</sub>)/p95(E<sub>non-ROI</sub>)</code>: penalizes off-target hotspots.",
    "ratio": "<b>B</b> — <code>−mean(E<sub>ROI</sub>)/mean(E<sub>non-ROI</sub>)</code>: ratio of means (exponent 1, vs √).",
    "auc": "<b>C</b> — <code>−AUC(E<sub>ROI</sub>, E<sub>non-ROI</sub>)</code>: the threshold-free eval metric itself.",
    "composite": "<b>D</b> — <code>−mean(E<sub>ROI</sub>)²/p95(E<sub>non-ROI</sub>)</code>: tail-focality × ROI intensity.",
}
kinds_present = []
for a in arms():
    k = next((c.get("kind") for c in cells if c.get("arm") == a), None)
    if k and k not in kinds_present:
        kinds_present.append(k)
obj_list = "".join(f"<li><span style='color:{color(a)};font-weight:600'>{label(a)}</span>: "
                   f"{OBJ_DESC.get(next((c.get('kind') for c in cells if c.get('arm')==a), ''), '')}</li>"
                   for a in arms())

comparative = "".join([
    fig("progress.png", "<b>How it's made:</b> after each evaluation, the mean-field ROI/non-ROI "
        "ratio of the current best montage, vs evaluation #. A shared ratio makes arms on different "
        "objective scales comparable. <b>Read it as:</b> higher = more focal; earlier climb = faster."),
    fig("roc.png", "<b>How it's made:</b> sweeping a field threshold, sensitivity = fraction of ROI "
        "above it, 1−specificity = fraction of non-ROI above it (SimNIBS's AUC). <b>Read it as:</b> "
        "bowed toward top-left (higher AUC) = more focal."),
    fig("distributions.png", "<b>How it's made:</b> TI-field histograms over ROI (colored) and "
        "non-ROI (grey) nodes. <b>Read it as:</b> more separation = more focal."),
    fig("summary.png", "<b>How it's made:</b> best mean ROI/non-ROI ratio per arm. Taller = more focal contrast."),
])

detail = ""
for t in targets():
    detail += f"<h3>{t} target</h3><div class='conds'>"
    for a in arms():
        key = f"{t}_{a}"
        t1 = fig(f"t1_{key}.png", "", dark=True)
        sc = fig(f"scalp_{key}.png", "")
        if t1 or sc:
            detail += f"<div class='cond'><h4 style='color:{color(a)}'>{label(a)}</h4>{t1}{sc}</div>"
    detail += "</div>"

is_variant = any(c.get("kind") in ("tail", "ratio", "auc", "composite") for c in cells)
title = ("Can integral focality beat the best-threshold ROC? — variant study"
         if is_variant else "Focality comparison")
lede = ("Four candidate threshold-free objectives (A tail-aware, B ratio, C direct-AUC, "
        "D focality×intensity) tested against the ROC baseline and the current integral, on two "
        "deep targets, at SimNIBS's default budget." if is_variant else
        "Comparing focality objectives on deep targets at SimNIBS's default budget.")

html = f"""<style>
:root {{ --ground:#f6f7f9; --panel:#fff; --ink:#1a1f2b; --muted:#5a6472; --line:#e2e6ec; --accent:#0f766e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --ground:#0f1319; --panel:#161b23; --ink:#e6e9ef; --muted:#98a2b3; --line:#262d38; --accent:#4fd1c5; }} }}
:root[data-theme="light"] {{ --ground:#f6f7f9; --panel:#fff; --ink:#1a1f2b; --muted:#5a6472; --line:#e2e6ec; --accent:#0f766e; }}
:root[data-theme="dark"] {{ --ground:#0f1319; --panel:#161b23; --ink:#e6e9ef; --muted:#98a2b3; --line:#262d38; --accent:#4fd1c5; }}
* {{ box-sizing:border-box; }}
.wrap {{ max-width:1060px; margin:0 auto; padding:2.4rem 1.2rem 4rem; background:var(--ground); color:var(--ink); font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; line-height:1.55; }}
.eyebrow {{ text-transform:uppercase; letter-spacing:.12em; font-size:.72rem; font-weight:600; color:var(--accent); margin:0 0 .3rem; }}
h1 {{ font-size:1.8rem; line-height:1.15; margin:.1rem 0 .5rem; text-wrap:balance; }}
h2 {{ font-size:1.25rem; margin:2.6rem 0 1rem; padding-bottom:.35rem; border-bottom:1px solid var(--line); }}
h3 {{ font-size:1.08rem; margin:1.8rem 0 .7rem; }} h4 {{ margin:0 0 .5rem; font-size:.92rem; }}
.lede {{ color:var(--muted); max-width:68ch; }}
.meta {{ display:flex; flex-wrap:wrap; gap:.5rem; margin:1.1rem 0 0; }}
.chip {{ font-family:ui-monospace,Menlo,monospace; font-size:.75rem; padding:.25rem .6rem; border:1px solid var(--line); border-radius:999px; background:var(--panel); color:var(--muted); }}
.status {{ margin:1.3rem 0 0; padding:.7rem 1rem; border-radius:10px; border:1px solid var(--line); border-left:3px solid var(--accent); background:var(--panel); font-size:.92rem; }}
.box {{ margin:1.4rem 0 0; padding:1rem 1.2rem; border-radius:12px; border:1px solid var(--line); background:var(--panel); }}
.box h2 {{ margin:0 0 .5rem; border:0; font-size:1.05rem; }} .box p {{ margin:.5rem 0; font-size:.9rem; color:var(--muted); }}
.box b {{ color:var(--ink); }} ul.findings,ul.objs {{ margin:.4rem 0; padding-left:1.1rem; }}
ul.findings li,ul.objs li {{ margin:.3rem 0; font-size:.9rem; color:var(--muted); }}
figure {{ margin:0 0 1.1rem; background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:.7rem; }}
figure.dark {{ background:#0d0d0f; }} figure img {{ display:block; width:100%; height:auto; border-radius:6px; }}
figcaption {{ color:var(--muted); font-size:.85rem; margin-top:.55rem; }}
.conds {{ display:grid; grid-template-columns:1fr 1fr; gap:1rem; }} @media (max-width:760px){{ .conds{{grid-template-columns:1fr;}} }}
.cond {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:.9rem; }}
.cond figure {{ border:0; padding:0; margin:.5rem 0 0; }} .cond figure.dark {{ padding:.3rem; border-radius:8px; }}
table {{ width:100%; border-collapse:collapse; margin-top:1rem; font-size:.88rem; }}
th,td {{ text-align:left; padding:.4rem .6rem; border-bottom:1px solid var(--line); }}
th {{ color:var(--muted); font-weight:600; font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; }}
.num {{ font-family:ui-monospace,Menlo,monospace; font-variant-numeric:tabular-nums; }}
.foot {{ margin-top:3rem; color:var(--muted); font-size:.8rem; border-top:1px solid var(--line); padding-top:1rem; }}
code {{ font-family:ui-monospace,Menlo,monospace; font-size:.85em; background:var(--panel); border:1px solid var(--line); padding:.05rem .3rem; border-radius:4px; }}
</style>
<div class="wrap">
  <p class="eyebrow">TI-Toolbox · flex-search focality</p>
  <h1>{title} <span style="font-weight:400;color:var(--muted);font-size:1rem">({d.get('subject','ernie')})</span></h1>
  <p class="lede">{lede}</p>
  <div class="meta">
    <span class="chip">SimNIBS default: popsize 13 · maxiter 1000 · tol 0.1</span>
    <span class="chip">2 mA · max_TI</span><span class="chip">SimNIBS 4.6 · ernie</span>
  </div>
  <div class="status">{status}</div>

  <div class="box"><h2>What the run shows</h2>
    {findings}
    <p style="margin-top:.6rem"><b>Read the table with three lenses:</b> <b>AUC</b> (focality; ★ = best per
    target), <b>ROI mean</b> (achieved on-target intensity, V/m), and <b>non-ROI p95</b> (the off-target
    hotspot — lower is safer). A good objective raises AUC and ROI intensity while keeping the hotspot down.</p>
  </div>

  <div class="box"><h2>Objectives (all threshold-free except ROC)</h2><ul class="objs">{obj_list}</ul>
    <p>Because these live on different numeric scales, every cross-arm plot uses the shared ROI/non-ROI
    contrast and the ROC AUC, computed on the same optimized-montage fields.</p></div>

  <h2>Metrics</h2>
  <table><thead><tr><th>Target</th><th>Arm</th><th>Thresholds</th><th>Evals</th><th>AUC</th>
    <th>ROI mean (V/m)</th><th>non-ROI p95</th><th>ROI/non-ROI</th></tr></thead><tbody>{rows}</tbody></table>

  <h2>Comparative panels</h2>
  {comparative}

  <h2>Per-condition: field on the T1 &amp; electrodes on the scalp</h2>
  <p class="lede" style="margin-bottom:.4rem">TI_max field on the subject T1; the <b>white contour marks
  the target ROI</b>. Electrodes are the optimized channel centres from the flex-output mesh.</p>
  {detail}
  <p class="foot">Real flex-search runs on SimNIBS <code>ernie</code>. Fields, electrodes, and the on-T1
  render come from the flex-output meshes; AUC/intensity/hotspot use each optimized montage's exact fields.</p>
</div>
"""
OUT.write_text(html)
print("wrote", OUT, f"({len(html)} chars)")
