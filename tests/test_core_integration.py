#!/usr/bin/env simnibs_python
"""
Integration tests for TI-Toolbox core modules

Tests integration between core modules (paths, constants, nifti, utils).
Ensures that modules work together correctly in realistic scenarios.
"""

import pytest
import os
import sys
import numpy as np
import tempfile
from pathlib import Path

# Add ti-toolbox directory to path
project_root = os.path.join(os.path.dirname(__file__), '..')
ti_toolbox_dir = os.path.join(project_root, 'ti-toolbox')
sys.path.insert(0, ti_toolbox_dir)

from core import get_path_manager, reset_path_manager, constants as const


class TestCoreModulesAvailability:
    """Test that all core modules can be imported"""

    def test_import_paths(self):
        """Test importing paths module"""
        from core import paths
        assert paths is not None

    def test_import_constants(self):
        """Test importing constants module"""
        from core import constants
        assert constants is not None

    def test_import_nifti(self):
        """Test importing nifti module"""
        from core import nifti
        assert nifti is not None

    def test_import_utils(self):
        """Test importing utils module"""
        from core import utils
        assert utils is not None

    def test_import_mesh(self):
        """Test importing mesh module"""
        from core import mesh
        assert mesh is not None

    def test_import_calc(self):
        """Test importing calc module"""
        from core import calc
        assert calc is not None

    def test_import_process(self):
        """Test importing process module"""
        from core import process
        assert process is not None

    def test_import_errors(self):
        """Test importing errors module"""
        from core import errors
        assert errors is not None


class TestCoreModuleInitialization:
    """Test core module initialization and singleton patterns"""

    def test_pathmanager_singleton_persistence(self):
        """Test PathManager singleton persists across imports"""
        from core import get_path_manager

        pm1 = get_path_manager()
        pm2 = get_path_manager()

        assert pm1 is pm2, "PathManager should be singleton"

    def test_constants_module_state(self):
        """Test that constants module maintains state"""
        from core import constants

        # Constants should be defined
        assert hasattr(constants, 'DIR_DERIVATIVES')
        assert hasattr(constants, 'ENV_PROJECT_DIR_NAME')

        # Values should be consistent
        value1 = constants.DIR_DERIVATIVES
        value2 = constants.DIR_DERIVATIVES
        assert value1 == value2


class TestPathsAndConstantsIntegration:
    """Test integration between paths and constants modules"""

    def test_pathmanager_uses_constants(self, tmp_path, monkeypatch):
        """Test that PathManager uses constants for directory names"""
        from core.paths import PathManager

        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name

        # Create derivatives directory using constant
        derivatives_dir = project_dir / const.DIR_DERIVATIVES
        derivatives_dir.mkdir(parents=True)

        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, project_name)
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(tmp_path / "mnt"))

        pm = PathManager()
        detected_derivatives = pm.get_derivatives_dir()

        # Should use constant for directory name
        assert detected_derivatives == str(derivatives_dir)

    def test_path_construction_with_constants(self):
        """Test constructing paths using constants"""
        # Simulate BIDS path construction
        project_dir = "/mnt/test_project"
        subject_id = "001"

        derivatives = os.path.join(project_dir, const.DIR_DERIVATIVES)
        simnibs_dir = os.path.join(derivatives, const.DIR_SIMNIBS)
        subject_dir = os.path.join(simnibs_dir, f"{const.PREFIX_SUBJECT}{subject_id}")
        m2m_dir = os.path.join(subject_dir, f"{const.DIR_M2M_PREFIX}{subject_id}")

        # Verify paths are constructed correctly
        assert derivatives == "/mnt/test_project/derivatives"
        assert simnibs_dir == "/mnt/test_project/derivatives/SimNIBS"
        assert subject_dir == "/mnt/test_project/derivatives/SimNIBS/sub-001"
        assert m2m_dir == "/mnt/test_project/derivatives/SimNIBS/sub-001/m2m_001"


