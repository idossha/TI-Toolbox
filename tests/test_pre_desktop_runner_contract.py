"""The Pre-processing page's submission reaches the runner as the user chose it, and an agent's
reaches it the same way (2026-10-22, package p27).

Inputs: ``contracts/fixtures/pre/*.json``, written by the page's real ``toSubmitConfig``
(``desktop/tests/unit/preprocess-submit-golden.test.ts``). Each file holds the user's saved
preferences (the ``PUT /api/surfer-settings`` body), the settings the page received, the steps
ticked, the subjects, the existing-output policy and the config the page sends.

Per fixture, offline (the job manager is never started; ``run_pipeline`` is a recorder):

1. ``PUT /api/surfer-settings`` with the preferences returns exactly the settings the page used.
2. ``POST /api/jobs/groups`` with the page's config is accepted; every stage's ``config.json``
   (``JobManager._runner_config_path``, the file the runner reads) has exactly its own step flag
   on, that one subject, the page's charm options and QSIPrep/QSIRecon processing values, thread
   counts within the CPU capacity, and nothing ``deserialize_config(strict=True)`` would drop.
3. ``python -m tit.pre config.json`` (``main``) hands ``run_pipeline`` those values.
4. An agent sending only ``{subject_ids, run_qsiprep, run_qsirecon, run_freesurfer}`` with the same
   saved preferences gets the same QSIPrep/QSIRecon settings and FreeSurfer operations as the page
   (``tit/server/app_defaults.py``: "an agent sends only the fields it chose and still runs what
   the app would").

Expected stage tags and flags are the G1-G6 table of ``tit.jobs.plans.plan_preprocessing``'s
docstring; expected values are the fixture's (the user's choices as the page sent them).
Reproduce: ``.venv/bin/python -m pytest tests/test_pre_desktop_runner_contract.py -q``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.config_io import deserialize_config  # noqa: E402
from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.pre.config import PreprocessConfig  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

FIXTURES = sorted(
    (Path(__file__).resolve().parents[1] / "contracts" / "fixtures" / "pre").glob(
        "*.json"
    )
)
AUTH = {"Authorization": "Bearer t"}
#: plan_preprocessing's stage table: tag -> the one step flag that stage runs.
STAGE_FLAG = {
    "G1": "convert_dicom",
    "G2a": "create_m2m",
    "G2b": "run_fastsurfer",
    "G2c": "run_freesurfer",
    "G3": "run_tissue_analysis",
    "G4": "run_qsiprep",
    "G5": "run_qsirecon",
    "G6": "extract_dti",
}
RESOURCES = ("cpus", "memory_gb", "omp_threads")


def _processing(settings: dict | None) -> dict | None:
    return (
        None
        if settings is None
        else {k: v for k, v in settings.items() if k not in RESOURCES}
    )


def test_has_fixtures_to_check():
    assert [p.stem for p in FIXTURES] == [
        "defaults",
        "freesurfer-subregions",
        "qsi-preferences",
        "replace",
    ]


@pytest.fixture
def server(tmp_path, monkeypatch, write_dwi):
    """A project every fixture's steps have inputs in, and a server at a fixed CPU capacity."""
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: tmp_path / "surfer-settings.json"
    )
    monkeypatch.delenv("TIT_FASTSURFER_THREADS", raising=False)
    pm = get_path_manager(str(tmp_path))
    for sid in ("001", "002"):
        anat = Path(pm.bids_anat(sid))
        anat.mkdir(parents=True)
        (anat / f"sub-{sid}_T1w.nii.gz").write_bytes(b"t1")
        write_dwi(Path(pm.bids_dwi(sid)), stem=f"sub-{sid}_dwi")
        # A finished recon-all: what subregions without recon-all require.
        fs = Path(pm.freesurfer_subject(sid))
        for name in (
            "scripts/recon-all.done",
            "mri/norm.mgz",
            "mri/aseg.mgz",
            "mri/wmparc.mgz",
        ):
            (fs / name).parent.mkdir(parents=True, exist_ok=True)
            (fs / name).write_bytes(b"x")
    manager = JobManager(str(tmp_path), budget=Cost(cpus=8, mem_gb=64))
    bootstrap.set_manager_for_testing(manager)
    client = TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="t")),
        base_url="http://127.0.0.1:8765",
    )
    yield client, manager, tmp_path
    bootstrap.reset_manager()


def _save_preferences(client, fixture) -> dict:
    r = client.put("/api/surfer-settings", headers=AUTH, json=fixture["preferences"])
    assert r.status_code == 200, r.text
    return r.json()


