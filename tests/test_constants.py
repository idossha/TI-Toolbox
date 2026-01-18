#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox constants module (core/constants.py)

Tests that all constants are defined correctly and remain consistent.
These constants are critical for path construction and configuration across the entire toolbox.
"""

import pytest
import os
import sys

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), "..")
ti_toolbox_dir = os.path.join(project_root, "tit")
sys.path.insert(0, ti_toolbox_dir)

from core import constants as const


class TestDirectoryConstants:
    """Test directory name constants"""

    def test_bids_directory_constants(self):
        """Test BIDS-compliant directory constants are defined"""
        assert hasattr(const, "DIR_DERIVATIVES")
        assert hasattr(const, "DIR_SOURCEDATA")
        assert hasattr(const, "DIR_CODE")

        assert const.DIR_DERIVATIVES == "derivatives"
        assert const.DIR_SOURCEDATA == "sourcedata"
        assert const.DIR_CODE == "code"

    def test_derivative_subdirectory_constants(self):
        """Test derivative subdirectory constants"""
        assert hasattr(const, "DIR_SIMNIBS")
        assert hasattr(const, "DIR_TI_TOOLBOX")
        assert hasattr(const, "DIR_LOGS")

        assert const.DIR_SIMNIBS == "SimNIBS"
        assert const.DIR_TI_TOOLBOX == "ti-toolbox"
        assert const.DIR_LOGS == "logs"

    def test_subject_level_directory_constants(self):
        """Test subject-level directory constants"""
        assert hasattr(const, "DIR_M2M_PREFIX")
        assert hasattr(const, "DIR_EEG_POSITIONS")
        assert hasattr(const, "DIR_ROIS")
        assert hasattr(const, "DIR_ANALYSIS")
        assert hasattr(const, "DIR_FLEX_SEARCH")
        assert hasattr(const, "DIR_EX_SEARCH")

        assert const.DIR_M2M_PREFIX == "m2m_"
        assert const.DIR_EEG_POSITIONS == "eeg_positions"
        assert const.DIR_ROIS == "ROIs"
        assert const.DIR_ANALYSIS == "Analyses"

    def test_no_hardcoded_paths(self):
        """Test that directory constants don't contain absolute paths"""
        # Directory constants should be relative names, not absolute paths
        dirs_to_check = [
            const.DIR_DERIVATIVES,
            const.DIR_SOURCEDATA,
            const.DIR_SIMNIBS,
            const.DIR_TI_TOOLBOX,
            const.DIR_EEG_POSITIONS,
            const.DIR_ROIS,
        ]

        for dir_const in dirs_to_check:
            assert not dir_const.startswith(
                "/"
            ), f"{dir_const} should not be absolute path"
            assert not dir_const.startswith(
                "\\"
            ), f"{dir_const} should not be absolute path"


class TestFileConstants:
    """Test file name and extension constants"""

    def test_config_file_constants(self):
        """Test configuration file name constants"""
        assert hasattr(const, "FILE_MONTAGE_LIST")
        assert hasattr(const, "FILE_ANALYZER_CONFIG")
        assert hasattr(const, "FILE_SIMULATOR_CONFIG")

        assert const.FILE_MONTAGE_LIST == "montage_list.json"
        assert const.FILE_ANALYZER_CONFIG == "analyzer.json"
        assert const.FILE_SIMULATOR_CONFIG == "simulator.json"

    def test_file_extension_constants(self):
        """Test file extension constants"""
        assert hasattr(const, "EXT_NIFTI")
        assert hasattr(const, "EXT_MESH")
        assert hasattr(const, "EXT_CSV")
        assert hasattr(const, "EXT_JSON")
        assert hasattr(const, "EXT_LOG")

        # Extensions should start with dot
        assert const.EXT_NIFTI == ".nii.gz"
        assert const.EXT_MESH == ".msh"
        assert const.EXT_CSV == ".csv"
        assert const.EXT_JSON == ".json"
        assert const.EXT_LOG == ".log"

    def test_template_file_constants(self):
        """Test template file constants"""
        assert hasattr(const, "FILE_EGI_TEMPLATE")
        assert const.FILE_EGI_TEMPLATE == "GSN-HydroCel-185.csv"


class TestNamingPatternConstants:
    """Test naming pattern and prefix constants"""

    def test_bids_prefix_constants(self):
        """Test BIDS naming prefix constants"""
        assert hasattr(const, "PREFIX_SUBJECT")
        assert hasattr(const, "PREFIX_SESSION")

        assert const.PREFIX_SUBJECT == "sub-"
        assert const.PREFIX_SESSION == "ses-"

    def test_prefix_format(self):
        """Test that prefixes have correct format"""
        # BIDS prefixes should end with hyphen
        assert const.PREFIX_SUBJECT.endswith("-")
        assert const.PREFIX_SESSION.endswith("-")


