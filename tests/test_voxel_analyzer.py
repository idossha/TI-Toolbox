#!/usr/bin/env python3

"""
Comprehensive pytest tests for voxel_analyzer.py

This module tests all the functionality in the voxel analyzer including:
- VoxelAnalyzer class initialization
- Spherical ROI analysis
- Cortical analysis (single region and whole head)
- Atlas region extraction and processing
- Image resampling functionality
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

# Add project root to path
project_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, project_root)

# Mock external dependencies before importing voxel_analyzer
from unittest.mock import MagicMock

# Mock nibabel
mock_nib = MagicMock()
mock_nib.load = MagicMock()
mock_nib.Nifti1Image = MagicMock()

# Mock matplotlib
mock_plt = MagicMock()

# Mock visualizer
mock_visualizer = MagicMock()

# Mock logging_util
mock_logging_util = MagicMock()

# Apply mocks
sys.modules['nibabel'] = mock_nib
sys.modules['matplotlib'] = MagicMock()
sys.modules['matplotlib.pyplot'] = mock_plt
sys.modules['visualizer'] = MagicMock()
sys.modules['visualizer'].VoxelVisualizer = mock_visualizer
sys.modules['tools'] = MagicMock()
sys.modules['tools'].logging_util = mock_logging_util

# Now import the voxel_analyzer module
from analyzer.voxel_analyzer import VoxelAnalyzer


class TestVoxelAnalyzerInitialization:
    """Test VoxelAnalyzer class initialization"""
    
    def test_init_with_logger(self):
        """Test initialization with provided logger"""
        mock_logger = MagicMock()
        mock_logger.getChild.return_value = mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=mock_logger
                )
        
        assert analyzer.field_nifti == "/path/to/field.nii.gz"
        assert analyzer.subject_dir == "/path/to/subject"
        assert analyzer.output_dir == "/path/to/output"
        assert analyzer.logger == mock_logger
        mock_logger.getChild.assert_called_once_with('voxel_analyzer')
    
    def test_init_without_logger(self):
        """Test initialization without logger (creates its own)"""
        mock_logger_instance = MagicMock()
        mock_logging_util.get_logger.return_value = mock_logger_instance
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                with patch('time.strftime', return_value='20240101_120000'):
                    analyzer = VoxelAnalyzer(
                        field_nifti="/path/to/field.nii.gz",
                        subject_dir="/path/to/subject",
                        output_dir="/path/to/output"
                    )
        
        assert analyzer.logger == mock_logger_instance
        mock_logging_util.get_logger.assert_called_once()
    
    def test_init_field_nifti_not_found(self):
        """Test initialization with non-existent field NIfTI file"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path != "/nonexistent/field.nii.gz"
            with patch('os.makedirs'):
                with pytest.raises(FileNotFoundError, match="Field file not found"):
                    VoxelAnalyzer(
                        field_nifti="/nonexistent/field.nii.gz",
                        subject_dir="/path/to/subject",
                        output_dir="/path/to/output"
                    )
    
    def test_init_creates_output_directory(self):
        """Test that initialization creates output directory if it doesn't exist"""
        mock_logger = MagicMock()
        mock_logger.getChild.return_value = mock_logger
        
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path != "/path/to/output"
            with patch('os.makedirs') as mock_makedirs:
                analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=mock_logger
                )
        
        mock_makedirs.assert_called_once_with("/path/to/output")
    
    def test_init_with_quiet_mode(self):
        """Test initialization with quiet mode enabled"""
        mock_logger = MagicMock()
        mock_logger.getChild.return_value = mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=mock_logger,
                    quiet=True
                )
        
        assert analyzer.quiet is True


