"""A job group whose jobs would write ONE output folder is refused before any job exists.

Pins (2026-10-22, package p19):

- sim:batch-duplicate-output-dir -- the Simulator's "Duplicate job" copies the montage name, so
  two rows (ernie, M) with different currents went into one ``POST /api/jobs/groups``. The
  scheduler runs a group's jobs one after another (lock ``subject:<sid>:sim:<name>``), nothing
  existed at submit, and the second silently replaced the first's ``Simulations/M``.
- ex:multi-target-run-name -- an uncombined two-ROI Ex row sent both targets with ``run_name``
  "r", so both wrote ``ex-search/r`` and only the last target's results survived.

The rule: one output folder belongs to one job of a group (the analyzer precedent, 329b658b).
A folder that is only a *preview* is not compared: an Ex/mEx config with no ``run_name`` plans
``time.strftime(...)`` and picks a fresh timestamp when it actually runs.

Where the expected folders come from: the derivatives layout ``tit/paths.py`` documents
(``derivatives/SimNIBS/sub-<id>/Simulations/<montage>``, ``.../ex-search/<run>``), written out
here as literal path components, not computed by the code under test. The Ex configs are the
desktop's own corpus case ``tests/fixtures/desktop_configs/optimizer-ex/bucketed-saved-separate.json``
(what the Optimizer builds for an uncombined L_Insula + R_Insula row), with the leadfield path
pointed at a seeded file. Reproduce: ``pytest tests/test_jobs_group_output_collision.py -q``.
Deliberately elsewhere: the desktop's own block on the same collision
(``desktop/tests/unit/run-output-collision.test.ts``).
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-collision"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
FAKE_RUNNER = os.path.join(os.path.dirname(__file__), "fake_runner.py")
EX_CASE = (
    Path(__file__).parent
    / "fixtures"
    / "desktop_configs"
    / "optimizer-ex"
    / "bucketed-saved-separate.json"
)
NET = "GSN-HydroCel-185"
ELECTRODES = [f"E{n:03d}" for n in range(1, 40)]


def _seed_subject(project: Path, sid: str) -> None:
    """What preflight requires of a sim and an ex job: head mesh, net CSV, leadfield, ROIs."""
    pm = get_path_manager(str(project))
    m2m = Path(pm.m2m(sid))
    m2m.mkdir(parents=True, exist_ok=True)
    (m2m / f"{sid}.msh").write_bytes(b"")
    eeg = Path(pm.eeg_positions(sid))
    eeg.mkdir(parents=True, exist_ok=True)
    # 10 mm apart: closer than 2 mm is a collapsed net, which preflight refuses.
    (eeg / f"{NET}.csv").write_text(
        "".join(f"Electrode,{10 * i},0,0,{name}\n" for i, name in enumerate(ELECTRODES))
    )
    leadfields = Path(pm.leadfields(sid))
    leadfields.mkdir(parents=True, exist_ok=True)
    (leadfields / f"{NET}_leadfield.hdf5").write_bytes(b"")
    rois = Path(pm.rois(sid))
    rois.mkdir(parents=True, exist_ok=True)
    for name in ("L_Insula", "R_Insula"):
        (rois / f"{name}.csv").write_text("-38,-4,6\n")


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    for sid in ("ernie", "101"):
        _seed_subject(tmp_path, sid)
    return tmp_path


@pytest.fixture()
def client(project: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: project / "preferences.json"
    )
    get_path_manager(str(project))
    manager = JobManager(
        str(project),
        runner_cwd=str(project),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, spec_path: [
            sys.executable,
            FAKE_RUNNER,
            spec_path,
        ],
    )
    manager.start()
    bootstrap.set_manager_for_testing(manager)
    yield TestClient(
        create_app(ServerSettings(project_dir=str(project), token=TOKEN)),
        base_url="http://127.0.0.1:8765",
    )
    bootstrap.reset_manager()


def _sim(sid: str, montage: str, intensities: list[float]) -> dict:
    return {
        "subject_id": sid,
        "intensities": intensities,
        "montages": [
            {
                "_type": "Montage",
                "name": montage,
                "mode": "net",
                "electrode_pairs": [["E001", "E002"], ["E003", "E004"]],
                "eeg_net": f"{NET}.csv",
            }
        ],
    }


def _ex_configs(project: Path, sid: str, run_names: list[str | None]) -> list[dict]:
    """The Optimizer's two Ex jobs for an uncombined L_Insula + R_Insula row, per the corpus."""
    case = json.loads(EX_CASE.read_text())
    configs = []
    for job, run_name in zip(case["jobs"], run_names, strict=True):
        config = copy.deepcopy(job["config"])
        config["subject_id"] = sid
        config["leadfield_hdf"] = str(
            project
            / "derivatives"
            / "SimNIBS"
            / f"sub-{sid}"
            / "leadfields"
            / f"{NET}_leadfield.hdf5"
        )
        config["run_name"] = run_name
        configs.append(config)
    assert [c["roi_name"] for c in configs] == ["L_Insula", "R_Insula"]
    return configs


