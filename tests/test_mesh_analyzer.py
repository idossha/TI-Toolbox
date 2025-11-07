#!/usr/bin/env simnibs_python

"""
Comprehensive pytest tests for mesh_analyzer.py

This module tests all the functionality in the mesh analyzer including:
- MeshAnalyzer class initialization
- Surface mesh generation
- Spherical ROI analysis
- Cortical analysis (single region and whole head)
- Normal field value extraction
- Focality metrics calculation
- Grey matter statistics
- Error handling and edge cases
"""

import os
import sys
import pytest
import tempfile
import subprocess
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call, mock_open
from io import StringIO

# Add ti-toolbox directory to path
project_root = str(Path(__file__).resolve().parent.parent)
ti_toolbox_dir = str(Path(project_root) / 'ti-toolbox')
sys.path.insert(0, ti_toolbox_dir)

# Mock external dependencies before importing mesh_analyzer
from unittest.mock import MagicMock

# Mock simnibs
mock_simnibs = MagicMock()
mock_simnibs.read_msh = MagicMock()
mock_simnibs.subject_atlas = MagicMock()

# Mock matplotlib
mock_plt = MagicMock()

# Mock visualizer
mock_visualizer = MagicMock()

# Mock logging_util
mock_logging_util = MagicMock()

# Apply mocks
sys.modules['simnibs'] = mock_simnibs
sys.modules['matplotlib.pyplot'] = mock_plt
sys.modules['visualizer'] = MagicMock()
sys.modules['visualizer'].MeshVisualizer = mock_visualizer
sys.modules['tools'] = MagicMock()
sys.modules['tools'].logging_util = mock_logging_util

# Now import the mesh_analyzer module
from analyzer.mesh_analyzer import MeshAnalyzer


class TestMeshAnalyzerInitialization:
    """Test MeshAnalyzer class initialization"""
    
    def test_init_with_logger(self):
        """Test initialization with provided logger"""
        mock_logger = MagicMock()
        mock_logger.getChild.return_value = mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=mock_logger
                )
        
        assert analyzer.field_mesh_path == "/path/to/field.msh"
        assert analyzer.field_name == "TI_max"
        assert analyzer.subject_dir == "/path/to/m2m_subject"
        assert analyzer.output_dir == "/path/to/output"
        assert analyzer.logger == mock_logger
        # getChild is called for 'mesh_analyzer' and 'visualizer'
        assert mock_logger.getChild.call_count >= 1
        assert any(call[0][0] == 'mesh_analyzer' for call in mock_logger.getChild.call_args_list)
    
    def test_init_without_logger(self):
        """Test initialization without logger (creates its own)"""
        mock_logger_instance = MagicMock()
        mock_logging_util.get_logger.return_value = mock_logger_instance
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                with patch('time.strftime', return_value='20240101_120000'):
                    analyzer = MeshAnalyzer(
                        field_mesh_path="/path/to/field.msh",
                        field_name="TI_max",
                        subject_dir="/path/to/m2m_subject",
                        output_dir="/path/to/output"
                    )
        
        assert analyzer.logger == mock_logger_instance
        mock_logging_util.get_logger.assert_called_once()
    
    def test_init_field_mesh_not_found(self):
        """Test initialization with non-existent field mesh file"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path != "/nonexistent/field.msh"
            with patch('os.makedirs'):
                with pytest.raises(FileNotFoundError, match="Field mesh file not found"):
                    MeshAnalyzer(
                        field_mesh_path="/nonexistent/field.msh",
                        field_name="TI_max",
                        subject_dir="/path/to/m2m_subject",
                        output_dir="/path/to/output"
                    )
    
    def test_init_creates_output_directory(self):
        """Test that initialization creates output directory if it doesn't exist"""
        mock_logger = MagicMock()
        mock_logger.getChild.return_value = mock_logger
        
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path != "/path/to/output"
            with patch('os.makedirs') as mock_makedirs:
                analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=mock_logger
                )
        
        # makedirs may be called multiple times for output directory and subdirectories
        assert mock_makedirs.call_count >= 1
        assert any("/path/to/output" in str(call) for call in mock_makedirs.call_args_list)


