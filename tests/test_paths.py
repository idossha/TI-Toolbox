#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox path management module (core/paths.py)

Tests the PathManager singleton and all path resolution functions.
Critical for ensuring BIDS-compliant directory navigation works correctly.
"""

import pytest
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from core.paths import (
    PathManager,
    get_path_manager,
    reset_path_manager,
)
from core import constants as const


@pytest.fixture
def mock_subject_structure(tmp_path):
    """Create mock subject structure - module-level fixture for reuse"""
    project_name = "test_project"
    project_dir = tmp_path / "mnt" / project_name
    subject_id = "001"

    # Create subject directories
    subject_dir = (
        project_dir
        / const.DIR_DERIVATIVES
        / const.DIR_SIMNIBS
        / f"{const.PREFIX_SUBJECT}{subject_id}"
    )
    m2m_dir = subject_dir / f"{const.DIR_M2M_PREFIX}{subject_id}"
    simulations_dir = subject_dir / "Simulations"

    subject_dir.mkdir(parents=True)
    m2m_dir.mkdir(parents=True)
    simulations_dir.mkdir(parents=True)

    # Create some simulation directories
    (simulations_dir / "montage1").mkdir()
    (simulations_dir / "montage2").mkdir()

    return {
        "project_dir": str(project_dir),
        "project_name": project_name,
        "subject_id": subject_id,
        "subject_dir": str(subject_dir),
        "m2m_dir": str(m2m_dir),
        "simulations_dir": str(simulations_dir),
    }


class TestPathManagerBasics:
    """Test PathManager initialization and basic functionality"""

    def test_pathmanager_singleton(self):
        """Test that PathManager is a singleton"""
        pm1 = get_path_manager()
        pm2 = get_path_manager()
        assert pm1 is pm2, "PathManager should be a singleton"

    def test_reset_path_manager(self):
        """Test resetting the PathManager singleton"""
        pm1 = get_path_manager()
        reset_path_manager()
        pm2 = get_path_manager()
        assert pm1 is not pm2, "Reset should create new instance"

    def test_pathmanager_initialization(self):
        """Test PathManager initialization"""
        pm = PathManager()
        assert pm is not None
        assert hasattr(pm, "_project_dir")
        assert hasattr(pm, "project_dir_name")


class TestProjectDetection:
    """Test project directory detection"""

    def test_detect_project_dir_with_env_var(self, tmp_path, monkeypatch):
        """Test project detection using PROJECT_DIR_NAME environment variable"""
        # Create mock project structure
        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name
        project_dir.mkdir(parents=True)

        # Set environment variable
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, project_name)

        # Mock the Docker mount prefix
        monkeypatch.setattr(const, "DOCKER_MOUNT_PREFIX", str(tmp_path / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        # Create new PathManager instance
        pm = PathManager()
        detected = pm.project_dir

        assert detected == str(project_dir)

    def test_detect_project_dir_no_env_var(self, monkeypatch):
        """Test project detection fails gracefully without environment variable"""
        # Unset environment variable
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)

        pm = PathManager()
        detected = pm.project_dir

        assert detected is None

    def test_get_project_dir_name(self, tmp_path, monkeypatch):
        """Test getting project directory name"""
        project_name = "my_test_project"
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, project_name)

        pm = PathManager()
        name = pm.project_dir_name

        assert name == project_name


class TestDirectoryPaths:
    """Test various directory path getters"""

    @pytest.fixture
    def mock_project_structure(self, tmp_path):
        """Create a mock BIDS-compliant project structure"""
        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name

        # Create BIDS structure
        (project_dir / const.DIR_DERIVATIVES / const.DIR_SIMNIBS).mkdir(parents=True)
        (project_dir / const.DIR_SOURCEDATA).mkdir(parents=True)
        (project_dir / const.DIR_CODE).mkdir(parents=True)

        return {
            "project_dir": str(project_dir),
            "project_name": project_name,
            "derivatives": str(project_dir / const.DIR_DERIVATIVES),
            "simnibs": str(project_dir / const.DIR_DERIVATIVES / const.DIR_SIMNIBS),
        }

    def test_get_derivatives_dir(self, mock_project_structure, monkeypatch):
        """Test getting derivatives directory"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_project_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_project_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        derivatives_dir = pm.path("derivatives")

        assert derivatives_dir == mock_project_structure["derivatives"]

    def test_get_simnibs_dir(self, mock_project_structure, monkeypatch):
        """Test getting SimNIBS directory"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_project_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_project_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        simnibs_dir = pm.path("simnibs")

        assert simnibs_dir == mock_project_structure["simnibs"]


class TestSubjectPaths:
    """Test subject-specific path operations"""

    def test_get_subject_dir(self, mock_subject_structure, monkeypatch):
        """Test getting subject directory"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_subject_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_subject_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        subject_dir = pm.path(
            "simnibs_subject", subject_id=mock_subject_structure["subject_id"]
        )

        assert subject_dir == mock_subject_structure["subject_dir"]

    def test_get_m2m_dir(self, mock_subject_structure, monkeypatch):
        """Test getting m2m directory"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_subject_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_subject_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        m2m_dir = pm.path("m2m", subject_id=mock_subject_structure["subject_id"])

        assert m2m_dir == mock_subject_structure["m2m_dir"]

    def test_get_m2m_dir_nonexistent(self, mock_subject_structure, monkeypatch):
        """Test m2m path resolution for non-existent subject (path resolves; directory does not exist)."""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_subject_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_subject_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        m2m_dir = pm.path("m2m", subject_id="999")
        assert isinstance(m2m_dir, str)
        assert not os.path.isdir(m2m_dir)


class TestSubjectListing:
    """Test subject and simulation listing functions"""

    @pytest.fixture
    def mock_multi_subject_structure(self, tmp_path):
        """Create project with multiple subjects"""
        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name
        simnibs_dir = project_dir / const.DIR_DERIVATIVES / const.DIR_SIMNIBS

        # Create multiple subjects
        subjects = ["001", "002", "003"]
        for subj_id in subjects:
            subject_dir = simnibs_dir / f"{const.PREFIX_SUBJECT}{subj_id}"
            m2m_dir = subject_dir / f"{const.DIR_M2M_PREFIX}{subj_id}"
            m2m_dir.mkdir(parents=True)

        # Create invalid subject (no m2m directory)
        invalid_subj = simnibs_dir / f"{const.PREFIX_SUBJECT}999"
        invalid_subj.mkdir(parents=True)

        return {
            "project_dir": str(project_dir),
            "project_name": project_name,
            "subjects": subjects,
        }

    def test_list_subjects(self, mock_multi_subject_structure, monkeypatch):
        """Test listing all subjects"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_multi_subject_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_multi_subject_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        subjects = pm.list_subjects()

        assert len(subjects) == 3
        assert set(subjects) == set(mock_multi_subject_structure["subjects"])

    def test_list_subjects_no_project(self, monkeypatch):
        """Test listing subjects when no project is found"""
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)

        pm = PathManager()
        subjects = pm.list_subjects()

        assert subjects == []

    def test_list_simulations(self, mock_subject_structure, monkeypatch):
        """Test listing simulations for a subject"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_subject_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_subject_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        simulations = pm.list_simulations(mock_subject_structure["subject_id"])

        assert len(simulations) == 2
        assert set(simulations) == {"montage1", "montage2"}

    def test_list_simulations_nonexistent_subject(
        self, mock_subject_structure, monkeypatch
    ):
        """Test listing simulations for non-existent subject"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_subject_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_subject_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        simulations = pm.list_simulations("999")

        assert simulations == []


