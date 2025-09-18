#!/usr/bin/env python3

"""
Test suite for group_analyzer.py

This module tests the group analyzer functionality including:
- Utility functions (format_duration, logging functions)
- Argument parsing and validation
- Output directory computation
- Command building
- Subject analysis execution
- Group analysis coordination
- Path collection and validation
"""

import pytest
import os
import sys
import tempfile
import subprocess
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import argparse

# Add the analyzer directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'analyzer'))

# Import the module under test
try:
    import group_analyzer
except ImportError as e:
    # If relative imports fail, try absolute import
    import sys
    import os
    analyzer_path = os.path.join(os.path.dirname(__file__), '..', 'analyzer')
    if analyzer_path not in sys.path:
        sys.path.insert(0, analyzer_path)
    import group_analyzer


class TestUtilityFunctions:
    """Test utility functions like format_duration and logging functions."""
    
    def test_format_duration_seconds_only(self):
        """Test format_duration with seconds only."""
        result = group_analyzer.format_duration(45)
        assert result == "45s"
    
    def test_format_duration_minutes_and_seconds(self):
        """Test format_duration with minutes and seconds."""
        result = group_analyzer.format_duration(125)
        assert result == "2m 5s"
    
    def test_format_duration_hours_minutes_seconds(self):
        """Test format_duration with hours, minutes, and seconds."""
        result = group_analyzer.format_duration(3665)
        assert result == "1h 1m 5s"
    
    def test_format_duration_zero_seconds(self):
        """Test format_duration with zero seconds."""
        result = group_analyzer.format_duration(0)
        assert result == "0s"
    
    def test_format_duration_float_input(self):
        """Test format_duration with float input."""
        result = group_analyzer.format_duration(45.7)
        assert result == "45s"
    
    @patch('group_analyzer.SUMMARY_MODE', True)
    @patch('group_analyzer._group_start_time', None)
    @patch('builtins.print')
    def test_log_group_analysis_start(self, mock_print):
        """Test log_group_analysis_start function."""
        group_analyzer.log_group_analysis_start(3, "spherical (mesh)")
        mock_print.assert_called_once_with("\nBeginning group analysis for 3 subjects (spherical (mesh))")
    
    @patch('group_analyzer.SUMMARY_MODE', False)
    @patch('group_analyzer._group_start_time', None)
    @patch('builtins.print')
    def test_log_group_analysis_start_no_summary_mode(self, mock_print):
        """Test log_group_analysis_start function when not in summary mode."""
        group_analyzer.log_group_analysis_start(3, "spherical (mesh)")
        mock_print.assert_not_called()
    
    @patch('group_analyzer.SUMMARY_MODE', True)
    @patch('group_analyzer._group_start_time', 1000)
    @patch('time.time', return_value=1045)
    @patch('builtins.print')
    def test_log_group_analysis_complete_success(self, mock_print, mock_time):
        """Test log_group_analysis_complete function with successful completion."""
        group_analyzer.log_group_analysis_complete(3, 3, "/path/to/output")
        expected_calls = [
            "└─ Group analysis completed (3/3 subjects successful, Total: 45s)",
            "   Group results saved to: /path/to/output"
        ]
        assert mock_print.call_count == 2
        for call in expected_calls:
            assert any(call in str(print_call) for print_call in mock_print.call_args_list)
    
    @patch('group_analyzer.SUMMARY_MODE', True)
    @patch('group_analyzer._group_start_time', 1000)
    @patch('time.time', return_value=1045)
    @patch('builtins.print')
    def test_log_group_analysis_complete_with_failures(self, mock_print, mock_time):
        """Test log_group_analysis_complete function with some failures."""
        group_analyzer.log_group_analysis_complete(2, 3, "/path/to/output")
        expected_calls = [
            "└─ Group analysis completed with failures (2/3 subjects successful, Total: 45s)",
            "   Group results saved to: /path/to/output"
        ]
        assert mock_print.call_count == 2
        for call in expected_calls:
            assert any(call in str(print_call) for print_call in mock_print.call_args_list)
    
    @patch('group_analyzer.SUMMARY_MODE', True)
    @patch('builtins.print')
    def test_log_group_subject_status_complete(self, mock_print):
        """Test log_group_subject_status function for completed subject."""
        group_analyzer.log_group_subject_status("subj001", "complete", "2m 30s")
        mock_print.assert_called_once_with("├─ Subject subj001: ✓ Complete (2m 30s)")
    
    @patch('group_analyzer.SUMMARY_MODE', True)
    @patch('builtins.print')
    def test_log_group_subject_status_failed(self, mock_print):
        """Test log_group_subject_status function for failed subject."""
        group_analyzer.log_group_subject_status("subj001", "failed", "1m 15s", "Error message")
        mock_print.assert_called_once_with("├─ Subject subj001: ✗ Failed (1m 15s) - Error message")