class TestSurfaceMeshGeneration:
    """Test surface mesh generation functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        # Use os.path.join to create proper paths for the current OS
        field_mesh_path = os.path.join("mnt", "project", "derivatives", "SimNIBS", "sub-001", "Simulations", "test_montage", "TI", "mesh", "test_field_TI.msh")
        subject_dir = os.path.join("mnt", "project", "derivatives", "SimNIBS", "sub-001", "m2m_001")
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = MeshAnalyzer(
                    field_mesh_path=field_mesh_path,
                    field_name="TI_max",
                    subject_dir=subject_dir,
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_generate_surface_mesh_existing_file(self):
        """Test surface mesh generation when file already exists"""
        expected_path = os.path.join("mnt", "project", "derivatives", "SimNIBS", "sub-001", "Simulations", "test_montage", "TI", "mesh", "test_field_TI_central.msh")
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                result = self.analyzer._generate_surface_mesh()
        
        assert result == expected_path
        assert self.analyzer._surface_mesh_path == expected_path
        self.mock_logger.debug.assert_called_with(f"Using existing surface mesh at: {expected_path}")
    
    def test_generate_surface_mesh_new_file(self):
        """Test surface mesh generation when file doesn't exist"""
        expected_path = os.path.join("mnt", "project", "derivatives", "SimNIBS", "sub-001", "Simulations", "test_montage", "TI", "mesh", "test_field_TI_central.msh")
        
        with patch('os.path.exists') as mock_exists:
            # First call returns False (file doesn't exist), second call returns True (file created)
            mock_exists.side_effect = [False, True]
            with patch('subprocess.run') as mock_run:
                with patch('os.makedirs'):
                    result = self.analyzer._generate_surface_mesh()
        
        assert result == expected_path
        assert self.analyzer._surface_mesh_path == expected_path
        mock_run.assert_called_once()
        self.mock_logger.info.assert_called_with("Generating surface mesh for specific field: test_field_TI.msh using msh2cortex...")

    def test_generate_surface_mesh_invalid_field_extension(self):
        """Reject unsupported field mesh extension"""
        self.analyzer.field_mesh_path = "/path/to/field.unsupported"
        with pytest.raises(ValueError):
            self.analyzer._generate_surface_mesh()
    
    def test_generate_surface_mesh_mti_simulation(self):
        """Test surface mesh generation for mTI simulation"""
        # Update analyzer for mTI simulation
        mti_field_path = os.path.join("mnt", "project", "derivatives", "SimNIBS", "sub-001", "Simulations", "test_montage", "mTI", "mesh", "test_field_mTI.msh")
        self.analyzer.field_mesh_path = mti_field_path
        
        expected_path = os.path.join("mnt", "project", "derivatives", "SimNIBS", "sub-001", "Simulations", "test_montage", "mTI", "mesh", "test_field_mTI_central.msh")
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                result = self.analyzer._generate_surface_mesh()
        
        assert result == expected_path
    
    def test_generate_surface_mesh_subprocess_error(self):
        """Test surface mesh generation with subprocess error"""
        # Create a proper mock exception with bytes for stdout/stderr
        mock_exception = subprocess.CalledProcessError(1, 'msh2cortex')
        mock_exception.stdout = b'error output'
        mock_exception.stderr = b'error details'
        
        with patch('os.path.exists', return_value=False):
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = mock_exception
                with patch('os.makedirs'):
                    with pytest.raises(RuntimeError, match="Failed to generate surface mesh using msh2cortex"):
                        self.analyzer._generate_surface_mesh()
    
    def test_generate_surface_mesh_invalid_path_structure(self):
        """Test surface mesh generation with invalid path structure"""
        # Update analyzer with invalid path
        self.analyzer.field_mesh_path = "/invalid/path/field.msh"
        
        with pytest.raises(ValueError, match="Could not determine simulation name from field mesh path"):
            self.analyzer._generate_surface_mesh()


