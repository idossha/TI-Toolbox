#!/usr/bin/env python3

"""
Test suite for visualizer.py

This module tests the visualizer functionality including:
- BaseVisualizer initialization and CSV saving
- Visualizer plotting methods
- MeshVisualizer mesh-specific functionality
- VoxelVisualizer voxel-specific functionality
- Error handling for missing dependencies
"""

import pytest
import os
import sys
import tempfile
import numpy as np
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import csv

# Add the analyzer directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'analyzer'))
# Add the utils directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

# Import the module under test
import visualizer
import logging_util
import matplotlib


class TestBaseVisualizerInitialization:
    """Test BaseVisualizer initialization and basic functionality."""
    
    def test_init_with_logger(self):
        """Test BaseVisualizer initialization with provided logger."""
        mock_logger = MagicMock()
        output_dir = "/path/to/output"
        
        with patch('os.makedirs') as mock_makedirs:
            viz = visualizer.BaseVisualizer(output_dir, mock_logger)
            
            assert viz.output_dir == output_dir
            assert viz.logger == mock_logger.getChild.return_value
            mock_logger.getChild.assert_called_once_with('visualizer')
    
    def test_init_without_logger(self):
        """Test BaseVisualizer initialization without logger."""
        output_dir = "/path/to/output"
        
        with patch('os.makedirs') as mock_makedirs, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.BaseVisualizer(output_dir, None)
            
            assert viz.output_dir == output_dir
            assert viz.logger == mock_logger
            # Check that makedirs was called for the log directory
            assert mock_makedirs.call_count >= 1
    
    def test_init_creates_output_directory(self):
        """Test that BaseVisualizer creates output directory if it doesn't exist."""
        output_dir = "/path/to/output"
        
        with patch('os.path.exists', return_value=False), \
             patch('os.makedirs') as mock_makedirs, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.BaseVisualizer(output_dir, None)
            
            mock_makedirs.assert_called_with(output_dir)
            mock_logger.info.assert_called_with(f"Creating output directory: {output_dir}")


class TestCSVSaving:
    """Test CSV saving functionality."""
    
    def test_save_results_to_csv_spherical(self):
        """Test saving spherical analysis results to CSV."""
        output_dir = "/path/to/output"
        results = {
            'mean_value': 0.5,
            'max_value': 1.0,
            'min_value': 0.1,
            'focality': 0.8,
            'elements_in_roi': 100,
            'roi_mask': np.array([True, False, True])  # Should be excluded
        }
        
        with patch('os.path.join', return_value="/path/to/output/spherical_region.csv"), \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.BaseVisualizer(output_dir, None)
            result_path = viz.save_results_to_csv(results, 'spherical', 'region', 'node')
            
            assert result_path == "/path/to/output/spherical_region.csv"
            mock_file.assert_any_call("/path/to/output/spherical_region.csv", 'w', newline='')
    
    def test_save_results_to_csv_cortical(self):
        """Test saving cortical analysis results to CSV."""
        output_dir = "/path/to/output"
        results = {
            'mean_value': 0.5,
            'max_value': 1.0,
            'min_value': 0.1,
            'focality': 0.8,
            'nodes_in_roi': 50,
            'visualization_file': '/path/to/viz.msh'
        }
        
        with patch('os.path.join', return_value="/path/to/output/cortical_region.csv"), \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.BaseVisualizer(output_dir, None)
            result_path = viz.save_results_to_csv(results, 'cortical', 'region', 'node')
            
            assert result_path == "/path/to/output/cortical_region.csv"
            mock_file.assert_any_call("/path/to/output/cortical_region.csv", 'w', newline='')
    
    def test_save_extra_info_to_csv(self):
        """Test saving focality extra information to CSV."""
        output_dir = "/path/to/output"
        focality_info = {
            'focality_50': 0.3,
            'focality_75': 0.5,
            'focality_90': 0.7,
            'focality_95': 0.9
        }
        
        with patch('os.path.join', return_value="/path/to/output/spherical_region_extra_info.csv"), \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.BaseVisualizer(output_dir, None)
            result_path = viz.save_extra_info_to_csv(focality_info, 'spherical', 'region', 'node')
            
            assert result_path == "/path/to/output/spherical_region_extra_info.csv"
            mock_file.assert_any_call("/path/to/output/spherical_region_extra_info.csv", 'w', newline='')
    
    def test_save_whole_head_results_to_csv(self):
        """Test saving whole head analysis results to CSV."""
        output_dir = "/path/to/output"
        results = {
            'region1': {
                'mean_value': 0.5,
                'max_value': 1.0,
                'min_value': 0.1,
                'focality': 0.8,
                'normal_mean_value': 0.3,
                'normal_max_value': 0.6,
                'normal_min_value': 0.05,
                'normal_focality': 0.6,
                'voxels_in_roi': 100
            }
        }
        
        with patch('os.path.join', return_value="/path/to/output/whole_head_DK40_summary.csv"), \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.BaseVisualizer(output_dir, None)
            result_path = viz.save_whole_head_results_to_csv(results, 'DK40', 'voxel')
            
            assert result_path == "/path/to/output/whole_head_DK40_summary.csv"
            mock_file.assert_any_call("/path/to/output/whole_head_DK40_summary.csv", 'w', newline='')


