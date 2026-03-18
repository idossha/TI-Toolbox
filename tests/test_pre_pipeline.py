#!/usr/bin/env python3
"""
Tests for tit/pre/structural.py — run_pipeline coverage.

Covers:
- parallel_recon path (lines 296-392)
- Report generation loop (lines 432-505)
- Individual step flags: run_qsiprep, run_qsirecon, extract_dti, run_subcortical
- Runner stop_event reassignment (line 296)
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy deps before importing tit.pre
for _mod in (
    "nibabel",
    "numpy",
    "scipy",
    "scipy.ndimage",
    "scipy.stats",
    "h5py",
    "simnibs",
):
    sys.modules.setdefault(_mod, MagicMock())

from tit.pre.structural import _run_step, _run_subject_pipeline, run_pipeline
from tit.pre.utils import PreprocessError, CommandRunner

STRUCTURAL = "tit.pre.structural"
REPORTING = "tit.reporting"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DummyReportGen:
    """Stand-in for PreprocessingReportGenerator that records calls."""

    instances: list = []

    def __init__(self, project_dir, subject_id):
        self.project_dir = project_dir
        self.subject_id = subject_id
        self.steps = []
        self.scanned = False
        self.generated = False
        DummyReportGen.instances.append(self)

    def add_processing_step(self, **kwargs):
        self.steps.append(kwargs)

    def scan_for_data(self):
        self.scanned = True

    def generate(self):
        self.generated = True
        return f"/proj/report_{self.subject_id}.html"

    @classmethod
    def reset(cls):
        cls.instances = []


@pytest.fixture
def dummy_report():
    """Reset DummyReportGen instance tracker before each test."""
    DummyReportGen.reset()
    return DummyReportGen


@pytest.fixture
def pipeline_mocks():
    """Provide common mocks for _run_subject_pipeline tests."""
    with (
        patch(f"{STRUCTURAL}.get_path_manager") as mock_pm,
        patch(f"{STRUCTURAL}.ensure_subject_dirs") as mock_dirs,
        patch(f"{STRUCTURAL}.ensure_dataset_descriptions") as mock_datasets,
        patch(f"{STRUCTURAL}.build_logger") as mock_logger,
        patch(f"{STRUCTURAL}.run_dicom_to_nifti") as mock_dicom,
        patch(f"{STRUCTURAL}.run_charm") as mock_charm,
        patch(f"{STRUCTURAL}.run_subject_atlas") as mock_atlas,
        patch(f"{STRUCTURAL}.run_recon_all") as mock_recon,
        patch(f"{STRUCTURAL}.run_tissue_analysis") as mock_tissue,
        patch(f"{STRUCTURAL}.run_qsiprep") as mock_qsiprep,
        patch(f"{STRUCTURAL}.run_qsirecon") as mock_qsirecon,
        patch(f"{STRUCTURAL}.extract_dti_tensor") as mock_dti,
        patch(f"{STRUCTURAL}.run_subcortical_segmentations") as mock_subcort,
    ):
        mock_logger.return_value = MagicMock()
        yield {
            "pm": mock_pm,
            "dirs": mock_dirs,
            "datasets": mock_datasets,
            "logger": mock_logger,
            "dicom": mock_dicom,
            "charm": mock_charm,
            "atlas": mock_atlas,
            "recon": mock_recon,
            "tissue": mock_tissue,
            "qsiprep": mock_qsiprep,
            "qsirecon": mock_qsirecon,
            "dti": mock_dti,
            "subcort": mock_subcort,
        }


def _make_runner():
    """Create a mock CommandRunner."""
    runner = MagicMock(spec=CommandRunner)
    runner.stop_event = None
    return runner


# ---------------------------------------------------------------------------
# _run_step
# ---------------------------------------------------------------------------


class TestRunStep:
    """Tests for the _run_step helper."""

    def test_calls_func_and_logs(self):
        logger = MagicMock()
        func = MagicMock()

        _run_step("My Step", func, logger)

        func.assert_called_once()
        info_msgs = [c[0][0] for c in logger.info.call_args_list]
        assert any("My Step" in m and "Started" in m for m in info_msgs)
        assert any("My Step" in m and "Complete" in m for m in info_msgs)

    def test_propagates_exception(self):
        """_run_step does not catch exceptions — they propagate."""
        logger = MagicMock()
        func = MagicMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            _run_step("Failing Step", func, logger)


# ---------------------------------------------------------------------------
# _run_subject_pipeline — individual step flags
# ---------------------------------------------------------------------------


class TestRunSubjectPipeline:
    """Tests for _run_subject_pipeline step dispatch."""

    def _call(self, mocks, **overrides):
        defaults = dict(
            convert_dicom=False,
            run_recon=False,
            parallel_recon=False,
            create_m2m=False,
            run_tissue=False,
            run_qsiprep_step=False,
            run_qsirecon_step=False,
            qsiprep_config=None,
            qsi_recon_config=None,
            extract_dti_step=False,
            run_subcortical=False,
            debug=False,
            runner=MagicMock(),
            callback=None,
        )
        defaults.update(overrides)
        _run_subject_pipeline("/proj", "001", **defaults)

    def test_qsiprep_step(self, pipeline_mocks):
        self._call(pipeline_mocks, run_qsiprep_step=True)
        pipeline_mocks["qsiprep"].assert_called_once()

    def test_qsirecon_step(self, pipeline_mocks):
        self._call(pipeline_mocks, run_qsirecon_step=True)
        pipeline_mocks["qsirecon"].assert_called_once()

    def test_extract_dti_step(self, pipeline_mocks):
        self._call(pipeline_mocks, extract_dti_step=True)
        pipeline_mocks["dti"].assert_called_once()

    def test_subcortical_step(self, pipeline_mocks):
        self._call(pipeline_mocks, run_subcortical=True)
        pipeline_mocks["subcort"].assert_called_once()

    def test_recon_only_path(self, pipeline_mocks):
        """run_recon=True without convert_dicom or create_m2m takes the recon-only branch."""
        self._call(pipeline_mocks, run_recon=True)
        pipeline_mocks["recon"].assert_called_once()
        pipeline_mocks["dicom"].assert_not_called()
        pipeline_mocks["charm"].assert_not_called()

    def test_dicom_and_recon(self, pipeline_mocks):
        """convert_dicom=True with run_recon=True takes the else branch."""
        self._call(pipeline_mocks, convert_dicom=True, run_recon=True)
        pipeline_mocks["dicom"].assert_called_once()
        pipeline_mocks["recon"].assert_called_once()

    def test_create_m2m_runs_charm_and_atlas(self, pipeline_mocks):
        self._call(pipeline_mocks, create_m2m=True)
        pipeline_mocks["charm"].assert_called_once()
        pipeline_mocks["atlas"].assert_called_once()

    def test_qsirecon_config_passed(self, pipeline_mocks):
        """qsi_recon_config dict is threaded through to run_qsirecon."""
        cfg = {"recon_specs": ["dipy_dki"], "atlases": ["AAL116"], "use_gpu": True}
        self._call(pipeline_mocks, run_qsirecon_step=True, qsi_recon_config=cfg)
        pipeline_mocks["qsirecon"].assert_called_once()
        kw = pipeline_mocks["qsirecon"].call_args
        assert kw.kwargs.get("recon_specs") == ["dipy_dki"]


# ---------------------------------------------------------------------------
# run_pipeline — parallel_recon path (lines 298-409)
# ---------------------------------------------------------------------------


class TestRunPipelineParallelRecon:
    """Tests for the parallel_recon=True branch of run_pipeline."""

    def _setup_executor(self, mock_executor_cls, mock_as_completed, n_subjects=2):
        mock_ctx = MagicMock()
        mock_executor_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_executor_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_future = MagicMock()
        mock_future.result.return_value = None
        mock_ctx.submit.return_value = mock_future
        mock_as_completed.return_value = [mock_future] * n_subjects
        return mock_ctx

    def test_parallel_recon_dispatches_phases(self, pipeline_mocks, dummy_report):
        """parallel_recon=True with 2 subjects uses ThreadPoolExecutor."""
        with (
            patch(f"{STRUCTURAL}.ThreadPoolExecutor") as mock_exec,
            patch(f"{STRUCTURAL}.as_completed") as mock_ac,
            patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report),
        ):
            self._setup_executor(mock_exec, mock_ac)
            result = run_pipeline(
                ["001", "002"],
                run_recon=True,
                parallel_recon=True,
                runner=_make_runner(),
            )
        assert result == 0
        assert mock_exec.called

    def test_parallel_recon_with_tissue_analysis(self, pipeline_mocks, dummy_report):
        """Tissue analysis runs after parallel recon."""
        with (
            patch(f"{STRUCTURAL}.ThreadPoolExecutor") as mock_exec,
            patch(f"{STRUCTURAL}.as_completed") as mock_ac,
            patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report),
        ):
            self._setup_executor(mock_exec, mock_ac)
            result = run_pipeline(
                ["001", "002"],
                run_recon=True,
                parallel_recon=True,
                run_tissue_analysis=True,
                runner=_make_runner(),
            )
        assert result == 0
        pipeline_mocks["tissue"].assert_called()

    def test_parallel_recon_with_qsi_steps(self, pipeline_mocks, dummy_report):
        """QSI steps run after parallel recon."""
        with (
            patch(f"{STRUCTURAL}.ThreadPoolExecutor") as mock_exec,
            patch(f"{STRUCTURAL}.as_completed") as mock_ac,
            patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report),
        ):
            self._setup_executor(mock_exec, mock_ac)
            result = run_pipeline(
                ["001", "002"],
                run_recon=True,
                parallel_recon=True,
                run_qsiprep=True,
                run_qsirecon=True,
                extract_dti=True,
                runner=_make_runner(),
            )
        assert result == 0
        pipeline_mocks["qsiprep"].assert_called()
        pipeline_mocks["qsirecon"].assert_called()
        pipeline_mocks["dti"].assert_called()

    def test_parallel_recon_with_subcortical(self, pipeline_mocks, dummy_report):
        """Subcortical segmentations run after parallel recon."""
        with (
            patch(f"{STRUCTURAL}.ThreadPoolExecutor") as mock_exec,
            patch(f"{STRUCTURAL}.as_completed") as mock_ac,
            patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report),
        ):
            self._setup_executor(mock_exec, mock_ac)
            result = run_pipeline(
                ["001", "002"],
                run_recon=True,
                parallel_recon=True,
                run_subcortical_segmentations=True,
                runner=_make_runner(),
            )
        assert result == 0
        pipeline_mocks["subcort"].assert_called()

    def test_parallel_recon_uses_parallel_cores(self, pipeline_mocks, dummy_report):
        """parallel_cores caps ThreadPoolExecutor workers."""
        with (
            patch(f"{STRUCTURAL}.ThreadPoolExecutor") as mock_exec,
            patch(f"{STRUCTURAL}.as_completed") as mock_ac,
            patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report),
        ):
            self._setup_executor(mock_exec, mock_ac)
            run_pipeline(
                ["001", "002"],
                run_recon=True,
                parallel_recon=True,
                parallel_cores=2,
                runner=_make_runner(),
            )
        mock_exec.assert_called_once_with(max_workers=2)


# ---------------------------------------------------------------------------
# run_pipeline — report generation (lines 432-505)
# ---------------------------------------------------------------------------


class TestRunPipelineReports:
    """Tests for report generation at the end of run_pipeline."""

    @patch(f"{STRUCTURAL}._run_subject_pipeline")
    @patch(f"{STRUCTURAL}.ensure_dataset_descriptions")
    @patch(f"{STRUCTURAL}.ensure_subject_dirs")
    @patch(f"{STRUCTURAL}.get_path_manager")
    def test_report_generated_for_each_subject(
        self, mock_pm, mock_dirs, mock_datasets, mock_run_sub, dummy_report
    ):
        with patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report):
            result = run_pipeline(
                ["001", "002"],
                convert_dicom=True,
                runner=_make_runner(),
            )
        assert result == 0
        assert len(dummy_report.instances) == 2
        assert all(inst.generated for inst in dummy_report.instances)
        assert all(inst.scanned for inst in dummy_report.instances)

    @patch(f"{STRUCTURAL}._run_subject_pipeline")
    @patch(f"{STRUCTURAL}.ensure_dataset_descriptions")
    @patch(f"{STRUCTURAL}.ensure_subject_dirs")
    @patch(f"{STRUCTURAL}.get_path_manager")
    def test_report_includes_dicom_step(
        self, mock_pm, mock_dirs, mock_datasets, mock_run_sub, dummy_report
    ):
        with patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report):
            run_pipeline(["001"], convert_dicom=True, runner=_make_runner())
        step_names = [s["step_name"] for s in dummy_report.instances[0].steps]
        assert "DICOM Conversion" in step_names

    @patch(f"{STRUCTURAL}._run_subject_pipeline")
    @patch(f"{STRUCTURAL}.ensure_dataset_descriptions")
    @patch(f"{STRUCTURAL}.ensure_subject_dirs")
    @patch(f"{STRUCTURAL}.get_path_manager")
    def test_report_includes_charm_steps(
        self, mock_pm, mock_dirs, mock_datasets, mock_run_sub, dummy_report
    ):
        with patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report):
            run_pipeline(["001"], create_m2m=True, runner=_make_runner())
        step_names = [s["step_name"] for s in dummy_report.instances[0].steps]
        assert "SimNIBS charm" in step_names
        assert "Subject Atlas Segmentation" in step_names

    @patch(f"{STRUCTURAL}._run_subject_pipeline")
    @patch(f"{STRUCTURAL}.ensure_dataset_descriptions")
    @patch(f"{STRUCTURAL}.ensure_subject_dirs")
    @patch(f"{STRUCTURAL}.get_path_manager")
    def test_report_includes_all_steps(
        self, mock_pm, mock_dirs, mock_datasets, mock_run_sub, dummy_report
    ):
        with patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report):
            run_pipeline(
                ["001"],
                convert_dicom=True,
                create_m2m=True,
                run_recon=True,
                run_tissue_analysis=True,
                run_qsiprep=True,
                run_qsirecon=True,
                extract_dti=True,
                run_subcortical_segmentations=True,
                runner=_make_runner(),
            )
        step_names = [s["step_name"] for s in dummy_report.instances[0].steps]
        assert "DICOM Conversion" in step_names
        assert "SimNIBS charm" in step_names
        assert "Subject Atlas Segmentation" in step_names
        assert "FreeSurfer recon-all" in step_names
        assert "Tissue Analysis" in step_names
        assert "QSIPrep" in step_names
        assert "QSIRecon" in step_names
        assert "DTI Tensor Extraction" in step_names
        assert "Subcortical Segmentations" in step_names

    @patch(f"{STRUCTURAL}._run_subject_pipeline")
    @patch(f"{STRUCTURAL}.ensure_dataset_descriptions")
    @patch(f"{STRUCTURAL}.ensure_subject_dirs")
    @patch(f"{STRUCTURAL}.get_path_manager")
    def test_report_logger_callback_called(
        self, mock_pm, mock_dirs, mock_datasets, mock_run_sub, dummy_report
    ):
        callback = MagicMock()
        with patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report):
            run_pipeline(
                ["001"],
                convert_dicom=True,
                runner=_make_runner(),
                logger_callback=callback,
            )
        callback.assert_called_once()
        assert "Report generated" in callback.call_args[0][0]


# ---------------------------------------------------------------------------
# run_pipeline — runner stop_event reassignment (line 295-296)
# ---------------------------------------------------------------------------


class TestRunPipelineRunnerStopEvent:
    """Test runner stop_event handling."""

    @patch(f"{STRUCTURAL}._run_subject_pipeline")
    @patch(f"{STRUCTURAL}.ensure_dataset_descriptions")
    @patch(f"{STRUCTURAL}.ensure_subject_dirs")
    @patch(f"{STRUCTURAL}.get_path_manager")
    def test_stop_event_reassigned_to_runner(
        self, mock_pm, mock_dirs, mock_datasets, mock_run_sub, dummy_report
    ):
        runner = MagicMock(spec=CommandRunner)
        runner.stop_event = MagicMock()
        new_stop = MagicMock()

        with patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report):
            run_pipeline(
                ["001"],
                convert_dicom=True,
                runner=runner,
                stop_event=new_stop,
            )
        assert runner.stop_event is new_stop


# ---------------------------------------------------------------------------
# run_pipeline — no subjects
# ---------------------------------------------------------------------------


class TestRunPipelineValidation:
    """Validation edge cases."""

    def test_empty_subject_list_raises(self):
        with pytest.raises(PreprocessError, match="No subjects"):
            run_pipeline([])

    def test_whitespace_only_subjects_raises(self):
        with pytest.raises(PreprocessError, match="No subjects"):
            run_pipeline(["", "  ", "\t"])
