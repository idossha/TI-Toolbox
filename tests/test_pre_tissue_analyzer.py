#!/usr/bin/env python
"""
Unit tests for TI-Toolbox tissue analyzer (pre/tissue_analyzer.py)
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from pre.tissue_analyzer import (
    DEFAULT_TISSUES,
    TISSUE_CONFIGS,
    TissueAnalyzer,
    run_tissue_analysis,
)
from pre.common import PreprocessError


def _fake_nifti(data: np.ndarray):
    """Create a mock NIfTI object."""
    from types import SimpleNamespace

    header = MagicMock()
    header.get_zooms.return_value = (1.0, 1.0, 1.0, 1.0)
    return SimpleNamespace(
        get_fdata=lambda: data,
        affine=np.eye(4),
        header=header,
    )


class TestDefaultTissues:
    """Test DEFAULT_TISSUES constant."""

    def test_contains_expected_values(self):
        assert "bone" in DEFAULT_TISSUES
        assert "csf" in DEFAULT_TISSUES
        assert "skin" in DEFAULT_TISSUES

    def test_is_tuple(self):
        assert isinstance(DEFAULT_TISSUES, tuple)

    def test_has_correct_count(self):
        assert len(DEFAULT_TISSUES) == 3


class TestTissueConfigs:
    """Test TISSUE_CONFIGS dictionary."""

    def test_has_required_keys(self):
        for tissue, config in TISSUE_CONFIGS.items():
            assert "name" in config
            assert "labels" in config
            assert "padding" in config
            assert "color_scheme" in config
            assert "tissue_color" in config
            assert "brain_labels" in config

    def test_labels_are_lists(self):
        for tissue, config in TISSUE_CONFIGS.items():
            assert isinstance(config["labels"], list)
            assert isinstance(config["brain_labels"], list)


class TestTissueAnalyzer:
    """Test TissueAnalyzer class."""

    def test_init_raises_on_unknown_tissue(self, tmp_path):
        nifti_path = tmp_path / "seg.nii.gz"
        nifti_path.write_text("dummy")

        data = np.zeros((3, 3, 3), dtype=float)
        logger = MagicMock()

        with patch("pre.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
            with pytest.raises(PreprocessError) as exc_info:
                TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), "unknown_tissue", logger)
            assert "Unknown tissue type" in str(exc_info.value)

    def test_creates_tissue_mask(self, tmp_path):
        nifti_path = tmp_path / "seg.nii.gz"
        nifti_path.write_text("dummy")

        data = np.zeros((4, 4, 4), dtype=float)
        data[1, 1, 1] = 4  # CSF label
        data[2, 2, 2] = 5  # Another CSF label
        logger = MagicMock()

        with patch("pre.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
            analyzer = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), "csf", logger)
            mask = analyzer._create_tissue_mask()

        assert mask.shape == data.shape
        assert mask[1, 1, 1] == 1
        assert mask[2, 2, 2] == 1
        assert mask.sum() == 2

    def test_creates_brain_mask(self, tmp_path):
        nifti_path = tmp_path / "seg.nii.gz"
        nifti_path.write_text("dummy")

        data = np.zeros((4, 4, 4), dtype=float)
        data[1, 1, 1] = 3  # Brain label
        data[2, 2, 2] = 42  # Another brain label
        logger = MagicMock()

        with patch("pre.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
            analyzer = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), "csf", logger)
            mask = analyzer._create_brain_mask()

        assert mask[1, 1, 1] == 1
        assert mask[2, 2, 2] == 1
        assert mask.sum() == 2

    def test_handles_no_tissue(self, tmp_path):
        nifti_path = tmp_path / "seg.nii.gz"
        nifti_path.write_text("dummy")

        data = np.zeros((4, 4, 4), dtype=float)  # No tissue labels
        logger = MagicMock()

        with patch("pre.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
            analyzer = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), "csf", logger)
            result = analyzer.analyze()

        assert result["volume_cm3"] == 0

    def test_calculates_thickness(self, tmp_path):
        nifti_path = tmp_path / "seg.nii.gz"
        nifti_path.write_text("dummy")

        # Create a simple 3D tissue block
        data = np.zeros((10, 10, 10), dtype=float)
        data[3:7, 3:7, 3:7] = 4  # CSF block
        logger = MagicMock()

        with patch("pre.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
            analyzer = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), "csf", logger)
            mask = analyzer._create_tissue_mask()
            stats = analyzer._calculate_thickness(mask)

        assert stats["mean"] > 0
        assert stats["max"] > stats["min"]
        assert stats["thickness_map"] is not None

    def test_loads_label_names_from_lut(self, tmp_path):
        nifti_path = tmp_path / "seg.nii.gz"
        nifti_path.write_text("dummy")

        lut = tmp_path / "labeling_LUT.txt"
        lut.write_text("# comment\n1\tGray Matter:\t0\t0\t0\t0\n2\tWhite Matter:\t0\t0\t0\t0\n")

        data = np.zeros((3, 3, 3), dtype=float)
        logger = MagicMock()

        with patch("pre.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
            analyzer = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), "csf", logger)

        assert analyzer.label_names.get(1) == "Gray Matter"
        assert analyzer.label_names.get(2) == "White Matter"


class TestRunTissueAnalysis:
    """Test run_tissue_analysis function."""

    @patch("pre.tissue_analyzer.get_path_manager")
    def test_raises_if_labeling_not_found(self, mock_get_pm):
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            mock_pm.path.return_value = str(label_path)

            logger = MagicMock()

            with pytest.raises(PreprocessError) as exc_info:
                run_tissue_analysis(tmpdir, "001", logger=logger)

            assert "Labeling.nii.gz not found" in str(exc_info.value)

    @patch("pre.tissue_analyzer.get_path_manager")
    @patch("pre.tissue_analyzer.TissueAnalyzer")
    def test_processes_default_tissues(self, mock_analyzer_class, mock_get_pm):
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()
            output_dir = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_dir)

            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = {"volume_cm3": 1.0}
            mock_analyzer_class.return_value = mock_analyzer

            logger = MagicMock()

            results = run_tissue_analysis(tmpdir, "001", logger=logger)

            # Should be called for each default tissue
            assert mock_analyzer_class.call_count == len(DEFAULT_TISSUES)
            assert len(results) == len(DEFAULT_TISSUES)

    @patch("pre.tissue_analyzer.get_path_manager")
    @patch("pre.tissue_analyzer.TissueAnalyzer")
    def test_processes_custom_tissues(self, mock_analyzer_class, mock_get_pm):
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()
            output_dir = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_dir)

            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = {"volume_cm3": 1.0}
            mock_analyzer_class.return_value = mock_analyzer

            logger = MagicMock()

            results = run_tissue_analysis(tmpdir, "001", tissues=["csf"], logger=logger)

            assert mock_analyzer_class.call_count == 1
            assert "csf" in results

    @patch("pre.tissue_analyzer.get_path_manager")
    @patch("pre.tissue_analyzer.TissueAnalyzer")
    def test_skips_unknown_tissue(self, mock_analyzer_class, mock_get_pm):
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        with tempfile.TemporaryDirectory() as tmpdir:
            label_path = Path(tmpdir) / "Labeling.nii.gz"
            label_path.touch()
            output_dir = Path(tmpdir) / "output"

            mock_pm.path.return_value = str(label_path)
            mock_pm.ensure_dir.return_value = str(output_dir)

            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = {"volume_cm3": 1.0}
            mock_analyzer_class.return_value = mock_analyzer

            logger = MagicMock()

            results = run_tissue_analysis(tmpdir, "001", tissues=["unknown", "csf"], logger=logger)

            # Should only process known tissue
            assert mock_analyzer_class.call_count == 1
            assert "csf" in results
            assert "unknown" not in results
            logger.warning.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
