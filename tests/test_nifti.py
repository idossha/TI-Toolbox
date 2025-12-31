#!/usr/bin/env simnibs_python
"""
Unit tests for TI-Toolbox NIfTI module (core/nifti.py)

Tests NIfTI file loading functions for TI-Toolbox BIDS structure.
These functions are critical for loading simulation results and analysis data.
"""

import pytest
import os
import sys
import numpy as np
import nibabel as nib
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add tit directory to path
project_root = os.path.join(os.path.dirname(__file__), '..')
ti_toolbox_dir = os.path.join(project_root, 'tit')
sys.path.insert(0, ti_toolbox_dir)

from core.nifti import (
    load_subject_nifti_ti_toolbox,
    load_group_data_ti_toolbox,
    load_grouped_subjects_ti_toolbox
)
from core import constants as const
from core.paths import reset_path_manager


@pytest.fixture(scope="session")
def nifti_test_data(tmp_path_factory):
    """Create shared test data for all nifti tests"""
    tmp_path = tmp_path_factory.mktemp("nifti_shared")

    project_name = "test_project"
    project_dir = tmp_path / "mnt" / project_name

    # Create all subjects and simulations needed across all tests
    subjects_and_sims = [
        ("001", "montage1"),
        ("002", "montage1"),
        ("003", "montage1"),
        ("004", "montage1"),  # For grouped tests
        ("005", "montage1"),  # For memory test
    ]

    filepaths = {}
    for subject_id, sim_name in subjects_and_sims:
        nifti_dir = (project_dir / const.DIR_DERIVATIVES /
                    const.DIR_SIMNIBS / f"{const.PREFIX_SUBJECT}{subject_id}" /
                    "Simulations" / sim_name / "TI" / "niftis")
        nifti_dir.mkdir(parents=True)

        # Create mock NIfTI file with different values for each subject
        data = np.random.rand(10, 10, 10).astype(np.float32) * (int(subject_id) if subject_id.isdigit() else 1)
        img = nib.Nifti1Image(data, np.eye(4))

        filename = f"grey_{sim_name}_TI_MNI_MNI_TI_max.nii.gz"
        filepath = nifti_dir / filename
        nib.save(img, filepath)

        filepaths[f"{subject_id}_{sim_name}"] = str(filepath)

    return {
        'tmp_path': tmp_path,
        'project_dir': str(project_dir),
        'project_name': project_name,
        'filepaths': filepaths
    }