class TestAtlasTypeExtraction:
    """Test atlas type extraction functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_extract_atlas_type_dk40(self):
        """Test DK40 atlas type extraction"""
        result = self.analyzer._extract_atlas_type("/path/to/subject_dk40.mgz")
        assert result == "DK40"
    
    def test_extract_atlas_type_dkt(self):
        """Test DKT atlas type extraction"""
        result = self.analyzer._extract_atlas_type("/path/to/subject_dkt.mgz")
        assert result == "DKT"
    
    def test_extract_atlas_type_hcp_mmp1(self):
        """Test HCP_MMP1 atlas type extraction"""
        result = self.analyzer._extract_atlas_type("/path/to/subject_hcp_mmp1.mgz")
        assert result == "HCP_MMP1"
    
    def test_extract_atlas_type_a2009s(self):
        """Test a2009s atlas type extraction"""
        result = self.analyzer._extract_atlas_type("/path/to/subject_a2009s.mgz")
        assert result == "a2009s"
    
    def test_extract_atlas_type_custom(self):
        """Test custom atlas type extraction"""
        result = self.analyzer._extract_atlas_type("/path/to/custom_atlas.mgz")
        assert result == "custom"

    def test_extract_atlas_type_unknown(self):
        """Unknown pattern returns 'custom'"""
        result = self.analyzer._extract_atlas_type("/path/to/subject_unknown.mgz")
        assert result in ("custom", "unknown")


class TestSphericalAnalysis:
    """Test spherical ROI analysis functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_analyze_sphere_success(self):
        """Test successful spherical analysis"""
        # Mock NIfTI data
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.array([[[1.0, 2.0, 3.0], [0.0, 5.0, 6.0]]])
        mock_img.header.get_zooms.return_value = [1.0, 1.0, 1.0]
        mock_img.affine = np.eye(4)
        
        mock_nib.load.return_value = mock_img
        
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
        assert 'voxels_in_roi' in result
    
    def test_analyze_sphere_no_voxels_in_roi(self):
        """Test spherical analysis with no voxels in ROI"""
        # Mock NIfTI data with all zeros
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.zeros((10, 10, 10))
        mock_img.header.get_zooms.return_value = [1.0, 1.0, 1.0]
        mock_img.affine = np.eye(4)
        
        mock_nib.load.return_value = mock_img
        
        result = self.analyzer.analyze_sphere(
            center_coordinates=[1, 1, 1],
            radius=1.0,
            visualize=False
        )
        
        assert result is None
        self.mock_logger.warning.assert_called()
    
    def test_analyze_sphere_4d_data(self):
        """Test spherical analysis with 4D data"""
        # Mock 4D NIfTI data
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.array([[[[1.0, 2.0, 3.0], [0.0, 5.0, 6.0]]]])
        mock_img.header.get_zooms.return_value = [1.0, 1.0, 1.0, 1.0]
        mock_img.affine = np.eye(4)
        
        mock_nib.load.return_value = mock_img
        
        with patch.object(self.analyzer, '_calculate_focality_metrics', return_value=None):
            with patch.object(self.analyzer.visualizer, 'save_results_to_csv'):
                with patch.object(self.analyzer.visualizer, 'save_extra_info_to_csv'):
                    result = self.analyzer.analyze_sphere(
                        center_coordinates=[1, 1, 1],
                        radius=2.0,
                        visualize=False
                    )
        
        assert result is not None
        # Should extract first volume from 4D data
        mock_img.get_fdata.assert_called_once()


