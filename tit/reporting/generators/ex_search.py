"""Ex-search report: one self-contained HTML record per exhaustive montage search.

Built on :mod:`tit.reporting.html.components` (ARCHITECTURE.md §14). Everything is read from the
run folder: ``run_config.json`` (buckets, current sweep, ROI name and radius, leadfield),
``final_output.csv`` (one row per montage and current split), the ROI confirmation
(``roi.tetravox.json``) and the leadfield's SimNIBS log (electrode geometry, conductivity).
Rules come from ``tit.reporting.qc_rules.RULES["opt"]``; the current check is an advisory.

The default view is the winner (ranked by composite = ROI mean × focality) on the app's EEG-cap
overlay with its dose, one chart of every montage's ROI mean against focality, the top 25 as a
sortable table, and the ROI and ranking in words; methods and the run record are collapsed.

``tit.opt.ex`` writes one when a search finishes. Rebuild one (nothing is re-searched)::

    simnibs_python -m tit.reporting.generators.ex_search <project> <subject> <run name> [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import time
from datetime import datetime
from pathlib import Path

from tit.reporting.generators import common
from tit.reporting.generators.common import fmt
from tit.reporting.html import components as c
from tit.reporting.html.components import Check, esc
from tit.reporting.qc_rules import RULES

logger = logging.getLogger(__name__)

REPORT_PREFIX = "ex_search_report"
SIZE_BUDGET = 1_000_000
TOP_N = 25
_FIELDS = ("TImax_ROI", "TImean_ROI", "TImean_GM", "Focality", "Composite_Index")


def read_results(csv_path: str | Path) -> list[dict]:
    """``final_output.csv`` rows with numbers as floats, ranked by composite (best first)."""
    from tit.opt.ex.results import parse_montage_string

    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                row = {k: float(r[k]) for k in _FIELDS}
                row["I1"], row["I2"] = float(r["Current_Ch1_mA"]), float(
                    r["Current_Ch2_mA"]
                )
            except (KeyError, TypeError, ValueError):
                continue
            e = parse_montage_string(r["Montage"])
            row["pairs"] = [e[i : i + 2] for i in range(0, len(e), 2)]
            rows.append(row)
    rows.sort(key=lambda r: r["Composite_Index"], reverse=True)
    return rows


def leadfield_facts(log_text: str) -> dict:
    """Electrode geometry and conductivity the leadfield was computed with (its SimNIBS log)."""

    def first(pattern: str) -> str | None:
        m = re.search(pattern, log_text)
        return m.group(1).strip() if m else None

    return {
        "shape": first(r"\nshape: (\S+)"),
        "dimensions": first(r"\ndimensions: \[([^\]]*)\]"),
        "thickness": first(r"\nthickness:\s*\[([^\]]*)\]"),
        "tensor": first(r"Using anisotropic .*? based on the file: (\S+)"),
        "simnibs": first(r"simnibs (\d[\w.]*)"),
    }


def collect(run_dir: str | Path, leadfield_dir: str | Path | None = None) -> dict:
    """Everything the report shows, from one ex-search run folder."""
    run_dir = Path(run_dir)
    cfg = json.loads((run_dir / "run_config.json").read_text())
    lf = {}
    if leadfield_dir:
        logs = sorted(Path(leadfield_dir).glob("simnibs_simulation_*.log"))
        if logs:
            lf = leadfield_facts(logs[-1].read_text(errors="replace"))
    return {
        "run": run_dir.name,
        "config": cfg,
        "rows": read_results(run_dir / "final_output.csv"),
        "roi": common.roi_summary(run_dir),
        "leadfield": lf,
    }


def net_of(cfg: dict) -> str:
    from tit.opt.ex.symmetry import net_name_from_leadfield

    return net_name_from_leadfield(cfg.get("leadfield_hdf", ""))


def checks(rec: dict) -> list[Check]:
    best = rec["rows"][0]
    return [common.current_check("opt", [best["I1"], best["I2"]])]


def _montage_name(pairs: list[list[str]]) -> str:
    return " ‖ ".join("–".join(p) for p in pairs)


def density_chart(rows: list[dict], top: int = TOP_N) -> str:
    """Every montage as ROI mean against focality: a log-shaded density grid, the top *top* as
    rings, the winner filled, and three curves of equal composite (ROI mean × focality).
    """
    width, height, ml, mr, mt, mb = 720, 380, 50, 16, 16, 40
    pw, ph = width - ml - mr, height - mt - mb
    xs = [r["TImean_ROI"] for r in rows]
    ys = [r["Focality"] for r in rows]
    x0, x1 = 0.0, max(xs) * 1.05
    y0, y1 = min(ys) * 0.97, max(ys) * 1.03
    nx, ny = 72, 40

    def X(v: float) -> float:
        return ml + (v - x0) / (x1 - x0) * pw

    def Y(v: float) -> float:
        return mt + ph - (v - y0) / (y1 - y0) * ph

    cells: dict[tuple[int, int], int] = {}
    for x, y in zip(xs, ys):
        key = (
            min(int((x - x0) / (x1 - x0) * nx), nx - 1),
            min(int((y - y0) / (y1 - y0) * ny), ny - 1),
        )
        cells[key] = cells.get(key, 0) + 1
    peak = math.log10(max(cells.values()) + 1)
    cw, ch = pw / nx, ph / ny
    p = [
        f'<svg class="chart" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="ROI mean against focality for {len(rows):,} montages; the top {top} and the winner marked">'
    ]
    for t in c.nice_ticks(y0, y1, 5):
        p.append(
            f'<line class="grid" x1="{ml}" x2="{ml + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>'
            f'<text x="{ml - 6}" y="{Y(t) + 4:.1f}" text-anchor="end">{t:g}</text>'
        )
    for t in c.nice_ticks(x0, x1, 6):
        p.append(
            f'<text x="{X(t):.1f}" y="{mt + ph + 16}" text-anchor="middle">{t:g}</text>'
        )
    for (i, j), n in sorted(cells.items()):
        a = 0.12 + 0.88 * math.log10(n + 1) / peak
        lo_x, lo_y = x0 + i * (x1 - x0) / nx, y0 + j * (y1 - y0) / ny
        tip = (
            f"{n:,} montage{'s' if n > 1 else ''}\nROI mean {lo_x:.3f}–{lo_x + (x1 - x0) / nx:.3f} V/m"
            f"\nfocality {lo_y:.2f}–{lo_y + (y1 - y0) / ny:.2f}"
        )
        p.append(
            f'<rect x="{ml + i * cw:.1f}" y="{mt + ph - (j + 1) * ch:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
            f'fill="var(--s1)" fill-opacity="{a:.2f}" data-tip="{esc(tip)}"/>'
        )
    best = rows[0]["Composite_Index"]
    for k in (0.5, 0.75):
        level = best * k
        pts = []
        for s in range(61):
            x = x0 + (x1 - x0) * s / 60
            if x > 0 and y0 <= level / x <= y1:
                pts.append(f"{X(x):.1f},{Y(level / x):.1f}")
        if len(pts) > 1:
            p.append(
                f'<polyline points="{" ".join(pts)}" fill="none" stroke="var(--ink-3)" stroke-width="1" stroke-dasharray="3 4"/>'
                f'<text x="{pts[-1].split(",")[0]}" y="{float(pts[-1].split(",")[1]) - 5:.1f}" text-anchor="end">composite {level:.3f}</text>'
            )
    for r in rows[1:top]:
        p.append(
            f'<circle cx="{X(r["TImean_ROI"]):.1f}" cy="{Y(r["Focality"]):.1f}" r="4.5" fill="none" stroke="var(--s2)" stroke-width="1.6" '
            f'data-tip="{esc(_montage_name(r["pairs"]))}\n{r["I1"]:g}/{r["I2"]:g} mA: ROI mean {r["TImean_ROI"]:.3f} V/m, focality {r["Focality"]:.2f}"/>'
        )
    w = rows[0]
    wx, wy = X(w["TImean_ROI"]), Y(w["Focality"])
    p.append(
        f'<circle cx="{wx:.1f}" cy="{wy:.1f}" r="6" fill="var(--s2)" stroke="var(--paper)" stroke-width="2" '
        f'data-tip="Winner: {esc(_montage_name(w["pairs"]))}"/>'
        f'<line x1="{wx - 5:.1f}" y1="{wy - 5:.1f}" x2="{wx - 30:.1f}" y2="{wy - 30:.1f}" stroke="var(--ink-2)"/>'
        f'<text x="{wx - 34:.1f}" y="{wy - 32:.1f}" text-anchor="end" class="t-ink">best: {esc(_montage_name(w["pairs"]))}</text>'
    )
    p.append(
        f'<line class="axis" x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}"/>'
        f'<text x="{ml + pw / 2:.1f}" y="{height - 4}" text-anchor="middle">Mean TI envelope in the ROI (V/m)</text>'
        f'<text transform="translate(12 {mt + ph / 2:.1f}) rotate(-90)" text-anchor="middle">Focality (ROI mean ÷ grey-matter mean)</text></svg>'
    )
    return "".join(p)


def build_html(rec: dict, subject_id: str, generated: datetime | None = None) -> str:
    import tit

    generated = generated or datetime.now()
    cfg, rows, lf = rec["config"], rec["rows"], rec["leadfield"]
    roi = rec["roi"] or {}
    cite = c.Cites()
    fig_no = iter(range(1, 20))
    best = rows[0]
    checks_ = checks(rec)
    seal, _ = c.verdict(checks_)
    n = len(rows)
    pairs = best["pairs"]
    name = _montage_name(pairs)
    radius = cfg.get("roi_radius")
    roi_name = (
        roi.get("name")
        or f"sphere of {radius:g} mm around the centre in {cfg.get('roi_name')}"
    )
    net = net_of(cfg)
    mA = [best["I1"], best["I2"]]

    # ── 1. verdict ──
    headline = f"{name} leads {n:,} montages"
    lede = (
        f"Ranked by composite (ROI mean × focality), the best montage gives a mean TI envelope of "
        f"<b>{best['TImean_ROI']:.3f} V/m</b> in the {esc(roi_name)} at {common.per_channel(mA)} mA per channel, "
        f"{best['Focality']:.2f}× the grey-matter mean. Check it with a full simulation before use."
    )
    key = [
        (
            "ROI mean",
            f"{best['TImean_ROI']:.3f}<small>V/m</small>",
            f"search median {sorted(r['TImean_ROI'] for r in rows)[n // 2]:.3f} V/m",
        ),
        (
            "Focality",
            f"{best['Focality']:.2f}<small>×</small>",
            "ROI mean ÷ grey-matter mean",
        ),
        (
            "ROI peak",
            f"{best['TImax_ROI']:.3f}<small>V/m</small>",
            "maximum in the ROI",
        ),
        ("Montages", f"{n:,}", "montage × current-split combinations"),
    ]
    extra = common.attention_callouts(checks_, cite) + c.stats(key)
    verdict_sec = c.verdict_section(seal, headline, lede, extra)

    # ── 2. winner ──
    dims = (lf.get("dimensions") or "").replace(", ", "×").replace(",", "×")
    cond = "anisotropic, from the DTI tensor" if lf.get("tensor") else "isotropic"
    dose = [
        (
            "Electrodes",
            (
                esc(
                    f"{lf.get('shape') or '?'} {dims} mm, gel {lf.get('thickness') or '?'} mm"
                )
                if lf
                else "as in the leadfield (not recorded)"
            ),
        ),
        (
            "Currents",
            f"{common.per_channel(mA)} mA per channel, {fmt(sum(mA))} mA total",
        ),
        (
            "Current sweep",
            f"{fmt(cfg.get('total_current_mA', 0))} mA total in {fmt(cfg.get('current_step_mA', 0))} mA steps, at most {fmt(cfg.get('channel_limit_mA') or 0)} mA per channel",
        ),
        (
            "Carrier frequencies",
            "not part of the field model (quasi-static); set them on the stimulator",
        ),
        (
            "Leadfield",
            (
                f"<code>{esc(cfg.get('leadfield_hdf', ''))}</code>, {cond}"
                if lf
                else f"<code>{esc(cfg.get('leadfield_hdf', ''))}</code>"
            ),
        ),
    ]
    d = RULES["opt"]["dose_record"]
    winner = common.cap_figure(next(fig_no), pairs, net, mA)
    winner += (
        '<h3 class="sub">Dose record</h3>'
        + c.kv(dose)
        + f'<p class="muted" style="font-size:13px;margin-top:10px">{c.inline(d["plain"])} {cite.dois(d["cite"])}</p>'
        + c.checks_table(
            checks_,
            "The current advisory never blocks; it compares the winner's dose with published evidence.",
            cite.dois,
        )
    )
    n_attn = sum(r.status in ("warn", "fail") for r in checks_)
    winner_sec = c.section(
        "winner",
        "Winning montage",
        winner,
        lead="Where to place the electrodes and how much current to use.",
        st="warn" if n_attn else "pass",
        st_label="Review current" if n_attn else "Within evidence",
    )

    # ── 3. results ──
    fig = c.figure(
        next(fig_no),
        "Every montage, ROI mean against focality",
        f"<div>{density_chart(rows)}</div>"
        + c.legend(
            [
                ("montages per cell (log shading)", "--s1"),
                (f"top {TOP_N}, winner filled", "--s2"),
            ],
            dot=True,
        ),
        "Up and to the right is better on both. Dashed curves have equal composite; hover a cell or ring for its values.",
    )
    table_rows = []
    for i, r in enumerate(rows[:TOP_N], 1):
        table_rows.append(
            [
                (str(i), i),
                esc("–".join(r["pairs"][0])),
                esc("–".join(r["pairs"][1])) if len(r["pairs"]) > 1 else "",
                (f"{fmt(r['I1'])} / {fmt(r['I2'])}", r["I1"]),
                (f"{r['TImean_ROI']:.3f}", r["TImean_ROI"]),
                (f"{r['TImax_ROI']:.3f}", r["TImax_ROI"]),
                (f"{r['TImean_GM']:.3f}", r["TImean_GM"]),
                (f"{r['Focality']:.2f}", r["Focality"]),
                (
                    (
                        f"<b>{r['Composite_Index']:.3f}</b>"
                        if i == 1
                        else f"{r['Composite_Index']:.3f}"
                    ),
                    r["Composite_Index"],
                ),
            ]
        )
    table = c.table(
        [
            "#",
            "Channel 1",
            "Channel 2",
            "mA",
            "ROI mean",
            "ROI max",
            "GM mean",
            "Focality",
            "Composite",
        ],
        table_rows,
        caption=f"Top {TOP_N} by composite. Fields in V/m. Select a column header to sort.",
        right={0, 3, 4, 5, 6, 7, 8},
        sortable=True,
    )
    results_sec = c.section(
        "results",
        "Search results",
        fig + table,
        lead="Where the winner sits among all candidates.",
    )

    # ── 4. target and ranking ──
    g = RULES["opt"]["goal_definition"]
    target = [("ROI", esc(roi_name))]
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
    target += [
        (
            "Intensity",
            "volume-weighted mean TI envelope over the ROI's mesh elements (ROI mean)",
        ),
        ("Focality", "ROI mean ÷ volume-weighted mean envelope over all grey matter"),
        ("Ranking", "composite = ROI mean × focality; higher is better"),
        (
            "Search space",
            esc(
                f"{cfg.get('electrode_mode', '')}: "
                + "; ".join(
                    f"{k.replace('_', ' ')} {len(v)}"
                    for k, v in (cfg.get("electrodes") or {}).items()
                    if isinstance(v, list)
                )
            ),
        ),
    ]
    target_sec = c.section(
        "target",
        "Target and ranking",
        c.kv(target)
        + f'<p class="muted" style="font-size:13px;margin-top:10px">{c.inline(g["plain"])} {cite.dois(g["cite"])}</p>',
        lead="What the search optimised, in plain words.",
    )

    # ── 5. technical ──
    paras = [
        f"Electrode montages for temporal interference stimulation {cite('grossman2017_ti')} were ranked by exhaustive search in TI-Toolbox "
        f"{cite('haber2026_titoolbox')}: {n:,} two-channel combinations and current splits on the {esc(Path(net).stem)} positions"
        + (f" {cite('jurcak2007_eeg_positions')}" if "10-" in net else "")
        + f", each evaluated from a SimNIBS {esc(lf.get('simnibs') or '')} {cite('saturnino2019_simnibs21')} leadfield of subject {esc(subject_id)}'s head model "
        f"{cite('puonti2020_charm')} with {cond} conductivities.",
        f"For each montage the maximal TI modulation amplitude {cite('grossman2017_ti')} was averaged in the {esc(roi_name)} and in grey matter; montages were "
        f"ranked by the product of the ROI mean and focality (their ratio). The best, {esc(name)} at {common.per_channel(mA)} mA per channel, "
        f"gave a ROI mean of {best['TImean_ROI']:.3f} V/m and a focality of {best['Focality']:.2f}.",
    ]
    tech = c.details(
        "Methods and references",
        c.methods(paras) + '<h3 class="sub">References</h3>' + cite.listing(),
        "boilerplate generated from this run; check before use",
    )
    tech += c.details(
        "Run record",
        c.kv(
            [
                ("Run", esc(rec["run"])),
                ("TI-Toolbox", esc(tit.__version__)),
                ("SimNIBS", esc(lf.get("simnibs") or "not recorded")),
                ("Results", f"<code>final_output.csv</code>, {n:,} rows"),
            ]
        )
        + '<h3 class="sub">run_config.json</h3>'
        + c.code(json.dumps(cfg, indent=1)),
        "versions and the configuration as run",
    )

    masthead = c.masthead(
        "Exhaustive montage search",
        f"sub-{subject_id}, {rec['run']}",
        [
            ("Subject", esc(subject_id)),
            ("Net", esc(Path(net).stem)),
            ("Montages", f"{n:,}"),
            ("Report", generated.strftime(common.STAMP)),
        ],
    )
    toc = [
        ("verdict", "Verdict", seal),
        ("winner", "Winning montage", "warn" if n_attn else "pass"),
        ("results", "Search results", None),
        ("target", "Target and ranking", None),
        ("technical", "Technical details", None),
    ]
    return c.page(
        title=f"sub-{subject_id} ex-search",
        kind="Ex-search report",
        subject=f"sub-{subject_id}",
        toc=toc,
        body=masthead
        + verdict_sec
        + winner_sec
        + results_sec
        + target_sec
        + c.section("technical", "Technical details", tech),
        footer=common.footer(generated),
        description=f"Ex-search report for sub-{subject_id}, {rec['run']}: {headline}",
        generator=f"TI-Toolbox {tit.__version__}",
    )


def create_ex_search_report(
    project_dir: str | Path,
    subject_id: str,
    run_dir: str | Path,
    out_dir: str | Path | None = None,
) -> Path:
    """Write the report for one ex-search run folder; into the project's reports unless *out_dir*."""
    from tit.paths import get_path_manager

    t0 = time.time()
    pm = get_path_manager(str(project_dir))
    rec = collect(run_dir, pm.leadfields(subject_id))
    if not rec["rows"]:
        raise ValueError(f"{run_dir}/final_output.csv has no montages")
    return common.write_report(
        build_html(rec, subject_id),
        project_dir,
        subject_id,
        REPORT_PREFIX,
        SIZE_BUDGET,
        out_dir,
        t0,
        label="Ex-search report",
    )


def main(argv: list[str] | None = None) -> int:
    from tit.paths import get_path_manager

    parser = argparse.ArgumentParser(
        description="Rebuild an ex-search report from its run folder."
    )
    parser.add_argument("project_dir")
    parser.add_argument("subject_id")
    parser.add_argument("run", help="run name under ex-search/, or a path")
    parser.add_argument(
        "--out", help="write the report here instead of into the project"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()
    run = Path(args.run)
    if not run.is_dir():
        run = Path(
            get_path_manager(args.project_dir).ex_search_run(args.subject_id, args.run)
        )
    path = create_ex_search_report(args.project_dir, args.subject_id, run, args.out)
    print(f"{path} {path.stat().st_size / 1e6:.2f} MB in {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