class TestLoadSubjectNifti:
    """Test load_subject_nifti_ti_toolbox function"""

    def test_load_subject_nifti_basic(self, nifti_test_data, monkeypatch):
        """Test basic NIfTI loading"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX',
                          str(nifti_test_data['tmp_path'] / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        data, img, filepath = load_subject_nifti_ti_toolbox(
            subject_id="001",
            simulation_name="montage1"
        )

        assert data.shape == (10, 10, 10)
        assert isinstance(img, nib.Nifti1Image)
        assert filepath == nifti_test_data['filepaths']['001_montage1']
        assert data.dtype == np.float32

    def test_load_subject_nifti_custom_pattern(self, nifti_test_data, monkeypatch):
        """Test loading with custom file pattern"""
        # Create file with custom pattern
        nifti_dir = Path(nifti_test_data['filepaths']['001_montage1']).parent
        custom_filename = "custom_montage1_file.nii.gz"
        custom_filepath = nifti_dir / custom_filename

        data = np.random.rand(10, 10, 10).astype(np.float32)
        img = nib.Nifti1Image(data, np.eye(4))
        nib.save(img, custom_filepath)

        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX',
                          str(nifti_test_data['tmp_path'] / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        loaded_data, loaded_img, loaded_path = load_subject_nifti_ti_toolbox(
            subject_id="001",
            simulation_name="montage1",
            nifti_file_pattern="custom_{simulation_name}_file.nii.gz"
        )

        assert loaded_data.shape == (10, 10, 10)
        assert loaded_path == str(custom_filepath)

    def test_load_subject_nifti_dtype(self, nifti_test_data, monkeypatch):
        """Test loading with different data types"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX',
                          str(nifti_test_data['tmp_path'] / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        # Load as float64
        data, img, filepath = load_subject_nifti_ti_toolbox(
            subject_id="001",
            simulation_name="montage1",
            dtype=np.float64
        )

        assert data.dtype == np.float64

    def test_load_subject_nifti_squeeze_dimensions(self, nifti_test_data, monkeypatch):
        """Test that extra dimensions are squeezed"""
        # Create 4D NIfTI file (should be squeezed to 3D)
        nifti_dir = Path(nifti_test_data['filepaths']['001_montage1']).parent

        # Create 4D data (with singleton 4th dimension)
        data_4d = np.random.rand(10, 10, 10, 1).astype(np.float32)
        img = nib.Nifti1Image(data_4d, np.eye(4))

        filename = "grey_montage1_TI_MNI_MNI_TI_max.nii.gz"
        filepath = nifti_dir / filename
        nib.save(img, filepath)  # Overwrite existing file

        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(nifti_test_data['tmp_path'] / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        data, img, filepath = load_subject_nifti_ti_toolbox(
            subject_id="001",
            simulation_name="montage1"
        )

        # Should be squeezed to 3D
        assert data.ndim == 3
        assert data.shape == (10, 10, 10)

    def test_load_subject_nifti_file_not_found(self, nifti_test_data, monkeypatch):
        """Test error when NIfTI file doesn't exist"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(nifti_test_data['tmp_path'] / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        with pytest.raises(FileNotFoundError):
            load_subject_nifti_ti_toolbox(
                subject_id="999",
                simulation_name="nonexistent"
            )

    def test_load_subject_nifti_no_project(self, monkeypatch):
        """Test error when project directory not found"""
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)

        reset_path_manager()  # Reset singleton after patching
        with pytest.raises(ValueError, match="Project directory not found"):
            load_subject_nifti_ti_toolbox(
                subject_id="001",
                simulation_name="montage1"
            )


class TestLoadGroupData:
    """Test load_group_data_ti_toolbox function"""

    def test_load_group_data_basic(self, nifti_test_data, monkeypatch):
        """Test loading group data"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX',
                          str(nifti_test_data['tmp_path'] / "mnt"))

        subject_configs = [
            {'subject_id': subj_id, 'simulation_name': "montage1"}
            for subj_id in ["001", "002", "003"]
        ]

        data_4d, template_img, subject_ids = load_group_data_ti_toolbox(subject_configs)

        # Check 4D array shape
        assert data_4d.shape == (10, 10, 10, 3)
        assert data_4d.dtype == np.float32

        # Check template image
        assert isinstance(template_img, nib.Nifti1Image)

        # Check subject IDs
        assert len(subject_ids) == 3
        assert set(subject_ids) == {"001", "002", "003"}

    def test_load_group_data_with_missing_subject(self, nifti_test_data, monkeypatch):
        """Test loading group data when one subject is missing"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX',
                          str(nifti_test_data['tmp_path'] / "mnt"))

        subject_configs = [
            {'subject_id': '001', 'simulation_name': "montage1"},
            {'subject_id': '002', 'simulation_name': "montage1"},
            {'subject_id': '999', 'simulation_name': "montage1"}  # Missing
        ]

        data_4d, template_img, subject_ids = load_group_data_ti_toolbox(subject_configs)

        # Should only load valid subjects
        assert data_4d.shape[3] == 2
        assert len(subject_ids) == 2
        assert '999' not in subject_ids

    def test_load_group_data_no_valid_subjects(self, nifti_test_data, monkeypatch):
        """Test error when no subjects can be loaded"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(nifti_test_data['tmp_path'] / "mnt"))

        subject_configs = [
            {'subject_id': '999', 'simulation_name': 'nonexistent'}
        ]

        with pytest.raises(ValueError, match="No subjects could be loaded"):
            load_group_data_ti_toolbox(subject_configs)

    def test_load_group_data_dtype(self, nifti_test_data, monkeypatch):
        """Test loading group data with different dtype"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX',
                          str(nifti_test_data['tmp_path'] / "mnt"))

        subject_configs = [
            {'subject_id': subj_id, 'simulation_name': "montage1"}
            for subj_id in ["001", "002", "003"]
        ]

        data_4d, template_img, subject_ids = load_group_data_ti_toolbox(
            subject_configs,
            dtype=np.float64
        )

        assert data_4d.dtype == np.float64


class TestLoadGroupedSubjects:
    """Test load_grouped_subjects_ti_toolbox function"""

    def test_load_grouped_subjects_basic(self, nifti_test_data, monkeypatch):
        """Test loading subjects organized by groups"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX',
                          str(nifti_test_data['tmp_path'] / "mnt"))

        subject_configs = [
            {'subject_id': '001', 'simulation_name': "montage1", 'group': 'group1'},
            {'subject_id': '002', 'simulation_name': "montage1", 'group': 'group1'},
            {'subject_id': '003', 'simulation_name': "montage1", 'group': 'group2'},
            {'subject_id': '004', 'simulation_name': "montage1", 'group': 'group2'}
        ]

        groups_data, template_img, groups_ids = load_grouped_subjects_ti_toolbox(subject_configs)

        # Check groups
        assert len(groups_data) == 2
        assert 'group1' in groups_data
        assert 'group2' in groups_data

        # Check group1 data
        assert groups_data['group1'].shape == (10, 10, 10, 2)
        assert len(groups_ids['group1']) == 2

        # Check group2 data
        assert groups_data['group2'].shape == (10, 10, 10, 2)
        assert len(groups_ids['group2']) == 2

        # Check template image
        assert isinstance(template_img, nib.Nifti1Image)

    def test_load_grouped_subjects_default_group(self, nifti_test_data, monkeypatch):
        """Test loading subjects without group specification"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX',
                          str(nifti_test_data['tmp_path'] / "mnt"))

        # Don't specify group (should use 'default')
        subject_configs = [
            {'subject_id': '001', 'simulation_name': "montage1"},
            {'subject_id': '002', 'simulation_name': "montage1"}
        ]

        groups_data, template_img, groups_ids = load_grouped_subjects_ti_toolbox(subject_configs)

        # Should be placed in 'default' group
        assert 'default' in groups_data
        assert groups_data['default'].shape[3] == 2


class TestNiftiIntegration:
    """Test integration scenarios"""

    def test_data_consistency_across_functions(self, nifti_test_data, monkeypatch):
        """Test that data loaded is consistent across different functions"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(nifti_test_data['tmp_path'] / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        # Load with single subject function
        data_single, _, _ = load_subject_nifti_ti_toolbox("001", "montage1")

        # Load with group function
        subject_configs = [{'subject_id': "001", 'simulation_name': "montage1"}]
        data_group, _, _ = load_group_data_ti_toolbox(subject_configs)

        # Data should be identical (within floating point precision)
        np.testing.assert_array_almost_equal(data_single, data_group[..., 0])