class TestArgumentParser:
    """Test argument parser setup and validation."""
    
    def test_setup_parser(self):
        """Test setup_parser function."""
        parser = group_analyzer.setup_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        
        # Test that required arguments are present
        args = parser.parse_args([
            '--space', 'mesh',
            '--analysis_type', 'spherical',
            '--coordinates', '10', '20', '30',
            '--radius', '5.0',
            '--subject', 'subj001', '/path/to/m2m', '/path/to/field.msh',
            '--output_dir', '/path/to/output'
        ])
        assert args.space == 'mesh'
        assert args.analysis_type == 'spherical'
        assert args.coordinates == ['10', '20', '30']
        assert args.radius == 5.0
        assert args.subject == [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        assert args.output_dir == '/path/to/output'
    
    def test_parser_optional_arguments(self):
        """Test parser with optional arguments."""
        parser = group_analyzer.setup_parser()
        args = parser.parse_args([
            '--space', 'voxel',
            '--analysis_type', 'cortical',
            '--region', 'prefrontal',
            '--subject', 'subj001', '/path/to/m2m', '/path/to/field.nii.gz', '/path/to/atlas.nii.gz',
            '--output_dir', '/path/to/output',
            '--quiet',
            '--visualize',
            '--no-compare'
        ])
        assert args.space == 'voxel'
        assert args.analysis_type == 'cortical'
        assert args.region == 'prefrontal'
        assert args.quiet is True
        assert args.visualize is True
        assert args.no_compare is True


class TestArgumentValidation:
    """Test argument validation function."""
    
    def test_validate_args_spherical_valid(self):
        """Test validate_args with valid spherical analysis arguments."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        args.space = 'mesh'
        
        with patch('os.path.isdir', return_value=True), \
             patch('os.path.exists', return_value=True):
            # Should not raise any exception
            group_analyzer.validate_args(args)
    
    def test_validate_args_no_subjects(self):
        """Test validate_args with no subjects."""
        args = MagicMock()
        args.subject = []
        
        with pytest.raises(ValueError, match="At least one --subject must be specified"):
            group_analyzer.validate_args(args)
    
    def test_validate_args_spherical_missing_coordinates(self):
        """Test validate_args with missing coordinates for spherical analysis."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        args.analysis_type = 'spherical'
        args.coordinates = None
        args.radius = 5.0
        
        with pytest.raises(ValueError, match="Coordinates are required for spherical analysis"):
            group_analyzer.validate_args(args)
    
    def test_validate_args_spherical_missing_radius(self):
        """Test validate_args with missing radius for spherical analysis."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = None
        
        with pytest.raises(ValueError, match="Radius is required for spherical analysis"):
            group_analyzer.validate_args(args)
    
    def test_validate_args_spherical_wrong_subject_args_count(self):
        """Test validate_args with wrong number of subject arguments for spherical analysis."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m']]  # Missing field_path
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        
        with pytest.raises(ValueError, match="Subject 1: Spherical analysis requires exactly 3 arguments"):
            group_analyzer.validate_args(args)
    
    def test_validate_args_cortical_mesh_missing_atlas_name(self):
        """Test validate_args with missing atlas name for mesh cortical analysis."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        args.analysis_type = 'cortical'
        args.space = 'mesh'
        args.atlas_name = None
        args.region = 'prefrontal'
        
        with pytest.raises(ValueError, match="Atlas name is required for mesh-based cortical analysis"):
            group_analyzer.validate_args(args)
    
    def test_validate_args_cortical_voxel_wrong_subject_args_count(self):
        """Test validate_args with wrong number of subject arguments for voxel cortical analysis."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.nii.gz']]  # Missing atlas_path
        args.analysis_type = 'cortical'
        args.space = 'voxel'
        args.region = 'prefrontal'
        
        with pytest.raises(ValueError, match="Subject 1: Voxel cortical analysis requires exactly 4 arguments"):
            group_analyzer.validate_args(args)
    
    def test_validate_args_cortical_missing_region_and_whole_head(self):
        """Test validate_args with missing region and whole_head flag for cortical analysis."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        args.analysis_type = 'cortical'
        args.space = 'mesh'
        args.atlas_name = 'DK40'
        args.region = None
        args.whole_head = False
        
        with pytest.raises(ValueError, match="Either --whole_head flag or --region must be specified for cortical analysis"):
            group_analyzer.validate_args(args)
    
    def test_validate_args_m2m_directory_not_found(self):
        """Test validate_args with non-existent m2m directory."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        args.space = 'mesh'
        
        with patch('os.path.isdir', return_value=False):
            with pytest.raises(ValueError, match="Subject subj001 m2m directory not found"):
                group_analyzer.validate_args(args)
    
    def test_validate_args_field_file_not_found(self):
        """Test validate_args with non-existent field file."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        args.space = 'mesh'
        
        with patch('os.path.isdir', return_value=True), \
             patch('os.path.exists', side_effect=lambda x: x != '/path/to/field.msh'):
            with pytest.raises(ValueError, match="Subject subj001 field file not found"):
                group_analyzer.validate_args(args)
    
    def test_validate_args_voxel_cortical_atlas_not_found(self):
        """Test validate_args with non-existent atlas file for voxel cortical analysis."""
        args = MagicMock()
        args.subject = [['subj001', '/path/to/m2m', '/path/to/field.nii.gz', '/path/to/atlas.nii.gz']]
        args.analysis_type = 'cortical'
        args.space = 'voxel'
        args.region = 'prefrontal'
        
        with patch('os.path.isdir', return_value=True), \
             patch('os.path.exists', side_effect=lambda x: x != '/path/to/atlas.nii.gz'):
            with pytest.raises(ValueError, match="Subject subj001 atlas file not found"):
                group_analyzer.validate_args(args)


class TestOutputDirectoryComputation:
    """Test output directory computation functions."""
    
    def test_compute_subject_output_dir_spherical_mesh(self):
        """Test compute_subject_output_dir for spherical mesh analysis."""
        args = MagicMock()
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        
        subject_args = ['subj001', '/path/to/m2m', '/path/to/Simulations/montage1/TI/mesh/field.msh']
        
        with patch('os.path.join') as mock_join, \
             patch('os.makedirs') as mock_makedirs:
            mock_join.side_effect = lambda *args: '/'.join(args)
            
            result = group_analyzer.compute_subject_output_dir(args, subject_args)
            
            # Should create directory with proper structure
            assert 'Simulations' in result
            assert 'montage1' in result
            assert 'Analyses' in result
            assert 'Mesh' in result
            assert 'sphere_x10_y20_z30_r5.0' in result
            mock_makedirs.assert_called_once()
    
    def test_compute_subject_output_dir_cortical_voxel_whole_head(self):
        """Test compute_subject_output_dir for cortical voxel whole head analysis."""
        args = MagicMock()
        args.space = 'voxel'
        args.analysis_type = 'cortical'
        args.whole_head = True
        
        subject_args = ['subj001', '/path/to/m2m', '/path/to/Simulations/montage1/TI/voxel/field.nii.gz', '/path/to/atlas.nii.gz']
        
        with patch('os.path.join') as mock_join, \
             patch('os.makedirs') as mock_makedirs, \
             patch('os.path.basename', return_value='atlas.nii.gz'), \
             patch('os.path.splitext', return_value=('atlas', '.nii.gz')):
            mock_join.side_effect = lambda *args: '/'.join(args)
            
            result = group_analyzer.compute_subject_output_dir(args, subject_args)
            
            assert 'Voxel' in result
            assert 'whole_head_atlas' in result
            mock_makedirs.assert_called_once()
    
    def test_compute_subject_output_dir_fallback(self):
        """Test compute_subject_output_dir fallback when Simulations not found."""
        args = MagicMock()
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        
        subject_args = ['subj001', '/path/to/m2m', '/path/to/field.msh']  # No Simulations in path
        
        with patch('os.path.join') as mock_join, \
             patch('os.makedirs') as mock_makedirs, \
             patch('os.path.dirname', return_value='/path/to'):
            mock_join.side_effect = lambda *args: '/'.join(args)
            
            result = group_analyzer.compute_subject_output_dir(args, subject_args)
            
            assert 'fallback_subj001' in result
            mock_makedirs.assert_called_once()


class TestCommandBuilding:
    """Test command building functions."""
    
    def test_build_main_analyzer_command_spherical_mesh(self):
        """Test build_main_analyzer_command for spherical mesh analysis."""
        args = MagicMock()
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        args.quiet = False
        
        subject_args = ['subj001', '/path/to/m2m', '/path/to/Simulations/montage1/TI/mesh/field.msh']
        subject_output_dir = '/path/to/output'
        
        with patch('group_analyzer.group_logger', None), \
             patch('group_analyzer.mni2subject_coords', None), \
             patch('pathlib.Path') as mock_path:
            mock_path.return_value.parent = Path('/path/to/analyzer')
            mock_path.return_value.__truediv__ = lambda self, other: Path(f'/path/to/analyzer/{other}')
            
            cmd = group_analyzer.build_main_analyzer_command(args, subject_args, subject_output_dir)
            
            assert 'simnibs_python' in cmd
            assert 'main_analyzer.py' in cmd[1]
            assert '--m2m_subject_path' in cmd
            assert '/path/to/m2m' in cmd
            assert '--montage_name' in cmd
            assert 'montage1' in cmd
            assert '--space' in cmd
            assert 'mesh' in cmd
            assert '--analysis_type' in cmd
            assert 'spherical' in cmd
            assert '--coordinates' in cmd
            assert '10' in cmd
            assert '20' in cmd
            assert '30' in cmd
            assert '--radius' in cmd
            assert '5.0' in cmd
            assert '--output_dir' in cmd
            assert '/path/to/output' in cmd
            assert '--visualize' in cmd
    
    def test_build_main_analyzer_command_cortical_voxel(self):
        """Test build_main_analyzer_command for cortical voxel analysis."""
        args = MagicMock()
        args.space = 'voxel'
        args.analysis_type = 'cortical'
        args.region = 'prefrontal'
        args.whole_head = False
        args.quiet = False
        
        subject_args = ['subj001', '/path/to/m2m', '/path/to/field.nii.gz', '/path/to/atlas.nii.gz']
        subject_output_dir = '/path/to/output'
        
        with patch('group_analyzer.group_logger', None), \
             patch('pathlib.Path') as mock_path:
            mock_path.return_value.parent = Path('/path/to/analyzer')
            mock_path.return_value.__truediv__ = lambda self, other: Path(f'/path/to/analyzer/{other}')
            
            cmd = group_analyzer.build_main_analyzer_command(args, subject_args, subject_output_dir)
            
            assert 'simnibs_python' in cmd
            assert '--field_path' in cmd
            assert '/path/to/field.nii.gz' in cmd
            assert '--atlas_path' in cmd
            assert '/path/to/atlas.nii.gz' in cmd
            assert '--region' in cmd
            assert 'prefrontal' in cmd
    
    def test_build_main_analyzer_command_with_mni_coords(self):
        """Test build_main_analyzer_command with MNI coordinate transformation."""
        args = MagicMock()
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        args.use_mni_coords = True
        args.quiet = False
        
        subject_args = ['subj001', '/path/to/m2m', '/path/to/field.msh']
        subject_output_dir = '/path/to/output'
        
        mock_mni2subject_coords = MagicMock(return_value=[15, 25, 35])
        
        with patch('group_analyzer.group_logger', None), \
             patch('group_analyzer.mni2subject_coords', mock_mni2subject_coords), \
             patch('pathlib.Path') as mock_path:
            mock_path.return_value.parent = Path('/path/to/analyzer')
            mock_path.return_value.__truediv__ = lambda self, other: Path(f'/path/to/analyzer/{other}')
            
            cmd = group_analyzer.build_main_analyzer_command(args, subject_args, subject_output_dir)
            
            # Should use transformed coordinates
            assert '--coordinates' in cmd
            assert '15' in cmd
            assert '25' in cmd
            assert '35' in cmd
            mock_mni2subject_coords.assert_called_once_with([10, 20, 30], '/path/to/m2m')
    
    def test_build_main_analyzer_command_mni_coords_error(self):
        """Test build_main_analyzer_command with MNI coordinate transformation error."""
        args = MagicMock()
        args.space = 'mesh'
        args.analysis_type = 'spherical'
        args.coordinates = [10, 20, 30]
        args.radius = 5.0
        args.use_mni_coords = True
        args.quiet = False
        
        subject_args = ['subj001', '/path/to/m2m', '/path/to/field.msh']
        subject_output_dir = '/path/to/output'
        
        mock_mni2subject_coords = MagicMock(side_effect=Exception("Transformation failed"))
        mock_logger = MagicMock()
        
        with patch('group_analyzer.group_logger', mock_logger), \
             patch('group_analyzer.mni2subject_coords', mock_mni2subject_coords), \
             patch('pathlib.Path') as mock_path:
            mock_path.return_value.parent = Path('/path/to/analyzer')
            mock_path.return_value.__truediv__ = lambda self, other: Path(f'/path/to/analyzer/{other}')
            
            with pytest.raises(RuntimeError, match="Failed to transform MNI coordinates for subject subj001"):
                group_analyzer.build_main_analyzer_command(args, subject_args, subject_output_dir)
            
            mock_logger.error.assert_called_once()


class TestSubjectAnalysis:
    """Test subject analysis execution."""
    
    @patch('group_analyzer.compute_subject_output_dir')
    @patch('group_analyzer.build_main_analyzer_command')
    @patch('subprocess.run')
    def test_run_subject_analysis_success(self, mock_run, mock_build_cmd, mock_compute_dir):
        """Test run_subject_analysis with successful execution."""
        args = MagicMock()
        args.quiet = False
        subject_args = ['subj001', '/path/to/m2m', '/path/to/field.msh']
        
        mock_compute_dir.return_value = '/path/to/output'
        mock_build_cmd.return_value = ['simnibs_python', 'main_analyzer.py', '--arg1', 'value1']
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Analysis completed successfully"
        
        with patch('group_analyzer.group_logger', None), \
             patch('time.time', side_effect=[1000, 1045]):
            success, output_dir = group_analyzer.run_subject_analysis(args, subject_args)
            
            assert success is True
            assert output_dir == '/path/to/output'
            mock_compute_dir.assert_called_once_with(args, subject_args)
            mock_build_cmd.assert_called_once_with(args, subject_args, '/path/to/output')
            mock_run.assert_called_once()
    
    @patch('group_analyzer.compute_subject_output_dir')
    @patch('group_analyzer.build_main_analyzer_command')
    @patch('subprocess.run')
    def test_run_subject_analysis_failure(self, mock_run, mock_build_cmd, mock_compute_dir):
        """Test run_subject_analysis with failed execution."""
        args = MagicMock()
        args.quiet = False
        subject_args = ['subj001', '/path/to/m2m', '/path/to/field.msh']
        
        mock_compute_dir.return_value = '/path/to/output'
        mock_build_cmd.return_value = ['simnibs_python', 'main_analyzer.py', '--arg1', 'value1']
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = "Error: Analysis failed"
        
        with patch('group_analyzer.group_logger', None), \
             patch('time.time', side_effect=[1000, 1045]):
            success, output_dir = group_analyzer.run_subject_analysis(args, subject_args)
            
            assert success is False
            assert output_dir == ""
            mock_run.assert_called_once()
    
    @patch('group_analyzer.compute_subject_output_dir')
    @patch('group_analyzer.build_main_analyzer_command')
    @patch('subprocess.Popen')
    def test_run_subject_analysis_quiet_mode(self, mock_popen, mock_build_cmd, mock_compute_dir):
        """Test run_subject_analysis in quiet mode with streaming output."""
        args = MagicMock()
        args.quiet = True
        subject_args = ['subj001', '/path/to/m2m', '/path/to/field.msh']
        
        mock_compute_dir.return_value = '/path/to/output'
        mock_build_cmd.return_value = ['simnibs_python', 'main_analyzer.py', '--arg1', 'value1']
        
        # Mock Popen for streaming output - use a generator that yields values
        def mock_readline():
            lines = [
                "Beginning analysis for subject: subj001\n",
                "├─ Step 1: Processing...\n",
                "└─ Step 2: Complete\n",
                ""  # Empty line to end the loop
            ]
            for line in lines:
                yield line
            while True:  # Keep yielding empty strings
                yield ""
        
        mock_proc = MagicMock()
        mock_proc.stdout.readline = MagicMock(side_effect=mock_readline())
        mock_proc.poll.side_effect = [None, None, None, 0]  # Process ends on 4th call
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        
        with patch('group_analyzer.group_logger', None), \
             patch('time.time', side_effect=[1000, 1045]), \
             patch('builtins.print'):
            success, output_dir = group_analyzer.run_subject_analysis(args, subject_args)
            
            assert success is True
            assert output_dir == '/path/to/output'
            mock_popen.assert_called_once()


class TestPathCollection:
    """Test analysis path collection and validation."""
    
    def test_collect_analysis_paths_success(self):
        """Test collect_analysis_paths with valid directories containing CSV files."""
        successful_dirs = ['/path/to/analysis1', '/path/to/analysis2']
        
        with patch('os.path.isdir', return_value=True), \
             patch('os.listdir', side_effect=[['file1.csv', 'file2.txt'], ['results.csv']]), \
             patch('group_analyzer.group_logger', None):
            result = group_analyzer.collect_analysis_paths(successful_dirs)
            
            assert result == successful_dirs
    
    def test_collect_analysis_paths_no_csv(self):
        """Test collect_analysis_paths with directories containing no CSV files."""
        successful_dirs = ['/path/to/analysis1', '/path/to/analysis2']
        
        with patch('os.path.isdir', return_value=True), \
             patch('os.listdir', return_value=['file1.txt', 'file2.log']), \
             patch('group_analyzer.group_logger', None):
            result = group_analyzer.collect_analysis_paths(successful_dirs)
            
            assert result == []
    
    def test_collect_analysis_paths_invalid_directories(self):
        """Test collect_analysis_paths with invalid directories."""
        successful_dirs = ['/path/to/analysis1', '/path/to/analysis2']
        
        with patch('os.path.isdir', return_value=False), \
             patch('group_analyzer.group_logger', None):
            result = group_analyzer.collect_analysis_paths(successful_dirs)
            
            assert result == []


class TestGroupAnalysis:
    """Test group analysis coordination functions."""
    
    @patch('group_analyzer.run_all_group_comparisons')
    def test_run_comprehensive_group_analysis_success(self, mock_run_comparisons):
        """Test run_comprehensive_group_analysis with successful execution."""
        analysis_paths = ['/path/to/analysis1', '/path/to/analysis2']
        project_name = 'test_project'
        expected_output = '/path/to/group_results'
        
        mock_run_comparisons.return_value = expected_output
        
        with patch('group_analyzer.group_logger', None):
            result = group_analyzer.run_comprehensive_group_analysis(analysis_paths, project_name)
            
            assert result == expected_output
            mock_run_comparisons.assert_called_once_with(analysis_paths, project_name)
    
    @patch('group_analyzer.run_all_group_comparisons')
    def test_run_comprehensive_group_analysis_empty_paths(self, mock_run_comparisons):
        """Test run_comprehensive_group_analysis with empty analysis paths."""
        analysis_paths = []
        
        with patch('group_analyzer.group_logger', None):
            result = group_analyzer.run_comprehensive_group_analysis(analysis_paths)
            
            assert result == ""
            mock_run_comparisons.assert_not_called()
    
    @patch('group_analyzer.run_all_group_comparisons')
    def test_run_comprehensive_group_analysis_exception(self, mock_run_comparisons):
        """Test run_comprehensive_group_analysis with exception."""
        analysis_paths = ['/path/to/analysis1']
        mock_run_comparisons.side_effect = Exception("Group analysis failed")
        
        with patch('group_analyzer.group_logger', None):
            result = group_analyzer.run_comprehensive_group_analysis(analysis_paths)
            
            assert result == ""


class TestGroupSubfolderName:
    """Test group subfolder name determination."""
    
    def test_determine_group_subfolder_name_spherical(self):
        """Test determine_group_subfolder_name for spherical analysis."""
        args = MagicMock()
        args.analysis_type = 'spherical'
        args.radius = 5.0
        
        first_subject_args = ['subj001', '/path/to/m2m', '/path/to/Simulations/montage1/TI/mesh/field.msh']
        
        with patch('pathlib.Path') as mock_path:
            mock_path.return_value.parts = ('/path/to/Simulations/montage1/TI/mesh/field.msh').split('/')
            
            result = group_analyzer.determine_group_subfolder_name(args, first_subject_args)
            
            assert result == "montage1_sphere_r5.0"
    
    def test_determine_group_subfolder_name_cortical_mesh_whole_head(self):
        """Test determine_group_subfolder_name for cortical mesh whole head analysis."""
        args = MagicMock()
        args.analysis_type = 'cortical'
        args.space = 'mesh'
        args.atlas_name = 'DK40'
        args.whole_head = True
        
        first_subject_args = ['subj001', '/path/to/m2m', '/path/to/Simulations/montage1/TI/mesh/field.msh']
        
        with patch('pathlib.Path') as mock_path:
            mock_path.return_value.parts = ('/path/to/Simulations/montage1/TI/mesh/field.msh').split('/')
            
            result = group_analyzer.determine_group_subfolder_name(args, first_subject_args)
            
            assert result == "montage1_whole_head_DK40"
    
    def test_determine_group_subfolder_name_cortical_voxel_region(self):
        """Test determine_group_subfolder_name for cortical voxel region analysis."""
        args = MagicMock()
        args.analysis_type = 'cortical'
        args.space = 'voxel'
        args.region = 'prefrontal'
        args.whole_head = False
        
        first_subject_args = ['subj001', '/path/to/m2m', '/path/to/Simulations/montage1/TI/voxel/field.nii.gz', '/path/to/atlas.nii.gz']
        
        with patch('pathlib.Path') as mock_path:
            mock_path.return_value.parts = ('/path/to/Simulations/montage1/TI/voxel/field.nii.gz').split('/')
            
            result = group_analyzer.determine_group_subfolder_name(args, first_subject_args)
            
            assert result == "montage1_prefrontal"
    
    def test_determine_group_subfolder_name_fallback_filename(self):
        """Test determine_group_subfolder_name with fallback to filename extraction."""
        args = MagicMock()
        args.analysis_type = 'spherical'
        args.radius = 5.0
        
        first_subject_args = ['subj001', '/path/to/m2m', '/path/to/field_TI.msh']
        
        with patch('pathlib.Path') as mock_path:
            mock_path.return_value.parts = ('/path/to/field_TI.msh').split('/')
            mock_path.return_value.stem = 'field_TI'
            
            result = group_analyzer.determine_group_subfolder_name(args, first_subject_args)
            
            assert result == "field_sphere_r5.0"


class TestGroupOutputDirectory:
    """Test group output directory creation."""
    
    @patch('group_analyzer._extract_project_name')
    def test_create_group_output_directory(self, mock_extract_project):
        """Test create_group_output_directory function."""
        first_subject_path = '/path/to/subject/m2m'
        expected_project = 'test_project'
        mock_extract_project.return_value = expected_project
        
        with patch('group_analyzer.group_logger', None):
            result = group_analyzer.create_group_output_directory(first_subject_path)
            
            assert result == f"/mnt/{expected_project}/derivatives/SimNIBS"
            mock_extract_project.assert_called_once_with(first_subject_path)


class TestMainFunction:
    """Test main function execution."""
    
    @patch('group_analyzer.setup_parser')
    @patch('group_analyzer.validate_args')
    @patch('group_analyzer.create_group_output_directory')
    @patch('group_analyzer._extract_project_name')
    @patch('group_analyzer.setup_group_logger')
    @patch('group_analyzer.run_subject_analysis')
    @patch('group_analyzer.collect_analysis_paths')
    @patch('group_analyzer.run_comprehensive_group_analysis')
    @patch('os.makedirs')
    def test_main_successful_analysis(self, mock_makedirs, mock_run_group, mock_collect, 
                                    mock_run_subject, mock_setup_logger, mock_extract_project,
                                    mock_create_dir, mock_validate, mock_setup_parser):
        """Test main function with successful analysis."""
        # Setup mocks
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        mock_args.quiet = False
        mock_args.no_compare = False
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        mock_create_dir.return_value = '/path/to/group_dir'
        mock_extract_project.return_value = 'test_project'
        mock_logger = MagicMock()
        mock_setup_logger.return_value = mock_logger
        
        mock_run_subject.return_value = (True, '/path/to/subject_output')
        mock_collect.return_value = ['/path/to/subject_output']
        mock_run_group.return_value = '/path/to/group_results'
        
        with patch('group_analyzer.group_logger', mock_logger):
            group_analyzer.main()
            
            mock_validate.assert_called_once_with(mock_args)
            mock_create_dir.assert_called_once()
            mock_setup_logger.assert_called_once()
            mock_run_subject.assert_called_once()
            mock_collect.assert_called_once()
            mock_run_group.assert_called_once()
    
    @patch('group_analyzer.setup_parser')
    @patch('group_analyzer.validate_args')
    def test_main_validation_error(self, mock_validate, mock_setup_parser):
        """Test main function with validation error."""
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        mock_validate.side_effect = ValueError("Validation failed")
        
        with patch('group_analyzer.group_logger', None), \
             patch('sys.exit') as mock_exit:
            group_analyzer.main()
            
            mock_exit.assert_called_once_with(1)
    
    @patch('group_analyzer.setup_parser')
    @patch('group_analyzer.validate_args')
    @patch('group_analyzer.create_group_output_directory')
    @patch('group_analyzer._extract_project_name')
    @patch('group_analyzer.setup_group_logger')
    @patch('group_analyzer.run_subject_analysis')
    @patch('os.makedirs')
    def test_main_no_compare_flag(self, mock_makedirs, mock_run_subject, mock_setup_logger,
                                 mock_extract_project, mock_create_dir, mock_validate, mock_setup_parser):
        """Test main function with --no-compare flag."""
        # Setup mocks
        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.subject = [['subj001', '/path/to/m2m', '/path/to/field.msh']]
        mock_args.quiet = False
        mock_args.no_compare = True
        mock_parser.parse_args.return_value = mock_args
        mock_setup_parser.return_value = mock_parser
        
        mock_create_dir.return_value = '/path/to/group_dir'
        mock_extract_project.return_value = 'test_project'
        mock_logger = MagicMock()
        mock_setup_logger.return_value = mock_logger
        
        mock_run_subject.return_value = (True, '/path/to/subject_output')
        
        with patch('group_analyzer.group_logger', mock_logger):
            group_analyzer.main()
            
            mock_validate.assert_called_once_with(mock_args)
            mock_run_subject.assert_called_once()
            # Should not call group comparison functions
            mock_logger.debug.assert_called()
            assert any("Group comparison was skipped" in str(call) for call in mock_logger.debug.call_args_list)


if __name__ == "__main__":
    pytest.main([__file__])
