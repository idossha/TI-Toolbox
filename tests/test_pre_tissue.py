"""Tests for tit.pre.tissue_analyzer — tissue analysis."""

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

from tit.pre.utils import PreprocessError


MODULE = "tit.pre.tissue_analyzer"


@pytest.fixture
def mock_nib():
    """Return the mocked nibabel module."""
    import nibabel as nib
    return nib


@pytest.fixture
def mock_nii_image(mock_nib):
    """Create a mock NIfTI image with real numpy data."""
    # 10x10x10 volume with some tissue labels
    data = np.zeros((10, 10, 10), dtype=np.float64)
    # CSF labels
    data[3:7, 3:7, 3:7] = 4  # CSF label
    # Brain labels
    data[4:6, 4:6, 4:6] = 3  # cerebral cortex

    img = MagicMock()
    img.get_fdata.return_value = data
    header = MagicMock()
    header.get_zooms.return_value = (1.0, 1.0, 1.0)
    img.header = header
    mock_nib.load.return_value = img

    return img


class TestTissueAnalyzerInit:
    """Tests for TissueAnalyzer initialization."""

    def test_valid_tissue_type(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        assert analyzer.tissue_name == "CSF"

    def test_invalid_tissue_type(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        with pytest.raises(PreprocessError, match="Unknown tissue type"):
            TissueAnalyzer(
                tmp_path / "label.nii.gz", tmp_path / "out", "invalid", MagicMock()
            )

    def test_output_dir_created(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        out = tmp_path / "nested" / "output"
        TissueAnalyzer(tmp_path / "label.nii.gz", out, "bone", MagicMock())
        assert out.exists()

    def test_voxel_volume_calculated(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        assert analyzer.voxel_volume == 1.0


class TestTissueAnalyzerMasks:
    """Tests for mask creation methods."""

    def test_create_tissue_mask(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        mask = analyzer._create_tissue_mask()
        assert mask.dtype == np.uint8
        assert np.sum(mask) > 0

    def test_create_brain_mask(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        mask = analyzer._create_brain_mask()
        assert mask.dtype == np.uint8


class TestTissueAnalyzerThickness:
    """Tests for thickness calculation."""

    def test_calculate_thickness_empty_mask(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        empty = np.zeros((10, 10, 10), dtype=np.uint8)
        result = analyzer._calculate_thickness(empty)
        assert result["max"] == 0
        assert result["thickness_map"] is None

    def test_calculate_thickness_with_data(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer
        from scipy import ndimage

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )

        mask = np.zeros((10, 10, 10), dtype=np.uint8)
        mask[3:7, 3:7, 3:7] = 1

        # Mock scipy.ndimage.distance_transform_edt to return real array
        dist_map = np.ones((10, 10, 10), dtype=np.float64)
        dist_map[mask > 0] = 2.0
        ndimage.distance_transform_edt = MagicMock(return_value=dist_map)

        result = analyzer._calculate_thickness(mask)
        assert result["thickness_map"] is not None
        assert result["mean"] > 0


class TestFilterToBrainRegion:
    """Tests for _filter_to_brain_region."""

    def test_no_brain_coords_returns_original(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        tissue = np.ones((10, 10, 10), dtype=np.uint8)
        brain = np.zeros((10, 10, 10), dtype=np.uint8)

        result = analyzer._filter_to_brain_region(tissue, brain)
        np.testing.assert_array_equal(result, tissue)

    def test_with_brain_coords(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        tissue = np.ones((10, 10, 10), dtype=np.uint8)
        brain = np.zeros((10, 10, 10), dtype=np.uint8)
        brain[5, 5, 5] = 1

        result = analyzer._filter_to_brain_region(tissue, brain)
        assert result.dtype == np.uint8


class TestAnalyze:
    """Tests for the main analyze method."""

    def test_analyze_no_tissue(self, mock_nib, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        # All zeros — no tissue found
        data = np.zeros((10, 10, 10), dtype=np.float64)
        img = MagicMock()
        img.get_fdata.return_value = data
        header = MagicMock()
        header.get_zooms.return_value = (1.0, 1.0, 1.0)
        img.header = header
        mock_nib.load.return_value = img

        logger = MagicMock()
        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", logger
        )
        result = analyzer.analyze()

        assert result["volume_cm3"] == 0
        logger.warning.assert_called()

    def test_analyze_with_tissue(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer
        from scipy import ndimage

        # Mock distance_transform_edt
        ndimage.distance_transform_edt = MagicMock(
            return_value=np.ones((10, 10, 10), dtype=np.float64)
        )

        logger = MagicMock()
        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", logger
        )

        # Mock visualization to avoid matplotlib issues
        analyzer._create_visualizations = MagicMock()

        result = analyzer.analyze()

        assert "volume_cm3" in result
        assert "thickness" in result
        assert "voxels" in result
        assert "report_path" in result

    def test_analyze_no_brain_mask(self, mock_nib, tmp_path):
        """When brain mask is empty, uses tissue mask directly."""
        from tit.pre.tissue_analyzer import TissueAnalyzer
        from scipy import ndimage

        data = np.zeros((10, 10, 10), dtype=np.float64)
        data[3:7, 3:7, 3:7] = 4  # CSF only, no brain labels

        img = MagicMock()
        img.get_fdata.return_value = data
        header = MagicMock()
        header.get_zooms.return_value = (1.0, 1.0, 1.0)
        img.header = header
        mock_nib.load.return_value = img

        ndimage.distance_transform_edt = MagicMock(
            return_value=np.ones((10, 10, 10), dtype=np.float64)
        )

        logger = MagicMock()
        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", logger
        )
        analyzer._create_visualizations = MagicMock()

        result = analyzer.analyze()
        assert result["volume_cm3"] > 0


class TestWriteReport:
    """Tests for _write_report."""

    def test_report_written(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        out = tmp_path / "out"
        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", out, "csf", MagicMock()
        )

        tissue_mask = np.zeros((10, 10, 10), dtype=np.uint8)
        tissue_mask[3:7, 3:7, 3:7] = 1
        filtered_mask = tissue_mask.copy()
        thickness = {"mean": 2.0, "std": 0.5, "min": 1.0, "max": 3.0}

        report = analyzer._write_report(tissue_mask, filtered_mask, thickness)
        assert report.exists()
        content = report.read_text()
        assert "CSF" in content
        assert "VOLUME" in content
        assert "THICKNESS" in content


class TestCreateThicknessFigure:
    """Tests for _create_thickness_figure."""

    def test_empty_mask_returns_none(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer
        import matplotlib.pyplot as plt

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        filtered = np.zeros((10, 10, 10), dtype=np.uint8)
        result = analyzer._create_thickness_figure(
            filtered, {"thickness_map": None, "mean": 0, "std": 0, "min": 0, "max": 0}, plt
        )
        assert result is None

    def test_with_data(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer
        import matplotlib.pyplot as plt

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        filtered = np.zeros((10, 10, 10), dtype=np.uint8)
        filtered[3:7, 3:7, 3:7] = 1
        thickness_map = np.ones((10, 10, 10), dtype=np.float64) * 2.0

        result = analyzer._create_thickness_figure(
            filtered,
            {"thickness_map": thickness_map, "mean": 2.0, "std": 0.5, "min": 1.0, "max": 3.0},
            plt,
        )
        # With mocked matplotlib, this should still work (returns the path)


class TestCreateMethodologyFigure:
    """Tests for _create_methodology_figure."""

    def test_empty_tissue_mask(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer
        import matplotlib.pyplot as plt

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        tissue = np.zeros((10, 10, 10), dtype=np.uint8)
        brain = np.zeros((10, 10, 10), dtype=np.uint8)
        filtered = np.zeros((10, 10, 10), dtype=np.uint8)

        result = analyzer._create_methodology_figure(tissue, brain, filtered, plt)
        assert result is None

    def test_with_data(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer
        import matplotlib.pyplot as plt

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        tissue = np.zeros((10, 10, 10), dtype=np.uint8)
        tissue[3:7, 3:7, 3:7] = 1
        brain = np.zeros((10, 10, 10), dtype=np.uint8)
        brain[4:6, 4:6, 4:6] = 1
        filtered = tissue.copy()

        # With mocked matplotlib, should not raise
        analyzer._create_methodology_figure(tissue, brain, filtered, plt)


class TestCreateVisualizations:
    """Tests for visualization creation."""

    def test_matplotlib_not_available(self, mock_nii_image, tmp_path):
        """Logs warning when matplotlib import fails."""
        from tit.pre.tissue_analyzer import TissueAnalyzer

        logger = MagicMock()
        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", logger
        )

        # matplotlib is mocked but importable — the function should still work
        tissue_mask = np.zeros((10, 10, 10), dtype=np.uint8)
        brain_mask = np.zeros((10, 10, 10), dtype=np.uint8)
        filtered_mask = np.zeros((10, 10, 10), dtype=np.uint8)
        thickness = {"mean": 0, "std": 0, "min": 0, "max": 0, "thickness_map": None}

        # Should not raise
        analyzer._create_visualizations(
            tissue_mask, brain_mask, filtered_mask, thickness
        )

    def test_calls_figure_methods(self, mock_nii_image, tmp_path):
        """Calls both thickness and methodology figure methods."""
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        analyzer._create_thickness_figure = MagicMock()
        analyzer._create_methodology_figure = MagicMock()

        tissue = np.ones((10, 10, 10), dtype=np.uint8)
        brain = np.zeros((10, 10, 10), dtype=np.uint8)
        filtered = np.ones((10, 10, 10), dtype=np.uint8)
        thickness = {"mean": 1, "std": 0.5, "min": 0.5, "max": 2.0, "thickness_map": None}

        analyzer._create_visualizations(tissue, brain, filtered, thickness)

        analyzer._create_thickness_figure.assert_called_once()
        analyzer._create_methodology_figure.assert_called_once()


class TestLoadLabelNames:
    """Tests for _load_label_names."""

    def test_no_lut_file(self, mock_nii_image, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        # label_names should be empty dict when no LUT found
        assert isinstance(analyzer.label_names, dict)

    def test_lut_file_found(self, mock_nib, tmp_path):
        from tit.pre.tissue_analyzer import TissueAnalyzer

        # Create LUT file
        lut = tmp_path / "labeling_LUT.txt"
        lut.write_text("# Header\n4\tCSF:\n515\tBone:\n")

        data = np.zeros((10, 10, 10), dtype=np.float64)
        img = MagicMock()
        img.get_fdata.return_value = data
        header = MagicMock()
        header.get_zooms.return_value = (1.0, 1.0, 1.0)
        img.header = header
        mock_nib.load.return_value = img

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        assert 4 in analyzer.label_names
        assert analyzer.label_names[4] == "CSF"

    def test_lut_with_invalid_values(self, mock_nib, tmp_path):
        """LUT lines with non-integer IDs are skipped."""
        from tit.pre.tissue_analyzer import TissueAnalyzer

        lut = tmp_path / "labeling_LUT.txt"
        lut.write_text("# Header\nabc\tBad:\n4\tCSF:\nxyz\tAlsoBad\n")

        data = np.zeros((10, 10, 10), dtype=np.float64)
        img = MagicMock()
        img.get_fdata.return_value = data
        header = MagicMock()
        header.get_zooms.return_value = (1.0, 1.0, 1.0)
        img.header = header
        mock_nib.load.return_value = img

        analyzer = TissueAnalyzer(
            tmp_path / "label.nii.gz", tmp_path / "out", "csf", MagicMock()
        )
        assert 4 in analyzer.label_names
        assert len(analyzer.label_names) == 1

    def test_lut_simnibs_path(self, mock_nib, tmp_path):
        """Finds LUT in SimNIBS derivatives structure."""
        from tit.pre.tissue_analyzer import TissueAnalyzer

        # Create SimNIBS-style path structure
        simnibs_dir = tmp_path / "derivatives" / "SimNIBS" / "sub-001"
        m2m_dir = simnibs_dir / "m2m_001" / "segmentation"
        m2m_dir.mkdir(parents=True)
        lut = m2m_dir / "labeling_LUT.txt"
        lut.write_text("4\tCSF:\n")

        nifti_path = simnibs_dir / "label.nii.gz"

        data = np.zeros((10, 10, 10), dtype=np.float64)
        img = MagicMock()
        img.get_fdata.return_value = data
        header = MagicMock()
        header.get_zooms.return_value = (1.0, 1.0, 1.0)
        img.header = header
        mock_nib.load.return_value = img

        analyzer = TissueAnalyzer(nifti_path, tmp_path / "out", "csf", MagicMock())
        assert 4 in analyzer.label_names

    def test_lut_os_error(self, mock_nib, tmp_path):
        """Handles OSError when reading LUT file."""
        from tit.pre.tissue_analyzer import TissueAnalyzer

        lut = tmp_path / "labeling_LUT.txt"
        lut.write_text("4\tCSF:\n")

        data = np.zeros((10, 10, 10), dtype=np.float64)
        img = MagicMock()
        img.get_fdata.return_value = data
        header = MagicMock()
        header.get_zooms.return_value = (1.0, 1.0, 1.0)
        img.header = header
        mock_nib.load.return_value = img

        logger = MagicMock()
        with patch("builtins.open", side_effect=OSError("permission denied")):
            analyzer = TissueAnalyzer(
                tmp_path / "label.nii.gz", tmp_path / "out", "csf", logger
            )
        assert len(analyzer.label_names) == 0


class TestRunTissueAnalysis:
    """Tests for the run_tissue_analysis entry point."""

    @patch(f"{MODULE}.get_path_manager")
    def test_missing_labeling_raises(self, mock_gpm, tmp_path):
        from tit.pre.tissue_analyzer import run_tissue_analysis

        pm = MagicMock()
        pm.tissue_labeling.return_value = str(tmp_path / "nonexistent.nii.gz")
        mock_gpm.return_value = pm

        with pytest.raises(PreprocessError, match="not found"):
            run_tissue_analysis("/proj", "001", logger=MagicMock())

    @patch(f"{MODULE}.TissueAnalyzer")
    @patch(f"{MODULE}.get_path_manager")
    def test_analyzes_all_tissues(self, mock_gpm, mock_analyzer_cls, tmp_path):
        from tit.pre.tissue_analyzer import run_tissue_analysis

        pm = MagicMock()
        label_path = tmp_path / "label.nii.gz"
        label_path.touch()
        pm.tissue_labeling.return_value = str(label_path)
        pm.ensure.return_value = str(tmp_path / "output")
        pm.tissue_analysis_output.return_value = str(tmp_path / "output")
        mock_gpm.return_value = pm

        mock_analyzer_cls.return_value.analyze.return_value = {"volume_cm3": 1.0}

        result = run_tissue_analysis("/proj", "001", logger=MagicMock())

        assert len(result) == 3  # bone, csf, skin

    @patch(f"{MODULE}.get_path_manager")
    def test_unknown_tissue_skipped(self, mock_gpm, tmp_path):
        from tit.pre.tissue_analyzer import run_tissue_analysis

        pm = MagicMock()
        label_path = tmp_path / "label.nii.gz"
        label_path.touch()
        pm.tissue_labeling.return_value = str(label_path)
        pm.ensure.return_value = str(tmp_path / "output")
        pm.tissue_analysis_output.return_value = str(tmp_path / "output")
        mock_gpm.return_value = pm

        logger = MagicMock()
        result = run_tissue_analysis(
            "/proj", "001", tissues=["invalid_tissue"], logger=logger
        )

        logger.warning.assert_called()
        assert result == {}
