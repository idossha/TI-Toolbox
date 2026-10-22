"""``plan_job`` keeps its contract against the real server for every flex kind, 2026-10-22.

What this pins: ``agent-plugin/mcp/jobs_server.py``'s plan_job / submit_job driven over HTTP
against the real FastAPI app (``tit.server.app.create_app``) with the fake runner, as in
``tests/test_agent_plugin_jobs.py::test_against_the_real_server_jobs_are_recorded_as_agent``:

* an invalid flex / flex_adaptive / flex_pareto config answers ``ok: false`` with the
  validate route's own field errors -- not a raw ``HTTP 422`` tool error from the run-folder
  probe that used to run first;
* a config that plans zero jobs is not ``ok`` and carries no ETA;
* for each flex kind a run name ``run_<kind>`` lands in ``PathManager.flex_search_run`` and
  the runner's ``config.json`` carries ``mode == kind`` (the Adaptive / Multi-threshold
  dispatch the Optimizer relies on).

Where the expected values come from: the tool's documented contract (plan_job: "errors,
missing inputs, output folders ... ETA"), ``POST /api/validate/<kind>`` called directly on the
same server, and ``PathManager`` computed in the test; nothing is read back from the plugin.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_plan_job.py -q
Deliberately elsewhere: request shapes against a fake server (tests/test_agent_plugin_jobs.py).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JOBS_SERVER = REPO / "agent-plugin" / "mcp" / "jobs_server.py"
TOKEN = "plan-job-test-token"
FLEX_KINDS = ("flex", "flex_adaptive", "flex_pareto")  # tit.jobs.kinds.FLEX_KINDS
ROI = {"_type": "SphericalROI", "x": -30.0, "y": 5.0, "z": 5.0, "radius": 10.0}


def call(mod, tool, **args):
    resp = mod.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
    )
    res = resp["result"]
    text = res["content"][0]["text"]
    return res["isError"], (text if res["isError"] else json.loads(text))


@pytest.fixture()
def live(monkeypatch, tmp_path):
    """The real app on a free port, a project with sub-101's head model, and the plugin."""
    pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    from tit.jobs import bootstrap
    from tit.jobs.manager import JobManager
    from tit.jobs.spec import Cost
    from tit.paths import get_path_manager
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    project = tmp_path / "proj"
    project.mkdir()
    pm = get_path_manager(str(project))
    m2m = Path(pm.m2m("101"))
    m2m.mkdir(parents=True)
    (m2m / "101.msh").write_bytes(b"")
    manager = JobManager(
        str(project),
        runner_cwd=str(project),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, spec_file: [
            sys.executable,
            str(REPO / "tests" / "fake_runner.py"),
            spec_file,
        ],
    )
    manager.start()
    bootstrap.set_manager_for_testing(manager)
    app = create_app(ServerSettings(project_dir=str(project), token=TOKEN))
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        port = server.servers[0].sockets[0].getsockname()[1]
        monkeypatch.setenv("TIT_SERVER_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("TIT_SERVER_TOKEN", TOKEN)
        monkeypatch.setenv("TIT_AGENT_POLL_S", "0.02")
        spec = importlib.util.spec_from_file_location("ti_jobs_plan", JOBS_SERVER)
        js = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(js)

        def as_user(method, path, body=None):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(body).encode() if body is not None else None,
                method=method,
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())

        yield js, pm, project, as_user
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        bootstrap.reset_manager()


@pytest.mark.parametrize("kind", FLEX_KINDS)
def test_an_invalid_flex_config_returns_the_validators_errors(live, kind):
    js, _, _, as_user = live
    expected = as_user(
        "POST",
        f"/api/validate/{kind}",
        {"config": {"subject_id": "101"}, "created_by": "agent"},
    )
    assert expected["ok"] is False and expected["errors"][0]["path"] == "roi"

    err, plan = call(js, "plan_job", kind=kind, config={}, subject_ids=["101"])
    assert not err, plan  # a structured answer, not a tool error
    assert plan["ok"] is False
    assert plan["errors"] == expected["errors"]
    assert plan["jobs"] == [] and plan["eta_minutes"] is None

    # submit_job refuses with the same field, never a raw HTTP status.
    err, text = call(js, "submit_job", kind=kind, config={}, subject_ids=["101"])
    assert err and "roi" in text and "HTTP 422" not in text


def test_an_invalid_goal_is_a_field_error_too(live):
    js, _, _, as_user = live
    config = {"roi": ROI, "goal": "nonsense", "subject_id": "101"}
    expected = as_user(
        "POST", "/api/validate/flex", {"config": config, "created_by": "agent"}
    )
    assert expected["ok"] is False
    err, plan = call(js, "plan_job", kind="flex", config=config, subject_ids=["101"])
    assert not err and plan["ok"] is False
    assert plan["errors"] == expected["errors"]


def test_a_plan_with_no_jobs_is_not_ok(live):
    js, _, _, _ = live
    err, plan = call(
        js, "plan_job", kind="sim", config={"montages": []}, subject_ids=["101"]
    )
    assert not err, plan
    assert plan["jobs"] == []
    assert plan["ok"] is False
    assert plan["eta_minutes"] is None
    assert "no jobs" in plan["reason"]


@pytest.mark.parametrize("kind", FLEX_KINDS)
def test_each_flex_kind_plans_into_its_run_folder_and_runs_in_its_mode(live, kind):
    js, pm, project, as_user = live
    from tit.jobs.registry import job_file_path

    run = f"run_{kind}"
    config = {"roi": ROI, "output_folder": run}
    err, plan = call(js, "plan_job", kind=kind, config=config, subject_ids=["101"])
    assert not err, plan
    assert plan["ok"] is True, plan
    assert [j["output_dir"] for j in plan["jobs"]] == [pm.flex_search_run("101", run)]
    assert plan["eta_minutes"] and plan["eta_minutes"] > 0

    as_user(
        "PUT",
        "/api/settings",
        {"panels": [], "theme": "system", "agent_auto_submit": True},
    )
    err, sub = call(js, "submit_job", kind=kind, config=config, subject_ids=["101"])
    assert not err, sub
    assert sub["output_folders"] == {"101": pm.flex_search_run("101", run)}
    err, done = call(js, "wait_for_job", job_ids=sub["job_ids"], timeout_s=20)
    assert not err and done["done"], done
    [job_id] = sub["job_ids"]
    runner = json.loads(
        Path(job_file_path(str(project), job_id, "config.json")).read_text()
    )
    assert runner["mode"] == kind
    assert runner["output_folder"] == pm.flex_search_run("101", run)


def test_a_refusal_without_a_message_never_reads_none():
    """``ValidateError`` requires ``path`` and ``message`` (contracts/openapi.yaml), but the
    plugin must not print Python's ``None`` when a server leaves one out."""
    spec = importlib.util.spec_from_file_location("ti_jobs_invalid", JOBS_SERVER)
    js = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(js)

    text = str(js.InvalidConfig([{"path": "roi"}, {"message": "goal is unknown"}]))
    assert text == "the config is invalid: roi: invalid; config: goal is unknown"
    assert str(js.InvalidConfig([])) == "the config is invalid"