class TestEnvironmentConfiguration:
    """Test environment-based configuration"""

    def test_project_detection_env_var(self, tmp_path, monkeypatch):
        """Test project detection using environment variable"""
        from core.paths import PathManager

        project_name = "my_project"
        project_dir = tmp_path / "mnt" / project_name
        project_dir.mkdir(parents=True)

        # Set environment variable using constant
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, project_name)
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(tmp_path / "mnt"))

        pm = PathManager()
        detected = pm.get_project_dir()

        assert detected == str(project_dir)

    def test_multiple_env_vars(self, monkeypatch):
        """Test handling multiple environment variables"""
        # Set multiple environment variables
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, "test_project")
        monkeypatch.setenv(const.ENV_SELECTED_EEG_NET, "EGI_template")
        monkeypatch.setenv(const.ENV_ROI_NAME, "hippocampus")

        # All should be accessible
        assert os.environ.get(const.ENV_PROJECT_DIR_NAME) == "test_project"
        assert os.environ.get(const.ENV_SELECTED_EEG_NET) == "EGI_template"
        assert os.environ.get(const.ENV_ROI_NAME) == "hippocampus"


class TestModuleInteroperability:
    """Test that modules work together correctly"""

    def test_import_from_core_package(self):
        """Test importing from core package"""
        # Should be able to import commonly used items
        from core import get_path_manager, constants

        assert get_path_manager is not None
        assert constants is not None

    def test_cross_module_constants_usage(self):
        """Test that constants are used consistently across modules"""
        from core import constants
        from core.paths import PathManager

        # PathManager should use same constants
        pm = PathManager()

        # Constants should be identical
        assert const.DIR_DERIVATIVES == constants.DIR_DERIVATIVES
        assert const.DIR_SIMNIBS == constants.DIR_SIMNIBS


class TestErrorHandling:
    """Test error handling across core modules"""

    def test_pathmanager_no_project_graceful(self, monkeypatch):
        """Test PathManager handles missing project gracefully"""
        from core.paths import PathManager

        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)

        pm = PathManager()

        # Should not crash, but return None
        assert pm.get_project_dir() is None
        assert pm.list_subjects() == []

    def test_invalid_env_var_handling(self, monkeypatch):
        """Test handling of invalid environment variables"""
        # Set invalid project directory
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, "nonexistent_project")

        from core.paths import PathManager

        pm = PathManager()

        # Should detect as None since directory doesn't exist
        result = pm.detect_project_dir()
        assert result is None


class TestDataTypeConsistency:
    """Test data type consistency across modules"""

    def test_constants_are_strings(self):
        """Test that directory/file constants are strings"""
        string_constants = [
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            const.FILE_MONTAGE_LIST,
            const.EXT_NIFTI,
            const.ENV_PROJECT_DIR_NAME
        ]

        for const_val in string_constants:
            assert isinstance(const_val, str), \
                f"Constant {const_val} should be string"

    def test_pathmanager_returns_consistent_types(self, tmp_path, monkeypatch):
        """Test PathManager returns consistent types"""
        from core.paths import PathManager

        project_name = "test_project"
        project_dir = tmp_path / "mnt" / project_name
        project_dir.mkdir(parents=True)

        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, project_name)
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(tmp_path / "mnt"))

        pm = PathManager()

        # String returns
        assert isinstance(pm.get_project_dir(), (str, type(None)))
        assert isinstance(pm.get_project_dir_name(), (str, type(None)))

        # List returns
        assert isinstance(pm.list_subjects(), list)


class TestCoreModuleDocumentation:
    """Test that core modules have proper documentation"""

    def test_modules_have_docstrings(self):
        """Test that core modules have docstrings"""
        from core import paths, constants, calc, mesh, process, errors

        modules_to_check = [paths, constants, calc, mesh, process, errors]

        for module in modules_to_check:
            assert module.__doc__ is not None, \
                f"Module {module.__name__} should have docstring"


class TestResetFunctionality:
    """Test reset and cleanup functionality"""

    def test_pathmanager_reset(self):
        """Test PathManager can be reset"""
        from core import get_path_manager, reset_path_manager

        pm1 = get_path_manager()
        reset_path_manager()
        pm2 = get_path_manager()

        # Should be different instances after reset
        assert pm1 is not pm2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
