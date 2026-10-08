"""Tests for the agent plugin's job driver (agent-plugin/mcp/jobs_server.py), 2026-10-07.

What this pins: discovery (env first, then the `tit.stack=ti-toolbox-v3` container, one project
at a time), the request each verb sends to tit.server (only the agent's own fields, with
created_by "agent"), find_regions passing the server's answer through, the
flex-result -> simulation chain, watch_proposal returning once per change, and (2026-10-08)
the stdio server answering other calls while a wait runs, with progress and cancellation.

Where the expected values come from: request shapes are the routes' own contracts
(contracts/openapi.yaml JobSpec/JobGroupRequest, PlanRequest, MontageSources) and the desktop's
builders (pages/_shared/roi/types.ts roiToConfig, pages/simulator/buildConfig.ts), restated by
hand (groundTruth: authored).
The last test drives the real FastAPI app (fake runner) over HTTP, so the wire shapes are also
checked against the server rather than against this file's fake.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_jobs.py -q
Deliberately elsewhere: created_by on the routes themselves (tests/test_jobs_routes.py); the
MCP stdio framing shared with server.py (agent-plugin/mcp/test_stdio.py).
"""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

REPO = Path(__file__).resolve().parents[1]
JOBS_SERVER = REPO / "agent-plugin" / "mcp" / "jobs_server.py"
TOKEN = "agent-test-token"