class TestVisualizerPlotting:
    """Test plotting functionality in Visualizer class."""
    
    def test_generate_cortex_scatter_plot_no_matplotlib(self):
        """Test generate_cortex_scatter_plot when matplotlib is not available."""
        with patch('visualizer.plt', None), \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.Visualizer("/path/to/output", None)
            viz.generate_cortex_scatter_plot({}, 'DK40', 'voxel')
            
            mock_logger.warning.assert_called_with("matplotlib not available. Cannot generate scatter plot.")
    
    @patch('visualizer.plt')
    def test_generate_cortex_scatter_plot_success(self, mock_plt):
        """Test successful generation of cortex scatter plot."""
        results = {
            'region1': {'mean_value': 0.5, 'voxels_in_roi': 100},
            'region2': {'mean_value': 0.8, 'voxels_in_roi': 150},
            'region3': {'mean_value': None, 'voxels_in_roi': 0}  # Should be filtered out
        }
        
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.join', return_value="/path/to/output/cortex_analysis_DK40.png"), \
             patch('os.makedirs'):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Mock matplotlib components
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_plt.subplots.return_value = (mock_fig, mock_ax)
            mock_plt.colorbar.return_value = MagicMock()
            mock_plt.tight_layout.return_value = None
            mock_plt.savefig.return_value = None
            mock_plt.close.return_value = None
            
            # Mock matplotlib.cm
            mock_plt.cm = MagicMock()
            mock_plt.cm.get_cmap.return_value = MagicMock()
            mock_plt.cm.ScalarMappable.return_value = MagicMock()
            mock_plt.Normalize.return_value = MagicMock()
            
            viz = visualizer.Visualizer("/path/to/output", None)
            viz.generate_cortex_scatter_plot(results, 'DK40', 'voxel')
            
            # Verify matplotlib calls
            mock_plt.subplots.assert_called_once_with(figsize=(15, 10))
            mock_plt.savefig.assert_called_once()
            mock_plt.close.assert_called_once()
    
    def test_generate_value_distribution_plot_no_matplotlib(self):
        """Test generate_value_distribution_plot when matplotlib is not available."""
        with patch('visualizer.plt', None), \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.Visualizer("/path/to/output", None)
            result = viz.generate_value_distribution_plot(
                np.array([0.1, 0.2, 0.3]), 'region1', 'DK40', 0.2, 0.3, 0.1, 'voxel'
            )
            
            assert result is None
            mock_logger.warning.assert_called_with("matplotlib not available. Cannot generate distribution plot.")
    
    @patch('visualizer.plt')
    def test_generate_value_distribution_plot_success(self, mock_plt):
        """Test successful generation of value distribution plot."""
        field_values = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.join', return_value="/path/to/output/voxel_distribution_region1.png"), \
             patch('os.makedirs'):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Mock matplotlib components
            mock_fig = MagicMock()
            mock_ax1 = MagicMock()
            mock_ax2 = MagicMock()
            mock_plt.subplots.return_value = (mock_fig, [mock_ax1, mock_ax2])
            mock_plt.colorbar.return_value = MagicMock()
            mock_plt.tight_layout.return_value = None
            mock_plt.savefig.return_value = None
            mock_plt.close.return_value = None
            
            viz = visualizer.Visualizer("/path/to/output", None)
            result = viz.generate_value_distribution_plot(
                field_values, 'region1', 'DK40', 0.3, 0.5, 0.1, 'voxel'
            )
            
            assert result == "/path/to/output/voxel_distribution_region1.png"
            mock_plt.subplots.assert_called_once()
            mock_plt.savefig.assert_called_once()
            mock_plt.close.assert_called_once()
    
    def test_generate_focality_histogram_no_matplotlib(self):
        """Test generate_focality_histogram when matplotlib is not available."""
        with patch('visualizer.plt', None), \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.BaseVisualizer("/path/to/output", None)
            result = viz.generate_focality_histogram(
                np.array([0.1, 0.2, 0.3]), np.array([0.1, 0.2]), 
                filename="test", region_name="region1"
            )
            
            assert result is None
            mock_logger.warning.assert_called_with("matplotlib not available. Cannot generate histogram.")
    
    @patch('visualizer.plt')
    def test_generate_focality_histogram_success(self, mock_plt):
        """Test successful generation of focality histogram."""
        whole_head_data = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        roi_data = np.array([0.1, 0.2])
        
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.join', return_value="/path/to/output/region1_whole_head_roi_histogram.png"), \
             patch('os.makedirs'):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Mock matplotlib components
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_plt.subplots.return_value = (mock_fig, mock_ax)
            mock_plt.cm.get_cmap.return_value = MagicMock()
            mock_plt.Normalize.return_value = MagicMock()
            mock_plt.cm.ScalarMappable.return_value = MagicMock()
            mock_plt.colorbar.return_value = MagicMock()
            mock_plt.tight_layout.return_value = None
            mock_plt.savefig.return_value = None
            mock_plt.close.return_value = None
            
            viz = visualizer.BaseVisualizer("/path/to/output", None)
            result = viz.generate_focality_histogram(
                whole_head_data, roi_data, filename="test", region_name="region1"
            )
            
            assert result == "/path/to/output/region1_whole_head_roi_histogram.png"
            mock_plt.subplots.assert_called_once()
            mock_plt.savefig.assert_called_once()
            mock_plt.close.assert_called_once()


