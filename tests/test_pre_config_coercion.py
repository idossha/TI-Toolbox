"""A pre config whose values do not have their declared type is refused, never coerced (p27).

What this pins (2026-10-22): ``PreprocessConfig``'s annotations are the contract -- ``subject_ids:
list[str]``, ``QSIPrepSettings.memory_gb: int | None`` and so on. Before this, a string sent for
a list was iterated character by character (``"001"`` became subjects ``0``, ``0``, ``1``, so the
runner preflighted and scaffolded ``sub-0``/``sub-1``), a string sent for a number survived to
``--mem-mb`` (``"16" * 1024``), and when ``deserialize_config`` did refuse, ``tit.pre.__main__``
fell back to a legacy constructor that accepted the same values verbatim and dropped
``charm_options``. Expected values come from those annotations, not from the code under test.

The refusal is checked at every place a pre config enters: ``deserialize_config`` itself, the
runner's ``_build_config``/``main``, ``check_job_config`` (``POST /api/jobs``) and
``POST /api/jobs/groups``. Reproduce: ``.venv/bin/python -m pytest
tests/test_pre_config_coercion.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from tit.config_io import deserialize_config
from tit.jobs.config_check import check_job_config
from tit.pre import __main__ as pre_main
from tit.pre.config import PreprocessConfig

BASE = {"subject_ids": ["001"], "run_qsiprep": True}


# ---------------------------------------------------------------------------------------------
# deserialize_config: wrong-typed values are named, not coerced
# ---------------------------------------------------------------------------------------------
ARRAY, NUMBER, OBJECT = "expected an array", "expected a number", "expected an object"


@pytest.mark.parametrize(
    "data, field, expected",
    [
        ({"subject_ids": "001"}, "PreprocessConfig.subject_ids", ARRAY),
        (
            {"subject_ids": ["001"], "freesurfer_subregions": "thalamus"},
            "PreprocessConfig.freesurfer_subregions",
            ARRAY,
        ),
        (
            {**BASE, "qsiprep_config": {"memory_gb": "16"}},
            "QSIPrepSettings.memory_gb",
            NUMBER,
        ),
        ({**BASE, "qsiprep_config": {"cpus": "4"}}, "QSIPrepSettings.cpus", NUMBER),
        (
            {**BASE, "qsiprep_config": {"output_resolution": "2"}},
            "QSIPrepSettings.output_resolution",
            NUMBER,
        ),
        (
            {"subject_ids": ["001"], "fastsurfer_threads": "8"},
            "PreprocessConfig.fastsurfer_threads",
            NUMBER,
        ),
        (
            {"subject_ids": ["001"], "freesurfer_threads": True},
            "PreprocessConfig.freesurfer_threads",
            NUMBER,
        ),
        (
            {
                "subject_ids": ["001"],
                "run_qsirecon": True,
                "qsi_recon_config": {"atlases": "AAL116"},
            },
            "QSIReconSettings.atlases",
            ARRAY,
        ),
        (
            {**BASE, "qsiprep_config": "patch2self"},
            "PreprocessConfig.qsiprep_config",
            OBJECT,
        ),
    ],
    ids=[
        "subject_ids-str",
        "subregions-str",
        "memory_gb-str",
        "cpus-str",
        "output_resolution-str",
        "fastsurfer_threads-str",
        "threads-bool",
        "atlases-str",
        "qsiprep_config-str",
    ],
)
def test_a_value_of_the_wrong_type_is_refused_naming_its_field(data, field, expected):
    with pytest.raises(
        ValueError, match=rf"^{field.replace('.', '[.]')}: {expected}, got "
    ):
        deserialize_config(PreprocessConfig, data)


def test_values_of_the_declared_types_still_deserialize():
    """Ints are valid floats (JSON has one number type); lists stay lists."""
    config = deserialize_config(
        PreprocessConfig,
        {
            **BASE,
            "subject_ids": ["001", "002"],
            "freesurfer_subregions": ["thalamus"],
            "qsiprep_config": {"memory_gb": 16, "cpus": 4, "output_resolution": 2},
            "qsi_recon_config": {"atlases": ["AAL116"], "memory_gb": None},
            "run_qsirecon": True,
        },
    )
    assert config.subject_ids == ["001", "002"]
    assert config.freesurfer_subregions == ["thalamus"]
    assert config.qsiprep_config.memory_gb == 16
    assert config.qsiprep_config.output_resolution == 2
    assert config.qsi_recon_config.atlases == ["AAL116"]
    assert config.qsi_recon_config.memory_gb is None


# ---------------------------------------------------------------------------------------------
# The runner: no legacy fallback
# ---------------------------------------------------------------------------------------------
def test_the_runner_keeps_charm_options():
    built = pre_main._build_config(
        {"subject_ids": ["001"], "create_m2m": True, "charm_options": {"denoise": True}}
    )
    assert built.charm_options == {"denoise": True}


@pytest.mark.parametrize(
    "data",
    [
        {"subject_ids": "001", "convert_dicom": True},
        {**BASE, "qsiprep_config": {"memory_gb": "16"}},
        # A refused value elsewhere in the config must not cost the user their charm options
        # by falling back to a constructor that never read them.
        {
            "subject_ids": ["001"],
            "create_m2m": True,
            "charm_options": {"denoise": True},
            "fastsurfer_threads": "8",
        },
    ],
    ids=["subject_ids-str", "memory_gb-str", "with-charm-options"],
)
def test_the_runner_refuses_what_deserialize_config_refuses(data):
    with pytest.raises(ValueError):
        pre_main._build_config(data)


def test_the_runner_exits_before_any_subject_is_touched(tmp_path, monkeypatch):
    """``python -m tit.pre`` with ``subject_ids: "001"`` stops with the config error."""
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {"project_dir": str(tmp_path), "subject_ids": "001", "convert_dicom": True}
        )
    )
    monkeypatch.setattr(sys, "argv", ["tit.pre", str(config)])
    with (
        patch("tit.pre.__main__.run_pipeline") as run_pipeline,
        patch("tit.logger.add_stream_handler"),
        pytest.raises(SystemExit) as stop,
    ):
        pre_main.main()
    run_pipeline.assert_not_called()
    assert str(stop.value.code).startswith("Invalid preprocessing config:")
    assert "subject_ids" in str(stop.value.code)
    assert not (tmp_path / "sub-0").exists() and not (tmp_path / "sub-1").exists()


# ---------------------------------------------------------------------------------------------
# Submission: POST /api/jobs (check_job_config) and POST /api/jobs/groups
# ---------------------------------------------------------------------------------------------
def test_check_job_config_refuses_a_string_memory_for_a_pre_job():
    with pytest.raises(ValueError, match=r"QSIPrepSettings\.memory_gb"):
        check_job_config("pre", {**BASE, "qsiprep_config": {"memory_gb": "16"}})


def test_check_job_config_refuses_a_string_subject_list_for_a_pre_job():
    with pytest.raises(ValueError, match="subject_ids"):
        check_job_config("pre", {"subject_ids": "001", "convert_dicom": True})


def test_check_job_config_accepts_a_pre_job_whose_subjects_are_in_the_body():
    """``POST /api/jobs`` may carry a pre job's subjects beside the config; the manager writes
    them into ``config.json`` (``JobManager._runner_config_path``), so they are not missing.
    """
    check_job_config(
        "pre",
        {
            "run_qsiprep": True,
            "qsiprep_config": {"memory_gb": 16},
            "project_dir": "/p",
        },
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tit.jobs import bootstrap
    from tit.jobs.manager import JobManager
    from tit.jobs.spec import Cost
    from tit.paths import get_path_manager
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: tmp_path / "prefs.json"
    )
    get_path_manager(str(tmp_path))
    manager = JobManager(str(tmp_path), budget=Cost(cpus=8, mem_gb=64))
    bootstrap.set_manager_for_testing(manager)
    yield TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="t")),
        base_url="http://127.0.0.1:8765",
    ), manager
    bootstrap.reset_manager()


@pytest.mark.parametrize("route", ["/api/jobs", "/api/jobs/groups"])
def test_submission_refuses_a_string_memory_before_anything_is_queued(client, route):
    http, manager = client
    r = http.post(
        route,
        headers={"Authorization": "Bearer t"},
        json={
            "kind": "pre",
            "config": {**BASE, "qsiprep_config": {"memory_gb": "16"}},
            "subject_ids": ["001"],
        },
    )
    assert r.status_code == 422, r.text
    assert "memory_gb" in r.json()["detail"]
    assert manager.list_jobs() == []
