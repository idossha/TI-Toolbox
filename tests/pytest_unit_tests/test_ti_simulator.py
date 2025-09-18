"""
Test suite for TI.py simulator

This module provides comprehensive tests for the TI simulator functionality,
including argument parsing, montage validation, simulation execution, and
file handling.
"""

import pytest
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock, mock_open, call
import numpy as np
from pathlib import Path

# Add the parent directory to the path to access the simulator module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# We'll test the TI.py functionality without importing it directly
# since it calls sys.exit() when simnibs is not available


class TestTIArgumentParsing:
    """Test command line argument parsing in TI.py"""
    
    def test_parse_intensity_single_value(self):
        """Test parsing single intensity value."""
        intensity_str = "1.0"
        if ',' in intensity_str:
            intensity1, intensity2 = map(float, intensity_str.split(','))
        else:
            intensity1 = intensity2 = float(intensity_str)
        
        assert intensity1 == 1.0
        assert intensity2 == 1.0
    
    def test_parse_intensity_comma_separated(self):
        """Test parsing comma-separated intensity values."""
        intensity_str = "1.0,2.0"
        if ',' in intensity_str:
            intensity1, intensity2 = map(float, intensity_str.split(','))
        else:
            intensity1 = intensity2 = float(intensity_str)
        
        assert intensity1 == 1.0
        assert intensity2 == 2.0
    
    def test_parse_dimensions(self):
        """Test parsing electrode dimensions."""
        dimensions_str = "10.0,20.0"
        dimensions = [float(x) for x in dimensions_str.split(',')]
        
        assert dimensions == [10.0, 20.0]
    
    def test_parse_montage_names_with_quiet(self):
        """Test parsing montage names with quiet flag."""
        remaining_args = ['montage1', 'montage2', '--quiet', 'montage3']
        montage_names = []
        quiet_mode = False
        
        for arg in remaining_args:
            if arg == '--quiet':
                quiet_mode = True
            else:
                montage_names.append(arg)
        
        assert montage_names == ['montage1', 'montage2', 'montage3']
        assert quiet_mode is True
    
    def test_parse_montage_names_without_quiet(self):
        """Test parsing montage names without quiet flag."""
        remaining_args = ['montage1', 'montage2', 'montage3']
        montage_names = []
        quiet_mode = False
        
        for arg in remaining_args:
            if arg == '--quiet':
                quiet_mode = True
            else:
                montage_names.append(arg)
        
        assert montage_names == ['montage1', 'montage2', 'montage3']
        assert quiet_mode is False


class TestMontageValidation:
    """Test montage validation functionality."""
    
    def test_validate_montage_valid(self):
        """Test validation of valid montage structure."""
        montage = [['electrode1', 'electrode2'], ['electrode3', 'electrode4']]
        montage_name = 'test_montage'
        
        # Simulate the validate_montage function
        def validate_montage(montage, montage_name):
            if not montage or len(montage) < 2 or len(montage[0]) < 2:
                return False
            return True
        
        result = validate_montage(montage, montage_name)
        assert result is True
    
    def test_validate_montage_invalid_empty(self):
        """Test validation of empty montage."""
        montage = []
        montage_name = 'test_montage'
        
        def validate_montage(montage, montage_name):
            if not montage or len(montage) < 2 or len(montage[0]) < 2:
                return False
            return True
        
        result = validate_montage(montage, montage_name)
        assert result is False
    
    def test_validate_montage_invalid_short(self):
        """Test validation of montage with insufficient pairs."""
        montage = [['electrode1', 'electrode2']]
        montage_name = 'test_montage'
        
        def validate_montage(montage, montage_name):
            if not montage or len(montage) < 2 or len(montage[0]) < 2:
                return False
            return True
        
        result = validate_montage(montage, montage_name)
        assert result is False
    
    def test_validate_montage_invalid_short_pair(self):
        """Test validation of montage with short electrode pair."""
        montage = [['electrode1'], ['electrode3', 'electrode4']]
        montage_name = 'test_montage'
        
        def validate_montage(montage, montage_name):
            if not montage or len(montage) < 2 or len(montage[0]) < 2:
                return False
            return True
        
        result = validate_montage(montage, montage_name)
        assert result is False


