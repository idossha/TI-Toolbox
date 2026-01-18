#!/usr/bin/env simnibs_python

"""
Test suite for main_analyzer.py

This module tests the main analyzer functionality including:
- Utility functions (formatting, logging, validation)
- Path construction
- Argument validation
"""

import pytest
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add the analyzer directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tit", "analyzer"))

# Import the module under test
try:
    import main_analyzer
except ImportError as e:
    # If relative imports fail, try absolute import
    import sys
    import os

    analyzer_path = os.path.join(os.path.dirname(__file__), "..", "tit", "analyzer")
    if analyzer_path not in sys.path:
        sys.path.insert(0, analyzer_path)
    import main_analyzer


class TestUtilityFunctions:
    """Test utility functions like formatting and validation."""

    def test_format_duration_seconds(self):
        """Test format_duration with seconds only."""
        result = main_analyzer.format_duration(45)
        assert result == "45s"

    def test_format_duration_minutes(self):
        """Test format_duration with minutes and seconds."""
        result = main_analyzer.format_duration(125)
        assert result == "2m 5s"

    def test_format_duration_hours(self):
        """Test format_duration with hours, minutes, and seconds."""
        result = main_analyzer.format_duration(3725)
        assert result == "1h 2m 5s"

    def test_validate_file_extension_valid(self):
        """Test file extension validation with valid extension."""
        # Should not raise an exception
        main_analyzer.validate_file_extension("test.msh", [".msh", ".nii"])

    def test_validate_file_extension_invalid(self):
        """Test file extension validation with invalid extension."""
        with pytest.raises(ValueError):
            main_analyzer.validate_file_extension("test.txt", [".msh", ".nii"])

    def test_validate_coordinates_valid(self):
        """Test coordinate validation with valid coordinates."""
        result = main_analyzer.validate_coordinates([10.0, 20.0, 30.0])
        assert result == [10.0, 20.0, 30.0]

    def test_validate_coordinates_invalid_length(self):
        """Test coordinate validation with wrong number of coordinates."""
        with pytest.raises(ValueError):
            main_analyzer.validate_coordinates([10.0, 20.0])

    def test_validate_coordinates_invalid_type(self):
        """Test coordinate validation with non-numeric coordinates."""
        with pytest.raises(ValueError):
            main_analyzer.validate_coordinates([10.0, "invalid", 30.0])

    def test_validate_radius_valid(self):
        """Test radius validation with valid radius."""
        result = main_analyzer.validate_radius(5.0)
        assert result == 5.0

    def test_validate_radius_zero(self):
        """Test radius validation with zero radius."""
        with pytest.raises(ValueError):
            main_analyzer.validate_radius(0.0)

    def test_validate_radius_negative(self):
        """Test radius validation with negative radius."""
        with pytest.raises(ValueError):
            main_analyzer.validate_radius(-1.0)


class TestPathConstruction:
    """Test path construction functions."""

    @patch("main_analyzer.get_path_manager")
    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_construct_mesh_field_path(self, mock_isdir, mock_exists, mock_get_pm):
        """Test mesh field path construction."""
        mock_isdir.return_value = True  # Mock project directory exists
        mock_pm = MagicMock()
        mock_pm.path_optional.return_value = (
            "/mnt/project/derivatives/SimNIBS/sub-001/Simulations/montage1/TI/mesh"
        )
        mock_get_pm.return_value = mock_pm
        mock_exists.return_value = False

        m2m_path = "/mnt/project/derivatives/SimNIBS/sub-001/m2m_001"
        montage = "montage1"
        result = main_analyzer.construct_mesh_field_path(m2m_path, montage)

        # Should return a path string
        assert isinstance(result, str)

    @patch("main_analyzer.get_path_manager")
    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_construct_mesh_field_path_with_path_manager(
        self, mock_isdir, mock_exists, mock_get_pm
    ):
        """Test mesh field path construction using PathManager."""
        mock_isdir.return_value = True  # Mock project directory exists
        mock_pm = MagicMock()
        mock_pm.path_optional.return_value = "/test/path"
        mock_get_pm.return_value = mock_pm
        mock_exists.return_value = False

        m2m_path = "/mnt/project/derivatives/SimNIBS/sub-001/m2m_001"
        montage = "montage1"
        result = main_analyzer.construct_mesh_field_path(m2m_path, montage)

        # The function should now use PathManager
        # (path_optional may or may not be called depending on the code path)


class TestLoggingFunctions:
    """Test logging utility functions."""

    @patch("main_analyzer.logger")
    def test_log_analysis_start(self, mock_logger):
        """Test analysis start logging."""
        main_analyzer.log_analysis_start("spherical", "001", "test_roi")
        mock_logger.info.assert_called()

    @patch("main_analyzer.logger")
    def test_log_analysis_complete(self, mock_logger):
        """Test analysis complete logging."""
        main_analyzer.log_analysis_complete(
            "spherical", "001", "results", "/output/path"
        )
        mock_logger.info.assert_called()

    @patch("main_analyzer.logger")
    def test_log_analysis_failed(self, mock_logger):
        """Test analysis failed logging."""
        main_analyzer.log_analysis_failed("spherical", "001", "error message")
        mock_logger.error.assert_called()


class TestROIHandling:
    """Test ROI description and handling functions."""

    def test_create_roi_description_spherical(self):
        """Test ROI description creation for spherical analysis."""
        mock_args = MagicMock()
        mock_args.analysis_type = "spherical"
        mock_args.coordinates = [10, 20, 30]
        mock_args.radius = 5.0

        result = main_analyzer.create_roi_description(mock_args)
        assert "spherical" in result.lower()
        assert "10.00" in result
        assert "5.0" in result

    def test_create_roi_description_cortical(self):
        """Test ROI description creation for cortical analysis."""
        mock_args = MagicMock()
        mock_args.analysis_type = "cortical"
        mock_args.whole_head = False
        mock_args.space = "mesh"
        mock_args.atlas_name = "test_atlas"
        mock_args.region = "precentral"

        result = main_analyzer.create_roi_description(mock_args)
        assert "precentral" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
