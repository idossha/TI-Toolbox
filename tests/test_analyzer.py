#!/usr/bin/env simnibs_python

"""
Comprehensive pytest tests for main_analyzer.py

This module tests all the functionality in the main analyzer script including:
- Utility functions (format_duration, validation functions)
- Logging functions
- ROI description creation
- Mesh field path construction
- Argument parsing and validation
- Main function execution with mocked dependencies
"""

import os
import sys
import pytest
import tempfile
import argparse
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Mock the analyzer modules before importing main_analyzer
from unittest.mock import MagicMock

# Store original modules for cleanup (match new imports via `tit.analyzer.*`)
_original_mesh_analyzer = sys.modules.get('tit.analyzer.mesh_analyzer')
_original_voxel_analyzer = sys.modules.get('tit.analyzer.voxel_analyzer')

# Create mock modules for the analyzer dependencies
mock_mesh_analyzer = MagicMock()
mock_voxel_analyzer = MagicMock()

# Add the mock modules to sys.modules before importing
sys.modules['tit.analyzer.mesh_analyzer'] = mock_mesh_analyzer
sys.modules['tit.analyzer.voxel_analyzer'] = mock_voxel_analyzer


@pytest.fixture(scope='module', autouse=True)
def cleanup_analyzer_mocks():
    """Cleanup mock dependencies after all tests"""
    yield  # Tests run here

    # Cleanup: restore original modules or remove mocks
    if _original_mesh_analyzer is not None:
        sys.modules['tit.analyzer.mesh_analyzer'] = _original_mesh_analyzer
    else:
        sys.modules.pop('tit.analyzer.mesh_analyzer', None)

    if _original_voxel_analyzer is not None:
        sys.modules['tit.analyzer.voxel_analyzer'] = _original_voxel_analyzer
    else:
        sys.modules.pop('tit.analyzer.voxel_analyzer', None)


# Now import the main_analyzer module (after mocks are set up)
from tit.analyzer.main_analyzer import (
    format_duration,
    validate_file_extension,
    validate_coordinates,
    validate_radius,
    create_roi_description,
    construct_mesh_field_path,
    setup_parser,
    validate_args,
    print_stat_if_exists,
    flush_output,
    log_analysis_start,
    log_analysis_complete,
    log_analysis_failed,
    log_analysis_step_start,
    log_analysis_step_complete,
    log_analysis_step_failed
)


class TestUtilityFunctions:
    """Test utility functions in main_analyzer.py"""
    
    def test_format_duration(self):
        """Test duration formatting in various formats"""
        # Test seconds only
        assert format_duration(30) == "30s"
        assert format_duration(59) == "59s"
        
        # Test minutes and seconds
        assert format_duration(60) == "1m 0s"
        assert format_duration(90) == "1m 30s"
        assert format_duration(3599) == "59m 59s"
        
        # Test hours, minutes, and seconds
        assert format_duration(3600) == "1h 0m 0s"
        assert format_duration(3661) == "1h 1m 1s"
        assert format_duration(7325) == "2h 2m 5s"
        
        # Test edge cases
        assert format_duration(0) == "0s"
        assert format_duration(1) == "1s"
    
    def test_validate_file_extension(self):
        """Test file extension validation"""
        # Test valid extensions
        validate_file_extension("test.nii", [".nii"])
        validate_file_extension("test.nii.gz", [".nii.gz"])
        validate_file_extension("test.mgz", [".mgz"])
        validate_file_extension("test.msh", [".msh"])
        
        # Test case insensitive
        validate_file_extension("test.NII", [".nii"])
        validate_file_extension("test.NII.GZ", [".nii.gz"])
        
        # Test invalid extensions
        with pytest.raises(ValueError, match="Invalid file extension"):
            validate_file_extension("test.txt", [".nii", ".mgz"])
        
        with pytest.raises(ValueError, match="Invalid file extension"):
            validate_file_extension("test.nii.gz", [".nii"])
        
        with pytest.raises(ValueError, match="Invalid file extension"):
            validate_file_extension("test", [".nii", ".mgz"])
    
    def test_validate_coordinates(self):
        """Test coordinate validation"""
        # Test valid coordinates
        coords = validate_coordinates(["10", "20", "30"])
        assert coords == [10.0, 20.0, 30.0]
        
        coords = validate_coordinates([10, 20, 30])
        assert coords == [10.0, 20.0, 30.0]
        
        coords = validate_coordinates([10.5, -20.3, 0])
        assert coords == [10.5, -20.3, 0.0]
        
        # Test invalid number of coordinates
        with pytest.raises(ValueError, match="Coordinates must be exactly three values"):
            validate_coordinates(["10", "20"])
        
        with pytest.raises(ValueError, match="Coordinates must be exactly three values"):
            validate_coordinates(["10", "20", "30", "40"])
        
        # Test invalid coordinate types
        with pytest.raises(ValueError, match="Coordinates must be numeric values"):
            validate_coordinates(["10", "abc", "30"])
        
        with pytest.raises(ValueError, match="Coordinates must be numeric values"):
            validate_coordinates([10, None, 30])
    
    def test_validate_radius(self):
        """Test radius validation"""
        # Test valid radius
        assert validate_radius("5.0") == 5.0
        assert validate_radius(5.0) == 5.0
        assert validate_radius(10) == 10.0
        assert validate_radius("0.1") == 0.1
        
        # Test invalid radius (zero or negative)
        with pytest.raises(ValueError, match="Radius must be a positive number"):
            validate_radius("0")
        
        with pytest.raises(ValueError, match="Radius must be a positive number"):
            validate_radius("-5")
        
        with pytest.raises(ValueError, match="Radius must be a positive number"):
            validate_radius(0)
        
        # Test invalid radius types
        with pytest.raises(ValueError, match="Radius must be a positive number"):
            validate_radius("abc")
        
        with pytest.raises(ValueError, match="Radius must be a positive number"):
            validate_radius(None)