def _group(client: TestClient, kind: str, entries: list[tuple[str, dict]], **extra):
    subject_ids = list(dict.fromkeys(sid for sid, _ in entries))
    return client.post(
        "/api/jobs/groups",
        headers=BEARER,
        json={
            "kind": kind,
            "config": entries[0][1],
            "subject_ids": subject_ids,
            "subject_configs": [
                {"subject_id": sid, "config": config} for sid, config in entries
            ],
            **extra,
        },
    )


def _job_count(client: TestClient) -> int:
    return len(client.get("/api/jobs", headers=BEARER).json())


def test_two_sim_jobs_for_one_subject_and_montage_are_refused(client, project):
    """The Duplicate-job repro: same (ernie, M), different currents, one group."""
    response = _group(
        client,
        "sim",
        [
            ("ernie", _sim("ernie", "M", [1.0, 1.0])),
            ("ernie", _sim("ernie", "M", [2.0, 2.0])),
        ],
    )
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    folder = project / "derivatives" / "SimNIBS" / "sub-ernie" / "Simulations" / "M"
    assert str(folder) in detail
    assert "2 jobs" in detail
    assert _job_count(client) == 0


def test_overwrite_confirmation_does_not_license_two_jobs_into_one_folder(client):
    """`overwrite` confirms replacing what is ON DISK; it says nothing about two jobs of one press."""
    response = _group(
        client,
        "sim",
        [
            ("ernie", _sim("ernie", "M", [1.0, 1.0])),
            ("ernie", _sim("ernie", "M", [2.0, 2.0])),
        ],
        overwrite=True,
    )
    assert response.status_code == 422, response.text
    assert _job_count(client) == 0


def test_one_montage_name_for_two_subjects_is_two_folders(client):
    response = _group(
        client,
        "sim",
        [
            ("ernie", _sim("ernie", "M", [1.0, 1.0])),
            ("101", _sim("101", "M", [1.0, 1.0])),
        ],
    )
    assert response.status_code == 201, response.text
    assert [job["subject_ids"] for job in response.json()["jobs"]] == [
        ["ernie"],
        ["101"],
    ]


def test_two_montages_of_one_subject_are_two_folders(client):
    response = _group(
        client,
        "sim",
        [
            ("ernie", _sim("ernie", "M", [1.0, 1.0])),
            ("ernie", _sim("ernie", "N", [1.0, 1.0])),
        ],
    )
    assert response.status_code == 201, response.text
    assert len(response.json()["jobs"]) == 2


def test_two_ex_targets_sharing_a_run_name_are_refused(client, project):
    """What the Optimizer sent for an uncombined two-ROI row named "r" before p19."""
    configs = _ex_configs(project, "ernie", ["r", "r"])
    response = _group(client, "ex", [("ernie", c) for c in configs])
    assert response.status_code == 422, response.text
    folder = project / "derivatives" / "SimNIBS" / "sub-ernie" / "ex-search" / "r"
    assert str(folder) in response.json()["detail"]
    assert _job_count(client) == 0


def test_ex_targets_with_their_own_run_names_are_accepted(client, project):
    configs = _ex_configs(project, "ernie", ["r_L_Insula", "r_R_Insula"])
    response = _group(client, "ex", [("ernie", c) for c in configs])
    assert response.status_code == 201, response.text
    assert len(response.json()["jobs"]) == 2


