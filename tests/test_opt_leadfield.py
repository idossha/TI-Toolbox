"""Tests for tit/opt/leadfield.py -- LeadfieldGenerator."""

import csv
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure simnibs.utils.csv_reader and simnibs.utils.TI_utils are mocked
for mod_name in ("simnibs.utils.csv_reader", "simnibs.utils.TI_utils"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pm_mock(tmp_path, subject_id="001"):
    """Create a PathManager mock with real directory structure."""
    pm = MagicMock()
    m2m_dir = tmp_path / "m2m_001"
    m2m_dir.mkdir(parents=True, exist_ok=True)

    lf_dir = tmp_path / "leadfields"
    lf_dir.mkdir(parents=True, exist_ok=True)

    eeg_dir = tmp_path / "eeg_positions"
    eeg_dir.mkdir(parents=True, exist_ok=True)

    rois_dir = tmp_path / "rois"
    rois_dir.mkdir(parents=True, exist_ok=True)

    pm.m2m.return_value = str(m2m_dir)
    pm.leadfields.return_value = str(lf_dir)
    pm.eeg_positions.return_value = str(eeg_dir)
    pm.ensure.return_value = str(lf_dir)
    pm.rois.return_value = str(rois_dir)

    return pm


# ---------------------------------------------------------------------------
# LeadfieldGenerator.__init__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLeadfieldGeneratorInit:
    @patch("tit.opt.leadfield.get_path_manager")
    def test_init_stores_attributes(self, mock_gpm):
        mock_gpm.return_value = MagicMock()
        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(
            subject_id="001",
            electrode_cap="GSN-HydroCel-185",
            progress_callback=None,
            termination_flag=None,
        )
        assert gen.subject_id == "001"
        assert gen.electrode_cap == "GSN-HydroCel-185"
        assert gen._progress_callback is None
        assert gen._termination_flag is None

    @patch("tit.opt.leadfield.get_path_manager")
    def test_init_with_callbacks(self, mock_gpm):
        mock_gpm.return_value = MagicMock()
        from tit.opt.leadfield import LeadfieldGenerator

        cb = MagicMock()
        tf = MagicMock(return_value=False)
        gen = LeadfieldGenerator(
            subject_id="001",
            progress_callback=cb,
            termination_flag=tf,
        )
        assert gen._progress_callback is cb
        assert gen._termination_flag is tf


# ---------------------------------------------------------------------------
# LeadfieldGenerator._log
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLeadfieldGeneratorLog:
    @patch("tit.opt.leadfield.get_path_manager")
    def test_log_calls_callback(self, mock_gpm):
        mock_gpm.return_value = MagicMock()
        from tit.opt.leadfield import LeadfieldGenerator

        cb = MagicMock()
        gen = LeadfieldGenerator(subject_id="001", progress_callback=cb)
        gen._log("test message", "info")
        cb.assert_called_once_with("test message", "info")

    @patch("tit.opt.leadfield.get_path_manager")
    def test_log_without_callback(self, mock_gpm):
        mock_gpm.return_value = MagicMock()
        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(subject_id="001")
        gen._log("test message")  # should not raise


# ---------------------------------------------------------------------------
# LeadfieldGenerator._cleanup
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLeadfieldGeneratorCleanup:
    @patch("tit.opt.leadfield.get_path_manager")
    def test_cleanup_removes_stale_files(self, mock_gpm, tmp_path):
        m2m_dir = tmp_path / "m2m_001"
        m2m_dir.mkdir()
        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.m2m.return_value = str(m2m_dir)

        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(subject_id="001")

        # Create stale files
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "simnibs_simulation_test.mat").write_text("stale")
        (output_dir / "test_electrodes_123.msh").write_text("stale")

        # Create leadfield dir to be removed
        lf_dir = m2m_dir / "leadfield"
        lf_dir.mkdir()
        (lf_dir / "temp.txt").write_text("temp")

        # Create ROI file to be removed
        roi_file = m2m_dir / "001_ROI.msh"
        roi_file.write_text("roi")

        gen._cleanup(output_dir)

        assert not (output_dir / "simnibs_simulation_test.mat").exists()
        assert not (output_dir / "test_electrodes_123.msh").exists()
        assert not lf_dir.exists()
        assert not roi_file.exists()


