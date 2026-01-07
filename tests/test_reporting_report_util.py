#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/reporting/report_util.py

Goal: cover the reporting entrypoints and filesystem conventions without relying
on external tools or large datasets.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_ensure_reports_directory_creates_subject_dir(tmp_path: Path):
    from tit.reporting import report_util as ru

    reports_dir = ru._ensure_reports_directory(str(tmp_path), "001")
    assert reports_dir.exists()
    assert reports_dir.is_dir()
    assert str(reports_dir).endswith(str(Path("derivatives/ti-toolbox/reports/sub-001")))


@pytest.mark.unit
def test_get_report_filename_is_stable_with_timestamp():
    from tit.reporting import report_util as ru

    ts = "20200101_010101"
    assert ru._get_report_filename("preprocessing", "001", timestamp=ts) == f"{ru.PREPROCESSING_REPORT_PREFIX}_{ts}.html"
    assert ru._get_report_filename("simulation", "sub-001", timestamp=ts) == f"{ru.SIMULATION_REPORT_PREFIX}_{ts}.html"
    assert ru._get_report_filename("custom", "001", timestamp=ts) == f"custom_report_{ts}.html"


@pytest.mark.unit
def test_create_preprocessing_report_applies_log_and_defaults_output_path(tmp_path: Path):
    from tit.reporting import report_util as ru

    # Make output deterministic
    with patch.object(ru, "_generate_timestamp", return_value="20200101_000000"), \
         patch.object(ru, "_ensure_reports_directory", return_value=tmp_path / "reports"), \
         patch.object(ru, "PreprocessingReportGenerator") as Gen:
        inst = MagicMock()
        # return the path we were asked to write
        inst.generate_html_report.side_effect = lambda p: p
        Gen.return_value = inst

        processing_log = {
            "steps": [{"step_name": "step1", "description": "desc"}],
            "errors": [{"error_message": "boom"}],
            "warnings": [{"warning_message": "warn"}],
        }

        out = ru.create_preprocessing_report(str(tmp_path), "sub-001", processing_log=processing_log)

        Gen.assert_called_once_with(str(tmp_path), "001")
        inst.add_processing_step.assert_called_once()
        inst.add_error.assert_called_once()
        inst.add_warning.assert_called_once()
        assert out.endswith("pre_processing_report_20200101_000000.html")


@pytest.mark.unit
def test_create_simulation_report_session_default_path(tmp_path: Path):
    from tit.reporting import report_util as ru

    with patch.object(ru, "SimulationReportGenerator") as Gen:
        inst = MagicMock()
        inst.generate_report.side_effect = lambda p: p
        Gen.return_value = inst

        out = ru.create_simulation_report(str(tmp_path), simulation_session_id="sess123", simulation_log=None)

        Gen.assert_called_once_with(str(tmp_path), "sess123")
        # session report goes into project_dir/derivatives/ti-toolbox/reports/
        assert out.endswith(str(Path("derivatives/ti-toolbox/reports/simulation_session_sess123.html")))


@pytest.mark.unit
def test_list_reports_filters_and_sorts(tmp_path: Path):
    from tit.reporting import report_util as ru

    base = tmp_path / "derivatives" / "ti-toolbox" / "reports"
    subdir = base / "sub-001"
    subdir.mkdir(parents=True)

    # Create two reports with distinct mtimes
    older = subdir / "pre_processing_report_20200101_000000.html"
    newer = subdir / "simulation_report_20200102_000000.html"
    older.write_text("old")
    newer.write_text("new")
    older_mtime = 1_600_000_000
    newer_mtime = 1_600_000_100
    older.touch()
    newer.touch()
    import os
    os.utime(older, (older_mtime, older_mtime))
    os.utime(newer, (newer_mtime, newer_mtime))

    reports = ru.list_reports(str(tmp_path), subject_id="001")
    assert len(reports) == 2
    assert reports[0]["filename"] == newer.name  # newest first

    pre = ru.list_reports(str(tmp_path), subject_id="001", report_type="preprocessing")
    assert len(pre) == 1
    assert pre[0]["type"] == "preprocessing"

    latest = ru.get_latest_report(str(tmp_path), "001", "simulation")
    assert latest.endswith(newer.name)