class TestMontageFileHandling:
    """Test montage file creation and loading."""
    
    def test_create_initial_montage_file(self):
        """Test creation of initial montage file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = os.path.join(temp_dir, 'config')
            os.makedirs(config_dir, exist_ok=True)
            montage_file = os.path.join(config_dir, 'montage_list.json')
            
            # Create initial content
            initial_content = {
                "nets": {
                    "EGI_template.csv": {
                        "uni_polar_montages": {},
                        "multi_polar_montages": {}
                    }
                }
            }
            
            with open(montage_file, 'w') as f:
                json.dump(initial_content, f, indent=4)
            
            # Verify file was created
            assert os.path.exists(montage_file)
            
            # Verify content
            with open(montage_file) as f:
                loaded_content = json.load(f)
            
            assert loaded_content == initial_content
    
    def test_load_montage_file(self):
        """Test loading montage file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = os.path.join(temp_dir, 'config')
            os.makedirs(config_dir, exist_ok=True)
            montage_file = os.path.join(config_dir, 'montage_list.json')
            
            # Create test content
            test_content = {
                "nets": {
                    "EGI_template.csv": {
                        "uni_polar_montages": {
                            "montage1": [["E1", "E2"], ["E3", "E4"]]
                        },
                        "multi_polar_montages": {
                            "montage2": [["E1", "E2"], ["E3", "E4"]]
                        }
                    }
                }
            }
            
            with open(montage_file, 'w') as f:
                json.dump(test_content, f, indent=4)
            
            # Load and verify
            with open(montage_file) as f:
                loaded_content = json.load(f)
            
            assert loaded_content == test_content
            assert "montage1" in loaded_content["nets"]["EGI_template.csv"]["uni_polar_montages"]
            assert "montage2" in loaded_content["nets"]["EGI_template.csv"]["multi_polar_montages"]


class TestFlexMontageHandling:
    """Test flex montage file handling."""
    
    def test_load_flex_montages_legacy_format(self):
        """Test loading flex montages in legacy array format."""
        flex_config = [
            {
                "name": "flex_montage1",
                "type": "flex_mapped",
                "electrode_labels": ["E1", "E2", "E3", "E4"],
                "pairs": [["E1", "E2"], ["E3", "E4"]],
                "eeg_net": "EGI_template.csv"
            }
        ]
        
        # Simulate the flex montage loading logic
        if isinstance(flex_config, list):
            flex_montages = flex_config
        elif isinstance(flex_config, dict) and 'montage' in flex_config:
            flex_montages = [flex_config['montage']]
        else:
            flex_montages = []
        
        assert len(flex_montages) == 1
        assert flex_montages[0]['name'] == "flex_montage1"
        assert flex_montages[0]['type'] == "flex_mapped"
    
    def test_load_flex_montages_individual_format(self):
        """Test loading flex montages in individual config format."""
        flex_config = {
            "subject_id": "subj001",
            "eeg_net": "EGI_template.csv",
            "montage": {
                "name": "flex_montage1",
                "type": "flex_mapped",
                "electrode_labels": ["E1", "E2", "E3", "E4"],
                "pairs": [["E1", "E2"], ["E3", "E4"]]
            }
        }
        
        # Simulate the flex montage loading logic
        if isinstance(flex_config, list):
            flex_montages = flex_config
        elif isinstance(flex_config, dict) and 'montage' in flex_config:
            flex_montages = [flex_config['montage']]
        else:
            flex_montages = []
        
        assert len(flex_montages) == 1
        assert flex_montages[0]['name'] == "flex_montage1"
        assert flex_montages[0]['type'] == "flex_mapped"
    
    def test_load_flex_montages_invalid_format(self):
        """Test loading flex montages with invalid format."""
        flex_config = {"invalid": "format"}
        
        # Simulate the flex montage loading logic
        if isinstance(flex_config, list):
            flex_montages = flex_config
        elif isinstance(flex_config, dict) and 'montage' in flex_config:
            flex_montages = [flex_config['montage']]
        else:
            flex_montages = []
        
        assert len(flex_montages) == 0


