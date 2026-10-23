"""``GET /api/jobs/{id}`` names the one folder a job's results live in (``output_dir``).

What this pins (2026-10-22)
    The desktop's folder buttons (the run pages' Terminal pane, the Jobs page) opened
    ``code/ti-toolbox/jobs/<id>/``, the job's own bookkeeping record, whenever the job had
    registered no artifact yet, which is the whole time a simulation or a search runs; and a
    finished simulation or flex-search, whose first artifact is the run folder itself, opened that
    folder's parent. The server now answers with the folder: the ``dir`` artifact the runner
    registered, else the folder the plan route names for the job's own spec, else the directory
    of its first registered file.

Where the expectations come from
    The folders are ``PathManager``'s (``simulation``, ``flex_search_run``, ``ex_search_run``,
    ``m2m``), the runners' own artifact events (``tit/sim/__main__.py`` registers
    ``Simulations/<montage>`` as a ``dir`` first, ``tit/opt/ex/__main__.py`` registers
    ``final_output.csv`` and ``run_config.json`` inside the run folder), and, for an analysis, the
    answer ``POST /api/plan/analyzer`` gives for the same config (the resolver the Analyzer page
    uses). Nothing is typed as a path string.

Run: .venv/bin/python -m pytest tests/test_job_output_dir.py -q -p no:cacheprovider
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.config_io import serialize_config  # noqa: E402
from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.opt.config import FlexConfig  # noqa: E402
from tit.paths import get_path_manager, reset_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-output-dir"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
SUBJECT = "ernie"


@pytest.fixture()
def project(tmp_path: Path):
    reset_path_manager()
    (tmp_path / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(tmp_path))
    yield pm
    bootstrap.reset_manager()
    reset_path_manager()


@pytest.fixture()
def manager(project) -> JobManager:
    """A manager that is never started: a submitted job stays queued, like a job that has not
    reported anything yet."""
    manager = JobManager(
        project.project_dir,
        runner_cwd=project.project_dir,
        budget=Cost(cpus=8, mem_gb=64),
    )
    bootstrap.set_manager_for_testing(manager)
    return manager


@pytest.fixture()
def client(project, manager) -> TestClient:
    settings = ServerSettings(project_dir=project.project_dir, token=TOKEN)
    return TestClient(create_app(settings), base_url=BASE)


def _register(manager: JobManager, job_id: str, *artifacts: dict) -> None:
    """The runner's artifact events, applied as the manager applies them while polling."""
    with manager._lock:
        manager._apply_events(
            job_id,
            manager._status[job_id],
            [{"type": "artifact", **artifact} for artifact in artifacts],
        )


def _output_dir(client: TestClient, job_id: str) -> str | None:
    response = client.get(f"/api/jobs/{job_id}", headers=BEARER)
    assert response.status_code == 200
    return response.json()["output_dir"]


def _montage(name: str) -> dict:
    return {
        "_type": "Montage",
        "name": name,
        "mode": "net",
        "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
        "eeg_net": "GSN-HydroCel-185.csv",
    }


def _sim(manager: JobManager, *names: str) -> str:
    config = {
        "subject_id": SUBJECT,
        "montages": [_montage(name) for name in names],
        "output_fields": ["TI_max"],
    }
    return manager.submit("sim", config, [SUBJECT])["id"]


def _flex(manager: JobManager, **overrides) -> str:
    config = serialize_config(
        FlexConfig(
            subject_id=SUBJECT,
            goal="mean",
            postproc="max_TI",
            current_mA=1.0,
            electrode=FlexConfig.ElectrodeConfig(),
            roi=FlexConfig.SphericalROI(x=0.0, y=0.0, z=0.0, radius=10.0),
            **overrides,
        )
    )
    return manager.submit("flex", config, [SUBJECT])["id"]