class TestLoggingFunctions:
    """Test logging functions in main_analyzer.py"""
    
    def setup_method(self):
        """Setup for each test method"""
        # Reset global variables
        import tit.analyzer.main_analyzer as ma
        ma.SUMMARY_MODE = False
        ma._start_times = {}
        ma._analysis_start_time = None
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', False)
    @patch('tit.analyzer.main_analyzer.logger')
    def test_log_analysis_start(self, mock_logger):
        """Test log_analysis_start function"""
        log_analysis_start("spherical", "test_subject", "Test ROI")
        
        mock_logger.info.assert_called_once_with(
            "Beginning analysis for subject: test_subject (Test ROI)"
        )
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', True)
    @patch('builtins.print')
    def test_log_analysis_start_summary_mode(self, mock_print):
        """Test log_analysis_start function in summary mode"""
        log_analysis_start("spherical", "test_subject", "Test ROI")
        
        mock_print.assert_called_once_with(
            "Beginning analysis for subject: test_subject (Test ROI)"
        )
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', False)
    @patch('tit.analyzer.main_analyzer.logger')
    def test_log_analysis_complete(self, mock_logger):
        """Test log_analysis_complete function"""
        import tit.analyzer.main_analyzer as ma
        ma._analysis_start_time = 1000.0
        
        with patch('time.time', return_value=1010.0):
            log_analysis_complete("spherical", "test_subject", "1 region", "/path/output")
        
        mock_logger.info.assert_called_once_with(
            "Analysis completed successfully for subject: test_subject (Total: 10s)"
        )
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', True)
    @patch('builtins.print')
    def test_log_analysis_complete_summary_mode(self, mock_print):
        """Test log_analysis_complete function in summary mode"""
        import tit.analyzer.main_analyzer as ma
        ma._analysis_start_time = 1000.0
        
        with patch('time.time', return_value=1010.0):
            log_analysis_complete("spherical", "test_subject", "1 region", "/path/output")
        
        expected_calls = [
            call("└─ Analysis completed successfully for subject: test_subject (1 region, Total: 10s)"),
            call("   Results saved to: /path/output")
        ]
        mock_print.assert_has_calls(expected_calls)
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', False)
    @patch('tit.analyzer.main_analyzer.logger')
    def test_log_analysis_failed(self, mock_logger):
        """Test log_analysis_failed function"""
        import tit.analyzer.main_analyzer as ma
        ma._analysis_start_time = 1000.0
        
        with patch('time.time', return_value=1010.0):
            log_analysis_failed("spherical", "test_subject", "Test error")
        
        mock_logger.error.assert_called_once_with(
            "Analysis failed for subject: test_subject (10s) - Test error"
        )
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', False)
    @patch('tit.analyzer.main_analyzer.logger')
    def test_log_analysis_step_start(self, mock_logger):
        """Test log_analysis_step_start function"""
        log_analysis_step_start("Field loading", "test_subject")
        
        mock_logger.info.assert_called_once_with("Field loading: Started")
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', True)
    @patch('builtins.print')
    def test_log_analysis_step_start_summary_mode(self, mock_print):
        """Test log_analysis_step_start function in summary mode"""
        log_analysis_step_start("Field loading", "test_subject")
        
        mock_print.assert_called_once_with("├─ Field loading: Started")
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', False)
    @patch('tit.analyzer.main_analyzer.logger')
    def test_log_analysis_step_complete(self, mock_logger):
        """Test log_analysis_step_complete function"""
        import tit.analyzer.main_analyzer as ma
        ma._start_times["test_subject_Field loading"] = 1000.0
        
        with patch('time.time', return_value=1010.0):
            log_analysis_step_complete("Field loading", "test_subject", "5 voxels")
        
        mock_logger.info.assert_called_once_with("Field loading: Complete (10s)")
        assert "test_subject_Field loading" not in ma._start_times
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', True)
    @patch('builtins.print')
    def test_log_analysis_step_complete_summary_mode(self, mock_print):
        """Test log_analysis_step_complete function in summary mode"""
        import tit.analyzer.main_analyzer as ma
        ma._start_times["test_subject_Field loading"] = 1000.0
        
        with patch('time.time', return_value=1010.0):
            log_analysis_step_complete("Field loading", "test_subject", "5 voxels")
        
        mock_print.assert_called_once_with("├─ Field loading: ✓ Complete (10s) - 5 voxels")
        assert "test_subject_Field loading" not in ma._start_times
    
    @patch('tit.analyzer.main_analyzer.SUMMARY_MODE', False)
    @patch('tit.analyzer.main_analyzer.logger')
    def test_log_analysis_step_failed(self, mock_logger):
        """Test log_analysis_step_failed function"""
        import tit.analyzer.main_analyzer as ma
        ma._start_times["test_subject_Field loading"] = 1000.0
        
        with patch('time.time', return_value=1010.0):
            log_analysis_step_failed("Field loading", "test_subject", "File not found")
        
        mock_logger.error.assert_called_once_with("Field loading: Failed (10s) - File not found")
        assert "test_subject_Field loading" not in ma._start_times


