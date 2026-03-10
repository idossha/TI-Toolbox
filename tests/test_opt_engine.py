"""Tests for tit/opt/ex/engine.py -- ExSearchEngine."""

import csv
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure simnibs.utils.TI_utils is mocked
for mod_name in ("simnibs.utils.TI_utils",):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(logger=None):
    """Create an ExSearchEngine with mocked dependencies."""
    if logger is None:
        logger = MagicMock()
    from tit.opt.ex.engine import ExSearchEngine

    return ExSearchEngine(
        leadfield_hdf="/fake/leadfield.hdf5",
        roi_file="/fake/roi.csv",
        roi_name="TestROI",
        logger=logger,
    )


def _setup_engine_fields(engine):
    """Setup engine with mock leadfield/mesh data for compute_ti_field."""
    engine.leadfield = MagicMock()
    engine.idx_lf = MagicMock()
    engine.mesh = MagicMock()
    engine.roi_indices = np.array([0, 1, 2])
    engine.roi_volumes = np.array([1.0, 1.0, 1.0])
    engine.gm_indices = np.array([0, 1, 2, 3, 4])
    engine.gm_volumes = np.array([1.0, 1.0, 1.0, 1.0, 1.0])


# ---------------------------------------------------------------------------
# ExSearchEngine.__init__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExSearchEngineInit:
    def test_stores_attributes(self):
        engine = _make_engine()
        assert engine.leadfield_hdf == "/fake/leadfield.hdf5"
        assert engine.roi_file == "/fake/roi.csv"
        assert engine.roi_name == "TestROI"
        assert engine.leadfield is None
        assert engine.mesh is None

    def test_initial_state(self):
        engine = _make_engine()
        assert engine.idx_lf is None
        assert engine.roi_coords is None
        assert engine.roi_indices is None
        assert engine.roi_volumes is None
        assert engine.gm_indices is None
        assert engine.gm_volumes is None


# ---------------------------------------------------------------------------
# ExSearchEngine._load_leadfield
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadLeadfield:
    def test_loads_via_simnibs(self):
        from simnibs.utils import TI_utils as TI

        TI.load_leadfield = MagicMock(return_value=("lf", "mesh", "idx"))

        engine = _make_engine()
        engine._load_leadfield()

        assert engine.leadfield == "lf"
        assert engine.mesh == "mesh"
        assert engine.idx_lf == "idx"
        TI.load_leadfield.assert_called_once_with("/fake/leadfield.hdf5")


# ---------------------------------------------------------------------------
# ExSearchEngine._load_roi_coordinates
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadRoiCoordinates:
    def test_reads_csv(self, tmp_path):
        roi_file = tmp_path / "roi.csv"
        with open(roi_file, "w", newline="") as f:
            csv.writer(f).writerow([10.5, -20.3, 55.0])

        engine = _make_engine()
        engine.roi_file = str(roi_file)
        engine._load_roi_coordinates()

        assert engine.roi_coords == [10.5, -20.3, 55.0]

    def test_skips_empty_rows(self, tmp_path):
        roi_file = tmp_path / "roi.csv"
        with open(roi_file, "w") as f:
            f.write("\n\n10.5, -20.3, 55.0\n")

        engine = _make_engine()
        engine.roi_file = str(roi_file)
        engine._load_roi_coordinates()

        assert engine.roi_coords == [10.5, -20.3, 55.0]

    def test_raises_on_invalid(self, tmp_path):
        roi_file = tmp_path / "roi.csv"
        roi_file.write_text("")

        engine = _make_engine()
        engine.roi_file = str(roi_file)

        with pytest.raises(ValueError, match="No valid coordinates"):
            engine._load_roi_coordinates()

    def test_handles_extra_columns(self, tmp_path):
        roi_file = tmp_path / "roi.csv"
        with open(roi_file, "w", newline="") as f:
            csv.writer(f).writerow([10.5, -20.3, 55.0, 99.0, 88.0])

        engine = _make_engine()
        engine.roi_file = str(roi_file)
        engine._load_roi_coordinates()

        assert engine.roi_coords == [10.5, -20.3, 55.0]


