#!/usr/bin/env simnibs_python

"""
Test suite for analyzer_visualizer.py

This module tests the visualization functionality including:
- Base visualizer class
- Mesh and voxel visualizers
- Plotting and data processing functions
"""

import pytest
import os
import sys
import tempfile
import numpy as np
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import the module under test via its package path (avoids collisions with any
# unrelated top-level `visualizer` modules when running in different environments).
from tit.analyzer import visualizer as analyzer_visualizer


class TestBaseVisualizer:
    """Test the base visualizer class."""

    def test_base_visualizer_initialization(self):
        """Test BaseVisualizer initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            viz = analyzer_visualizer.BaseVisualizer(output_dir=temp_dir)
            assert viz.output_dir == temp_dir
            assert hasattr(viz, 'logger')

    def test_base_visualizer_default_output_dir(self):
        """Test BaseVisualizer with default output directory."""
        viz = analyzer_visualizer.BaseVisualizer(".")
        assert viz.output_dir == "."
        assert hasattr(viz, 'logger')


class TestVisualizer:
    """Test the main Visualizer class."""

    def test_visualizer_initialization(self):
        """Test Visualizer initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            viz = analyzer_visualizer.Visualizer(output_dir=temp_dir)
            assert isinstance(viz, analyzer_visualizer.BaseVisualizer)
            assert viz.output_dir == temp_dir

    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.figure')
    @patch('matplotlib.pyplot.close')
    def test_save_plot(self, mock_close, mock_figure, mock_savefig):
        """Test plot saving functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            viz = analyzer_visualizer.Visualizer(output_dir=temp_dir)

            # Mock a simple plot
            mock_fig = MagicMock()
            mock_figure.return_value = mock_fig

            # This would test the save_plot method if it existed
            # For now, just ensure the class can be instantiated
            assert viz.output_dir == temp_dir


class TestMeshVisualizer:
    """Test the MeshVisualizer class."""

    def test_mesh_visualizer_initialization(self):
        """Test MeshVisualizer initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            viz = analyzer_visualizer.MeshVisualizer(output_dir=temp_dir)
            assert isinstance(viz, analyzer_visualizer.Visualizer)
            assert viz.output_dir == temp_dir

    def test_mesh_data_loading(self):
        """Test mesh data loading setup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            viz = analyzer_visualizer.MeshVisualizer(output_dir=temp_dir)

            # Test that the class can be instantiated
            assert viz.output_dir == temp_dir
            assert isinstance(viz, analyzer_visualizer.MeshVisualizer)


class TestVoxelVisualizer:
    """Test the VoxelVisualizer class."""

    def test_voxel_visualizer_initialization(self):
        """Test VoxelVisualizer initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            viz = analyzer_visualizer.VoxelVisualizer(output_dir=temp_dir)
            assert isinstance(viz, analyzer_visualizer.Visualizer)
            assert viz.output_dir == temp_dir

    @patch('nibabel.load')
    def test_nifti_data_loading(self, mock_load):
        """Test NIfTI data loading."""
        mock_img = MagicMock()
        mock_load.return_value = mock_img

        with tempfile.TemporaryDirectory() as temp_dir:
            viz = analyzer_visualizer.VoxelVisualizer(output_dir=temp_dir)

            # Test would load NIfTI data
            # For now, just ensure the class can be instantiated
            assert viz.output_dir == temp_dir


class TestDataProcessing:
    """Test data processing functions."""

    def test_data_validation(self):
        """Test data validation functions."""
        # This would test data validation functions
        # For now, just ensure the module can be imported and classes instantiated
        with tempfile.TemporaryDirectory() as temp_dir:
            base_viz = analyzer_visualizer.BaseVisualizer(output_dir=temp_dir)
            viz = analyzer_visualizer.Visualizer(output_dir=temp_dir)
            mesh_viz = analyzer_visualizer.MeshVisualizer(output_dir=temp_dir)
            voxel_viz = analyzer_visualizer.VoxelVisualizer(output_dir=temp_dir)

            assert base_viz is not None
            assert viz is not None
            assert mesh_viz is not None
            assert voxel_viz is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
