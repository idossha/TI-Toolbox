#!/usr/bin/env simnibs_python
"""
Unit tests for `tit.analyzer.field_selector`.

These tests avoid SimNIBS and focus on file/path selection logic.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _make_project(
    tmp_path: Path, subject_id: str, montage: str
) -> tuple[str, str, Path]:
    project_dir = tmp_path / "mnt" / "proj"
    m2m_dir = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / f"m2m_{subject_id}"
    )
    sim_dir = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / "Simulations"
        / montage
    )
    m2m_dir.mkdir(parents=True, exist_ok=True)
    sim_dir.mkdir(parents=True, exist_ok=True)
    return subject_id, montage, project_dir


def test_select_field_file_mesh_prefers_mti_when_present(tmp_path, monkeypatch):
    # Arrange
    subject_id, montage, project_dir = _make_project(tmp_path, "001", "montage1")
    m2m_dir = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / f"m2m_{subject_id}"
    )

    # Create mTI mesh folder + file
    mti_mesh = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / "Simulations"
        / montage
        / "mTI"
        / "mesh"
    )
    mti_mesh.mkdir(parents=True, exist_ok=True)
    (mti_mesh / f"{montage}_mTI.msh").write_text("dummy")

    # Point PathManager env resolution at this temp project
    from tit.core import constants as const

    monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, "proj")
    monkeypatch.setattr(const, "DOCKER_MOUNT_PREFIX", str(tmp_path / "mnt"))

    from tit.analyzer.field_selector import select_field_file

    # Act
    field_path, field_name = select_field_file(str(m2m_dir), montage, space="mesh")

    # Assert
    assert field_path.endswith(f"{montage}_mTI.msh")
    assert field_name in {"TI_Max", "TI_max"}  # depends on mTI detection


def test_select_field_file_voxel_finds_grey_file(tmp_path, monkeypatch):
    subject_id, montage, project_dir = _make_project(tmp_path, "001", "montage1")
    m2m_dir = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / f"m2m_{subject_id}"
    )
    nifti_dir = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / "Simulations"
        / montage
        / "TI"
        / "niftis"
    )
    nifti_dir.mkdir(parents=True, exist_ok=True)
    (nifti_dir / "grey_TI_max.nii.gz").write_text("dummy")

    from tit.core import constants as const

    monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, "proj")
    monkeypatch.setattr(const, "DOCKER_MOUNT_PREFIX", str(tmp_path / "mnt"))

    from tit.analyzer.field_selector import select_field_file

    field_path, field_name = select_field_file(str(m2m_dir), montage, space="voxel")
    assert field_path.endswith("grey_TI_max.nii.gz")
    assert field_name == "TI_max"


def test_select_field_file_invalid_space_raises(tmp_path, monkeypatch):
    subject_id, montage, project_dir = _make_project(tmp_path, "001", "montage1")
    m2m_dir = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject_id}"
        / f"m2m_{subject_id}"
    )

    from tit.core import constants as const

    monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, "proj")
    monkeypatch.setattr(const, "DOCKER_MOUNT_PREFIX", str(tmp_path / "mnt"))

    from tit.analyzer.field_selector import select_field_file

    with pytest.raises(ValueError):
        select_field_file(str(m2m_dir), montage, space="nope")
