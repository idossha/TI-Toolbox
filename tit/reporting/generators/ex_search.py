"""Ex-search report: one self-contained HTML record per exhaustive montage search.

Built on :mod:`tit.reporting.html.components` (ARCHITECTURE.md §14). Everything is read from the
run folder: ``run_config.json`` (buckets, current sweep, ROI name and radius, leadfield),
``final_output.csv`` (one row per montage and current split), the ROI confirmation
(``roi.tetravox.json``) and the leadfield's SimNIBS log (electrode geometry, conductivity).
The goal definition and dose record come from ``tit.reporting.qc_rules.RULES["opt"]``; the page
has no checks.

The default view is the winner (ranked by composite = ROI mean × focality) with its electrodes and
dose, one chart of every montage's ROI mean against focality, the top 25 as a sortable table, and
the ROI and ranking in words; methods and the run record are collapsed.

``tit.opt.ex`` and ``tit.opt.mex`` write one when a search finishes (an mEx page lists four
channels at its one current). Rebuild one (nothing is re-searched)::

    simnibs_python -m tit.reporting.generators.ex_search <project> <subject> <run name> [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import statistics
import time
from datetime import datetime
from itertools import zip_longest
from pathlib import Path

from tit.reporting.generators import common
from tit.reporting.generators.common import fmt
from tit.reporting.html import components as c
from tit.reporting.html.components import esc
from tit.reporting.qc_rules import RULES

logger = logging.getLogger(__name__)

REPORT_PREFIX = "ex_search_report"
SIZE_BUDGET = 1_000_000
TOP_N = 25
_FIELDS = ("TImax_ROI", "TImean_ROI", "TImean_GM", "Focality", "Composite_Index")


def read_results(csv_path: str | Path) -> list[dict]:
    """``final_output.csv`` rows with numbers as floats, ranked by composite (best first)."""
    return _read_rows(csv_path)[0]


def _read_rows(csv_path: str | Path) -> tuple[list[dict], int]:
    """The ranked rows of :func:`read_results` and how many rows were left out: an unreadable
    montage or a number that is missing or not finite (NaN, inf) has no place in a ranking.
    """
    from tit.opt.ex.results import parse_montage_string

    rows, skipped = [], 0
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                row = {k: float(r[k]) for k in _FIELDS}
                row["I1"], row["I2"] = float(r["Current_Ch1_mA"]), float(
                    r["Current_Ch2_mA"]
                )
                e = parse_montage_string(r["Montage"])
                # An mEx CSV carries Current_Ch3/Ch4 too (older ones only Ch1/Ch2).
                currents = [row["I1"], row["I2"]] + [
                    float(r[f"Current_Ch{k}_mA"])
                    for k in range(3, len(e) // 2 + 1)
                    if r.get(f"Current_Ch{k}_mA") not in (None, "")
                ]
            except (KeyError, TypeError, ValueError, AttributeError):
                skipped += 1
                continue
            if not all(math.isfinite(v) for v in [*row.values(), *currents]):
                skipped += 1
                continue
            row["pairs"] = [e[i : i + 2] for i in range(0, len(e), 2)]
            row["currents"] = currents
            rows.append(row)
    rows.sort(key=lambda r: r["Composite_Index"], reverse=True)
    return rows, skipped


def top_distinct(rows: list[dict], top: int = TOP_N) -> list[dict]:
    """The best *top* rows that are different stimulations.

    A row is the set of its channels, each an unordered electrode pair at its current: the TI
    envelope ignores channel polarity and order, so runs written before pool mode evaluated each
    montage once list one montage up to eight times. Rows are ranked best first.
    """
    seen, kept = set(), []
    for r in rows:
        key = frozenset(
            (frozenset(pair), None if current is None else round(current, 9))
            for pair, current in zip_longest(r["pairs"], channel_currents(r))
        )
        if key not in seen:
            seen.add(key)
            kept.append(r)
            if len(kept) == top:
                break
    return kept


def channel_currents(row: dict) -> list[float]:
    """The current of each channel of *row* (mA), in pair order: two for ex, four for mEx."""
    return row.get("currents") or [row["I1"], row["I2"]]


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
        "conductivity": (
            "anisotropic"
            if "Using anisotropic" in log_text
            else "isotropic" if "Using isotropic conductivities" in log_text else None
        ),
        "simnibs": first(r"simnibs (\d[\w.]*)"),
    }


def leadfield_log(leadfield_dir: str | Path, cfg: dict) -> str | None:
    """The text of the SimNIBS log that built this run's leadfield, or ``None``.

    A subject's ``leadfields/`` keeps one log per attempt, for every net. A log whose
    ``EEG Cap:`` line names another net is never used; among the rest, one that names the run's
    HDF5 file (written when the leadfield finished) beats one that only names its net, which
    beats one that names no net (an attempt that died first); the newest breaks ties.
    """
    hdf = Path(cfg.get("leadfield_hdf") or "").name
    net = net_of(cfg)
    best, best_key = None, None
    for log in sorted(Path(leadfield_dir).glob("simnibs_simulation_*.log")):
        text = log.read_text(errors="replace")
        cap = re.search(r"EEG Cap:\s*(\S+)", text)
        if cap and Path(cap.group(1)).stem != net:
            continue
        key = (bool(hdf) and hdf in text, cap is not None, log.name)
        if best_key is None or key > best_key:
            best, best_key = text, key
    return best


def collect(run_dir: str | Path, leadfield_dir: str | Path | None = None) -> dict:
    """Everything the report shows, from one ex-search run folder."""
    run_dir = Path(run_dir)
    cfg = json.loads((run_dir / "run_config.json").read_text())
    lf = {}
    log = leadfield_log(leadfield_dir, cfg) if leadfield_dir else None
    if log:
        lf = leadfield_facts(log)
    rows, skipped = _read_rows(run_dir / "final_output.csv")
    if cfg.get("current_mA") is not None:
        # mEx drives every pair at the one configured current; its older CSVs carry only the
        # first two channels' currents, rounded to 0.1 mA.
        for row in rows:
            row["currents"] = [float(cfg["current_mA"])] * len(row["pairs"])
    return {
        "run": run_dir.name,
        "config": cfg,
        "rows": rows,
        "skipped": skipped,
        "roi": common.roi_summary(run_dir),
        "leadfield": lf,
    }


def net_of(cfg: dict) -> str:
    from tit.opt.ex.symmetry import net_name_from_leadfield

    return net_name_from_leadfield(cfg.get("leadfield_hdf", ""))


def target_description(cfg: dict) -> str:
    """The ROI as ``run_config.json`` defines it, for a run without a ROI plate.

    Spheres around the centres in ``roi_names`` (or ``roi_name``), in subject or MNI
    coordinates, joined with any ``roi_atlas`` labels or masks. A run written before these
    fields were recorded is named, not described: its ``roi_name`` may be only a label.
    """
    name = cfg.get("roi_name") or "target ROI"
    if not any(k in cfg for k in ("roi_names", "roi_atlas", "roi_coordinate_space")):
        return f"{name} (shape not recorded in this run)"
    radius = cfg.get("roi_radius")
    names = cfg.get("roi_names")
    names = [name] if names is None else names
    mni = "MNI " if cfg.get("roi_coordinate_space") == "mni" else ""
    parts = []
    if len(names) == 1:
        parts.append(f"sphere of {radius:g} mm around the {mni}centre in {names[0]}")
    elif names:
        parts.append(
            f"union of {radius:g} mm spheres around the {mni}centres in {', '.join(names)}"
        )
    for atlas in cfg.get("roi_atlas") or []:
        where = Path(str(atlas.get("atlas_path", ""))).name
        where += " (MNI)" if atlas.get("atlas_space") == "mni" else ""
        label = atlas.get("label")
        parts.append(f"mask {where}" if label is None else f"label {label} of {where}")
    return " + ".join(parts) or name


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
    # One value on an axis (a single row, or every montage tied at 0) still needs a span.
    x0, x1 = 0.0, max(xs) * 1.05 or 1.0
    y0, y1 = min(ys) * 0.97, max(ys) * 1.03
    if y1 <= y0:
        y1 = y0 + 1.0
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
    for k in (0.5, 0.75) if best > 0 else ():
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
    for r in top_distinct(rows, top)[1:]:
        p.append(
            f'<circle cx="{X(r["TImean_ROI"]):.1f}" cy="{Y(r["Focality"]):.1f}" r="4.5" fill="none" stroke="var(--s2)" stroke-width="1.6" '
            f'data-tip="{esc(_montage_name(r["pairs"]))}\n{"/".join(f"{v:g}" for v in channel_currents(r))} mA: ROI mean {r["TImean_ROI"]:.3f} V/m, focality {r["Focality"]:.2f}"/>'
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
    seal = "pass"
    n = len(rows)
    pairs = best["pairs"]
    name = _montage_name(pairs)
    roi_name = roi.get("name") or target_description(cfg)
    net = net_of(cfg)
    mA = channel_currents(best)
    channels = len(pairs)
    channels_word = {2: "two", 4: "four"}.get(channels, str(channels))
    # ex sweeps the split; mEx (run_config "current_mA") runs one fixed current per pair
    swept = cfg.get("current_mA") is None

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
            f"search median {statistics.median(r['TImean_ROI'] for r in rows):.3f} V/m",
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
        (
            "Montages",
            f"{n:,}",
            (
                "montage × current-split combinations"
                if swept
                else "montages, one current on every channel"
            ),
        ),
    ]
    verdict_sec = c.verdict_section(seal, headline, lede, c.stats(key))

    # ── 2. winner ──
    dims = (lf.get("dimensions") or "").replace(", ", "×").replace(",", "×")
    # Only what the leadfield's own log states; an attempt that died early states nothing.
    cond = {
        "anisotropic": "anisotropic, from the DTI tensor",
        "isotropic": "isotropic",
    }.get(lf.get("conductivity"))
    electrodes = "as in the leadfield (not recorded)"
    if lf.get("shape") and dims:
        electrodes = esc(
            f"{lf['shape']} {dims} mm"
            + (f", gel {lf['thickness']} mm" if lf.get("thickness") else "")
        )
    total, step = cfg.get("total_current_mA", 0), cfg.get("current_step_mA", 0)
    limit = cfg.get("channel_limit_mA")
    if limit is None:  # runs before 2026-10-24 recorded no limit and swept up to total - step
        limit = round(total - step, 9)
    dose = [
        ("Electrodes", electrodes),
        (
            "Currents",
            f"{common.per_channel(mA)} mA per channel, {fmt(sum(mA))} mA total",
        ),
        (
            (
                "Current sweep",
                f"{fmt(total)} mA total in {fmt(step)} mA steps, at most {fmt(limit)} mA per channel",
            )
            if swept
            else (
                "Current sweep",
                f"none: every channel at {common.per_channel(mA)} mA",
            )
        ),
        (
            "Carrier frequencies",
            "not part of the field model (quasi-static); set them on the stimulator",
        ),
        (
            "Leadfield",
            f"<code>{esc(cfg.get('leadfield_hdf', ''))}</code>"
            + (f", {cond}" if cond else ""),
        ),
    ]
    d = RULES["opt"]["dose_record"]
    winner = (
        c.kv(
            [
                (f"Channel {i}", f"{esc(' → '.join(p))}, {fmt(m)} mA")
                for i, (p, m) in enumerate(zip(pairs, mA), 1)
            ]
        )
        + '<h3 class="sub">Dose record</h3>'
        + c.kv(dose)
        + f'<p class="muted" style="font-size:13px;margin-top:10px">{c.inline(d["plain"])} {cite.dois(d["cite"])}</p>'
    )
    winner_sec = c.section(
        "winner",
        "Winning montage",
        winner,
        lead="Where to place the electrodes and how much current to use.",
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
    for i, r in enumerate(top_distinct(rows), 1):
        currents = channel_currents(r)
        table_rows.append(
            [
                (str(i), i),
                *[
                    esc("–".join(r["pairs"][k])) if k < len(r["pairs"]) else ""
                    for k in range(channels)
                ],
                (" / ".join(fmt(v) for v in currents), currents[0]),
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
            *[f"Channel {k}" for k in range(1, channels + 1)],
            "mA",
            "ROI mean",
            "ROI max",
            "GM mean",
            "Focality",
            "Composite",
        ],
        table_rows,
        caption=f"Top {TOP_N} by composite. Fields in V/m. Select a column header to sort.",
        right={0, *range(channels + 1, channels + 7)},
        sortable=True,
    )
    skipped = rec.get("skipped", 0)
    left_out = (
        f'<p class="muted" style="font-size:13px">{skipped:,} row{"s" if skipped != 1 else ""} '
        "of final_output.csv left out: an unreadable montage or a number that is not finite.</p>"
        if skipped
        else ""
    )
    results_sec = c.section(
        "results",
        "Search results",
        fig + table + left_out,
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
    elif roi.get("vertices"):
        target.append(("Size", f"{roi['vertices']:,} cortical surface vertices"))
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
        f"Electrode montages for temporal interference stimulation were ranked by exhaustive search in TI-Toolbox: {n:,} {channels_word}-channel combinations{' and current splits' if swept else ''} on the {esc(Path(net).stem)} positions"
        + (f" {cite('jurcak2007_eeg_positions')}" if "10-" in net else "")
        + f", each evaluated from a SimNIBS {esc(lf.get('simnibs') or '')} {cite('saturnino2019_simnibs21')} leadfield of subject {esc(subject_id)}'s head model "
        f"{cite('puonti2020_charm')}"
        + (f" with {lf['conductivity']} conductivities." if cond else "."),
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
        ("winner", "Winning montage", None),
        ("results", "Search results", None),
        ("target", "Target and ranking", None),
        ("technical", "Technical details", None),
    ]
    return c.page(
        # The run, not only the subject: tit.catalog lists the report by this title.
        title=f"{rec['run']} ex-search",
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
    """Write the report for one ex- or mEx-search run folder; into the project's reports unless
    *out_dir*."""
    from tit.paths import get_path_manager

    t0 = time.time()
    pm = get_path_manager(str(project_dir))
    rec = collect(run_dir, pm.leadfields(subject_id))
    if not rec["rows"]:
        raise ValueError(f"{run_dir}/final_output.csv has no montages")
    if all(r["TImax_ROI"] == 0 and r["TImean_ROI"] == 0 for r in rec["rows"]):
        raise ValueError(
            f"Every montage in {run_dir}/final_output.csv scored 0 in the ROI "
            f"{rec['config'].get('roi_name')!r}: the ROI selected no leadfield mesh elements, "
            "so the ranking is arbitrary and there is no winner to report."
        )
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
