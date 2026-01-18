#!/usr/bin/env simnibs_python
"""
Unit tests for sim.post_processor module.

Tests PostProcessor class for handling simulation post-processing:
- Initialization
- Directory structure creation
- File organization logic
- Safe file operations (mock subprocess calls)
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, Mock, patch, call
from types import ModuleType

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def mock_simnibs():
    """Mock simnibs module and dependencies."""
    # Create mock simnibs module
    simnibs_mod = ModuleType("simnibs")

    # Mock mesh class
    class MockMesh:
        def __init__(self, field_data=None):
            self.elmdata = []
            self.nodedata = []
            self.field = field_data or {}

        def crop_mesh(self, tags):
            return MockMesh(self.field)

        def add_element_field(self, data, name):
            self.field[name] = Mock(value=data)

        def add_node_field(self, data, name):
            self.field[name] = Mock(value=data)

        def view(self, visible_tags=None, visible_fields=None):
            mock_view = Mock()
            mock_view.write_opt = Mock(return_value=None)
            return mock_view

        def nodes_normals(self):
            import numpy as np

            mock_normals = Mock()
            mock_normals.value = np.array([[0, 0, 1], [0, 0, 1]])
            return mock_normals

    # Mock mesh_io
    mesh_io = MagicMock()
    mesh_io.read_msh = Mock(
        side_effect=lambda path: MockMesh(
            {
                "E": Mock(value=[[1, 0, 0], [0, 1, 0]]),
                "E_normal": Mock(value=[1.0, 1.0]),
            }
        )
    )
    mesh_io.write_msh = Mock(return_value=None)

    simnibs_mod.mesh_io = mesh_io

    # Install mock
    sys.modules["simnibs"] = simnibs_mod

    # Mock simnibs.utils.TI_utils
    simnibs_utils_mod = ModuleType("simnibs.utils")
    ti_utils = ModuleType("TI_utils")

    import numpy as np

    def mock_get_maxTI(e1, e2):
        return np.ones(len(e1)) if hasattr(e1, "__len__") else np.array([1.0])

    def mock_get_dirTI(e1, e2, normals):
        return np.zeros(len(e1)) if hasattr(e1, "__len__") else np.array([0.0])

    ti_utils.get_maxTI = mock_get_maxTI
    ti_utils.get_dirTI = mock_get_dirTI

    simnibs_utils_mod.TI_utils = ti_utils
    sys.modules["simnibs.utils"] = simnibs_utils_mod

    yield simnibs_mod

    # Cleanup
    if "simnibs" in sys.modules:
        del sys.modules["simnibs"]
    if "simnibs.utils" in sys.modules:
        del sys.modules["simnibs.utils"]


@pytest.fixture
def mock_core_calc():
    """Mock core.calc module."""
    core_calc = ModuleType("core.calc")

    import numpy as np

    def mock_get_TI_vectors(e1, e2):
        return (
            np.ones((len(e1), 3)) if hasattr(e1, "__len__") else np.array([[1, 0, 0]])
        )

    core_calc.get_TI_vectors = mock_get_TI_vectors

    sys.modules["core.calc"] = core_calc

    yield core_calc

    # Cleanup
    if "core.calc" in sys.modules:
        del sys.modules["core.calc"]


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    logger = MagicMock()
    logger.info = Mock()
    logger.debug = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    return logger


@pytest.fixture
def setup_test_structure(tmp_path):
    """Create test directory structure."""
    subject_id = "001"
    m2m_dir = (
        tmp_path / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / f"m2m_{subject_id}"
    )
    m2m_dir.mkdir(parents=True, exist_ok=True)

    # Create T1 file
    t1_file = m2m_dir / "T1.nii.gz"
    t1_file.write_text("dummy T1 data")

    # Create simulation directories
    sim_dir = (
        tmp_path
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / "Simulations"
        / "test_montage"
    )
    hf_dir = sim_dir / "high_Frequency"
    hf_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy mesh files
    for i in range(1, 5):
        mesh_file = hf_dir / f"{subject_id}_TDCS_{i}_scalar.msh"
        mesh_file.write_text("dummy mesh data")

    # Create subject_volumes directory
    volumes_dir = hf_dir / "subject_volumes"
    volumes_dir.mkdir(exist_ok=True)
    (volumes_dir / "dummy_volume.nii.gz").write_text("volume data")

    # Create subject_overlays directory
    overlays_dir = hf_dir / "subject_overlays"
    overlays_dir.mkdir(exist_ok=True)
    (overlays_dir / f"{subject_id}_TDCS_1_scalar_central.msh").write_text(
        "central mesh 1"
    )
    (overlays_dir / f"{subject_id}_TDCS_2_scalar_central.msh").write_text(
        "central mesh 2"
    )

    # Create fields_summary.txt
    (hf_dir / "fields_summary.txt").write_text("summary data")

    return {
        "subject_id": subject_id,
        "m2m_dir": str(m2m_dir),
        "sim_dir": str(sim_dir),
        "hf_dir": str(hf_dir),
        "volumes_dir": str(volumes_dir),
        "overlays_dir": str(overlays_dir),
        "t1_file": str(t1_file),
    }


@pytest.fixture
def load_post_processor(mock_simnibs, mock_core_calc):
    """Load PostProcessor after mocking dependencies."""
    from tit.sim.post_processor import PostProcessor

    return PostProcessor


class TestPostProcessorInitialization:
    """Test suite for PostProcessor initialization."""

    def test_initialization(
        self, load_post_processor, mock_logger, setup_test_structure
    ):
        """Test PostProcessor initializes with correct attributes."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id=setup_test_structure["subject_id"],
            conductivity_type="scalar",
            m2m_dir=setup_test_structure["m2m_dir"],
            logger=mock_logger,
        )

        assert processor.subject_id == setup_test_structure["subject_id"]
        assert processor.conductivity_type == "scalar"
        assert processor.m2m_dir == setup_test_structure["m2m_dir"]
        assert processor.logger == mock_logger

    def test_tools_dir_path(
        self, load_post_processor, mock_logger, setup_test_structure
    ):
        """Test PostProcessor sets tools_dir correctly."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id=setup_test_structure["subject_id"],
            conductivity_type="scalar",
            m2m_dir=setup_test_structure["m2m_dir"],
            logger=mock_logger,
        )

        assert "tools" in processor.tools_dir
        assert os.path.isabs(processor.tools_dir)


class TestPostProcessorSafeOperations:
    """Test suite for safe file operations."""

    def test_safe_move_success(self, load_post_processor, mock_logger, tmp_path):
        """Test _safe_move successfully moves files."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id="001",
            conductivity_type="scalar",
            m2m_dir=str(tmp_path),
            logger=mock_logger,
        )

        # Create source file
        src = tmp_path / "source.txt"
        src.write_text("test data")

        # Create destination directory
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        dest = dest_dir / "source.txt"

        processor._safe_move(str(src), str(dest))

        assert dest.exists()
        assert not src.exists()
        assert dest.read_text() == "test data"

    def test_safe_move_nonexistent(self, load_post_processor, mock_logger, tmp_path):
        """Test _safe_move handles non-existent source gracefully."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id="001",
            conductivity_type="scalar",
            m2m_dir=str(tmp_path),
            logger=mock_logger,
        )

        src = tmp_path / "nonexistent.txt"
        dest = tmp_path / "dest.txt"

        # Should not raise exception
        processor._safe_move(str(src), str(dest))
        assert not dest.exists()

    def test_safe_rmdir_success(self, load_post_processor, mock_logger, tmp_path):
        """Test _safe_rmdir removes empty directory."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id="001",
            conductivity_type="scalar",
            m2m_dir=str(tmp_path),
            logger=mock_logger,
        )

        # Create empty directory
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        processor._safe_rmdir(str(empty_dir))

        assert not empty_dir.exists()

    def test_safe_rmdir_nonempty(self, load_post_processor, mock_logger, tmp_path):
        """Test _safe_rmdir does not remove non-empty directory."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id="001",
            conductivity_type="scalar",
            m2m_dir=str(tmp_path),
            logger=mock_logger,
        )

        # Create non-empty directory
        nonempty_dir = tmp_path / "nonempty"
        nonempty_dir.mkdir()
        (nonempty_dir / "file.txt").write_text("data")

        processor._safe_rmdir(str(nonempty_dir))

        # Directory should still exist
        assert nonempty_dir.exists()


class TestPostProcessorTIFileOrganization:
    """Test suite for TI file organization."""

    def test_organize_ti_files_moves_mesh_files(
        self, load_post_processor, mock_logger, setup_test_structure
    ):
        """Test _organize_ti_files moves high-frequency mesh files."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id=setup_test_structure["subject_id"],
            conductivity_type="scalar",
            m2m_dir=setup_test_structure["m2m_dir"],
            logger=mock_logger,
        )

        # Create destination directories
        hf_mesh_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_mesh"
        )
        hf_nifti_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_nifti"
        )
        hf_analysis_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_analysis"
        )
        surface_overlays_dir = os.path.join(
            setup_test_structure["sim_dir"], "surface_overlays"
        )
        documentation_dir = os.path.join(
            setup_test_structure["sim_dir"], "documentation"
        )

        for d in [
            hf_mesh_dir,
            hf_nifti_dir,
            hf_analysis_dir,
            surface_overlays_dir,
            documentation_dir,
        ]:
            os.makedirs(d, exist_ok=True)

        processor._organize_ti_files(
            hf_dir=setup_test_structure["hf_dir"],
            hf_mesh_dir=hf_mesh_dir,
            hf_nifti_dir=hf_nifti_dir,
            hf_analysis_dir=hf_analysis_dir,
            surface_overlays_dir=surface_overlays_dir,
            documentation_dir=documentation_dir,
        )

        # Check that mesh files were moved
        assert os.path.exists(os.path.join(hf_mesh_dir, "001_TDCS_1_scalar.msh"))

    def test_organize_ti_files_moves_volumes(
        self, load_post_processor, mock_logger, setup_test_structure
    ):
        """Test _organize_ti_files moves subject_volumes files."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id=setup_test_structure["subject_id"],
            conductivity_type="scalar",
            m2m_dir=setup_test_structure["m2m_dir"],
            logger=mock_logger,
        )

        # Create destination directories
        hf_mesh_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_mesh"
        )
        hf_nifti_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_nifti"
        )
        hf_analysis_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_analysis"
        )
        surface_overlays_dir = os.path.join(
            setup_test_structure["sim_dir"], "surface_overlays"
        )
        documentation_dir = os.path.join(
            setup_test_structure["sim_dir"], "documentation"
        )

        for d in [
            hf_mesh_dir,
            hf_nifti_dir,
            hf_analysis_dir,
            surface_overlays_dir,
            documentation_dir,
        ]:
            os.makedirs(d, exist_ok=True)

        processor._organize_ti_files(
            hf_dir=setup_test_structure["hf_dir"],
            hf_mesh_dir=hf_mesh_dir,
            hf_nifti_dir=hf_nifti_dir,
            hf_analysis_dir=hf_analysis_dir,
            surface_overlays_dir=surface_overlays_dir,
            documentation_dir=documentation_dir,
        )

        # Check that volume files were moved
        assert os.path.exists(os.path.join(hf_nifti_dir, "dummy_volume.nii.gz"))
        # subject_volumes directory should be removed
        assert not os.path.exists(setup_test_structure["volumes_dir"])

    def test_organize_ti_files_moves_overlays(
        self, load_post_processor, mock_logger, setup_test_structure
    ):
        """Test _organize_ti_files moves subject_overlays files."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id=setup_test_structure["subject_id"],
            conductivity_type="scalar",
            m2m_dir=setup_test_structure["m2m_dir"],
            logger=mock_logger,
        )

        # Create destination directories
        hf_mesh_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_mesh"
        )
        hf_nifti_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_nifti"
        )
        hf_analysis_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_analysis"
        )
        surface_overlays_dir = os.path.join(
            setup_test_structure["sim_dir"], "surface_overlays"
        )
        documentation_dir = os.path.join(
            setup_test_structure["sim_dir"], "documentation"
        )

        for d in [
            hf_mesh_dir,
            hf_nifti_dir,
            hf_analysis_dir,
            surface_overlays_dir,
            documentation_dir,
        ]:
            os.makedirs(d, exist_ok=True)

        processor._organize_ti_files(
            hf_dir=setup_test_structure["hf_dir"],
            hf_mesh_dir=hf_mesh_dir,
            hf_nifti_dir=hf_nifti_dir,
            hf_analysis_dir=hf_analysis_dir,
            surface_overlays_dir=surface_overlays_dir,
            documentation_dir=documentation_dir,
        )

        # Check that overlay files were moved
        assert os.path.exists(
            os.path.join(surface_overlays_dir, "001_TDCS_1_scalar_central.msh")
        )
        # subject_overlays directory should be removed
        assert not os.path.exists(setup_test_structure["overlays_dir"])