# ---------------------------------------------------------------------------
# LeadfieldGenerator.generate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLeadfieldGeneratorGenerate:
    @patch("tit.opt.leadfield.get_path_manager")
    def test_generate_runs_simnibs(self, mock_gpm, tmp_path):
        pm = _make_pm_mock(tmp_path)
        mock_gpm.return_value = pm

        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(subject_id="001")

        output_dir = tmp_path / "leadfields"
        # Create a fake HDF5 file to be found
        (output_dir / "leadfield.hdf5").write_text("fake")

        import simnibs

        simnibs.run_simnibs = MagicMock()
        simnibs.sim_struct.TDCSLEADFIELD.return_value = MagicMock()

        result = gen.generate(output_dir=str(output_dir))
        assert str(result).endswith(".hdf5")
        simnibs.run_simnibs.assert_called_once()

    @patch("tit.opt.leadfield.get_path_manager")
    def test_generate_cancelled_before_start(self, mock_gpm, tmp_path):
        pm = _make_pm_mock(tmp_path)
        mock_gpm.return_value = pm

        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(
            subject_id="001",
            termination_flag=lambda: True,
        )

        import simnibs

        simnibs.sim_struct.TDCSLEADFIELD.return_value = MagicMock()

        with pytest.raises(InterruptedError, match="cancelled before starting"):
            gen.generate(output_dir=str(tmp_path / "out"))

    @patch("tit.opt.leadfield.get_path_manager")
    def test_generate_cancelled_after_simnibs(self, mock_gpm, tmp_path):
        pm = _make_pm_mock(tmp_path)
        mock_gpm.return_value = pm

        from tit.opt.leadfield import LeadfieldGenerator

        call_count = [0]

        def term_flag():
            call_count[0] += 1
            return call_count[0] > 1  # False first, True second

        gen = LeadfieldGenerator(
            subject_id="001",
            termination_flag=term_flag,
        )

        import simnibs

        simnibs.run_simnibs = MagicMock()
        simnibs.sim_struct.TDCSLEADFIELD.return_value = MagicMock()

        with pytest.raises(InterruptedError, match="cancelled after SimNIBS"):
            gen.generate(output_dir=str(tmp_path / "out"))


# ---------------------------------------------------------------------------
# LeadfieldGenerator.list_leadfields
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLeadfieldGeneratorListLeadfields:
    @patch("tit.opt.leadfield.get_path_manager")
    def test_list_leadfields_parses_names(self, mock_gpm, tmp_path):
        lf_dir = tmp_path / "leadfields"
        lf_dir.mkdir()

        # Create mock leadfield files
        (lf_dir / "001_leadfield_EEG10-10.hdf5").write_bytes(b"x" * 1024)
        (lf_dir / "sub_leadfield_GSN-HydroCel-185.hdf5").write_bytes(b"y" * 2048)

        pm = MagicMock()
        pm.leadfields.return_value = str(lf_dir)
        mock_gpm.return_value = pm

        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(subject_id="001")
        results = gen.list_leadfields()
        assert len(results) == 2
        # Each result is (net_name, path, size_gb)
        for name, path, size in results:
            assert isinstance(name, str)
            assert isinstance(size, float)

    @patch("tit.opt.leadfield.get_path_manager")
    def test_list_leadfields_with_subject_id_prefix(self, mock_gpm, tmp_path):
        lf_dir = tmp_path / "leadfields"
        lf_dir.mkdir()

        (lf_dir / "001_leadfield_EEG10-10.hdf5").write_bytes(b"x" * 1024)

        pm = MagicMock()
        pm.leadfields.return_value = str(lf_dir)
        mock_gpm.return_value = pm

        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(subject_id="001")
        results = gen.list_leadfields()
        # The "001_" prefix should be stripped from net_name
        assert len(results) == 1
        name = results[0][0]
        assert "001" not in name or name == "001"  # prefix stripped

    @patch("tit.opt.leadfield.get_path_manager")
    def test_list_leadfields_custom_subject(self, mock_gpm, tmp_path):
        lf_dir = tmp_path / "leadfields"
        lf_dir.mkdir()
        (lf_dir / "test_leadfield.hdf5").write_bytes(b"x" * 512)

        pm = MagicMock()
        pm.leadfields.return_value = str(lf_dir)
        mock_gpm.return_value = pm

        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(subject_id="001")
        results = gen.list_leadfields(subject_id="002")
        pm.leadfields.assert_called_with("002")


# ---------------------------------------------------------------------------
# LeadfieldGenerator.get_electrode_names
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLeadfieldGeneratorGetElectrodeNames:
    @patch("tit.opt.leadfield.get_path_manager")
    def test_get_electrode_names(self, mock_gpm, tmp_path):
        pm = _make_pm_mock(tmp_path)
        mock_gpm.return_value = pm

        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(subject_id="001")

        mock_eeg_pos = MagicMock(
            return_value={"E1": [0, 0, 0], "E2": [1, 1, 1], "Cz": [0, 0, 1]}
        )
        with patch.dict(
            sys.modules,
            {"simnibs.utils.csv_reader": MagicMock(eeg_positions=mock_eeg_pos)},
        ):
            names = gen.get_electrode_names()
        assert names == ["Cz", "E1", "E2"]

    @patch("tit.opt.leadfield.get_path_manager")
    def test_get_electrode_names_custom_cap(self, mock_gpm, tmp_path):
        pm = _make_pm_mock(tmp_path)
        mock_gpm.return_value = pm

        from tit.opt.leadfield import LeadfieldGenerator

        gen = LeadfieldGenerator(subject_id="001")

        mock_eeg_pos = MagicMock(return_value={"A": [0, 0, 0]})
        with patch.dict(
            sys.modules,
            {"simnibs.utils.csv_reader": MagicMock(eeg_positions=mock_eeg_pos)},
        ):
            names = gen.get_electrode_names(cap_name="CustomCap")
        mock_eeg_pos.assert_called_once()
        call_args = mock_eeg_pos.call_args
        assert call_args[1].get("cap_name") == "CustomCap" or "CustomCap" in str(
            call_args
        )