class TestMeshVisualizer:
    """Test MeshVisualizer functionality."""
    
    def test_init(self):
        """Test MeshVisualizer initialization."""
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.makedirs'):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.MeshVisualizer("/path/to/output", None)
            
            assert viz.output_dir == "/path/to/output"
            assert viz.logger == mock_logger
    
    def test_visualize_cortex_roi_no_simnibs(self):
        """Test visualize_cortex_roi when simnibs is not available."""
        with patch('visualizer.simnibs', None), \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.MeshVisualizer("/path/to/output", None)
            result = viz.visualize_cortex_roi(
                MagicMock(), np.array([True, False]), 'region1', 
                np.array([0.1, 0.2]), 0.5
            )
            
            assert result is None
            mock_logger.warning.assert_called_with("simnibs not available. Cannot generate mesh visualization.")
    
    @patch('visualizer.simnibs')
    def test_visualize_cortex_roi_success(self, mock_simnibs):
        """Test successful cortex ROI visualization."""
        mock_mesh = MagicMock()
        mock_mesh.nodes.nr = 2
        mock_simnibs.read_msh.return_value = mock_mesh
        
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.join', return_value="/path/to/output/region1_ROI.msh"), \
             patch('os.makedirs'), \
             patch('builtins.open', mock_open()):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.MeshVisualizer("/path/to/output", None)
            result = viz.visualize_cortex_roi(
                MagicMock(), np.array([True, False]), 'region1', 
                np.array([0.1, 0.2]), 0.5, surface_mesh_path="/path/to/mesh.msh"
            )
            
            assert result == "/path/to/output/region1_ROI.msh"
            mock_simnibs.read_msh.assert_called_once_with("/path/to/mesh.msh")
    
    def test_visualize_spherical_roi_no_simnibs(self):
        """Test visualize_spherical_roi when simnibs is not available."""
        with patch('visualizer.simnibs', None), \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.MeshVisualizer("/path/to/output", None)
            result = viz.visualize_spherical_roi(
                MagicMock(), np.array([True, False]), [0, 0, 0], 5.0,
                np.array([0.1, 0.2]), 0.5
            )
            
            assert result is None
            mock_logger.warning.assert_called_with("simnibs not available. Cannot generate mesh visualization.")
    
    @patch('visualizer.simnibs')
    def test_visualize_spherical_roi_success(self, mock_simnibs):
        """Test successful spherical ROI visualization."""
        mock_mesh = MagicMock()
        mock_mesh.nodes.nr = 2
        mock_simnibs.read_msh.return_value = mock_mesh

        # Create a proper mock for gm_surf with nodes attribute
        mock_gm_surf = MagicMock()
        mock_gm_surf.nodes.nr = 2

        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.join', return_value="/path/to/output/sphere_x0.0_y0.0_z0.0_r5.0.msh"), \
             patch('os.makedirs'), \
             patch('builtins.open', mock_open()), \
             patch('os.path.exists', return_value=True), \
             patch('os.path.dirname', return_value="/path/to"), \
             patch('os.path.basename', return_value="mesh.msh"), \
             patch('os.path.splitext', return_value=("mesh", ".msh")):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            viz = visualizer.MeshVisualizer("/path/to/output", None)
            result = viz.visualize_spherical_roi(
                mock_gm_surf, np.array([True, False]), [0, 0, 0], 5.0,
                np.array([0.1, 0.2]), 0.5, surface_mesh_path="/path/to/mesh.msh"
            )

            assert result == "/path/to/output/sphere_x0.0_y0.0_z0.0_r5.0.msh"
            # The function should call read_msh for the normal mesh
            mock_simnibs.read_msh.assert_called()


