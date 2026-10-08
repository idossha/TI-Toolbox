"""Tests for the agent plugin's job driver (agent-plugin/mcp/jobs_server.py), 2026-10-07.

What this pins: discovery (env first, then the `tit.stack=ti-toolbox-v3` container, one project
at a time), the request each verb sends to tit.server, host-side staging that copies and never
overwrites or escapes `sourcedata/sub-<id>/`, the ROI objects find_regions builds, and the
flex-result -> simulation chain.

Where the expected values come from: request shapes are the routes' own contracts
(contracts/openapi.yaml JobSpec/JobGroupRequest, PlanRequest, MontageSources) and the desktop's
builders (pages/_shared/roi/types.ts roiToConfig, pages/simulator/buildConfig.ts), restated by
hand (groundTruth: authored). The DICOM fixtures are hand-built Part-10 bytes per DICOM PS3.10
(preamble, "DICM", explicit- and implicit-VR elements), not written by the reader under test.
The last test drives the real FastAPI app (fake runner) over HTTP, so the wire shapes are also
checked against the server rather than against this file's fake.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_jobs.py -q
Deliberately elsewhere: created_by on the routes themselves (tests/test_jobs_routes.py); the
MCP stdio framing shared with server.py (agent-plugin/mcp/test_stdio.py).
"""

from __future__ import annotations

import importlib.util
import json
import struct
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
    err, out = call(js, "connect")
    assert not err, out
    assert out["project"]["host_path"] == str(fake.project)
    assert out["subjects"][0]["id"] == "101"
    assert [j["id"] for j in out["active_jobs"]] == ["j1"]
    assert TOKEN not in json.dumps(out)
    assert {r["auth"] for r in fake.requests} == {f"Bearer {TOKEN}"}


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
# raw data
# ---------------------------------------------------------------------------------------------


def _dicom(path: Path, description: str, *, explicit=True, modality="MR"):
    """Part-10 bytes: 128-byte preamble, DICM, then (0008,0060) and (0008,103E) elements."""

    def element(group, elem, vr, value):
        value = value.encode() + (b" " if len(value) % 2 else b"")
        tag = struct.pack("<HH", group, elem)
        if explicit:
            return tag + vr + struct.pack("<H", len(value)) + value
        return tag + struct.pack("<I", len(value)) + value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\0" * 128
        + b"DICM"
        + element(0x0008, 0x0060, b"CS", modality)
        + element(0x0008, 0x103E, b"LO", description)
    )


def test_inspect_raw_data_guesses_modalities(js, tmp_path):
    raw = tmp_path / "scan"
    for i in range(3):
        _dicom(raw / "s002" / f"IM{i:04d}", "T1_MPRAGE_SAG_1mm")
    _dicom(raw / "s005" / "IM0001", "ep2d_diff_mddw_64", explicit=False)
    _dicom(raw / "s001" / "IM0001", "AAHead_Scout")
    _dicom(raw / "ct" / "1.dcm", "Head 1.0", modality="CT")
    (raw / "nifti").mkdir()
    (raw / "nifti" / "sub-01_T2w.nii.gz").write_bytes(b"x")
    (raw / "s002" / "._IM0000").write_bytes(b"appledouble")

    err, out = call(js, "inspect_raw_data", path=str(raw))
    assert not err, out
    assert out["proposed_mapping"] == {
        "T1w": [str(raw.resolve() / "s002")],
        "ct": [str(raw.resolve() / "ct")],
        "dwi": [str(raw.resolve() / "s005")],
        "T2w": [str(raw.resolve() / "nifti" / "sub-01_T2w.nii.gz")],
    }
    by_source = {e["source"]: e for e in out["entries"]}
    assert by_source[str(raw.resolve() / "s002")]["series"] == ["T1_MPRAGE_SAG_1mm"]
    assert by_source[str(raw.resolve() / "s002")]["files"] == 3  # dotfiles ignored
    assert by_source[str(raw.resolve() / "s001")]["guess"] is None


def test_stage_copies_with_sidecars_and_refuses_to_overwrite(js, fake, tmp_path):
    raw = tmp_path / "raw"
    for i in range(2):
        _dicom(raw / "T1_series" / f"IM{i}", "T1_MPRAGE")
    (raw / "dwi.nii.gz").write_bytes(b"dwi")
    (raw / "dwi.bval").write_text("0 1000")
    (raw / "dwi.bvec").write_text("0 1")
    mapping = {"T1w": [str(raw / "T1_series")], "DWI": str(raw / "dwi.nii.gz")}

    err, out = call(js, "stage_raw_data", subject_id="101", mapping=mapping)
    assert not err, out
    sub = fake.project / "sourcedata" / "sub-101"
    assert sorted(
        p.relative_to(sub).as_posix() for p in sub.rglob("*") if p.is_file()
    ) == [
        "T1w/T1_series/IM0",
        "T1w/T1_series/IM1",
        "dwi/dwi.bval",
        "dwi/dwi.bvec",
        "dwi/dwi.nii.gz",
    ]
    assert (raw / "dwi.nii.gz").exists()  # copied, not moved

    (raw / "T2.nii").write_bytes(b"t2")
    err, text = call(
        js,
        "stage_raw_data",
        subject_id="101",
        mapping={**mapping, "T2w": [str(raw / "T2.nii")]},
    )
    assert err and "already exists" in text
    assert not (sub / "T2w").exists()  # nothing copied when any target exists


