"""Resource preferences persist per user and produce honest job reservations."""

import json

import pytest
from pydantic import ValidationError

from tit import surfer_settings as prefs
from tit.jobs.costs import default_cost
from tit.server.routes.surfer_settings import SurferPreferences, put_surfer_settings


@pytest.fixture(autouse=True)
def user_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(
        prefs.PathManager, "user_config_dir", staticmethod(lambda: str(tmp_path))
    )
    monkeypatch.setattr(prefs.os, "cpu_count", lambda: 12)
    # Keep CI worker affinity from shrinking the synthetic 12-CPU host.
    monkeypatch.setattr(
        prefs.os, "sched_getaffinity", lambda pid: set(range(12)), raising=False
    )
    monkeypatch.setattr(prefs, "get_container_resource_limits", lambda: (None, None))
    monkeypatch.delenv("TIT_FASTSURFER_THREADS", raising=False)


def test_automatic_leaves_one_thread_for_host_and_respects_container_quota(monkeypatch):
    assert prefs.read_settings()["default_threads"] == 11
    monkeypatch.setattr(prefs, "get_container_resource_limits", lambda: (5, None))
    assert prefs.effective_threads("fastsurfer") == 4
    assert prefs.effective_threads("freesurfer") == 4


def test_user_preferences_persist_and_clamp_to_current_capacity():
    response = put_surfer_settings(
        SurferPreferences(fastsurfer_threads=30, freesurfer_threads=3)
    )
    assert response.effective_fastsurfer_threads == 12
    assert response.effective_freesurfer_threads == 3
    assert json.loads(prefs.settings_path().read_text())["fastsurfer_threads"] == 30
    assert prefs.effective_threads("fastsurfer", 20) == 20


def test_job_snapshot_keeps_cost_and_execution_consistent():
    config = prefs.resolve_job_threads({"run_fastsurfer": True})
    prefs.save_preferences({"fastsurfer_threads": 2, "freesurfer_threads": None})
    assert config["fastsurfer_threads"] == 11
    assert default_cost("pre", config).cpus == 11
    assert prefs.effective_threads("fastsurfer", config["fastsurfer_threads"]) == 11
    assert default_cost("pre", {"run_fastsurfer": True}).cpus == 2


def test_environment_override_matches_reservation(monkeypatch):
    monkeypatch.setenv("TIT_FASTSURFER_THREADS", "6")
    assert default_cost("pre", {"run_fastsurfer": True}).cpus == 6


@pytest.mark.parametrize("value", [0, -1, 4097, True, 1.5, "2"])
def test_invalid_preferences_rejected(value):
    with pytest.raises(ValidationError):
        SurferPreferences(fastsurfer_threads=value)


def test_reset_and_corrupt_preferences_use_automatic():
    prefs.settings_path().write_text("[]")
    assert prefs.effective_threads("freesurfer") == 11
    put_surfer_settings(SurferPreferences())
    assert prefs.load_preferences() == prefs.default_preferences()


def test_http_preferences_roundtrip_and_invalid_body():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tit.server.routes.surfer_settings import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        saved = client.put(
            "/api/surfer-settings",
            json={"fastsurfer_threads": 3, "freesurfer_threads": None},
        )
        assert saved.status_code == 200
        assert (
            client.get("/api/surfer-settings").json()["effective_fastsurfer_threads"]
            == 3
        )
        assert (
            client.put(
                "/api/surfer-settings", json={"fastsurfer_threads": True}
            ).status_code
            == 422
        )
        assert client.get("/api/surfer-settings").json()["fastsurfer_threads"] == 3


def test_all_reconstruction_operations_enabled_by_default():
    settings = prefs.read_settings()
    assert settings["freesurfer_recon_all"] is True
    assert settings["freesurfer_subregions"] == ["thalamus", "hippo-amygdala"]


def test_preprocessing_resources_snapshot_and_preserve_overrides():
    prefs.save_preferences(
        {
            "charm_threads": 4,
            "qsiprep_threads": 5,
            "qsiprep_memory_gb": 10,
            "qsiprep_omp_threads": 2,
        }
    )
    result = prefs.resolve_job_threads(
        {
            "create_m2m": True,
            "run_qsiprep": True,
            "qsiprep_config": {"denoise_method": "none"},
        }
    )
    assert result["charm_threads"] == 4
    assert result["qsiprep_config"] == {
        "denoise_method": "none",
        "cpus": 5,
        "memory_gb": 10,
        "omp_threads": 2,
    }
    assert default_cost("pre", result).cpus == 5
    assert default_cost("pre", result).mem_gb == 10
    explicit = prefs.resolve_job_threads(
        {
            "create_m2m": True,
            "charm_threads": 2,
            "run_qsiprep": True,
            "qsiprep_config": {"cpus": 3, "memory_gb": 8, "omp_threads": 1},
        }
    )
    assert explicit["charm_threads"] == 2
    assert explicit["qsiprep_config"] == {"cpus": 3, "memory_gb": 8, "omp_threads": 1}