class TestSimulationPaths:
    """Test simulation-specific path operations"""

    @pytest.fixture
    def mock_simulation_structure(self, tmp_path):
        """Create mock simulation structure with TI output"""
        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name
        subject_id = "001"
        sim_name = "montage1"

        # Create simulation directory structure
        sim_dir = (
            project_dir
            / const.DIR_DERIVATIVES
            / const.DIR_SIMNIBS
            / f"{const.PREFIX_SUBJECT}{subject_id}"
            / "Simulations"
            / sim_name
        )
        ti_dir = sim_dir / "TI"
        ti_dir.mkdir(parents=True)

        # Create TI mesh file
        ti_mesh = ti_dir / f"{subject_id}_{sim_name}_TI.msh"
        ti_mesh.touch()

        return {
            "project_dir": str(project_dir),
            "project_name": project_name,
            "subject_id": subject_id,
            "sim_name": sim_name,
            "sim_dir": str(sim_dir),
            "ti_mesh": str(ti_mesh),
        }

    def test_get_simulation_dir(self, mock_simulation_structure, monkeypatch):
        """Test getting simulation directory"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_simulation_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_simulation_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        sim_dir = pm.path(
            "simulation",
            subject_id=mock_simulation_structure["subject_id"],
            simulation_name=mock_simulation_structure["sim_name"],
        )

        assert sim_dir == mock_simulation_structure["sim_dir"]

    def test_get_ti_mesh_path(self, mock_simulation_structure, monkeypatch):
        """Test getting TI mesh file path"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_simulation_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_simulation_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        ti_mesh = pm.path(
            "ti_mesh",
            subject_id=mock_simulation_structure["subject_id"],
            simulation_name=mock_simulation_structure["sim_name"],
        )

        # The actual implementation returns: TI/mesh/<sim>_TI.msh
        expected_path = os.path.join(
            mock_simulation_structure["sim_dir"],
            "TI",
            "mesh",
            f"{mock_simulation_structure['sim_name']}_TI{const.EXT_MESH}",
        )
        assert ti_mesh == expected_path


