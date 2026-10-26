"""Real JSON GET responses validate against the hand-written ``contracts/openapi.yaml``.

What this pins
--------------
The desktop's API types (``schema.d.ts``) are generated from the contract, but most
routes return plain ``dict``s, so FastAPI's own OpenAPI says nothing about them and
``dev/contracts_check.py`` can only warn. Here the contract is the oracle and the
server's responses are the data: every contract ``GET`` with a ``200
application/json`` schema is called on the real app (``TestClient``) against the
synthetic project in ``tests/contract_project.py`` (TI with MNI and hf_peak/hf_sar,
mTI, vn, Mesh and Voxel analyses, flex/ex runs, reports, stats, averages, ROIs,
free-hand configs, caps) and validated with ``jsonschema``'s Draft 2020-12 validator,
``$ref``s resolved through a registry rooted at the whole contract.

* A list response must be non-empty where the project has data for it, so items are
  actually validated (an empty array satisfies any ``items`` schema).
* The contract's JSON GET paths minus the exercised ones must equal ``EXEMPT``
  exactly, each exemption with its reason: a new route cannot go unchecked, and a
  route that becomes exercised must leave the list.
* A corrupted response fails validation, so the check cannot be vacuous.
* The job and proposal routes are called on an app whose real ``JobManager`` runs
  ``tests/fake_runner.py`` in place of SimNIBS: a ``sim`` job with a real
  ``SimulationConfig``, a ``tools`` job that reports an artifact folder of the
  project, and a pending agent proposal, so ``JobStatus``, ``JobDetail``, ``Event``,
  ``JobOutputs`` and ``Proposal`` items are validated, not empty lists.
* Violations found and left open are listed in ``KNOWN_VIOLATIONS`` with why and who
  fixes them (2026-10-22: the contract's OpenAPI 3.0 ``nullable: true`` on candidate
  metrics, ``/api/system``'s null optional blocks, and ``PipelineConfig``'s ``oneOf``
  that every job config matches more than once); an entry that stops occurring fails,
  so the list only shrinks.

Reproduce: ``.venv/bin/python -m pytest tests/test_contract_response_conformance.py -q``.
The scene routes' bodies are validated in ``tests/test_scene_routes.py`` (they need
published surfaces); request bodies are ``dev/contracts_check.py``'s.
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from typing import Any, Callable

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from tests.contract_project import ContractProject, build_contract_project
from tests.test_jobs_routes import wait_until
from tit.jobs import bootstrap
from tit.jobs.manager import JobManager
from tit.jobs.spec import Cost
from tit.server.app import create_app
from tit.server.settings import ServerSettings

REPO = Path(__file__).resolve().parent.parent
CONTRACT = yaml.safe_load(
    (REPO / "contracts" / "openapi.yaml").read_text(encoding="utf-8")
)
CONTRACT_URI = "urn:tit-contract"
TOKEN = "contract-conformance"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
BASE_URL = "http://127.0.0.1:8765"
FAKE_RUNNER = str(REPO / "tests" / "fake_runner.py")


def _json_get_paths() -> set[str]:
    paths = set()
    for path, item in CONTRACT["paths"].items():
        response = (item.get("get") or {}).get("responses", {}).get("200", {})
        if "application/json" in response.get("content", {}):
            paths.add(path)
    return paths


def _items(key: str | None = None) -> Callable[[Any], list]:
    """The list in a response that must be non-empty (the body itself, or ``body[key]``)."""
    return lambda body: body if key is None else body[key]


P = ContractProject(root=Path("."))  # identifiers only; the tree is built per test
SID, SIM = P.subject, P.ti_sim

#: contract path -> (URL to call, which list must be non-empty or None).
REQUESTS: dict[str, tuple[str, Callable[[Any], list] | None]] = {
    "/api/health": ("/api/health", None),
    "/api/version": ("/api/version", None),
    "/api/capabilities": ("/api/capabilities", None),
    "/api/project": ("/api/project", None),
    "/api/project/status": ("/api/project/status", None),
    "/api/example-data": ("/api/example-data", _items("datasets")),
    "/api/system": ("/api/system", None),
    "/api/system/storage": ("/api/system/storage", None),
    "/api/catalog/subjects": ("/api/catalog/subjects", _items("subjects")),
    "/api/catalog/subjects/{id}": (f"/api/catalog/subjects/{SID}", None),
    "/api/catalog/simulations": (
        f"/api/catalog/simulations?subject={SID}",
        _items("simulations"),
    ),
    "/api/catalog/simulations/{name}": (
        f"/api/catalog/simulations/{SIM}?subject={SID}",
        _items("niftis"),
    ),
    "/api/catalog/montages": ("/api/catalog/montages", None),
    "/api/catalog/eeg-nets": (f"/api/catalog/eeg-nets?subject={SID}", _items()),
    "/api/catalog/atlases": (f"/api/catalog/atlases?subject={SID}", _items()),
    "/api/catalog/atlases/regions": (
        f"/api/catalog/atlases/regions?subject={SID}&atlas=DK40",
        None,
    ),
    "/api/catalog/rois": (f"/api/catalog/rois?subject={SID}", _items()),
    "/api/catalog/leadfields": (f"/api/catalog/leadfields?subject={SID}", _items()),
    "/api/catalog/flex-runs": (f"/api/catalog/flex-runs?subject={SID}", _items()),
    "/api/catalog/flex-runs/{run}/mapping": (
        f"/api/catalog/flex-runs/{P.flex_run}/mapping?subject={SID}&eeg_net={P.net}",
        None,
    ),
    "/api/catalog/ex-runs": (f"/api/catalog/ex-runs?subject={SID}", _items()),
    "/api/catalog/optimization-candidates": (
        f"/api/catalog/optimization-candidates?subject={SID}&kind=ex&run={P.ex_run}",
        _items("candidates"),
    ),
    "/api/catalog/optimization-candidates/{candidate_id}": (
        "/api/catalog/optimization-candidates/{candidate}"
        f"?subject={SID}&kind=ex&run={P.ex_run}",
        None,
    ),
    "/api/catalog/analyses": (
        f"/api/catalog/analyses?subject={SID}&simulation={SIM}",
        _items(),
    ),
    "/api/catalog/analyses/{name}/summary": (
        f"/api/catalog/analyses/{P.mesh_analysis}/summary?subject={SID}&simulation={SIM}",
        _items("rows"),
    ),
    "/api/catalog/reports": (f"/api/catalog/reports?subject={SID}", _items()),
    "/api/catalog/freehand": (f"/api/catalog/freehand?subject={SID}", _items()),
    "/api/catalog/group": ("/api/catalog/group", _items("stats")),
    "/api/catalog/notes": ("/api/catalog/notes", None),
    "/api/catalog/project-summary": ("/api/catalog/project-summary", None),
    "/api/catalog/overview": ("/api/catalog/overview", None),
    "/api/schema": ("/api/schema", None),
    "/api/jobs": ("/api/jobs", _items()),
    "/api/jobs/{id}": ("/api/jobs/{sim_job}", None),
    "/api/jobs/{id}/events": ("/api/jobs/{tools_job}/events", _items()),
    "/api/jobs/{id}/artifacts": ("/api/jobs/{tools_job}/artifacts", _items("files")),
    "/api/proposals": ("/api/proposals", _items()),
    "/api/proposals/{id}": ("/api/proposals/{proposal}", _items("steps")),
    "/api/sim-from-flex": (
        f"/api/sim-from-flex?subject={SID}&flex_run={P.flex_run}&eeg_net={P.net}",
        None,
    ),
    "/api/view/{kind}": (f"/api/view/simulation?subject={SID}&simulation={SIM}", None),
    "/api/viewer/candidates": (
        f"/api/viewer/candidates?subject={SID}&simulation={SIM}",
        None,
    ),
    "/api/viewer/tree": (f"/api/viewer/tree?subject={SID}", None),
    "/api/viewer/scenes": ("/api/viewer/scenes", None),
    "/api/viewer/scenes/suggest/name": (
        f"/api/viewer/scenes/suggest/name?subject={SID}&simulation={SIM}&field=TI_max",
        None,
    ),
    "/api/cpu-limit": ("/api/cpu-limit", None),
    "/api/surfer-settings": ("/api/surfer-settings", None),
    "/api/settings": ("/api/settings", None),
    "/api/caps/available": (f"/api/caps/available?subject={SID}", _items("caps")),
    "/api/guide/manifest": ("/api/guide/manifest", None),
    "/api/guide/regions": ("/api/guide/regions?atlas=DK40", _items("legend")),
    "/api/guide/electrodes": (
        "/api/guide/electrodes?net=EEG10-10_UI_Jurak_2007.csv",
        _items("electrodes"),
    ),
    "/api/notebooks": ("/api/notebooks", _items("notebooks")),
    "/api/notebooks/{name}": ("/api/notebooks/{notebook}", None),
    "/api/kernels": ("/api/kernels", None),
}

#: Contract JSON GET paths this test does not call, each with the reason.
EXEMPT: dict[str, str] = {
    "/api/scene/manifest": "needs published surfaces; tests/test_scene_routes.py validates it",
    "/api/scene/regions": "needs published labels; tests/test_scene_routes.py validates it",
    "/api/scene/electrodes": "tests/test_scene_routes.py validates it against the contract",
    "/api/catalog/regions": (
        "reads the voxel atlases' label values with nibabel, a MagicMock on the host"
    ),
    "/api/catalog/nifti/labels": (
        "reads a NIfTI's label values with nibabel, a MagicMock on the host"
    ),
    "/api/catalog/optimization-candidates/{candidate_id}/mapping": (
        "flex-only (an ex run answers 404), and needs a flex run's candidate_history/ "
        "written by SimNIBS's optimizer"
    ),
    "/api/caps/inspect": "warps the cap onto the subject's scalp with SimNIBS (mocked)",
    "/api/viewer/scenes/{name}": "needs a scene saved by the native viewer",
}


#: Contract violations found by this test and left open, each with why and who fixes it.
#: An entry is a regex over "<location>: <message>" lines; one that stops matching any
#: error fails the test, so this list shrinks when the fix lands and cannot rot.
KNOWN_VIOLATIONS: dict[str, tuple[str, str]] = {
    "/api/catalog/optimization-candidates": (
        r"candidates/\d+/metrics/(roi_p99_9|background_p95): None is not of type 'number'",
        "contract: OptimizationCandidate.metrics says `nullable: true`, an OpenAPI 3.0 keyword "
        "that this 3.1 document ignores; an ex run has no p99.9/p95 so the server's null is "
        "the intent. Fix the contract to `type: [number, 'null']` (contracts owner).",
    ),
    "/api/catalog/optimization-candidates/{candidate_id}": (
        r"candidate/metrics/(roi_p99_9|background_p95): None is not of type 'number'",
        "same `nullable: true` contract defect as the candidate page",
    ),
    "/api/jobs/{id}": (
        r"spec/config: \{'subject_id': '101'.* is valid under each of .*",
        "contract: JobSpec.config is PipelineConfig, a `oneOf` of 19 placeholder members "
        "that each accept any object, so every real config matches all of them and `oneOf` "
        "(exactly one) fails for every job. Make it `anyOf`, or pick the member by `kind` "
        "(contracts owner).",
    ),
    "/api/system": (
        r"(disk_docker|docker/own): None is not of type 'object'",
        "the server sends null for an optional block it cannot read (no Docker socket, "
        "no visible /var/lib/docker), where tit/server/schemas.py says such fields are "
        "omitted and the contract types them object-only; omit them or allow null.",
    ),
}


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ContractProject:
    built = build_contract_project(tmp_path / "project")
    # SimNIBS (a MagicMock on the host) owns the MNI caps folder; give it one cap.
    caps = tmp_path / "simnibs_caps"
    caps.mkdir()
    (caps / P.net).write_text("Electrode,-26.1,113.7,19.1,E001\n", encoding="utf-8")
    import tit.caps

    monkeypatch.setattr(tit.caps, "simnibs_caps_dir", lambda: caps)
    return built


@pytest.fixture()
def client(project: ContractProject) -> TestClient:
    app = create_app(ServerSettings(project_dir=str(project.root), token=TOKEN))
    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client


#: Contract paths answered from job and proposal records, called on the ``jobs`` app.
JOB_PATHS = {p for p in REQUESTS if p.startswith(("/api/jobs", "/api/proposals"))}
MONTAGE = {
    "_type": "Montage",
    "name": "m1",
    "mode": "net",
    "electrode_pairs": [["E001", "E002"], ["E003", "E004"]],
    "eeg_net": P.net,  # the four electrodes contract_project writes on this net
}


@pytest.fixture()
def jobs(project: ContractProject) -> tuple[TestClient, dict[str, str]]:
    """An app whose real JobManager ran two finished jobs, plus one pending proposal.

    The manager is the real one with ``tests/fake_runner.py`` as the runner (the
    wiring of ``tests/test_jobs_routes.py``): submission, preflight, the job records,
    events.jsonl and the artifact walk are the server's own.
    """
    root = str(project.root)
    manager = JobManager(
        root,
        runner_cwd=root,
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, spec: [sys.executable, FAKE_RUNNER, spec],
    )
    manager.start()
    bootstrap.set_manager_for_testing(manager)
    try:
        app = create_app(ServerSettings(project_dir=root, token=TOKEN))
        with TestClient(app, base_url=BASE_URL) as test_client:
            yield test_client, _seed_jobs(test_client, project)
    finally:
        bootstrap.reset_manager()


def _state(client: TestClient, job_id: str) -> str:
    return client.get(f"/api/jobs/{job_id}", headers=BEARER).json()["status"]["state"]


def _seed_jobs(client: TestClient, project: ContractProject) -> dict[str, str]:
    sim_dir = (
        project.root / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / SIM
    )
    submitted = {
        "sim_job": {
            "kind": "sim",
            "subject_ids": [SID],
            "config": {"subject_id": SID, "montages": [MONTAGE]},
        },
        "tools_job": {
            "kind": "tools",
            "subject_ids": [SID],
            "config": {
                "__fake": {
                    "stages": ["prepare", "run"],
                    "progress_steps": 2,
                    "artifact": str(sim_dir),
                    "outputs": {"simulation": SIM},
                }
            },
        },
    }
    ids = {}
    for key, body in submitted.items():
        response = client.post("/api/jobs", headers=BEARER, json=body)
        assert response.status_code == 201, response.text
        ids[key] = response.json()["id"]
    for job_id in ids.values():
        wait_until(lambda job_id=job_id: _state(client, job_id) == "succeeded")
    response = client.post(
        "/api/proposals",
        headers=BEARER,
        json={
            "title": "Simulate m1",
            "rationale": "contract conformance",
            "client": "Claude Code",
            "steps": [
                {
                    "id": "sim",
                    "kind": "sim",
                    "subject_ids": [SID],
                    "config": {"montages": [MONTAGE]},
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    ids["proposal"] = response.json()["id"]
    return ids


def _validator(path: str) -> jsonschema.Draft202012Validator:
    parts = ("paths", path, "get", "responses", "200", "content", "application/json")
    pointer = "/".join(p.replace("~", "~0").replace("/", "~1") for p in parts)
    registry = Registry().with_resource(
        CONTRACT_URI,
        Resource.from_contents(CONTRACT, default_specification=DRAFT202012),
    )
    return jsonschema.Draft202012Validator(
        {"$ref": f"{CONTRACT_URI}#/{pointer}/schema"}, registry=registry
    )


def _url(
    client: TestClient,
    project: ContractProject,
    template: str,
    seeded: dict[str, str] | None = None,
) -> str:
    url = template.replace("{root}", str(project.root))
    for key, value in (seeded or {}).items():
        url = url.replace("{" + key + "}", value)
    if "{candidate}" in url:
        page = client.get(
            f"/api/catalog/optimization-candidates?subject={SID}&kind=ex&run={P.ex_run}",
            headers=BEARER,
        ).json()
        url = url.replace("{candidate}", page["candidates"][0]["id"])
    if "{notebook}" in url:
        listing = client.get("/api/notebooks", headers=BEARER).json()
        url = url.replace("{notebook}", listing["notebooks"][0]["name"])
    return url


def test_every_contract_json_get_is_exercised_or_exempt() -> None:
    contract_paths = _json_get_paths()
    assert len(contract_paths) > 50, "the contract parser found too few GET routes"
    assert not set(REQUESTS) & set(EXEMPT), "a path is both exercised and exempt"
    assert set(KNOWN_VIOLATIONS) <= set(
        REQUESTS
    ), "a known violation on an unexercised path"
    unknown = set(REQUESTS) - contract_paths
    assert (
        not unknown
    ), f"REQUESTS names paths the contract does not have: {sorted(unknown)}"
    unchecked = contract_paths - set(REQUESTS) - set(EXEMPT)
    stale = set(EXEMPT) - (contract_paths - set(REQUESTS))
    assert not unchecked and not stale, (
        f"unchecked contract routes (exercise or exempt them): {sorted(unchecked)}; "
        f"stale exemptions: {sorted(stale)}"
    )


@pytest.mark.parametrize("path", sorted(REQUESTS))
def test_the_real_response_matches_the_contract(
    request: pytest.FixtureRequest, project: ContractProject, path: str
) -> None:
    if path in JOB_PATHS:
        client, seeded = request.getfixturevalue("jobs")
    else:
        client, seeded = request.getfixturevalue("client"), {}
    template, items = REQUESTS[path]
    url = _url(client, project, template, seeded)
    assert "{" not in url, f"unfilled placeholder in {url}"
    response = client.get(url, headers=BEARER)
    assert response.status_code == 200, (url, response.status_code, response.text[:400])
    body = response.json()
    if items is not None:
        listed = items(body)
        assert (
            isinstance(listed, list) and listed
        ), f"{url}: the list the project has data for is empty or not a list"
    errors = sorted(
        _validator(path).iter_errors(body), key=lambda e: list(e.absolute_path)
    )
    lines = [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message[:300]}"
        for e in errors
    ]
    known = KNOWN_VIOLATIONS.get(path)
    if known is not None:
        matched = [line for line in lines if re.fullmatch(known[0], line)]
        assert (
            matched
        ), f"{path}: the known violation is fixed -- remove it from KNOWN_VIOLATIONS"
        lines = [line for line in lines if line not in matched]
    assert not lines, f"{path} breaks the contract:\n" + "\n".join(lines[:10])


def test_the_project_covers_ti_mti_vn_mni_and_hf_outputs(client: TestClient) -> None:
    """The fixture reaches the branches it claims to (else the checks above are thin)."""
    sims = client.get(f"/api/catalog/simulations?subject={SID}", headers=BEARER).json()
    assert {s["name"] for s in sims["simulations"]} == {P.ti_sim, P.mti_sim, P.vn_sim}
    detail = client.get(
        f"/api/catalog/simulations/{SIM}?subject={SID}", headers=BEARER
    ).json()
    assert {n["space"] for n in detail["niftis"]} == {"subject", "mni"}
    analyses = client.get(
        f"/api/catalog/analyses?subject={SID}&simulation={SIM}", headers=BEARER
    ).json()
    assert len(analyses) == 2
    group = client.get("/api/catalog/group", headers=BEARER).json()
    assert {(s["type"], s["name"]) for s in group["stats"]} == set(P.stats)


def test_a_corrupted_response_fails_validation(client: TestClient) -> None:
    """The negative control: if these passed, every check above would be vacuous."""
    body = client.get(
        f"/api/catalog/simulations/{SIM}?subject={SID}", headers=BEARER
    ).json()
    validator = _validator("/api/catalog/simulations/{name}")
    validator.validate(body)  # the real body is valid

    nulled = copy.deepcopy(body)
    nulled["niftis"] = None  # contract: array of NiftiRef
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(nulled)

    dropped = copy.deepcopy(body)
    del dropped["fields"]  # contract: required
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(dropped)

    nested = copy.deepcopy(body)
    nested["niftis"][0]["space"] = "MNI152"  # contract enum: subject | mni
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(nested)
