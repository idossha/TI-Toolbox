"""Submission refuses a config key ``/api/validate`` calls unknown.

What this pins
--------------
1. ``POST /api/jobs`` and ``POST /api/jobs/groups`` (a template and a ``subject_configs``
   entry) answer 422 naming a misspelled config key, for every kind with a config class. Before, ``/api/validate`` was strict and submission was not: a
   ``conductivty: "vn"`` typo was accepted with 201 and the runner silently ran the default
   (the "Space switch had no effect" class of bug). The oracle is ``POST /api/validate/<kind>``
   on the same config: submission must refuse what it reports as an unknown key.
2. What the server and the runner own is still accepted: ``project_dir`` and ``_type`` in the
   config, ``montage_sources`` beside it in the body, the stats runner's ``mode``.
3. ``pre``: a config whose subjects ride in the body (no ``subject_ids`` in it) still has its
   misspelling named -- only the strict parse in ``check_job_config`` can see it there. The
   keys from before the FastSurfer stage (``run_recon``, ...) are the one deliberate difference
   from ``/api/validate``: the runner and ``POST /api/plan/pre`` translate them, so submission
   accepts them, with or without ``subject_ids`` in the config, and a group plans the stage
   ``run_recon`` asks for (G2b), as the plan route shows for the same body.

Configs: one accepted desktop-corpus case per kind (``tests/fixtures/desktop_configs``, written
by the real desktop builders and accepted by every server validator), plus a hand-written
leadfield config (no page builds one).

Reproduce: ``.venv/bin/python -m pytest tests/test_submit_strict.py -q``.
Deliberately elsewhere: strict deserialisation itself (``tests/test_config_io.py``), the
envelope keys of ``/api/validate`` (``tests/test_validate_envelope_keys.py``).
Written 2026-10-22 (package p41).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

# stats/nifti_average/nilearn import scipy.ndimage/scipy.stats (test_plan_routes.py's fallback).
for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.config_check import check_job_config  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes.validate import ALL_KINDS, refuse_unknown_keys  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-strict"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
CORPUS = Path(__file__).parent / "fixtures" / "desktop_configs"
PLACEHOLDER = "/corpus/project"
TYPO = "conductivty"  # the repro's misspelling; a field of no config class


def _corpus_configs(project: Path) -> dict[str, tuple[dict, list[str]]]:
    """kind -> (config, subject_ids) of the first case the desktop and server both accept."""
    found: dict[str, tuple[dict, list[str]]] = {}
    gap_ids = {
        case_id
        for gap in (CORPUS / "known_gaps").glob("*.json")
        for case_id in json.loads(gap.read_text())["case_ids"]
    }
    for path in sorted(CORPUS.glob("*/*.json")):
        if path.parent.name == "known_gaps":
            continue
        case = json.loads(path.read_text().replace(PLACEHOLDER, str(project)))
        if not case["desktop"]["accepts"] or case["id"] in gap_ids:
            continue
        for job in case["jobs"]:
            found.setdefault(job["kind"], (job["config"], job["subject_ids"]))
    found.setdefault(
        "leadfield",
        ({"subject_id": "001", "eeg_net": "GSN-HydroCel-185.csv"}, ["001"]),
    )
    return found


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}")
    return root


@pytest.fixture()
def manager(project: Path, monkeypatch):
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: project / "preferences.json"
    )
    get_path_manager(str(project))
    fake = str(Path(__file__).parent / "fake_runner.py")
    jobs = JobManager(
        str(project),
        runner_cwd=str(project),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, spec: [sys.executable, fake, spec],
    )
    jobs.start()
    bootstrap.set_manager_for_testing(jobs)
    yield jobs
    jobs.shutdown()
    bootstrap.reset_manager()


@pytest.fixture()
def client(project: Path, manager) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def test_every_kind_with_a_config_class_has_a_case(project: Path) -> None:
    assert set(_corpus_configs(project)) == set(ALL_KINDS)


@pytest.mark.parametrize("kind", sorted(ALL_KINDS))
def test_a_misspelled_key_is_refused_at_submit_as_validate_reports_it(
    kind: str, client: TestClient, project: Path
) -> None:
    config, subject_ids = _corpus_configs(project)[kind]
    # The clean config passes both submit-time config checks...
    check_job_config(kind, config)
    refuse_unknown_keys(kind, config)
    typo = {**config, TYPO: "vn"}
    # ...and the oracle: /api/validate reports the misspelling.
    validate = client.post(
        f"/api/validate/{kind}", json={"config": typo}, headers=BEARER
    ).json()
    assert validate["ok"] is False and TYPO in validate["errors"][0]["message"]

    r = client.post(
        "/api/jobs",
        json={"kind": kind, "config": typo, "subject_ids": subject_ids},
        headers=BEARER,
    )
    assert r.status_code == 422, r.text
    assert TYPO in r.json()["detail"]
    assert client.get("/api/jobs", headers=BEARER).json() == []


def test_a_misspelled_key_nested_in_a_montage_is_refused(
    client: TestClient, project: Path
) -> None:
    config, subject_ids = _corpus_configs(project)["sim"]
    montage = {**config["montages"][0], "electrode_pair": [["E1", "E2"]]}
    r = client.post(
        "/api/jobs",
        json={
            "kind": "sim",
            "config": {**config, "montages": [montage]},
            "subject_ids": subject_ids,
        },
        headers=BEARER,
    )
    assert r.status_code == 422, r.text
    assert "electrode_pair" in r.json()["detail"]


@pytest.mark.parametrize("kind", ["sim", "flex", "ex", "pre"])
def test_a_group_template_with_a_misspelled_key_is_refused(
    kind: str, client: TestClient, project: Path
) -> None:
    config, subject_ids = _corpus_configs(project)[kind]
    r = client.post(
        "/api/jobs/groups",
        json={"kind": kind, "config": {**config, TYPO: 1}, "subject_ids": subject_ids},
        headers=BEARER,
    )
    assert r.status_code == 422, r.text
    assert TYPO in r.json()["detail"]
    assert client.get("/api/jobs", headers=BEARER).json() == []


def test_a_group_subject_config_with_a_misspelled_key_is_refused(
    client: TestClient, project: Path
) -> None:
    config, _ = _corpus_configs(project)["sim"]
    r = client.post(
        "/api/jobs/groups",
        json={
            "kind": "sim",
            "config": config,
            "subject_ids": ["001", "002"],
            "subject_configs": [
                {"subject_id": "002", "config": {**config, TYPO: "vn"}}
            ],
        },
        headers=BEARER,
    )
    assert r.status_code == 422, r.text
    assert TYPO in r.json()["detail"]


def test_envelope_and_dispatch_keys_are_not_unknown(project: Path) -> None:
    configs = _corpus_configs(project)
    sim, _ = configs["sim"]
    refuse_unknown_keys("sim", {**sim, "project_dir": str(project)})
    check_job_config("sim", {**sim, "project_dir": str(project)})
    stats, _ = configs["stats"]
    assert stats["_type"] in ("GroupComparisonConfig", "CorrelationConfig")
    mode = (
        "correlation" if stats["_type"] == "CorrelationConfig" else "group_comparison"
    )
    refuse_unknown_keys("stats", {**stats, "mode": mode})


def _seed_sim_inputs(project: Path, sid: str) -> None:
    pm = get_path_manager(str(project))
    m2m = Path(pm.m2m(sid))
    m2m.mkdir(parents=True, exist_ok=True)
    (m2m / f"{sid}.msh").write_bytes(b"")
    eeg = Path(pm.eeg_positions(sid))
    eeg.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        f"Electrode,{10 * i},0,0,{name}\n"
        for i, name in enumerate(["E1", "E2", "E3", "E4"])
    )
    (eeg / "GSN-HydroCel-185.csv").write_text(rows)


SIM_CONFIG = {
    "subject_id": "001",
    "montages": [
        {
            "_type": "Montage",
            "name": "m1",
            "mode": "net",
            "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
            "eeg_net": "GSN-HydroCel-185.csv",
        }
    ],
}


def test_montage_sources_beside_the_config_is_still_accepted(
    client: TestClient, project: Path
) -> None:
    _seed_sim_inputs(project, "001")
    r = client.post(
        "/api/jobs",
        json={
            "kind": "sim",
            "config": {**SIM_CONFIG, "project_dir": str(project)},
            "subject_ids": ["001"],
            "montage_sources": {"flex": []},
        },
        headers=BEARER,
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------------------------
# pre: the subjects ride in the body, and keys from before the FastSurfer stage are translated
# ---------------------------------------------------------------------------------------------


def _pre_without_subjects(project: Path) -> dict:
    config, _ = _corpus_configs(project)["pre"]
    return {k: v for k, v in config.items() if k != "subject_ids"}


@pytest.mark.parametrize("route", ["/api/jobs", "/api/jobs/groups"])
def test_a_pre_config_without_its_subjects_still_refuses_a_misspelled_key(
    route: str, client: TestClient, project: Path
) -> None:
    """``POST /api/jobs`` takes a pre job's subjects from the body, so its config may carry no
    ``subject_ids``. ``PreprocessConfig`` refuses an empty subject list, so the lenient parse
    ``refuse_unknown_keys`` starts from fails and it has nothing to say: the strict parse in
    ``check_job_config`` (with the subjects filled in, as the manager writes config.json) is
    what must name the misspelling."""
    r = client.post(
        route,
        json={
            "kind": "pre",
            "config": {**_pre_without_subjects(project), TYPO: 1},
            "subject_ids": ["001"],
        },
        headers=BEARER,
    )
    assert r.status_code == 422, r.text
    assert TYPO in r.json()["detail"]
    assert client.get("/api/jobs", headers=BEARER).json() == []


#: A config JSON from before the FastSurfer stage: the four keys of
#: ``tit.pre.config.LEGACY_KEYS``. ``run_recon`` means ``run_fastsurfer``
#: (``tests/test_pre_config_migration.py``), the others are dropped.
LEGACY_PRE = {
    "convert_dicom": True,  # supplies the T1w, so preflight has nothing missing
    "create_m2m": True,
    "run_recon": True,
    "parallel_recon": True,
    "parallel_cores": 4,
    "run_subcortical_segmentations": False,
}


def test_a_legacy_pre_config_is_translated_not_refused_at_submit(
    client: TestClient, project: Path
) -> None:
    """The pre runner and ``POST /api/plan/pre`` translate these keys
    (``migrate_legacy_keys``), so submission accepts them too; only a key nobody translates
    is unknown."""
    r = client.post(
        "/api/jobs",
        json={"kind": "pre", "config": LEGACY_PRE, "subject_ids": ["001"]},
        headers=BEARER,
    )
    assert r.status_code == 201, r.text
    refused = client.post(
        "/api/jobs",
        json={
            "kind": "pre",
            "config": {**LEGACY_PRE, TYPO: 1},
            "subject_ids": ["001"],
        },
        headers=BEARER,
    )
    assert refused.status_code == 422 and TYPO in refused.json()["detail"]


def _stage_tags(tags) -> set[str]:
    return {t for t in tags if t.startswith("G")}


def test_a_legacy_pre_group_queues_the_stages_the_plan_shows(
    client: TestClient, project: Path, manager: JobManager
) -> None:
    """A group carries ``subject_ids`` in the config, as the Preprocess page sends it. Such a
    legacy config was refused as ``unknown key run_recon`` while the same body without
    ``subject_ids`` passed ``POST /api/jobs``; and once accepted, it must run what it asked
    for: ``run_recon`` is the FastSurfer stage (G2b), which the group used to drop. The oracle
    is ``POST /api/plan/pre`` for the same body. (A proposal step validates through
    ``/api/validate`` first, which still names these keys as outdated.)"""
    body = {
        "kind": "pre",
        "config": {**LEGACY_PRE, "subject_ids": ["001"]},
        "subject_ids": ["001"],
    }
    plan = client.post(
        "/api/plan/pre",
        json={"config": body["config"], "subject_ids": ["001"]},
        headers=BEARER,
    )
    assert plan.status_code == 200, plan.text
    planned = {
        stage["label"].split(":")[1] for stage in plan.json()["resolved"]["stages"]
    }
    assert "G2b" in planned

    r = client.post("/api/jobs/groups", json=body, headers=BEARER)
    assert r.status_code == 201, r.text
    queued = manager.list_jobs()
    assert {
        tag for job in queued for tag in _stage_tags(manager._specs[job["id"]].tags)
    } == planned