class TestValidation:
    """Test subject validation functions"""

    def test_validate_subject_structure_valid(
        self, mock_subject_structure, monkeypatch
    ):
        """Test validating a properly structured subject"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_subject_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_subject_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        validation = pm.validate_subject_structure(mock_subject_structure["subject_id"])

        # Check the actual validation structure returned by the implementation
        assert "valid" in validation
        assert isinstance(validation["valid"], bool)
        assert validation["valid"] is True
        assert "missing" in validation
        assert "warnings" in validation
        assert isinstance(validation["missing"], list)
        assert isinstance(validation["warnings"], list)

    def test_validate_subject_structure_invalid(
        self, mock_subject_structure, monkeypatch
    ):
        """Test validating a non-existent subject"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_subject_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_subject_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        validation = pm.validate_subject_structure("999")

        assert "valid" in validation
        assert validation["valid"] is False


class TestFreeSurferPaths:
    """Test FreeSurfer-specific path operations"""

    @pytest.fixture
    def mock_freesurfer_structure(self, tmp_path):
        """Create mock FreeSurfer structure"""
        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name
        subject_id = "001"

        # Create FreeSurfer directory
        fs_dir = (
            project_dir
            / const.DIR_DERIVATIVES
            / "freesurfer"
            / f"{const.PREFIX_SUBJECT}{subject_id}"
        )
        fs_mri_dir = fs_dir / "mri"
        fs_mri_dir.mkdir(parents=True)

        return {
            "project_dir": str(project_dir),
            "project_name": project_name,
            "subject_id": subject_id,
            "fs_dir": str(fs_dir),
            "fs_mri_dir": str(fs_mri_dir),
        }

    def test_get_freesurfer_subject_dir(self, mock_freesurfer_structure, monkeypatch):
        """Test getting FreeSurfer subject directory"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_freesurfer_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_freesurfer_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        fs_dir = pm.path(
            "freesurfer_subject", subject_id=mock_freesurfer_structure["subject_id"]
        )

        assert fs_dir == mock_freesurfer_structure["fs_dir"]

    def test_get_freesurfer_mri_dir(self, mock_freesurfer_structure, monkeypatch):
        """Test getting FreeSurfer MRI directory"""
        monkeypatch.setenv(
            const.ENV_PROJECT_DIR_NAME, mock_freesurfer_structure["project_name"]
        )
        monkeypatch.setattr(
            const,
            "DOCKER_MOUNT_PREFIX",
            os.path.dirname(mock_freesurfer_structure["project_dir"]),
        )

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()
        fs_mri_dir = pm.path(
            "freesurfer_mri", subject_id=mock_freesurfer_structure["subject_id"]
        )

        assert fs_mri_dir == mock_freesurfer_structure["fs_mri_dir"]


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_subject_id(self, tmp_path, monkeypatch):
        """Test handling of empty subject ID"""
        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name
        project_dir.mkdir(parents=True)

        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, project_name)
        monkeypatch.setattr(const, "DOCKER_MOUNT_PREFIX", str(tmp_path / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()

        # Empty subject ID returns a canonical "sub-" path.
        subject_dir = pm.path("simnibs_subject", subject_id="")
        expected_path = os.path.join(pm.path("simnibs"), "sub-")
        assert subject_dir == expected_path

    def test_special_characters_in_subject_id(self, tmp_path, monkeypatch):
        """Test handling of subject IDs with special characters"""
        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name
        simnibs_dir = project_dir / const.DIR_DERIVATIVES / const.DIR_SIMNIBS
        simnibs_dir.mkdir(parents=True)

        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, project_name)
        monkeypatch.setattr(const, "DOCKER_MOUNT_PREFIX", str(tmp_path / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()

        # Subject ID with special characters
        result = pm.path("simnibs_subject", subject_id="test@123")
        assert isinstance(result, str)

    def test_pathmanager_without_project(self, monkeypatch):
        """Test PathManager behavior when no project is found"""
        # Ensure no project environment is set
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)

        reset_path_manager()  # Reset singleton after patching
        pm = PathManager()

        # Should not crash, but return None for project-dependent operations
        assert pm.project_dir is None
        assert pm.list_subjects() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