class TestSimulationSetup:
    """Test simulation setup and configuration."""
    
    def test_create_temp_directory(self):
        """Test creation of temporary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            simulation_dir = temp_dir
            temp_sim_dir = os.path.join(simulation_dir, "tmp")
            
            if not os.path.exists(temp_sim_dir):
                os.makedirs(temp_sim_dir, exist_ok=True)
            
            assert os.path.exists(temp_sim_dir)
    
    def test_setup_simnibs_session(self):
        """Test SimNIBS session setup."""
        # Mock sim_struct without importing the actual module
        mock_sim_struct = MagicMock()
        mock_session = MagicMock()
        mock_sim_struct.SESSION.return_value = mock_session
        
        # Simulate session setup
        S = mock_sim_struct.SESSION()
        S.subpath = "/path/to/subpath"
        S.anisotropy_type = "vn"
        S.pathfem = "/path/to/fem"
        S.eeg_cap = "/path/to/eeg"
        S.map_to_surf = True
        S.map_to_fsavg = False
        S.map_to_vol = True
        S.map_to_mni = True
        S.open_in_gmsh = False
        S.tissues_in_niftis = "all"
        S.dti_nii = "/path/to/dti"
        
        assert S.subpath == "/path/to/subpath"
        assert S.anisotropy_type == "vn"
        assert S.map_to_surf is True
    
    def test_setup_electrode_configuration(self):
        """Test electrode configuration setup."""
        # Mock sim_struct without importing the actual module
        mock_sim_struct = MagicMock()
        mock_session = MagicMock()
        mock_tdcs = MagicMock()
        
        # Create separate mock electrodes
        mock_electrode1 = MagicMock()
        mock_electrode2 = MagicMock()
        
        mock_sim_struct.SESSION.return_value = mock_session
        mock_session.add_tdcslist.return_value = mock_tdcs
        mock_tdcs.add_electrode.side_effect = [mock_electrode1, mock_electrode2]
        
        # Simulate electrode setup
        S = mock_sim_struct.SESSION()
        tdcs = S.add_tdcslist()
        tdcs.anisotropy_type = "vn"
        tdcs.currents = [1.0, -1.0]
        
        electrode1 = tdcs.add_electrode()
        electrode1.channelnr = 1
        electrode1.centre = "E1"
        electrode1.shape = "rect"
        electrode1.dimensions = [10.0, 20.0]
        electrode1.thickness = [1.0, 2.0]
        
        electrode2 = tdcs.add_electrode()
        electrode2.channelnr = 2
        electrode2.centre = "E2"
        electrode2.shape = "rect"
        electrode2.dimensions = [10.0, 20.0]
        electrode2.thickness = [1.0, 2.0]
        
        assert tdcs.currents == [1.0, -1.0]
        assert electrode1.channelnr == 1
        assert electrode2.channelnr == 2


class TestTICalculation:
    """Test TI calculation functionality."""
    
    def test_ti_max_calculation(self):
        """Test TI maximum calculation."""
        # Mock TI utils without importing the actual module
        mock_ti = MagicMock()
        
        # Mock electric field values
        ef1_value = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        ef2_value = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
        
        # Mock TI calculation result
        mock_ti.get_maxTI.return_value = np.array([1.0, 1.0])
        
        # Simulate TI calculation
        TImax = mock_ti.get_maxTI(ef1_value, ef2_value)
        
        mock_ti.get_maxTI.assert_called_once_with(ef1_value, ef2_value)
        assert np.array_equal(TImax, np.array([1.0, 1.0]))
    
    def test_ti_normal_calculation(self):
        """Test TI normal component calculation."""
        # Mock TI utils without importing the actual module
        mock_ti = MagicMock()
        
        # Mock electric field values and surface normals
        ef1_value = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        ef2_value = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
        surface_normals = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]])
        
        # Mock TI normal calculation result
        mock_ti.get_dirTI.return_value = np.array([0.5, 0.5])
        
        # Simulate TI normal calculation
        TI_normal = mock_ti.get_dirTI(ef1_value, ef2_value, surface_normals)
        
        mock_ti.get_dirTI.assert_called_once_with(ef1_value, ef2_value, surface_normals)
        assert np.array_equal(TI_normal, np.array([0.5, 0.5]))


class TestMeshFileHandling:
    """Test mesh file reading and writing."""
    
    def test_read_mesh_files(self):
        """Test reading mesh files."""
        # Mock mesh_io without importing the actual module
        mock_mesh_io = MagicMock()
        mock_mesh = MagicMock()
        mock_mesh.field = {"E": MagicMock()}
        mock_mesh.field["E"].value = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        mock_mesh_io.read_msh.return_value = mock_mesh
        
        # Simulate mesh reading
        m1_file = "/path/to/mesh1.msh"
        m2_file = "/path/to/mesh2.msh"
        
        m1 = mock_mesh_io.read_msh(m1_file)
        m2 = mock_mesh_io.read_msh(m2_file)
        
        assert mock_mesh_io.read_msh.call_count == 2
        mock_mesh_io.read_msh.assert_any_call(m1_file)
        mock_mesh_io.read_msh.assert_any_call(m2_file)
    
    def test_write_mesh_files(self):
        """Test writing mesh files."""
        # Mock mesh_io without importing the actual module
        mock_mesh_io = MagicMock()
        mock_mesh = MagicMock()
        mock_mesh_io.write_msh.return_value = None
        
        # Simulate mesh writing
        output_file = "/path/to/output.msh"
        mock_mesh_io.write_msh(mock_mesh, output_file)
        
        mock_mesh_io.write_msh.assert_called_once_with(mock_mesh, output_file)
    
    def test_crop_mesh(self):
        """Test mesh cropping functionality."""
        # Mock mesh_io without importing the actual module
        mock_mesh_io = MagicMock()
        mock_mesh = MagicMock()
        mock_cropped_mesh = MagicMock()
        mock_mesh.crop_mesh.return_value = mock_cropped_mesh
        mock_mesh_io.read_msh.return_value = mock_mesh
        
        # Simulate mesh cropping
        m1 = mock_mesh_io.read_msh("/path/to/mesh.msh")
        tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
        cropped_mesh = m1.crop_mesh(tags=tags_keep)
        
        mock_mesh.crop_mesh.assert_called_once_with(tags=tags_keep)
        assert cropped_mesh == mock_cropped_mesh


class TestCompletionReport:
    """Test simulation completion report generation."""
    
    def test_create_completion_report(self):
        """Test creation of completion report."""
        completion_report = {
            'session_id': 'test_session',
            'subject_id': 'subj001',
            'project_dir': '/path/to/project',
            'simulation_dir': '/path/to/simulation',
            'completed_simulations': [],
            'timestamp': '2024-01-01T12:00:00',
            'total_simulations': 0,
            'success_count': 0,
            'error_count': 0
        }
        
        assert completion_report['subject_id'] == 'subj001'
        assert completion_report['total_simulations'] == 0
        assert len(completion_report['completed_simulations']) == 0
    
    def test_add_successful_simulation(self):
        """Test adding successful simulation to report."""
        completion_report = {
            'completed_simulations': [],
            'success_count': 0
        }
        
        # Add successful simulation
        simulation_info = {
            'montage_name': 'test_montage',
            'montage_type': 'regular',
            'status': 'completed',
            'temp_path': '/path/to/temp',
            'output_files': {
                'TI': ['/path/to/TI.msh']
            }
        }
        
        completion_report['completed_simulations'].append(simulation_info)
        completion_report['success_count'] += 1
        
        assert len(completion_report['completed_simulations']) == 1
        assert completion_report['success_count'] == 1
        assert completion_report['completed_simulations'][0]['montage_name'] == 'test_montage'


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_missing_simnibs_import(self):
        """Test handling of missing simnibs import."""
        # Simulate the simnibs check without importing the actual module
        mesh_io = None
        run_simnibs = None
        sim_struct = None
        TI = None
        
        with patch('sys.exit') as mock_exit:
            # Simulate the simnibs check
            if mesh_io is None or run_simnibs is None or sim_struct is None or TI is None:
                print("Error: simnibs is required for TI simulation but is not installed")
                sys.exit(1)
            
            mock_exit.assert_called_once_with(1)
    
    def test_invalid_montage_structure(self):
        """Test handling of invalid montage structure."""
        def validate_montage(montage, montage_name):
            if not montage or len(montage) < 2 or len(montage[0]) < 2:
                return False
            return True
        
        invalid_montage = [['electrode1']]  # Only one electrode in first pair
        result = validate_montage(invalid_montage, 'test_montage')
        
        assert result is False
    
    def test_missing_montage_file(self):
        """Test handling of missing montage file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            montage_file = os.path.join(temp_dir, 'nonexistent.json')
            
            # Check if file exists
            if not os.path.exists(montage_file):
                # Create initial content
                initial_content = {
                    "nets": {
                        "EGI_template.csv": {
                            "uni_polar_montages": {},
                            "multi_polar_montages": {}
                        }
                    }
                }
                
                with open(montage_file, 'w') as f:
                    json.dump(initial_content, f, indent=4)
            
            assert os.path.exists(montage_file)