def _submit(client, manager, config, subject_ids, **extra) -> dict[str, dict]:
    """Submit a pre group; ``{"<sid>:<tag>": config.json the runner reads}``."""
    r = client.post(
        "/api/jobs/groups",
        headers=AUTH,
        json={"kind": "pre", "config": config, "subject_ids": subject_ids, **extra},
    )
    assert r.status_code == 201, r.text
    stages = {}
    for job in r.json()["jobs"]:
        spec = manager._specs[job["id"]]
        (tag,) = [t for t in spec.tags if t in STAGE_FLAG]
        written = json.loads(Path(manager._runner_config_path(spec)).read_text())
        stages[f"{spec.subject_ids[0]}:{tag}"] = written
    return stages


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_the_settings_the_page_used_are_what_the_server_returns(server, path):
    fixture = json.loads(path.read_text())
    client, _, _ = server
    got = _save_preferences(client, fixture)
    got.pop("freesurfer_license")
    assert got == fixture["settings"]


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_every_stage_config_carries_the_users_choices(server, path):
    fixture = json.loads(path.read_text())
    client, manager, project = server
    _save_preferences(client, fixture)
    sent = fixture["config"]
    stages = _submit(client, manager, sent, fixture["subject_ids"])

    ticked = [tag for tag, flag in STAGE_FLAG.items() if fixture["flags"][flag]]
    assert sorted(stages) == sorted(
        f"{sid}:{tag}" for sid in fixture["subject_ids"] for tag in ticked
    )
    capacity = fixture["available_threads"]
    for key, written in stages.items():
        sid, tag = key.split(":")
        assert written["project_dir"] == str(project)
        assert written["subject_ids"] == [sid]
        assert [f for f in STAGE_FLAG.values() if written[f]] == [STAGE_FLAG[tag]]
        assert written["skip_existing_outputs"] is (fixture["policy"] == "skip")
        assert written["replace_existing_outputs"] is (fixture["policy"] == "replace")
        assert written["freesurfer_recon_all"] == sent["freesurfer_recon_all"]
        assert written["freesurfer_subregions"] == sent["freesurfer_subregions"]
        assert written["charm_options"] == sent["charm_options"]
        assert _processing(written["qsiprep_config"]) == _processing(
            sent["qsiprep_config"]
        )
        assert _processing(written["qsi_recon_config"]) == _processing(
            sent["qsi_recon_config"]
        )
        threads = [
            written[k]
            for k in ("charm_threads", "fastsurfer_threads", "freesurfer_threads")
        ] + [
            (written[c] or {}).get(r)
            for c in ("qsiprep_config", "qsi_recon_config")
            for r in ("cpus", "omp_threads")
        ]
        assert all(t is None or 1 <= t <= capacity for t in threads), (key, threads)
        # Nothing the runner would silently ignore.
        body = {k: v for k, v in written.items() if k != "project_dir"}
        deserialize_config(PreprocessConfig, body, strict=True)

        # The runner hands run_pipeline exactly these values.
        from tit.pre import __main__ as pre_main

        config_file = project / f"{sid}-{tag}.json"
        config_file.write_text(json.dumps(written))
        calls = []
        with (
            patch.object(pre_main, "run_pipeline", lambda **kw: calls.append(kw) or 0),
            patch("tit.logger.add_stream_handler"),
            patch.object(sys, "argv", ["tit.pre", str(config_file)]),
            pytest.raises(SystemExit) as stop,
        ):
            pre_main.main()
        assert stop.value.code == 0
        (kwargs,) = calls
        assert kwargs["subject_ids"] == [sid]
        for name, value in body.items():
            assert kwargs[name] == value, (key, name)


#: What the agent sends: the steps it chose, nothing else.
AGENT_CONFIG = {"run_qsiprep": True, "run_qsirecon": True, "run_freesurfer": True}


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_an_agent_with_the_same_saved_preferences_runs_what_the_page_would(
    server, path
):
    fixture = json.loads(path.read_text())
    client, manager, _ = server
    _save_preferences(client, fixture)
    r = client.put(
        "/api/settings",
        headers=AUTH,
        json={"panels": [], "theme": "system", "agent_auto_submit": True},
    )
    assert r.status_code == 200, r.text
    agent = _submit(
        client,
        manager,
        {"subject_ids": ["001"], **AGENT_CONFIG},
        ["001"],
        created_by="agent",
    )
    page = fixture["config"]
    assert agent["001:G2c"]["freesurfer_recon_all"] == page["freesurfer_recon_all"]
    assert agent["001:G2c"]["freesurfer_subregions"] == page["freesurfer_subregions"]
    if page["run_qsiprep"]:
        desktop = _submit(client, manager, page, ["001"])
        for tag, field in (("G4", "qsiprep_config"), ("G5", "qsi_recon_config")):
            assert agent[f"001:{tag}"][field] == desktop[f"001:{tag}"][field], field
    else:
        # The page fills QSI settings from the saved preferences whenever QSIPrep is ticked.
        for tag, field in (("G4", "qsiprep_config"), ("G5", "qsi_recon_config")):
            assert _processing(agent[f"001:{tag}"][field]) == fixture["settings"][field]


def test_an_agents_own_choice_wins_over_the_saved_preference(server):
    """Saved: patch2self, recon-all off. The agent asks for no denoising and recon-all."""
    fixture = json.loads(FIXTURES[2].read_text())  # qsi-preferences
    client, manager, _ = server
    _save_preferences(client, fixture)
    client.put(
        "/api/settings",
        headers=AUTH,
        json={"panels": [], "theme": "system", "agent_auto_submit": True},
    )
    agent = _submit(
        client,
        manager,
        {
            "subject_ids": ["001"],
            **AGENT_CONFIG,
            "qsiprep_config": {"denoise_method": "none"},
            "freesurfer_subregions": ["hippo-amygdala"],
        },
        ["001"],
        created_by="agent",
    )
    qsiprep = agent["001:G4"]["qsiprep_config"]
    assert qsiprep["denoise_method"] == "none"
    # The rest of the saved processing preferences still apply.
    assert qsiprep["unringing_method"] == "mrdegibbs"
    assert qsiprep["mni_normalization"] is True
    assert agent["001:G2c"]["freesurfer_subregions"] == ["hippo-amygdala"]
