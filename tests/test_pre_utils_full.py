"""Extended tests for tit.pre.utils — full coverage."""

import json
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from tit.pre.utils import (
    CommandRunner,
    PreprocessCancelled,
    PreprocessError,
    _dataset_description_target,
    _find_anat_files,
    _terminate_process,
    build_logger,
    discover_subjects,
    ensure_dataset_descriptions,
    ensure_subject_dirs,
)


MODULE = "tit.pre.utils"


class TestPreprocessErrors:
    """Tests for custom exception classes."""

    def test_preprocess_error(self):
        with pytest.raises(PreprocessError):
            raise PreprocessError("failed")

    def test_preprocess_cancelled(self):
        with pytest.raises(PreprocessCancelled):
            raise PreprocessCancelled("cancelled")


class TestFindAnatFiles:
    """Tests for _find_anat_files."""

    @patch(f"{MODULE}.get_path_manager")
    def test_both_files_exist(self, mock_gpm, tmp_path):
        pm = MagicMock()
        anat_dir = tmp_path / "sub-001" / "anat"
        anat_dir.mkdir(parents=True)
        pm.bids_anat.return_value = str(anat_dir)
        mock_gpm.return_value = pm

        t1 = anat_dir / "sub-001_T1w.nii.gz"
        t2 = anat_dir / "sub-001_T2w.nii.gz"
        t1.touch()
        t2.touch()

        result_t1, result_t2 = _find_anat_files("001")
        assert result_t1 == t1
        assert result_t2 == t2

    @patch(f"{MODULE}.get_path_manager")
    def test_no_files(self, mock_gpm, tmp_path):
        pm = MagicMock()
        anat_dir = tmp_path / "sub-001" / "anat"
        anat_dir.mkdir(parents=True)
        pm.bids_anat.return_value = str(anat_dir)
        mock_gpm.return_value = pm

        t1, t2 = _find_anat_files("001")
        assert t1 is None
        assert t2 is None

    @patch(f"{MODULE}.get_path_manager")
    def test_t1_only(self, mock_gpm, tmp_path):
        pm = MagicMock()
        anat_dir = tmp_path / "sub-001" / "anat"
        anat_dir.mkdir(parents=True)
        pm.bids_anat.return_value = str(anat_dir)
        mock_gpm.return_value = pm

        t1 = anat_dir / "sub-001_T1w.nii.gz"
        t1.touch()

        result_t1, result_t2 = _find_anat_files("001")
        assert result_t1 == t1
        assert result_t2 is None


class TestEnsureSubjectDirs:
    """Tests for ensure_subject_dirs."""

    @patch(f"{MODULE}.get_path_manager")
    def test_creates_all_dirs(self, mock_gpm):
        pm = MagicMock()
        pm.sourcedata_dicom.return_value = "/proj/sourcedata/sub-001/T1w/dicom"
        pm.bids_anat.return_value = "/proj/sub-001/anat"
        pm.freesurfer_subject.return_value = "/proj/derivatives/freesurfer/sub-001"
        pm.sub.return_value = "/proj/derivatives/SimNIBS/sub-001"
        pm.ti_toolbox.return_value = "/proj/derivatives/ti-toolbox"
        mock_gpm.return_value = pm

        ensure_subject_dirs("/proj", "001")

        assert pm.ensure.call_count == 6  # T1w dicom, T2w dicom, bids_anat, freesurfer, sub, ti-toolbox


class TestDatasetDescriptionTarget:
    """Tests for _dataset_description_target."""

    def test_freesurfer(self):
        path = _dataset_description_target("/proj", "freesurfer")
        assert "freesurfer" in str(path)
        assert path.name == "dataset_description.json"

    def test_simnibs(self):
        path = _dataset_description_target("/proj", "simnibs")
        assert "SimNIBS" in str(path)

    def test_ti_toolbox(self):
        path = _dataset_description_target("/proj", "ti-toolbox")
        assert "ti-toolbox" in str(path)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown dataset"):
            _dataset_description_target("/proj", "unknown")