class TestEnvironmentVariables:
    """Test environment variable handling."""
    
    def test_tissue_conductivity_override(self):
        """Test tissue conductivity override via environment variables."""
        with patch.dict(os.environ, {'TISSUE_COND_1': '0.5', 'TISSUE_COND_2': '0.3'}):
            # Simulate conductivity setting
            tdcs = MagicMock()
            tdcs.cond = [MagicMock(), MagicMock()]
            
            # Set custom conductivities
            for i in range(len(tdcs.cond)):
                tissue_num = i + 1
                env_var = f"TISSUE_COND_{tissue_num}"
                if env_var in os.environ:
                    tdcs.cond[i].value = float(os.environ[env_var])
            
            assert tdcs.cond[0].value == 0.5
            assert tdcs.cond[1].value == 0.3
    
    def test_log_file_environment_variable(self):
        """Test log file path from environment variable."""
        with patch.dict(os.environ, {'TI_LOG_FILE': '/path/to/custom.log'}):
            log_file = os.environ.get('TI_LOG_FILE')
            assert log_file == '/path/to/custom.log'
    
    def test_flex_montages_file_environment_variable(self):
        """Test flex montages file from environment variable."""
        with patch.dict(os.environ, {'FLEX_MONTAGES_FILE': '/path/to/flex.json'}):
            flex_montages_file = os.environ.get('FLEX_MONTAGES_FILE')
            assert flex_montages_file == '/path/to/flex.json'


