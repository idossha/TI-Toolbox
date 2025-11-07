#!/usr/bin/env simnibs_python
"""
Unit tests for ex-search analyzer (ti-toolbox/opt/ex/ex_analyzer.py)
"""

import pytest
import numpy as np
import sys
import os
import tempfile
import json
import csv
from unittest.mock import MagicMock, patch, Mock, mock_open
from pathlib import Path

# Add ti-toolbox directory to path
project_root = os.path.join(os.path.dirname(__file__), '..')
ti_toolbox_dir = os.path.join(project_root, 'ti-toolbox')
sys.path.insert(0, ti_toolbox_dir)

from opt.ex.ex_analyzer import analyze_ex_search
from opt.roi import ROICoordinateHelper


class TestAnalyzeExSearch:
    """Test analyze_ex_search function"""

    def setup_method(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.opt_dir = os.path.join(self.temp_dir, "opt")
        self.roi_dir = os.path.join(self.temp_dir, "roi")
        os.makedirs(self.opt_dir)
        os.makedirs(self.roi_dir)

        # Create mock logger
        self.logger = MagicMock()

    def teardown_method(self):
        """Cleanup test fixtures"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_analyze_no_mesh_files(self):
        """Test analysis with no mesh files"""
        position_files = []

        result = analyze_ex_search(
            self.opt_dir,
            self.roi_dir,
            position_files,
            "/fake/m2m",
            self.logger
        )

        # Should handle gracefully with no files
        self.logger.info.assert_called()

    @patch('opt.ex.ex_analyzer.mesh_io')
    @patch('opt.ex.ex_analyzer.ROICoordinateHelper')
    def test_analyze_with_valid_mesh(self, mock_roi_helper, mock_mesh_io):
        """Test analysis with valid mesh file"""
        # Create fake mesh file
        mesh_file = os.path.join(self.opt_dir, "test_montage.msh")
        open(mesh_file, 'w').close()

        # Create ROI position file
        roi_file = os.path.join(self.roi_dir, "target1.csv")
        with open(roi_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["x", "y", "z"])
            writer.writerow([10.0, 20.0, 30.0])

        # Mock mesh object
        mock_mesh = MagicMock()
        mock_field = MagicMock()
        mock_field.value = np.ones(100) * 0.5  # 100 elements with value 0.5
        mock_mesh.field = {'TImax': mock_field}
        mock_mesh.elm.tag1 = np.ones(100) * 2  # Gray matter tags
        mock_mesh_io.read_msh.return_value = mock_mesh

        # Mock ROI helper
        mock_roi_helper.load_roi_from_csv.return_value = np.array([10.0, 20.0, 30.0])

        # Mock find_roi_element_indices to return some indices
        with patch('opt.ex.ex_analyzer.find_roi_element_indices') as mock_find:
            mock_find.return_value = (np.array([0, 1, 2]), np.array([1.0, 1.0, 1.0]))

            result = analyze_ex_search(
                self.opt_dir,
                self.roi_dir,
                [roi_file],
                "/fake/m2m",
                self.logger
            )

            # Should have processed the mesh
            assert mock_mesh_io.read_msh.called
            assert self.logger.info.called

    @patch('opt.ex.ex_analyzer.mesh_io')
    def test_analyze_mesh_load_error(self, mock_mesh_io):
        """Test analysis handles mesh loading errors"""
        # Create fake mesh file
        mesh_file = os.path.join(self.opt_dir, "bad_mesh.msh")
        open(mesh_file, 'w').close()

        # Mock mesh_io to raise exception
        mock_mesh_io.read_msh.side_effect = Exception("Failed to load mesh")

        roi_file = os.path.join(self.roi_dir, "target1.csv")
        with open(roi_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["x", "y", "z"])
            writer.writerow([10.0, 20.0, 30.0])

        result = analyze_ex_search(
            self.opt_dir,
            self.roi_dir,
            [roi_file],
            "/fake/m2m",
            self.logger
        )

        # Should log error
        self.logger.error.assert_called()

    def test_analyze_creates_analysis_directory(self):
        """Test that analysis directory is created"""
        analyze_ex_search(
            self.opt_dir,
            self.roi_dir,
            [],
            "/fake/m2m",
            self.logger
        )

        analysis_dir = os.path.join(self.opt_dir, "analysis")
        assert os.path.exists(analysis_dir)
        assert os.path.isdir(analysis_dir)


class TestROICoordinateHelper:
    """Test ROICoordinateHelper utility"""

    def setup_method(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup test fixtures"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_load_roi_from_valid_csv(self):
        """Test loading ROI from valid CSV file"""
        csv_file = os.path.join(self.temp_dir, "roi.csv")
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["x", "y", "z"])
            writer.writerow([10.5, 20.5, 30.5])

        coords = ROICoordinateHelper.load_roi_from_csv(csv_file)

        assert coords is not None
        assert len(coords) == 3
        assert np.isclose(coords[0], 10.5)
        assert np.isclose(coords[1], 20.5)
        assert np.isclose(coords[2], 30.5)

    def test_load_roi_from_invalid_csv(self):
        """Test loading ROI from invalid CSV file"""
        csv_file = os.path.join(self.temp_dir, "bad_roi.csv")
        with open(csv_file, 'w') as f:
            f.write("invalid,data\n")

        coords = ROICoordinateHelper.load_roi_from_csv(csv_file)

        # Should return None for invalid file
        assert coords is None

    def test_load_roi_from_nonexistent_file(self):
        """Test loading ROI from non-existent file"""
        fake_file = os.path.join(self.temp_dir, "does_not_exist.csv")

        coords = ROICoordinateHelper.load_roi_from_csv(fake_file)

        # Should return None for non-existent file
        assert coords is None


class TestExSearchIntegration:
    """Integration tests for ex-search analysis workflow"""

    def setup_method(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup test fixtures"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('opt.ex.ex_analyzer.mesh_io')
    @patch('opt.ex.ex_analyzer.find_roi_element_indices')
    def test_full_analysis_workflow(self, mock_find_roi, mock_mesh_io):
        """Test complete analysis workflow"""
        # Setup directories
        opt_dir = os.path.join(self.temp_dir, "opt")
        roi_dir = os.path.join(self.temp_dir, "roi")
        os.makedirs(opt_dir)
        os.makedirs(roi_dir)

        # Create multiple mesh files
        for i in range(3):
            mesh_file = os.path.join(opt_dir, f"montage_{i}.msh")
            open(mesh_file, 'w').close()

        # Create multiple ROI files
        roi_files = []
        for i in range(2):
            roi_file = os.path.join(roi_dir, f"roi_{i}.csv")
            with open(roi_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["x", "y", "z"])
                writer.writerow([i * 10, i * 10, 0])
            roi_files.append(roi_file)

        # Mock mesh data
        mock_mesh = MagicMock()
        mock_field = MagicMock()
        mock_field.value = np.random.rand(100) * 1.0
        mock_mesh.field = {'TImax': mock_field}
        mock_mesh.elm.tag1 = np.ones(100) * 2
        mock_mesh_io.read_msh.return_value = mock_mesh

        # Mock ROI finding
        mock_find_roi.return_value = (np.array([0, 1, 2]), np.array([1.0, 1.0, 1.0]))

        logger = MagicMock()

        result = analyze_ex_search(
            opt_dir,
            roi_dir,
            roi_files,
            "/fake/m2m",
            logger
        )

        # Should have processed all meshes
        assert mock_mesh_io.read_msh.call_count == 3
        assert logger.info.call_count >= 3  # At least one log per mesh

    @patch('opt.ex.ex_analyzer.mesh_io')
    def test_analysis_with_missing_field(self, mock_mesh_io):
        """Test analysis when TImax field is missing"""
        opt_dir = os.path.join(self.temp_dir, "opt")
        roi_dir = os.path.join(self.temp_dir, "roi")
        os.makedirs(opt_dir)
        os.makedirs(roi_dir)

        mesh_file = os.path.join(opt_dir, "test.msh")
        open(mesh_file, 'w').close()

        roi_file = os.path.join(roi_dir, "roi.csv")
        with open(roi_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["x", "y", "z"])
            writer.writerow([0, 0, 0])

        # Mock mesh without TImax field
        mock_mesh = MagicMock()
        mock_mesh.field = {}  # No TImax field
        mock_mesh_io.read_msh.return_value = mock_mesh

        logger = MagicMock()

        with patch('opt.ex.ex_analyzer.find_roi_element_indices') as mock_find:
            mock_find.return_value = (np.array([0, 1]), np.array([1.0, 1.0]))

            result = analyze_ex_search(
                opt_dir,
                roi_dir,
                [roi_file],
                "/fake/m2m",
                logger
            )

            # Should log error about missing field
            assert logger.error.called or logger.warning.called

    @patch('opt.ex.ex_analyzer.mesh_io')
    @patch('opt.ex.ex_analyzer.find_roi_element_indices')
    def test_analysis_with_empty_roi(self, mock_find_roi, mock_mesh_io):
        """Test analysis when no elements found in ROI"""
        opt_dir = os.path.join(self.temp_dir, "opt")
        roi_dir = os.path.join(self.temp_dir, "roi")
        os.makedirs(opt_dir)
        os.makedirs(roi_dir)

        mesh_file = os.path.join(opt_dir, "test.msh")
        open(mesh_file, 'w').close()

        roi_file = os.path.join(roi_dir, "roi.csv")
        with open(roi_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["x", "y", "z"])
            writer.writerow([1000, 1000, 1000])  # Far from mesh

        mock_mesh = MagicMock()
        mock_field = MagicMock()
        mock_field.value = np.ones(100)
        mock_mesh.field = {'TImax': mock_field}
        mock_mesh_io.read_msh.return_value = mock_mesh

        # Return empty ROI
        mock_find_roi.return_value = (np.array([]), np.array([]))

        logger = MagicMock()

        result = analyze_ex_search(
            opt_dir,
            roi_dir,
            [roi_file],
            "/fake/m2m",
            logger
        )

        # Should log warning about empty ROI
        assert logger.warning.called
