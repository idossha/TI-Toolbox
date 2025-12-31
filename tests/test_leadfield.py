#!/usr/bin/env simnibs_python
"""
Comprehensive tests for tit/opt/leadfield.py

Tests cover the LeadfieldGenerator class:
- Initialization and configuration
- Leadfield generation (HDF5)
- Leadfield listing (HDF5)
- Cleanup operations
- Electrode name extraction

All external dependencies (SimNIBS, h5py, PathManager) are mocked.
"""

import pytest
import os
import sys
from unittest.mock import Mock, MagicMock, patch, mock_open, call
from pathlib import Path

# Add tit directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tit'))


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
def sample_node_coords():
    """Create sample node coordinates for HDF5 file"""
    return np.random.randn(5000, 3).astype(np.float64)


@pytest.fixture
def sample_tetrahedral_indices():
    """Create sample tetrahedral element indices"""
    # 4 vertices per tetrahedron, 1-indexed
    return np.random.randint(1, 5001, size=(1000, 4), dtype=np.int32)




# ==============================================================================
# TEST LeadfieldGenerator.__init__()
# ==============================================================================

class TestLeadfieldGeneratorInit:
    """Test LeadfieldGenerator initialization"""

    @pytest.mark.unit
    @patch('tit.opt.leadfield.get_path_manager')
    def test_init_basic(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test basic initialization"""
        from tit.opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')

        assert gen.subject_dir == sample_subject_dir
        assert gen.electrode_cap == 'EEG10-10'
        assert gen.subject_id == '101'  # Extracted from m2m_101
        assert gen.lfm is None
        assert gen.positions is None

    @pytest.mark.unit
    @patch('tit.opt.leadfield.get_path_manager')
    def test_init_with_callbacks(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test initialization with progress callback and termination flag"""
        from tit.opt.leadfield import LeadfieldGenerator

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
    @patch('tit.opt.leadfield.get_path_manager')
    @patch('tit.opt.leadfield.logging_util.get_logger')
    def test_init_with_logger(self, mock_get_logger, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test initialization creates logger when no callback"""
        from tit.opt.leadfield import LeadfieldGenerator

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
    @patch('tit.opt.leadfield.get_path_manager')
    @patch('glob.glob')
    @patch('tit.opt.leadfield.os.remove')
    @patch('shutil.rmtree')
    def test_cleanup_simulation_files(self, mock_rmtree, mock_remove, mock_glob, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test cleanup of .mat simulation files"""
        from tit.opt.leadfield import LeadfieldGenerator

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
    @patch('tit.opt.leadfield.get_path_manager')
    @patch('glob.glob')
    @patch('shutil.rmtree')
    def test_cleanup_leadfield_directory(self, mock_rmtree, mock_glob, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test cleanup of temporary leadfield directory"""
        from tit.opt.leadfield import LeadfieldGenerator

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
    @patch('tit.opt.leadfield.get_path_manager')
    @patch('glob.glob')
    def test_cleanup_roi_mesh_file(self, mock_glob, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test cleanup of ROI mesh file"""
        from tit.opt.leadfield import LeadfieldGenerator

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
    @patch('tit.opt.leadfield.get_path_manager')
    @patch('simnibs.run_simnibs')
    @patch('glob.glob')
    def test_generate_leadfield_basic(self, mock_glob, mock_run_simnibs, mock_get_pm, tmp_path, sample_subject_dir, mock_path_manager):
        """Test basic leadfield generation"""
        from tit.opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Create actual HDF5 file for the test
        output_dir = Path(tmp_path) / 'fake_output'
        output_dir.mkdir(exist_ok=True)
        hdf5_file = output_dir / 'EEG10-10_leadfield.hdf5'
        hdf5_file.write_text("dummy hdf5 content")  # Create the file

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')

        result = gen.generate_leadfield(output_dir=str(output_dir))

        assert 'hdf5' in result
        mock_run_simnibs.assert_called_once()

    @pytest.mark.unit
    @patch('tit.opt.leadfield.get_path_manager')
    def test_generate_leadfield_mesh_not_found(self, mock_get_pm, tmp_path, mock_path_manager):
        """Test error when mesh file not found"""
        from tit.opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Create directory without mesh file
        subject_dir = tmp_path / 'm2m_999'
        subject_dir.mkdir()

        gen = LeadfieldGenerator(subject_dir)

        with pytest.raises(FileNotFoundError, match="Mesh file not found"):
            gen.generate_leadfield()

    @pytest.mark.unit
    @patch('tit.opt.leadfield.get_path_manager')
    @patch('simnibs.run_simnibs')
    @patch('glob.glob')
    def test_generate_leadfield_with_termination(self, mock_glob, mock_run_simnibs, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test leadfield generation with termination flag"""
        from tit.opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        termination_flag = MagicMock(return_value=True)  # Immediately terminate

        gen = LeadfieldGenerator(sample_subject_dir, termination_flag=termination_flag)

        with pytest.raises(InterruptedError, match="cancelled"):
            gen.generate_leadfield()

        mock_run_simnibs.assert_not_called()  # Should not run if terminated early


# ==============================================================================
# TEST LeadfieldGenerator.load_from_hdf5()
# ==============================================================================







# ==============================================================================
# TEST LeadfieldGenerator.list_available_leadfields_hdf5()
# ==============================================================================

class TestListAvailableLeadfieldsHdf5:
    """Test listing available HDF5 leadfield files"""

    @pytest.mark.unit
    @patch('tit.opt.leadfield.get_path_manager')
    @patch('os.path.exists')
    def test_list_hdf5_leadfields(self, mock_exists, mock_get_pm, mock_path_manager, tmp_path):
        """Test listing HDF5 leadfield files"""
        from tit.opt.leadfield import LeadfieldGenerator

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
    @patch('tit.opt.leadfield.get_path_manager')
    @patch('os.path.exists')
    def test_list_hdf5_leadfields_empty_dir(self, mock_exists, mock_get_pm, mock_path_manager):
        """Test listing when no HDF5 files exist"""
        from tit.opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager
        mock_path_manager.get_leadfield_dir = MagicMock(return_value=None)
        mock_exists.return_value = False

        gen = LeadfieldGenerator(Path('/fake/m2m_101'))
        leadfields = gen.list_available_leadfields_hdf5()

        assert len(leadfields) == 0


# ==============================================================================
# TEST LeadfieldGenerator.get_electrode_names_from_cap()
# ==============================================================================

class TestGetElectrodeNamesFromCap:
    """Test electrode name extraction from EEG cap file"""

    @pytest.mark.unit
    @patch('tit.opt.leadfield.get_path_manager')
    def test_get_electrode_names_basic(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test basic electrode name extraction"""
        from tit.opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        # Create sample EEG cap file with proper format
        cap_file = sample_subject_dir / 'eeg_positions' / 'EEG10-10.csv'
        cap_file.parent.mkdir(exist_ok=True)
        cap_file.write_text(
            'Electrode,10,20,30,Fp1\n'
            'Electrode,15,25,35,Fp2\n'
            'Electrode,12,22,32,F3\n'
        )

        gen = LeadfieldGenerator(sample_subject_dir, electrode_cap='EEG10-10')
        electrodes = gen.get_electrode_names_from_cap()

        assert len(electrodes) == 3
        assert 'Fp1' in electrodes
        assert 'Fp2' in electrodes
        assert 'F3' in electrodes

    @pytest.mark.unit
    @patch('tit.opt.leadfield.get_path_manager')
    def test_get_electrode_names_file_not_found(self, mock_get_pm, sample_subject_dir, mock_path_manager):
        """Test error when cap file not found"""
        from tit.opt.leadfield import LeadfieldGenerator

        mock_get_pm.return_value = mock_path_manager

        gen = LeadfieldGenerator(sample_subject_dir)

        with pytest.raises(OSError, match="Could not find EEG cap file"):
            gen.get_electrode_names_from_cap('nonexistent')




# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================

class TestLeadfieldGeneratorIntegration:
    """Integration tests for complete workflows"""



if __name__ == '__main__':
    pytest.main([__file__, '-v'])