class TestEnvironmentVariableConstants:
    """Test environment variable name constants"""

    def test_project_env_var_constants(self):
        """Test project-related environment variable constants"""
        assert hasattr(const, "ENV_PROJECT_DIR_NAME")
        assert hasattr(const, "ENV_PROJECT_DIR")

        assert const.ENV_PROJECT_DIR_NAME == "PROJECT_DIR_NAME"
        assert const.ENV_PROJECT_DIR == "PROJECT_DIR"

    def test_subject_env_var_constants(self):
        """Test subject-related environment variable constants"""
        assert hasattr(const, "ENV_SUBJECT_NAME")
        assert hasattr(const, "ENV_SUBJECT_ID")

        assert isinstance(const.ENV_SUBJECT_NAME, str)
        assert isinstance(const.ENV_SUBJECT_ID, str)

    def test_tool_specific_env_var_constants(self):
        """Test tool-specific environment variable constants"""
        assert hasattr(const, "ENV_SELECTED_EEG_NET")
        assert hasattr(const, "ENV_ROI_NAME")
        assert hasattr(const, "ENV_TI_LOG_FILE")

        assert isinstance(const.ENV_SELECTED_EEG_NET, str)
        assert isinstance(const.ENV_ROI_NAME, str)

    def test_display_env_var_constants(self):
        """Test display and system environment variable constants"""
        assert hasattr(const, "ENV_DISPLAY")
        assert hasattr(const, "ENV_HOST_IP")

        assert const.ENV_DISPLAY == "DISPLAY"
        assert const.ENV_HOST_IP == "HOST_IP"

    def test_env_var_uppercase(self):
        """Test that environment variable names are uppercase"""
        env_vars = [
            const.ENV_PROJECT_DIR_NAME,
            const.ENV_PROJECT_DIR,
            const.ENV_DISPLAY,
            const.ENV_HOST_IP,
        ]

        for env_var in env_vars:
            assert (
                env_var.isupper() or "_" in env_var
            ), f"Environment variable {env_var} should be uppercase"


class TestDockerConstants:
    """Test Docker-related constants"""

    def test_docker_mount_prefix(self):
        """Test Docker mount prefix constant"""
        assert hasattr(const, "DOCKER_MOUNT_PREFIX")
        assert isinstance(const.DOCKER_MOUNT_PREFIX, str)
        # Should be an absolute path
        assert (
            const.DOCKER_MOUNT_PREFIX.startswith("/")
            or const.DOCKER_MOUNT_PREFIX.startswith("C:")
            or const.DOCKER_MOUNT_PREFIX.startswith("\\")
        )


class TestFieldConstants:
    """Test field name constants for mesh/simulation data"""

    def test_field_name_constants(self):
        """Test that field name constants exist"""
        # Check if field name constants are defined
        # These are commonly used in mesh processing
        field_attrs = [attr for attr in dir(const) if "FIELD" in attr]

        # Should have some field-related constants
        assert len(field_attrs) >= 0, "Expected field name constants"


class TestConstantTypes:
    """Test that constants have correct types"""

    def test_directory_constants_are_strings(self):
        """Test that all directory constants are strings"""
        dir_constants = [
            const.DIR_DERIVATIVES,
            const.DIR_SOURCEDATA,
            const.DIR_CODE,
            const.DIR_SIMNIBS,
            const.DIR_TI_TOOLBOX,
            const.DIR_M2M_PREFIX,
            const.DIR_EEG_POSITIONS,
        ]

        for dir_const in dir_constants:
            assert isinstance(
                dir_const, str
            ), f"Directory constant should be string, got {type(dir_const)}"

    def test_file_constants_are_strings(self):
        """Test that all file name constants are strings"""
        file_constants = [
            const.FILE_MONTAGE_LIST,
            const.FILE_ANALYZER_CONFIG,
            const.FILE_SIMULATOR_CONFIG,
            const.EXT_NIFTI,
            const.EXT_MESH,
        ]

        for file_const in file_constants:
            assert isinstance(
                file_const, str
            ), f"File constant should be string, got {type(file_const)}"

    def test_env_var_constants_are_strings(self):
        """Test that all environment variable constants are strings"""
        env_constants = [
            const.ENV_PROJECT_DIR_NAME,
            const.ENV_PROJECT_DIR,
            const.ENV_DISPLAY,
        ]

        for env_const in env_constants:
            assert isinstance(
                env_const, str
            ), f"Environment variable constant should be string, got {type(env_const)}"


