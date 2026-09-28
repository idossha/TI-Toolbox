"""Flex-search report: one self-contained HTML record per flex-search run.

Built on :mod:`tit.reporting.html.components` (ARCHITECTURE.md §14). Everything is read from the
run folder: ``flex_meta.json`` (goal, ROI, currents, electrode, every restart's value),
``candidate_history/NN/`` (the accepted candidate's ROI and background means and currents, and
the manifest's metric definitions), ``electrode_positions.json``, the ROI confirmation
(``roi.tetravox.json``), the final per-channel simulations and the run's own figures
(``valid_skin_region.png``, ``roi.png``, embedded as WebP). Rules come from
``tit.reporting.qc_rules.RULES["opt"]``.

Flex electrodes sit at free scalp positions, so they are listed by coordinate, not drawn on a cap.

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
from tit.reporting.html.components import esc
from tit.reporting.qc_rules import RULES

logger = logging.getLogger(__name__)

REPORT_PREFIX = "flex_search_report"
SIZE_BUDGET = 1_000_000
#: The run's own figures the report embeds, with their WebP width (px).
_RUN_FIGURES = {"roi.png": 1200, "valid_skin_region.png": 1000}

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


def run_figures(run_dir: Path) -> dict[str, bytes]:
    """``{file name: WebP bytes}`` for each of :data:`_RUN_FIGURES` the run wrote."""
    import io

    from PIL import Image

    out = {}
    for name, width in _RUN_FIGURES.items():
        if (run_dir / name).is_file():
            image = Image.open(run_dir / name)
            image.thumbnail((width, width))
            buf = io.BytesIO()
            image.save(buf, "WEBP", quality=80, method=6)
            out[name] = buf.getvalue()
    return out


def _run_figure(rec: dict, fig_no, name: str, title: str, caption: str) -> str:
    image = rec["figures"].get(name)
    return (
        c.figure(next(fig_no), title, c.img(image, caption), caption) if image else ""
    )


def collect(run_dir: str | Path) -> dict:
    """Everything the report shows, from one flex-search run folder."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "flex_meta.json").read_text())
    pos_file = run_dir / "electrode_positions.json"
    positions = json.loads(pos_file.read_text()) if pos_file.is_file() else {}
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
        "carriers": carriers,
        "roi": common.roi_summary(run_dir),
        "simnibs": simnibs,
        "calibration_error_pct": float(calib.group(1)) if calib else None,
        "figures": run_figures(run_dir),
    }
    config = (
        rec["restarts"][0]["manifest"].get("config") if rec["restarts"] else None
    ) or {}
    rec["config"] = config
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


def build_html(rec: dict, subject_id: str, generated: datetime | None = None) -> str:
    import tit

    generated = generated or datetime.now()
    meta, roi = rec["meta"], rec["roi"] or {"name": "target ROI"}
    cite = c.Cites()
    fig_no = iter(range(1, 20))
    success = bool(meta["result"].get("success"))
    seal = "pass"
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
                f"{common.per_channel(mA)}<small>mA</small>",
                f"{fmt(total)} mA total",
            )
        )
    else:
        seal, headline = "fail", "No valid montage found"
        lede = "Every optimiser run failed to accept a valid electrode placement. See the run log in the output folder."
        key = []
    extra = c.stats(key) if key else ""
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
        + _run_figure(
            rec,
            fig_no,
            "roi.png",
            "The target",
            "The target on the subject's T1 in three planes, as the run confirmed it.",
        )
        + '<h3 class="sub">How the score is measured</h3>'
        + c.kv(goal_rows)
        + f'<p class="muted" style="font-size:13px;margin-top:10px">{c.inline(g["plain"])} {cite.dois(g["cite"])}</p>',
        lead="What the optimiser aimed at, in the words it used.",
    )

    # ── 3. best montage ──
    body = _run_figure(
        rec,
        fig_no,
        "valid_skin_region.png",
        "Where electrodes could go",
        "Scalp the optimiser could place electrodes on (green) and excluded scalp (grey), "
        "seen from above, the front and both sides.",
    )
    if rec["positions"]:
        pos_rows = []
        for i, p in enumerate(rec["positions"]):
            ch, arr = (
                rec["channel_array"][i]
                if i < len(rec["channel_array"])
                else (i // 2, i % 2)
            )
            pos_rows.append(
                [
                    f"Ch {ch + 1}",
                    "+" if arr == 0 else "−",
                    "({:.1f}, {:.1f}, {:.1f})".format(*p),
                ]
            )
        body += c.table(
            ["Channel", "Pole", "Position (mm, subject)"],
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
            f"{common.per_channel(mA)} mA per channel, {fmt(total)} mA total"
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
    runs_sec = c.section(
        "runs",
        "Optimiser runs",
        runs,
    )

    # ── 5. technical details ──
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
        "Electrode positions for temporal interference stimulation were optimised in TI-Toolbox "
        f"with SimNIBS {esc(rec['simnibs'] or '')} {cite('saturnino2019_simnibs21')} and its leadfield-free "
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
            f"{float(best['non_roi_mean']):.3f} V/m elsewhere at {common.per_channel(mA)} mA."
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
        ("runs", "Optimiser runs", None),
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
    t0 = time.time()
    rec = collect(run_dir)
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