def _ex(manager: JobManager, **overrides) -> str:
    config = {
        "subject_id": SUBJECT,
        "leadfield_hdf": "leadfield.hdf5",
        "roi_name": "target.csv",
        "electrodes": {
            "_type": "PoolElectrodes",
            "electrodes": ["E1", "E2", "E3", "E4"],
        },
        "total_current": 2.0,
        "current_step": 1.0,
        **overrides,
    }
    return manager.submit("ex", config, [SUBJECT])["id"]


# --------------------------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------------------------


def test_a_running_simulation_answers_with_its_montage_folder(
    client: TestClient, manager: JobManager, project
) -> None:
    """Before the runner has registered anything, the plan names the folder."""
    job_id = _sim(manager, "L_Insula")
    folder = Path(project.simulation(SUBJECT, "L_Insula"))
    folder.mkdir(parents=True)
    assert _output_dir(client, job_id) == str(folder)


def test_a_simulation_whose_folder_does_not_exist_yet_answers_null(
    client: TestClient, manager: JobManager, project
) -> None:
    """A queued job has created nothing; the button must not point at a folder that is not there."""
    job_id = _sim(manager, "L_Insula")
    assert not os.path.exists(project.simulation(SUBJECT, "L_Insula"))
    assert _output_dir(client, job_id) is None


def test_a_finished_simulation_answers_with_the_folder_it_registered_not_its_parent(
    client: TestClient, manager: JobManager, project
) -> None:
    """The runner registers ``Simulations/<montage>`` as a ``dir``, then the mesh inside it."""
    job_id = _sim(manager, "L_Insula")
    folder = Path(project.simulation(SUBJECT, "L_Insula"))
    mesh = Path(project.ti_mesh(SUBJECT, "L_Insula"))
    mesh.parent.mkdir(parents=True)
    mesh.write_bytes(b"")
    _register(
        manager,
        job_id,
        {"path": str(folder), "kind": "dir", "label": "L_Insula"},
        {"path": str(mesh), "kind": "mesh", "label": "L_Insula"},
    )
    assert _output_dir(client, job_id) == str(folder)


def test_a_simulation_of_two_montages_has_no_single_folder(
    client: TestClient, manager: JobManager, project
) -> None:
    job_id = _sim(manager, "L_Insula", "R_Insula")
    for name in ("L_Insula", "R_Insula"):
        Path(project.simulation(SUBJECT, name)).mkdir(parents=True)
    assert _output_dir(client, job_id) is None
    _register(
        manager,
        job_id,
        *(
            {"path": project.simulation(SUBJECT, name), "kind": "dir", "label": name}
            for name in ("L_Insula", "R_Insula")
        ),
    )
    assert _output_dir(client, job_id) is None


# --------------------------------------------------------------------------------------------
# optimisation searches
# --------------------------------------------------------------------------------------------


def test_a_flex_search_with_a_named_folder_answers_before_it_registers_anything(
    client: TestClient, manager: JobManager, project
) -> None:
    run = Path(project.flex_search_run(SUBJECT, "insula_run"))
    job_id = _flex(manager, output_folder=str(run))
    assert _output_dir(client, job_id) is None  # the runner has not created it
    run.mkdir(parents=True)
    assert _output_dir(client, job_id) == str(run)


def test_a_flex_search_that_leaves_the_name_to_the_runner_answers_once_it_registers_it(
    client: TestClient, manager: JobManager, project
) -> None:
    """The plan only previews a timestamp for it, so the plan is not asked."""
    job_id = _flex(manager)
    Path(project.flex_search(SUBJECT)).mkdir(parents=True)
    assert _output_dir(client, job_id) is None
    run = Path(project.flex_search_run(SUBJECT, "20261022_101500"))
    run.mkdir(parents=True)
    assert _output_dir(client, job_id) is None
    _register(
        manager, job_id, {"path": str(run), "kind": "dir", "label": "output_folder"}
    )
    assert _output_dir(client, job_id) == str(run)


