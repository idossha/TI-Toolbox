"""Automatic toolbox licensing and optional administrator overrides.

Run: .venv/bin/python -m pytest tests/test_freesurfer_license.py -q
Synthetic override text is authored; real bundled contents are never printed.
"""

from pathlib import Path
import hashlib

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
    monkeypatch.setattr(
        prefs, "BUNDLED_FS_LICENSE_PATH", tmp_path / "missing-bundle.txt"
    )
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
    assert problem.path == prefs.BUNDLED_FS_LICENSE_PATH
    assert "FreeSurfer recon-all, FreeSurfer thalamic nuclei" in problem.message
    assert "Repair or update" in problem.message
    assert "no personal license is required" in problem.message
    assert "Register" not in problem.message
    assert "Settings" not in problem.message
    only_thalamus = missing_freesurfer_license([STEP_FREESURFER_THALAMUS], ["001"])
    assert only_thalamus[0].step == STEP_FREESURFER_THALAMUS
    assert "FreeSurfer thalamic nuclei cannot find" in only_thalamus[0].message

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


def test_fresh_install_uses_the_v2_toolbox_license_without_user_setup(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    bundled = root / "tit/resources/freesurfer/license.txt"
    monkeypatch.setattr(prefs, "BUNDLED_FS_LICENSE_PATH", bundled)
    assert (
        hashlib.sha256(bundled.read_bytes()).hexdigest()
        == hashlib.sha256(
            (root / "container/blueprint/license.txt").read_bytes()
        ).hexdigest()
    )
    assert bundled.stat().st_size > 0
    assert resolve_fs_license_path() == bundled
    assert prefs.freesurfer_license_status() == {
        "configured": True,
        "source": "bundled",
        "email": None,
    }
    assert missing_freesurfer_license([STEP_FREESURFER, STEP_FREESURFER_HIPPO]) == []
    prefs.save_freesurfer_license(LICENSE)
    assert resolve_fs_license_path() == prefs.freesurfer_license_path()
    prefs.clear_freesurfer_license()
    assert resolve_fs_license_path() == bundled


def test_qsi_stages_bundled_license_for_both_sibling_containers(tmp_path, monkeypatch):
    from tit.pre.qsi.docker_builder import DockerCommandBuilder
    from tit.pre.qsi.config import QSIPrepConfig, QSIReconConfig

    bundled = (
        Path(__file__).resolve().parents[1] / "tit/resources/freesurfer/license.txt"
    )
    monkeypatch.setattr(prefs, "BUNDLED_FS_LICENSE_PATH", bundled)
    monkeypatch.setenv("LOCAL_PROJECT_DIR", "/host/project")
    monkeypatch.setattr(
        "tit.pre.qsi.docker_builder.get_inherited_dood_resources", lambda: (2, 4)
    )
    builder = DockerCommandBuilder(str(tmp_path))
    staged = tmp_path / ".freesurfer_license.txt"
    assert (
        hashlib.sha256(staged.read_bytes()).digest()
        == hashlib.sha256(bundled.read_bytes()).digest()
    )
    commands = [
        builder.build_qsiprep_cmd(QSIPrepConfig(subject_id="001")),
        builder.build_qsirecon_cmd(QSIReconConfig(subject_id="001"), "dipy_dki"),
    ]
    for command in commands:
        assert (
            "/host/project/.freesurfer_license.txt:/opt/freesurfer/license.txt:ro"
            in command
        )
        assert "FS_LICENSE=/opt/freesurfer/license.txt" in command
        assert (
            command[command.index("--fs-license-file") + 1]
            == "/opt/freesurfer/license.txt"
        )