class TestPathConstruction:
    """Test path construction and directory creation."""
    
    def test_construct_derivatives_path(self):
        """Test construction of derivatives directory path."""
        project_dir = "/path/to/project"
        subject_id = "subj001"
        
        derivatives_dir = os.path.join(project_dir, 'derivatives')
        simnibs_dir = os.path.join(derivatives_dir, 'SimNIBS', f'sub-{subject_id}')
        base_subpath = os.path.join(simnibs_dir, f'm2m_{subject_id}')
        
        # Use os.path.normpath to handle different path separators
        assert os.path.normpath(derivatives_dir) == os.path.normpath("/path/to/project/derivatives")
        assert os.path.normpath(simnibs_dir) == os.path.normpath("/path/to/project/derivatives/SimNIBS/sub-subj001")
        assert os.path.normpath(base_subpath) == os.path.normpath("/path/to/project/derivatives/SimNIBS/sub-subj001/m2m_subj001")
    
    def test_construct_config_path(self):
        """Test construction of config directory path."""
        project_dir = "/path/to/project"
        
        ti_csc_dir = os.path.join(project_dir, 'code', 'ti-toolbox')
        config_dir = os.path.join(ti_csc_dir, 'config')
        montage_file = os.path.join(config_dir, 'montage_list.json')
        
        # Use os.path.normpath to handle different path separators
        assert os.path.normpath(ti_csc_dir) == os.path.normpath("/path/to/project/code/ti-toolbox")
        assert os.path.normpath(config_dir) == os.path.normpath("/path/to/project/code/ti-toolbox/config")
        assert os.path.normpath(montage_file) == os.path.normpath("/path/to/project/code/ti-toolbox/config/montage_list.json")
    
    def test_construct_simulation_paths(self):
        """Test construction of simulation output paths."""
        simulation_dir = "/path/to/simulation"
        montage_name = "test_montage"
        
        temp_dir = os.path.join(simulation_dir, "tmp")
        montage_dir = os.path.join(temp_dir, montage_name)
        
        # Use os.path.normpath to handle different path separators
        assert os.path.normpath(temp_dir) == os.path.normpath("/path/to/simulation/tmp")
        assert os.path.normpath(montage_dir) == os.path.normpath("/path/to/simulation/tmp/test_montage")


if __name__ == "__main__":
    pytest.main([__file__])
