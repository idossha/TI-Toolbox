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

With "Optimize current ratio" ticked (the desktop leaves that box enabled for every goal, and the
adaptive mode is its default threshold mode), every step must also get the ratio search: the
splits are ``ratio_levels``' documented grid -- ``n`` (21, odd) channel-1 currents spaced evenly
from a quarter to three quarters of the total ``2 x current_mA``, channel 2 taking the rest --
computed here from that sentence, not from the function. Before 2026-10-22 ``FlexConfig`` refused
the combination at submit ("requires explicit numeric thresholds") although both drivers set the
thresholds before every focality step (audit_flex #1).
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

for _mod in (
    "simnibs.optimization",
    "simnibs.optimization.tes_flex_optimization",
    "simnibs.optimization.tes_flex_optimization.electrode_layout",
):
    sys.modules.setdefault(_mod, MagicMock())

from tit.jobs.config_check import check_job_config
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


def _ratio_grid(current_mA: float, n: int = 21) -> list[tuple[float, float]]:
    """The documented split grid: channel 1 from T/4 to 3T/4 in n-1 equal steps, T = 2 x I."""
    total = 2.0 * current_mA
    step = (0.75 * total - 0.25 * total) / (n - 1)
    return [
        (0.25 * total + k * step, total - (0.25 * total + k * step)) for k in range(n)
    ]


def _run_desktop_job(
    kind: str, tmp_path, ratio_installs: list | None = None, **overrides
) -> list[tuple[str, object]]:
    """Submit *kind* as the desktop does and run the runner; return (goal, threshold) per run.

    *overrides* are form fields layered over the desktop config; each ratio-search install
    (``base_mA``, ``ratios``) is appended to *ratio_installs* when given.
    """
    project = tmp_path / "project"
    project.mkdir()
    manager = JobManager(str(project), budget=Cost(cpus=1, mem_gb=1))
    config = with_app_defaults(kind, {**DESKTOP_FOCALITY_CONFIG, **overrides})
    # The submit-time guard POST /api/jobs runs, on exactly what the desktop sends.
    check_job_config(kind, config)
    job = manager.submit(kind, config, ["001"])
    config_path = manager._runner_config_path(manager._specs[job["id"]])

    pm = MagicMock()
    pm.m2m.return_value = str(tmp_path / "m2m_001")
    pm.flex_search.return_value = str(tmp_path / "flex")

    runs: list[tuple[str, object]] = []

    def fake_run_flex_search(config, *, report=True):
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

    def fake_install_ratio_search(opt, objective, *, base_mA, ratios):
        if ratio_installs is not None:
            ratio_installs.append({"base_mA": base_mA, "ratios": list(ratios)})

    from tit.opt.flex.__main__ import main

    with (
        patch(
            "tit.opt.flex.objectives.install_ratio_search", fake_install_ratio_search
        ),
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "focality_runs"),
    [
        ("flex_adaptive", [_expected(20, 80)]),
        ("flex_pareto", [_expected(20, 80), _expected(30, 80), _expected(40, 80)]),
    ],
)
def test_derived_threshold_modes_run_with_the_current_ratio_search(
    kind, focality_runs, tmp_path
):
    installs: list = []
    runs = _run_desktop_job(
        kind,
        tmp_path,
        ratio_installs=installs,
        optimize_current_ratio=True,
        current_mA=1.5,
    )
    assert runs == [("mean", None)] + [("focality", t) for t in focality_runs]
    # The ratio search is installed on every step, mean calibration included, over the
    # documented grid for 2 x 1.5 mA.
    assert len(installs) == len(runs)
    want = _ratio_grid(1.5)
    for install in installs:
        assert install["base_mA"] == 1.5
        assert np.asarray(install["ratios"]) == pytest.approx(np.array(want))


@pytest.mark.unit
def test_submit_guard_validates_the_mode_the_kind_names():
    """kind=flex_adaptive runs FlexConfig(mode='flex_adaptive'); a goal that mode cannot run
    (FlexConfig: mode flex_adaptive/flex_pareto requires goal 'focality') is refused at submit.
    """
    config = with_app_defaults(
        "flex_adaptive", {**DESKTOP_FOCALITY_CONFIG, "goal": "focality_tf"}
    )
    with pytest.raises(
        ValueError, match="mode='flex_adaptive' requires goal='focality'"
    ):
        check_job_config("flex_adaptive", config)
    # The same body as a plain single run is a valid threshold-free focality search.
    check_job_config("flex", {**config, "adaptive": None})


@pytest.mark.unit
def test_fixed_threshold_ratio_search_without_thresholds_is_still_refused():
    """mode='flex' has no driver to derive thresholds: the ratio search's own ROC objective
    needs them, so the submit guard refuses the config instead of the runner failing later.
    """
    config = with_app_defaults(
        "flex",
        {**DESKTOP_FOCALITY_CONFIG, "optimize_current_ratio": True, "thresholds": None},
    )
    with pytest.raises(ValueError, match="thresholds"):
        check_job_config("flex", config)