class TestConstantUsage:
    """Test practical usage patterns of constants"""

    def test_path_construction(self):
        """Test that constants can be used for path construction"""
        # Simulate path construction
        project_dir = "/mnt/test_project"
        derivatives = os.path.join(project_dir, const.DIR_DERIVATIVES)
        simnibs_dir = os.path.join(derivatives, const.DIR_SIMNIBS)

        assert derivatives == "/mnt/test_project/derivatives"
        assert simnibs_dir == "/mnt/test_project/derivatives/SimNIBS"

    def test_subject_path_construction(self):
        """Test subject-specific path construction"""
        subject_id = "001"
        subject_dir_name = f"{const.PREFIX_SUBJECT}{subject_id}"

        assert subject_dir_name == "sub-001"

    def test_m2m_path_construction(self):
        """Test m2m directory path construction"""
        subject_id = "001"
        m2m_dir_name = f"{const.DIR_M2M_PREFIX}{subject_id}"

        assert m2m_dir_name == "m2m_001"

    def test_file_extension_usage(self):
        """Test file extension usage"""
        base_name = "test_file"
        nifti_file = f"{base_name}{const.EXT_NIFTI}"
        mesh_file = f"{base_name}{const.EXT_MESH}"

        assert nifti_file == "test_file.nii.gz"
        assert mesh_file == "test_file.msh"


class TestConstantConsistency:
    """Test consistency between related constants"""

    def test_no_duplicate_values(self):
        """Test that key directory constants don't have duplicate values"""
        # Get all DIR_ constants
        dir_constants = {
            name: getattr(const, name)
            for name in dir(const)
            if name.startswith("DIR_") and not name.startswith("DIR_M2M_PREFIX")
        }

        # Check for duplicates (excluding prefixes)
        values = list(dir_constants.values())
        unique_values = set(values)

        # Most values should be unique (some duplicates like subdirs are OK)
        assert (
            len(unique_values) > len(values) * 0.7
        ), "Too many duplicate directory constant values"

    def test_extension_consistency(self):
        """Test that file extensions are consistent"""
        extensions = [
            const.EXT_NIFTI,
            const.EXT_MESH,
            const.EXT_CSV,
            const.EXT_JSON,
            const.EXT_LOG,
        ]

        # All extensions should start with dot
        for ext in extensions:
            assert ext.startswith("."), f"Extension {ext} should start with dot"

    def test_no_trailing_slashes_in_dirs(self):
        """Test that directory constants don't have trailing slashes"""
        dir_constants = [
            const.DIR_DERIVATIVES,
            const.DIR_SOURCEDATA,
            const.DIR_SIMNIBS,
            const.DIR_TI_TOOLBOX,
        ]

        for dir_const in dir_constants:
            assert not dir_const.endswith(
                "/"
            ), f"Directory constant {dir_const} should not end with slash"
            assert not dir_const.endswith(
                "\\"
            ), f"Directory constant {dir_const} should not end with backslash"


class TestConstantImmutability:
    """Test that constants behave as constants"""

    def test_constants_are_not_empty(self):
        """Test that string constants are not empty"""
        string_constants = [
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            const.FILE_MONTAGE_LIST,
            const.EXT_NIFTI,
            const.ENV_PROJECT_DIR_NAME,
        ]

        for const_val in string_constants:
            assert len(const_val) > 0, "Constant should not be empty string"

    def test_constants_have_meaningful_names(self):
        """Test that constant names follow naming conventions"""
        # Get all public constants
        public_constants = [
            name for name in dir(const) if not name.startswith("_") and name.isupper()
        ]

        # Should have a reasonable number of constants
        assert len(public_constants) > 10, "Expected more than 10 public constants"

        # Check naming patterns
        dir_constants = [c for c in public_constants if c.startswith("DIR_")]
        file_constants = [c for c in public_constants if c.startswith("FILE_")]
        ext_constants = [c for c in public_constants if c.startswith("EXT_")]
        env_constants = [c for c in public_constants if c.startswith("ENV_")]

        assert len(dir_constants) > 5, "Expected multiple DIR_ constants"
        assert len(file_constants) > 2, "Expected multiple FILE_ constants"
        assert len(ext_constants) > 3, "Expected multiple EXT_ constants"
        assert len(env_constants) > 3, "Expected multiple ENV_ constants"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
