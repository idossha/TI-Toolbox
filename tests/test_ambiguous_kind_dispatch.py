"""The server reads an ambiguous kind's config the way its runner dispatches it.

What this pins (2026-10-22)
    ``stats`` and ``blender`` each have several config classes under one job kind. The server
    picks one in :func:`tit.server.routes.validate.cls_for` (used by ``/api/validate``,
    ``/api/plan`` and, through the overwrite check, ``POST /api/jobs``); the runner picks one in
    its own ``main()``. Before this, the two disagreed:

    - ``blender`` without ``_type`` was validated and planned as ``MontageConfig`` and accepted at
      submit, while ``tit.blender.__main__`` logged "Unknown blender config type: None" and
      exited 1;
    - ``stats`` with the older ``mode`` key: the runner (and the lock table) let ``mode`` win,
      while ``cls_for`` and the plan ignored it, so a correlation run was planned into
      ``stats/group_comparison/<name>``.

Where the expectations come from
    The oracle is each runner's own ``main()``, run on the same body with its handlers replaced
    by recorders: which handler it calls (or that it refuses) is the truth the server must agree
    with. A body the server accepts must reach the handler of the class the server chose, its plan
    folder must be that mode's ``stats/<mode>/<analysis_name>`` and the lock key the runner asks
    for must name the same mode. A body the runner cannot run as the server reads it must be
    refused by the server (422 at plan and submit, ``ok: false`` at validate).

Run: .venv/bin/python -m pytest tests/test_ambiguous_kind_dispatch.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.locks import keys_for  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes.validate import KindNotConfigurable, cls_for  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-ambiguous"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
NAME = "run1"

#: Rows a GroupComparisonConfig and a CorrelationConfig both accept (the non-strict readers --
#: cls_for, the plan, the runner -- ignore the other class's key), so only the dispatch decides.
_BOTH_ROWS = [
    {"subject_id": f"00{i}", "simulation_name": "M1", "response": i % 2}
    | {"effect_size": 0.1 * i}
    for i in range(1, 5)
]
_GROUP_ROWS = [
    {k: r[k] for k in ("subject_id", "simulation_name", "response")} for r in _BOTH_ROWS
]
_CORR_ROWS = [
    {k: r[k] for k in ("subject_id", "simulation_name", "effect_size")}
    for r in _BOTH_ROWS
]

#: (case id, the dispatch keys of the body). Rows are added per use.
STATS_CASES = [
    ("type-group", {"_type": "GroupComparisonConfig"}),
    ("type-correlation", {"_type": "CorrelationConfig"}),
    ("neither", {}),
    ("mode-correlation", {"mode": "correlation"}),
    ("mode-group", {"mode": "group_comparison"}),
    ("mode-and-type-agree", {"mode": "correlation", "_type": "CorrelationConfig"}),
    (
        "mode-contradicts-type",
        {"mode": "correlation", "_type": "GroupComparisonConfig"},
    ),
    ("mode-unknown", {"mode": "bogus"}),
    ("type-unknown", {"_type": "PermutationConfig"}),
]

#: What the stats runner runs for each handler (tit.stats.__main__'s own two entry points).
_HANDLER_MODE = {
    "_run_group_comparison": "group_comparison",
    "_run_correlation": "correlation",
}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(root))
    m2m = Path(pm.m2m("001"))
    m2m.mkdir(parents=True)
    (m2m / "001.msh").write_bytes(b"")
    # The simulation a blender body names, so a submit is judged on its config, not refused
    # earlier for a missing input.
    Path(pm.simulation("001", "M1")).mkdir(parents=True)
    return root


@pytest.fixture()
def client(project: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: project / "preferences.json"
    )

    def never_run(kind, config, spec_path):  # a refused body must never reach a runner
        raise AssertionError(f"a {kind} job was started")

    manager = JobManager(
        str(project),
        runner_cwd=str(project),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=never_run,
    )
    manager.start()
    bootstrap.set_manager_for_testing(manager)
    yield TestClient(
        create_app(ServerSettings(project_dir=str(project), token=TOKEN)), base_url=BASE
    )
    bootstrap.reset_manager()


def _run_main(module, body: dict, project: Path, tmp_path: Path, monkeypatch):
    """Run *module*.main() on *body* (as the manager writes it); return its exit outcome."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**body, "project_dir": str(project)}))
    monkeypatch.setattr(sys, "argv", [module.__name__, str(path)])
    monkeypatch.delenv("TIT_JOB_ID", raising=False)
    try:
        code = module.main()
    except SystemExit as exc:
        code = exc.code
    except (ValueError, TypeError) as exc:  # the runner died before dispatching
        return f"crash: {exc}"
    return code


