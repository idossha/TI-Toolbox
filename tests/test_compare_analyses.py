#!/usr/bin/env simnibs_python

"""
Test suite for compare_analyses.py

This module tests the analysis comparison functionality including:
- Project name extraction
- Group logger setup
- Path validation and processing
"""

import pytest
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add the analyzer directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tit', 'analyzer'))

# Import the module under test
try:
    import compare_analyses
except ImportError as e:
    # If relative imports fail, try absolute import
    import sys
    import os
    analyzer_path = os.path.join(os.path.dirname(__file__), '..', 'tit', 'analyzer')
    if analyzer_path not in sys.path:
        sys.path.insert(0, analyzer_path)
    import compare_analyses


class TestProjectNameExtraction:
    """Test project name extraction from file paths."""

    def test_extract_project_name_mnt_pattern(self):
        """Test extraction from /mnt/{project_name}/derivatives/... pattern."""
        test_path = "/mnt/my_project/derivatives/SimNIBS/sub-001/Simulations/montage1/TI/fields.msh"
        result = compare_analyses._extract_project_name(test_path)
        assert result == "my_project"

    def test_extract_project_name_different_mnt_pattern(self):
        """Test extraction from different /mnt patterns."""
        test_path = "/mnt/test_project_123/derivatives/ti-toolbox/logs/sub-001/analyzer.log"
        result = compare_analyses._extract_project_name(test_path)
        assert result == "test_project_123"

    def test_extract_project_name_no_mnt_pattern(self):
        """Test extraction fallback when /mnt pattern not found but derivatives found."""
        test_path = "/home/user/projects/my_project/derivatives/SimNIBS/sub-001/Simulations/montage1/TI/fields.msh"
        result = compare_analyses._extract_project_name(test_path)
        # Should extract the directory before 'derivatives'
        assert result == "my_project"

    def test_extract_project_name_empty_path(self):
        """Test extraction with empty path."""
        result = compare_analyses._extract_project_name("")
        assert result == "unknown_project"

    def test_extract_project_name_root_path(self):
        """Test extraction with root path only."""
        result = compare_analyses._extract_project_name("/")
        assert result == "unknown_project"


class TestGroupLoggerSetup:
    """Test group logger setup functionality."""

    @patch('compare_analyses.logging_util.get_logger')
    @patch('os.makedirs')
    @patch('os.path.exists')
    @patch('os.path.isdir')
    def test_setup_group_logger_creates_directory(self, mock_isdir, mock_exists, mock_makedirs, mock_get_logger):
        """Test that setup_group_logger creates the log directory."""
        mock_isdir.return_value = True  # Mock project directory exists
        mock_exists.return_value = False
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Reset global logger
        compare_analyses.group_logger = None

        result = compare_analyses.setup_group_logger("test_project")

        # Should create the directory
        mock_makedirs.assert_called_once()
        # Should call get_logger
        mock_get_logger.assert_called_once()
        # Should return the logger
        assert result == mock_logger

    @patch('compare_analyses.logging_util.get_logger')
    def test_setup_group_logger_reuses_existing(self, mock_get_logger):
        """Test that setup_group_logger reuses existing logger."""
        mock_logger = MagicMock()
        compare_analyses.group_logger = mock_logger

        result = compare_analyses.setup_group_logger("test_project")

        # Should not call get_logger again
        mock_get_logger.assert_not_called()
        # Should return the existing logger
        assert result == mock_logger

    @patch('compare_analyses.logging_util.get_logger')
    @patch('os.makedirs')
    @patch('os.path.isdir')
    def test_setup_group_logger_log_file_creation(self, mock_isdir, mock_makedirs, mock_get_logger):
        """Test that the log file path is constructed correctly."""
        mock_isdir.return_value = True  # Mock project directory exists
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Reset global logger
        compare_analyses.group_logger = None

        result = compare_analyses.setup_group_logger("test_project")

        # Check that get_logger was called with a log file path containing the expected directory
        call_args = mock_get_logger.call_args
        log_file_path = call_args[0][1]  # Second argument is the log file path
        assert "group_analysis" in log_file_path
        assert log_file_path.endswith(".log")


class TestPathValidation:
    """Test path validation and processing functions."""

    def test_path_validation_with_valid_paths(self):
        """Test path validation with valid analysis paths."""
        # This would test the validate_analysis_paths function
        # For now, just ensure the module can be imported and basic functions work
        assert callable(compare_analyses._extract_project_name)
        assert callable(compare_analyses.setup_group_logger)

    def test_empty_analysis_list(self):
        """Test behavior with empty analysis list."""
        # This would test functions that process analysis lists
        # For now, just ensure basic functions are callable
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
