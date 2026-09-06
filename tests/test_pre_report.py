"""Tests for tit.pre.report -- the ``report`` job kind's runner (F0).

F0 evidence (dev/notes/v3-pipelines-program.md §0): every trailing report job of a
`pre` group failed with ``unknown job kind: 'report'`` (jobs 614b666712054f03,
d6ccfcce2e2c43ce) because tit/jobs/kinds.py's MODULE_FOR_KIND had no entry for it.
This module is that entry's runner: `simnibs_python -m tit.pre.report config.json`,
config as produced by tit.jobs.plans.plan_preprocessing's trailing PlannedJob.
"""

import json
from unittest.mock import MagicMock, patch, mock_open

import pytest

MODULE = "tit.pre.report"


def _config(**overrides):
    base = {"project_dir": "/proj", "subject_ids": ["001"]}
    base.update(overrides)
    return base


@pytest.mark.unit
class TestMain:
    @patch(f"{MODULE}.sys.exit")
    @patch(f"{MODULE}.sys.argv", ["__main__", "/tmp/config.json"])
    @patch("tit.reporting.PreprocessingReportGenerator")
    @patch(f"{MODULE}._hold_locks")
    def test_reports_every_requested_step_as_completed(
        self, mock_locks, mock_report_cls, mock_exit
    ):
        mock_locks.return_value.__enter__ = MagicMock(return_value=None)
        mock_locks.return_value.__exit__ = MagicMock(return_value=False)
        mock_gen = MagicMock()
        mock_gen.generate.return_value = "/proj/derivatives/ti-toolbox/reports/sub-001/x.html"
        mock_report_cls.return_value = mock_gen

        config = _config(convert_dicom=True, create_m2m=True, run_tissue_analysis=True)
        with patch("builtins.open", mock_open(read_data=json.dumps(config))), patch(
            f"{MODULE}.get_path_manager"
        ) as mock_gpm:
            mock_gpm.return_value.project_dir = "/proj"
            from tit.pre.report import main

            main()

        # convert_dicom + create_m2m (two steps: charm + atlas) + run_tissue_analysis = 4 steps.
        assert mock_gen.add_processing_step.call_count == 4
        step_names = {c.kwargs["step_name"] for c in mock_gen.add_processing_step.call_args_list}
        assert step_names == {
            "DICOM Conversion",
            "SimNIBS charm",
            "Subject Atlas Segmentation",
            "Tissue Analysis",
        }
        for c in mock_gen.add_processing_step.call_args_list:
            assert c.kwargs["status"] == "completed"

        mock_gen.scan_for_data.assert_called_once()
        mock_gen.generate.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch(f"{MODULE}.sys.exit")
    @patch(f"{MODULE}.sys.argv", ["__main__", "/tmp/config.json"])
    @patch("tit.reporting.PreprocessingReportGenerator")
    @patch(f"{MODULE}._hold_locks")
    def test_flag_not_requested_is_not_reported(self, mock_locks, mock_report_cls, mock_exit):
        mock_locks.return_value.__enter__ = MagicMock(return_value=None)
        mock_locks.return_value.__exit__ = MagicMock(return_value=False)
        mock_gen = MagicMock()
        mock_gen.generate.return_value = "/proj/report.html"
        mock_report_cls.return_value = mock_gen

        config = _config(convert_dicom=True)  # create_m2m, etc. left False
        with patch("builtins.open", mock_open(read_data=json.dumps(config))), patch(
            f"{MODULE}.get_path_manager"
        ) as mock_gpm:
            mock_gpm.return_value.project_dir = "/proj"
            from tit.pre.report import main

            main()

        step_names = {c.kwargs["step_name"] for c in mock_gen.add_processing_step.call_args_list}
        assert step_names == {"DICOM Conversion"}
        mock_exit.assert_called_once_with(0)

    @patch(f"{MODULE}.sys.exit")
    @patch(f"{MODULE}.sys.argv", ["__main__", "/tmp/config.json"])
    @patch("tit.reporting.PreprocessingReportGenerator")
    @patch(f"{MODULE}._hold_locks")
    def test_report_generation_failure_exits_nonzero(
        self, mock_locks, mock_report_cls, mock_exit
    ):
        mock_locks.return_value.__enter__ = MagicMock(return_value=None)
        mock_locks.return_value.__exit__ = MagicMock(return_value=False)
        mock_gen = MagicMock()
        mock_gen.generate.side_effect = OSError("disk full")
        mock_report_cls.return_value = mock_gen

        config = _config(convert_dicom=True)
        with patch("builtins.open", mock_open(read_data=json.dumps(config))), patch(
            f"{MODULE}.get_path_manager"
        ) as mock_gpm:
            mock_gpm.return_value.project_dir = "/proj"
            from tit.pre.report import main

            main()

        mock_exit.assert_called_once_with(1)

    @patch(f"{MODULE}.sys.argv", ["__main__", "/tmp/config.json"])
    def test_rejects_more_than_one_subject(self):
        # A misuse guard: plan_preprocessing only ever emits one subject per report job.
        # sys.exit is deliberately left real here (not mocked to a no-op) so the test
        # proves execution actually stops instead of falling through into report building.
        config = _config(subject_ids=["001", "002"])
        with patch("builtins.open", mock_open(read_data=json.dumps(config))), patch(
            f"{MODULE}.get_path_manager"
        ):
            from tit.pre.report import main

            with pytest.raises(SystemExit, match="one subject"):
                main()