class TestCorticalAnalysis:
    """Test cortical analysis functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_analyze_cortex_success(self):
        """Test successful cortical analysis"""
        # Mock atlas and field data
        mock_atlas_img = MagicMock()
        mock_atlas_arr = np.array([[[1, 1, 0], [0, 0, 0]]])
        mock_field_img = MagicMock()
        mock_field_arr = np.array([[[1.0, 2.0, 0.0], [0.0, 5.0, 6.0]]])
        
        # Mock region info
        region_info = {1: {'name': 'TestRegion', 'voxel_count': 100, 'color': (0.5, 0.5, 0.5)}}
        
        with patch.object(self.analyzer, 'load_brain_image', side_effect=[(mock_atlas_img, mock_atlas_arr), (mock_field_img, mock_field_arr)]):
            with patch.object(self.analyzer, 'get_atlas_regions', return_value=region_info):
                with patch.object(self.analyzer, 'find_region', return_value=(1, 'TestRegion')):
                    with patch.object(self.analyzer, '_calculate_focality_metrics', return_value=None):
                        with patch.object(self.analyzer.visualizer, 'save_results_to_csv'):
                            with patch.object(self.analyzer.visualizer, 'save_extra_info_to_csv'):
                                result = self.analyzer.analyze_cortex(
                                    atlas_file="/path/to/atlas.mgz",
                                    target_region="TestRegion",
                                    visualize=False
                                )
        
        assert result is not None
        assert 'mean_value' in result
        assert 'max_value' in result
        assert 'min_value' in result
        assert 'focality' in result
        assert 'voxels_in_roi' in result
    
    def test_analyze_cortex_no_voxels_in_region(self):
        """Test cortical analysis with no voxels in region"""
        # Mock atlas and field data
        mock_atlas_img = MagicMock()
        mock_atlas_arr = np.zeros((10, 10, 10))
        mock_field_img = MagicMock()
        mock_field_arr = np.ones((10, 10, 10))
        
        # Mock region info
        region_info = {1: {'name': 'TestRegion', 'voxel_count': 0, 'color': (0.5, 0.5, 0.5)}}
        
        with patch.object(self.analyzer, 'load_brain_image', side_effect=[(mock_atlas_img, mock_atlas_arr), (mock_field_img, mock_field_arr)]):
            with patch.object(self.analyzer, 'get_atlas_regions', return_value=region_info):
                with patch.object(self.analyzer, 'find_region', return_value=(1, 'TestRegion')):
                    with patch.object(self.analyzer.visualizer, 'save_results_to_csv'):
                        result = self.analyzer.analyze_cortex(
                            atlas_file="/path/to/atlas.mgz",
                            target_region="TestRegion",
                            visualize=False
                        )
        
        assert result is not None
        assert result['mean_value'] is None
        assert result['max_value'] is None
        assert result['min_value'] is None
        assert result['focality'] is None
        self.mock_logger.warning.assert_called()
    
    def test_analyze_cortex_no_positive_values(self):
        """Test cortical analysis with no positive values in region"""
        # Mock atlas and field data
        mock_atlas_img = MagicMock()
        mock_atlas_arr = np.array([[[1, 1, 0], [0, 0, 0]]])
        mock_field_img = MagicMock()
        mock_field_arr = np.array([[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]])  # All zeros
        
        # Mock region info
        region_info = {1: {'name': 'TestRegion', 'voxel_count': 100, 'color': (0.5, 0.5, 0.5)}}
        
        with patch.object(self.analyzer, 'load_brain_image', side_effect=[(mock_atlas_img, mock_atlas_arr), (mock_field_img, mock_field_arr)]):
            with patch.object(self.analyzer, 'get_atlas_regions', return_value=region_info):
                with patch.object(self.analyzer, 'find_region', return_value=(1, 'TestRegion')):
                    with patch.object(self.analyzer.visualizer, 'save_results_to_csv'):
                        result = self.analyzer.analyze_cortex(
                            atlas_file="/path/to/atlas.mgz",
                            target_region="TestRegion",
                            visualize=False
                        )
        
        assert result is not None
        assert result['mean_value'] is None
        assert result['max_value'] is None
        assert result['min_value'] is None
        assert result['focality'] is None
        self.mock_logger.warning.assert_called()


class TestWholeHeadAnalysis:
    """Test whole head analysis functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_analyze_whole_head_success(self):
        """Test successful whole head analysis"""
        # Mock atlas and field data
        mock_atlas_img = MagicMock()
        mock_atlas_arr = np.array([[[1, 2, 0], [0, 0, 0]]])
        mock_field_img = MagicMock()
        mock_field_arr = np.array([[[1.0, 2.0, 0.0], [0.0, 5.0, 6.0]]])
        
        # Mock region info
        region_info = {
            1: {'name': 'Region1', 'voxel_count': 100, 'color': (0.5, 0.5, 0.5)},
            2: {'name': 'Region2', 'voxel_count': 200, 'color': (0.7, 0.7, 0.7)}
        }
        
        with patch.object(self.analyzer, 'load_brain_image', side_effect=[(mock_atlas_img, mock_atlas_arr), (mock_field_img, mock_field_arr)]):
            with patch.object(self.analyzer, 'get_atlas_regions', return_value=region_info):
                with patch.object(self.analyzer.visualizer, 'save_whole_head_results_to_csv'):
                    result = self.analyzer.analyze_whole_head(
                        atlas_file="/path/to/atlas.mgz",
                        visualize=False
                    )
        
        assert result is not None
        assert 'Region1' in result
        assert 'Region2' in result
        assert 'mean_value' in result['Region1']
        assert 'mean_value' in result['Region2']
    
    def test_analyze_whole_head_empty_region(self):
        """Test whole head analysis with empty region"""
        # Mock atlas and field data
        mock_atlas_img = MagicMock()
        mock_atlas_arr = np.array([[[1, 0, 0], [0, 0, 0]]])
        mock_field_img = MagicMock()
        mock_field_arr = np.array([[[1.0, 0.0, 0.0], [0.0, 0.0, 0.0]]])
        
        # Mock region info with one empty region
        region_info = {
            1: {'name': 'Region1', 'voxel_count': 100, 'color': (0.5, 0.5, 0.5)},
            2: {'name': 'EmptyRegion', 'voxel_count': 0, 'color': (0.7, 0.7, 0.7)}
        }
        
        with patch.object(self.analyzer, 'load_brain_image', side_effect=[(mock_atlas_img, mock_atlas_arr), (mock_field_img, mock_field_arr)]):
            with patch.object(self.analyzer, 'get_atlas_regions', return_value=region_info):
                with patch.object(self.analyzer.visualizer, 'save_whole_head_results_to_csv'):
                    result = self.analyzer.analyze_whole_head(
                        atlas_file="/path/to/atlas.mgz",
                        visualize=False
                    )
        
        assert result is not None
        assert 'Region1' in result
        assert 'EmptyRegion' in result
        assert result['EmptyRegion']['mean_value'] is None


