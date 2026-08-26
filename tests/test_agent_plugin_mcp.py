"""Tests for the agent-plugin MCP server (agent-plugin/mcp/server.py).

The server is dependency-free and is exercised both in-process (handler
functions) and end-to-end over stdio as an MCP client would use it.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "agent-plugin" / "mcp" / "server.py"


@pytest.fixture(scope="module")
def srv():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ti_mcp_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.REPO_ROOT == REPO, "server must auto-detect the checkout it lives in"
    return mod


def _call(srv, tool, **args):
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
    )
    res = resp["result"]
    text = res["content"][0]["text"]
    return res["isError"], (json.loads(text) if not res["isError"] else text)


@pytest.fixture
def project(tmp_path):
    """Minimal BIDS/TI-Toolbox project with one complete and one bare subject."""
    root = tmp_path / "proj"
    (root / "sub-101" / "anat").mkdir(parents=True)
    (root / "sub-101" / "anat" / "sub-101_T1w.nii.gz").write_bytes(b"")
    (root / "sub-102").mkdir()
    sn = root / "derivatives" / "SimNIBS" / "sub-101"
    (sn / "m2m_101").mkdir(parents=True)
    (sn / "m2m_101" / "101.msh").write_bytes(b"")
    (sn / "leadfields").mkdir()
    (sn / "leadfields" / "101_leadfield_EEG10-20.hdf5").write_bytes(b"")
    sim = sn / "Simulations" / "L_Insula"
    (sim / "TI" / "mesh").mkdir(parents=True)
    (sim / "TI" / "mesh" / "101_L_Insula_TI.msh").write_bytes(b"")
    (sim / "TI" / "niftis").mkdir()
    (sim / "TI" / "niftis" / "grey_101_L_Insula_TI_max.nii.gz").write_bytes(b"")
    (sim / "Analyses" / "Voxel" / "sphere_x-35_y5_z5_r10").mkdir(parents=True)
    (sn / "flex-search" / "run1").mkdir(parents=True)
    cfg = root / "code" / "ti-toolbox" / "config"
    cfg.mkdir(parents=True)
    (cfg / "montage_list.json").write_text(
        json.dumps(
            {
                "nets": {
                    "GSN-HydroCel-185.csv": {
                        "uni_polar_montages": {"L_Insula": [["E1", "E2"], ["E3", "E4"]]}
                    }
                }
            }
        )
    )
    (root / "derivatives" / "ti-toolbox" / "reports").mkdir(parents=True)
    (root / "derivatives" / "ti-toolbox" / "reports" / "sub-101_sim.html").write_text(
        ""
    )
    return root


class TestWikiTools:
    def test_list_pages_includes_core(self, srv):
        err, out = _call(srv, "list_wiki_pages")
        assert not err
        slugs = {p["slug"] for p in out["pages"]}
        assert {
            "simulator",
            "flex-search",
            "ex-search",
            "analyzer",
            "scripting",
        } <= slugs
        page = next(p for p in out["pages"] if p["slug"] == "flex-search")
        assert page["url"] == "https://idossha.github.io/TI-Toolbox/wiki/flex-search/"

    def test_read_page_and_section(self, srv):
        err, out = _call(srv, "read_wiki_page", page="scripting")
        assert not err and "FlexConfig" in out["content"]
        first = out["headings"][0].lstrip("# ")
        err, sec = _call(srv, "read_wiki_page", page="scripting", section=first)
        assert not err and sec["content"].lstrip("# ").startswith(first)
        assert len(sec["content"]) < len(out["content"])

    def test_read_page_bad_slug(self, srv):
        err, msg = _call(srv, "read_wiki_page", page="../etc/passwd")
        assert err and "Invalid" in msg
        err, msg = _call(srv, "read_wiki_page", page="does-not-exist")
        assert err

    def test_search(self, srv):
        err, out = _call(srv, "search_wiki", query="leadfield", max_results=5)
        assert not err and out["total_matches"] > 0 and len(out["results"]) <= 5
        assert "ex-search" in out["pages_matched"]

    def test_changelog_and_version(self, srv):
        err, v = _call(srv, "get_toolbox_version")
        assert not err and v["version"].count(".") == 2
        err, out = _call(srv, "read_changelog", version=v["version"])
        assert not err and out["version"] == f"v{v['version']}"
        err, out = _call(srv, "read_changelog", max_versions=2)
        assert not err and out["versions_available"][0] == f"v{v['version']}"


class TestSourceTools:
    def test_read_source_with_range(self, srv):
        err, out = _call(
            srv, "read_source_file", path="tit/paths.py", start_line=1, end_line=5
        )
        assert not err and out["content"].count("\n") == 4 and out["total_lines"] > 100

    def test_source_path_restrictions(self, srv):
        for bad in (
            "../secrets",
            "/etc/passwd",
            ".git/config",
            "uv.lock",
            "tit/../pyproject.toml",
        ):
            err, _ = _call(srv, "read_source_file", path=bad)
            assert err, bad

    def test_find_symbol_and_search(self, srv):
        err, out = _call(srv, "find_symbol", name="PathManager")
        assert not err and any(d["path"] == "tit/paths.py" for d in out["definitions"])
        err, out = _call(
            srv, "search_source", pattern=r"def get_path_manager", max_results=3
        )
        assert not err and out["results"]
        err, _ = _call(srv, "search_source", pattern="(")
        assert err

    def test_list_dir(self, srv):
        err, out = _call(srv, "list_source_dir", path="tit")
        assert not err and "paths.py" in out["entries"] and "sim/" in out["entries"]


class TestProjectTools:
    def test_inspect_project(self, srv, project):
        err, out = _call(srv, "inspect_project", project_root=str(project))
        assert not err and out["looks_like_ti_project"]
        by_id = {s["id"]: s for s in out["subjects"]}
        assert set(by_id) == {"101", "102"}
        s = by_id["101"]
        assert s["has_m2m"] and s["has_head_mesh"] and not s["freesurfer_recon"]
        assert s["leadfields"] == ["101_leadfield_EEG10-20.hdf5"]
        assert s["flex_search_runs"] == ["run1"]
        sim = s["simulations"]["L_Insula"]
        assert sim["mesh_files"] == ["101_L_Insula_TI.msh"]
        assert sim["nifti_files"] == ["grey_101_L_Insula_TI_max.nii.gz"]
        assert sim["analyses"] == {"Voxel": ["sphere_x-35_y5_z5_r10"]}
        assert not by_id["102"]["has_m2m"] and by_id["102"]["simulations"] == {}
        assert out["reports"] == ["sub-101_sim.html"]
        assert out["config_files"] == ["montage_list.json"]

    def test_inspect_subject_filter_and_missing(self, srv, project):
        err, out = _call(
            srv, "inspect_project", project_root=str(project), subject="102"
        )
        assert not err and [s["id"] for s in out["subjects"]] == ["102"]
        err, _ = _call(srv, "inspect_project", project_root=str(project / "nope"))
        assert err

    def test_read_project_config(self, srv, project):
        err, out = _call(
            srv,
            "read_project_config",
            project_root=str(project),
            name="montage_list.json",
        )
        assert not err and "GSN-HydroCel-185.csv" in out["content"]["nets"]
        err, _ = _call(
            srv, "read_project_config", project_root=str(project), name="../../x.json"
        )
        assert err


class TestProtocol:
    def test_unknown_tool_and_method(self, srv):
        r = srv.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "nope"},
            }
        )
        assert r["error"]["code"] == -32602
        r = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "bogus"})
        assert r["error"]["code"] == -32601
        assert (
            srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
            is None
        )

    def test_tool_schemas_are_objects(self, srv):
        for t in srv._public_tools():
            assert t["inputSchema"]["type"] == "object" and "handler" not in t

    def test_stdio_roundtrip(self, project):
        msgs = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "inspect_project",
                    "arguments": {"project_root": str(project)},
                },
            },
            "not json",
        ]
        stdin = (
            "\n".join(m if isinstance(m, str) else json.dumps(m) for m in msgs) + "\n"
        )
        env = {**os.environ, "TI_TOOLBOX_OFFLINE": "1"}
        proc = subprocess.run(
            [sys.executable, str(SERVER)],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        out = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
        assert out[0]["result"]["serverInfo"]["name"] == "ti-toolbox"
        assert {t["name"] for t in out[1]["result"]["tools"]} >= {
            "inspect_project",
            "search_wiki",
        }
        assert out[2]["result"]["isError"] is False
        assert out[3]["error"]["code"] == -32700
