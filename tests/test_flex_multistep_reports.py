"""Adaptive and Pareto flex jobs: one run folder, one report, a self-describing manifest.

Pins (2026-10-22, package p12; spec: "one self-contained HTML record per flex-search run",
``tit/reporting/generators/flex_search.py``):
* a Pareto (multi-threshold) job leaves exactly one report, about its sweep folder, which exists
  after the job; no point folder remains; the mean calibration is nested in
  ``<sweep>/mean_calibration`` so the catalog lists one run, whose manifest carries the sweep
  (``pareto``: one entry per point, thresholds = pct/100 x the calibration's achievable mean);
* an adaptive job leaves one report and one catalog entry (focality run, with the calibration in
  ``mean_calibration/``), also when the job names no output folder;
* a focality (ROC) report states the score and both thresholds in V/m.

The drivers, ``run_flex_search``, the manifest writer, the recorder and the report generator are
all real; only the SimNIBS optimiser is :class:`tests.test_flex_rerun_same_folder.FakeOpt`. Its
objective is ``-mean(ROI) x scale`` with ``mean(ROI)`` = 0.25 V/m, so the scales below set each
step's score by hand: calibration 1.6 -> achievable 0.4 V/m; points 200/280/240 -> -50/-70/-60.
Run: ``python -m pytest tests/test_flex_multistep_reports.py -q``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_flex_rerun_same_folder import (  # noqa: F401  (flex_project is a fixture)
    flex_config,
    flex_project,
    report_runs,
    reports,
)
from tit.opt.config import FlexConfig

ACHIEVABLE = 0.25 * 1.6  # V/m, the calibration run's roi_mean


@pytest.fixture(autouse=True)
def _no_plot(monkeypatch):
    """matplotlib is a stub on the host (tests/conftest.py); the scatter plot is not pinned here."""
    monkeypatch.setattr("tit.opt.flex.pareto.generate_pareto_plot", lambda *a: None)


def _named_run(page: Path) -> str:
    """The run folder name a report is about (its masthead reads ``sub-001, <run>``)."""
    return re.search(r"<h1>sub-001, ([^<]+)</h1>", page.read_text()).group(1)


def test_a_pareto_job_writes_one_report_about_its_sweep_folder(flex_project):
    from tit.catalog import flex_runs
    from tit.opt.flex.drivers import run_pareto_sweep

    pm, scales = flex_project
    scales[:] = [1.6, 200.0, 280.0, 240.0]  # calibration, then the three points
    sweep = Path(pm.flex_search("001")) / "sweep"
    config = flex_config(
        str(sweep),
        goal="focality",
        mode="flex_pareto",
        pareto=FlexConfig.ParetoSweepConfig(
            roi_pcts=[80.0], nonroi_pcts=[20.0, 30.0, 40.0]
        ),
    )

    result = run_pareto_sweep(config)

    assert result.success and result.best_value == pytest.approx(-70.0)
    (page,) = reports(pm)  # one report for the job
    assert _named_run(page) == "sweep" and sweep.is_dir()
    # No point folder survives; the calibration is nested, so the catalog sees one run.
    assert sorted(p.name for p in sweep.iterdir() if p.is_dir()) == [
        "candidate_history",
        "mean_calibration",
    ]
    assert sorted(p.name for p in (sweep / "candidate_history").iterdir()) == [
        "point_000",
        "point_001",
        "point_002",
    ]
    calibration = json.loads(
        (sweep / "mean_calibration" / "flex_meta.json").read_text()
    )
    assert calibration["goal"] == "mean"
    assert -calibration["result"]["best_value"] == pytest.approx(ACHIEVABLE)
    (entry,) = flex_runs(pm, "001")
    assert entry["name"] == "sweep"

    # The base manifest identifies itself as the sweep it is.
    sweep_meta = entry["manifest"]["pareto"]
    assert sweep_meta["achievable_roi_mean_vm"] == pytest.approx(ACHIEVABLE)
    assert [p["nonroi_threshold_vm"] for p in sweep_meta["points"]] == pytest.approx(
        [0.2 * ACHIEVABLE, 0.3 * ACHIEVABLE, 0.4 * ACHIEVABLE]
    )
    assert [p["roi_threshold_vm"] for p in sweep_meta["points"]] == pytest.approx(
        [0.8 * ACHIEVABLE] * 3
    )
    assert [p["focality_score"] for p in sweep_meta["points"]] == pytest.approx(
        [-50.0, -70.0, -60.0]
    )
    assert sweep_meta["best_point"]["run_index"] == 1
    # The promoted point is point 1 (30 % non-ROI): its manifest, thresholds and score.
    assert (
        entry["manifest"]["thresholds"]
        == f"{0.3 * ACHIEVABLE:.4f},{0.8 * ACHIEVABLE:.4f}"
    )
    assert entry["manifest"]["result"]["best_value"] == pytest.approx(-70.0)
    results = json.loads((sweep / "pareto_results.json").read_text())
    assert len(results["points"]) == 3

    html = page.read_text()
    assert "ROC focality score 70.00" in html
    assert "non-ROI maximum 0.12 V/m, ROI minimum 0.32 V/m" in html
    assert report_runs(page) == "1"
    assert "done (promoted)" in html


def test_a_pareto_rerun_into_the_same_folder_replaces_the_sweep(flex_project):
    from tit.opt.flex.drivers import run_pareto_sweep

    pm, scales = flex_project
    sweep = Path(pm.flex_search("001")) / "sweep"
    grid = dict(goal="focality", mode="flex_pareto")
    scales[:] = [1.6, 200.0, 280.0, 240.0, 1.6, 300.0]
    run_pareto_sweep(
        flex_config(
            str(sweep),
            pareto=FlexConfig.ParetoSweepConfig(
                roi_pcts=[80.0], nonroi_pcts=[20.0, 30.0, 40.0]
            ),
            **grid,
        )
    )
    run_pareto_sweep(
        flex_config(
            str(sweep),
            pareto=FlexConfig.ParetoSweepConfig(roi_pcts=[80.0], nonroi_pcts=[20.0]),
            **grid,
        )
    )
    assert [p.name for p in (sweep / "candidate_history").iterdir()] == ["point_000"]
    meta = json.loads((sweep / "flex_meta.json").read_text())
    assert len(meta["pareto"]["points"]) == 1
    assert meta["result"]["best_value"] == pytest.approx(-75.0)


@pytest.mark.parametrize("named", [True, False])
def test_an_adaptive_job_is_one_run_with_one_report(flex_project, named):
    from tit.catalog import flex_runs
    from tit.opt.flex.drivers import run_adaptive_focality

    pm, scales = flex_project
    scales[:] = [1.6, 280.0]
    folder = str(Path(pm.flex_search("001")) / "thalamus_focal") if named else None
    result = run_adaptive_focality(
        flex_config(folder, goal="focality", mode="flex_adaptive")
    )

    (entry,) = flex_runs(pm, "001")
    assert entry["path"] == result.output_folder
    if named:
        assert entry["name"] == "thalamus_focal"
    assert entry["goal"] == "focality"
    # Adaptive thresholds: 20 % / 80 % of the calibration's achievable 0.4 V/m.
    assert entry["manifest"]["thresholds"] == "0.0800,0.3200"
    calibration = Path(result.output_folder) / "mean_calibration" / "flex_meta.json"
    assert json.loads(calibration.read_text())["goal"] == "mean"
    (page,) = reports(pm)
    assert _named_run(page) == Path(result.output_folder).name
    html = page.read_text()
    assert "ROC focality score 70.00" in html
    assert "non-ROI maximum 0.08 V/m, ROI minimum 0.32 V/m" in html


def test_a_failed_calibration_still_leaves_the_jobs_one_report(flex_project):
    from tit.opt.flex.drivers import run_adaptive_focality

    pm, scales = flex_project
    scales[:] = [float("nan")]  # a non-finite field: the recorder accepts no candidate
    folder = Path(pm.flex_search("001")) / "deep"
    result = run_adaptive_focality(
        flex_config(str(folder), goal="focality", mode="flex_adaptive")
    )
    assert not result.success
    (page,) = reports(pm)  # the calibration's own report says why the job stopped
    assert _named_run(page) == "mean_calibration"
    assert '<h2 id="verdict-h">No valid montage found</h2>' in page.read_text()
    assert (folder / "mean_calibration" / "flex_meta.json").is_file()
    assert not (folder / "flex_meta.json").exists()  # the focality step never ran
