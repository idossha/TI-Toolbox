#!/usr/bin/env python3
"""
Tests for tit/pre/structural.py — run_pipeline coverage.

Covers:
- report generation
- Report generation loop (lines 432-505)
- Individual step flags: run_fastsurfer, run_qsiprep, run_qsirecon, extract_dti
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
from tit.pre.preflight import PreprocessingOutput
from tit.pre.utils import PreprocessError, CommandRunner

STRUCTURAL = "tit.pre.structural"
REPORTING = "tit.reporting"


@pytest.fixture(autouse=True)
def _stub_bidsignore():
    """These tests mock the path manager, so the project root is not a real path.

    ensure_bidsignore writes there for real; its own behaviour is covered by
    TestEnsureBidsignore in test_pre_utils_full.py.
    """
    with patch(f"{STRUCTURAL}.ensure_bidsignore"):
        yield


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
        patch(f"{STRUCTURAL}.run_fastsurfer") as mock_fastsurfer,
        patch(f"{STRUCTURAL}.run_tissue_analysis") as mock_tissue,
        patch(f"{STRUCTURAL}.run_qsiprep") as mock_qsiprep,
        patch(f"{STRUCTURAL}.run_qsirecon") as mock_qsirecon,
        patch(f"{STRUCTURAL}.extract_dti_tensor") as mock_dti,
        patch(
            f"{STRUCTURAL}.existing_outputs_for_step", return_value=[]
        ) as mock_existing,
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
            "fastsurfer": mock_fastsurfer,
            "tissue": mock_tissue,
            "qsiprep": mock_qsiprep,
            "qsirecon": mock_qsirecon,
            "dti": mock_dti,
            "existing": mock_existing,
        }


@pytest.fixture(autouse=True)
def no_missing_preprocessing_inputs():
    """Most pipeline tests focus on orchestration, not input preflight."""
    with patch(f"{STRUCTURAL}.find_missing_preprocessing_inputs", return_value=[]):
        yield


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

    def test_emits_a_stage_event_per_step(self, tmp_path, monkeypatch):
        """Orchestration-only finer progress: each named step reports its own
        `stage` event (a no-op unless $TIT_EVENTS_FILE is set) -- see
        tit.jobs.events."""
        import json

        import tit.logger as logger_mod
        from tit.jobs import events as events_mod

        events_path = tmp_path / "events.jsonl"
        monkeypatch.setenv("TIT_EVENTS_FILE", str(events_path))
        logger_mod._event_sinks.clear()
        events_mod._reset_state()
        try:
            _run_step("SimNIBS charm", MagicMock(), MagicMock())
            lines = [
                json.loads(line)
                for line in events_path.read_text().splitlines()
                if line.strip()
            ]
            assert any(
                e["type"] == "stage" and e["stage"] == "SimNIBS charm" for e in lines
            )
        finally:
            logger_mod._event_sinks.clear()
            events_mod._reset_state()


# ---------------------------------------------------------------------------
# _run_subject_pipeline — individual step flags
# ---------------------------------------------------------------------------


class TestRunSubjectPipeline:
    """Tests for _run_subject_pipeline step dispatch."""

    def _call(self, mocks, **overrides):
        defaults = dict(
            convert_dicom=False,
            run_fastsurfer_step=False,
            create_m2m=False,
            run_tissue=False,
            run_qsiprep_step=False,
            run_qsirecon_step=False,
            qsiprep_config=None,
            qsi_recon_config=None,
            extract_dti_step=False,
            runner=MagicMock(),
            callback=None,
            skip_existing_outputs=False,
            replace_existing_outputs=False,
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

    def test_fastsurfer_only_path(self, pipeline_mocks):
        """FastSurfer alone runs neither conversion nor charm."""
        self._call(pipeline_mocks, run_fastsurfer_step=True)
        pipeline_mocks["fastsurfer"].assert_called_once()
        pipeline_mocks["dicom"].assert_not_called()
        pipeline_mocks["charm"].assert_not_called()

    def test_dicom_and_fastsurfer(self, pipeline_mocks):
        """Conversion and FastSurfer both run, conversion first."""
        self._call(pipeline_mocks, convert_dicom=True, run_fastsurfer_step=True)
        pipeline_mocks["dicom"].assert_called_once()
        pipeline_mocks["fastsurfer"].assert_called_once()

    def test_fastsurfer_threads_forwarded(self, pipeline_mocks):
        """fastsurfer_threads reaches run_fastsurfer as a keyword."""
        self._call(pipeline_mocks, run_fastsurfer_step=True, fastsurfer_threads=6)
        assert pipeline_mocks["fastsurfer"].call_args.kwargs["threads"] == 6

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

    def test_existing_output_blocks_by_default(self, pipeline_mocks, tmp_path):
        """Existing selected outputs fail unless skip or replace is selected."""
        output = PreprocessingOutput(
            subject_id="001",
            step="charm",
            label="SimNIBS charm",
            path=tmp_path / "m2m_001",
        )
        pipeline_mocks["existing"].return_value = [output]

        with pytest.raises(PreprocessError, match="already exists"):
            self._call(pipeline_mocks, create_m2m=True)

        pipeline_mocks["charm"].assert_not_called()

    def test_skip_existing_output_skips_step(self, pipeline_mocks, tmp_path):
        """skip_existing_outputs leaves existing outputs in place and skips the step."""
        output = PreprocessingOutput(
            subject_id="001",
            step="charm",
            label="SimNIBS charm",
            path=tmp_path / "m2m_001",
        )
        pipeline_mocks["existing"].return_value = [output]

        self._call(
            pipeline_mocks,
            create_m2m=True,
            skip_existing_outputs=True,
        )

        pipeline_mocks["charm"].assert_not_called()
        pipeline_mocks["atlas"].assert_not_called()

    def test_replace_existing_output_removes_and_runs(self, pipeline_mocks, tmp_path):
        """replace_existing_outputs removes the existing output and runs the step."""
        output_dir = tmp_path / "m2m_001"
        output_dir.mkdir()
        (output_dir / "old.txt").write_text("old")
        output = PreprocessingOutput(
            subject_id="001",
            step="charm",
            label="SimNIBS charm",
            path=output_dir,
        )
        pipeline_mocks["existing"].return_value = [output]

        self._call(
            pipeline_mocks,
            create_m2m=True,
            replace_existing_outputs=True,
        )

        assert not output_dir.exists()
        pipeline_mocks["charm"].assert_called_once()
        pipeline_mocks["atlas"].assert_called_once()


# ---------------------------------------------------------------------------
# run_pipeline — report generation (lines 432-505)
# ---------------------------------------------------------------------------


class TestRunPipelineReports:
    """Tests for report generation at the end of run_pipeline."""

    @patch(f"{STRUCTURAL}._run_subject_pipeline")
    @patch(f"{STRUCTURAL}.ensure_dataset_descriptions")
    @patch(f"{STRUCTURAL}.ensure_subject_dirs")
    @patch(f"{STRUCTURAL}.get_path_manager")
    def test_scaffolds_bidsignore_once_per_run(
        self, mock_pm, mock_dirs, mock_datasets, mock_run_sub, dummy_report
    ):
        """CT output needs .bidsignore, so the pipeline must write it."""
        from tit.pre import structural

        # Stub the report generator like the tests below: the mocked path
        # manager makes the project root a MagicMock, and the real generator
        # would write its HTML into a literal MagicMock/ tree in the repo.
        with patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report):
            run_pipeline(["001", "002"], convert_dicom=True, runner=_make_runner())

        structural.ensure_bidsignore.assert_called_once()

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
    def test_report_marks_skipped_step(
        self, mock_pm, mock_dirs, mock_datasets, mock_run_sub, dummy_report
    ):
        mock_run_sub.return_value = {"DICOM Conversion": None}
        with patch(f"{REPORTING}.PreprocessingReportGenerator", dummy_report):
            run_pipeline(["001"], convert_dicom=True, runner=_make_runner())

        step = dummy_report.instances[0].steps[0]
        assert step["step_name"] == "DICOM Conversion"
        assert step["status"] == "skipped"

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
                run_fastsurfer=True,
                run_tissue_analysis=True,
                run_qsiprep=True,
                run_qsirecon=True,
                extract_dti=True,
                runner=_make_runner(),
            )
        step_names = [s["step_name"] for s in dummy_report.instances[0].steps]
        assert "DICOM Conversion" in step_names
        assert "SimNIBS charm" in step_names
        assert "Subject Atlas Segmentation" in step_names
        assert "FastSurfer segmentation" in step_names
        assert "Tissue Analysis" in step_names
        assert "QSIPrep" in step_names
        assert "QSIRecon" in step_names
        assert "DTI Tensor Extraction" in step_names

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
        with patch("tit.telemetry.track_event") as mock_track_event:
            with pytest.raises(PreprocessError, match="No subjects"):
                run_pipeline([])
        mock_track_event.assert_not_called()

    def test_whitespace_only_subjects_raises(self):
        with patch("tit.telemetry.track_event") as mock_track_event:
            with pytest.raises(PreprocessError, match="No subjects"):
                run_pipeline(["", "  ", "\t"])
        mock_track_event.assert_not_called()

    def test_skip_and_replace_are_mutually_exclusive(self):
        with pytest.raises(PreprocessError, match="cannot both be true"):
            run_pipeline(
                ["001"],
                skip_existing_outputs=True,
                replace_existing_outputs=True,
            )

    def test_missing_inputs_raise_before_telemetry(self):
        problem = MagicMock()
        problem.subject_id = "001"
        problem.label = "SimNIBS charm"
        problem.message = "SimNIBS charm requires a BIDS T1w image"
        problem.path = "/proj/sub-001/anat"

        with (
            patch(f"{STRUCTURAL}.get_path_manager") as mock_pm,
            patch(
                f"{STRUCTURAL}.find_missing_preprocessing_inputs",
                return_value=[problem],
            ),
            patch("tit.telemetry.track_event") as mock_track_event,
        ):
            mock_pm.return_value._root.return_value = "/proj"
            with pytest.raises(
                PreprocessError, match="Missing required preprocessing inputs"
            ):
                run_pipeline(["001"], create_m2m=True)

        mock_track_event.assert_not_called()