class TestMemoryManagement:
    """Test memory management in loading functions"""

    def test_group_loading_cleans_up(self, nifti_test_data, monkeypatch):
        """Test that group loading properly cleans up intermediate data"""
        # This is a behavioral test - we can't directly measure memory,
        # but we ensure the function completes without issues
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(nifti_test_data['tmp_path'] / "mnt"))

        subject_configs = [
            {'subject_id': subj_id, 'simulation_name': "montage1"}
            for subj_id in ["001", "002", "003", "004", "005"]
        ]

        # Should complete without memory errors
        data_4d, template_img, subject_ids = load_group_data_ti_toolbox(subject_configs)

        assert data_4d.shape == (10, 10, 10, 5)
        assert len(subject_ids) == 5


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_subject_configs(self, nifti_test_data, monkeypatch):
        """Test with empty subject configurations"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(nifti_test_data['tmp_path'] / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        with pytest.raises(ValueError, match="No subjects could be loaded"):
            load_group_data_ti_toolbox([])

    def test_invalid_simulation_name(self, nifti_test_data, monkeypatch):
        """Test with invalid simulation name"""
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, nifti_test_data['project_name'])
        monkeypatch.setattr(const, 'DOCKER_MOUNT_PREFIX', str(nifti_test_data['tmp_path'] / "mnt"))

        reset_path_manager()  # Reset singleton after patching
        with pytest.raises(FileNotFoundError):
            load_subject_nifti_ti_toolbox("001", "invalid_sim")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
