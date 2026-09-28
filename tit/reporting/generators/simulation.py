"""Simulator report: one self-contained HTML record per simulated montage.

Built on :mod:`tit.reporting.html.components` (ARCHITECTURE.md §14) like the DTI report. Everything
is read from what the simulation wrote: ``documentation/config.json`` (montage, currents,
electrodes, conductivity), the SimNIBS log (whether the DTI tensor was used, per-carrier currents,
the solves), ``high_Frequency/analysis/fields_summary.txt`` (per-carrier grey-matter percentiles),
the grey/white-matter envelope NIfTIs and, when the Analyzer has run on it, the ROI analysis. Rules
come from ``tit.reporting.qc_rules.RULES["sim"]``; the current checks are advisories, never blocking.

The default view is the verdict with the key numbers, the montage on the app's EEG-cap overlay, the
envelope at the target, and the safety advisories; software checks, per-carrier fields, methods,
references and the run record are collapsed under Technical details.

``tit.sim`` writes one after every montage (:meth:`tit.sim.base.BaseSimulation.run`). Rebuild one
(nothing is re-simulated; an ROI analysis run since is included)::

    simnibs_python -m tit.reporting.generators.simulation <project> <subject> <simulation> [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from tit.reporting.generators import common
from tit.reporting.generators.common import fmt
from tit.reporting.html import components as c
from tit.reporting.html.components import Check, esc
from tit.reporting.qc_rules import RULES

logger = logging.getLogger(__name__)

REPORT_PREFIX = "simulation_report"
#: Report size budget (bytes); the rebuild command and tests check it.
SIZE_BUDGET = 1_500_000

_CONDUCTIVITY = {
    "scalar": "isotropic (SimNIBS standard tissue values)",
    "vn": "anisotropic, volume-normalised (vn)",
    "dir": "anisotropic, direct mapping (dir)",
    "mc": "anisotropic, mean conductivity (mc)",
}


# ── reading the simulation's outputs ─────────────────────────────────────


def parse_fields_summary(text: str) -> list[dict]:
    """Per carrier (``ernie_TDCS_1``, …): the grey-matter ``magnE`` percentiles SimNIBS printed."""
    out = []
    for block in re.split(r"\n(?=\S+\n=+\n)", text.strip()):
        name = block.split("\n", 1)[0].strip()
        head = re.search(r"\|Field\s*\|(.+)\|", block)
        row = re.search(r"\|magnE\s*\|(.+)\|", block)
        if not (head and row):
            continue
        pcts = [h.strip().rstrip("%") for h in head.group(1).split("|")]
        vals = [float(v.split()[0]) for v in row.group(1).split("|")]
        out.append({"name": name, **{f"p{p}": v for p, v in zip(pcts, vals)}})
    return out


def parse_log(text: str) -> dict:
    """What the SimNIBS log says about the run: carrier currents, the tensor, the solves."""
    tensor = re.search(r"Using anisotropic .*? based on the file: (\S+)", text)
    solver = re.search(r"Using solver options: (\S+)", text)
    return {
        "currents_A": [
            [float(v) for v in m.split(",")]
            for m in re.findall(r"Currents \(A\): \[([^\]]+)\]", text)
        ],
        "tensor": tensor.group(1) if tensor else None,
        "solver": solver.group(1) if solver else None,
        "n_solved": len(re.findall(r"Time to solve:", text)),
        "calibration_error_pct": [
            float(v) for v in re.findall(r"current calibration error: ([\d.]+)%", text)
        ],
        "simnibs": (re.search(r"simnibs (\d[\w.]*)", text) or [None, None])[1],
    }


def _roi_analysis(sim_dir: Path) -> dict | None:
    """The newest Analyzer result for this simulation (``Analyses/<space>/<name>/results.csv``)."""
    found = sorted(
        (sim_dir / "Analyses").glob("*/*/results.csv"), key=lambda p: p.stat().st_mtime
    )
    if not found:
        return None
    rows = dict(csv.reader(found[-1].open()))
    meta_path = found[-1].parent / "analysis.json"
    meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}

    def num(k: str) -> float | None:
        try:
            return float(rows[k])
        except (KeyError, ValueError):
            return None

    mask = found[-1].parent / "roi_overlay.nii.gz"
    return {
        "name": rows.get("region_name") or found[-1].parent.name,
        "space": rows.get("space") or meta.get("space"),
        "type": rows.get("analysis_type") or meta.get("analysis_type"),
        "mean": num("roi_mean"),
        "max": num("roi_max"),
        "focality": num("roi_focality"),
        "gm_mean": num("gm_mean"),
        "n": num("n_elements"),
        "mask": str(mask) if mask.is_file() else None,
        "folder": found[-1].parent.name,
    }


def _envelope_niftis(sim_dir: Path, name: str, mode: str) -> dict[str, Path]:
    """``{"grey": …, "white": …}`` envelope NIfTIs (``<mode>/niftis/<tissue>_<name>_*TI_max.nii.gz``)."""
    out = {}
    for tissue in ("grey", "white"):
        hits = sorted(
            (sim_dir / mode / "niftis").glob(f"{tissue}_{name}_*TI_max.nii.gz")
        )
        if hits:
            out[tissue] = hits[0]
    return out


def collect(sim_dir: str | Path) -> dict:
    """Everything the report shows, from one simulation folder."""
    sim_dir = Path(sim_dir)
    doc = sim_dir / "documentation"
    config = json.loads((doc / "config.json").read_text())
    logs = sorted(doc.glob("simnibs_simulation_*.log"))
    log = parse_log(logs[-1].read_text(errors="replace")) if logs else parse_log("")
    summary = sim_dir / "high_Frequency" / "analysis" / "fields_summary.txt"
    mode = "mTI" if str(config.get("simulation_mode", "TI")).upper() == "MTI" else "TI"
    rec = {
        "name": config.get("simulation_name") or sim_dir.name,
        "mode": mode,
        "config": config,
        "log": log,
        "carriers": (
            parse_fields_summary(summary.read_text()) if summary.is_file() else []
        ),
        "roi": _roi_analysis(sim_dir),
        "envelope": None,
    }
    niftis = _envelope_niftis(sim_dir, rec["name"], mode)
    if "grey" in niftis:
        import nibabel as nib

        gm = np.asarray(nib.load(niftis["grey"]).dataobj, dtype=np.float32)
        v = gm[gm > 0]
        if v.size:
            rec["envelope"] = {
                "median": float(np.median(v)),
                "p99_9": float(np.percentile(v, 99.9)),
                "max": float(v.max()),
            }
    rec["niftis"] = {k: str(p) for k, p in niftis.items()}
    return rec


# ── the envelope figure ──────────────────────────────────────────────────


def field_images(rec: dict, t1_path: str | Path) -> dict | None:
    """Axial, coronal and sagittal envelope panels through the ROI centre (or the grey-matter
    hot spot), over the T1, with the ROI outline; WebP bytes plus label geometry."""
    import nibabel as nib

    from tit.plotting import slices as s

    if "grey" not in rec["niftis"] or not rec["envelope"]:
        return None
    t1_img = nib.load(str(t1_path))
    t1, affine = s.canonical(
        np.asarray(t1_img.dataobj, dtype=np.float32), t1_img.affine
    )
    field = np.zeros_like(t1)
    for path in rec["niftis"].values():
        img = nib.load(path)
        f, _ = s.canonical(np.asarray(img.dataobj, dtype=np.float32), img.affine)
        if f.shape != t1.shape:
            return None
        field = np.maximum(field, f)
    brain = field > 0
    roi = None
    if rec["roi"] and rec["roi"]["mask"]:
        m = nib.load(rec["roi"]["mask"])
        roi, _ = s.canonical(np.asarray(m.dataobj) > 0, m.affine)
        roi = roi if roi.shape == t1.shape and roi.any() else None
    lo, hi = rec["envelope"]["median"], rec["envelope"]["p99_9"]
    centre_mask = roi if roi is not None else (field >= hi)
    centre = np.round(np.argwhere(centre_mask).mean(axis=0)).astype(int)
    box = s.brain_box(brain)
    grey = np.clip(
        (t1 - np.percentile(t1[brain], 1)) / np.ptp(np.percentile(t1[brain], [1, 99])),
        0,
        1,
    )
    world = affine[:3, :3] @ centre + affine[:3, 3]
    names = ("sagittal", "coronal", "axial")
    tiles, outlines, labels = [], [], []
    for axis in (2, 1, 0):
        rgb = s.overlay(
            s.oriented(grey, axis, centre[axis], box),
            s.oriented(field, axis, centre[axis], box),
            lo,
            hi,
        )
        tiles.append(rgb)
        outlines.append(
            s.oriented(roi, axis, centre[axis], box) if roi is not None else None
        )
        labels.append(f"{names[axis]} {'xyz'[axis]} = {world[axis]:+.0f} mm")
    image, tile = s.mosaic(tiles, cols=3)
    mask_mosaic = s.mosaic(
        [
            o if o is not None else np.zeros(t.shape[:2], bool)
            for o, t in zip(outlines, tiles)
        ],
        cols=3,
    )[0]
    contours = [(mask_mosaic, "#4cc9f0", 1.3)] if roi is not None else []
    return {
        "image": s.render(image, contours),
        "labels": labels,
        "tile": tile,
        "shape": image.shape,
        "lo": lo,
        "hi": hi,
        "stops": s.colour_stops(),
        "centred_on": (
            "the ROI centre"
            if roi is not None
            else "the grey-matter hot spot (top 0.1 %)"
        ),
    }


def _colour_bar(lo: float, hi: float, stops: list[str]) -> str:
    grad = ",".join(stops)
    return (
        f'<div class="cbar"><span class="num">{lo:.2f}</span><i style="background:linear-gradient(90deg,{grad})"></i>'
        f'<span class="num">{hi:.2f} V/m</span></div>'
    )


EXTRA_CSS = (
    ".cbar{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ink-2);margin-top:8px;max-width:460px}"
    ".cbar i{flex:1;height:10px;border-radius:2px}"
)


# ── checks ───────────────────────────────────────────────────────────────


def checks(rec: dict) -> list[Check]:
    """Software checks (internal) then advisories, all from the run's own record."""
    cfg, log, env = rec["config"], rec["log"], rec["envelope"]
    currents = [float(v) for v in cfg.get("intensities") or []]
    total = sum(currents)
    rows = []
    n = len(currents)
    solved = log["n_solved"]
    rows.append(
        common.rule_check(
            "sim",
            "solver_rtol",
            "pass" if n and solved >= n else "fail",
            f"{solved} of {n} carrier solves logged ({log['solver'] or 'solver not logged'})",
            f"≤ {RULES['sim']['solver_rtol']['value']:g} (SimNIBS default, not overridden)",
        )
    )
    sums = [abs(sum(cs)) * 1e3 for cs in log["currents_A"]]
    rows.append(
        common.rule_check(
            "sim",
            "channel_current_sum",
            "pass" if sums and max(sums) < 1e-9 else "fail",
            (
                f"{max(sums):.3g} mA largest imbalance over {len(sums)} carriers"
                if sums
                else "no currents logged"
            ),
            "= 0 mA",
        )
    )
    if env and total > 0:
        lo, hi = RULES["sim"]["peak_field_order_check"]["value"]
        per_mA = env["p99_9"] / total
        rows.append(
            common.rule_check(
                "sim",
                "peak_field_order_check",
                "pass" if lo <= per_mA <= hi else "fail",
                f"{per_mA:.3g} V/m per mA (grey-matter 99.9th percentile)",
                f"{lo:g}–{hi:g} V/m per mA",
            )
        )
    if currents:
        rows.append(common.current_check("sim", currents))
    if rec["carriers"]:
        from tit.constants import CONDUCTIVITY_GRAY_MATTER as sigma

        j = sigma * sum(cr.get("p99.9", 0.0) for cr in rec["carriers"])
        r = RULES["sim"]["brain_peak_J"]
        row = common.rule_check(
            "sim",
            "brain_peak_J",
            "pass" if j < r["value"] else "warn",
            f"≈ {j:.2g} A/m² (estimate)",
            f"< {r['value']:g} {r['unit']}",
        )
        row.note = (
            f"estimate: grey-matter conductivity {sigma:g} S/m × the sum of the carriers' "
            "99.9th-percentile grey-matter fields; the simulation does not write current density"
        )
        rows.append(row)
    return rows