@pytest.fixture()
def js(monkeypatch):
    spec = importlib.util.spec_from_file_location("ti_jobs_server", JOBS_SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("TIT_AGENT_POLL_S", "0.01")
    return mod


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


class FakeServer:
    """A tit.server stand-in: canned answers per (method, path), every request recorded."""

    def __init__(self):
        self.routes = {}
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                query = {k: v[0] for k, v in parse_qs(parts.query).items()}
                outer.requests.append(
                    {
                        "method": self.command,
                        "path": parts.path,
                        "query": query,
                        "body": body,
                        "auth": self.headers.get("Authorization"),
                    }
                )
                answer = outer.routes.get((self.command, parts.path))
                status, payload = (
                    answer(query, body) if callable(answer) else (200, answer)
                )
                if answer is None:
                    status, payload = 404, {"detail": f"no route {parts.path}"}
                raw = (
                    payload.encode()
                    if isinstance(payload, str)
                    else json.dumps(payload).encode()
                )
                self.send_response(status)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = _serve

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(
            target=self.httpd.serve_forever, args=(0.01,), daemon=True
        ).start()

    def sent(self, method, path):
        return [r for r in self.requests if r["method"] == method and r["path"] == path]


@pytest.fixture()
def fake(js, monkeypatch, tmp_path):
    server = FakeServer()
    project = tmp_path / "project"
    project.mkdir()
    server.routes[("GET", "/api/project")] = {
        "container_path": "/mnt/project",
        "host_path": str(project),
        "name": "project",
    }
    monkeypatch.setenv("TIT_SERVER_URL", server.url)
    monkeypatch.setenv("TIT_SERVER_TOKEN", TOKEN)
    server.project = project
    yield server
    server.httpd.shutdown()


# ---------------------------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------------------------


def test_connect_uses_env_and_never_returns_the_token(js, fake):
    fake.routes[("GET", "/api/catalog/subjects")] = {
        "subjects": [{"id": "101", "has_raw": True, "has_m2m": False}]
    }
    fake.routes[("GET", "/api/jobs")] = [
        {"id": "j1", "kind": "pre", "state": "running", "subject_ids": ["101"]},
        {"id": "j0", "kind": "sim", "state": "succeeded", "subject_ids": ["101"]},
    ]
    fake.routes[("GET", "/api/settings")] = {"agent_auto_submit": False}
    err, out = call(js, "connect")
    assert not err, out
    assert out["project"]["host_path"] == str(fake.project)
    assert out["subjects"][0]["id"] == "101"
    assert [j["id"] for j in out["active_jobs"]] == ["j1"]
    assert out["approval_required"] is True and "propose_pipeline" in out["next"]
    assert TOKEN not in json.dumps(out)
    assert {r["auth"] for r in fake.requests} == {f"Bearer {TOKEN}"}
    # An app from before proposals has no such setting and no approval step.
    fake.routes[("GET", "/api/settings")] = {"theme": "system"}
    assert call(js, "connect")[1]["approval_required"] is False


def _docker(monkeypatch, js, containers):
    """Answer `docker ps` / `docker inspect` the way Docker does for *containers*."""

    class Done:
        def __init__(self, stdout):
            self.returncode, self.stdout, self.stderr = 0, stdout, ""

    def run(argv, **kwargs):
        if argv[1] == "ps":
            assert f"label=tit.stack={js.STACK_ID}" in argv
            return Done("".join(c["Id"] + "\n" for c in containers))
        return Done(json.dumps(containers))

    monkeypatch.delenv("TIT_SERVER_URL", raising=False)
    monkeypatch.delenv("TIT_SERVER_TOKEN", raising=False)
    monkeypatch.setattr(js.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(js.subprocess, "run", run)


def _container(cid, port, host_dir):
    return {
        "Id": cid,
        "Config": {
            "Env": [f"TIT_SERVER_TOKEN=tok-{cid}", f"TIT_SERVER_PORT={port}", "X=1"],
            "Labels": {
                "tit.stack": "ti-toolbox-v3",
                "tit.service": "tit",
                "tit.host_project_dir": host_dir,
            },
        },
    }


def test_discovery_reads_the_running_container(js, monkeypatch, tmp_path):
    _docker(monkeypatch, js, [_container("c1", 8790, str(tmp_path))])
    conn = js._discover()
    assert conn == {
        "origin": "http://127.0.0.1:8790",
        "token": "tok-c1",
        "host_project": str(tmp_path),
    }


def test_discovery_asks_which_project_when_several_are_open(js, monkeypatch, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    _docker(
        monkeypatch,
        js,
        [_container("c1", 8790, str(a)), _container("c2", 8791, str(b))],
    )
    with pytest.raises(js.ToolError, match="project="):
        js._discover()
    assert js._discover(str(b))["origin"] == "http://127.0.0.1:8791"


def test_no_stack_says_how_to_start_one(js, monkeypatch):
    _docker(monkeypatch, js, [])
    err, text = call(js, "connect")
    assert err and "open the ti-toolbox desktop app" in text.lower()


# ---------------------------------------------------------------------------------------------
# find_regions
# ---------------------------------------------------------------------------------------------


LAB = "/mnt/project/derivatives/SimNIBS/sub-101/m2m_101/segmentation/labeling.nii.gz"
#: GET /api/catalog/regions's answer for "thalamus" (tit.catalog.find_regions, whose search and
#: ROI construction are pinned in tests/test_region_rois.py).
THALAMUS = [
    {
        "atlas": "labeling.nii.gz",
        "kind": "volume",
        "matches": [
            {"id": 10, "name": "Left-Thalamus", "hemi": None, "side": "left"},
            {"id": 49, "name": "Right-Thalamus", "hemi": None, "side": "right"},
        ],
        "rois": {
            "all": {
                "_type": "SubcorticalROI",
                "atlas_path": [LAB, LAB],
                "label": [10, 49],
                "tissues": "GM",
                "atlas_space": "subject",
            },
        },
    }
]


def test_find_regions_passes_the_servers_answer_through(js, fake):
    fake.routes[("GET", "/api/catalog/regions")] = THALAMUS
    err, out = call(js, "find_regions", subject_id="101", query="bilateral thalamus")
    assert not err, out
    assert out["atlases"] == THALAMUS
    assert fake.sent("GET", "/api/catalog/regions")[0]["query"] == {
        "subject": "101",
        "q": "bilateral thalamus",
    }
    fake.routes[("GET", "/api/catalog/regions")] = []
    err, text = call(js, "find_regions", subject_id="101", query="amygdala")
    assert err and "no region" in text


# ---------------------------------------------------------------------------------------------
# plan / submit / wait
# ---------------------------------------------------------------------------------------------

ROI = {
    "_type": "SubcorticalROI",
    "atlas_path": ["/a.nii.gz"],
    "label": [10],
    "tissues": "GM",
}
FLEX_ROOT = "/mnt/project/derivatives/SimNIBS/sub-101/flex-search"


def _plan_routes(fake, will_overwrite=False):
    fake.routes[("POST", "/api/validate/flex")] = {"ok": True, "errors": []}
    fake.routes[("POST", "/api/validate/sim")] = {"ok": True, "errors": []}
    fake.routes[("POST", "/api/jobs/preflight")] = {"missing": []}

    def plan(query, body):
        config = body["config"]
        out = config.get("output_folder") or f"{FLEX_ROOT}/20261007_000000"
        if config.get("montages"):
            out = f"/mnt/project/.../Simulations/{config['montages'][0]['name']}"
        job = {
            "kind": "flex",
            "subject": body["subject_ids"][0],
            "output_dir": out,
            "exists": will_overwrite,
            "will_overwrite": will_overwrite,
        }
        return 200, {
            "jobs": [job],
            "lock_conflicts": [],
            "cost": {"cpus": 1, "mem_gb": 2, "eta_minutes": 12.5},
            "warnings": [],
        }

    fake.routes[("POST", "/api/plan/flex")] = plan
    fake.routes[("POST", "/api/plan/sim")] = plan


def test_plan_job_sends_the_agents_fields_and_names_the_run_folder(js, fake):
    _plan_routes(fake)
    err, out = call(
        js,
        "plan_job",
        kind="flex",
        config={"roi": ROI, "current_mA": 2.0, "output_folder": "thalamus_max"},
        subject_ids=["101"],
    )
    assert not err, out
    assert out["ok"] and out["eta_minutes"] == 12.5
    # Only what the agent chose: the server fills the app's defaults for created_by "agent".
    sent = fake.sent("POST", "/api/validate/flex")[0]["body"]
    assert sent == {
        "config": {
            "roi": ROI,
            "current_mA": 2.0,
            "output_folder": f"{FLEX_ROOT}/thalamus_max",
            "subject_id": "101",
        },
        "created_by": "agent",
    }
    for path in ("/api/jobs/preflight", "/api/plan/flex"):
        assert {r["body"]["created_by"] for r in fake.sent("POST", path)} == {"agent"}
    probe = fake.sent("POST", "/api/plan/flex")[0]["body"]["config"]
    assert probe["output_folder"] is None


def test_plan_job_reports_what_would_be_overwritten(js, fake):
    _plan_routes(fake, will_overwrite=True)
    err, out = call(
        js, "plan_job", kind="flex", config={"roi": ROI}, subject_ids=["101"]
    )
    assert not err
    assert out["will_overwrite"] and "ask the user" in out["next"]


def test_submit_job_uses_the_group_route_like_the_app(js, fake):
    fake.routes[("POST", "/api/jobs/groups")] = lambda q, b: (
        201,
        {
            "group_id": "g1",
            "jobs": [
                {"id": f"j{i}", "kind": "sim", "state": "queued", "subject_ids": [s]}
                for i, s in enumerate(b["subject_ids"])
            ],
        },
    )
    montage = {
        "_type": "Montage",
        "name": "m",
        "mode": "net",
        "electrode_pairs": [["a", "b"]],
    }
    err, out = call(
        js,
        "submit_job",
        kind="sim",
        config={"montages": [montage], "subject_id": "999"},
        subject_ids=["101", "102"],
    )
    assert not err, out
    assert out["job_ids"] == ["j0", "j1"]
    body = fake.sent("POST", "/api/jobs/groups")[0]["body"]
    assert body["created_by"] == "agent"
    assert body["tags"] == ["sim-batch"]
    assert [e["subject_id"] for e in body["subject_configs"]] == ["101", "102"]
    assert [e["config"]["subject_id"] for e in body["subject_configs"]] == [
        "101",
        "102",
    ]
    # The server fills the app's defaults.
    assert "map_to_fsavg" not in body["subject_configs"][0]["config"]
    assert "overwrite" not in body


def test_submit_preprocess_is_one_group(js, fake):
    fake.routes[("POST", "/api/jobs/groups")] = {"group_id": "g", "jobs": []}
    err, out = call(
        js,
        "submit_job",
        kind="pre",
        config={"run_fastsurfer": False},
        subject_ids=["101"],
    )
    assert not err, out
    body = fake.sent("POST", "/api/jobs/groups")[0]["body"]
    assert body["subject_ids"] == ["101"] and body["created_by"] == "agent"
    assert body["config"] == {"run_fastsurfer": False, "subject_ids": ["101"]}
    assert "subject_configs" not in body
    err, text = call(
        js, "submit_job", kind="pre", config={}, subject_ids=["101"], after=["j1"]
    )
    assert err and "cannot wait" in text


def test_submit_job_with_after_uses_single_jobs(js, fake):
    fake.routes[("POST", "/api/jobs")] = lambda q, b: (
        201,
        {
            "id": "j9",
            "kind": b["kind"],
            "state": "queued",
            "subject_ids": b["subject_ids"],
        },
    )
    err, out = call(
        js,
        "submit_job",
        kind="analyzer",
        config={"x": 1},
        subject_ids=["101"],
        after=["j1"],
        overwrite=True,
    )
    assert not err, out
    body = fake.sent("POST", "/api/jobs")[0]["body"]
    assert body == {
        "kind": "analyzer",
        "config": {"x": 1, "subject_id": "101"},
        "subject_ids": ["101"],
        "created_by": "agent",
        "after": ["j1"],
        "overwrite": True,
    }


def test_wait_for_job_returns_log_and_outputs_once_finished(js, fake):
    states = iter(["queued", "running", "succeeded"])
    fake.routes[("GET", "/api/jobs/j1")] = lambda q, b: (
        200,
        {"spec": {}, "status": {"id": "j1", "kind": "sim", "state": next(states)}},
    )
    fake.routes[("GET", "/api/jobs/j1/log")] = "line1\nline2\n"
    fake.routes[("GET", "/api/jobs/j1/artifacts")] = {
        "folder": "/mnt/project/sim",
        "files": [{"path": "/mnt/project/sim/a.msh", "kind": "mesh", "label": "a.msh"}],
    }
    err, out = call(js, "wait_for_job", job_ids=["j1"], timeout_s=5)
    assert not err, out
    assert out["done"]
    [job] = out["jobs"]
    assert job["state"] == "succeeded"
    assert job["log_tail"] == ["line1", "line2"]
    assert job["output_folder"] == "/mnt/project/sim"


def test_wait_for_job_times_out_without_failing(js, fake):
    fake.routes[("GET", "/api/jobs/j1")] = {
        "status": {"id": "j1", "kind": "pre", "state": "running"}
    }
    err, out = call(js, "wait_for_job", job_ids=["j1"], timeout_s=0)
    assert not err and not out["done"] and "again" in out["next"]


# ---------------------------------------------------------------------------------------------
# flex -> sim
# ---------------------------------------------------------------------------------------------

#: GET /api/sim-from-flex's answer (tit.sim.montage_sources.resolve_flex_simulation, whose
#: run/placement/current rules are pinned in tests/test_flex_simulation_resolver.py).
RESOLVED = {
    "flex_run": "thalamus_max",
    "eeg_net": "GSN-HydroCel-185.csv",
    "placement": "mapped to GSN-HydroCel-185.csv",
    "intensities": [2.0, 2.0],
    "intensities_from": "the run's current_mA per channel",
    "montage": {
        "_type": "Montage",
        "name": "thalamus_max",
        "mode": "flex_mapped",
        "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
        "eeg_net": "GSN-HydroCel-185.csv",
    },
}


def _groups(fake):
    fake.routes[("POST", "/api/jobs/groups")] = lambda q, b: (
        201,
        {"group_id": "g", "jobs": [{"id": "s1", "kind": "sim", "state": "queued"}]},
    )


def test_simulate_flex_result_asks_the_server_and_submits_its_montage(js, fake):
    _plan_routes(fake)
    _groups(fake)
    fake.routes[("GET", "/api/sim-from-flex")] = RESOLVED
    err, out = call(
        js, "simulate_flex_result", subject_id="101", eeg_net="GSN-HydroCel-185"
    )
    assert not err, out
    assert out["submitted"] and out["job_ids"] == ["s1"]
    assert fake.sent("GET", "/api/sim-from-flex")[0]["query"] == {
        "subject": "101",
        "eeg_net": "GSN-HydroCel-185",
    }
    config = fake.sent("POST", "/api/jobs/groups")[0]["body"]["subject_configs"][0][
        "config"
    ]
    assert config["montages"] == [RESOLVED["montage"]]
    assert config["intensities"] == [2.0, 2.0]
    assert config["subject_id"] == "101"
    assert out["intensities_from"] == RESOLVED["intensities_from"]


def test_simulate_flex_result_given_currents_win_and_dry_run_submits_nothing(js, fake):
    _plan_routes(fake)
    _groups(fake)
    fake.routes[("GET", "/api/sim-from-flex")] = RESOLVED
    err, out = call(
        js,
        "simulate_flex_result",
        subject_id="101",
        flex_run="thalamus_max",
        intensities=[1.5, 0.5],
        dry_run=True,
    )
    assert not err and not out["submitted"]
    assert out["intensities_mA"] == [1.5, 0.5] and out["intensities_from"] == "given"
    sent = fake.sent("POST", "/api/validate/sim")[0]["body"]["config"]
    assert sent["intensities"] == [1.5, 0.5]
    assert fake.sent("POST", "/api/jobs/groups") == []


def test_simulate_flex_result_will_not_overwrite_unasked(js, fake):
    _plan_routes(fake, will_overwrite=True)
    _groups(fake)
    fake.routes[("GET", "/api/sim-from-flex")] = RESOLVED
    err, out = call(js, "simulate_flex_result", subject_id="101")
    assert not err and not out["submitted"]
    assert fake.sent("POST", "/api/jobs/groups") == []


# ---------------------------------------------------------------------------------------------
# proposals
# ---------------------------------------------------------------------------------------------


def _proposal(state="pending", note=None, edited_config=None):
    proposed = {
        "id": "opt",
        "kind": "flex",
        "config": {"goal": "mean"},
        "subject_ids": ["101"],
        "after": [],
        "overwrite": False,
    }
    step = {
        **proposed,
        "config": edited_config or proposed["config"],
        "state": "queued" if state == "approved" else "proposed",
        "job_ids": ["j1"] if state == "approved" else [],
        "plan": {"outputs": [{"output_dir": "/p/flex/run"}], "eta_minutes": 30.0},
    }
    return {
        "id": "abcdef0123456789",
        "title": "Optimise",
        "status": "running" if state == "approved" else state,
        "decision": {"state": state, "at": None, "note": note},
        "steps": [step],
        "proposed_steps": [proposed],
        "edited": edited_config is not None,
    }


def test_propose_pipeline_dry_runs_then_creates(js, fake):
    js.handle(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {"clientInfo": {"name": "claude-code", "version": "2"}},
        }
    )
    fake.routes[("POST", "/api/proposals")] = lambda q, b: (201, _proposal())
    err, out = call(
        js,
        "propose_pipeline",
        title="Optimise for the thalamus",
        rationale="you asked for the strongest field",
        steps=[
            {
                "id": "opt",
                "kind": "flex",
                "config": {"goal": "mean"},
                "subject_ids": ["101"],
            },
            {
                "id": "sim",
                "kind": "sim_from_flex",
                "config": {"flex_step": "opt"},
                "subject_ids": ["101"],
            },
        ],
    )
    assert not err, out
    assert out["proposed"] and out["proposal_id"] == "abcdef0123456789"
    assert "watch_proposal" in out["next"] and "background" in out["next"]
    dry, real = [r["body"] for r in fake.sent("POST", "/api/proposals")]
    assert dry["dry_run"] is True and "dry_run" not in real
    assert real["created_by"] == "agent" and real["client"] == "Claude Code"
    # As the agent wrote them: the server fills the app's defaults.
    flex, sim = real["steps"]
    assert flex["config"] == {"goal": "mean"}
    assert sim["config"] == {"flex_step": "opt"}


def test_propose_pipeline_names_a_target_find_regions_returned(js, fake):
    fake.routes[("GET", "/api/catalog/regions")] = THALAMUS
    fake.routes[("POST", "/api/proposals")] = lambda q, b: (201, _proposal())
    roi = call(js, "find_regions", subject_id="101", query="thalamus")[1]["atlases"][0][
        "rois"
    ]["all"]
    steps = [
        {"id": "opt", "kind": "flex", "config": {"roi": roi}, "subject_ids": ["101"]}
    ]
    assert not call(js, "propose_pipeline", title="t", rationale="r", steps=steps)[0]
    sent = fake.sent("POST", "/api/proposals")[-1]["body"]["steps"][0]
    assert sent["note"] == "Target: Left-Thalamus, Right-Thalamus"
    # The agent's own note wins.
    steps[0]["note"] = "both thalami"
    call(js, "propose_pipeline", title="t", rationale="r", steps=steps)
    assert fake.sent("POST", "/api/proposals")[-1]["body"]["steps"][0]["note"] == (
        "both thalami"
    )


def test_propose_pipeline_with_errors_shows_the_user_nothing(js, fake):
    bad = _proposal()
    bad["steps"][0]["plan"] = {"errors": ["roi: missing"]}
    fake.routes[("POST", "/api/proposals")] = lambda q, b: (201, bad)
    err, out = call(
        js,
        "propose_pipeline",
        title="t",
        rationale="r",
        steps=[{"id": "opt", "kind": "flex", "config": {}, "subject_ids": ["101"]}],
    )
    assert not err and out["proposed"] is False
    assert out["steps"][0]["errors"] == ["roi: missing"]
    assert len(fake.sent("POST", "/api/proposals")) == 1  # the dry run only


def test_watch_proposal_reports_a_rejection_with_the_users_note(js, fake):
    answers = iter([_proposal(), _proposal("rejected", note="use the left side")])
    fake.routes[("GET", "/api/proposals/abcdef0123456789")] = lambda q, b: (
        200,
        next(answers),
    )
    err, out = call(js, "watch_proposal", proposal_id="abcdef0123456789", timeout_s=5)
    assert not err, out
    assert out["changed"] and out["done"] and out["events"] == ["rejected"]
    assert out["note"] == "use the left side" and "unchanged" in out["next"]


def test_watch_proposal_returns_once_per_change_until_done(js, fake):
    """pending -> approved (edited) -> step running (no change) -> step succeeded (done)."""
    route = ("GET", "/api/proposals/abcdef0123456789")
    pid = "abcdef0123456789"
    fake.routes[route] = _proposal()
    err, out = call(js, "watch_proposal", proposal_id=pid, timeout_s=0)
    assert not err and not out["changed"] and out["decision"] == "pending"
    assert "Say nothing" in out["next"]

    fake.routes[route] = _proposal("approved", edited_config={"goal": "max"})
    err, out = call(js, "watch_proposal", proposal_id=pid, timeout_s=5)
    assert not err, out
    assert out["events"] == ["approved"] and out["edited_by_user"] is True
    [step] = out["steps"]
    assert step["edited"] and step["approved_config"] == {"goal": "max"}
    assert step["job_ids"] == ["j1"] and not out["done"]

    # The decision was reported, so the same proposal is no longer a change.
    err, out = call(js, "watch_proposal", proposal_id=pid, timeout_s=0)
    assert not err and not out["changed"] and out["events"] == []

    finished = _proposal("approved")
    finished["status"] = "succeeded"
    finished["steps"][0]["state"] = "succeeded"
    fake.routes[route] = finished
    fake.routes[("GET", "/api/jobs/j1")] = {
        "status": {"id": "j1", "kind": "flex", "state": "succeeded"}
    }
    fake.routes[("GET", "/api/jobs/j1/log")] = "best mean field 0.365 V/m\n"
    fake.routes[("GET", "/api/jobs/j1/artifacts")] = {
        "folder": "/p/flex/run",
        "files": [{"path": "/p/flex/run/report.html", "kind": "report", "label": "r"}],
    }
    err, out = call(js, "watch_proposal", proposal_id=pid, timeout_s=5)
    assert not err, out
    assert out["events"] == ["step opt succeeded"] and out["done"]
    [done] = out["finished"]
    [job] = done["jobs"]
    assert job["output_folder"] == "/p/flex/run"
    assert job["log_tail"] == ["best mean field 0.365 V/m"]
    assert "final summary" in out["next"]


def _initialize(js, client):
    js.handle(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {"clientInfo": {"name": client, "version": "1"}},
        }
    )


@pytest.mark.parametrize(
    "client, args, budget",
    [
        ("claude-code", {}, 1500.0),  # the client backgrounds it, so it may wait long
        ("codex-mcp-client", {}, 45.0),  # under Codex's 60 s per-tool timeout
        ("claude-code", {"timeout_s": 99999}, 1500.0),
        ("codex-mcp-client", {"timeout_s": -3}, 0.0),
    ],
)
def test_wait_budget_follows_the_client(js, client, args, budget):
    _initialize(js, client)
    assert js._wait_budget(args) == budget


def test_codex_is_told_to_end_the_turn_and_offer_status(js, fake):
    _initialize(js, "codex-mcp-client")
    fake.routes[("GET", "/api/proposals/abcdef0123456789")] = _proposal()
    err, out = call(js, "watch_proposal", proposal_id="abcdef0123456789", timeout_s=0)
    assert not err and "'status'" in out["next"] and "timeout_s=0" in out["next"]


def test_get_proposal_summarises_steps(js, fake):
    fake.routes[("GET", "/api/proposals/abcdef0123456789")] = _proposal("approved")
    err, out = call(js, "get_proposal", proposal_id="abcdef0123456789")
    assert not err, out
    assert out["status"] == "running"
    assert out["steps"][0]["state"] == "queued"
    assert out["steps"][0]["output_dirs"] == ["/p/flex/run"]


# ---------------------------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------------------------


def test_every_tool_declares_honest_annotations(js):
    tools = js.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"][
        "tools"
    ]
    hints = {t["name"]: t["annotations"] for t in tools}
    assert len(hints) == 11
    read_only = {n for n, h in hints.items() if h["readOnlyHint"]}
    assert read_only == {
        "connect",
        "find_regions",
        "get_config_schema",
        "plan_job",
        "wait_for_job",
        "watch_proposal",
        "get_proposal",
    }
    assert {n for n, h in hints.items() if h.get("destructiveHint")} == {
        "submit_job",
        "cancel_job",
        "simulate_flex_result",
    }
    assert all(t["inputSchema"]["type"] == "object" for t in tools)


