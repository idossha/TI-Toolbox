#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox structural pre-processing pipeline (pre/structural.py)
"""

import os
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from pre.structural import (
    _run_step,
    _run_subject_pipeline,
    run_pipeline,
)
from pre.common import PreprocessError, PreprocessCancelled, CommandRunner


class TestRunStep:
    """Test _run_step helper function"""

    def test_run_step_executes_function_successfully(self):
        """Test executes function and logs success"""
        logger = MagicMock()
        func = MagicMock()

        result = _run_step("Test Step", func, logger)

        func.assert_called_once()
        assert result is True

        # Verify logging
        info_calls = [call[0][0] for call in logger.info.call_args_list]
        assert any("Test Step" in msg and "Started" in msg for msg in info_calls)
        assert any("Test Step" in msg and "Complete" in msg for msg in info_calls)

    def test_run_step_logs_failure_on_exception(self):
        """Test logs failure when function raises exception"""
        logger = MagicMock()
        func = MagicMock(side_effect=RuntimeError("Test error"))

        result = _run_step("Test Step", func, logger)

        assert result is False

        # Verify error was logged
        assert logger.error.called
        error_msg = logger.error.call_args[0][0]
        assert "Test Step failed" in error_msg

    def test_run_step_reraises_preprocess_cancelled(self):
        """Test re-raises PreprocessCancelled without catching"""
        logger = MagicMock()
        func = MagicMock(side_effect=PreprocessCancelled("User cancelled"))

        with pytest.raises(PreprocessCancelled):
            _run_step("Test Step", func, logger)

    def test_run_step_catches_other_exceptions(self):
        """Test catches and handles other exceptions"""
        logger = MagicMock()
        func = MagicMock(side_effect=ValueError("Invalid value"))

        result = _run_step("Test Step", func, logger)

        # Should not raise, should return False
        assert result is False


class TestRunSubjectPipeline:
    """Test _run_subject_pipeline function"""

    @patch("pre.structural.build_logger")
    @patch("pre.structural.get_overwrite_policy")
    @patch("pre.structural.run_dicom_to_nifti")
    def test_run_subject_pipeline_dicom_only(
        self, mock_run_dicom, mock_get_policy, mock_build_logger
    ):
        """Test pipeline with DICOM conversion only"""
        from tit.core.overwrite import OverwritePolicy

        mock_logger = MagicMock()
        mock_build_logger.return_value = mock_logger
        mock_policy = OverwritePolicy(overwrite=False, prompt=False)
        mock_get_policy.return_value = mock_policy

        runner = MagicMock()

        result = _run_subject_pipeline(
            "/test/project",
            "001",
            convert_dicom=True,
            run_recon=False,
            parallel_recon=False,
            create_m2m=False,
            run_tissue=False,
            run_qsiprep_step=False,
            run_qsirecon_step=False,
            qsi_recon_config=None,
            extract_dti_step=False,
            debug=False,
            overwrite=None,
            prompt_overwrite=None,
            runner=runner,
            callback=None,
        )

        assert result is True
        mock_run_dicom.assert_called_once()

    @patch("pre.structural.build_logger")
    @patch("pre.structural.get_overwrite_policy")
    @patch("pre.structural.run_charm")
    @patch("pre.structural.run_subject_atlas")
    def test_run_subject_pipeline_charm_and_atlas(
        self, mock_run_atlas, mock_run_charm, mock_get_policy, mock_build_logger
    ):
        """Test pipeline with charm and subject_atlas"""
        from tit.core.overwrite import OverwritePolicy

        mock_logger = MagicMock()
        mock_build_logger.return_value = mock_logger
        mock_policy = OverwritePolicy(overwrite=False, prompt=False)
        mock_get_policy.return_value = mock_policy

        runner = MagicMock()

        result = _run_subject_pipeline(
            "/test/project",
            "001",
            convert_dicom=False,
            run_recon=False,
            parallel_recon=False,
            create_m2m=True,
            run_tissue=False,
            run_qsiprep_step=False,
            run_qsirecon_step=False,
            qsi_recon_config=None,
            extract_dti_step=False,
            debug=False,
            overwrite=None,
            prompt_overwrite=None,
            runner=runner,
            callback=None,
        )

        assert result is True
        mock_run_charm.assert_called_once()
        mock_run_atlas.assert_called_once()

    @patch("pre.structural.build_logger")
    @patch("pre.structural.get_overwrite_policy")
    @patch("pre.structural.run_recon_all")
    def test_run_subject_pipeline_recon_only(
        self, mock_run_recon, mock_get_policy, mock_build_logger
    ):
        """Test pipeline with recon-all only"""
        from tit.core.overwrite import OverwritePolicy

        mock_logger = MagicMock()
        mock_build_logger.return_value = mock_logger
        mock_policy = OverwritePolicy(overwrite=False, prompt=False)
        mock_get_policy.return_value = mock_policy

        runner = MagicMock()

        result = _run_subject_pipeline(
            "/test/project",
            "001",
            convert_dicom=False,
            run_recon=True,
            parallel_recon=False,
            create_m2m=False,
            run_tissue=False,
            run_qsiprep_step=False,
            run_qsirecon_step=False,
            qsi_recon_config=None,
            extract_dti_step=False,
            debug=False,
            overwrite=None,
            prompt_overwrite=None,
            runner=runner,
            callback=None,
        )

        assert result is True
        mock_run_recon.assert_called_once()

    @patch("pre.structural.build_logger")
    @patch("pre.structural.get_overwrite_policy")
    @patch("pre.structural.run_tissue_analysis")
    def test_run_subject_pipeline_tissue_analysis(
        self, mock_run_tissue, mock_get_policy, mock_build_logger
    ):
        """Test pipeline with tissue analysis"""
        from tit.core.overwrite import OverwritePolicy

        mock_logger = MagicMock()
        mock_build_logger.return_value = mock_logger
        mock_policy = OverwritePolicy(overwrite=False, prompt=False)
        mock_get_policy.return_value = mock_policy

        runner = MagicMock()

        result = _run_subject_pipeline(
            "/test/project",
            "001",
            convert_dicom=False,
            run_recon=False,
            parallel_recon=False,
            create_m2m=False,
            run_tissue=True,
            run_qsiprep_step=False,
            run_qsirecon_step=False,
            qsi_recon_config=None,
            extract_dti_step=False,
            debug=False,
            overwrite=None,
            prompt_overwrite=None,
            runner=runner,
            callback=None,
        )

        assert result is True
        mock_run_tissue.assert_called_once()

    @patch("pre.structural.build_logger")
    @patch("pre.structural.get_overwrite_policy")
    @patch(
        "pre.structural.run_dicom_to_nifti", side_effect=RuntimeError("DICOM failed")
    )
    def test_run_subject_pipeline_returns_false_on_failure(
        self, mock_run_dicom, mock_get_policy, mock_build_logger
    ):
        """Test returns False when a step fails"""
        from tit.core.overwrite import OverwritePolicy

        mock_logger = MagicMock()
        mock_build_logger.return_value = mock_logger
        mock_policy = OverwritePolicy(overwrite=False, prompt=False)
        mock_get_policy.return_value = mock_policy

        runner = MagicMock()

        result = _run_subject_pipeline(
            "/test/project",
            "001",
            convert_dicom=True,
            run_recon=False,
            parallel_recon=False,
            create_m2m=False,
            run_tissue=False,
            run_qsiprep_step=False,
            run_qsirecon_step=False,
            qsi_recon_config=None,
            extract_dti_step=False,
            debug=False,
            overwrite=None,
            prompt_overwrite=None,
            runner=runner,
            callback=None,
        )

        assert result is False


@pytest.mark.unit
def test_run_pipeline_generates_preprocessing_report(tmp_path, monkeypatch):
    from tit import reporting

    project_dir = str(tmp_path)
    subject_id = "001"

    monkeypatch.setattr(
        "pre.structural.ensure_subject_dirs", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "pre.structural.ensure_dataset_descriptions", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "pre.structural._run_subject_pipeline", lambda *_args, **_kwargs: True
    )

    calls = {"generated": False}

    class DummyReportGenerator:
        def __init__(self, project_dir, subject_id):
            calls["init"] = (project_dir, subject_id)
            self.steps = []
            self.scanned = False

        def add_processing_step(self, **kwargs):
            self.steps.append(kwargs)

        def scan_for_data(self):
            self.scanned = True

        def generate(self):
            calls["generated"] = True
            return Path(project_dir) / "report.html"

    monkeypatch.setattr(reporting, "PreprocessingReportGenerator", DummyReportGenerator)

    exit_code = run_pipeline(
        project_dir,
        [subject_id],
        convert_dicom=True,
        run_recon=False,
        parallel_recon=False,
        create_m2m=False,
        run_tissue_analysis=False,
        run_qsiprep=False,
        run_qsirecon=False,
        qsi_recon_config=None,
        extract_dti=False,
        debug=False,
        overwrite=None,
        prompt_overwrite=None,
        stop_event=None,
        logger_callback=None,
        runner=MagicMock(),
    )

    assert exit_code == 0
    assert calls["init"] == (project_dir, subject_id)
    assert calls["generated"] is True


class TestRunPipeline:
    """Test run_pipeline function"""

    def test_run_pipeline_raises_if_no_subjects(self):
        """Test raises PreprocessError if no subjects provided"""
        with pytest.raises(PreprocessError) as exc_info:
            run_pipeline("/test/project", [])

        assert "No subjects provided" in str(exc_info.value)

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_processes_single_subject(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test processes single subject successfully"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        result = run_pipeline(
            "/test/project",
            ["001"],
            convert_dicom=True,
            run_recon=False,
            create_m2m=False,
        )

        assert result == 0
        mock_ensure_dirs.assert_called_once_with("/test/project", "001")
        mock_run_subject.assert_called_once()

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_processes_multiple_subjects(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test processes multiple subjects"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        result = run_pipeline(
            "/test/project", ["001", "002", "003"], convert_dicom=True
        )

        assert result == 0
        assert mock_ensure_dirs.call_count == 3
        assert mock_run_subject.call_count == 3

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_returns_1_on_failure(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test returns 1 when processing fails"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = False  # Failure

        result = run_pipeline("/test/project", ["001"], convert_dicom=True)

        assert result == 1

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_ensures_freesurfer_dataset_description(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test ensures freesurfer dataset description when run_recon=True"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        run_pipeline("/test/project", ["001"], run_recon=True)

        # Verify freesurfer was included in datasets
        call_args = mock_ensure_datasets.call_args[0]
        datasets = call_args[1]
        assert "freesurfer" in datasets

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_ensures_simnibs_dataset_description(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test ensures simnibs dataset description when create_m2m=True"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        run_pipeline("/test/project", ["001"], create_m2m=True)

        # Verify simnibs was included in datasets
        call_args = mock_ensure_datasets.call_args[0]
        datasets = call_args[1]
        assert "simnibs" in datasets

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_always_ensures_ti_toolbox_dataset(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test always ensures ti-toolbox dataset description"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        run_pipeline("/test/project", ["001"], convert_dicom=True)

        # Verify ti-toolbox was included in datasets
        call_args = mock_ensure_datasets.call_args[0]
        datasets = call_args[1]
        assert "ti-toolbox" in datasets

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_strips_whitespace_from_subject_ids(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test strips whitespace from subject IDs"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        run_pipeline("/test/project", ["  001  ", "002\n", "\t003"], convert_dicom=True)

        # Verify subjects were cleaned
        assert mock_run_subject.call_count == 3
        call_subjects = [call[0][1] for call in mock_run_subject.call_args_list]
        assert call_subjects == ["001", "002", "003"]

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_filters_empty_subject_ids(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test filters out empty subject IDs"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        run_pipeline("/test/project", ["001", "", "   ", "002"], convert_dicom=True)

        # Verify only valid subjects were processed
        assert mock_run_subject.call_count == 2

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_creates_runner_if_not_provided(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test creates CommandRunner if not provided"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        run_pipeline(
            "/test/project", ["001"], convert_dicom=True, runner=None  # Not provided
        )

        # Verify runner was passed to subject pipeline
        call_kwargs = mock_run_subject.call_args[1]
        assert "runner" in call_kwargs
        assert isinstance(call_kwargs["runner"], CommandRunner)

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_uses_provided_runner(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test uses provided CommandRunner"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        custom_runner = CommandRunner()

        run_pipeline("/test/project", ["001"], convert_dicom=True, runner=custom_runner)

        # Verify custom runner was passed
        call_kwargs = mock_run_subject.call_args[1]
        assert call_kwargs["runner"] is custom_runner

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_reraises_preprocess_cancelled(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test re-raises PreprocessCancelled exception"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.side_effect = PreprocessCancelled("User cancelled")

        with pytest.raises(PreprocessCancelled):
            run_pipeline("/test/project", ["001"], convert_dicom=True)

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_continues_on_exception(
        self, mock_run_subject, mock_ensure_datasets, mock_ensure_dirs, mock_get_pm
    ):
        """Test continues processing other subjects after exception"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        # First subject raises exception, second succeeds
        mock_run_subject.side_effect = [Exception("First subject failed"), True]

        result = run_pipeline("/test/project", ["001", "002"], convert_dicom=True)

        # Should process both subjects despite first failure
        assert mock_run_subject.call_count == 2
        assert result == 1  # Overall failure

    @patch("pre.structural.get_path_manager")
    @patch("pre.structural.ensure_subject_dirs")
    @patch("pre.structural.ensure_dataset_descriptions")
    @patch("pre.structural.ThreadPoolExecutor")
    @patch("pre.structural._run_subject_pipeline")
    def test_run_pipeline_parallel_recon(
        self,
        mock_run_subject,
        mock_executor,
        mock_ensure_datasets,
        mock_ensure_dirs,
        mock_get_pm,
    ):
        """Test parallel recon-all processing"""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        mock_run_subject.return_value = True

        # Mock ThreadPoolExecutor
        mock_executor_instance = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance

        # Mock futures
        mock_future = MagicMock()
        mock_future.result.return_value = True
        mock_executor_instance.submit.return_value = mock_future

        from concurrent.futures import as_completed

        with patch("pre.structural.as_completed", return_value=[mock_future]):
            result = run_pipeline(
                "/test/project", ["001", "002"], run_recon=True, parallel_recon=True
            )

            # Verify ThreadPoolExecutor was used
            assert mock_executor.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
