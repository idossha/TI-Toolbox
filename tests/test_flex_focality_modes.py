"""The Optimizer's threshold-based focality modes reach SimNIBS with a threshold.

User report against v3.1.0: Optimizer -> Threshold-based focality -> Multi-threshold, every
default left alone, fails with SimNIBS's ``ValueError: Please define TESoptimize.threshold for
focallity optimization!``.

Pins the whole path the desktop drives: the config it submits for kind ``flex_adaptive`` /
``flex_pareto`` (``thresholds: null`` and no ``mode`` -- the kind carries the mode), through the
server's defaults and the job manager's runner ``config.json``, into ``tit.opt.flex.__main__``'s
driver dispatch and the real :func:`tit.opt.flex.builder.build_optimization`. Only SimNIBS (the
optimisation object) and the optimisation run itself are faked, plus the sweep's
plot (matplotlib is mocked on the host).

Expected thresholds are the percentages the form shows (``app_defaults``: adaptive 80/20,
multi-threshold ROI 80 x non-ROI 20/30/40) of the mean run's achievable ROI intensity, which the
fake mean run reports as 4 V/m (``best_value=-4``: SimNIBS stores the negated mean). SimNIBS's
``TESoptimize.threshold`` order is ``[non-ROI, ROI]`` in V/m.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

for _mod in (
    "simnibs.optimization",
    "simnibs.optimization.tes_flex_optimization",
    "simnibs.optimization.tes_flex_optimization.electrode_layout",
):
    sys.modules.setdefault(_mod, MagicMock())

from tit.jobs.manager import JobManager
from tit.jobs.spec import Cost
from tit.opt.config import FlexResult
from tit.server.app_defaults import with_app_defaults

ACHIEVABLE_V_PER_M = 4.0

# What desktop/src/renderer/pages/optimizer/flexConfig.ts `buildFlexConfig` sends for a
# threshold-based focality search in adaptive / multi-threshold mode: no thresholds, no mode.
DESKTOP_FOCALITY_CONFIG = {
    "subject_id": "001",
    "goal": "focality",
    "non_roi_method": "everything_else",
    "non_roi": None,
    "thresholds": None,
    "roi": {
        "_type": "SphericalROI",
        "x": [-42.0],
        "y": [-20.0],
        "z": [55.0],
        "radius": [10.0],
        "use_mni": False,
        "volumetric": False,
        "tissues": "GM",
    },
}


def _expected(nonroi_pct: float, roi_pct: float) -> list[float]:
    return [
        round(ACHIEVABLE_V_PER_M * nonroi_pct / 100, 4),
        round(ACHIEVABLE_V_PER_M * roi_pct / 100, 4),
    ]


def _run_desktop_job(kind: str, tmp_path) -> list[tuple[str, object]]:
    """Submit *kind* as the desktop does and run the runner; return (goal, threshold) per run."""
    project = tmp_path / "project"
    project.mkdir()
    manager = JobManager(str(project), budget=Cost(cpus=1, mem_gb=1))
    job = manager.submit(
        kind, with_app_defaults(kind, DESKTOP_FOCALITY_CONFIG), ["001"]
    )
    config_path = manager._runner_config_path(manager._specs[job["id"]])

    pm = MagicMock()
    pm.m2m.return_value = str(tmp_path / "m2m_001")
    pm.flex_search.return_value = str(tmp_path / "flex")

    runs: list[tuple[str, object]] = []

    def fake_run_flex_search(config):
        from tit.opt.flex.builder import build_optimization

        opt = build_optimization(config)
        # Only an assigned threshold lands in the instance dict; a MagicMock invents the rest.
        runs.append((opt.goal, vars(opt).get("threshold")))
        return FlexResult(
            success=True,
            output_folder=config.output_folder or str(tmp_path / "flex" / "mean"),
            function_values=[-ACHIEVABLE_V_PER_M],
            best_value=-ACHIEVABLE_V_PER_M,
            best_run_index=0,
        )

    from tit.opt.flex.__main__ import main

    with (
        patch("tit.paths.get_path_manager", return_value=pm),
        patch(
            "tit.opt.flex.runtime.optimization_class",
            return_value=lambda: MagicMock(),
        ),
        patch("tit.opt.flex.builder.utils.configure_roi"),
        patch("tit.opt.flex.__main__.run_flex_search", fake_run_flex_search),
        patch("tit.opt.flex.flex.run_flex_search", fake_run_flex_search),
        patch("tit.logger.add_stream_handler"),
        # The sweep's JSON + plot; matplotlib is mocked on the host.
        patch("tit.opt.flex.pareto.save_results", return_value=("r.json", "r.png")),
        patch.object(sys, "argv", ["prog", config_path]),
        pytest.raises(SystemExit) as exit_info,
    ):
        main()
    assert exit_info.value.code == 0
    return runs


@pytest.mark.unit
def test_runner_config_carries_the_mode_its_kind_names(tmp_path):
    manager = JobManager(str(tmp_path), budget=Cost(cpus=1, mem_gb=1))
    for kind in ("flex", "flex_adaptive", "flex_pareto"):
        job = manager.submit(kind, with_app_defaults(kind, DESKTOP_FOCALITY_CONFIG), [])
        with open(manager._runner_config_path(manager._specs[job["id"]])) as f:
            assert json.load(f)["mode"] == kind


@pytest.mark.unit
def test_multi_threshold_defaults_give_every_focality_run_a_threshold(tmp_path):
    runs = _run_desktop_job("flex_pareto", tmp_path)
    assert runs == [
        ("mean", None),
        ("focality", _expected(20, 80)),
        ("focality", _expected(30, 80)),
        ("focality", _expected(40, 80)),
    ]


@pytest.mark.unit
def test_adaptive_defaults_give_the_focality_run_a_threshold(tmp_path):
    runs = _run_desktop_job("flex_adaptive", tmp_path)
    assert runs == [("mean", None), ("focality", _expected(20, 80))]