# ── the page ─────────────────────────────────────────────────────────────


def _range_row(rec: dict, cite: c.Cites) -> str:
    """ROI mean against the published TI range, scaled to this run's total current."""
    r = RULES["sim"]["roi_envelope_V_per_m"]
    total = sum(float(v) for v in rec["config"].get("intensities") or [])
    lo, hi = (v * total / r["at_mA_total"] for v in r["range"])
    mean = rec["roi"]["mean"]
    where = "within" if lo <= mean <= hi else ("below" if mean < lo else "above")
    scaled = (
        "" if total == r["at_mA_total"] else f" (scaled from {r['at_mA_total']:g} mA)"
    )
    rail = c.gate_scale(mean, 0, max(hi * 1.6, mean * 1.1), (lo, hi), st="info")
    return (
        f'<div class="split" style="margin-top:14px;align-items:center"><div>{rail}'
        '<div class="muted" style="font-size:12px">band: published range · dot: ROI mean</div></div>'
        f'<p class="muted" style="margin:0;font-size:13px">ROI mean {mean:.3f} V/m is <b>{where}</b> the published range for '
        f"optimised TI, {lo:.2f}–{hi:.2f} V/m at {fmt(total)} mA total{scaled} {cite.dois(r['cite'])}.</p></div>"
    )