def test_a_waiting_watch_never_holds_up_other_calls_and_stops_on_cancel(fake):
    """Over the real stdio entry point. Claude Code sends the agent's next call while a
    backgrounded one still runs (seen with a stub server under claude 2.1.294, 2026-10-08),
    so a pending watch must not block get_proposal; notifications/cancelled (TaskStop) ends it;
    progress goes to the token the client sent."""
    import os
    import subprocess
    import sys
    import time

    fake.routes[("GET", "/api/proposals/abcdef0123456789")] = _proposal()
    proc = subprocess.Popen(
        [sys.executable, str(JOBS_SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env={
            **os.environ,
            "TIT_SERVER_URL": fake.url,
            "TIT_SERVER_TOKEN": TOKEN,
            "TIT_AGENT_POLL_S": "0.05",
        },
    )

    def send(msg):
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()

    def read():
        return json.loads(proc.stdout.readline())

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "claude-code", "version": "2"}},
            }
        )
        assert read()["id"] == 1
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "watch_proposal",
                    "arguments": {"proposal_id": "abcdef0123456789"},
                    "_meta": {"progressToken": "tok-2"},
                },
            }
        )
        progress = read()  # the watch's first poll
        assert progress["method"] == "notifications/progress"
        assert progress["params"]["progressToken"] == "tok-2"
        assert progress["params"]["message"].startswith("pending")
        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_proposal",
                    "arguments": {"proposal_id": "abcdef0123456789"},
                },
            }
        )
        assert read()["id"] == 3  # answered while the watch still waits
        started = time.monotonic()
        send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 2},
            }
        )
        watch = read()
        assert watch["id"] == 2 and time.monotonic() - started < 5
        assert json.loads(watch["result"]["content"][0]["text"])["changed"] is False
    finally:
        proc.kill()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------------------------
