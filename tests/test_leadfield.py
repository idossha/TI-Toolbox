#!/usr/bin/env simnibs_python
"""
Comprehensive tests for ti-toolbox/opt/leadfield.py

Tests cover the LeadfieldGenerator class:
- Initialization and configuration
- Leadfield generation (HDF5 + NPY)
- HDF5 loading and centroid computation
- NPY saving and loading
- Leadfield listing (HDF5 and NPY)
- Cleanup operations
- Electrode name extraction
- Complete workflow (generate_and_save_numpy)

All external dependencies (SimNIBS, h5py, PathManager) are mocked.
"""

import pytest
import numpy as np
import os
import sys
from unittest.mock import Mock, MagicMock, patch, mock_open, call
from pathlib import Path

# Add ti-toolbox directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ti-toolbox'))


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def sample_subject_dir(tmp_path):
    """Create sample subject directory structure"""
    subject_dir = tmp_path / 'm2m_101'
    subject_dir.mkdir()

    # Create mesh file
    mesh_file = subject_dir / '101.msh'
    mesh_file.touch()

    # Create eeg_positions directory
    eeg_dir = subject_dir / 'eeg_positions'
    eeg_dir.mkdir()

    # Create sample EEG cap file
    cap_file = eeg_dir / 'EEG10-10.csv'
    cap_file.write_text('Electrode,Type,Size,X,Y,Z,Label\n1,electrode,5.0,10.0,20.0,30.0,Fp1\n')

    return subject_dir


@pytest.fixture
def mock_path_manager():
    """Create mock PathManager"""
    mock_pm = MagicMock()
    mock_pm.get_leadfield_dir = MagicMock(return_value='/fake/project/derivatives/SimNIBS/sub-101/leadfields')
    mock_pm.get_eeg_positions_dir = MagicMock(return_value='/fake/m2m_101/eeg_positions')
    return mock_pm


@pytest.fixture
def sample_leadfield_matrix():
    """Create sample leadfield matrix"""
    # Shape: (n_electrodes, n_voxels, 3) - typical leadfield shape
    return np.random.randn(64, 1000, 3).astype(np.float64)


@pytest.fixture
def sample_positions():
    """Create sample position coordinates"""
    # Shape: (n_voxels, 3) - x, y, z coordinates
    return np.random.randn(1000, 3).astype(np.float64)


@pytest.fixture
def sample_node_coords():
    """Create sample node coordinates for HDF5 file"""
    return np.random.randn(5000, 3).astype(np.float64)


@pytest.fixture
def sample_tetrahedral_indices():
    """Create sample tetrahedral element indices"""
    # 4 vertices per tetrahedron, 1-indexed
    return np.random.randint(1, 5001, size=(1000, 4), dtype=np.int32)


@pytest.fixture
def mock_hdf5_file(sample_leadfield_matrix, sample_node_coords, sample_tetrahedral_indices):
    """Create mock HDF5 file structure"""
    mock_file = MagicMock()

    # Mock nested structure: f['mesh_leadfield']['leadfields']['tdcs_leadfield']
    mock_leadfield_data = sample_leadfield_matrix
    mock_tdcs_leadfield = MagicMock()
    mock_tdcs_leadfield.__array__ = lambda: mock_leadfield_data

    mock_leadfields = MagicMock()
    mock_leadfields.__getitem__ = MagicMock(return_value=mock_tdcs_leadfield)

    mock_nodes = MagicMock()
    mock_nodes.__getitem__ = MagicMock(return_value=sample_node_coords)

    mock_elm = MagicMock()
    mock_elm.__getitem__ = MagicMock(return_value=sample_tetrahedral_indices)

    mock_mesh_leadfield = MagicMock()
    mock_mesh_leadfield.__getitem__ = MagicMock(side_effect=lambda key: {
        'leadfields': mock_leadfields,
        'nodes': mock_nodes,
        'elm': mock_elm
    }[key])

    mock_file.__getitem__ = MagicMock(side_effect=lambda key: mock_mesh_leadfield if key == 'mesh_leadfield' else None)
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)

    return mock_file