def build_html(
    rec: dict,
    images: dict | None,
    subject_id: str,
    generated: datetime | None = None,
) -> str:
    """The whole report from the collected record and the rendered envelope figure."""
    import tit

    generated = generated or datetime.now()
    cfg, log, env, roi = rec["config"], rec["log"], rec["envelope"], rec["roi"]
    cite = c.Cites()
    fig_no = iter(range(1, 20))
    pairs = [list(p) for p in cfg.get("electrode_pairs") or []]
    currents = [float(v) for v in cfg.get("intensities") or []]
    total = sum(currents)
    rows = checks(rec)
    internal = [r for r in rows if r.role == "internal"]
    advisories = [r for r in rows if r.role == "advisory"]
    seal, headline = c.verdict(rows)
    cond = cfg.get("conductivity", "scalar")
    montage = " and ".join("–".join(p) for p in pairs) or rec["name"]
    per_ch = (
        fmt(currents[0])
        if len(set(currents)) == 1
        else " / ".join(fmt(v) for v in currents)
    )

    # ── 1. verdict ──
    if seal != "fail":
        if roi and roi["mean"] is not None:
            headline = f"{roi['mean']:.3f} V/m mean envelope in the ROI"
        elif env:
            headline = f"{env['p99_9']:.3f} V/m peak envelope in grey matter"
    tensor = log["tensor"]
    cond_txt = _CONDUCTIVITY.get(cond, esc(cond))
    if cond != "scalar":
        cond_txt += (
            " from the subject's DTI tensor"
            if tensor
            else " (the log does not confirm a tensor was read)"
        )
    n_attn = sum(a.status in ("warn", "fail") for a in advisories)
    lede = f"{'Multichannel temporal' if rec['mode'] == 'mTI' else 'Temporal'} interference with {esc(montage)} " f"at {per_ch} mA per channel ({fmt(total)} mA total), {cond_txt}. " + (
        f"The ROI mean is {roi['focality']:.2f}× the grey-matter mean. "
        if roi and roi.get("focality")
        else ""
    ) + (
        "Safety advisories are within their evidence ranges."
        if not n_attn
        else "Read the advisories below."
    )
    key = []
    if roi and roi["mean"] is not None:
        key += [
            (
                "ROI mean",
                f"{roi['mean']:.3f}<small>V/m</small>",
                f"max {roi['max']:.3f} V/m" if roi["max"] else "",
            ),
            (
                (
                    "Focality",
                    f"{roi['focality']:.2f}<small>×</small>",
                    "ROI mean / grey-matter mean",
                )
                if roi.get("focality")
                else None
            ),
        ]
    if env:
        key += [
            (
                "Grey matter 99.9th pct",
                f"{env['p99_9']:.3f}<small>V/m</small>",
                f"median {env['median']:.3f} V/m",
            ),
        ]
    key.append(
        (
            "Total current",
            f"{fmt(total)}<small>mA</small>",
            f"{len(currents)} channels × {per_ch} mA",
        )
    )
    extra = common.attention_callouts(advisories, cite) + c.stats([k for k in key if k])
    verdict_sec = c.verdict_section(seal, headline, lede, extra)

    # ── 2. montage ──
    geo = cfg.get("electrode_geometry") or {}
    dims = "×".join(f"{d:g}" for d in geo.get("dimensions") or [])
    dose = [
        (
            "Electrodes",
            esc(
                f"{geo.get('shape', '?')} {dims} mm, gel {geo.get('gel_thickness', '?')} mm, rubber {geo.get('rubber_thickness', '?')} mm"
            ),
        ),
        (
            "Current",
            f"{per_ch} mA per channel, {fmt(total)} mA total (each electrode carries its channel's current)",
        ),
        (
            "Carrier frequencies",
            "not part of the field model (quasi-static); set them on the stimulator",
        ),
        ("EEG net", esc(Path(str(cfg.get("eeg_net") or "—")).stem)),
        (
            "Conductivity",
            cond_txt + (f": <code>{esc(Path(tensor).name)}</code>" if tensor else ""),
        ),
    ]
    if cfg.get("is_xyz_montage") or not cfg.get("eeg_net"):
        cap = c.kv(common.channel_rows([[str(e) for e in p] for p in pairs], currents))
    else:
        cap = common.cap_figure(next(fig_no), pairs, cfg["eeg_net"], currents)
    montage_sec = c.section(
        "montage",
        "Montage and dose",
        cap + '<h3 class="sub">Dose</h3>' + c.kv(dose),
        lead="Where the current goes in and how much.",
    )

    # ── 3. field ──
    body = ""
    if images:
        labels = c.tile_labels(images["labels"], 3, images["tile"], images["shape"])
        outline = "The ROI is outlined in cyan. " if roi and roi.get("mask") else ""
        body += c.figure(
            next(fig_no),
            "TI envelope amplitude",
            f'<div class="lightbox"><div class="lb-inner">{c.img(images["image"], "TI envelope over the T1, through " + images["centred_on"])}{labels}</div></div>'
            + _colour_bar(images["lo"], images["hi"], images["stops"]),
            f"Slices through {images['centred_on']}. Coloured where the envelope is above the grey-matter median "
            f"({images['lo']:.2f} V/m), up to its 99.9th percentile; grey and white matter only. {outline}"
            "Neurological convention: subject left on image left.",
        )
    if roi and roi["mean"] is not None:
        body += _range_row(rec, cite)
        body += c.kv(
            [
                ("ROI", esc(f"{roi['name']} ({roi['type']} analysis, {roi['space']})")),
                (
                    "Grey-matter mean",
                    f"{roi['gm_mean']:.3f} V/m" if roi["gm_mean"] else "—",
                ),
            ]
        )
    else:
        body += '<p class="muted">No ROI analysis yet. Run the Analyzer on this simulation to compare a target with the published TI range, then rebuild this report.</p>'
    field_sec = c.section(
        "field",
        "Field",
        body,
        lead="Where the envelope is strongest, and how the target compares.",
    )

    # ── 4. safety ──
    safety_sec = c.section(
        "safety",
        "Safety advisories",
        c.checks_table(
            advisories,
            "Advisories never block; they compare this dose with published evidence.",
            cite.dois,
        ),
        st="warn" if n_attn else "pass",
        st_label="Review" if n_attn else "Within evidence",
    )

    # ── 5. technical details ──
    tech = c.details(
        "Software checks",
        c.checks_table(
            internal,
            "Consistency checks of the run itself, not published limits.",
            cite.dois,
        ),
        "solver, current conservation, field scale",
        open_=any(r.status == "fail" for r in internal),
    )
    if rec["carriers"]:
        pct = [k for k in rec["carriers"][0] if k.startswith("p")]
        tech += c.details(
            "Carrier fields",
            c.table(
                ["Carrier", "Channel"] + [f"{k[1:]} %" for k in pct],
                [
                    [
                        esc(cr["name"]),
                        esc(" → ".join(pairs[i])) if i < len(pairs) else "",
                    ]
                    + [f"{cr[k]:.3f}" for k in pct]
                    for i, cr in enumerate(rec["carriers"])
                ],
                caption="Each high-frequency carrier alone: grey-matter |E| percentiles (V/m) from SimNIBS's field summary.",
                right=set(range(2, 2 + len(pct))),
            )
            + (
                f'<p class="muted" style="font-size:13px;margin-top:10px">SimNIBS estimated the electrode current calibration error at '
                f"{', '.join(f'{v:g} %' for v in log['calibration_error_pct'])}.</p>"
                if log["calibration_error_pct"]
                else ""
            ),
            "per-carrier grey-matter percentiles",
        )
    paras = [
        f"Temporal interference stimulation {cite('grossman2017_ti')} was simulated in TI-Toolbox {cite('haber2026_titoolbox')} with SimNIBS "
        f"{esc(log['simnibs'] or '')} {cite('saturnino2019_simnibs21')} on the head model of subject {esc(subject_id)} {cite('puonti2020_charm')}. "
        f"{len(pairs)} channels ({esc(montage)}) each delivered {per_ch} mA through {esc(geo.get('shape', ''))} {dims} mm electrodes with "
        f"{geo.get('gel_thickness', '?')} mm gel"
        + (
            f"; positions from the {esc(Path(str(cfg.get('eeg_net'))).stem)} layout {cite('jurcak2007_eeg_positions')}"
            if cfg.get("eeg_net") and "10-" in str(cfg.get("eeg_net"))
            else ""
        )
        + ". "
        + (
            f"Tissue conductivities were anisotropic in white and grey matter, derived from diffusion tensors ({esc(cond)}) "
            f"{cite('tuch2001_conductivity', 'opitz2011_tissue_efield')}."
            if cond != "scalar"
            else "Tissue conductivities were isotropic SimNIBS standard values."
        ),
        "The TI envelope was taken as the maximal modulation amplitude over field orientations "
        f"{cite('grossman2017_ti')}"
        + (
            f"; in the ROI its mean was {roi['mean']:.3f} V/m."
            if roi and roi["mean"] is not None
            else "."
        ),
    ]
    tech += c.details(
        "Methods and references",
        c.methods(paras) + '<h3 class="sub">References</h3>' + cite.listing(),
        "boilerplate generated from this run; check before use",
    )
    run = [
        ("Simulation", esc(rec["name"])),
        ("Created", esc(str(cfg.get("created_at", "—"))[:16].replace("T", " "))),
        ("TI-Toolbox", esc(tit.__version__)),
        ("SimNIBS", esc(log["simnibs"] or "not recorded")),
        ("Solver", esc(log["solver"] or "not recorded")),
    ]
    if roi:
        run.append(("ROI analysis", esc(roi["folder"])))
    tech += c.details(
        "Run record",
        c.kv(run)
        + '<h3 class="sub">config.json</h3>'
        + c.code(json.dumps(cfg, indent=1)),
        "versions and the configuration as run",
    )

    masthead = c.masthead(
        "TI simulation" if rec["mode"] == "TI" else "mTI simulation",
        rec["name"],
        [
            ("Subject", esc(subject_id)),
            ("Conductivity", esc(cond)),
            ("Total current", f"{fmt(total)} mA"),
            ("Report", generated.strftime(common.STAMP)),
        ],
    )
    toc = [
        ("verdict", "Verdict", seal),
        ("montage", "Montage and dose", None),
        ("field", "Field", None),
        ("safety", "Safety advisories", "warn" if n_attn else "pass"),
        (
            "technical",
            "Technical details",
            "fail" if any(r.status == "fail" for r in internal) else None,
        ),
    ]
    return c.page(
        title=f"{rec['name']} simulation",
        kind="Simulation report",
        subject=f"sub-{subject_id}",
        toc=toc,
        body=masthead
        + verdict_sec
        + montage_sec
        + field_sec
        + safety_sec
        + c.section("technical", "Technical details", tech),
        footer=common.footer(generated),
        description=f"Simulation report for sub-{subject_id}, {rec['name']}: {headline}",
        generator=f"TI-Toolbox {tit.__version__}",
        extra_css=EXTRA_CSS,
    )