@pytest.mark.parametrize(
    "subject_id, mapping, message",
    [
        ("../evil", {"T1w": ["/tmp"]}, "invalid subject id"),
        ("101", {"flair": ["/tmp"]}, "unknown modality"),
        ("101", {"T1w": ["relative/path"]}, "absolute"),
    ],
)
def test_stage_rejects_bad_input(js, fake, subject_id, mapping, message):
    err, text = call(js, "stage_raw_data", subject_id=subject_id, mapping=mapping)
    assert err and message in text
    assert not (fake.project / "sourcedata").exists()


def test_stage_refuses_a_path_that_escapes_the_subject_folder(js, fake, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (fake.project / "sourcedata" / "sub-101").mkdir(parents=True)
    (fake.project / "sourcedata" / "sub-101" / "T1w").symlink_to(outside)
    src = tmp_path / "t1.nii.gz"
    src.write_bytes(b"t1")
    err, text = call(
        js, "stage_raw_data", subject_id="101", mapping={"T1w": [str(src)]}
    )
    assert err and "outside" in text
    assert list(outside.iterdir()) == []


# ---------------------------------------------------------------------------------------------
# find_regions
# ---------------------------------------------------------------------------------------------


def test_find_regions_builds_the_desktops_roi_objects(js, fake):
    lab = (
        "/mnt/project/derivatives/SimNIBS/sub-101/m2m_101/segmentation/labeling.nii.gz"
    )
    annot = "/mnt/project/derivatives/SimNIBS/sub-101/m2m_101/segmentation/lh.101_DK40.annot"
    fake.routes[("GET", "/api/catalog/atlases")] = [
        {"id": "labeling.nii.gz", "path": lab, "kind": "volume"},
        {"id": "DK40", "path": annot, "kind": "surface"},
    ]
    regions = {
        "labeling.nii.gz": [
            {"id": 10, "name": "Left-Thalamus", "hemi": None},
            {"id": 49, "name": "Right-Thalamus", "hemi": None},
            {"id": 17, "name": "Left-Hippocampus", "hemi": None},
        ],
        "DK40": [
            {"id": 24, "name": "precentral", "hemi": "lh"},
            {"id": 24, "name": "precentral", "hemi": "rh"},
        ],
    }
    fake.routes[("GET", "/api/catalog/atlases/regions")] = lambda q, b: (
        200,
        regions[q["atlas"]],
    )

    err, out = call(js, "find_regions", subject_id="101", query="bilateral thalamus")
    assert not err, out
    [hit] = out["atlases"]
    assert hit["rois"]["all"] == {
        "_type": "SubcorticalROI",
        "atlas_path": [lab, lab],
        "label": [10, 49],
        "tissues": "GM",
        "atlas_space": "subject",
    }
    assert hit["rois"]["left"]["label"] == [10]
    assert hit["rois"]["right"]["label"] == [49]

    err, out = call(js, "find_regions", subject_id="101", query="precentral")
    [hit] = out["atlases"]
    assert hit["rois"]["all"] == {
        "_type": "AtlasROI",
        "atlas_path": [annot, annot.replace("/lh.", "/rh.")],
        "label": [24, 24],
        "hemisphere": ["lh", "rh"],
    }

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


def test_plan_job_fills_app_defaults_and_names_the_run_folder(js, fake):
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
    validated = fake.sent("POST", "/api/validate/flex")[0]["body"]["config"]
    assert validated["subject_id"] == "101"
    assert validated["current_mA"] == 2.0  # the agent's value wins
    assert (
        validated["max_iterations"] == 500
    )  # the Optimizer page's default, not the dataclass's
    assert validated["electrode"] == {
        "shape": "ellipse",
        "dimensions": [8, 8],
        "gel_thickness": 4,
    }
    assert validated["output_folder"] == f"{FLEX_ROOT}/thalamus_max"
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
    assert body["subject_configs"][0]["config"]["map_to_fsavg"] is False  # app default
    assert "overwrite" not in body


def test_submit_preprocess_is_one_group_with_the_apps_defaults(js, fake):
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
    assert body["config"]["subject_ids"] == ["101"]
    assert (
        body["config"]["convert_dicom"] and body["config"]["create_m2m"]
    )  # Pre-processing page
    assert body["config"]["run_fastsurfer"] is False  # the agent's choice wins
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

FLEX_RUN = {
    "name": "thalamus_max",
    "created": "2026-10-07T10:00:00",
    "manifest": {"current_mA": 2.0, "current_split": None},
    "mappings": [
        {"eeg_net": "GSN-HydroCel-185.csv", "pairs": [["E1", "E2"], ["E3", "E4"]]}
    ],
    "optimized": [[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [1, 1, 1]]],
}


def _groups(fake):
    fake.routes[("POST", "/api/jobs/groups")] = lambda q, b: (
        201,
        {"group_id": "g", "jobs": [{"id": "s1", "kind": "sim", "state": "queued"}]},
    )


def test_simulate_flex_result_submits_the_mapped_montage_at_the_runs_current(js, fake):
    _plan_routes(fake)
    _groups(fake)
    fake.routes[("GET", "/api/catalog/flex-runs")] = [FLEX_RUN]
    err, out = call(js, "simulate_flex_result", subject_id="101")
    assert not err, out
    assert out["submitted"] and out["job_ids"] == ["s1"]
    config = fake.sent("POST", "/api/jobs/groups")[0]["body"]["subject_configs"][0][
        "config"
    ]
    assert config["montages"] == [
        {
            "_type": "Montage",
            "name": "thalamus_max",
            "mode": "flex_mapped",
            "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
            "eeg_net": "GSN-HydroCel-185.csv",
        }
    ]
    assert config["intensities"] == [2.0, 2.0]
    assert config["subject_id"] == "101"


def test_simulate_flex_result_free_xyz_and_on_demand_mapping(js, fake):
    _plan_routes(fake)
    _groups(fake)
    run = {**FLEX_RUN, "mappings": []}
    fake.routes[("GET", "/api/catalog/flex-runs")] = [run]
    fake.routes[("GET", "/api/catalog/flex-runs/thalamus_max/mapping")] = {
        "eeg_net": "EEG10-10_UI_Jurak_2007.csv",
        "pairs": [["Fz", "Cz"], ["P3", "P4"]],
    }
    err, out = call(js, "simulate_flex_result", subject_id="101", dry_run=True)
    assert not err and not out["submitted"]
    sent = fake.sent("POST", "/api/validate/sim")[0]["body"]["config"]["montages"][0]
    assert sent["mode"] == "flex_free" and sent["eeg_net"] is None

    err, out = call(
        js, "simulate_flex_result", subject_id="101", eeg_net="EEG10-10_UI_Jurak_2007"
    )
    assert not err, out
    asked = fake.sent("GET", "/api/catalog/flex-runs/thalamus_max/mapping")[0]["query"]
    assert asked == {"subject": "101", "eeg_net": "EEG10-10_UI_Jurak_2007.csv"}


def test_simulate_flex_result_will_not_overwrite_unasked(js, fake):
    _plan_routes(fake, will_overwrite=True)
    _groups(fake)
    fake.routes[("GET", "/api/catalog/flex-runs")] = [FLEX_RUN]
    err, out = call(js, "simulate_flex_result", subject_id="101")
    assert not err and not out["submitted"]
    assert fake.sent("POST", "/api/jobs/groups") == []


# ---------------------------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------------------------


def test_every_tool_declares_honest_annotations(js):
    tools = js.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"][
        "tools"
    ]
    hints = {t["name"]: t["annotations"] for t in tools}
    assert len(hints) == 10
    read_only = {n for n, h in hints.items() if h["readOnlyHint"]}
    assert read_only == {
        "connect",
        "inspect_raw_data",
        "find_regions",
        "get_config_schema",
        "plan_job",
        "wait_for_job",
    }
    assert {n for n, h in hints.items() if h.get("destructiveHint")} == {
        "submit_job",
        "cancel_job",
        "simulate_flex_result",
    }
    assert all(t["inputSchema"]["type"] == "object" for t in tools)


# ---------------------------------------------------------------------------------------------
# against the real server
# ---------------------------------------------------------------------------------------------


def test_against_the_real_server_jobs_are_recorded_as_agent(js, monkeypatch, tmp_path):
    """connect -> plan_job -> submit_job -> wait_for_job over HTTP to the real FastAPI app."""
    pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    import os
    import sys
    import time

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

        err, sub = call(js, "submit_job", **args)
        assert not err, sub
        [job_id] = sub["job_ids"]
        assert sub["group_id"]

        err, done = call(js, "wait_for_job", job_ids=[job_id], timeout_s=20)
        assert not err, done
        assert done["done"] and done["jobs"][0]["state"] == "succeeded"
        spec = json.loads(Path(spec_path(str(project), job_id)).read_text())
        assert spec["created_by"] == "agent"
        assert spec["config"]["map_to_fsavg"] is False
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        bootstrap.reset_manager()
