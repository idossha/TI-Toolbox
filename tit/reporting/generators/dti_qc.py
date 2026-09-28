"""DTI quality-control report: one self-contained HTML record per tensor extraction.

Built on :mod:`tit.reporting.html.components` (ARCHITECTURE.md §14). The numbers come from
``DTI_coregT1_qc.json``, written by :func:`tit.pre.qsi.dti_extractor.extract_dti_tensor`; the
images come from :mod:`tit.plotting.dti_qc`; every rule's label, role, citation and plain text from
``tit.reporting.qc_rules.RULES["dti"]``. The default view is the verdict, the user-facing gate,
advisories that need attention, preprocessing, one registration and one fibre-orientation figure,
and FA/MD by tissue; the rest sits in collapsed Technical details.

Rebuild a report from an existing tensor and QC record (nothing is re-fitted)::

    simnibs_python -m tit.reporting.generators.dti_qc <project> <subject> [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from tit.reporting.html import components as c
from tit.reporting.html.components import Check, esc
from tit.reporting.qc_rules import RULES

logger = logging.getLogger(__name__)

REPORT_PREFIX = "dti_qc"
#: Report size budget (bytes); the rebuild command and tests check it.
SIZE_BUDGET = 2_500_000

EXTRA_CSS = ":root{--wm-c:#ffd23f;--pial-c:#4cc9f0}.dec-fig .scrub{max-width:620px}"
_STAMP = "%Y-%m-%d %H:%M"

#: The blocking checks in table order: record field -> (recorded threshold key, value format,
#: threshold format, unit, display scale, rail lo, rail hi).
_GATES = {
    "ncc_chain": ("min_ncc", ".3f", ".2f", "", 1, 0.8, 1.0),
    "chain_vs_ncc_mm": ("max_chain_vs_ncc_mm", ".2f", ".1f", " mm", 1, 0.0, 2.0),
    "pct_pd": ("min_pct_pd", ".1f", ".0f", " %", 1, 95.0, 100.0),
    "pct_wmgm_zero": ("max_pct_wmgm_zero", ".2f", ".0f", " %", 1, 0.0, 10.0),
    "wm_md_median": ("wm_md_range", ".2f", ".2f", " ×10⁻³ mm²/s", 1e3, 0.3, 1.3),
    "n_out_of_brain": ("max_out_of_brain", ",", "", "", 1, 0.0, 10.0),
}
_OP = {">=": "≥", "<=": "≤", "==": "="}

_PE = {
    "Anterior-Posterior": "A→P",
    "Posterior-Anterior": "P→A",
    "Left-Right": "L→R",
    "Right-Left": "R→L",
}
_VERSIONS = {
    "ti_toolbox": "TI-Toolbox",
    "qsiprep": "QSIPrep",
    "simnibs": "SimNIBS",
    "dipy": "DIPY",
    "numpy": "NumPy",
    "scipy": "SciPy",
    "nibabel": "NiBabel",
    "python": "Python",
}


def gate_checks(qc: dict) -> list[Check]:
    """The six blocking checks of ``DTI_coregT1_qc.json``; each row's status comes from ``failures`` only."""
    rows = []
    for key, (tkey, vfmt, tfmt, unit, s, lo, hi) in _GATES.items():
        r, t, v = RULES["dti"][key], qc["thresholds"][tkey], qc[key] * s
        if r["rule"] == "within":
            ok = (t[0] * s, t[1] * s)
            text = f"{ok[0]:{tfmt}}–{ok[1]:{tfmt}}{unit}"
        else:
            text = f"{_OP[r['rule']]} {t * s:{tfmt}}{unit}"
            # "==" gets a sliver of band so the accepted value shows on the rail.
            ok = {">=": (t * s, hi), "<=": (lo, t * s), "==": (t, t + 0.2)}[r["rule"]]
        status = c.gate_status(key, qc.get("failures", []))
        rows.append(
            Check(
                key,
                r["label"],
                r["plain"],
                f"{v:{vfmt}}{unit}",
                text,
                status,
                role=r["role"],
                value=v,
                rail=(lo, hi, *ok),
                cite=r["cite"],
                note=r["note"],
            )
        )
    return rows