class TestNormalFieldExtraction:
    """Test TI_normal field value extraction"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field_TI.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    
    def test_extract_normal_field_values_file_not_found(self):
        """Test normal field extraction when file doesn't exist"""
        with patch('os.path.exists', return_value=False):
            result_values, result_stats = self.analyzer._extract_normal_field_values(np.array([True, False]))
        
        assert result_values is None
        assert result_stats is None
        self.mock_logger.warning.assert_called()
    
    def test_extract_normal_field_values_success(self):
        """Test successful normal field extraction"""
        # Mock mesh data
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_normal': MagicMock()}
        mock_mesh.field['TI_normal'].value = np.array([1.0, 2.0, 3.0, 0.0])
        mock_mesh.nodes_areas.return_value = np.array([0.1, 0.2, 0.3, 0.4])
        
        roi_mask = np.array([True, True, False, True])
        
        with patch('os.path.exists', return_value=True):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                result_values, result_stats = self.analyzer._extract_normal_field_values(roi_mask)
        
        assert result_values is not None
        assert result_stats is not None
        assert 'normal_mean_value' in result_stats
        assert 'normal_max_value' in result_stats
        assert 'normal_min_value' in result_stats
        assert 'normal_focality' in result_stats
    
    def test_extract_normal_field_values_no_ti_normal_field(self):
        """Test normal field extraction when TI_normal field doesn't exist"""
        mock_mesh = MagicMock()
        mock_mesh.field = {'other_field': MagicMock()}
        
        roi_mask = np.array([True, False])
        
        with patch('os.path.exists', return_value=True):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                result_values, result_stats = self.analyzer._extract_normal_field_values(roi_mask)
        
        assert result_values is None
        assert result_stats is None
        self.mock_logger.warning.assert_called()


class TestSphericalAnalysis:
    """Test spherical ROI analysis functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_analyze_sphere_success(self):
        """Test successful spherical analysis"""
        # Mock surface mesh data
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([1.0, 2.0, 3.0, 0.0, 5.0])
        mock_mesh.nodes.node_coord = np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4]])
        mock_mesh.nodes_areas.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                with patch.object(self.analyzer, '_extract_normal_field_values', return_value=(None, None)):
                    with patch.object(self.analyzer, '_calculate_focality_metrics', return_value=None):
                        with patch.object(self.analyzer.visualizer, 'save_results_to_csv'):
                            with patch.object(self.analyzer.visualizer, 'save_extra_info_to_csv'):
                                result = self.analyzer.analyze_sphere(
                                    center_coordinates=[1, 1, 1],
                                    radius=2.0,
                                    visualize=False
                                )
        
        assert result is not None
        assert 'mean_value' in result
        assert 'max_value' in result
        assert 'min_value' in result
        assert 'focality' in result
        assert 'nodes_in_roi' in result
    
    def test_analyze_sphere_no_nodes_in_roi(self):
        """Test spherical analysis with no nodes in ROI"""
        # Mock surface mesh data with nodes far from center
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([1.0, 2.0, 3.0])
        mock_mesh.nodes.node_coord = np.array([[100, 100, 100], [200, 200, 200], [300, 300, 300]])
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                result = self.analyzer.analyze_sphere(
                    center_coordinates=[1, 1, 1],
                    radius=1.0,
                    visualize=False
                )
        
        assert result is None
        self.mock_logger.error.assert_called()
    
    def test_analyze_sphere_no_positive_values(self):
        """Test spherical analysis with no positive values in ROI"""
        # Mock surface mesh data with all negative values
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([-1.0, -2.0, -3.0])
        mock_mesh.nodes.node_coord = np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]])
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                result = self.analyzer.analyze_sphere(
                    center_coordinates=[1, 1, 1],
                    radius=2.0,
                    visualize=False
                )
        
        assert result is None
        self.mock_logger.warning.assert_called()
    
    def test_analyze_sphere_field_not_found(self):
        """Test spherical analysis when field doesn't exist"""
        mock_mesh = MagicMock()
        mock_mesh.field = {'other_field': MagicMock()}
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                with pytest.raises(ValueError, match="Field 'TI_max' not found"):
                    self.analyzer.analyze_sphere(
                        center_coordinates=[1, 1, 1],
                        radius=2.0,
                        visualize=False
                    )