def test_partial_updates_preserve_other_user_preferences():
    put_surfer_settings(
        SurferPreferences(charm_threads=4, freesurfer_subregions=["thalamus"])
    )
    put_surfer_settings(SurferPreferences(fastsurfer_threads=2))
    assert prefs.load_preferences()["charm_threads"] == 4
    assert prefs.load_preferences()["freesurfer_subregions"] == ["thalamus"]


def test_empty_freesurfer_operation_selection_rejected():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        put_surfer_settings(
            SurferPreferences(freesurfer_recon_all=False, freesurfer_subregions=[])
        )
    assert error.value.status_code == 422


def test_qsi_defaults_match_pipeline_dataclasses():
    from dataclasses import asdict
    from tit.pre.config import QSIPrepSettings, QSIReconSettings

    saved = prefs.load_preferences()
    for key, config in (
        ("qsiprep_config", QSIPrepSettings()),
        ("qsi_recon_config", QSIReconSettings()),
    ):
        pipeline_defaults = asdict(config)
        for resource in ("cpus", "memory_gb", "omp_threads"):
            pipeline_defaults.pop(resource)
        assert saved[key] == pipeline_defaults


def test_qsi_nested_partial_updates_persist_without_changing_resources():
    put_surfer_settings(
        SurferPreferences(
            qsiprep_threads=4,
            qsiprep_config={"output_resolution": 1.5, "denoise_method": "none"},
        )
    )
    put_surfer_settings(
        SurferPreferences(
            qsiprep_config={"unringing_method": "rpg"},
            qsi_recon_config={"recon_specs": ["dipy_dki"], "atlases": ["AAL116"]},
        )
    )
    stored = json.loads(prefs.settings_path().read_text())
    assert stored["qsiprep_threads"] == 4
    assert stored["qsiprep_config"]["output_resolution"] == 1.5
    assert stored["qsiprep_config"]["denoise_method"] == "none"
    assert stored["qsiprep_config"]["unringing_method"] == "rpg"
    assert prefs.read_settings()["qsi_recon_config"]["recon_specs"] == ["dipy_dki"]
    put_surfer_settings(SurferPreferences(qsi_recon_config={"atlases": None}))
    assert prefs.read_settings()["qsi_recon_config"]["atlases"] is None
    assert prefs.read_settings()["qsi_recon_config"]["recon_specs"] == ["dipy_dki"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("qsiprep_config", {"output_resolution": 0}),
        ("qsiprep_config", {"output_resolution": float("inf")}),
        ("qsiprep_config", {"denoise_method": "unknown"}),
        ("qsiprep_config", {"cpus": 4}),
        ("qsi_recon_config", {"recon_specs": []}),
        ("qsi_recon_config", {"recon_specs": ["unknown"]}),
        ("qsi_recon_config", {"atlases": ["unknown"]}),
        ("qsi_recon_config", {"use_gpu": "yes"}),
    ],
)
def test_invalid_qsi_preferences_do_not_replace_saved_choices(key, value):
    prefs.save_preferences({"qsiprep_config": {"output_resolution": 1.5}})
    with pytest.raises(ValueError):
        prefs.save_preferences({key: value})
    assert prefs.load_preferences()["qsiprep_config"]["output_resolution"] == 1.5


def test_corrupt_qsi_preferences_fall_back_independently():
    prefs.settings_path().write_text(
        json.dumps(
            {
                "qsiprep_config": {"output_resolution": -1},
                "qsi_recon_config": {"recon_specs": ["dipy_dki"]},
                "qsiprep_threads": 3,
            }
        )
    )
    saved = prefs.load_preferences()
    assert saved["qsiprep_config"]["output_resolution"] == 2.0
    assert saved["qsi_recon_config"]["recon_specs"] == ["dipy_dki"]
    assert saved["qsiprep_threads"] == 3


def test_charm_options_are_user_defaults_snapshotted_per_job():
    put_surfer_settings(
        SurferPreferences(
            charm_options={"denoise": False, "segmentation_final_resolution": 0.8}
        )
    )
    result = prefs.resolve_job_threads({"create_m2m": True})
    assert result["charm_options"] == {
        "denoise": False,
        "segmentation_final_resolution": 0.8,
    }
    put_surfer_settings(SurferPreferences(charm_options=None))
    assert prefs.load_preferences()["charm_options"] is None
    assert result["charm_options"]["denoise"] is False
    assert prefs.resolve_job_threads(
        {"create_m2m": True, "charm_options": {"skin_facet_size": 3}}
    )["charm_options"] == {"skin_facet_size": 3}
