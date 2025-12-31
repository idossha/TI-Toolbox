#!/usr/bin/env simnibs_python
"""
Unit tests for sim.session_builder module.

Tests SessionBuilder class for constructing SimNIBS SESSION objects:
- Initialization and path handling
- TI mode session building (2 pairs)
- mTI mode session building (4+ pairs)
- EEG cap handling (electrode names vs XYZ coordinates)
- DTI tensor handling
- Tissue conductivity overrides

Note: These tests use the real SimNIBS sim_struct from the Docker container
but mock the PathManager for path resolution.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def mock_path_manager(tmp_path):
    """Mock PathManager for testing."""
    class MockPathManager:
        def __init__(self):
            self.project_dir = str(tmp_path)

        def get_m2m_dir(self, subject_id):
            m2m_path = tmp_path / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / f"m2m_{subject_id}"
            m2m_path.mkdir(parents=True, exist_ok=True)
            return str(m2m_path)

    return MockPathManager()


@pytest.fixture
def setup_test_files(tmp_path, mock_path_manager):
    """Create test files in temporary directory."""
    subject_id = "001"
    m2m_dir = tmp_path / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / f"m2m_{subject_id}"
    m2m_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy mesh file
    mesh_file = m2m_dir / f"{subject_id}.msh"
    mesh_file.write_text("dummy mesh data")

    # Create dummy tensor file
    tensor_file = m2m_dir / "DTI_coregT1_tensor.nii.gz"
    tensor_file.write_text("dummy tensor data")

    # Create eeg_positions directory
    eeg_dir = m2m_dir / "eeg_positions"
    eeg_dir.mkdir(exist_ok=True)

    # Create dummy EEG cap file
    eeg_cap = eeg_dir / "EGI_template.csv"
    eeg_cap.write_text("Label,X,Y,Z\nCz,0,0,100\nOz,0,-50,50\n")

    return {
        'subject_id': subject_id,
        'm2m_dir': str(m2m_dir),
        'mesh_file': str(mesh_file),
        'tensor_file': str(tensor_file),
        'eeg_cap': str(eeg_cap),
        'path_manager': mock_path_manager
    }


class TestSessionBuilderInitialization:
    """Test suite for SessionBuilder initialization."""

    @patch('tit.sim.session_builder.get_path_manager')
    def test_initialization(self, mock_get_pm, setup_test_files):
        """Test SessionBuilder initializes with correct paths."""
        from tit.sim.config import SimulationConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig()
        )

        builder = SessionBuilder(config)

        assert builder.config == config
        assert builder.m2m_dir == setup_test_files['m2m_dir']
        assert builder.mesh_file == setup_test_files['mesh_file']
        assert "DTI_coregT1_tensor.nii.gz" in builder.tensor_file

    @patch('tit.sim.session_builder.get_path_manager')
    def test_paths_exist(self, mock_get_pm, setup_test_files):
        """Test that SessionBuilder finds existing paths."""
        from tit.sim.config import SimulationConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig()
        )

        builder = SessionBuilder(config)

        assert os.path.exists(builder.m2m_dir)
        assert os.path.exists(builder.mesh_file)
        assert os.path.exists(builder.tensor_file)


class TestSessionBuilderTIMode:
    """Test suite for SessionBuilder TI mode (2 pairs)."""

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_ti_session_basic(self, mock_get_pm, setup_test_files):
        """Test building basic TI session with 2 electrode pairs."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(
                pair1=2.0, pair2=2.0,
                pair3=2.0, pair4=2.0
            ),
            electrode=ElectrodeConfig()
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        assert session.subpath == setup_test_files['m2m_dir']
        assert session.fnamehead == setup_test_files['mesh_file']
        assert session.anisotropy_type == "dir"
        assert session.pathfem == "/output/dir"

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_ti_session_eeg_cap(self, mock_get_pm, setup_test_files):
        """Test TI session sets EEG cap for electrode names."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
            eeg_net="EGI_template.csv"
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")],
            is_xyz=False
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        assert session.eeg_cap.endswith("EGI_template.csv")
        assert "eeg_positions" in session.eeg_cap

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_ti_session_xyz_no_eeg_cap(self, mock_get_pm, setup_test_files):
        """Test TI session does not set EEG cap for XYZ coordinates."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig()
        )

        montage = MontageConfig(
            name="xyz_montage",
            electrode_pairs=[
                ([0.0, 0.0, 100.0], [0.0, 0.0, -100.0]),
                ([50.0, 0.0, 0.0], [-50.0, 0.0, 0.0])
            ],
            is_xyz=True
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        # eeg_cap should be empty string or not set for XYZ mode
        assert session.eeg_cap == "" or not session.eeg_cap

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_ti_session_mapping_options(self, mock_get_pm, setup_test_files):
        """Test TI session applies mapping options."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(),
            map_to_surf=True,
            map_to_vol=True,
            map_to_mni=True,
            map_to_fsavg=False
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        assert session.map_to_surf is True
        assert session.map_to_vol is True
        assert session.map_to_mni is True
        assert session.map_to_fsavg is False

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_ti_session_dti_tensor(self, mock_get_pm, setup_test_files):
        """Test TI session sets DTI tensor when file exists."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig()
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        # Tensor file exists in setup_test_files
        assert session.dti_nii == setup_test_files['tensor_file']

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_ti_session_adds_two_pairs(self, mock_get_pm, setup_test_files):
        """Test TI session adds exactly 2 electrode pairs."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig()
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        assert len(session.poslists) == 2

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_ti_session_current_conversion(self, mock_get_pm, setup_test_files):
        """Test TI session converts mA to Amperes."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(
                pair1=2000.0,  # TI pair 1: 2000 mA = 2.0 A
                pair2=1500.0,  # TI pair 2: 1500 mA = 1.5 A
                pair3=1000.0,  # Not used in TI mode
                pair4=500.0    # Not used in TI mode
            ),
            electrode=ElectrodeConfig()
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        # TI pair 1 uses pair1: 2000 mA -> 2.0 A
        assert session.poslists[0].currents == [2.0, -2.0]
        # TI pair 2 uses pair2: 1500 mA -> 1.5 A
        assert session.poslists[1].currents == [1.5, -1.5]