class TestPostProcessorMTIFileOrganization:
    """Test suite for mTI file organization."""

    def test_organize_mti_files_renames_mesh_files(
        self, load_post_processor, mock_logger, setup_test_structure
    ):
        """Test _organize_mti_files renames HF files (1,2,3,4 -> A,B,C,D)."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id=setup_test_structure["subject_id"],
            conductivity_type="scalar",
            m2m_dir=setup_test_structure["m2m_dir"],
            logger=mock_logger,
        )

        # Create destination directories
        hf_mesh_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_mesh"
        )
        hf_analysis_dir = os.path.join(
            setup_test_structure["sim_dir"], "high_Frequency_analysis"
        )
        documentation_dir = os.path.join(
            setup_test_structure["sim_dir"], "documentation"
        )

        for d in [hf_mesh_dir, hf_analysis_dir, documentation_dir]:
            os.makedirs(d, exist_ok=True)

        processor._organize_mti_files(
            hf_dir=setup_test_structure["hf_dir"],
            hf_mesh_dir=hf_mesh_dir,
            hf_analysis_dir=hf_analysis_dir,
            documentation_dir=documentation_dir,
        )

        # Check that files were renamed
        assert os.path.exists(os.path.join(hf_mesh_dir, "001_TDCS_A_scalar.msh"))
        assert os.path.exists(os.path.join(hf_mesh_dir, "001_TDCS_B_scalar.msh"))
        assert os.path.exists(os.path.join(hf_mesh_dir, "001_TDCS_C_scalar.msh"))
        assert os.path.exists(os.path.join(hf_mesh_dir, "001_TDCS_D_scalar.msh"))


class TestPostProcessorExtractFields:
    """Test suite for field extraction."""

    @patch("subprocess.run")
    def test_extract_fields_uses_script(
        self, mock_subprocess, load_post_processor, mock_logger, tmp_path
    ):
        """Test _extract_fields uses field_extract.py script when available."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id="001",
            conductivity_type="scalar",
            m2m_dir=str(tmp_path),
            logger=mock_logger,
        )

        # Create dummy field_extract.py script
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        field_extract = tools_dir / "field_extract.py"
        field_extract.write_text("#!/usr/bin/env python\nprint('extracting')")

        # Override tools_dir
        processor.tools_dir = str(tools_dir)

        # Create input mesh
        input_mesh = tmp_path / "test.msh"
        input_mesh.write_text("mesh data")

        # Mock successful subprocess run
        mock_subprocess.return_value = Mock(returncode=0, stderr="")

        processor._extract_fields(str(input_mesh), str(tmp_path), "test")

        # Verify subprocess was called
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "simnibs_python" in call_args
        assert str(field_extract) in call_args

    @patch("subprocess.run")
    def test_extract_fields_handles_timeout(
        self, mock_subprocess, load_post_processor, mock_logger, tmp_path
    ):
        """Test _extract_fields handles subprocess timeout gracefully."""
        import subprocess as sp

        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id="001",
            conductivity_type="scalar",
            m2m_dir=str(tmp_path),
            logger=mock_logger,
        )

        # Create dummy field_extract.py script
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        field_extract = tools_dir / "field_extract.py"
        field_extract.write_text("#!/usr/bin/env python\nprint('extracting')")

        processor.tools_dir = str(tools_dir)

        # Create input mesh
        input_mesh = tmp_path / "test.msh"
        input_mesh.write_text("mesh data")

        # Mock timeout
        mock_subprocess.side_effect = sp.TimeoutExpired("cmd", 300)

        # Should not raise exception
        processor._extract_fields(str(input_mesh), str(tmp_path), "test")

        # Logger should have warning
        mock_logger.warning.assert_called()