class TestEnsureDatasetDescriptions:
    """Tests for ensure_dataset_descriptions."""

    def test_creates_from_template(self, tmp_path):
        """Creates dataset_description.json from template when available."""
        # Create the template
        repo_root = Path(__file__).resolve().parents[1]
        assets = repo_root / "resources" / "dataset_descriptions"
        assets.mkdir(parents=True, exist_ok=True)

        template = assets / "freesurfer.dataset_description.json"
        template_content = json.dumps({
            "Name": "FreeSurfer",
            "BIDSVersion": "1.10.0",
            "DatasetType": "derivative",
            "SourceDatasets": [{"URI": ""}],
            "DatasetLinks": {},
        })
        template.write_text(template_content, encoding="utf-8")

        try:
            ensure_dataset_descriptions(str(tmp_path), ["freesurfer"])

            target = tmp_path / "derivatives" / "freesurfer" / "dataset_description.json"
            assert target.exists()
            data = json.loads(target.read_text(encoding="utf-8"))
            assert data["Name"] == "FreeSurfer"
            # URI should be filled in
            assert data["SourceDatasets"][0]["URI"] != ""
        finally:
            template.unlink(missing_ok=True)

    def test_creates_fallback_when_no_template(self, tmp_path):
        """Creates fallback JSON when no template exists."""
        ensure_dataset_descriptions(str(tmp_path), ["ti-toolbox"])

        target = tmp_path / "derivatives" / "ti-toolbox" / "dataset_description.json"
        assert target.exists()

    def test_skips_unknown_dataset(self, tmp_path):
        """Skips unknown dataset names gracefully."""
        ensure_dataset_descriptions(str(tmp_path), ["nonexistent"])
        # Should not raise

    def test_does_not_overwrite_existing(self, tmp_path):
        """Does not overwrite existing description file."""
        target = tmp_path / "derivatives" / "SimNIBS" / "dataset_description.json"
        target.parent.mkdir(parents=True)
        original = json.dumps({
            "Name": "Existing",
            "BIDSVersion": "1.10.0",
            "SourceDatasets": [{"URI": "existing"}],
            "DatasetLinks": {"proj": "../../"},
        })
        target.write_text(original, encoding="utf-8")

        ensure_dataset_descriptions(str(tmp_path), ["simnibs"])

        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["Name"] == "Existing"
        # URI should not be changed since it's already set
        assert data["SourceDatasets"][0]["URI"] == "existing"


class TestBuildLogger:
    """Tests for build_logger."""

    @patch(f"{MODULE}.get_path_manager")
    @patch("tit.logger.add_file_handler")
    def test_creates_logger(self, mock_handler, mock_gpm, tmp_path):
        pm = MagicMock()
        log_dir = tmp_path / "logs"
        pm.logs.return_value = str(log_dir)
        mock_gpm.return_value = pm

        logger = build_logger("charm", "001", str(tmp_path))

        mock_handler.assert_called_once()
        assert logger is not None

    @patch(f"{MODULE}.get_path_manager")
    @patch("tit.logger.add_file_handler")
    def test_custom_log_file(self, mock_handler, mock_gpm, tmp_path):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        mock_gpm.return_value = pm

        custom = str(tmp_path / "custom.log")
        build_logger("charm", "001", str(tmp_path), log_file=custom)

        mock_handler.assert_called_once_with(custom, logger_name="tit.pre.charm.001")


class TestTerminateProcess:
    """Tests for _terminate_process."""

    @patch(f"{MODULE}.os.name", "posix")
    @patch(f"{MODULE}.os.killpg")
    def test_posix_kills_process_group(self, mock_killpg):
        proc = MagicMock()
        proc.pid = 12345

        _terminate_process(proc)

        mock_killpg.assert_called_once()

    @patch(f"{MODULE}.os.name", "nt")
    def test_windows_terminates(self):
        proc = MagicMock()

        _terminate_process(proc)

        proc.terminate.assert_called_once()

    @patch(f"{MODULE}.os.name", "posix")
    @patch(f"{MODULE}.os.killpg", side_effect=ProcessLookupError)
    def test_fallback_to_terminate(self, mock_killpg):
        proc = MagicMock()
        proc.pid = 12345

        _terminate_process(proc)

        proc.terminate.assert_called_once()

    @patch(f"{MODULE}.os.name", "posix")
    @patch(f"{MODULE}.os.killpg", side_effect=ProcessLookupError)
    def test_double_failure_suppressed(self, mock_killpg):
        proc = MagicMock()
        proc.pid = 12345
        proc.terminate.side_effect = ProcessLookupError

        # Should not raise
        _terminate_process(proc)


