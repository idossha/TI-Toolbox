"""Flex report: restarts are keyed by their ``candidate_history/NN`` name, never by position.

Pins (2026-10-22, package p12):
* ``candidate_history`` entries that are not restart dirs (``.DS_Store``, an AppleDouble ``._00``,
  a stale ``03`` beyond ``result.all_values``) are ignored: the real run
  ``sub-101/flex-search/20260919_131736_879_1`` has ``candidate_history/.DS_Store`` and its report
  raised ``IndexError``;
* restart *i* of the runs table is ``all_values[i]`` beside ``candidate_history/<i:02d>``, so a
  missing ``01`` shows "failed" in row 2 and does not shift row 3;
* the verdict tiles and currents come from the best restart's *accepted* candidate, and a failed
  run (``best_run_index`` -1) states the manifest's ``current_mA``, not a rejected trial's split;
* a Pareto sweep folder (``candidate_history/point_NNN/NN``) is read through its ``pareto``
  section, never as restarts, and ``main`` renders all five sections.

Every number below is written into the fixture by hand in this file (candidate rows, manifest
values), so each expectation is a value the fixture states, not one the generator computed.
Run: ``python -m pytest tests/test_flex_report_restarts.py -q``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_reporting_runs import _flex_dir, _structure

HEADER = (
    "candidate_id,evaluation,objective,roi_mean,roi_p99_9,non_roi_mean,non_roi_p95,"
    "target_background_ratio,current_ch1_mA,current_ch2_mA,geometry_file\n"
)
SECTIONS = ("verdict", "target", "montage", "runs", "technical")


def _restart(run: Path, name: str, rows: list[str], accepted: str | None) -> None:
    """``candidate_history/<name>/`` with *rows* and the manifest naming *accepted*."""
    h = run / "candidate_history" / name
    h.mkdir(parents=True, exist_ok=True)
    (h / "candidates.csv").write_text(HEADER + "".join(r + "\n" for r in rows))
    (h / "candidate_manifest.json").write_text(
        json.dumps(
            {
                "accepted_candidate_id": accepted,
                "evaluations": 10,
                "valid_candidates": len(rows),
                "config": {"anisotropy_type": "scalar"},
            }
        )
    )


def _set_meta(run: Path, **result) -> dict:
    meta = json.loads((run / "flex_meta.json").read_text())
    meta["result"].update(result)
    (run / "flex_meta.json").write_text(json.dumps(meta))
    return meta


def _html(run: Path) -> str:
    from tit.reporting.generators import flex_search as flex

    return flex.build_html(flex.collect(run), "X")


def _section(html: str, anchor: str) -> str:
    m = re.search(rf'<section class="sec" id="{anchor}".*?</section>', html, re.S)
    assert m, f"no {anchor} section"
    return m.group(0)


def _run_rows(html: str) -> list[list[str]]:
    """The runs table as text cells, one list per row."""
    body = re.search(r"<tbody>(.*?)</tbody>", _section(html, "runs"), re.S).group(1)
    return [
        [re.sub("<[^>]+>", "", cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", tr)]
        for tr in re.findall(r"<tr>(.*?)</tr>", body)
    ]


def _tile(html: str, label: str) -> str | None:
    m = re.search(
        rf"<dt>{re.escape(label)}</dt><dd><b>(.*?)</b>", _section(html, "verdict")
    )
    return m.group(1) if m else None


def _kv(html: str, label: str) -> str:
    return re.search(rf"<dt>{re.escape(label)}</dt><dd>(.*?)</dd>", html).group(1)


def test_dotfiles_in_candidate_history_are_not_restarts(tmp_path):
    run = _flex_dir(tmp_path)  # one restart, 00, accepted r:9 with roi_mean 0.04
    (run / "candidate_history" / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    (run / "candidate_history" / "._00").write_bytes(b"\x00\x05\x16\x07")
    html = _html(run)
    _structure(html, SECTIONS, 1_000_000, require_status=False)
    assert _tile(html, "Target mean") == "0.040<small>V/m</small>"
    assert len(_run_rows(html)) == 1  # == len(all_values)
    assert _kv(html, "Runs") == "1"


def test_a_missing_restart_dir_does_not_shift_the_runs(tmp_path):
    run = _flex_dir(tmp_path, values=(-1.1, -1.8))
    for name in ("00", "01"):
        for f in (run / "candidate_history" / name).iterdir():
            f.unlink()
        (run / "candidate_history" / name).rmdir()
    _restart(run, "00", ["a:1,1,-1.1,0.11,0.2,0.1,0.15,1.1,0.6,1.4,g"], "a:1")
    _restart(
        run,
        "02",
        [
            "c:1,1,-1.2,0.3,0.5,0.25,0.3,1.2,1.0,1.0,g",
            "c:2,2,-1.8,0.05,0.09,0.0277,0.04,1.8,0.8,1.2,g",
        ],
        "c:2",
    )
    meta = json.loads((run / "flex_meta.json").read_text())
    meta["current_split"] = [0.8, 1.2]
    meta["n_multistart"] = 3
    meta["result"] = {
        "success": True,
        "best_value": -1.8,
        "best_run_index": 2,
        "all_values": [-1.1, None, -1.8],  # restart 2 failed; strict JSON writes null
    }
    (run / "flex_meta.json").write_text(json.dumps(meta))

    html = _html(run)
    # The verdict and the dose come from 02's accepted row (c:2), not from 00 or a rejected c:1.
    assert _tile(html, "Target mean") == "0.050<small>V/m</small>"
    assert _tile(html, "Target ÷ background") == "1.80<small>×</small>"
    assert _tile(html, "Currents") == "0.8 / 1.2<small>mA</small>"
    rows = _run_rows(html)
    assert [r[0] for r in rows] == ["1", "2", "3 (best)"]
    assert rows[0][1:3] == ["1.100", "0.110"]
    assert rows[1][1:3] == ["failed", "—"]
    assert rows[2][1:3] == ["1.800", "0.050"]
    assert _kv(html, "Runs") == "3"


def test_a_stale_restart_beyond_all_values_is_ignored(tmp_path):
    run = _flex_dir(tmp_path, values=(-1.8,))
    _restart(run, "03", ["s:1,1,-9.0,9.0,9.9,0.1,0.2,90,1.0,1.0,g"], "s:1")
    html = _html(run)
    assert len(_run_rows(html)) == 1 and _kv(html, "Runs") == "1"
    assert "9.000" not in html  # nothing from the stale 03 is shown


def test_a_failed_run_states_the_manifest_current_not_a_rejected_split(tmp_path):
    run = _flex_dir(tmp_path, values=(-1.8, -1.8))
    meta = json.loads((run / "flex_meta.json").read_text())
    meta.update(current_mA=1.5, current_split=None)
    meta["result"] = {
        "success": False,
        "best_value": None,
        "best_run_index": -1,
        "all_values": [None, None],
    }
    (run / "flex_meta.json").write_text(json.dumps(meta))
    for name in ("00", "01"):  # trials were recorded, none was accepted
        (run / "candidate_history" / name / "candidates.csv").unlink()
        _restart(run, name, ["t:1,1,-1.3,0.2,0.3,0.1,0.2,2,0.7,1.3,g"], None)

    html = _html(run)
    assert '<h2 id="verdict-h">No valid montage found</h2>' in html
    assert _kv(html, "Currents").startswith("1.5 mA per channel, 3 mA total")
    rows = _run_rows(html)
    assert [r[1] for r in rows] == ["failed", "failed"]
    assert [r[2] for r in rows] == [
        "—",
        "—",
    ]  # a rejected trial is not the run's result


def _pareto_dir(tmp_path: Path) -> Path:
    """A sweep folder as ``run_pareto_sweep`` leaves it: three points' histories under
    ``point_NNN/00`` and the best point's (index 1) manifest with the sweep in ``pareto``.
    """
    run = _flex_dir(tmp_path, goal="focality")
    for f in (run / "candidate_history" / "00").iterdir():
        f.unlink()
    (run / "candidate_history" / "00").rmdir()
    for i, (roi_mean, objective) in enumerate(
        [(0.31, -50.0), (0.22, -70.0), (0.27, -60.0)]
    ):
        _restart(
            run,
            f"point_{i:03d}/00",
            [f"p{i}:1,1,{objective},{roi_mean},0.5,0.1,0.2,3,1.0,1.0,g"],
            f"p{i}:1",
        )
    meta = json.loads((run / "flex_meta.json").read_text())
    achievable = 0.4
    points = [
        {
            "run_index": i,
            "roi_pct": 80.0,
            "nonroi_pct": nonroi,
            "roi_threshold_vm": 0.8 * achievable,
            "nonroi_threshold_vm": nonroi / 100 * achievable,
            "focality_score": score,
            "status": "done",
        }
        for i, (nonroi, score) in enumerate(
            [(20.0, -50.0), (30.0, -70.0), (40.0, -60.0)]
        )
    ]
    meta.update(
        goal="focality",
        thresholds="0.1200,0.3200",
        current_split=None,
        optimize_current_ratio=False,
        n_multistart=1,
        pareto={
            "roi_pcts": [80.0],
            "nonroi_pcts": [20.0, 30.0, 40.0],
            "achievable_roi_mean_vm": achievable,
            "best_point": {
                "run_index": 1,
                "roi_pct": 80.0,
                "nonroi_pct": 30.0,
                "focality_score": -70.0,
            },
            "points": points,
        },
    )
    meta["result"] = {
        "success": True,
        "best_value": -70.0,
        "best_run_index": 0,
        "all_values": [-70.0],
    }
    (run / "flex_meta.json").write_text(json.dumps(meta))
    return run


def test_a_pareto_sweep_folder_reports_its_best_point_and_the_sweep(tmp_path):
    from tit.reporting.generators import flex_search as flex

    run = _pareto_dir(tmp_path)
    out = tmp_path / "out"
    assert flex.main(["/nonexistent-project", "X", str(run), "--out", str(out)]) == 0
    (page,) = out.glob("flex_search_report_*.html")
    html = page.read_text()
    _structure(html, SECTIONS, flex.SIZE_BUDGET, require_status=False)
    # The best point (index 1, point_001) is the promoted montage: its accepted roi_mean.
    assert _tile(html, "Target mean") == "0.220<small>V/m</small>"
    rows = _run_rows(html)
    assert rows[0][:3] == ["1 (best)", "70.000", "0.220"]
    # The sweep table: one row per point, thresholds in V/m (pct/100 x 0.4 V/m).
    sweep = re.search(
        r"<tbody>(.*?)</tbody>", _section(html, "runs").split("</table>")[1], re.S
    )
    assert sweep, "no sweep table after the runs table"
    sweep_rows = [
        [re.sub("<[^>]+>", "", td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr)]
        for tr in re.findall(r"<tr>(.*?)</tr>", sweep.group(1))
    ]
    assert sweep_rows == [
        ["80 %", "20 %", "0.320", "0.080", "50.00", "done"],
        ["80 %", "30 %", "0.320", "0.120", "70.00", "done (promoted)"],
        ["80 %", "40 %", "0.320", "0.160", "60.00", "done"],
    ]
    # The ROC goal names the thresholds the promoted point ran with, in V/m.
    assert _kv(html, "Thresholds") == "non-ROI maximum 0.12 V/m, ROI minimum 0.32 V/m"


def test_a_pareto_folder_without_its_sweep_section_still_renders(tmp_path):
    """A sweep written before the manifest carried ``pareto`` (Dataset 000 has none, the shape
    is from the audit): ``point_NNN`` is never a restart, so the page renders with one run.
    """
    from tit.reporting.generators import flex_search as flex

    run = _pareto_dir(tmp_path)
    meta = json.loads((run / "flex_meta.json").read_text())
    meta["pareto"] = None
    (run / "flex_meta.json").write_text(json.dumps(meta))
    html = _html(run)
    _structure(html, SECTIONS, flex.SIZE_BUDGET, require_status=False)
    rows = _run_rows(html)
    assert len(rows) == 1 and rows[0][1] == "70.000" and rows[0][2] == "—"


def test_a_legacy_infinity_restart_is_failed_not_a_score(tmp_path):
    """Manifests written before the strict-JSON fix hold ``Infinity`` (Python's json reads it):
    that restart accepted nothing, so its row reads "failed", never "-inf" or a huge score.
    """
    run = _flex_dir(tmp_path, values=(-1.8, -1.8))
    meta = json.loads((run / "flex_meta.json").read_text())
    meta["result"].update(best_value=-1.8, best_run_index=1)
    (run / "flex_meta.json").write_text(
        json.dumps(meta).replace(
            '"all_values": [-1.8, -1.8]', '"all_values": [Infinity, -1.8]'
        )
    )
    assert "Infinity" in (run / "flex_meta.json").read_text()
    rows = _run_rows(_html(run))
    assert [r[:2] for r in rows] == [["1", "failed"], ["2 (best)", "1.800"]]


def test_a_manifest_that_says_failed_has_no_best_restart(tmp_path):
    """``success`` false is a failed run even when ``best_run_index`` names a restart (a manifest
    edited or written by an older driver): no "(best)" row, and the dose is the manifest's
    ``current_mA`` rather than restart 00's accepted split (0.7 / 1.3 mA in the fixture).
    """
    run = _flex_dir(tmp_path, values=(-1.8,))
    meta = json.loads((run / "flex_meta.json").read_text())
    meta.update(current_mA=1.5)
    meta["result"].update(success=False, best_run_index=0)
    (run / "flex_meta.json").write_text(json.dumps(meta))
    html = _html(run)
    assert '<h2 id="verdict-h">No valid montage found</h2>' in html
    assert _kv(html, "Currents").startswith("1.5 mA per channel, 3 mA total")
    assert [r[0] for r in _run_rows(html)] == ["1"]


@pytest.mark.parametrize(
    "thresholds,words",
    [
        ("0.2", "0.2 V/m, as both the non-ROI maximum and the ROI minimum"),
        ("0.1,0.25", "non-ROI maximum 0.1 V/m, ROI minimum 0.25 V/m"),
    ],
)
def test_a_roc_report_states_one_or_two_thresholds(tmp_path, thresholds, words):
    """SimNIBS reads one ROC threshold as both bounds and two as (non-ROI max, ROI min)."""
    run = _flex_dir(tmp_path, goal="focality")
    meta = json.loads((run / "flex_meta.json").read_text())
    meta["thresholds"] = thresholds
    (run / "flex_meta.json").write_text(json.dumps(meta))
    assert _kv(_html(run), "Thresholds") == words


def test_three_roc_thresholds_are_not_given_a_meaning(tmp_path):
    """Three values match neither SimNIBS form: the report shows no Thresholds row."""
    run = _flex_dir(tmp_path, goal="focality")
    meta = json.loads((run / "flex_meta.json").read_text())
    meta["thresholds"] = "0.1,0.2,0.3"
    (run / "flex_meta.json").write_text(json.dumps(meta))
    assert "<dt>Thresholds</dt>" not in _html(run)