def _stats_runner(body: dict, project: Path, tmp_path: Path, monkeypatch):
    """The stats runner's verdict: (handler it called or None, its lock keys, exit outcome)."""
    from tit.stats import __main__ as runner

    called: list[tuple[str, str]] = []
    requested: list[list[str]] = []

    def recorder(name):
        def handler(config, started=0.0):
            called.append((name, type(config).__name__))
            return 0

        return handler

    for name in _HANDLER_MODE:
        monkeypatch.setattr(runner, name, recorder(name))

    def hold(kind, subject_ids, config_dict):
        requested.append([r.resource for r in keys_for(kind, subject_ids, config_dict)])
        return nullcontext()

    monkeypatch.setattr(runner.locks, "hold_for_job", hold)
    outcome = _run_main(runner, body, project, tmp_path, monkeypatch)
    return (called[0] if called else None), (requested[0] if requested else []), outcome


def _server_class(kind: str, body: dict) -> str | None:
    try:
        return cls_for(kind, body).__name__
    except KindNotConfigurable:
        return None


@pytest.mark.parametrize("case,keys", STATS_CASES, ids=[c for c, _ in STATS_CASES])
def test_stats_server_and_runner_agree(
    case, keys, client: TestClient, project: Path, tmp_path: Path, monkeypatch
) -> None:
    body = {
        "analysis_name": NAME,
        "subjects": _BOTH_ROWS,
        "n_permutations": 100,
        **keys,
    }
    server = _server_class("stats", body)
    plan = client.post("/api/plan/stats", json={"config": body}, headers=BEARER)
    handler, runner_keys, outcome = _stats_runner(body, project, tmp_path, monkeypatch)

    if server is None or plan.status_code != 200:
        # The server refuses: the body must be one the runner cannot run as the server would
        # read it -- it crashes, or it runs under a mode its own lock key does not name.
        assert plan.status_code == 422, plan.text
        runner_mode = _HANDLER_MODE[handler[0]] if handler else None
        lock_modes = {
            k.split(":")[2].split("/")[0]
            for k in runner_keys
            if k.startswith("project:stats:")
        }
        assert handler is None or lock_modes != {
            runner_mode
        }, f"{case}: the server refused a body the runner runs cleanly as {handler}"
        return

    assert outcome == 0, outcome
    assert handler is not None
    name, config_class = handler
    mode = _HANDLER_MODE[name]
    # The runner ran the class the server validated and planned.
    assert config_class == server
    # The plan's folder is the one that mode's runner writes: stats/<mode>/<analysis_name>.
    pm = get_path_manager(str(project))
    assert Path(plan.json()["jobs"][0]["output_dir"]) == Path(
        pm.stats_output(mode, NAME)
    )
    # The runner's own lock request and the server's (submit-time) one name the same folder.
    assert f"project:stats:{mode}/{NAME}" in runner_keys
    server_keys = [r.resource for r in keys_for("stats", [], body)]
    assert f"project:stats:{mode}/{NAME}" in server_keys


#: The spec of the table above, stated per case: the class each accepted body must run as.
_EXPECTED_STATS = {
    "type-group": "GroupComparisonConfig",
    "type-correlation": "CorrelationConfig",
    "neither": "GroupComparisonConfig",
    "mode-correlation": "CorrelationConfig",
    "mode-group": "GroupComparisonConfig",
    "mode-and-type-agree": "CorrelationConfig",
    "mode-contradicts-type": None,
    "mode-unknown": None,
    "type-unknown": None,
}


@pytest.mark.parametrize("case,keys", STATS_CASES, ids=[c for c, _ in STATS_CASES])
def test_stats_cls_for_follows_mode_then_type(case, keys) -> None:
    assert (
        _server_class("stats", {"analysis_name": NAME, **keys}) == _EXPECTED_STATS[case]
    )