class TestCorticalAnalysis:
    """Test cortical analysis functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_analyze_cortex_success(self):
        """Test successful cortical analysis"""
        # Mock surface mesh data
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([1.0, 2.0, 3.0, 0.0, 5.0])
        mock_mesh.nodes_areas.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        
        # Mock atlas data
        mock_atlas = {'region1': np.array([True, True, False, True, False])}
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                with patch('simnibs.subject_atlas', return_value=mock_atlas):
                    with patch.object(self.analyzer, '_extract_normal_field_values', return_value=(None, None)):
                        with patch.object(self.analyzer, '_calculate_focality_metrics', return_value=None):
                            with patch.object(self.analyzer.visualizer, 'save_results_to_csv'):
                                with patch.object(self.analyzer.visualizer, 'save_extra_info_to_csv'):
                                    result = self.analyzer.analyze_cortex(
                                        atlas_type="DK40",
                                        target_region="region1",
                                        visualize=False
                                    )
        
        assert result is not None
        assert 'mean_value' in result
        assert 'max_value' in result
        assert 'min_value' in result
        assert 'focality' in result
    
    def test_analyze_cortex_region_not_found(self):
        """Test cortical analysis with region not in atlas"""
        mock_atlas = {'region1': np.array([True, False])}
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=MagicMock()):
                with patch('simnibs.subject_atlas', return_value=mock_atlas):
                    with pytest.raises(ValueError, match="Region 'nonexistent' not found"):
                        self.analyzer.analyze_cortex(
                            atlas_type="DK40",
                            target_region="nonexistent",
                            visualize=False
                        )
    
    def test_analyze_cortex_no_nodes_in_roi(self):
        """Test cortical analysis with no nodes in ROI"""
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([1.0, 2.0, 3.0])
        mock_mesh.nodes_areas.return_value = np.array([0.1, 0.2, 0.3])
        
        # Mock atlas with empty ROI
        mock_atlas = {'region1': np.array([False, False, False])}
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                with patch('simnibs.subject_atlas', return_value=mock_atlas):
                    with patch.object(self.analyzer.visualizer, 'save_results_to_csv'):
                        result = self.analyzer.analyze_cortex(
                            atlas_type="DK40",
                            target_region="region1",
                            visualize=False
                        )
        
        assert result is not None
        assert result['mean_value'] is None
        assert result['max_value'] is None
        assert result['min_value'] is None
        assert result['focality'] is None


class TestWholeHeadAnalysis:
    """Test whole head analysis functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_analyze_whole_head_success(self):
        """Test successful whole head analysis"""
        # Mock surface mesh data
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([1.0, 2.0, 3.0, 0.0, 5.0])
        mock_mesh.nodes_areas.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        
        # Mock atlas data with multiple regions
        mock_atlas = {
            'region1': np.array([True, True, False, True, False]),
            'region2': np.array([False, False, True, False, True])
        }
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                with patch('simnibs.subject_atlas', return_value=mock_atlas):
                    with patch.object(self.analyzer, '_extract_normal_field_values', return_value=(None, None)):
                        with patch.object(self.analyzer.visualizer, 'save_whole_head_results_to_csv'):
                            result = self.analyzer.analyze_whole_head(
                                atlas_type="DK40",
                                visualize=False
                            )
        
        assert result is not None
        assert 'region1' in result
        assert 'region2' in result
        assert 'mean_value' in result['region1']
        assert 'mean_value' in result['region2']
    
    def test_analyze_whole_head_empty_region(self):
        """Test whole head analysis with empty region"""
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([1.0, 2.0, 3.0])
        mock_mesh.nodes_areas.return_value = np.array([0.1, 0.2, 0.3])
        
        # Mock atlas with one empty region
        mock_atlas = {
            'region1': np.array([True, True, False]),
            'empty_region': np.array([False, False, False])
        }
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                with patch('simnibs.subject_atlas', return_value=mock_atlas):
                    with patch.object(self.analyzer, '_extract_normal_field_values', return_value=(None, None)):
                        with patch.object(self.analyzer.visualizer, 'save_whole_head_results_to_csv'):
                            result = self.analyzer.analyze_whole_head(
                                atlas_type="DK40",
                                visualize=False
                            )
        
        assert result is not None
        assert 'region1' in result
        assert 'empty_region' in result
        assert result['empty_region']['mean_value'] is None