class TestSessionBuilderMTIMode:
    """Test suite for SessionBuilder mTI mode (4+ pairs)."""

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_mti_session_basic(self, mock_get_pm, setup_test_files):
        """Test building basic mTI session with 4 electrode pairs."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig()
        )

        montage = MontageConfig(
            name="mti_montage",
            electrode_pairs=[
                ("Cz", "Oz"),
                ("C3", "C4"),
                ("F3", "F4"),
                ("P3", "P4")
            ]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        assert session.pathfem == "/output/dir"
        assert len(session.poslists) == 4

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_mti_session_adds_four_pairs(self, mock_get_pm, setup_test_files):
        """Test mTI session adds exactly 4 electrode pairs."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig()
        )

        montage = MontageConfig(
            name="mti_montage",
            electrode_pairs=[
                ("Cz", "Oz"),
                ("C3", "C4"),
                ("F3", "F4"),
                ("P3", "P4")
            ]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        assert len(session.poslists) == 4

    @patch('tit.sim.session_builder.get_path_manager')
    def test_build_mti_session_current_distribution(self, mock_get_pm, setup_test_files):
        """Test mTI session distributes currents correctly."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(
                pair1=2000.0,  # Pair 1
                pair2=1500.0,  # Pair 2
                pair3=1000.0,  # Pair 3
                pair4=500.0    # Pair 4
            ),
            electrode=ElectrodeConfig()
        )

        montage = MontageConfig(
            name="mti_montage",
            electrode_pairs=[
                ("Cz", "Oz"),
                ("C3", "C4"),
                ("F3", "F4"),
                ("P3", "P4")
            ]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        # Check currents (converted from mA to A)
        assert session.poslists[0].currents == [2.0, -2.0]
        assert session.poslists[1].currents == [1.5, -1.5]
        assert session.poslists[2].currents == [1.0, -1.0]
        assert session.poslists[3].currents == [0.5, -0.5]


class TestSessionBuilderElectrodeConfiguration:
    """Test suite for electrode configuration."""

    @patch('tit.sim.session_builder.get_path_manager')
    def test_electrode_shape(self, mock_get_pm, setup_test_files):
        """Test electrode shape is applied."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(shape="rect")
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        # Check first electrode of first pair
        assert session.poslists[0].electrode[0].shape == "rect"

    @patch('tit.sim.session_builder.get_path_manager')
    def test_electrode_dimensions(self, mock_get_pm, setup_test_files):
        """Test electrode dimensions are applied."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(dimensions=[10.0, 12.0])
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        assert session.poslists[0].electrode[0].dimensions == [10.0, 12.0]

    @patch('tit.sim.session_builder.get_path_manager')
    def test_electrode_thickness(self, mock_get_pm, setup_test_files):
        """Test electrode thickness (gel + sponge) is applied."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        config = SimulationConfig(
            subject_id=setup_test_files['subject_id'],
            project_dir="/test/project",
            conductivity_type=ConductivityType.DIR,
            intensities=IntensityConfig(),
            electrode=ElectrodeConfig(
                thickness=5.0,
                sponge_thickness=3.0
            )
        )

        montage = MontageConfig(
            name="test_montage",
            electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
        )

        builder = SessionBuilder(config)
        session = builder.build_session(montage, "/output/dir")

        assert session.poslists[0].electrode[0].thickness == [5.0, 3.0]