class TestVoxelVisualizer:
    """Test VoxelVisualizer functionality."""
    
    def test_init(self):
        """Test VoxelVisualizer initialization."""
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.makedirs'):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.VoxelVisualizer("/path/to/output", None)
            
            assert viz.output_dir == "/path/to/output"
            assert viz.logger == mock_logger
    
    def test_create_cortex_nifti_no_nibabel(self):
        """Test create_cortex_nifti when nibabel is not available."""
        with patch('visualizer.nib', None), \
             patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            viz = visualizer.VoxelVisualizer("/path/to/output", None)
            result = viz.create_cortex_nifti(
                MagicMock(), np.array([1, 2]), np.array([0.1, 0.2]), 1, 'region1'
            )

            assert result is None
    
    @patch('visualizer.nib')
    def test_create_cortex_nifti_success(self, mock_nib):
        """Test successful cortex NIfTI creation."""
        mock_atlas_img = MagicMock()
        mock_atlas_img.affine = np.eye(4)
        mock_nifti_img = MagicMock()
        mock_nib.Nifti1Image.return_value = mock_nifti_img

        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.join', return_value="/path/to/output/region1_ROI.nii.gz"), \
             patch('os.makedirs'), \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            viz = visualizer.VoxelVisualizer("/path/to/output", None)
            result = viz.create_cortex_nifti(
                mock_atlas_img, np.array([1, 2]), np.array([0.1, 0.2]), 1, 'region1'
            )

            assert result == "/path/to/output/region1_ROI.nii.gz"
            mock_nib.Nifti1Image.assert_called_once()
            mock_nib.save.assert_called_once_with(mock_nifti_img, "/path/to/output/region1_ROI.nii.gz")
    
    def test_find_region_by_id(self):
        """Test find_region with integer ID."""
        region_info = {1: {'name': 'Region1'}, 2: {'name': 'Region2'}}
        
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.makedirs'):
            viz = visualizer.VoxelVisualizer("/path/to/output", None)
            region_id, region_name = viz.find_region(1, region_info)
            
            assert region_id == 1
            assert region_name == 'Region1'
    
    def test_find_region_by_name(self):
        """Test find_region with string name."""
        region_info = {1: {'name': 'Left-Hippocampus'}, 2: {'name': 'Right-Hippocampus'}}
        
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.makedirs'):
            viz = visualizer.VoxelVisualizer("/path/to/output", None)
            region_id, region_name = viz.find_region('left', region_info)
            
            assert region_id == 1
            assert region_name == 'Left-Hippocampus'
    
    def test_find_region_not_found(self):
        """Test find_region with non-existent region name."""
        region_info = {1: {'name': 'Region1'}, 2: {'name': 'Region2'}}
        
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.makedirs'):
            viz = visualizer.VoxelVisualizer("/path/to/output", None)
            
            with pytest.raises(ValueError, match="Region name 'nonexistent' not found"):
                viz.find_region('nonexistent', region_info)
    
    def test_find_region_no_region_info(self):
        """Test find_region without region info for string lookup."""
        with patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.makedirs'):
            viz = visualizer.VoxelVisualizer("/path/to/output", None)
            
            with pytest.raises(ValueError, match="Region labels are required to look up regions by name"):
                viz.find_region('region1', None)