# against the real server
# ---------------------------------------------------------------------------------------------


def test_against_the_real_server_jobs_are_recorded_as_agent(js, monkeypatch, tmp_path):
    """Over HTTP to the real FastAPI app: connect -> plan_job -> submit_job refused ->
    propose_pipeline -> the user approves -> the server queues it -> wait_for_job; then, with
    direct submissions allowed, submit_job -> wait_for_job."""
    pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    import os
    import sys
    import time
    import urllib.request

    from tit.jobs import bootstrap
    from tit.jobs.manager import JobManager
    from tit.jobs.registry import spec_path
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
    eeg = Path(pm.eeg_positions("101"))
    eeg.mkdir(parents=True)
    (eeg / "GSN-HydroCel-185.csv").write_text(
        "".join(f"Electrode,{i},0,0,E{i}\n" for i in range(1, 5))
    )
    fake_runner = str(REPO / "tests" / "fake_runner.py")
    manager = JobManager(
        str(project),
        runner_cwd=str(project),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, spec_file: [
            sys.executable,
            fake_runner,
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

        err, out = call(js, "connect")
        assert not err, out
        assert [s["id"] for s in out["subjects"]] == ["101"]
        assert out["approval_required"] is True  # the default
        err, schema = call(js, "get_config_schema", kind="flex_adaptive")
        assert not err and schema["class"] == "FlexConfig"
        # The Optimizer page's values (tit/server/app_defaults.py), served in /api/schema.
        assert schema["app_defaults_filled_in"]["goal"] == "focality"
        assert schema["app_defaults_filled_in"]["max_iterations"] == 500

        montage = {
            "_type": "Montage",
            "name": "m1",
            "mode": "net",
            "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
            "eeg_net": "GSN-HydroCel-185.csv",
        }
        args = {
            "kind": "sim",
            "config": {"montages": [montage]},
            "subject_ids": ["101"],
        }
        err, plan = call(js, "plan_job", **args)
        assert not err, plan
        assert plan["ok"] and plan["jobs"][0]["output_dir"].endswith(
            os.path.join("Simulations", "m1")
        )

        # Approval required: a direct submission is refused and names the way forward.
        err, text = call(js, "submit_job", **args)
        assert err and "HTTP 403" in text and "propose_pipeline" in text

        err, proposed = call(
            js,
            "propose_pipeline",
            title="Simulate m1",
            rationale="the user asked",
            steps=[{"id": "sim", **args}],
        )
        assert not err and proposed["proposed"], proposed
        pid = proposed["proposal_id"]
        err, waiting = call(js, "watch_proposal", proposal_id=pid, timeout_s=0)
        assert not err and waiting["decision"] == "pending" and not waiting["changed"]

        def as_user(method, path, body=None):  # what the app's Approve button sends
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

        as_user("POST", f"/api/proposals/{pid}/approve", {})
        err, approved = call(js, "watch_proposal", proposal_id=pid, timeout_s=5)
        assert not err and approved["events"] == ["approved"], approved
        [job_id] = approved["steps"][0]["job_ids"]

        err, done = call(js, "wait_for_job", job_ids=[job_id], timeout_s=20)
        assert not err, done
        assert done["done"] and done["jobs"][0]["state"] == "succeeded"
        spec = json.loads(Path(spec_path(str(project), job_id)).read_text())
        assert spec["created_by"] == "agent"
        assert spec["tags"] == [f"proposal:{pid}"]
        assert (
            spec["config"]["map_to_fsavg"] is False
        )  # the app default the server filled
        err, status = call(js, "get_proposal", proposal_id=pid)
        assert not err and status["status"] == "succeeded", status

        # The user allows direct submissions: submit_job goes straight to the queue.
        as_user(
            "PUT",
            "/api/settings",
            {"panels": [], "theme": "system", "agent_auto_submit": True},
        )
        err, sub = call(js, "submit_job", **{**args, "overwrite": True})
        assert not err, sub
        assert sub["group_id"]
        err, done = call(js, "wait_for_job", job_ids=sub["job_ids"], timeout_s=20)
        assert not err and done["jobs"][0]["state"] == "succeeded", done
        spec = json.loads(Path(spec_path(str(project), sub["job_ids"][0])).read_text())
        assert spec["config"]["map_to_fsavg"] is False  # filled for created_by "agent"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        bootstrap.reset_manager()


def test_propose_pipeline_reports_the_lock_waits_its_dry_run_found(js, fake):
    """Like plan_job, the agent hears which running job a step would queue behind."""
    held = {"key": "subject:101:flex:write", "held_by": "j1", "kind": "flex"}
    waiting = _proposal()
    waiting["steps"][0]["plan"] = {
        **waiting["steps"][0]["plan"],
        "lock_conflicts": [held],
    }
    fake.routes[("POST", "/api/proposals")] = lambda q, b: (201, waiting)
    err, out = call(
        js,
        "propose_pipeline",
        title="t",
        rationale="r",
        steps=[{"id": "opt", "kind": "flex", "config": {}, "subject_ids": ["101"]}],
    )
    assert not err and out["proposed"]
    assert out["steps"][0]["lock_conflicts"] == [held]
