"""The user's own FreeSurfer license: stored once, resolved for licensed stages only.

The license is issued per registered person and is never bundled or fetched, so
the toolbox only ever stores what the user pasted. FastSurfer ``--seg_only``
needs none; recon-all and the subregion tools do, and preflight must say which.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tit import surfer_settings as prefs
from tit.pre.preflight import (
    STEP_FASTSURFER,
    STEP_FREESURFER,
    STEP_FREESURFER_HIPPO,
    STEP_FREESURFER_THALAMUS,
    find_missing_preprocessing_inputs,
    missing_freesurfer_license,
)
from tit.pre.qsi.docker_builder import resolve_fs_license_path

LICENSE = "someone@example.org\n12345\n *Ab1cD2eF3gH\n FSabc123DEF456\n"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(
        prefs.PathManager, "user_config_dir", staticmethod(lambda: str(tmp_path))
    )
    monkeypatch.delenv("FS_LICENSE", raising=False)
    monkeypatch.setattr(
        "tit.pre.qsi.docker_builder.const.FS_LICENSE_PATH",
        str(tmp_path / "image-placeholder-license.txt"),
    )
    monkeypatch.setattr(prefs, "get_container_resource_limits", lambda: (None, None))
    return tmp_path


def test_nothing_stored_resolves_to_none():
    assert resolve_fs_license_path() is None
    assert prefs.freesurfer_license_status() == {
        "configured": False,
        "source": None,
        "email": None,
    }


def test_store_normalises_and_is_owner_readable_only(tmp_path):
    path = prefs.save_freesurfer_license(
        "  someone@example.org\r\n12345\r\n *k\r\n FSk\r\n\r\n"
    )
    assert path == tmp_path / prefs.FS_LICENSE_FILENAME
    assert path.read_text() == "someone@example.org\n12345\n *k\n FSk\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert resolve_fs_license_path() == path
    assert prefs.freesurfer_license_status() == {
        "configured": True,
        "source": "app",
        "email": "someone@example.org",
    }
    prefs.clear_freesurfer_license()
    assert resolve_fs_license_path() is None


@pytest.mark.parametrize(
    "text",
    ["", "   \n", "12345\nkey", "not an email\n12345", "x" * 5000, "a@b.c\n\x00"],
)
def test_text_that_is_not_a_license_is_refused(text, tmp_path):
    with pytest.raises(ValueError):
        prefs.save_freesurfer_license(text)
    assert not (tmp_path / prefs.FS_LICENSE_FILENAME).exists()


def test_environment_license_wins_and_empty_placeholder_does_not_count(
    tmp_path, monkeypatch
):
    placeholder = tmp_path / "image-placeholder-license.txt"
    placeholder.touch()  # the Apptainer image ships an empty file at FS_LICENSE_PATH
    assert resolve_fs_license_path() is None
    prefs.save_freesurfer_license(LICENSE)
    env_license = tmp_path / "env.txt"
    env_license.write_text(LICENSE)
    monkeypatch.setenv("FS_LICENSE", str(env_license))
    assert resolve_fs_license_path() == env_license
    assert prefs.freesurfer_license_status()["source"] == "environment"


def test_fastsurfer_seg_only_never_needs_a_license(tmp_path):
    anat = tmp_path / "sub-001" / "anat"
    anat.mkdir(parents=True)
    (anat / "sub-001_T1w.nii.gz").touch()
    assert missing_freesurfer_license([STEP_FASTSURFER], ["001"]) == []
    assert (
        find_missing_preprocessing_inputs(
            str(tmp_path), ["001"], run_fastsurfer=True, create_m2m=True
        )
        == []
    )


def test_preflight_names_exactly_the_licensed_stages(tmp_path):
    anat = tmp_path / "sub-001" / "anat"
    anat.mkdir(parents=True)
    (anat / "sub-001_T1w.nii.gz").touch()
    problems = find_missing_preprocessing_inputs(
        str(tmp_path),
        ["001"],
        run_fastsurfer=True,
        run_freesurfer=True,
        freesurfer_recon_all=True,
        freesurfer_subregions=["thalamus", "hippo-amygdala"],
    )
    assert len(problems) == 1
    problem = problems[0]
    assert problem.step == STEP_FREESURFER
    assert problem.label == "FreeSurfer license"
    assert problem.path == tmp_path / prefs.FS_LICENSE_FILENAME
    assert (
        "FreeSurfer recon-all, FreeSurfer thalamic nuclei, "
        "FreeSurfer hippocampus/amygdala run FreeSurfer" in problem.message
    )
    assert prefs.FS_REGISTRATION_URL in problem.message
    assert "FastSurfer segmentation needs no license" in problem.message
    assert "Settings -> Pre-processing" in problem.message

    only_thalamus = missing_freesurfer_license([STEP_FREESURFER_THALAMUS], ["001"])
    assert only_thalamus[0].step == STEP_FREESURFER_THALAMUS
    assert only_thalamus[0].message.startswith(
        "FreeSurfer thalamic nuclei run FreeSurfer"
    )
    assert missing_freesurfer_license([STEP_FREESURFER_HIPPO, STEP_FASTSURFER])[
        0
    ].message.startswith("FreeSurfer hippocampus/amygdala run FreeSurfer")

    prefs.save_freesurfer_license(LICENSE)
    assert missing_freesurfer_license([STEP_FREESURFER], ["001"]) == []


def test_http_license_store_and_forget_never_return_the_key():
    from tit.server.routes.surfer_settings import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    before = client.get("/api/surfer-settings").json()["freesurfer_license"]
    assert before == {"configured": False, "source": None, "email": None}

    refused = client.put(
        "/api/surfer-settings/freesurfer-license", json={"text": "not a license"}
    )
    assert refused.status_code == 422
    assert "email" in refused.json()["detail"]

    stored = client.put(
        "/api/surfer-settings/freesurfer-license", json={"text": LICENSE}
    )
    assert stored.status_code == 200
    body = stored.json()
    assert body["freesurfer_license"] == {
        "configured": True,
        "source": "app",
        "email": "someone@example.org",
    }
    assert "FSabc123DEF456" not in stored.text

    forgotten = client.delete("/api/surfer-settings/freesurfer-license")
    assert forgotten.status_code == 200
    assert forgotten.json()["freesurfer_license"]["configured"] is False