class TestROIDescription:
    """Test ROI description creation"""
    
    def test_create_roi_description_spherical(self):
        """Test ROI description for spherical analysis"""
        args = Mock()
        args.analysis_type = 'spherical'
        args.coordinates = [10.0, 20.0, 30.0]
        args.radius = 5.0

        description = create_roi_description(args)
        # Updated to match actual implementation format
        assert description == "Spherical: (10.00,20.00,30.00) r5.0mm"
    
    def test_create_roi_description_cortical_mesh_whole_head(self):
        """Test ROI description for cortical mesh analysis (whole head)"""
        args = Mock()
        args.analysis_type = 'cortical'
        args.space = 'mesh'
        args.atlas_name = 'DK40'
        args.whole_head = True
        args.region = None
        
        description = create_roi_description(args)
        assert description == "Cortical: DK40 (whole head)"
    
    def test_create_roi_description_cortical_mesh_region(self):
        """Test ROI description for cortical mesh analysis (specific region)"""
        args = Mock()
        args.analysis_type = 'cortical'
        args.space = 'mesh'
        args.atlas_name = 'DK40'
        args.whole_head = False
        args.region = 'superiorfrontal'
        
        description = create_roi_description(args)
        assert description == "Cortical: DK40.superiorfrontal"
    
    def test_create_roi_description_cortical_voxel_whole_head(self):
        """Test ROI description for cortical voxel analysis (whole head)"""
        args = Mock()
        args.analysis_type = 'cortical'
        args.space = 'voxel'
        args.atlas_path = '/path/to/atlas.nii.gz'
        args.whole_head = True
        args.region = None
        
        description = create_roi_description(args)
        assert description == "Cortical: atlas.nii.gz (whole head)"
    
    def test_create_roi_description_cortical_voxel_region(self):
        """Test ROI description for cortical voxel analysis (specific region)"""
        args = Mock()
        args.analysis_type = 'cortical'
        args.space = 'voxel'
        args.atlas_path = '/path/to/atlas.nii.gz'
        args.whole_head = False
        args.region = 'Left-Hippocampus'
        
        description = create_roi_description(args)
        assert description == "Cortical: atlas.nii.gz.Left-Hippocampus"