class TestAtlasRegionExtraction:
    """Test atlas region extraction functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_get_atlas_regions_success(self):
        """Test successful atlas region extraction"""
        # Mock labels file content
        labels_content = """# Header line
# Another header line
1 1 100 1000.0 Region1
2 2 200 2000.0 Region2
"""
        
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=labels_content)):
                result = self.analyzer.get_atlas_regions("/path/to/atlas.mgz")
        
        assert result is not None
        assert 1 in result
        assert 2 in result
        assert result[1]['name'] == 'Region1'
        assert result[2]['name'] == 'Region2'
        assert result[1]['voxel_count'] == 100
        assert result[2]['voxel_count'] == 200
    
    def test_get_atlas_regions_file_not_found(self):
        """Test atlas region extraction when labels file doesn't exist"""
        with patch('os.path.exists', return_value=False):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock()
                result = self.analyzer.get_atlas_regions("/path/to/atlas.mgz")
        
        assert result == {}
        mock_run.assert_called_once()
    
    def test_get_atlas_regions_subprocess_error(self):
        """Test atlas region extraction with subprocess error"""
        # Create a proper mock exception with bytes for stdout/stderr
        mock_exception = subprocess.CalledProcessError(1, 'mri_segstats')
        mock_exception.stdout = b'error output'
        mock_exception.stderr = b'error details'
        
        with patch('os.path.exists', return_value=False):
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = mock_exception
                result = self.analyzer.get_atlas_regions("/path/to/atlas.mgz")
        
        assert result == {}
        self.mock_logger.warning.assert_called()