def create_simulation_report(
    project_dir: str | Path,
    subject_id: str,
    simulation_name: str,
    out_dir: str | Path | None = None,
) -> Path:
    """Write the report for one simulation folder; into the project's reports unless *out_dir*."""
    from tit.paths import get_path_manager

    t0 = time.time()
    pm = get_path_manager(str(project_dir))
    rec = collect(pm.simulation(subject_id, simulation_name))
    try:
        images = field_images(rec, Path(pm.m2m(subject_id)) / "T1.nii.gz")
    except (OSError, ValueError) as exc:
        logger.warning(f"Simulation report: no envelope figure ({exc})")
        images = None
    html = build_html(rec, images, subject_id)
    return common.write_report(
        html,
        project_dir,
        subject_id,
        REPORT_PREFIX,
        SIZE_BUDGET,
        out_dir,
        t0,
        label="Simulation report",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild a simulation report from its outputs."
    )
    parser.add_argument("project_dir")
    parser.add_argument("subject_id")
    parser.add_argument("simulation")
    parser.add_argument(
        "--out", help="write the report here instead of into the project"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()
    path = create_simulation_report(
        args.project_dir, args.subject_id, args.simulation, args.out
    )
    print(f"{path} {path.stat().st_size / 1e6:.2f} MB in {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