class TestMeshFieldPathConstruction:
    """Test mesh field path construction"""
    
    @patch('os.path.exists')
    @patch('os.path.basename')
    def test_construct_mesh_field_path_ti_simulation(self, mock_basename, mock_exists):
        """Test mesh field path construction for TI simulation"""
        # Mock the path structure
        mock_basename.side_effect = lambda x: {
            '/path/to/m2m_subject': 'm2m_subject',
            '/path/to/project': 'project'
        }.get(x, 'unknown')
        
        # Mock that TI directory exists (not mTI)
        mock_exists.side_effect = lambda x: 'TI' in x and 'mTI' not in x
        
        result = construct_mesh_field_path('/path/to/m2m_subject', 'test_montage')
        
        # Should return TI path
        assert 'TI' in result
        assert 'test_montage' in result
        assert result.endswith('_TI.msh')
    
    @patch('os.path.exists')
    @patch('os.path.basename')
    def test_construct_mesh_field_path_mti_simulation(self, mock_basename, mock_exists):
        """Test mesh field path construction for mTI simulation"""
        # Mock the path structure
        mock_basename.side_effect = lambda x: {
            '/path/to/m2m_subject': 'm2m_subject',
            '/path/to/project': 'project'
        }.get(x, 'unknown')
        
        # Mock that mTI directory exists
        mock_exists.side_effect = lambda x: 'mTI' in x
        
        result = construct_mesh_field_path('/path/to/m2m_subject', 'test_montage')
        
        # Should return mTI path
        assert 'mTI' in result
        assert 'test_montage' in result
        assert result.endswith('_mTI.msh')
    
    @patch('os.path.exists')
    @patch('os.path.basename')
    def test_construct_mesh_field_path_montage_variations(self, mock_basename, mock_exists):
        """Test mesh field path construction with different montage name variations"""
        # Mock the path structure
        mock_basename.side_effect = lambda x: {
            '/path/to/m2m_subject': 'm2m_subject',
            '/path/to/project': 'project'
        }.get(x, 'unknown')
        
        # Mock that TI directory exists
        mock_exists.side_effect = lambda x: 'TI' in x and 'mTI' not in x
        
        # Test with _TINormal suffix
        result = construct_mesh_field_path('/path/to/m2m_subject', 'test_montage_TINormal')
        assert 'test_montage_TINormal' in result
        assert result.endswith('_TI.msh')
        
        # Test with Normal suffix
        result = construct_mesh_field_path('/path/to/m2m_subject', 'test_montageNormal')
        assert 'test_montageNormal' in result
        assert result.endswith('_TI.msh')


class TestArgumentParser:
    """Test argument parser setup"""
    
    def test_setup_parser(self):
        """Test that argument parser is set up correctly"""
        parser = setup_parser()
        
        # Check that it's an ArgumentParser instance
        assert isinstance(parser, argparse.ArgumentParser)
        
        # Check required arguments
        required_args = ['m2m_subject_path', 'space', 'analysis_type']
        for arg in required_args:
            action = parser._option_string_actions[f'--{arg}']
            assert action.required == True
        
        # Check choices for space
        space_action = parser._option_string_actions['--space']
        assert space_action.choices == ['mesh', 'voxel']
        
        # Check choices for analysis_type
        analysis_action = parser._option_string_actions['--analysis_type']
        assert analysis_action.choices == ['spherical', 'cortical']
    
    def test_parser_optional_arguments(self):
        """Test that optional arguments are defined correctly"""
        parser = setup_parser()
        
        # Check optional arguments exist
        optional_args = [
            'montage_name', 'field_path', 'atlas_name', 'atlas_path',
            'coordinates', 'radius', 'region', 'whole_head',
            'output_dir', 'visualize', 'log_file', 'quiet'
        ]
        
        for arg in optional_args:
            assert f'--{arg}' in parser._option_string_actions


