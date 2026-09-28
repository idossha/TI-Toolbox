"""Flex-search report: one self-contained HTML record per flex-search run.

Built on :mod:`tit.reporting.html.components` (ARCHITECTURE.md §14). Everything is read from the
run folder: ``flex_meta.json`` (goal, ROI, currents, electrode, every restart's value),
``candidate_history/NN/`` (the accepted candidate's ROI and background means and currents, and
the manifest's metric definitions), ``electrode_positions.json``, the ROI confirmation
(``roi.tetravox.json``) and the final per-channel simulations. Rules come from
``tit.reporting.qc_rules.RULES["opt"]``; the current check and the restart count are advisories.

Flex electrodes sit at free scalp positions. The cap figure is the app's EEG-cap overlay with each
electrode drawn at its nearest cap position (listed with the distance), for orientation only.

``tit.opt.flex`` writes one when a run finishes. Rebuild one (nothing is re-optimised)::

    simnibs_python -m tit.reporting.generators.flex_search <project> <subject> <run folder> [--out DIR]
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

from tit.reporting.generators import common
from tit.reporting.generators.common import fmt
from tit.reporting.generators.simulation import parse_fields_summary
from tit.reporting.html import components as c
from tit.reporting.html.components import Check, esc
from tit.reporting.qc_rules import RULES

logger = logging.getLogger(__name__)

REPORT_PREFIX = "flex_search_report"
SIZE_BUDGET = 1_000_000
#: The cap layout used to place free electrodes when the run names no net.
DEFAULT_NET = "EEG10-10_UI_Jurak_2007.csv"

_POSTPROC = {
    "max_TI": "the TI envelope in its strongest direction",
    "dir_TI_normal": "the TI envelope normal to the cortex",
    "dir_TI_tangential": "the TI envelope tangential to the cortex",
}


_BACKGROUND = {
    "everything_else": "everything outside the target, in the optimised tissue",
    "specific": "a second region you chose",
}
_METRIC = {
    "roi_mean": "Target mean",
    "roi_p99_9": "Target 99.9th pct",
    "non_roi_mean": "Background mean",
    "non_roi_p95": "Background 95th pct",
    "target_background_ratio": "Target ÷ background",
}


def goal_words(meta: dict) -> tuple[str, str, float]:
    """``(what the goal maximises, what the score means, the score as a user reads it)``.

    The optimiser minimises, so every score is the negative of the quantity it maximises.
    """
    goal, v = meta.get("goal"), -float(meta["result"]["best_value"])
    w = float(meta.get("intensity_weight") or 0.0)
    if goal == "mean":
        return "the mean field in the target", f"mean target field {v:.3f} V/m", v
    if goal == "max":
        return (
            "the peak (99.9th percentile) field in the target",
            f"peak target field {v:.3f} V/m",
            v,
        )
    if goal == "focality":
        return (
            "focality by SimNIBS's threshold-based ROC measure",
            f"ROC focality score {v:.2f} (100 × (√2 − ROC distance); higher is more focal)",
            v,
        )
    power = "" if not w else f"<sup>{1 + w:g}</sup>"
    return (
        "the target's mean field relative to everywhere else",
        f"target mean{power} {v:.2f}× the background mean",
        v,
    )


def _best_rows(run_dir: Path) -> list[dict]:
    """Per restart: the accepted candidate's row (``candidates.csv``) plus its manifest."""
    out = []
    for hist in sorted((run_dir / "candidate_history").glob("*")):
        manifest = (
            json.loads((hist / "candidate_manifest.json").read_text())
            if (hist / "candidate_manifest.json").is_file()
            else {}
        )
        row = {}
        if (hist / "candidates.csv").is_file():
            accepted = manifest.get("accepted_candidate_id")
            for r in csv.DictReader((hist / "candidates.csv").open()):
                if r["candidate_id"] == accepted or (
                    not accepted
                    and (not row or float(r["objective"]) < float(row["objective"]))
                ):
                    row = r
        out.append({"restart": hist.name, "row": row, "manifest": manifest})
    return out