class TestPostProcessorNiftiTransformation:
    """Test suite for NIfTI transformation."""

    @patch("subprocess.run")
    def test_transform_to_nifti_uses_script(
        self, mock_subprocess, load_post_processor, mock_logger, tmp_path
    ):
        """Test _transform_to_nifti uses mesh2nii_loop.sh script when available."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id="001",
            conductivity_type="scalar",
            m2m_dir=str(tmp_path),
            logger=mock_logger,
        )

        # Create dummy mesh2nii_loop.sh script
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        mesh2nii = tools_dir / "mesh2nii_loop.sh"
        mesh2nii.write_text("#!/bin/bash\necho 'converting'")

        processor.tools_dir = str(tools_dir)

        # Create mesh directory
        mesh_dir = tmp_path / "meshes"
        mesh_dir.mkdir()

        # Create output directory
        output_dir = tmp_path / "niftis"
        output_dir.mkdir()

        # Mock successful subprocess run
        mock_subprocess.return_value = Mock(returncode=0, stderr="")

        processor._transform_to_nifti(str(mesh_dir), str(output_dir))

        # Verify subprocess was called
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "bash" in call_args
        assert str(mesh2nii) in call_args


class TestPostProcessorT1Conversion:
    """Test suite for T1 to MNI conversion."""

    @patch("subprocess.run")
    def test_convert_t1_to_mni_success(
        self, mock_subprocess, load_post_processor, mock_logger, setup_test_structure
    ):
        """Test _convert_t1_to_mni runs subject2mni command."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id=setup_test_structure["subject_id"],
            conductivity_type="scalar",
            m2m_dir=setup_test_structure["m2m_dir"],
            logger=mock_logger,
        )

        # Mock successful subprocess run
        mock_subprocess.return_value = Mock(returncode=0, stderr="")

        processor._convert_t1_to_mni()

        # Verify subprocess was called
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "subject2mni" in call_args

    def test_convert_t1_to_mni_skips_if_exists(
        self, load_post_processor, mock_logger, setup_test_structure
    ):
        """Test _convert_t1_to_mni skips if MNI file already exists."""
        PostProcessor = load_post_processor

        processor = PostProcessor(
            subject_id=setup_test_structure["subject_id"],
            conductivity_type="scalar",
            m2m_dir=setup_test_structure["m2m_dir"],
            logger=mock_logger,
        )

        # Create MNI file
        m2m_path = setup_test_structure["m2m_dir"]
        mni_file = os.path.join(
            m2m_path, f"T1_{setup_test_structure['subject_id']}_MNI.nii.gz"
        )
        os.makedirs(os.path.dirname(mni_file), exist_ok=True)
        with open(mni_file, "w") as f:
            f.write("mni data")

        with patch("subprocess.run") as mock_subprocess:
            processor._convert_t1_to_mni()

            # Should not call subprocess
            mock_subprocess.assert_not_called()

    def test_convert_t1_to_mni_skips_if_no_t1(
        self, load_post_processor, mock_logger, tmp_path
    ):
        """Test _convert_t1_to_mni skips if T1 file doesn't exist."""
        PostProcessor = load_post_processor

        # Use temporary directory without T1 file
        processor = PostProcessor(
            subject_id="001",
            conductivity_type="scalar",
            m2m_dir=str(tmp_path),
            logger=mock_logger,
        )

        with patch("subprocess.run") as mock_subprocess:
            processor._convert_t1_to_mni()

            # Should not call subprocess
            mock_subprocess.assert_not_called()