class TestImageResampling:
    """Test image resampling functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_resample_to_match_success(self):
        """Test successful image resampling"""
        # Mock source image
        mock_source_img = MagicMock()
        mock_source_img.shape = (64, 64, 64)
        
        # Mock resampled image
        mock_resampled_img = MagicMock()
        mock_resampled_data = np.zeros((128, 128, 128))
        mock_resampled_img.get_fdata.return_value = mock_resampled_data
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_temp.return_value.__enter__.return_value.name = "/tmp/temp.nii.gz"
            with patch('subprocess.run') as mock_run:
                with patch('nibabel.load', return_value=mock_resampled_img):
                    with patch('os.unlink'):
                        result_img, result_data = self.analyzer.resample_to_match(
                            mock_source_img,
                            (128, 128, 128),
                            np.eye(4)
                        )
        
        assert result_img == mock_resampled_img
        assert np.array_equal(result_data, mock_resampled_data)
        mock_run.assert_called_once()
    
    def test_resample_to_match_existing_file(self):
        """Test image resampling with existing resampled file"""
        # Mock source image
        mock_source_img = MagicMock()
        mock_source_img.shape = (64, 64, 64)
        
        # Mock existing resampled image
        mock_existing_img = MagicMock()
        mock_existing_data = np.zeros((128, 128, 128))
        mock_existing_img.get_fdata.return_value = mock_existing_data
        
        with patch('os.path.exists', return_value=True):
            with patch('nibabel.load', return_value=mock_existing_img):
                result_img, result_data = self.analyzer.resample_to_match(
                    mock_source_img,
                    (128, 128, 128),
                    np.eye(4),
                    source_path="/path/to/atlas.mgz"
                )
        
        assert result_img == mock_existing_img
        assert np.array_equal(result_data, mock_existing_data)


class TestFocalityMetrics:
    """Test focality metrics calculation"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_calculate_focality_metrics_success(self):
        """Test successful focality metrics calculation"""
        field_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        voxel_volume = 1.0
        region_name = "test_region"
        
        result = self.analyzer._calculate_focality_metrics(field_data, voxel_volume, region_name)
        
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
        assert 'total_volume_cm3' in result
        assert 'num_voxels' in result
        assert 'voxel_volume_mm3' in result
    
    def test_calculate_focality_metrics_empty_data(self):
        """Test focality metrics calculation with empty data"""
        field_data = np.array([])
        voxel_volume = 1.0
        region_name = "test_region"
        
        result = self.analyzer._calculate_focality_metrics(field_data, voxel_volume, region_name)
        
        assert result is None
        self.mock_logger.warning.assert_called()
    
    def test_calculate_focality_metrics_nan_values(self):
        """Test focality metrics calculation with NaN values"""
        field_data = np.array([1.0, np.nan, 3.0, 4.0, 5.0])
        voxel_volume = 1.0
        region_name = "test_region"
        
        result = self.analyzer._calculate_focality_metrics(field_data, voxel_volume, region_name)
        
        assert result is not None
        assert result['num_voxels'] == 4  # Should exclude NaN values


class TestGreyMatterStatistics:
    """Test grey matter statistics calculation"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_get_grey_matter_statistics_success(self):
        """Test successful grey matter statistics calculation"""
        # Mock NIfTI data
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.array([[[1.0, 2.0, 3.0], [0.0, 5.0, 6.0]]])
        
        mock_nib.load.return_value = mock_img
        
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
        # Mock NIfTI data with all zeros
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.zeros((10, 10, 10))
        
        mock_nib.load.return_value = mock_img
        
        result = self.analyzer.get_grey_matter_statistics()
        
        assert result is not None
        assert result['grey_mean'] == 0.0
        assert result['grey_max'] == 0.0
        assert result['grey_min'] == 0.0
        self.mock_logger.warning.assert_called()
    
    def test_get_grey_matter_statistics_4d_data(self):
        """Test grey matter statistics with 4D data"""
        # Mock 4D NIfTI data
        mock_img = MagicMock()
        mock_img.get_fdata.return_value = np.array([[[[1.0, 2.0, 3.0], [0.0, 5.0, 6.0]]]])
        
        mock_nib.load.return_value = mock_img
        
        result = self.analyzer.get_grey_matter_statistics()
        
        assert result is not None
        assert 'grey_mean' in result
        assert 'grey_max' in result
        assert 'grey_min' in result


class TestImageLoading:
    """Test image loading functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_load_brain_image_nifti(self):
        """Test loading NIfTI image"""
        # Mock NIfTI image
        mock_img = MagicMock()
        mock_data = np.array([[[1.0, 2.0, 3.0]]])
        mock_img.get_fdata.return_value = mock_data
        
        # Reset the mock to avoid interference from other tests
        mock_nib.load.reset_mock()
        mock_nib.load.return_value = mock_img
        
        result_img, result_data = self.analyzer.load_brain_image("/path/to/image.nii.gz")
        
        assert result_img == mock_img
        assert np.array_equal(result_data, mock_data)
        # Check that load was called with the correct path (may be called multiple times due to other operations)
        assert any(call[0][0] == "/path/to/image.nii.gz" for call in mock_nib.load.call_args_list)
    
    def test_load_brain_image_mgz_success(self):
        """Test loading MGZ image successfully"""
        # Mock MGZ image
        mock_img = MagicMock()
        mock_data = np.array([[[1.0, 2.0, 3.0]]])
        mock_img.get_fdata.return_value = mock_data
        
        mock_nib.load.return_value = mock_img
        
        result_img, result_data = self.analyzer.load_brain_image("/path/to/image.mgz")
        
        assert result_img == mock_img
        assert np.array_equal(result_data, mock_data)
    
    def test_load_brain_image_mgz_conversion(self):
        """Test loading MGZ image with conversion"""
        # Mock conversion process
        mock_converted_img = MagicMock()
        mock_converted_data = np.array([[[1.0, 2.0, 3.0]]])
        mock_converted_img.get_fdata.return_value = mock_converted_data
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_temp.return_value.__enter__.return_value.name = "/tmp/temp.nii.gz"
            with patch('subprocess.run'):
                with patch('nibabel.load', side_effect=[Exception("Direct load failed"), mock_converted_img]):
                    with patch('os.unlink'):
                        result_img, result_data = self.analyzer.load_brain_image("/path/to/image.mgz")
        
        assert result_img == mock_converted_img
        assert np.array_equal(result_data, mock_converted_data)