# ---------------------------------------------------------------------------
# ExSearchEngine._find_roi_elements
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindRoiElements:
    def test_finds_elements_within_radius(self):
        engine = _make_engine()
        engine.roi_coords = [0.0, 0.0, 0.0]

        # Create mock mesh with baricenters
        centers = np.array([
            [0.0, 0.0, 0.0],   # inside
            [1.0, 0.0, 0.0],   # inside (dist=1)
            [5.0, 0.0, 0.0],   # outside (dist=5, radius=3)
            [10.0, 0.0, 0.0],  # outside
        ])
        volumes = np.array([1.0, 2.0, 3.0, 4.0])

        mesh = MagicMock()
        mesh.elements_baricenters.return_value = MagicMock(value=centers)
        mesh.elements_volumes_and_areas.return_value = MagicMock(value=volumes)
        engine.mesh = mesh

        engine._find_roi_elements(roi_radius=3.0)

        assert len(engine.roi_indices) == 2
        assert 0 in engine.roi_indices
        assert 1 in engine.roi_indices
        np.testing.assert_array_equal(engine.roi_volumes, [1.0, 2.0])

    def test_handles_2d_volumes(self):
        engine = _make_engine()
        engine.roi_coords = [0.0, 0.0, 0.0]

        centers = np.array([[0.0, 0.0, 0.0]])
        volumes = np.array([[1.0, 0.5]])  # 2D

        mesh = MagicMock()
        mesh.elements_baricenters.return_value = MagicMock(value=centers)
        mesh.elements_volumes_and_areas.return_value = MagicMock(value=volumes)
        engine.mesh = mesh

        engine._find_roi_elements(roi_radius=5.0)
        assert len(engine.roi_indices) == 1


# ---------------------------------------------------------------------------
# ExSearchEngine._find_gm_elements
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindGmElements:
    def test_finds_gm_by_tag(self):
        engine = _make_engine()

        tags = np.array([1, 2, 2, 1, 2])  # GM=2
        volumes = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        mesh = MagicMock()
        mesh.elm.tag1 = tags
        mesh.elements_volumes_and_areas.return_value = MagicMock(value=volumes)
        engine.mesh = mesh

        engine._find_gm_elements()

        assert len(engine.gm_indices) == 3
        np.testing.assert_array_equal(engine.gm_volumes, [2.0, 3.0, 5.0])


# ---------------------------------------------------------------------------
# ExSearchEngine.compute_ti_field
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeTiField:
    def test_computes_metrics(self):
        from simnibs.utils import TI_utils as TI

        engine = _make_engine()
        _setup_engine_fields(engine)

        # Mock TI functions to return known arrays
        ti_field = np.array([0.1, 0.2, 0.3, 0.15, 0.25])
        TI.get_field = MagicMock(return_value=np.zeros((5, 3)))
        TI.get_maxTI = MagicMock(return_value=ti_field)

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        assert "TestROI_TImax_ROI" in result
        assert "TestROI_TImean_ROI" in result
        assert "TestROI_TImean_GM" in result
        assert "TestROI_Focality" in result
        assert "TestROI_n_elements" in result
        assert result["current_ch1_mA"] == 1.0
        assert result["current_ch2_mA"] == 1.0

    def test_empty_roi(self):
        from simnibs.utils import TI_utils as TI

        engine = _make_engine()
        _setup_engine_fields(engine)
        engine.roi_indices = np.array([], dtype=int)
        engine.roi_volumes = np.array([])

        ti_field = np.array([0.1, 0.2, 0.3, 0.15, 0.25])
        TI.get_field = MagicMock(return_value=np.zeros((5, 3)))
        TI.get_maxTI = MagicMock(return_value=ti_field)

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)

        assert result["TestROI_TImax_ROI"] == 0.0
        assert result["TestROI_TImean_ROI"] == 0.0
        assert result["TestROI_Focality"] == 0.0

    def test_zero_gm_mean(self):
        from simnibs.utils import TI_utils as TI

        engine = _make_engine()
        _setup_engine_fields(engine)
        engine.gm_indices = np.array([3, 4])
        engine.gm_volumes = np.array([1.0, 1.0])

        # All-zero GM field
        ti_field = np.array([0.1, 0.2, 0.3, 0.0, 0.0])
        TI.get_field = MagicMock(return_value=np.zeros((5, 3)))
        TI.get_maxTI = MagicMock(return_value=ti_field)

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)
        assert result["TestROI_Focality"] == 0.0

    def test_empty_gm(self):
        from simnibs.utils import TI_utils as TI

        engine = _make_engine()
        _setup_engine_fields(engine)
        engine.gm_indices = np.array([], dtype=int)
        engine.gm_volumes = np.array([])

        ti_field = np.array([0.1, 0.2, 0.3])
        TI.get_field = MagicMock(return_value=np.zeros((3, 3)))
        TI.get_maxTI = MagicMock(return_value=ti_field)

        result = engine.compute_ti_field("E1", "E2", 1.0, "E3", "E4", 1.0)
        assert result["TestROI_TImean_GM"] == 0.0
        assert result["TestROI_Focality"] == 0.0


