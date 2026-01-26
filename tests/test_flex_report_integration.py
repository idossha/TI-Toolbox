#!/usr/bin/env simnibs_python
"""
Integration-style unit test for flex-search reporting hook.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.mark.unit
def test_flex_main_triggers_report_generation(tmp_path, monkeypatch):
    from tit.opt.flex import flex as flex_module
    from tit import reporting

    args = SimpleNamespace(
        n_multistart=1,
        subject="001",
        goal="mean",
        postproc="max_TI",
        roi_method="spherical",
        electrode_shape="rect",
        dimensions="8,8",
        thickness=4.0,
        current=1.0,
        non_roi_method="everything_else",
        thresholds="0.2",
        enable_mapping=False,
        disable_mapping_simulation=False,
        max_iterations=None,
        population_size=None,
        cpus=None,
        run_final_electrode_simulation=False,
        skip_final_electrode_simulation=True,
        project_dir=str(tmp_path),
        eeg_net="GSN-HydroCel-185",
        roi_name="Target ROI",
    )

    base_output = tmp_path / "flex-output"
    base_output.mkdir(parents=True, exist_ok=True)

    def build_optimization(_args):
        return SimpleNamespace(output_folder=str(base_output))

    monkeypatch.setattr(flex_module.flex_config, "parse_arguments", lambda: args)
    monkeypatch.setattr(flex_module.flex_config, "build_optimization", build_optimization)
    monkeypatch.setattr(
        flex_module.flex_config, "configure_optimizer_options", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        flex_module, "configure_external_loggers", lambda *_a, **_k: None
    )

    monkeypatch.setattr(flex_module.multi_start, "run_single_optimization", lambda *_a, **_k: 1.0)
    monkeypatch.setattr(flex_module.multi_start, "copy_best_solution", lambda *_a, **_k: True)
    monkeypatch.setattr(
        flex_module.multi_start,
        "create_single_optimization_summary_file",
        lambda *_a, **_k: None,
    )

    for name in [
        "log_optimization_start",
        "log_optimization_step_start",
        "log_run_details",
        "log_optimization_step_complete",
        "log_optimization_step_failed",
        "log_optimization_complete",
        "log_session_footer",
    ]:
        monkeypatch.setattr(flex_module.flex_log, name, lambda *_a, **_k: None)

    monkeypatch.setattr(flex_module.flex_log, "setup_logger", lambda *_a, **_k: MagicMock())

    calls = {"generated": False}

    class DummyReportGenerator:
        def __init__(self, project_dir, subject_id):
            calls["init"] = (project_dir, subject_id)

        def set_configuration(self, **kwargs):
            calls["config"] = kwargs

        def set_roi_info(self, **kwargs):
            calls["roi"] = kwargs

        def add_search_result(self, **kwargs):
            calls.setdefault("results", []).append(kwargs)

        def set_best_solution(self, **kwargs):
            calls["best"] = kwargs

        def generate(self):
            calls["generated"] = True
            return Path(tmp_path) / "flex_report.html"

    monkeypatch.setattr(reporting, "FlexSearchReportGenerator", DummyReportGenerator)

    exit_code = flex_module.main()

    assert exit_code == 0
    assert calls["init"] == (str(tmp_path), "001")
    assert calls["generated"] is True