def test_blank_ex_run_names_are_timestamp_previews_and_not_compared(client, project):
    """Both plans preview the same `time.strftime` folder; each run picks its own when it starts."""
    configs = _ex_configs(project, "ernie", [None, None])
    response = _group(client, "ex", [("ernie", c) for c in configs])
    assert response.status_code == 201, response.text
    assert len(response.json()["jobs"]) == 2


def test_a_shared_folder_already_on_disk_is_refused_as_shared_not_asked_about(
    client, project
):
    """The 422 comes before the 409 question: no answer to "replace what is on disk?" makes two
    jobs into one folder safe, so the user must not be offered that answer."""
    folder = project / "derivatives" / "SimNIBS" / "sub-ernie" / "Simulations" / "M"
    folder.mkdir(parents=True)
    (folder / "TI.msh").write_bytes(b"x")
    # One job into the existing folder is the overwrite question (409), so the folder is live.
    single = _group(client, "sim", [("ernie", _sim("ernie", "M", [1.0, 1.0]))])
    assert single.status_code == 409, single.text

    response = _group(
        client,
        "sim",
        [
            ("ernie", _sim("ernie", "M", [1.0, 1.0])),
            ("ernie", _sim("ernie", "M", [2.0, 2.0])),
        ],
    )
    assert response.status_code == 422, response.text
    assert str(folder) in response.json()["detail"]
    assert _job_count(client) == 0


def _flex(sid: str, output_folder: str | None) -> dict:
    """A flex search the server accepts for a seeded subject (subject-space sphere target)."""
    return {
        "subject_id": sid,
        "goal": "mean",
        "postproc": "max_TI",
        "current_mA": 1.0,
        "electrode": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4},
        "roi": {
            "_type": "SphericalROI",
            "x": [-30.0],
            "y": [10.0],
            "z": [5.0],
            "radius": [10.0],
            "use_mni": False,
            "volumetric": False,
            "tissues": "GM",
        },
        "skin_region_margin_mm": 0,
        "output_folder": output_folder,
    }


def test_flex_searches_without_a_folder_are_timestamp_previews_and_not_compared(
    client, monkeypatch
):
    """Both plans preview the same timestamp folder (here pinned, as within one second); each
    run picks its own when it starts, so two agreeing previews prove nothing."""
    monkeypatch.setattr(
        "tit.opt.flex.utils.generate_run_dirname", lambda base: "20261022_000000"
    )
    response = _group(
        client,
        "flex",
        [("ernie", _flex("ernie", None)), ("ernie", _flex("ernie", None))],
    )
    assert response.status_code == 201, response.text
    assert len(response.json()["jobs"]) == 2


def test_two_flex_searches_into_one_named_folder_are_refused(client, project):
    folder = project / "derivatives" / "SimNIBS" / "sub-ernie" / "flex-search" / "run_a"
    response = _group(
        client,
        "flex",
        [
            ("ernie", _flex("ernie", str(folder))),
            ("ernie", _flex("ernie", str(folder))),
        ],
    )
    assert response.status_code == 422, response.text
    assert str(folder) in response.json()["detail"]
    assert _job_count(client) == 0


def test_an_approved_proposal_step_with_two_jobs_into_one_folder_queues_nothing(
    client, project
):
    """The proposal engine queues an approved step through the same group check: a step that
    names one subject twice is two identical simulations into one folder."""
    montage = _sim("ernie", "M", [1.0, 1.0])["montages"][0]
    created = client.post(
        "/api/proposals",
        headers=BEARER,
        json={
            "title": "Simulate M twice",
            "steps": [
                {
                    "id": "sim",
                    "kind": "sim",
                    "config": {"montages": [montage], "intensities": [1.0, 1.0]},
                    "subject_ids": ["ernie", "ernie"],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    approved = client.post(
        f"/api/proposals/{created.json()['id']}/approve", headers=BEARER
    )
    assert approved.status_code == 200, approved.text
    [step] = approved.json()["steps"]
    folder = project / "derivatives" / "SimNIBS" / "sub-ernie" / "Simulations" / "M"
    assert step["state"] == "error"
    assert "would write the same folder" in step["error"]
    assert str(folder) in step["error"]
    assert step["job_ids"] == []
    assert _job_count(client) == 0