def test_an_ex_search_answers_with_the_directory_of_its_results(
    client: TestClient, manager: JobManager, project
) -> None:
    """``tit/opt/ex/__main__.py`` registers ``final_output.csv`` and ``run_config.json``."""
    job_id = _ex(manager)
    assert _output_dir(client, job_id) is None
    run = Path(project.ex_search_run(SUBJECT, "20261022_101500"))
    run.mkdir(parents=True)
    _register(
        manager,
        job_id,
        {"path": str(run / "final_output.csv"), "kind": "csv", "label": "results"},
        {"path": str(run / "run_config.json"), "kind": "json", "label": "config"},
    )
    assert _output_dir(client, job_id) == str(run)


def test_an_ex_search_with_a_run_name_answers_while_it_runs(
    client: TestClient, manager: JobManager, project
) -> None:
    job_id = _ex(manager, run_name="insula_run")
    run = Path(project.ex_search_run(SUBJECT, "insula_run"))
    run.mkdir(parents=True)
    assert _output_dir(client, job_id) == str(run)


# --------------------------------------------------------------------------------------------
# analysis, pre-processing
# --------------------------------------------------------------------------------------------


def test_an_analysis_answers_with_the_folder_the_plan_route_names(
    client: TestClient, manager: JobManager, project
) -> None:
    """The analysis folder, not the folder of whichever file the runner registered first."""
    config = {
        "subject_id": SUBJECT,
        "simulation": "L_Insula",
        "space": "mesh",
        "analysis_type": "spherical",
        "center": [1.0, 2.0, 3.0],
        "radius": 5.0,
    }
    job_id = manager.submit("analyzer", config, [SUBJECT])["id"]
    planned = client.post(
        "/api/plan/analyzer",
        json={"config": config, "subject_ids": [SUBJECT]},
        headers=BEARER,
    ).json()["jobs"]
    (folder,) = [job["output_dir"] for job in planned]
    assert "Analyses" in folder
    Path(folder, "figures").mkdir(parents=True)
    _register(
        manager,
        job_id,
        {"path": f"{folder}/figures/histogram.pdf", "kind": "pdf"},
        {"path": f"{folder}/results.csv", "kind": "csv"},
    )
    assert _output_dir(client, job_id) == folder


def test_a_pre_processing_stage_answers_with_its_subjects_stage_folder(
    client: TestClient, manager: JobManager, project
) -> None:
    from tit.jobs.plans import plan_preprocessing
    from tit.pre.config import PreprocessConfig

    (charm,) = plan_preprocessing(
        PreprocessConfig(subject_ids=[SUBJECT], create_m2m=True), [SUBJECT]
    )
    job_id = manager.submit(charm.kind, charm.config, charm.subject_ids)["id"]
    assert _output_dir(client, job_id) is None  # charm has not created m2m_<id> yet
    Path(project.m2m(SUBJECT)).mkdir(parents=True)
    assert _output_dir(client, job_id) == project.m2m(SUBJECT)


# --------------------------------------------------------------------------------------------
# never outside the project
# --------------------------------------------------------------------------------------------


def test_a_folder_outside_the_project_is_never_answered(
    client: TestClient, manager: JobManager, project, tmp_path_factory
) -> None:
    outside = tmp_path_factory.mktemp("elsewhere")
    job_id = _sim(manager, "L_Insula")
    _register(manager, job_id, {"path": str(outside), "kind": "dir"})
    assert _output_dir(client, job_id) is None

    other = _sim(manager, "R_Insula")
    _register(manager, other, {"path": str(outside / "mesh.msh"), "kind": "mesh"})
    assert _output_dir(client, other) is None


def test_the_field_is_declared_in_the_contract(client: TestClient) -> None:
    yaml = pytest.importorskip("yaml")
    contract = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "contracts" / "openapi.yaml").read_text()
    )
    detail = contract["components"]["schemas"]["JobDetail"]
    assert detail["properties"]["output_dir"]["type"] == ["string", "null"]
    assert "output_dir" not in detail["required"]