class TestCommandRunner:
    """Tests for the CommandRunner class."""

    def test_init_default_stop_event(self):
        runner = CommandRunner()
        assert isinstance(runner.stop_event, threading.Event)
        assert not runner.stop_event.is_set()

    def test_init_custom_stop_event(self):
        event = threading.Event()
        runner = CommandRunner(stop_event=event)
        assert runner.stop_event is event

    def test_request_stop_sets_event(self):
        runner = CommandRunner()
        runner.request_stop()
        assert runner.stop_event.is_set()

    def test_run_cancelled_before_start(self):
        runner = CommandRunner()
        runner.stop_event.set()

        with pytest.raises(PreprocessCancelled, match="cancelled"):
            runner.run(["echo", "test"], logger=MagicMock())

    def test_run_empty_command_raises(self):
        runner = CommandRunner()

        with pytest.raises(ValueError, match="empty"):
            runner.run([], logger=MagicMock())

    @patch(f"{MODULE}.subprocess.Popen")
    def test_run_success(self, mock_popen):
        proc = MagicMock()
        proc.stdout.readline = MagicMock(side_effect=["line1\n", "line2\n", ""])
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        runner = CommandRunner()
        logger = MagicMock()
        result = runner.run(["echo", "test"], logger=logger)

        assert result == 0

    @patch(f"{MODULE}.subprocess.Popen")
    def test_run_failure(self, mock_popen):
        proc = MagicMock()
        proc.stdout.readline = MagicMock(side_effect=[""])
        proc.wait.return_value = 1
        mock_popen.return_value = proc

        runner = CommandRunner()
        result = runner.run(["false"], logger=MagicMock())

        assert result == 1

    def test_terminate_all(self):
        runner = CommandRunner()
        proc1 = MagicMock()
        proc1.pid = 1
        proc2 = MagicMock()
        proc2.pid = 2
        runner._processes = {proc1, proc2}

        with patch(f"{MODULE}._terminate_process") as mock_term:
            runner.terminate_all()
            assert mock_term.call_count == 2


class TestDiscoverSubjectsAdditional:
    """Additional discover_subjects tests."""

    def test_tgz_in_subject_root(self, tmp_path):
        """Discovers subject with .tgz at top level."""
        sd = tmp_path / "sourcedata" / "sub-003"
        sd.mkdir(parents=True)
        (sd / "data.tgz").touch()

        result = discover_subjects(str(tmp_path))
        assert "003" in result

    def test_bids_root_subjects(self, tmp_path):
        """Discovers subjects at project root with anat NIfTI."""
        anat = tmp_path / "sub-004" / "anat"
        anat.mkdir(parents=True)
        (anat / "sub-004_T1w.nii.gz").touch()

        result = discover_subjects(str(tmp_path))
        assert "004" in result

    def test_t2w_sourcedata(self, tmp_path):
        """Discovers subjects with T2w data."""
        sd = tmp_path / "sourcedata" / "sub-005" / "T2w"
        sd.mkdir(parents=True)
        (sd / "scan.nii.gz").touch()

        result = discover_subjects(str(tmp_path))
        assert "005" in result

    def test_deduplication(self, tmp_path):
        """Subjects found in both sourcedata and bids root are not duplicated."""
        # Sourcedata
        sd = tmp_path / "sourcedata" / "sub-006" / "T1w"
        sd.mkdir(parents=True)
        (sd / "scan.nii").touch()

        # BIDS root
        anat = tmp_path / "sub-006" / "anat"
        anat.mkdir(parents=True)
        (anat / "sub-006_T1w.nii.gz").touch()

        result = discover_subjects(str(tmp_path))
        assert result.count("006") == 1

    def test_no_sourcedata_dir(self, tmp_path):
        """Works when sourcedata directory doesn't exist."""
        result = discover_subjects(str(tmp_path))
        assert result == []