# ==============================================================================
# TEST LeadfieldGenerator.__init__()
# ==============================================================================

class TestLeadfieldGeneratorInit:
    """Test LeadfieldGenerator initialization"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    def test_init_basic(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test basic initialization"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')

        assert gen.subject_dir == sample_subject_dir
        assert gen.electrode_cap == 'EEG10-10'
        assert gen.subject_id == '101'  # Extracted from m2m_101
        assert gen.lfm is None
        assert gen.positions is None

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    def test_init_with_callbacks(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test initialization with progress callback and termination flag"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        callback_messages = []
        def progress_callback(msg, msg_type):
            callback_messages.append((msg, msg_type))

        termination_flag = MagicMock(return_value=False)

        gen = LeadfieldGenerator(
            sample_subject_dir,
            progress_callback=progress_callback,
            termination_flag=termination_flag
        )

        assert gen._progress_callback == progress_callback
        assert gen._termination_flag == termination_flag
        assert gen.logger is None  # Should not create logger when callback provided

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('opt.leadfield.logging_util.get_logger')
    def test_init_with_logger(self, mock_get_logger, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test initialization creates logger when no callback"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_logger = MagicMock()
        mock_logger.level = 20  # INFO level
        mock_get_logger.return_value = mock_logger

        gen = LeadfieldGenerator(sample_subject_dir)

        assert gen.logger is not None
        mock_get_logger.assert_called_once()


# ==============================================================================
# TEST LeadfieldGenerator.cleanup_old_simulations()
# ==============================================================================

class TestCleanupOldSimulations:
    """Test cleanup of old simulation files"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('glob.glob')
    @patch('opt.leadfield.os.remove')
    @patch('shutil.rmtree')
    def test_cleanup_simulation_files(self, mock_rmtree, mock_remove, mock_glob, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test cleanup of .mat simulation files"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Mock finding old .mat files
        mock_glob.return_value = [
            str(sample_subject_dir / 'simnibs_simulation_01.mat'),
            str(sample_subject_dir / 'simnibs_simulation_02.mat')
        ]

        gen = LeadfieldGenerator(sample_subject_dir)
        gen.cleanup_old_simulations()

        # Should have removed both files
        assert mock_remove.call_count == 2

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('glob.glob')
    @patch('shutil.rmtree')
    def test_cleanup_leadfield_directory(self, mock_rmtree, mock_glob, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test cleanup of temporary leadfield directory"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_glob.return_value = []  # No .mat files

        # Create temporary leadfield directory
        leadfield_dir = sample_subject_dir / 'leadfield'
        leadfield_dir.mkdir()

        gen = LeadfieldGenerator(sample_subject_dir)
        gen.cleanup_old_simulations()

        # Should have attempted to remove directory
        mock_rmtree.assert_called()

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('glob.glob')
    def test_cleanup_roi_mesh_file(self, mock_glob, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test cleanup of ROI mesh file"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_glob.return_value = []

        # Create ROI mesh file
        roi_file = sample_subject_dir / '101_ROI.msh'
        roi_file.touch()

        gen = LeadfieldGenerator(sample_subject_dir)

        # Verify file exists before cleanup
        assert roi_file.exists()

        gen.cleanup_old_simulations()

        # File should be removed after cleanup
        assert not roi_file.exists()


# ==============================================================================
# TEST LeadfieldGenerator.generate_leadfield()
# ==============================================================================

class TestGenerateLeadfield:
    """Test leadfield generation workflow"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('simnibs.run_simnibs')
    @patch('glob.glob')
    def test_generate_leadfield_basic(self, mock_glob, mock_run_simnibs, mock_get_pm, tmp_path, sample_subject_dir, mock_path_manager):
        """Test basic leadfield generation"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Create actual HDF5 file for the test
        output_dir = Path(tmp_path) / 'fake_output'
        output_dir.mkdir(exist_ok=True)
        hdf5_file = output_dir / 'EEG10-10_leadfield.hdf5'
        hdf5_file.write_text("dummy hdf5 content")  # Create the file

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')

        # Mock load_from_hdf5 and save_numpy
        gen.load_from_hdf5 = MagicMock(return_value=(
            np.random.randn(64, 1000, 3),
            np.random.randn(1000, 3)
        ))
        gen.save_numpy = MagicMock(return_value=(
            '/fake/output/EEG10-10_leadfield.npy',
            '/fake/output/EEG10-10_positions.npy'
        ))

        result = gen.generate_leadfield(output_dir=str(output_dir))

        assert 'hdf5' in result
        assert 'npy_leadfield' in result
        assert 'npy_positions' in result
        mock_run_simnibs.assert_called_once()

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    def test_generate_leadfield_mesh_not_found(self, mock_get_pm, tmp_path, mock_path_manager):
        """Test error when mesh file not found"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Create directory without mesh file
        subject_dir = tmp_path / 'm2m_999'
        subject_dir.mkdir()

        gen = LeadfieldGenerator(subject_dir)

        with pytest.raises(FileNotFoundError, match="Mesh file not found"):
            gen.generate_leadfield()

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('simnibs.run_simnibs')
    @patch('glob.glob')
    def test_generate_leadfield_with_termination(self, mock_glob, mock_run_simnibs, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test leadfield generation with termination flag"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        termination_flag = MagicMock(return_value=True)  # Immediately terminate

        gen = LeadfieldGenerator(sample_subject_dir, termination_flag=termination_flag)

        with pytest.raises(InterruptedError, match="cancelled"):
            gen.generate_leadfield()

        mock_run_simnibs.assert_not_called()  # Should not run if terminated early


# ==============================================================================
# TEST LeadfieldGenerator.load_from_hdf5()
# ==============================================================================

class TestLoadFromHdf5:
    """Test loading leadfield from HDF5 file"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('h5py.File')
    def test_load_from_hdf5_with_centroids(self, mock_h5py_file, mock_get_pm, tmp_path, mock_path_manager, mock_hdf5_file, sample_leadfield_matrix, sample_node_coords, sample_tetrahedral_indices):
        """Test HDF5 loading with centroid computation"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_h5py_file.return_value.__enter__ = MagicMock(return_value=mock_hdf5_file)
        mock_h5py_file.return_value.__exit__ = MagicMock(return_value=False)

        gen = LeadfieldGenerator(Path('/fake/m2m_101'))

        # Create a real temporary file so the path.exists() check passes
        hdf5_path = tmp_path / 'leadfield.hdf5'
        hdf5_path.write_text('dummy')

        lfm, positions = gen.load_from_hdf5(hdf5_path, compute_centroids=True)

        assert lfm.shape == sample_leadfield_matrix.shape
        assert positions.shape[0] == 1000  # n_voxels
        assert positions.shape[1] == 3     # x, y, z
        assert gen.lfm is not None
        assert gen.positions is not None

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('h5py.File')
    def test_load_from_hdf5_without_centroids(self, mock_h5py_file, mock_get_pm, tmp_path, mock_path_manager, mock_hdf5_file):
        """Test HDF5 loading without centroid computation (use nodes directly)"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_h5py_file.return_value.__enter__ = MagicMock(return_value=mock_hdf5_file)
        mock_h5py_file.return_value.__exit__ = MagicMock(return_value=False)

        gen = LeadfieldGenerator(Path('/fake/m2m_101'))

        # Create a real temporary file so the path.exists() check passes
        hdf5_path = tmp_path / 'leadfield.hdf5'
        hdf5_path.write_text('dummy')

        lfm, positions = gen.load_from_hdf5(hdf5_path, compute_centroids=False)

        assert lfm is not None
        assert positions is not None

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    def test_load_from_hdf5_file_not_found(self, mock_get_pm, mock_path_manager):
        """Test error handling when HDF5 file doesn't exist"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        gen = LeadfieldGenerator(Path('/fake/m2m_101'))

        with pytest.raises(FileNotFoundError, match="HDF5 file not found"):
            gen.load_from_hdf5(Path('/nonexistent/file.hdf5'))


# ==============================================================================
# TEST LeadfieldGenerator.save_numpy()
# ==============================================================================

class TestSaveNumpy:
    """Test saving leadfield as NumPy files"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('numpy.save')
    def test_save_numpy_with_net_name(self, mock_np_save, mock_get_pm, sample_subject_dir, mock_path_manager, sample_leadfield_matrix, sample_positions):
        """Test saving NumPy files with network name"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')
        gen.lfm = sample_leadfield_matrix
        gen.positions = sample_positions

        output_dir = Path('/fake/output')
        lfm_path, pos_path = gen.save_numpy(output_dir, net_name='EEG10-10')

        assert 'EEG10-10_leadfield.npy' in str(lfm_path)
        assert 'EEG10-10_positions.npy' in str(pos_path)
        assert mock_np_save.call_count == 2

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('numpy.save')
    def test_save_numpy_without_net_name(self, mock_np_save, mock_get_pm, sample_subject_dir, mock_path_manager, sample_leadfield_matrix, sample_positions):
        """Test saving NumPy files using electrode_cap"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='GSN-256')
        gen.lfm = sample_leadfield_matrix
        gen.positions = sample_positions

        lfm_path, pos_path = gen.save_numpy(Path('/fake/output'))

        assert 'GSN-256_leadfield.npy' in str(lfm_path)
        assert 'GSN-256_positions.npy' in str(pos_path)

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    def test_save_numpy_not_loaded(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test error when trying to save without loading first"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        gen = LeadfieldGenerator(sample_subject_dir)

        with pytest.raises(ValueError, match="Leadfield not loaded"):
            gen.save_numpy(Path('/fake/output'))


# ==============================================================================
# TEST LeadfieldGenerator.load_numpy()
# ==============================================================================

class TestLoadNumpy:
    """Test loading leadfield from NumPy files"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('numpy.load')
    @patch('pathlib.Path.exists')
    def test_load_numpy_success(self, mock_exists, mock_np_load, mock_get_pm, sample_subject_dir, mock_path_manager, sample_leadfield_matrix, sample_positions):
        """Test successful NumPy file loading"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_exists.return_value = True
        mock_np_load.side_effect = [sample_leadfield_matrix, sample_positions]

        gen = LeadfieldGenerator(sample_subject_dir)

        lfm, positions = gen.load_numpy(
            Path('/fake/leadfield.npy'),
            Path('/fake/positions.npy')
        )

        assert lfm.shape == sample_leadfield_matrix.shape
        assert positions.shape == sample_positions.shape
        assert gen.lfm is not None
        assert gen.positions is not None

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('pathlib.Path.exists')
    def test_load_numpy_leadfield_not_found(self, mock_exists, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test error when leadfield file not found"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_exists.return_value = False

        gen = LeadfieldGenerator(sample_subject_dir)

        with pytest.raises(FileNotFoundError, match="Leadfield file not found"):
            gen.load_numpy(Path('/fake/leadfield.npy'), Path('/fake/positions.npy'))


# ==============================================================================
# TEST LeadfieldGenerator.list_available_leadfields_hdf5()
# ==============================================================================

class TestListAvailableLeadfieldsHdf5:
    """Test listing available HDF5 leadfield files"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('os.path.exists')
    def test_list_hdf5_leadfields(self, mock_exists, mock_get_pm, mock_path_manager, tmp_path):
        """Test listing HDF5 leadfield files"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Create temporary leadfields directory
        leadfields_dir = tmp_path / 'leadfields'
        leadfields_dir.mkdir()
        mock_path_manager.get_leadfield_dir = MagicMock(return_value=str(leadfields_dir))
        mock_exists.return_value = True

        # Create HDF5 files
        (leadfields_dir / 'EEG10-10_leadfield.hdf5').touch()
        (leadfields_dir / 'GSN-256_leadfield.hdf5').touch()
        (leadfields_dir / 'not_a_leadfield.txt').touch()  # Should be ignored

        gen = LeadfieldGenerator(Path('/fake/m2m_101'))
        leadfields = gen.list_available_leadfields_hdf5()

        assert len(leadfields) >= 2
        # Check that we got valid tuples (net_name, path, size)
        for net_name, path, size in leadfields:
            assert isinstance(net_name, str)
            assert isinstance(path, str)
            assert isinstance(size, float)

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('os.path.exists')
    def test_list_hdf5_leadfields_empty_dir(self, mock_exists, mock_get_pm, mock_path_manager):
        """Test listing when no HDF5 files exist"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_path_manager.get_leadfield_dir = MagicMock(return_value=None)
        mock_exists.return_value = False

        gen = LeadfieldGenerator(Path('/fake/m2m_101'))
        leadfields = gen.list_available_leadfields_hdf5()

        assert len(leadfields) == 0


# ==============================================================================
# TEST LeadfieldGenerator.list_available_leadfields_npy()
# ==============================================================================

class TestListAvailableLeadfieldsNpy:
    """Test listing available NPY leadfield file pairs"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('os.path.exists')
    def test_list_npy_leadfields(self, mock_exists, mock_get_pm, mock_path_manager, tmp_path):
        """Test listing NPY leadfield file pairs"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Create temporary leadfields directory
        leadfields_dir = tmp_path / 'leadfields'
        leadfields_dir.mkdir()
        mock_path_manager.get_leadfield_dir = MagicMock(return_value=str(leadfields_dir))
        mock_exists.return_value = True

        # Create NPY file pairs
        (leadfields_dir / 'EEG10-10_leadfield.npy').touch()
        (leadfields_dir / 'EEG10-10_positions.npy').touch()
        (leadfields_dir / 'GSN-256_leadfield.npy').touch()
        (leadfields_dir / 'GSN-256_positions.npy').touch()

        gen = LeadfieldGenerator(Path('/fake/m2m_101'))
        leadfields = gen.list_available_leadfields_npy()

        assert len(leadfields) >= 2
        # Check tuple format: (net_name, leadfield_path, positions_path, total_size)
        for net_name, lfm_path, pos_path, size in leadfields:
            assert isinstance(net_name, str)
            assert 'leadfield.npy' in lfm_path
            assert 'positions.npy' in pos_path
            assert isinstance(size, float)

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('os.path.exists')
    def test_list_npy_leadfields_missing_positions(self, mock_exists, mock_get_pm, mock_path_manager, tmp_path):
        """Test listing NPY when positions file is missing"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        leadfields_dir = tmp_path / 'leadfields'
        leadfields_dir.mkdir()
        mock_path_manager.get_leadfield_dir = MagicMock(return_value=str(leadfields_dir))
        mock_exists.return_value = True

        # Create leadfield without positions
        (leadfields_dir / 'incomplete_leadfield.npy').touch()

        gen = LeadfieldGenerator(Path('/fake/m2m_101'))
        leadfields = gen.list_available_leadfields_npy()

        # Should not include incomplete pairs
        assert all('incomplete' not in lf[0] for lf in leadfields)


# ==============================================================================
# TEST LeadfieldGenerator.get_electrode_names_from_cap()
# ==============================================================================

class TestGetElectrodeNamesFromCap:
    """Test electrode name extraction from EEG cap file"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    def test_get_electrode_names_basic(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test basic electrode name extraction"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Create sample EEG cap file with proper format
        cap_file = sample_subject_dir / 'eeg_positions' / 'EEG10-10.csv'
        cap_file.parent.mkdir(exist_ok=True)
        cap_file.write_text(
            'Label,X,Y,Z\n'
            'Fp1,10,20,30\n'
            'Fp2,15,25,35\n'
            'F3,12,22,32\n'
        )

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')
        electrodes = gen.get_electrode_names_from_cap(eeg_cap_path=str(cap_file))

        assert len(electrodes) == 3
        assert 'Fp1' in electrodes
        assert 'Fp2' in electrodes
        assert 'F3' in electrodes

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    def test_get_electrode_names_file_not_found(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test error when cap file not found"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        gen = LeadfieldGenerator(sample_subject_dir)

        with pytest.raises(FileNotFoundError, match="not found"):
            gen.get_electrode_names_from_cap(eeg_cap_path='/nonexistent/cap.csv')


# ==============================================================================
# TEST LeadfieldGenerator.generate_and_save_numpy()
# ==============================================================================

class TestGenerateAndSaveNumpy:
    """Test complete workflow: generate + convert + save"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('opt.leadfield.LeadfieldGenerator.generate_leadfield')
    @patch('numpy.load')
    def test_generate_and_save_numpy_complete(self, mock_np_load, mock_generate, mock_get_pm, sample_subject_dir, mock_path_manager, sample_leadfield_matrix):
        """Test complete workflow from generation to NPY files"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Mock generate_leadfield return value
        mock_generate.return_value = {
            'hdf5': '/fake/output/EEG10-10_leadfield.hdf5',
            'npy_leadfield': '/fake/output/EEG10-10_leadfield.npy',
            'npy_positions': '/fake/output/EEG10-10_positions.npy'
        }

        # Mock numpy load for shape retrieval
        mock_np_load.return_value = sample_leadfield_matrix

        # Create EEG cap file
        cap_file = sample_subject_dir / 'eeg_positions' / 'EEG10-10.csv'
        cap_file.parent.mkdir(exist_ok=True)
        cap_file.touch()
        mock_path_manager.get_eeg_positions_dir = MagicMock(return_value=str(cap_file.parent))

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')
        gen.lfm = sample_leadfield_matrix  # Set lfm for shape retrieval

        lfm_path, pos_path, shape = gen.generate_and_save_numpy(
            output_dir='/fake/output',
            eeg_cap_file='EEG10-10.csv'
        )

        assert lfm_path == '/fake/output/EEG10-10_leadfield.npy'
        assert pos_path == '/fake/output/EEG10-10_positions.npy'
        assert shape == sample_leadfield_matrix.shape

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    def test_generate_and_save_numpy_cap_not_found(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test error when EEG cap file not found"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_path_manager.get_eeg_positions_dir = MagicMock(return_value=None)

        gen = LeadfieldGenerator(sample_subject_dir)

        with pytest.raises(FileNotFoundError, match="EEG positions directory not found"):
            gen.generate_and_save_numpy('/fake/output', 'nonexistent.csv')


# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================

class TestLeadfieldGeneratorIntegration:
    """Integration tests for complete workflows"""

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('h5py.File')
    @patch('numpy.save')
    def test_hdf5_to_npy_workflow(self, mock_np_save, mock_h5py_file, mock_get_pm, tmp_path, sample_subject_dir, mock_path_manager, mock_hdf5_file):
        """Test workflow: load HDF5 -> save as NPY"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_h5py_file.return_value.__enter__ = MagicMock(return_value=mock_hdf5_file)
        mock_h5py_file.return_value.__exit__ = MagicMock(return_value=False)

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')

        # Create a real temporary file so the path.exists() check passes
        hdf5_path = tmp_path / 'leadfield.hdf5'
        hdf5_path.write_text('dummy')

        # Load from HDF5
        lfm, positions = gen.load_from_hdf5(hdf5_path)

        # Save as NPY
        lfm_path, pos_path = gen.save_numpy(Path('/fake/output'))

        assert gen.lfm is not None
        assert gen.positions is not None
        assert mock_np_save.call_count == 2

    @pytest.mark.unit
    @patch('opt.leadfield.get_path_manager')
    @patch('numpy.load')
    @patch('pathlib.Path.exists')
    def test_npy_load_workflow(self, mock_exists, mock_np_load, mock_get_pm, sample_subject_dir, mock_path_manager, sample_leadfield_matrix, sample_positions):
        """Test workflow: load existing NPY files"""
        from opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_exists.return_value = True
        mock_np_load.side_effect = [sample_leadfield_matrix, sample_positions]

        gen = LeadfieldGenerator(sample_subject_dir)

        lfm, positions = gen.load_numpy(
            Path('/fake/leadfield.npy'),
            Path('/fake/positions.npy')
        )

        assert lfm.shape == (64, 1000, 3)
        assert positions.shape == (1000, 3)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