class TestArgumentValidation:
    """Test argument validation"""
    
    def setup_method(self):
        """Setup for each test method"""
        # Create a mock logger
        self.mock_logger = Mock()
        
        # Patch the logger in the module
        with patch('analyzer.main_analyzer.logger', self.mock_logger):
            pass
    
    @patch('os.path.isdir')
    @patch('os.path.exists')
    def test_validate_args_mesh_spherical_valid(self, mock_exists, mock_isdir):
        """Test validation of valid mesh spherical arguments"""
        mock_isdir.return_value = True
        mock_exists.return_value = True
        
        args = Mock()
        args.m2m_subject_path = '/path/to/m2m'
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.montage_name = 'test_montage'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        args.atlas_name = None
        args.atlas_path = None
        args.region = None
        args.whole_head = False
        
        with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
            with patch('analyzer.main_analyzer.validate_file_extension'):
                with patch('analyzer.main_analyzer.validate_coordinates', return_value=[10.0, 20.0, 30.0]):
                    with patch('analyzer.main_analyzer.validate_radius', return_value=5.0):
                        # Should not raise any exceptions
                        validate_args(args)
    
    @patch('os.path.isdir')
    def test_validate_args_invalid_m2m_path(self, mock_isdir):
        """Test validation with invalid m2m path"""
        mock_isdir.return_value = False
        
        args = Mock()
        args.m2m_subject_path = '/invalid/path'
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.montage_name = 'test_montage'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        
        with pytest.raises(ValueError, match="m2m subject directory not found"):
            validate_args(args)
    
    @patch('os.path.isdir')
    @patch('os.path.exists')
    def test_validate_args_mesh_missing_montage(self, mock_exists, mock_isdir):
        """Test validation with missing montage name for mesh analysis"""
        mock_isdir.return_value = True
        mock_exists.return_value = False
        
        args = Mock()
        args.m2m_subject_path = '/path/to/m2m'
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.montage_name = None
        args.field_path = None
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        
        with pytest.raises(ValueError, match="--montage_name is required for mesh analysis"):
            validate_args(args)
    
    @patch('os.path.isdir')
    def test_validate_args_voxel_missing_field_path(self, mock_isdir):
        """Test validation with missing field path for voxel analysis"""
        mock_isdir.return_value = True
        
        args = Mock()
        args.m2m_subject_path = '/path/to/m2m'
        args.space = 'voxel'
        args.analysis_type = 'spherical'
        args.field_path = None
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        
        with pytest.raises(ValueError, match="--field_path is required for voxel analysis"):
            validate_args(args)
    
    @patch('os.path.isdir')
    @patch('os.path.exists')
    def test_validate_args_spherical_missing_coordinates(self, mock_exists, mock_isdir):
        """Test validation with missing coordinates for spherical analysis"""
        mock_isdir.return_value = True
        mock_exists.return_value = True

        args = Mock()
        args.m2m_subject_path = '/path/to/m2m'
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.montage_name = 'test_montage'
        args.field_path = None
        args.coordinates = None
        args.radius = 5.0

        with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
            with pytest.raises(ValueError, match="Coordinates are required for spherical analysis"):
                validate_args(args)
    
    @patch('os.path.isdir')
    @patch('os.path.exists')
    def test_validate_args_spherical_missing_radius(self, mock_exists, mock_isdir):
        """Test validation with missing radius for spherical analysis"""
        mock_isdir.return_value = True
        mock_exists.return_value = True

        args = Mock()
        args.m2m_subject_path = '/path/to/m2m'
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.montage_name = 'test_montage'
        args.field_path = None
        args.coordinates = [10, 20, 30]
        args.radius = None

        with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
            with pytest.raises(ValueError, match="Radius is required for spherical analysis"):
                validate_args(args)
    
    @patch('os.path.isdir')
    @patch('os.path.exists')
    def test_validate_args_cortical_mesh_missing_atlas(self, mock_exists, mock_isdir):
        """Test validation with missing atlas name for mesh cortical analysis"""
        mock_isdir.return_value = True
        mock_exists.return_value = True

        args = Mock()
        args.m2m_subject_path = '/path/to/m2m'
        args.space = 'mesh'
        args.analysis_type = 'cortical'
        args.montage_name = 'test_montage'
        args.field_path = None
        args.atlas_name = None
        args.region = 'test_region'
        args.whole_head = False

        with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
            with pytest.raises(ValueError, match="Atlas name is required for mesh-based cortical analysis"):
                validate_args(args)
    
    @patch('os.path.isdir')
    @patch('os.path.exists')
    def test_validate_args_cortical_voxel_missing_atlas(self, mock_exists, mock_isdir):
        """Test validation with missing atlas path for voxel cortical analysis"""
        mock_isdir.return_value = True
        mock_exists.return_value = True

        args = Mock()
        args.m2m_subject_path = '/path/to/m2m'
        args.space = 'voxel'
        args.analysis_type = 'cortical'
        args.field_path = '/path/to/field.nii.gz'
        args.atlas_path = None
        args.region = 'test_region'
        args.whole_head = False

        with pytest.raises(ValueError, match="Atlas path is required for voxel-based cortical analysis"):
            validate_args(args)
    
    @patch('os.path.isdir')
    @patch('os.path.exists')
    def test_validate_args_cortical_missing_region_and_whole_head(self, mock_exists, mock_isdir):
        """Test validation with missing both region and whole_head for cortical analysis"""
        mock_isdir.return_value = True
        mock_exists.return_value = True

        args = Mock()
        args.m2m_subject_path = '/path/to/m2m'
        args.space = 'mesh'
        args.analysis_type = 'cortical'
        args.montage_name = 'test_montage'
        args.field_path = None
        args.atlas_name = 'DK40'
        args.region = None
        args.whole_head = False

        with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
            with pytest.raises(ValueError, match="Either --whole_head flag or --region must be specified"):
                validate_args(args)


class TestPrintStatistics:
    """Test print statistics helper function"""
    
    @patch('builtins.print')
    def test_print_stat_if_exists_numeric(self, mock_print):
        """Test printing numeric statistics"""
        results = {'mean_value': 1.234567, 'max_value': 2.5, 'min_value': 0.1}
        
        print_stat_if_exists(results, 'mean_value', 'Mean Value')
        mock_print.assert_called_with("Mean Value: 1.234567")
        
        print_stat_if_exists(results, 'max_value', 'Max Value')
        mock_print.assert_called_with("Max Value: 2.500000")
    
    @patch('builtins.print')
    def test_print_stat_if_exists_non_numeric(self, mock_print):
        """Test printing non-numeric statistics"""
        results = {'region_name': 'Left-Hippocampus', 'status': 'completed'}
        
        print_stat_if_exists(results, 'region_name', 'Region')
        mock_print.assert_called_with("Region: Left-Hippocampus")
        
        print_stat_if_exists(results, 'status', 'Status')
        mock_print.assert_called_with("Status: completed")
    
    @patch('builtins.print')
    def test_print_stat_if_exists_missing_key(self, mock_print):
        """Test printing when key doesn't exist"""
        results = {'mean_value': 1.234567}
        
        print_stat_if_exists(results, 'missing_key', 'Missing')
        mock_print.assert_not_called()
    
    @patch('builtins.print')
    def test_print_stat_if_exists_none_value(self, mock_print):
        """Test printing when value is None"""
        results = {'mean_value': None, 'max_value': 2.5}
        
        print_stat_if_exists(results, 'mean_value', 'Mean Value')
        mock_print.assert_not_called()
        
        print_stat_if_exists(results, 'max_value', 'Max Value')
        mock_print.assert_called_with("Max Value: 2.500000")