def nearest_cap(positions: list[list[float]], eeg_csv: Path) -> dict | None:
    """Each optimised position's nearest distinct electrode of the net (Hungarian assignment,
    :func:`tit.tools.map_electrodes.map_electrodes_to_net`), with the distance in mm."""
    import numpy as np

    from tit.opt.ex.buckets import _read_eeg_positions
    from tit.tools.map_electrodes import map_electrodes_to_net

    net = {k: v for k, v in _read_eeg_positions(eeg_csv).items() if len(v) == 3}
    if not net or not positions:
        return None
    labels = list(net)
    result = map_electrodes_to_net(
        np.asarray(positions, float),
        np.asarray([net[k] for k in labels], float),
        labels,
        list(range(len(positions))),
    )
    order = sorted(
        range(len(positions)), key=lambda i: result["channel_array_indices"][i]
    )
    return {
        "net": eeg_csv.name,
        "labels": [result["mapped_labels"][i] for i in order],
        "distances": [float(result["distances"][i]) for i in order],
    }


def collect(run_dir: str | Path, eeg_positions_dir: str | Path | None = None) -> dict:
    """Everything the report shows, from one flex-search run folder."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "flex_meta.json").read_text())
    pos_file = run_dir / "electrode_positions.json"
    positions = json.loads(pos_file.read_text()) if pos_file.is_file() else {}
    mapping_file = run_dir / "electrode_mapping.json"
    mapping = json.loads(mapping_file.read_text()) if mapping_file.is_file() else None
    carriers = []
    for d in sorted(run_dir.glob("final_sim_*")):
        f = d / "fields_summary.txt"
        if f.is_file():
            carriers += parse_fields_summary(f.read_text())
    logs = sorted(run_dir.glob("simnibs_optimization_*.log"))
    simnibs = None
    if logs:
        m = re.search(r"simnibs (\d[\w.]*)", logs[-1].read_text(errors="replace"))
        simnibs = m.group(1) if m else None
    summary = run_dir / "summary.txt"
    calib = (
        re.search(
            r"calibration error exceeded 10%! Estimated error value: ([\d.]+)%",
            summary.read_text(),
        )
        if summary.is_file()
        else None
    )
    rec = {
        "run": run_dir.name,
        "meta": meta,
        "restarts": _best_rows(run_dir),
        "positions": positions.get("optimized_positions") or [],
        "channel_array": positions.get("channel_array_indices") or [],
        "mapping": mapping,
        "carriers": carriers,
        "roi": common.roi_summary(run_dir),
        "simnibs": simnibs,
        "calibration_error_pct": float(calib.group(1)) if calib else None,
        "cap": None,
    }
    config = (
        rec["restarts"][0]["manifest"].get("config") if rec["restarts"] else None
    ) or {}
    rec["config"] = config
    if eeg_positions_dir and rec["positions"]:
        net = config.get("eeg_net") or DEFAULT_NET
        csv_path = Path(eeg_positions_dir) / net
        if csv_path.is_file():
            rec["cap"] = nearest_cap(rec["positions"], csv_path)
    return rec


def currents(rec: dict) -> list[float]:
    """Per-channel currents of the accepted montage (the searched split when there is one)."""
    meta = rec["meta"]
    best = (
        rec["restarts"][meta["result"].get("best_run_index") or 0]["row"]
        if rec["restarts"]
        else {}
    )
    if best.get("current_ch1_mA"):
        return [float(best["current_ch1_mA"]), float(best["current_ch2_mA"])]
    if meta.get("current_split"):
        return [float(v) for v in meta["current_split"]]
    return [float(meta["current_mA"])] * 2


def checks(rec: dict) -> list[Check]:
    meta = rec["meta"]
    values = [
        v
        for v in meta["result"].get("all_values") or []
        if v is not None and abs(v) < 1e30
    ]
    n = len(values)
    r = RULES["opt"]["n_valid_restarts"]
    rows = [
        common.rule_check(
            "opt",
            "n_valid_restarts",
            "pass" if n >= r["value"] else "warn",
            f"{n} of {len(meta['result'].get('all_values') or [])}",
            f"≥ {r['value']}",
        )
    ]
    if n >= 2:
        best = min(values)
        spread = (
            f"{100 * (max(values) - min(values)) / abs(best):.1f} % of the best score"
        )
    else:
        spread = "not measurable with one run"
    rows.append(common.rule_check("opt", "restart_spread", "info", spread))
    rows.append(common.current_check("opt", currents(rec)))
    return rows


def _pairs(rec: dict) -> list[list[str]] | None:
    labels = (rec["mapping"] or {}).get("mapped_labels") or (rec["cap"] or {}).get(
        "labels"
    )
    if not labels or len(labels) < 4:
        return None
    return [labels[i : i + 2] for i in range(0, len(labels) - 1, 2)]


def build_html(rec: dict, subject_id: str, generated: datetime | None = None) -> str:
    import tit

    generated = generated or datetime.now()
    meta, roi = rec["meta"], rec["roi"] or {"name": "target ROI"}
    cite = c.Cites()
    fig_no = iter(range(1, 20))
    success = bool(meta["result"].get("success"))
    rows = checks(rec)
    advisories = [r for r in rows if r.role == "advisory"]
    seal, _ = c.verdict(rows)
    mA = currents(rec)
    total = sum(mA)
    el = meta.get("electrode") or {}
    dims = "×".join(f"{d:g}" for d in el.get("dimensions") or [])
    best_i = meta["result"].get("best_run_index") or 0
    best = rec["restarts"][best_i]["row"] if rec["restarts"] else {}
    defs = (
        rec["restarts"][best_i]["manifest"].get("metric_definitions", {})
        if rec["restarts"]
        else {}
    )
    roi_name = esc(roi["name"])

    # ── 1. verdict ──
    if success:
        maximises, score_txt, _ = goal_words(meta)
        headline = f"Best montage: {re.sub('<[^>]+>', '', score_txt)}"
        lede = (
            f"Flex-search placed {len(mA)} channels of {esc(el.get('shape', ''))} {dims} mm electrodes freely on the scalp "
            f"to maximise {maximises} in the <b>{roi_name}</b>, using {esc(_POSTPROC.get(meta.get('postproc'), meta.get('postproc', '')))}."
        )
        key = []
        if best.get("roi_mean"):
            key.append(
                (
                    "Target mean",
                    f"{float(best['roi_mean']):.3f}<small>V/m</small>",
                    f"99.9th pct {float(best['roi_p99_9']):.3f} V/m",
                )
            )
            key.append(
                (
                    "Background mean",
                    f"{float(best['non_roi_mean']):.3f}<small>V/m</small>",
                    "everywhere else",
                )
            )
            if best.get("target_background_ratio"):
                key.append(
                    (
                        "Target ÷ background",
                        f"{float(best['target_background_ratio']):.2f}<small>×</small>",
                        "mean over mean",
                    )
                )
        key.append(
            (
                "Currents",
                f"{' / '.join(fmt(v) for v in mA)}<small>mA</small>",
                f"{fmt(total)} mA total",
            )
        )
    else:
        seal, headline = "fail", "No valid montage found"
        lede = "Every optimiser run failed to accept a valid electrode placement. See the run log in the output folder."
        key = []
    extra = common.attention_callouts(advisories, cite) + (c.stats(key) if key else "")
    verdict_sec = c.verdict_section(seal, headline, lede, extra)

    # ── 2. target and goal ──
    target = [("Target", roi_name)]
    if roi.get("atlas"):
        target.append(("Atlas", esc(roi["atlas"])))
    if roi.get("volume_mm3"):
        target.append(
            (
                "Size",
                f"{roi['volume_mm3'] / 1000:.1f} cm³"
                + (
                    f", {100 * roi['gm_overlap']:.0f} % grey matter"
                    if roi.get("gm_overlap") is not None
                    else ""
                ),
            )
        )
    if roi.get("centroid"):
        target.append(
            (
                "Centre",
                "({:.0f}, {:.0f}, {:.0f}) mm, subject space".format(*roi["centroid"]),
            )
        )
    g = RULES["opt"]["goal_definition"]
    goal_rows = [
        (
            "Goal",
            f"<code>{esc(meta.get('goal', ''))}</code>: {goal_words(meta)[0] if success else ''}",
        ),
        (
            "Background",
            _BACKGROUND.get(
                meta.get("non_roi_method"), esc(str(meta.get("non_roi_method") or "—"))
            ),
        ),
    ]
    for k, v in defs.items():
        goal_rows.append((_METRIC.get(k, k.replace("_", " ")), esc(v)))
    target_sec = c.section(
        "target",
        "Target and goal",
        c.kv(target)
        + '<h3 class="sub">How the score is measured</h3>'
        + c.kv(goal_rows)
        + f'<p class="muted" style="font-size:13px;margin-top:10px">{c.inline(g["plain"])} {cite.dois(g["cite"])}</p>',
        lead="What the optimiser aimed at, in the words it used.",
    )

    # ── 3. best montage ──
    body = ""
    pairs = _pairs(rec)
    if pairs:
        mapped = rec["mapping"] is not None
        body += common.cap_figure(
            next(fig_no),
            pairs,
            (rec["cap"] or {}).get("net")
            or rec["config"].get("eeg_net")
            or DEFAULT_NET,
            mA,
            "Top view, nose up. "
            + (
                "Electrodes as mapped to the net by the run."
                if mapped
                else "Flex electrodes sit at free positions; each is drawn at its nearest cap position (distances below), for orientation only."
            ),
        )
    if rec["positions"]:
        near = rec["cap"] or {}
        pos_rows = []
        for i, p in enumerate(rec["positions"]):
            ch, arr = (
                rec["channel_array"][i]
                if i < len(rec["channel_array"])
                else (i // 2, i % 2)
            )
            nearest = (
                f"{esc(near['labels'][i])} ({near['distances'][i]:.0f} mm)"
                if near.get("labels")
                else "—"
            )
            pos_rows.append(
                [
                    f"Ch {ch + 1}",
                    "+" if arr == 0 else "−",
                    "({:.1f}, {:.1f}, {:.1f})".format(*p),
                    nearest,
                ]
            )
        body += c.table(
            ["Channel", "Pole", "Position (mm, subject)", "Nearest cap electrode"],
            pos_rows,
            caption="Optimised electrode centres on the scalp.",
            right={2},
        )
    d = RULES["opt"]["dose_record"]
    dose = [
        (
            "Electrodes",
            esc(
                f"{el.get('shape', '?')} {dims} mm, gel {el.get('gel_thickness', '?')} mm"
            ),
        ),
        (
            "Currents",
            f"{' / '.join(fmt(v) for v in mA)} mA per channel, {fmt(total)} mA total"
            + (" (split searched)" if meta.get("optimize_current_ratio") else ""),
        ),
        (
            "Carrier frequencies",
            "not part of the field model (quasi-static); set them on the stimulator",
        ),
        ("Minimum electrode distance", f"{meta.get('min_electrode_distance', '—')} mm"),
    ]
    body += (
        '<h3 class="sub">Dose record</h3>'
        + c.kv(dose)
        + (
            f'<p class="muted" style="font-size:13px;margin-top:10px">{c.inline(d["plain"])} {cite.dois(d["cite"])}</p>'
        )
    )
    montage_sec = c.section(
        "montage",
        "Best montage",
        body,
        lead="Where to place the electrodes and how much current to use.",
    )

    # ── 4. runs ──
    run_rows = []
    for i, r in enumerate(rec["restarts"]):
        row, man = r["row"], r["manifest"]
        val = (meta["result"].get("all_values") or [None] * (i + 1))[i]
        ok = val is not None and abs(val) < 1e30
        run_rows.append(
            [
                f"{i + 1}" + (" (best)" if i == best_i and success else ""),
                (f"{-val:.3f}", -val) if ok else ("failed", -1e9),
                (
                    (f"{float(row['roi_mean']):.3f}", float(row["roi_mean"]))
                    if row.get("roi_mean")
                    else "—"
                ),
                (
                    (f"{float(row['non_roi_mean']):.3f}", float(row["non_roi_mean"]))
                    if row.get("non_roi_mean")
                    else "—"
                ),
                (f"{man.get('valid_candidates', 0):,}", man.get("valid_candidates", 0)),
                (f"{man.get('evaluations', 0):,}", man.get("evaluations", 0)),
            ]
        )
    runs = c.table(
        [
            "Run",
            "Score",
            "Target mean (V/m)",
            "Background mean (V/m)",
            "Valid placements",
            "Evaluations",
        ],
        run_rows,
        caption="One row per independent optimiser run (multi-start); the score is the quantity the goal maximises.",
        right={1, 2, 3, 4, 5},
        sortable=len(run_rows) > 1,
    )
    runs += c.checks_table(
        [r for r in rows if r.id in ("n_valid_restarts", "restart_spread")],
        "Agreement between runs is the only check on a single optimum.",
        cite.dois,
    )
    runs_st = next(r.status for r in rows if r.id == "n_valid_restarts")
    runs_sec = c.section(
        "runs",
        "Optimiser runs",
        runs,
        st=runs_st,
        st_label="Agree" if runs_st == "pass" else "One run",
    )

    # ── 5. safety ──
    safety = [r for r in rows if r.id == "electrode_peak_current"]
    n_attn = sum(r.status in ("warn", "fail") for r in safety)
    safety_sec = c.section(
        "safety",
        "Safety advisory",
        c.checks_table(
            safety,
            "Advisories never block; they compare this dose with published evidence.",
            cite.dois,
        ),
        st="warn" if n_attn else "pass",
        st_label="Review" if n_attn else "Within evidence",
    )

    # ── 6. technical details ──
    tech = ""
    if rec["carriers"]:
        pct = [k for k in rec["carriers"][0] if k.startswith("p")]
        tech += c.details(
            "Final simulation per channel",
            c.table(
                ["Channel"] + [f"{k[1:]} %" for k in pct],
                [
                    [f"Ch {i + 1}"] + [f"{cr[k]:.3f}" for k in pct]
                    for i, cr in enumerate(rec["carriers"])
                ],
                caption="Each channel alone at its current, grey-matter |E| percentiles (V/m) from SimNIBS's field summary.",
                right=set(range(1, 1 + len(pct))),
            )
            + (
                f'<p class="muted" style="font-size:13px;margin-top:10px">SimNIBS estimated the current calibration error at {rec["calibration_error_pct"]:g} %, above its 10 % warning.</p>'
                if rec["calibration_error_pct"]
                else ""
            ),
            "the winning electrodes simulated one channel at a time",
        )
    man = rec["restarts"][best_i]["manifest"] if rec["restarts"] else {}
    term = (man.get("optimizer_termination") or {}).get("global") or {}
    paras = [
        f"Electrode positions for temporal interference stimulation {cite('grossman2017_ti')} were optimised in TI-Toolbox "
        f"{cite('haber2026_titoolbox')} with SimNIBS {esc(rec['simnibs'] or '')} {cite('saturnino2019_simnibs21')} and its leadfield-free "
        f"framework {cite.dois(['10.1016/j.compbiomed.2025.110648'])}, on the head model of subject {esc(subject_id)} {cite('puonti2020_charm')}. "
        f"Two channels of {esc(el.get('shape', ''))} {dims} mm electrodes were placed by differential evolution "
        f"({len(rec['restarts'])} run{'s' if len(rec['restarts']) != 1 else ''}"
        + (
            f", {term['evaluations']:,} evaluations and {term.get('iterations', '?')} iterations in the best"
            if term.get("evaluations")
            else ""
        )
        + f") to maximise {goal_words(meta)[0] if success else 'the goal'} in the {roi_name}.",
    ]
    if success and best.get("roi_mean"):
        paras.append(
            f"The best montage gave a mean envelope of {float(best['roi_mean']):.3f} V/m in the target and "
            f"{float(best['non_roi_mean']):.3f} V/m elsewhere at {' / '.join(fmt(v) for v in mA)} mA."
        )
    tech += c.details(
        "Methods and references",
        c.methods(paras) + '<h3 class="sub">References</h3>' + cite.listing(),
        "boilerplate generated from this run; check before use",
    )
    run = [
        ("Run folder", esc(rec["run"])),
        ("Created", esc(str(meta.get("created", "—")).replace("T", " ")[:16])),
        ("TI-Toolbox", esc(tit.__version__)),
        ("SimNIBS", esc(rec["simnibs"] or "not recorded")),
        ("Conductivity", esc(rec["config"].get("anisotropy_type", "—"))),
    ]
    tech += c.details(
        "Run record",
        c.kv(run)
        + '<h3 class="sub">flex_meta.json</h3>'
        + c.code(json.dumps(meta, indent=1)),
        "versions and the manifest as written",
    )

    masthead = c.masthead(
        "Flex-search",
        f"sub-{subject_id}, {rec['run']}",
        [
            ("Subject", esc(subject_id)),
            ("Goal", esc(meta.get("goal", "—"))),
            ("Runs", str(len(rec["restarts"]))),
            ("Report", generated.strftime(common.STAMP)),
        ],
    )
    toc = [
        ("verdict", "Verdict", seal),
        ("target", "Target and goal", None),
        ("montage", "Best montage", None),
        ("runs", "Optimiser runs", runs_st),
        ("safety", "Safety advisory", "warn" if n_attn else "pass"),
        ("technical", "Technical details", None),
    ]
    return c.page(
        title=f"sub-{subject_id} flex-search",
        kind="Flex-search report",
        subject=f"sub-{subject_id}",
        toc=toc,
        body=masthead
        + verdict_sec
        + target_sec
        + montage_sec
        + runs_sec
        + safety_sec
        + c.section("technical", "Technical details", tech),
        footer=common.footer(generated),
        description=f"Flex-search report for sub-{subject_id}, {rec['run']}: {headline}",
        generator=f"TI-Toolbox {tit.__version__}",
    )


def create_flex_search_report(
    project_dir: str | Path,
    subject_id: str,
    run_dir: str | Path,
    out_dir: str | Path | None = None,
) -> Path:
    """Write the report for one flex-search run folder; into the project's reports unless *out_dir*."""
    from tit.paths import get_path_manager

    t0 = time.time()
    pm = get_path_manager(str(project_dir))
    rec = collect(run_dir, pm.eeg_positions(subject_id))
    return common.write_report(
        build_html(rec, subject_id),
        project_dir,
        subject_id,
        REPORT_PREFIX,
        SIZE_BUDGET,
        out_dir,
        t0,
        label="Flex-search report",
    )


def main(argv: list[str] | None = None) -> int:
    from tit.paths import get_path_manager

    parser = argparse.ArgumentParser(
        description="Rebuild a flex-search report from its run folder."
    )
    parser.add_argument("project_dir")
    parser.add_argument("subject_id")
    parser.add_argument("run", help="run folder name under flex-search/, or a path")
    parser.add_argument(
        "--out", help="write the report here instead of into the project"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()
    run = Path(args.run)
    if not run.is_dir():
        run = (
            Path(get_path_manager(args.project_dir).flex_search(args.subject_id))
            / args.run
        )
    path = create_flex_search_report(args.project_dir, args.subject_id, run, args.out)
    print(f"{path} {path.stat().st_size / 1e6:.2f} MB in {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