def _motion_chart(
    bvals: list[float], fd: list[float], mean_fd: float, bmax: float
) -> str:
    """Per volume: diffusion weighting (in or out of the fit) above framewise displacement."""
    n, width, ml, mr = len(fd), 1000, 44, 10
    pw, h1, gap, h2 = width - ml - mr, 16, 34, 96
    height, y0 = h1 + gap + h2 + 34, h1 + gap
    fmax = max(2.0, -(-max(fd, default=0) * 2 // 1) / 2)

    def X(i: float) -> float:
        return ml + (i + 0.5) / n * pw

    def Y(v: float) -> float:
        return y0 + h2 - min(v, fmax) / fmax * h2

    p = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Diffusion weighting and head motion per volume">',
        f'<text x="{ml - 6}" y="{h1 - 3}" text-anchor="end">b</text><text x="{ml}" y="{y0 - 10}">Framewise displacement (mm)</text>',
    ]
    for i, b in enumerate(bvals[:n]):
        colour = (
            "var(--ink)"
            if b < 100
            else f"var(--{'s1' if b <= bmax else 'rule-strong'})"
        )
        tip = f"Volume {i}: b = {b:.0f} s/mm² ({'in the fit' if b <= bmax else 'not used'})"
        p.append(
            f'<rect x="{X(i) - pw / n / 2 + 0.6:.1f}" y="0" width="{max(pw / n - 1.2, 1):.1f}" height="{h1}" rx="1.5" fill="{colour}" data-tip="{esc(tip)}"/>'
        )
    for t in c.nice_ticks(0, fmax, 4):
        p.append(
            f'<line class="grid" x1="{ml}" x2="{width - mr}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/><text x="{ml - 6}" y="{Y(t) + 4:.1f}" text-anchor="end">{t:g}</text>'
        )
    bw = min(pw / n - 1.4, 5)
    for i, v in enumerate(fd):
        p.append(
            f'<rect x="{X(i) - bw / 2:.1f}" y="{Y(v):.1f}" width="{bw:.1f}" height="{max(Y(0) - Y(v), 0):.1f}" fill="var(--s1)" opacity=".8"/>'
            f'<rect class="hit" x="{X(i) - pw / n / 2:.1f}" y="{y0}" width="{pw / n:.1f}" height="{h2}" data-tip="Volume {i}: FD {v:.2f} mm"/>'
        )
    p.append(
        f'<line x1="{ml}" x2="{width - mr}" y1="{Y(mean_fd):.1f}" y2="{Y(mean_fd):.1f}" stroke="var(--ink)" stroke-width="1.2"/>'
        f'<text x="{width - mr}" y="{y0 - 10}" text-anchor="end" class="t-ink">— mean {mean_fd:.2f} mm</text>'
    )
    p += [
        f'<text x="{X(t):.1f}" y="{y0 + h2 + 16}" text-anchor="middle">{t}</text>'
        for t in range(0, n, 16)
    ]
    p.append(
        f'<text x="{ml + pw / 2:.1f}" y="{height - 2}" text-anchor="middle">Volume (acquisition order)</text></svg>'
    )
    return "".join(p)


def build_html(
    qc: dict,
    images: dict,
    subject_id: str,
    generated: datetime | None = None,
    tensor_written: datetime | None = None,
) -> str:
    """The whole report from the QC record and the rendered images (no file access)."""
    import tit

    generated = generated or datetime.now()
    sid = esc(subject_id)
    cite = c.Cites()
    fig_no = iter(range(1, 20))
    gates, advs = gate_checks(qc), [Check(**a) for a in qc.get("advisories", [])]
    internal = [g for g in gates if g.role == "internal"]
    attention = [
        a for a in advs if a.role == "advisory" and a.status in ("warn", "fail")
    ]
    ids = {a.id for a in attention}
    passed = not qc.get("failures")
    seal, headline = c.verdict(gates + advs, consequence="tensor not written")
    m, acq, mot, sdc, prov = (
        qc.get(k) or {}
        for k in ("metrics", "acquisition", "motion", "sdc", "provenance")
    )
    sc, q = acq.get("scanner", {}), acq.get("qsiprep", {})
    bmax = prov.get("config", {}).get("DTI_BMAX", 1500)
    bvals, tissue = acq.get("bvals", []), m.get("tissue", {})
    shells = ", ".join(
        f"{n} × b={b}"
        for b, n in sorted(acq.get("shells", {}).items(), key=lambda kv: int(kv[0]))
    )
    model = str(sc.get("ManufacturersModelName") or "").replace("_", " ")
    scanner = esc(
        f"{sc.get('Manufacturer')} {model}, {sc.get('MagneticFieldStrength')} T"
    )
    mni = "MNI" if images.get("is_mni", True) else "approximate MNI"
    md_lo, md_hi = qc["thresholds"]["wm_md_range"]
    md_range = f"{md_lo * 1e3:.1f}–{md_hi * 1e3:.1f} ×10⁻³ mm²/s"
    shift = m.get("residual_shift") or {}

    def worst(r: dict) -> float:
        return max(abs(r["best_ap_mm"]), abs(r["best_si_mm"]))

    # ── 1. verdict ──
    if passed:
        lede = (
            f"The tensor was written to <code>m2m_{sid}/DTI_coregT1_tensor.nii.gz</code> and SimNIBS can use it for "
            "anisotropic conductivity (<code>vn</code>, <code>dir</code> or <code>mc</code>)."
            + (
                " Read the advisories below before relying on it in the regions they name."
                if attention
                else " Nothing needs attention."
            )
        )
        callouts = ""
    else:
        failed = ", ".join(g.label.lower() for g in gates if g.status == "fail")
        lede = (
            f"The tensor was <b>not written</b> because of: {esc(failed)}. SimNIBS cannot use this subject for anisotropic "
            "conductivity until the cause is fixed and the DTI step is run again. The figures show the tensor as computed."
        )
        callouts = c.callout(
            "fail",
            "Tensor not written.",
            "<p>Check QSIPrep's report for this subject, and that charm ran on the same T1w QSIPrep used. "
            "The failed checks are listed under Technical details.</p>",
        )
    for a in attention:
        if a.id == "sdc_applied":
            fmaps = sdc.get("dwi_fmaps", [])
            no_intended = [
                f"<code>{esc(f['file'])}</code>" for f in fmaps if not f["intended_for"]
            ]
            no_json = [
                f"<code>{esc(f['file'])}</code>" for f in fmaps if not f["has_json"]
            ]
            body = ""
            if no_intended:
                sidecar = (
                    f", and {', '.join(no_json)} has no sidecar" if no_json else ""
                )
                body = (
                    f"QSIPrep ran without TOPUP because the reverse phase-encoding b0 series in <code>sub-{sid}/fmap/</code> "
                    f"({', '.join(no_intended)}) have no <code>IntendedFor</code>{sidecar}. "
                )
            if "residual_shift_mm" in ids and shift:
                region, r = max(shift.items(), key=lambda kv: worst(kv[1]))
                body += f"FA sits up to {worst(r):.0f} mm off the T1 anatomy ({esc(region.split(' (')[0].lower())} region). "
            body += (
                f"Without it, frontal and temporal tensors can be shifted by a few mm {cite.dois(list(a.cite))}. For targets there, re-run QSIPrep with distortion correction "
                "(TI-Toolbox now adds <code>IntendedFor</code> to a usable fieldmap and falls back to SyN), then extract the tensor again."
            )
            callouts += c.callout(
                "warn", "No susceptibility distortion correction.", f"<p>{body}</p>"
            )
        elif not (a.id == "residual_shift_mm" and "sdc_applied" in ids):
            refs = cite.dois(list(a.cite)) if a.cite else ""
            callouts += c.callout(
                a.status,
                f"{esc(a.label)}: {esc(a.shown)} (rule {esc(a.threshold)}).",
                f"<p>{c.inline(a.description)} {refs}</p>",
            )
    gate_table = c.checks_table(
        [g for g in gates if g.role == "gate"],
        "The published-range check a user can act on; failing it stops the tensor "
        "from being written. Software consistency checks are under Technical details.",
        cite.dois,
    )
    verdict_sec = c.verdict_section(
        seal,
        headline,
        lede,
        callouts + f'<h3 class="sub">Quality gate</h3>{gate_table}',
    )

    # ── 2. preprocessing ──
    summary = []
    if sc.get("Manufacturer"):
        vox = (acq.get("raw_voxel_mm") or [None])[0]
        pe = sdc.get("pe_direction") or sc.get("PhaseEncodingDirection") or ""
        vox_txt = f", {vox:g} mm voxels" if vox else ""
        pe_txt = f", phase encoding {esc(_PE.get(pe, pe))}" if pe else ""
        summary.append(("Scanner", scanner + vox_txt + pe_txt))
    if bvals:
        summary.append(("Diffusion volumes", f"{len(bvals)}: {shells} s/mm²"))
    if q.get("version"):
        steps = [
            str(q[k])
            for k in ("denoise_method", "unringing_method")
            if q.get(k) not in (None, "none")
        ] + [f"{q.get('hmc_model')} motion/eddy correction"]
        res = q.get("output_resolution") or "?"
        summary.append(
            ("QSIPrep", f"{esc(q['version'])}: {esc(', '.join(steps))}; {res} mm AC-PC")
        )
    if sdc.get("reported") is not None:
        sdc_st = "pass" if sdc.get("applied") else "warn"
        summary.append(("Distortion correction", c.status(sdc_st, sdc["reported"])))
    n_fit = (
        f" ({sum(b <= bmax for b in bvals)} of {len(bvals)} volumes)" if bvals else ""
    )
    summary.append(
        ("Tensor fit", f"DIPY weighted least squares on b ≤ {bmax:g} s/mm²{n_fit}")
    )
    summary.append(
        (
            "To the head model",
            "QSIPrep's AC-PC→T1w transform, applied exactly; tensors rotated with it",
        )
    )
    if mot.get("mean_fd") is not None:
        summary.append(
            (
                "Head motion",
                f"mean framewise displacement {mot['mean_fd']:.2f} mm (largest step {mot['max_fd']:.2f} mm)",
            )
        )
    prep_sec = c.section(
        "preprocessing",
        "Preprocessing",
        c.kv(summary),
        lead="From the scanner to the tensor SimNIBS reads.",
    )

    # ── 3. registration ──
    planes = [("axial", "Axial"), ("coronal", "Coronal"), ("sagittal", "Sagittal")]
    panels = ""
    for key, name in planes:
        r = images["registration"][key]
        labels = c.tile_labels(r["labels"], r["cols"], r["tile"], r["shape"])
        flick = c.flicker(
            r["t1"], r["fa"], "T1w", "FA", f"{name} registration mosaic", labels
        )
        panels += f'<div data-panel="{key}">{flick}</div>'
    contours = c.legend([("WM boundary", "--wm-c"), ("pial boundary", "--pial-c")])
    reg_fig = c.figure(
        next(fig_no),
        "FA against the head-model T1",
        panels,
        f"The same charm contours on both images: {contours}"
        "On FA, bright white matter should fill the yellow outline; white matter spilling out on one side is residual distortion. "
        f"Slices at fixed {mni} coordinates; subject left is on image left. Press space on a focused image to switch.",
        c.segmented(planes, "Plane", "data-tab")
        + c.segmented(
            [("a", "T1w"), ("b", "FA"), ("auto", "Flicker")], "Image shown", "data-mode"
        ),
        cls="flick-fig",
        attrs='data-default="auto"',
    )
    reg_st = next(
        (
            a.status
            for a in advs
            if a.id == "residual_shift_mm" and a.status in ("pass", "warn")
        ),
        None,
    )
    reg_label = "Residual distortion" if reg_st == "warn" else "Aligned"
    reg_sec = c.section(
        "registration", "Registration", reg_fig, st=reg_st, st_label=reg_label
    )

    # ── 4. fibre orientation ──
    dec = images["dec"]
    sphere = "".join(
        c.label(
            name,
            f"left:{50 + 51 * u:.1f}%;top:{50 - 51 * v:.1f}%;transform:translate(-50%,-50%);color:#fff;font-weight:600;font-size:11px;text-shadow:0 0 3px #000",
        )
        for name, (u, v) in images["sphere_axes"].items()
    )
    sphere_img = c.img(
        images["sphere"],
        "Orientation legend: red left–right, green anterior–posterior, blue superior–inferior",
        "image/png",
    )
    overlay = (
        f'<div style="position:absolute;right:6px;bottom:6px;width:26%;aspect-ratio:1">{sphere_img}{sphere}</div>'
        + c.label("L", "left:6px;top:5px")
        + c.label("R", "right:6px;top:5px")
    )
    n_dec = next(fig_no)
    start = dec["z"].index(20) if 20 in dec["z"] else 0
    z_labels = [f"z = {z:+d}" for z in dec["z"]]
    dec_fig = c.figure(
        n_dec,
        "Principal diffusion direction",
        c.scrubber(
            n_dec,
            dec["frames"],
            z_labels,
            start,
            "Direction-encoded colour map, axial",
            extra=overlay,
        ),
        "Colour is the direction of the main fibre axis in world coordinates — red left–right, green anterior–posterior, blue "
        f"superior–inferior — scaled by FA. The corpus callosum should cross red and the corticospinal tracts run blue. Drag the slider ({mni} z).",
        cls="dec-fig",
    )
    ori = [
        a.status
        for a in advs
        if a.id in ("tract_frac_expected", "flip_identity_best") and a.status != "info"
    ]
    ori_st = max(ori, key=["pass", "warn", "fail"].index) if ori else None
    ori_label = {
        "pass": "Orientation correct",
        "warn": "Check orientation",
        "fail": "Orientation wrong",
    }.get(ori_st)
    ori_sec = c.section(
        "orientation", "Fibre orientation", dec_fig, st=ori_st, st_label=ori_label
    )

    # ── 5. FA and MD ──
    dist_body, lead = "", ""
    if tissue:
        present = [
            (t, v)
            for t, v in (("WM", "--s1"), ("GM", "--s2"), ("CSF", "--s3"))
            if t in tissue
        ]

        def series(key: str) -> list[dict]:
            return [
                {"label": t, "values": tissue[t][key], "var": v} for t, v in present
            ]

        fa_chart = c.hist_chart(
            series("fa_hist"), m["fa_bins"], xlabel="Fractional anisotropy"
        )
        md_chart = c.hist_chart(
            series("md_hist"),
            [b * 1e3 for b in m["md_bins"]],
            xlabel="Mean diffusivity (×10⁻³ mm²/s)",
            band=(md_lo * 1e3, md_hi * 1e3, "gate range (WM median)"),
            xlim=(0, 2.4),
        )
        keys = c.legend(
            [("White matter", "--s1"), ("Grey matter", "--s2"), ("CSF", "--s3")]
        )
        dist_body = c.figure(
            next(fig_no),
            "FA and MD by tissue",
            f'<div class="cols"><div>{fa_chart}</div><div>{md_chart}</div></div>',
            f"Share of voxels per bin within each charm tissue. {keys}Hover for bin values.",
        )
        rows = []
        for t, _ in present:
            s = tissue[t]
            rows.append(
                [
                    f'<span class="name">{t}</span>',
                    f"{s['n']:,}",
                    f"{s['fa_median']:.2f}",
                    f"{s['fa_iqr'][0]:.2f}–{s['fa_iqr'][1]:.2f}",
                    f"{s['md_median'] * 1e3:.2f}",
                    f"{s['md_iqr'][0] * 1e3:.2f}–{s['md_iqr'][1] * 1e3:.2f}",
                ]
            )
        dist_body += c.table(
            ["Tissue", "Voxels", "FA median", "FA IQR", "MD median", "MD IQR"],
            rows,
            caption="MD in ×10⁻³ mm²/s.",
            right={1, 2, 3, 4, 5},
        )
        if "WM" in tissue:
            ref = (qc.get("reference") or {}).get("wm_fa_median")
            ref_txt = f" (reference subject ernie {ref:.2f})" if ref is not None else ""
            lead = (
                f"White-matter median FA is {tissue['WM']['fa_median']:.2f}{ref_txt}; it varies with age and scanner "
                f"{cite.dois(RULES['dti']['wm_fa_median']['cite'])}. "
            )
    md_st = c.gate_status("wm_md_median", qc.get("failures", []))
    dist_sec = c.section(
        "diffusivity",
        "FA and MD by tissue",
        dist_body,
        lead=f"{lead}The white-matter median MD gate is {md_range}.",
        st=md_st,
        st_label="In range" if md_st == "pass" else "Out of range",
    )

    # ── 6. technical details ──
    body = c.checks_table(
        internal + advs,
        "Software checks block the tensor like the gate but test TI-Toolbox's own consistency, not "
        "published limits. Advisories never block; reported values have no pass/fail.",
        cite.dois,
    )
    if shift:
        body += c.table(
            ["Region", "A–P shift", "S–I shift"],
            [
                [esc(r), f"{v['best_ap_mm']:+.0f} mm", f"{v['best_si_mm']:+.0f} mm"]
                for r, v in shift.items()
            ],
            right={1, 2},
            caption="Residual distortion: the shift of smoothed FA that best matches charm's WM, per region (1 mm steps, ±5 mm; + is anterior or superior).",
        )
    if cond := m.get("conductivity"):
        body += (
            f'<p class="muted" style="font-size:13px;margin-top:12px">In SimNIBS the eigenvalue-ratio cap (<code>aniso_maxratio</code> = {cond["max_ratio"]:g}) '
            f"changes {cond['pct_wm_ratio_clamped']:.2f} % of white-matter voxels; in <code>vn</code> mode <code>aniso_maxcond</code> = {cond['max_cond']:g} "
            f"binds in {cond['pct_wm_vn_maxcond']:.1f} % (per voxel, before mesh interpolation).</p>"
        )
    failed_internal = any(g.status == "fail" for g in internal)
    tech = c.details(
        "All checks",
        body,
        "software checks, advisories and reported values",
        open_=failed_internal,
    )
    if mot.get("fd") and mot.get("mean_fd") is not None:
        keys = c.legend(
            [
                ("b = 0", "--ink"),
                (f"b ≤ {bmax:g}, in the fit", "--s1"),
                (f"b > {bmax:g}, not used", "--rule-strong"),
            ],
            dot=True,
        )
        chart = _motion_chart(bvals, mot["fd"], mot["mean_fd"], bmax)
        tech += c.details(
            "Head motion per volume",
            f"<div>{chart}</div>{keys}",
            "framewise displacement from QSIPrep's confounds",
        )
    paras = []
    if sc.get("Manufacturer") and q.get("version"):
        pre = []
        if q.get("denoise_method") == "dwidenoise":
            pre.append(f"MP-PCA denoising {cite('veraart2016_mppca')}")
        if q.get("unringing_method") == "mrdegibbs":
            pre.append(f"Gibbs-ringing removal {cite('kellner2016_gibbs')}")
        steps = (
            [" and ".join(pre) + f" in MRtrix3 {cite('tournier2019_mrtrix3')}"]
            if pre
            else []
        )
        steps.append(
            f"head-motion and eddy-current correction with FSL eddy {cite('andersson2016_eddy')}"
            if q.get("hmc_model") == "eddy"
            else "head-motion correction"
        )
        steps.append("rigid coregistration to the T1-weighted image")
        sdc_txt = (
            f"Susceptibility distortion was corrected ({esc(sdc['reported'])})."
            if sdc.get("applied")
            else "No susceptibility distortion correction was applied."
        )
        paras.append(
            f"Diffusion-weighted images ({scanner}; {len(bvals)} volumes: {shells} s/mm²) were preprocessed with QSIPrep "
            f"{esc(q['version'])} {cite('cieslak2021_qsiprep')}, based on Nipype {cite('gorgolewski2011_nipype')}: {', '.join(steps)}"
            f" and resampling to {q.get('output_resolution') or '?'} mm AC-PC space. {sdc_txt}"
        )
    paras.append(
        f"Diffusion tensors were fitted by weighted least squares in DIPY {cite('garyfallidis2014_dipy')} to the volumes with b ≤ {bmax:g} s/mm², "
        "mapped into the head model's T1 space with QSIPrep's AC-PC-to-T1w transform, resampled by normalised trilinear interpolation, "
        "reoriented by the rotation factor of that transform, and restricted to the dilated white- and grey-matter mask of the charm "
        f"segmentation {cite('puonti2020_charm')} (TI-Toolbox). The tensor was accepted when white-matter median diffusivity "
        f"lay in {md_range} {cite.dois(RULES['dti']['wm_md_median']['cite'])} and software consistency checks passed."
    )
    paras.append(
        "For anisotropic simulations, SimNIBS maps diffusion to conductivity tensors by direct scaling "
        "or volume normalisation."
    )
    tech += c.details(
        "Methods and references",
        c.methods(paras) + '<h3 class="sub">References</h3>' + cite.listing(),
        "boilerplate generated from this run; check before use",
    )
    versions = prov.get("versions", {})
    facts = [
        (name, esc(str(versions.get(k) or "not recorded")))
        for k, name in _VERSIONS.items()
        if k in versions
    ]
    if h := prov.get("config_hash"):
        facts.append(
            ("Configuration hash", f'<span class="hash" title="{h}">{h[:12]}</span>')
        )
    if prov.get("created"):
        facts.append(
            ("Recorded", f"{esc(prov['created'])} ({esc(prov.get('recorded_by', ''))})")
        )
    if g := m.get("grid"):
        facts.append(
            ("Grid", f"{' × '.join(map(str, g['shape']))}, {g['zooms'][0]:g} mm, RAS")
        )
    repro = c.kv(facts)
    if prov.get("inputs"):
        repro += '<h3 class="sub">Inputs</h3>' + c.table(
            ["Input", "Path", "SHA-256", "Size"],
            [
                [
                    f'<span class="name">{esc(k)}</span>',
                    f"<code>{esc(v['path'])}</code>",
                    f'<span class="hash" title="{v["sha256"]}">{v["sha256"][:16]}…</span>',
                    f"{v['bytes'] / 1e6:.1f} MB",
                ]
                for k, v in prov["inputs"].items()
            ],
            right={3},
        )
    if q.get("command"):
        repro += '<h3 class="sub">QSIPrep command</h3>' + c.code(q["command"])
    repro += '<h3 class="sub">DTI_coregT1_qc.json</h3>' + c.code(
        json.dumps(qc, indent=1)
    )
    tech += c.details("Reproducibility", repro, "versions, input hashes, the QC record")

    if not passed:
        tensor = ("Tensor", "<b>not written</b>")
    elif tensor_written:
        tensor = ("Tensor written", tensor_written.strftime(_STAMP))
    else:
        tensor = ("Tensor", "written")
    masthead = c.masthead(
        "Diffusion tensor quality control",
        f"sub-{subject_id}",
        [
            ("Subject", sid),
            tensor,
            ("QSIPrep", esc(str(q.get("version") or "—"))),
            ("Report", generated.strftime(_STAMP)),
        ],
    )
    toc = [
        ("verdict", "Verdict", seal),
        (
            "preprocessing",
            "Preprocessing",
            "warn" if sdc.get("reported") and not sdc.get("applied") else None,
        ),
        ("registration", "Registration", reg_st),
        ("orientation", "Fibre orientation", ori_st),
        ("diffusivity", "FA and MD", md_st),
        ("technical", "Technical details", "fail" if failed_internal else None),
    ]
    return c.page(
        title=f"sub-{subject_id} DTI QC",
        kind="Diffusion tensor QC",
        subject=f"sub-{subject_id}",
        toc=toc,
        body=masthead
        + verdict_sec
        + prep_sec
        + reg_sec
        + ori_sec
        + dist_sec
        + c.section("technical", "Technical details", tech),
        footer=f"<span>TI-Toolbox {esc(tit.__version__)}</span><span>Generated {generated.strftime(_STAMP)}</span>",
        description=f"Diffusion tensor quality control for sub-{subject_id}: {headline}",
        generator=f"TI-Toolbox {tit.__version__}",
        extra_css=EXTRA_CSS,
    )


def create_dti_qc_report(
    project_dir: str | Path,
    subject_id: str,
    qc: dict,
    vols,
    out_dir: str | Path | None = None,
) -> Path:
    """Render the images from *vols* (:class:`~tit.pre.qsi.dti_advisories.DtiVolumes`) and write the report.

    Written to ``derivatives/ti-toolbox/reports/sub-<id>/dti_qc_<timestamp>.html`` unless *out_dir*
    is given. Works for a failed gate too: *vols* holds the tensor that was computed but not written.
    """
    from tit import constants as const
    from tit.paths import get_path_manager
    from tit.plotting.dti_qc import render_all

    t0 = time.time()
    written = None
    if not qc.get("failures"):
        m2m = Path(get_path_manager(str(project_dir)).m2m(subject_id))
        tensor = m2m / const.FILE_DTI_TENSOR
        if tensor.is_file():
            written = datetime.fromtimestamp(tensor.stat().st_mtime)
    html = build_html(qc, render_all(vols), subject_id, tensor_written=written)
    out = (
        Path(out_dir)
        if out_dir
        else Path(get_path_manager(str(project_dir)).reports()) / f"sub-{subject_id}"
    )
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{REPORT_PREFIX}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path.write_text(html, encoding="utf-8")
    size = path.stat().st_size
    logger.info(
        f"DTI QC report: {path} ({size / 1e6:.2f} MB, {time.time() - t0:.0f} s)"
    )
    if size > SIZE_BUDGET:
        logger.warning(
            f"DTI QC report is {size / 1e6:.2f} MB, over its {SIZE_BUDGET / 1e6:.1f} MB budget"
        )
    return path


def main(argv: list[str] | None = None) -> int:
    """Rebuild a DTI QC report from the written tensor and QC record; advisories are measured if missing."""
    from tit import constants as const
    from tit.paths import get_path_manager
    from tit.pre.qsi.dti_advisories import load_volumes
    from tit.pre.qsi.dti_extractor import record_advisories

    parser = argparse.ArgumentParser(
        description="Rebuild a DTI QC report from an existing tensor and QC record."
    )
    parser.add_argument("project_dir")
    parser.add_argument("subject_id")
    parser.add_argument(
        "--out",
        help="write the report (and the completed QC record) here instead of into the project",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()
    m2m = Path(get_path_manager(args.project_dir).m2m(args.subject_id))
    qc = json.loads((m2m / const.FILE_DTI_QC).read_text())
    vols = load_volumes(m2m)
    if "advisories" not in qc:
        record_advisories(
            qc,
            vols,
            args.project_dir,
            args.subject_id,
            recorded_by="report rebuild",
            logger=logger,
        )
        if args.out:
            Path(args.out).mkdir(parents=True, exist_ok=True)
            (Path(args.out) / const.FILE_DTI_QC).write_text(
                json.dumps(qc, indent=1) + "\n"
            )
    path = create_dti_qc_report(
        args.project_dir, args.subject_id, qc, vols, out_dir=args.out
    )
    print(f"{path} {path.stat().st_size / 1e6:.2f} MB in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