class TestMainFunction:
    """Test main function with mocked dependencies"""
    
    def setup_method(self):
        """Setup for each test method"""
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        
        # Mock logger
        self.mock_logger = Mock()
    
    def teardown_method(self):
        """Cleanup after each test method"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('tit.analyzer.main_analyzer.MeshAnalyzer')
    @patch('tit.analyzer.main_analyzer.VoxelAnalyzer')
    @patch('tit.analyzer.main_analyzer.logging_util.get_logger')
    @patch('tit.analyzer.main_analyzer.setup_parser')
    def test_main_mesh_spherical_analysis(self, mock_setup_parser, mock_get_logger, mock_voxel_analyzer, mock_mesh_analyzer):
        """Test main function with mesh spherical analysis"""
        # Setup mock parser and arguments
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.m2m_subject_path = '/path/to/m2m'
        mock_args.space = 'mesh'
        mock_args.analysis_type = 'spherical'
        mock_args.montage_name = 'test_montage'
        mock_args.coordinates = [10.0, 20.0, 30.0]
        mock_args.radius = 5.0
        mock_args.visualize = False
        mock_args.quiet = False
        mock_args.log_file = None
        mock_args.output_dir = 'analysis_output'
        mock_args.field_path = '/path/to/field.msh'
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        # Setup mock logger
        mock_get_logger.return_value = self.mock_logger
        
        # Setup mock analyzer
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.analyze_sphere.return_value = {
            'mean_value': 1.5,
            'max_value': 2.0,
            'min_value': 1.0,
            'voxel_count': 100
        }
        mock_mesh_analyzer.return_value = mock_analyzer_instance
        
        # Mock file operations
        with patch('os.path.isdir', return_value=True):
            with patch('os.path.exists', return_value=True):
                with patch('os.makedirs'):
                    with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
                        # Run main function
                        from tit.analyzer.main_analyzer import main
                        main()
        
        # Verify analyzer was called correctly
        mock_mesh_analyzer.assert_called_once()
        mock_analyzer_instance.analyze_sphere.assert_called_once_with(
            center_coordinates=[10.0, 20.0, 30.0],
            radius=5.0,
            visualize=False
        )
    
    @patch('tit.analyzer.main_analyzer.MeshAnalyzer')
    @patch('tit.analyzer.main_analyzer.VoxelAnalyzer')
    @patch('tit.analyzer.main_analyzer.logging_util.get_logger')
    @patch('tit.analyzer.main_analyzer.setup_parser')
    def test_main_voxel_cortical_analysis(self, mock_setup_parser, mock_get_logger, mock_voxel_analyzer, mock_mesh_analyzer):
        """Test main function with voxel cortical analysis"""
        # Setup mock parser and arguments
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.m2m_subject_path = '/path/to/m2m'
        mock_args.space = 'voxel'
        mock_args.analysis_type = 'cortical'
        mock_args.field_path = '/path/to/field.nii.gz'
        mock_args.atlas_path = '/path/to/atlas.nii.gz'
        mock_args.region = 'Left-Hippocampus'
        mock_args.visualize = False
        mock_args.quiet = False
        mock_args.log_file = None
        mock_args.output_dir = 'analysis_output'
        mock_args.whole_head = False
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        # Setup mock logger
        mock_get_logger.return_value = self.mock_logger
        
        # Setup mock analyzer
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.analyze_cortex.return_value = {
            'mean_value': 1.5,
            'max_value': 2.0,
            'min_value': 1.0
        }
        mock_voxel_analyzer.return_value = mock_analyzer_instance
        
        # Mock file operations
        with patch('os.path.isdir', return_value=True):
            with patch('os.path.exists', return_value=True):
                with patch('os.makedirs'):
                    # Run main function
                    from tit.analyzer.main_analyzer import main
                    main()
        
        # Verify analyzer was called correctly
        mock_voxel_analyzer.assert_called_once()
        mock_analyzer_instance.analyze_cortex.assert_called_once_with(
            atlas_file='/path/to/atlas.nii.gz',
            target_region='Left-Hippocampus',
            visualize=False
        )

    @patch('tit.analyzer.main_analyzer.MeshAnalyzer')
    @patch('tit.analyzer.main_analyzer.VoxelAnalyzer')
    @patch('tit.analyzer.main_analyzer.logging_util.get_logger')
    @patch('tit.analyzer.main_analyzer.setup_parser')
    def test_main_voxel_cortical_whole_head(self, mock_setup_parser, mock_get_logger, mock_voxel_analyzer, mock_mesh_analyzer):
        """Test main function with voxel cortical whole-head analysis"""
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.m2m_subject_path = '/path/to/m2m'
        mock_args.space = 'voxel'
        mock_args.analysis_type = 'cortical'
        mock_args.field_path = '/path/to/field.nii.gz'
        mock_args.atlas_path = '/path/to/atlas.nii.gz'
        mock_args.whole_head = True
        mock_args.region = None
        mock_args.visualize = False
        mock_args.quiet = False
        mock_args.log_file = None
        mock_args.output_dir = 'analysis_output'
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser

        mock_get_logger.return_value = self.mock_logger

        mock_analyzer_instance = Mock()
        mock_analyzer_instance.analyze_whole_head.return_value = {
            'Region1': {'mean_value': 1.0}
        }
        mock_voxel_analyzer.return_value = mock_analyzer_instance

        with patch('os.path.isdir', return_value=True):
            with patch('os.path.exists', return_value=True):
                with patch('os.makedirs'):
                    from tit.analyzer.main_analyzer import main
                    main()

        mock_voxel_analyzer.assert_called_once()
        mock_analyzer_instance.analyze_whole_head.assert_called_once_with(
            atlas_file='/path/to/atlas.nii.gz',
            visualize=False
        )
    
    @patch('tit.analyzer.main_analyzer.MeshAnalyzer')
    @patch('tit.analyzer.main_analyzer.VoxelAnalyzer')
    @patch('tit.analyzer.main_analyzer.logging_util.get_logger')
    @patch('tit.analyzer.main_analyzer.setup_parser')
    def test_main_whole_head_analysis(self, mock_setup_parser, mock_get_logger, mock_voxel_analyzer, mock_mesh_analyzer):
        """Test main function with whole head analysis"""
        # Setup mock parser and arguments
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.m2m_subject_path = '/path/to/m2m'
        mock_args.space = 'mesh'
        mock_args.analysis_type = 'cortical'
        mock_args.montage_name = 'test_montage'
        mock_args.atlas_name = 'DK40'
        mock_args.whole_head = True
        mock_args.visualize = False
        mock_args.quiet = False
        mock_args.log_file = None
        mock_args.output_dir = 'analysis_output'
        mock_args.field_path = '/path/to/field.msh'
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        # Setup mock logger
        mock_get_logger.return_value = self.mock_logger
        
        # Setup mock analyzer
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.analyze_whole_head.return_value = {
            'region1': {'mean_value': 1.5, 'max_value': 2.0},
            'region2': {'mean_value': 1.2, 'max_value': 1.8}
        }
        mock_mesh_analyzer.return_value = mock_analyzer_instance
        
        # Mock file operations
        with patch('os.path.isdir', return_value=True):
            with patch('os.path.exists', return_value=True):
                with patch('os.makedirs'):
                    with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
                        # Run main function
                        from tit.analyzer.main_analyzer import main
                        main()
        
        # Verify analyzer was called correctly
        mock_mesh_analyzer.assert_called_once()
        mock_analyzer_instance.analyze_whole_head.assert_called_once_with(
            atlas_type='DK40',
            visualize=False
        )
    
    @patch('tit.analyzer.main_analyzer.MeshAnalyzer')
    @patch('tit.analyzer.main_analyzer.VoxelAnalyzer')
    @patch('tit.analyzer.main_analyzer.logging_util.get_logger')
    @patch('tit.analyzer.main_analyzer.setup_parser')
    def test_main_quiet_mode(self, mock_setup_parser, mock_get_logger, mock_voxel_analyzer, mock_mesh_analyzer):
        """Test main function in quiet mode"""
        # Setup mock parser and arguments
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.m2m_subject_path = '/path/to/m2m'
        mock_args.space = 'mesh'
        mock_args.analysis_type = 'spherical'
        mock_args.montage_name = 'test_montage'
        mock_args.coordinates = [10.0, 20.0, 30.0]
        mock_args.radius = 5.0
        mock_args.visualize = False
        mock_args.quiet = True
        mock_args.log_file = None
        mock_args.output_dir = 'analysis_output'
        mock_args.field_path = '/path/to/field.msh'
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        # Setup mock logger
        mock_get_logger.return_value = self.mock_logger
        
        # Setup mock analyzer
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.analyze_sphere.return_value = {
            'mean_value': 1.5,
            'max_value': 2.0,
            'min_value': 1.0,
            'voxel_count': 100
        }
        mock_mesh_analyzer.return_value = mock_analyzer_instance
        
        # Mock file operations
        with patch('os.path.isdir', return_value=True):
            with patch('os.path.exists', return_value=True):
                with patch('os.makedirs'):
                    with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
                        with patch('builtins.print') as mock_print:
                            # Run main function
                            from tit.analyzer.main_analyzer import main
                            main()
        
        # Verify quiet mode logging was used
        # The print calls should include summary mode messages
        assert any('Beginning analysis for subject' in str(call) for call in mock_print.call_args_list)
    
    @patch('tit.analyzer.main_analyzer.MeshAnalyzer')
    @patch('tit.analyzer.main_analyzer.VoxelAnalyzer')
    @patch('tit.analyzer.main_analyzer.logging_util.get_logger')
    @patch('tit.analyzer.main_analyzer.setup_parser')
    def test_main_analyzer_initialization_failure(self, mock_setup_parser, mock_get_logger, mock_voxel_analyzer, mock_mesh_analyzer):
        """Test main function when analyzer initialization fails"""
        # Setup mock parser and arguments
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.m2m_subject_path = '/path/to/m2m'
        mock_args.space = 'mesh'
        mock_args.analysis_type = 'spherical'
        mock_args.montage_name = 'test_montage'
        mock_args.coordinates = [10.0, 20.0, 30.0]
        mock_args.radius = 5.0
        mock_args.visualize = False
        mock_args.quiet = False
        mock_args.log_file = None
        mock_args.output_dir = 'analysis_output'
        mock_args.field_path = '/path/to/field.msh'
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        # Setup mock logger
        mock_get_logger.return_value = self.mock_logger
        
        # Setup mock analyzer to return None (initialization failure)
        mock_mesh_analyzer.return_value = None
        
        # Mock file operations
        with patch('os.path.isdir', return_value=True):
            with patch('os.path.exists', return_value=True):
                with patch('os.makedirs'):
                    with patch('analyzer.main_analyzer.construct_mesh_field_path', return_value='/path/to/field.msh'):
                        with patch('sys.exit') as mock_exit:
                            # Run main function
                            from tit.analyzer.main_analyzer import main
                            main()
        
        # Verify that sys.exit was called with error code 1
        mock_exit.assert_called_once_with(1)
    
    @patch('tit.analyzer.main_analyzer.MeshAnalyzer')
    @patch('tit.analyzer.main_analyzer.VoxelAnalyzer')
    @patch('tit.analyzer.main_analyzer.logging_util.get_logger')
    @patch('tit.analyzer.main_analyzer.setup_parser')
    def test_main_validation_error(self, mock_setup_parser, mock_get_logger, mock_voxel_analyzer, mock_mesh_analyzer):
        """Test main function when argument validation fails"""
        # Setup mock parser and arguments
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.m2m_subject_path = '/invalid/path'
        mock_args.space = 'mesh'
        mock_args.analysis_type = 'spherical'
        mock_args.montage_name = 'test_montage'
        mock_args.coordinates = [10.0, 20.0, 30.0]
        mock_args.radius = 5.0
        mock_args.visualize = False
        mock_args.quiet = False
        mock_args.log_file = None
        mock_args.output_dir = 'analysis_output'
        mock_args.field_path = '/path/to/field.msh'
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        # Setup mock logger
        mock_get_logger.return_value = self.mock_logger
        
        # Mock file operations to return False for invalid path
        with patch('os.path.isdir', return_value=False):
            with patch('sys.exit') as mock_exit:
                # Run main function
                from tit.analyzer.main_analyzer import main
                main()
        
        # Verify that sys.exit was called with error code 1
        mock_exit.assert_called_once_with(1)


class TestFlushOutput:
    """Test flush output function"""
    
    @patch('sys.stdout.flush')
    @patch('sys.stderr.flush')
    def test_flush_output_success(self, mock_stderr_flush, mock_stdout_flush):
        """Test flush_output function when flush operations succeed"""
        flush_output()
        
        mock_stdout_flush.assert_called_once()
        mock_stderr_flush.assert_called_once()
    
    @patch('sys.stdout.flush')
    @patch('sys.stderr.flush')
    def test_flush_output_exception(self, mock_stderr_flush, mock_stdout_flush):
        """Test flush_output function when flush operations raise exceptions"""
        # Make flush operations raise exceptions
        mock_stdout_flush.side_effect = Exception("Flush error")
        mock_stderr_flush.side_effect = Exception("Flush error")
        
        # Should not raise any exceptions
        flush_output()
        
        mock_stdout_flush.assert_called_once()
        # stderr flush should also be called even if it raises an exception
        mock_stderr_flush.assert_called_once()


if __name__ == "__main__":
    # Run tests if script is executed directly
    pytest.main([__file__, "-v"])