@pytest.mark.parametrize(
    "keys,rows,expected_dir",
    [
        ({"mode": "correlation"}, _CORR_ROWS, "correlation"),
        ({"mode": "group_comparison"}, _GROUP_ROWS, "group_comparison"),
    ],
)
def test_stats_validate_accepts_the_legacy_mode_key(
    keys, rows, expected_dir, client: TestClient, project: Path
) -> None:
    """The runner pops ``mode`` before reading the config, so strict validation must too."""
    body = {"analysis_name": NAME, "subjects": rows, "n_permutations": 100, **keys}
    resp = client.post("/api/validate/stats", json={"config": body}, headers=BEARER)
    assert resp.json() == {"ok": True, "errors": []}
    plan = client.post("/api/plan/stats", json={"config": body}, headers=BEARER)
    assert plan.status_code == 200, plan.text
    assert Path(plan.json()["jobs"][0]["output_dir"]).parent.name == expected_dir


def test_stats_validate_names_the_contradiction(client: TestClient) -> None:
    body = {
        "analysis_name": NAME,
        "subjects": _CORR_ROWS,
        "mode": "correlation",
        "_type": "GroupComparisonConfig",
    }
    resp = client.post(
        "/api/validate/stats", json={"config": body}, headers=BEARER
    ).json()
    assert resp["ok"] is False
    assert resp["errors"][0]["path"] == "_type"
    assert "correlation" in resp["errors"][0]["message"]


# ---------------------------------------------------------------------------------------------
# blender
# ---------------------------------------------------------------------------------------------

_BLENDER_HANDLERS = {
    "MontageConfig": "_run_montage",
    "VectorConfig": "_run_vectors",
    "RegionConfig": "_run_regions",
    "SubcorticalConfig": "_run_subcortical",
}

BLENDER_CASES = [
    ("montage", {"_type": "MontageConfig"}),
    ("vector", {"_type": "VectorConfig"}),
    ("region", {"_type": "RegionConfig"}),
    ("subcortical", {"_type": "SubcorticalConfig"}),
    ("no-type", {}),
    ("legacy-mode-key", {"mode": "VectorConfig"}),
    ("unknown-type", {"_type": "MeshConfig"}),
]


def _blender_runner(body, project, tmp_path, monkeypatch):
    from tit.blender import __main__ as runner

    called: list[str] = []
    for name in _BLENDER_HANDLERS.values():
        monkeypatch.setattr(
            runner,
            name,
            lambda data, logger, _n=name: called.append(_n) or str(tmp_path / "out"),
        )
    monkeypatch.setattr(runner.locks, "hold_for_job", lambda *a: nullcontext())
    outcome = _run_main(runner, body, project, tmp_path, monkeypatch)
    return (called[0] if called else None), outcome


@pytest.mark.parametrize("case,keys", BLENDER_CASES, ids=[c for c, _ in BLENDER_CASES])
def test_blender_server_and_runner_agree(
    case, keys, client: TestClient, project: Path, tmp_path: Path, monkeypatch
) -> None:
    body = {"subject_id": "001", "simulation_name": "M1", **keys}
    server = _server_class("blender", body)
    handler, outcome = _blender_runner(body, project, tmp_path, monkeypatch)
    plan = client.post("/api/plan/blender", json={"config": body}, headers=BEARER)
    validate = client.post(
        "/api/validate/blender", json={"config": body}, headers=BEARER
    ).json()

    if handler is None:
        # The runner refuses (exit 1, nothing exported): the server must refuse too, everywhere.
        assert outcome == 1
        assert server is None
        assert plan.status_code == 422, plan.text
        assert "_type" in plan.json()["detail"]
        assert validate["ok"] is False and validate["errors"][0]["path"] == "_type"
        submit = client.post(
            "/api/jobs",
            json={"kind": "blender", "config": body, "subject_ids": ["001"]},
            headers=BEARER,
        )
        assert submit.status_code == 422, submit.text
        assert "_type" in json.dumps(submit.json())
        return

    assert outcome == 0
    assert handler == _BLENDER_HANDLERS[server]
    assert plan.status_code == 200, plan.text
    assert validate == {"ok": True, "errors": []}


def test_blender_without_type_is_refused_by_cls_for() -> None:
    with pytest.raises(KindNotConfigurable, match="_type"):
        cls_for("blender", {"subject_id": "001", "simulation_name": "M1"})
