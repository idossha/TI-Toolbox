#!/usr/bin/env simnibs_python
"""
Additional unit tests for the template-based PathManager resolver.

Focus:
- key/entity validation
- optional resolution behavior
- directory creation helper
"""

import os
from pathlib import Path

import pytest

from tit.core.paths import PathManager, reset_path_manager
from tit.core import constants as const


@pytest.fixture
def pm_in_tmp_project(tmp_path, monkeypatch) -> PathManager:
    project_name = "test_project"
    project_dir = tmp_path / "mnt" / project_name
    project_dir.mkdir(parents=True)
    monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, project_name)
    monkeypatch.setattr(const, "DOCKER_MOUNT_PREFIX", str(tmp_path / "mnt"))
    reset_path_manager()
    return PathManager()


def test_path_unknown_key_raises(pm_in_tmp_project: PathManager):
    with pytest.raises(KeyError):
        pm_in_tmp_project.path("does_not_exist")


def test_path_missing_entities_raises(pm_in_tmp_project: PathManager):
    with pytest.raises(ValueError):
        pm_in_tmp_project.path("m2m")  # requires subject_id


def test_path_optional_missing_entities_returns_none(pm_in_tmp_project: PathManager):
    assert pm_in_tmp_project.path_optional("m2m") is None


def test_path_optional_unknown_key_returns_none(pm_in_tmp_project: PathManager):
    assert pm_in_tmp_project.path_optional("does_not_exist") is None


def test_ensure_dir_creates_directory(pm_in_tmp_project: PathManager):
    p = pm_in_tmp_project.ensure_dir("ti_logs", subject_id="001")
    assert isinstance(p, str)
    assert os.path.isdir(p)


def test_path_rendering_is_deterministic(pm_in_tmp_project: PathManager):
    a = pm_in_tmp_project.path("simulation", subject_id="001", simulation_name="montage1")
    b = pm_in_tmp_project.path("simulation", simulation_name="montage1", subject_id="001")  # kwargs order differs
    assert a == b