class TestRegionFinding:
    """Test region finding functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_logger = MagicMock()
        self.mock_logger.getChild.return_value = self.mock_logger
        
        with patch('os.path.exists', return_value=True):
            with patch('os.makedirs'):
                self.analyzer = VoxelAnalyzer(
                    field_nifti="/path/to/field.nii.gz",
                    subject_dir="/path/to/subject",
                    output_dir="/path/to/output",
                    logger=self.mock_logger
                )
    
    def test_find_region_by_id(self):
        """Test finding region by ID"""
        region_info = {
            1: {'name': 'Region1', 'voxel_count': 100, 'color': (0.5, 0.5, 0.5)},
            2: {'name': 'Region2', 'voxel_count': 200, 'color': (0.7, 0.7, 0.7)}
        }
        
        region_id, region_name = self.analyzer.find_region(1, region_info)
        
        assert region_id == 1
        assert region_name == 'Region1'
    
    def test_find_region_by_name(self):
        """Test finding region by name"""
        region_info = {
            1: {'name': 'Left-Hippocampus', 'voxel_count': 100, 'color': (0.5, 0.5, 0.5)},
            2: {'name': 'Right-Hippocampus', 'voxel_count': 200, 'color': (0.7, 0.7, 0.7)}
        }
        
        region_id, region_name = self.analyzer.find_region("Left-Hippocampus", region_info)
        
        assert region_id == 1
        assert region_name == 'Left-Hippocampus'
    
    def test_find_region_case_insensitive(self):
        """Test finding region with case-insensitive search"""
        region_info = {
            1: {'name': 'Left-Hippocampus', 'voxel_count': 100, 'color': (0.5, 0.5, 0.5)}
        }
        
        region_id, region_name = self.analyzer.find_region("left-hippocampus", region_info)
        
        assert region_id == 1
        assert region_name == 'Left-Hippocampus'
    
    def test_find_region_not_found(self):
        """Test finding region that doesn't exist"""
        region_info = {
            1: {'name': 'Region1', 'voxel_count': 100, 'color': (0.5, 0.5, 0.5)}
        }
        
        with pytest.raises(ValueError, match="Region name 'NonExistent' not found"):
            self.analyzer.find_region("NonExistent", region_info)
    
    def test_find_region_no_region_info(self):
        """Test finding region without region info"""
        with pytest.raises(ValueError, match="Region labels are required"):
            self.analyzer.find_region("Region1", None)

if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v"])