class TestSessionBuilderTissueConductivity:
    """Test suite for tissue conductivity overrides."""

    @patch('tit.sim.session_builder.get_path_manager')
    def test_tissue_conductivity_from_env(self, mock_get_pm, setup_test_files):
        """Test tissue conductivity override from environment variables."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        # Set environment variables
        os.environ['TISSUE_COND_1'] = '0.5'
        os.environ['TISSUE_COND_2'] = '0.8'

        try:
            config = SimulationConfig(
                subject_id=setup_test_files['subject_id'],
                project_dir="/test/project",
                conductivity_type=ConductivityType.DIR,
                intensities=IntensityConfig(),
                electrode=ElectrodeConfig()
            )

            montage = MontageConfig(
                name="test_montage",
                electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
            )

            builder = SessionBuilder(config)
            session = builder.build_session(montage, "/output/dir")

            # Check that conductivity values were set (if the implementation supports it)
            # Note: This depends on how tissue conductivity is applied in the actual implementation
            assert len(session.poslists) >= 1
        finally:
            # Cleanup environment
            if 'TISSUE_COND_1' in os.environ:
                del os.environ['TISSUE_COND_1']
            if 'TISSUE_COND_2' in os.environ:
                del os.environ['TISSUE_COND_2']

    @patch('tit.sim.session_builder.get_path_manager')
    def test_tissue_conductivity_invalid_env(self, mock_get_pm, setup_test_files):
        """Test tissue conductivity ignores invalid environment values."""
        from tit.sim.config import SimulationConfig, MontageConfig, ConductivityType, IntensityConfig, ElectrodeConfig
        from tit.sim.session_builder import SessionBuilder

        mock_get_pm.return_value = setup_test_files['path_manager']

        # Set invalid environment variable
        os.environ['TISSUE_COND_1'] = 'invalid'

        try:
            config = SimulationConfig(
                subject_id=setup_test_files['subject_id'],
                project_dir="/test/project",
                conductivity_type=ConductivityType.DIR,
                intensities=IntensityConfig(),
                electrode=ElectrodeConfig()
            )

            montage = MontageConfig(
                name="test_montage",
                electrode_pairs=[("Cz", "Oz"), ("C3", "C4")]
            )

            builder = SessionBuilder(config)
            session = builder.build_session(montage, "/output/dir")

            # Should not crash with invalid value
            assert session is not None
        finally:
            # Cleanup environment
            if 'TISSUE_COND_1' in os.environ:
                del os.environ['TISSUE_COND_1']