# ---------------------------------------------------------------------------
# ExSearchEngine.initialize
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInitialize:
    def test_calls_all_steps(self):
        engine = _make_engine()
        engine._load_leadfield = MagicMock()
        engine._load_roi_coordinates = MagicMock()
        engine._find_roi_elements = MagicMock()
        engine._find_gm_elements = MagicMock()

        engine.initialize(roi_radius=5.0)

        engine._load_leadfield.assert_called_once()
        engine._load_roi_coordinates.assert_called_once()
        engine._find_roi_elements.assert_called_once_with(5.0)
        engine._find_gm_elements.assert_called_once()


# ---------------------------------------------------------------------------
# ExSearchEngine.run
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRun:
    def test_basic_run(self):
        engine = _make_engine()
        engine.compute_ti_field = MagicMock(return_value={
            "TestROI_TImax_ROI": 0.5,
            "TestROI_TImean_ROI": 0.3,
            "TestROI_TImean_GM": 0.2,
            "TestROI_Focality": 1.5,
            "TestROI_n_elements": 100,
            "current_ch1_mA": 1.0,
            "current_ch2_mA": 1.0,
        })

        results = engine.run(
            e1_plus=["E1"],
            e1_minus=["E2"],
            e2_plus=["E3"],
            e2_minus=["E4"],
            current_ratios=[(1.0, 1.0)],
            all_combinations=False,
            output_dir="/tmp/out",
        )

        assert len(results) == 1
        engine.compute_ti_field.assert_called_once()

    def test_multiple_combinations(self):
        engine = _make_engine()
        engine.compute_ti_field = MagicMock(return_value={
            "TestROI_TImax_ROI": 0.5,
            "TestROI_TImean_ROI": 0.3,
            "TestROI_TImean_GM": 0.2,
            "TestROI_Focality": 1.5,
            "TestROI_n_elements": 100,
            "current_ch1_mA": 1.0,
            "current_ch2_mA": 1.0,
        })

        results = engine.run(
            e1_plus=["E1", "E2"],
            e1_minus=["E3"],
            e2_plus=["E4"],
            e2_minus=["E5"],
            current_ratios=[(1.0, 1.0), (1.5, 0.5)],
            all_combinations=False,
            output_dir="/tmp/out",
        )

        assert len(results) == 4  # 2 electrodes * 2 ratios

    def test_empty_results_no_crash(self):
        engine = _make_engine()
        results = engine.run(
            e1_plus=[],
            e1_minus=[],
            e2_plus=[],
            e2_minus=[],
            current_ratios=[(1.0, 1.0)],
            all_combinations=False,
            output_dir="/tmp/out",
        )
        assert len(results) == 0