class TestErrorHandling:
    """Test error handling in various scenarios."""
    
    def test_generate_focality_histogram_empty_data(self):
        """Test generate_focality_histogram with empty data."""
        with patch('visualizer.plt') as mock_plt, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.BaseVisualizer("/path/to/output", None)
            result = viz.generate_focality_histogram(
                np.array([]), np.array([0.1, 0.2]), filename="test"
            )
            
            assert result is None
            mock_logger.warning.assert_called_with("No whole-head data to plot")
    
    def test_generate_cortex_scatter_plot_no_valid_results(self):
        """Test generate_cortex_scatter_plot with no valid results."""
        with patch('visualizer.plt') as mock_plt, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            viz = visualizer.Visualizer("/path/to/output", None)
            viz.generate_cortex_scatter_plot({}, 'DK40', 'voxel')
            
            mock_logger.warning.assert_called_with("No valid results to plot")
    
    def test_generate_value_distribution_plot_empty_values(self):
        """Test generate_value_distribution_plot with empty field values."""
        with patch('visualizer.plt') as mock_plt, \
             patch('visualizer.logging_util.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Mock matplotlib components
            mock_fig = MagicMock()
            mock_ax1 = MagicMock()
            mock_ax2 = MagicMock()
            mock_plt.subplots.return_value = (mock_fig, [mock_ax1, mock_ax2])
            mock_plt.colorbar.return_value = MagicMock()
            mock_plt.tight_layout.return_value = None
            mock_plt.savefig.return_value = None
            mock_plt.close.return_value = None
            
            viz = visualizer.Visualizer("/path/to/output", None)
            result = viz.generate_value_distribution_plot(
                np.array([]), 'region1', 'DK40', 0.3, 0.5, 0.1, 'voxel'
            )

            # Should return None for empty array
            assert result is None


class TestPathHandling:
    """Test path handling and file operations."""
    
    def test_save_results_to_csv_path_construction(self):
        """Test that CSV file paths are constructed correctly."""
        output_dir = "/path/to/output"
        results = {'mean_value': 0.5}

        with patch('os.path.join') as mock_join, \
             patch('builtins.open', mock_open()), \
             patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_join.return_value = "/path/to/output/spherical_region.csv"
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            viz = visualizer.BaseVisualizer(output_dir, None)
            result_path = viz.save_results_to_csv(results, 'spherical', 'region', 'node')

            mock_join.assert_any_call(output_dir, "spherical_region.csv")
            assert result_path == "/path/to/output/spherical_region.csv"
    
    def test_save_whole_head_results_to_csv_path_construction(self):
        """Test that whole head CSV file paths are constructed correctly."""
        output_dir = "/path/to/output"
        results = {'region1': {'mean_value': 0.5}}

        with patch('os.path.join') as mock_join, \
             patch('builtins.open', mock_open()), \
             patch('visualizer.logging_util.get_logger') as mock_get_logger, \
             patch('os.path.basename', return_value="output"), \
             patch('time.strftime', return_value="20250101_120000"):
            mock_join.return_value = "/path/to/output/whole_head_DK40_summary.csv"
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            viz = visualizer.BaseVisualizer(output_dir, None)
            result_path = viz.save_whole_head_results_to_csv(results, 'DK40', 'voxel')

            mock_join.assert_any_call(output_dir, "whole_head_DK40_summary.csv")
            assert result_path == "/path/to/output/whole_head_DK40_summary.csv"


if __name__ == "__main__":
    pytest.main([__file__])