class TestFocalityMetrics:
    """Test focality metrics calculation"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_calculate_focality_metrics_success(self):
        """Test successful focality metrics calculation"""
        field_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        element_sizes = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        region_name = "test_region"
        
        result = self.analyzer._calculate_focality_metrics(field_data, element_sizes, region_name)
        
        assert result is not None
        assert 'region_name' in result
        assert 'field_name' in result
        assert 'max_value' in result
        assert 'min_value' in result
        assert 'percentile_95' in result
        assert 'percentile_99' in result
        assert 'percentile_99_9' in result
        assert 'focality_50' in result
        assert 'focality_75' in result
        assert 'focality_90' in result
        assert 'focality_95' in result
        assert 'total_area_cm2' in result
        assert 'num_elements' in result
    
    def test_calculate_focality_metrics_empty_data(self):
        """Test focality metrics calculation with empty data"""
        field_data = np.array([])
        element_sizes = np.array([])
        region_name = "test_region"
        
        result = self.analyzer._calculate_focality_metrics(field_data, element_sizes, region_name)
        
        assert result is None
        self.mock_logger.warning.assert_called()
    
    def test_calculate_focality_metrics_nan_values(self):
        """Test focality metrics calculation with NaN values"""
        field_data = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
        element_sizes = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        region_name = "test_region"
        
        result = self.analyzer._calculate_focality_metrics(field_data, element_sizes, region_name)
        
        assert result is not None
        assert result['num_elements'] == 4  # Should exclude NaN values


class TestGreyMatterStatistics:
    """Test grey matter statistics calculation"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_get_grey_matter_statistics_success(self):
        """Test successful grey matter statistics calculation"""
        # Mock surface mesh data
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([1.0, 2.0, 3.0, 0.0, 5.0])
        mock_mesh.nodes_areas.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                result = self.analyzer.get_grey_matter_statistics()
        
        assert result is not None
        assert 'grey_mean' in result
        assert 'grey_max' in result
        assert 'grey_min' in result
        assert result['grey_mean'] > 0
        assert result['grey_max'] > 0
        assert result['grey_min'] > 0
    
    def test_get_grey_matter_statistics_no_positive_values(self):
        """Test grey matter statistics with no positive values"""
        mock_mesh = MagicMock()
        mock_mesh.field = {'TI_max': MagicMock()}
        mock_mesh.field['TI_max'].value = np.array([-1.0, -2.0, -3.0])
        mock_mesh.nodes_areas.return_value = np.array([0.1, 0.2, 0.3])
        
        with patch.object(self.analyzer, '_generate_surface_mesh', return_value="/path/to/surface.msh"):
            with patch('simnibs.read_msh', return_value=mock_mesh):
                result = self.analyzer.get_grey_matter_statistics()
        
        assert result is not None
        assert result['grey_mean'] == 0.0
        assert result['grey_max'] == 0.0
        assert result['grey_min'] == 0.0
        self.mock_logger.warning.assert_called()
    
    def test_get_grey_matter_statistics_fallback_to_original_mesh(self):
        """Test grey matter statistics fallback to original mesh"""
        # Mock surface mesh generation failure
        with patch.object(self.analyzer, '_generate_surface_mesh', side_effect=Exception("Surface generation failed")):
            # Mock original mesh data
            mock_original_mesh = MagicMock()
            mock_original_mesh.field = {'TI_max': MagicMock()}
            mock_original_mesh.field['TI_max'].value = np.array([1.0, 2.0, 3.0, 0.0, 5.0])
            
            with patch('simnibs.read_msh', return_value=mock_original_mesh):
                result = self.analyzer.get_grey_matter_statistics()
        
        assert result is not None
        assert 'grey_mean' in result
        assert 'grey_max' in result
        assert 'grey_min' in result
        # Check that the fallback message was logged (it should be the first info call)
        info_calls = [call for call in self.mock_logger.info.call_args_list if "Falling back to original mesh" in str(call)]
        assert len(info_calls) > 0


class TestCleanup:
    """Test cleanup functionality"""
    
    def test_destructor_cleanup(self):
        """Test that destructor cleans up temporary directory"""
        mock_logger = MagicMock()
        mock_logger.getChild.return_value = mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                analyzer = MeshAnalyzer(
                    field_mesh_path="/path/to/field.msh",
                    field_name="TI_max",
                    subject_dir="/path/to/m2m_subject",
                    output_dir="/path/to/output",
                    logger=mock_logger
                )
        
        # Set up a mock temporary directory
        mock_temp_dir = MagicMock()
        analyzer._temp_dir = mock_temp_dir
        
        # Call destructor
        analyzer.__del__()
        
        # Verify cleanup was called
        mock_temp_dir.cleanup.assert_called_once()
        mock_logger.info.assert_called_with("Cleaning up temporary directory...")


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v"])