# ---------------------------------------------------------------------------
# ExSearchEngine._log_config_summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLogConfigSummary:
    def test_logs_summary(self):
        logger = MagicMock()
        engine = _make_engine(logger=logger)
        engine._log_config_summary(
            ["E1"], ["E2"], ["E3"], ["E4"],
            [(1.0, 1.0)], False, 1,
        )
        assert logger.info.call_count >= 3


# ---------------------------------------------------------------------------
# Static ROI CRUD methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestROICrud:
    @patch("tit.paths.get_path_manager")
    def test_get_available_rois(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        (roi_dir / "motor.csv").write_text("1,2,3")
        (roi_dir / "visual.csv").write_text("4,5,6")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        rois = ExSearchEngine.get_available_rois("001")
        assert rois == ["motor.csv", "visual.csv"]

    @patch("tit.paths.get_path_manager")
    def test_create_roi(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ok, msg = ExSearchEngine.create_roi("001", "motor", 10.0, -20.0, 55.0)
        assert ok is True
        assert (roi_dir / "motor.csv").exists()
        assert (roi_dir / "roi_list.txt").exists()

        # Read the CSV
        with open(roi_dir / "motor.csv") as f:
            row = list(csv.reader(f))[0]
        assert float(row[0]) == 10.0

    @patch("tit.paths.get_path_manager")
    def test_create_roi_with_csv_suffix(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ok, msg = ExSearchEngine.create_roi("001", "motor.csv", 10.0, -20.0, 55.0)
        assert ok is True
        assert (roi_dir / "motor.csv").exists()

    @patch("tit.paths.get_path_manager")
    def test_create_roi_no_duplicate_in_list(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir(parents=True)
        (roi_dir / "roi_list.txt").write_text("motor.csv\n")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ExSearchEngine.create_roi("001", "motor.csv", 10.0, -20.0, 55.0)
        content = (roi_dir / "roi_list.txt").read_text()
        assert content.count("motor.csv") == 1

    @patch("tit.paths.get_path_manager")
    def test_delete_roi(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        (roi_dir / "motor.csv").write_text("1,2,3")
        (roi_dir / "roi_list.txt").write_text("motor.csv\nvisual.csv\n")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ok, msg = ExSearchEngine.delete_roi("001", "motor")
        assert ok is True
        assert not (roi_dir / "motor.csv").exists()
        content = (roi_dir / "roi_list.txt").read_text()
        assert "motor.csv" not in content
        assert "visual.csv" in content

    @patch("tit.paths.get_path_manager")
    def test_delete_nonexistent_roi(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ok, msg = ExSearchEngine.delete_roi("001", "nonexistent")
        assert ok is True

    @patch("tit.paths.get_path_manager")
    def test_delete_last_roi_clears_list(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        (roi_dir / "motor.csv").write_text("1,2,3")
        (roi_dir / "roi_list.txt").write_text("motor.csv\n")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        ExSearchEngine.delete_roi("001", "motor")
        content = (roi_dir / "roi_list.txt").read_text()
        assert content == ""

    @patch("tit.paths.get_path_manager")
    def test_get_roi_coordinates(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        with open(roi_dir / "motor.csv", "w", newline="") as f:
            csv.writer(f).writerow([10.5, -20.3, 55.0])

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        coords = ExSearchEngine.get_roi_coordinates("001", "motor")
        assert coords == (10.5, -20.3, 55.0)

    @patch("tit.paths.get_path_manager")
    def test_get_roi_coordinates_not_found(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        coords = ExSearchEngine.get_roi_coordinates("001", "nonexistent")
        assert coords is None

    @patch("tit.paths.get_path_manager")
    def test_get_roi_coordinates_empty_file(self, mock_gpm, tmp_path):
        roi_dir = tmp_path / "rois"
        roi_dir.mkdir()
        (roi_dir / "empty.csv").write_text("")

        mock_gpm.return_value = MagicMock()
        mock_gpm.return_value.rois.return_value = str(roi_dir)

        from tit.opt.ex.engine import ExSearchEngine

        coords = ExSearchEngine.get_roi_coordinates("001", "empty")
        assert coords is None
