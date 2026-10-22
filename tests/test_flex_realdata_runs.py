"""Every completed flex run in Dataset 000 satisfies the manifest / candidate / geometry invariants.

Pins (2026-10-22, package p12). For each ``sub-*/flex-search/*/flex_meta.json`` (4 runs today:
sub-101, sub-CHN, sub-ernie x2), from the definitions, never from a previous run's numbers:

* the optimiser minimises (``tit/opt/flex/manifest.py``): ``best_value == min(finite
  all_values)``, ``best_run_index == argmin``; one ``candidate_history/NN`` per restart
  (``len(all_values) == n_multistart``), and restart *i*'s accepted candidate exists in its
  ``candidates.csv`` with ``objective == all_values[i]``;
* goal identities (``tit/opt/flex/candidates.py`` metric definitions, ``objectives.make_objective``):
  mean -> ``-best == roi_mean``; max -> ``-best == roi_p99_9``; focality_tf with w = 0 ->
  ``-best == target_background_ratio == roi_mean / non_roi_mean``;
* every candidate row: ``roi_mean <= roi_p99_9``; ``non_roi_mean > 0`` when observed and
  ``ratio == roi_mean / non_roi_mean``; the channel currents add to the total
  (``ratio_total_mA`` or 2 x ``current_mA``), and with the ratio search each channel is on the
  ``linspace(T/4, 3T/4, levels|1)`` grid (``objectives.ratio_levels`` docstring);
* ``electrode_positions.json``: 4 centres in channel/array order ``[[0,0],[0,1],[1,0],[1,1]]``,
  equal to the accepted candidate's pose translations (<= 1e-6 mm), 50-150 mm from the origin,
  and no two discs overlap (centre distance >= the electrode diameter);
* plausibility: 0.002 <= roi_mean / current_mA <= 2 (V/m per mA);
* ``valid_skin_region.png`` and ``roi.png`` exist and are not one flat colour;
* ``tit.catalog.flex_runs`` lists exactly the folders holding ``flex_meta.json`` (aborted
  ``NN``-only folders are not runs), and the report renders for every run (sub-101's
  ``candidate_history/.DS_Store`` once crashed it) with the best restart's accepted roi_mean.

Gated: ``export TIT_DATASET_000=/Users/idohaber/datasets/000`` (read-only; the test compares an
mtime listing of everything it read before and after). Skips with the reason when unset.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = os.environ.get("TIT_DATASET_000", "")
pytestmark = pytest.mark.skipif(
    not ROOT or not Path(ROOT, "derivatives", "SimNIBS").is_dir(),
    reason="skipping: TIT_DATASET_000 is unset or has no derivatives/SimNIBS "
    "(export TIT_DATASET_000=/path/to/Dataset000, read-only)",
)


def _runs() -> list[Path]:
    return sorted(
        Path(ROOT, "derivatives", "SimNIBS").glob("sub-*/flex-search/*/flex_meta.json")
    )


def _mtimes(paths) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in paths}


def _rows(path: Path) -> list[dict]:
    with path.open() as stream:
        return list(csv.DictReader(stream))


def _f(value: str) -> float | None:
    return float(value) if value not in ("", None) else None


@pytest.fixture(scope="module")
def runs():
    found = [p.parent for p in _runs()]
    assert found, "has no flex runs to check"
    before = _mtimes(p for run in found for p in run.rglob("*") if p.is_file())
    yield found
    after = _mtimes(p for run in found for p in run.rglob("*") if p.is_file())
    assert after == before, "a test wrote into the read-only dataset"


def _restarts(run: Path) -> dict[int, Path]:
    history = run / "candidate_history"
    return {
        int(p.name): p for p in history.iterdir() if p.is_dir() and p.name.isdigit()
    }


def _accepted(hist: Path) -> dict:
    manifest = json.loads((hist / "candidate_manifest.json").read_text())
    rows = [
        r
        for r in _rows(hist / "candidates.csv")
        if r["candidate_id"] == manifest["accepted_candidate_id"]
    ]
    assert (
        len(rows) == 1
    ), f"{hist}: accepted candidate {manifest['accepted_candidate_id']} not in candidates.csv"
    return rows[0]


def test_the_result_is_the_minimum_over_the_restarts_and_each_restart_is_recorded(runs):
    for run in runs:
        meta = json.loads((run / "flex_meta.json").read_text())
        values = meta["result"]["all_values"]
        finite = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
        assert meta["result"]["success"] and finite, run
        assert meta["result"]["best_value"] == min(finite), run
        assert meta["result"]["best_run_index"] == values.index(min(finite)), run
        assert len(values) == meta["n_multistart"] == len(_restarts(run)), run
        for i, hist in _restarts(run).items():
            if values[i] is not None:
                assert float(_accepted(hist)["objective"]) == values[i], (run, i)


def test_the_goal_score_is_the_quantity_it_names(runs):
    for run in runs:
        meta = json.loads((run / "flex_meta.json").read_text())
        best = _accepted(_restarts(run)[meta["result"]["best_run_index"]])
        score = -meta["result"]["best_value"]
        if meta["goal"] == "mean":
            assert score == float(best["roi_mean"]), run
        elif meta["goal"] == "max":
            assert score == float(best["roi_p99_9"]), run
        elif meta["goal"] == "focality_tf" and not meta.get("intensity_weight"):
            ratio = float(best["roi_mean"]) / float(best["non_roi_mean"])
            assert score == pytest.approx(
                float(best["target_background_ratio"]), rel=1e-12
            )
            assert score == pytest.approx(ratio, rel=1e-12), run


def test_every_candidate_row_is_physically_consistent(runs):
    checked = 0
    for run in runs:
        meta = json.loads((run / "flex_meta.json").read_text())
        total = meta.get("ratio_total_mA") or 2 * float(meta["current_mA"])
        grid = np.linspace(
            total / 4, 3 * total / 4, int(meta.get("ratio_levels") or 21) | 1
        )
        for hist in _restarts(run).values():
            for r in _rows(hist / "candidates.csv"):
                roi_mean, p999 = float(r["roi_mean"]), float(r["roi_p99_9"])
                assert roi_mean <= p999, (hist, r["candidate_id"])
                non = _f(r["non_roi_mean"])
                if non is not None:
                    assert non > 0
                    assert float(r["target_background_ratio"]) == pytest.approx(
                        roi_mean / non, rel=1e-12
                    )
                c1, c2 = float(r["current_ch1_mA"]), float(r["current_ch2_mA"])
                assert c1 + c2 == pytest.approx(total, abs=1e-9), (
                    hist,
                    r["candidate_id"],
                )
                if meta.get("optimize_current_ratio"):
                    for c in (c1, c2):
                        assert np.min(np.abs(grid - c)) <= 1e-9, (hist, c)
                else:
                    assert c1 == c2 == pytest.approx(float(meta["current_mA"]))
                checked += 1
    assert checked > 0, "has no candidate rows to check"


def test_the_final_electrodes_are_the_accepted_candidates_and_do_not_overlap(runs):
    for run in runs:
        meta = json.loads((run / "flex_meta.json").read_text())
        hist = _restarts(run)[meta["result"]["best_run_index"]]
        best = _accepted(hist)
        record = next(
            json.loads(line)
            for line in (hist / "candidate_geometry.jsonl").read_text().splitlines()
            if json.loads(line)["candidate_id"] == best["candidate_id"]
        )
        poses = [
            np.asarray(cell["posmat"])[:3, 3]
            for channel in record["electrodes"]
            for cell in channel
        ]
        pos = json.loads((run / "electrode_positions.json").read_text())
        centres = np.asarray(pos["optimized_positions"], dtype=float)
        assert centres.shape == (4, 3)
        assert pos["channel_array_indices"] == [[0, 0], [0, 1], [1, 0], [1, 1]]
        assert np.max(np.abs(centres - np.asarray(poses))) <= 1e-6, run
        norms = np.linalg.norm(centres, axis=1)
        assert np.all((norms >= 50) & (norms <= 150)), (run, norms)
        diameter = max(meta["electrode"]["dimensions"])
        gaps = [
            np.linalg.norm(a - b)
            for i, a in enumerate(centres)
            for b in centres[i + 1 :]
        ]
        assert min(gaps) >= diameter, (run, min(gaps))
        assert 0.002 <= float(best["roi_mean"]) / float(meta["current_mA"]) <= 2, run


def test_the_run_figures_are_real_images(runs):
    Image = pytest.importorskip("PIL.Image")
    if not hasattr(Image, "open") or type(Image).__name__ == "MagicMock":
        pytest.skip("skipping: PIL is a stub here")
    for run in runs:
        for name in ("valid_skin_region.png", "roi.png"):
            with Image.open(run / name) as image:
                extrema = image.convert("RGB").getextrema()
            assert any(lo != hi for lo, hi in extrema), (run, name, "one flat colour")


def test_the_catalog_lists_exactly_the_runs_with_a_manifest(runs):
    from tit.catalog import flex_runs, subject_ids
    from tit.paths import get_path_manager

    pm = get_path_manager(ROOT)
    for sid in subject_ids(pm):
        flex_root = Path(pm.flex_search(sid))
        if not flex_root.is_dir():
            continue
        expected = sorted(
            p.name for p in flex_root.iterdir() if (p / "flex_meta.json").is_file()
        )
        assert sorted(r["name"] for r in flex_runs(pm, sid)) == expected, sid


def test_the_report_renders_every_run_from_its_best_restart(runs):
    from tit.reporting.generators import flex_search as flex

    for run in runs:
        meta = json.loads((run / "flex_meta.json").read_text())
        best = _accepted(_restarts(run)[meta["result"]["best_run_index"]])
        html = flex.build_html(
            flex.collect(run), run.parent.parent.name.removeprefix("sub-")
        )
        tile = re.search(r"<dt>Target mean</dt><dd><b>([\d.]+)<small>", html)
        assert tile and tile.group(1) == f"{float(best['roi_mean']):.3f}", run
        runs_cell = re.search(r"<dt>Runs</dt><dd>(\d+)</dd>", html).group(1)
        assert int(runs_cell) == meta["n_multistart"], run
