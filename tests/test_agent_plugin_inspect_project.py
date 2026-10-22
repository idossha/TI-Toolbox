"""The agent's ``inspect_project`` sees what ``tit.catalog`` and ``PathManager`` see, 2026-10-22.

What this pins: ``agent-plugin/mcp/server.py::tool_inspect_project`` -- the zero-dependency
inspector agents call before diagnosing "my result is missing" -- reports

* an mTI simulation's ``mTI/mesh/<montage>_mTI.msh`` and ``mTI/niftis`` files (it used to
  read only ``TI/``), and
* FastSurfer/FreeSurfer presence, ``has_m2m`` and simulation names exactly as
  ``tit.catalog.list_subjects`` reports them, with every subject the catalog lists (including
  subjects staged only under ``sourcedata/``) and every flex run the catalog lists.

Where the expected values come from: the synthetic project is laid out with ``PathManager``
(``ti_mesh_dir``/``mti_mesh_dir``) and the mTI file name of ``tit/sim/mTI.py``
(``f"{name}_mTI.msh"``, NIfTIs in the sibling ``niftis`` directory per
``tit/sim/utils.py``); the real-data half compares against ``tit.catalog`` run on the same
directory, a second implementation of the same discovery.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_inspect_project.py -q
Real data: export TIT_DATASET_000=/path/to/Dataset000 (read-only; never written).
Deliberately elsewhere: the job-store half of inspect_project (tests/test_agent_plugin_mcp.py).
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "agent-plugin" / "mcp" / "server.py"
DATASET = os.environ.get("TIT_DATASET_000", "")


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("ti_mcp_server_inspect", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def inspect(srv, root: str, **args) -> dict:
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "inspect_project",
                "arguments": {"project_root": root, **args},
            },
        }
    )
    assert resp["result"]["isError"] is False, resp
    return json.loads(resp["result"]["content"][0]["text"])


def _touch(path: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


@pytest.fixture()
def project(tmp_path):
    """sub-101: head model, FastSurfer, one 4-pair (mTI) simulation; sub-102: DICOMs staged in
    sourcedata only; sub-103: a FastSurfer run and nothing else; sub-104: a legacy FreeSurfer
    recon and nothing else."""
    from tit.paths import get_path_manager

    pm = get_path_manager(str(tmp_path))
    _touch(os.path.join(pm.m2m("101"), "101.msh"))
    _touch(os.path.join(pm.fastsurfer_subject("101"), "mri", "aparc.DKTatlas+aseg.mgz"))
    # A 4-pair simulation "S": the two intermediate TI meshes, the mTI mesh and its NIfTIs.
    _touch(os.path.join(pm.ti_mesh_dir("101", "S"), "S_TI_AB.msh"))
    _touch(os.path.join(pm.ti_mesh_dir("101", "S"), "S_TI_CD.msh"))
    mti_mesh = pm.mti_mesh_dir("101", "S")
    _touch(os.path.join(mti_mesh, "S_mTI.msh"))
    _touch(os.path.join(mti_mesh, "S_mTI.msh.opt"))  # SimNIBS view file, not a mesh
    mti_niftis = os.path.join(os.path.dirname(mti_mesh), "niftis")
    _touch(os.path.join(mti_niftis, "grey_S_mTI_max.nii.gz"))
    _touch(os.path.join(mti_niftis, "S_mTI_max.nii"))
    _touch(os.path.join(pm.sourcedata_subject("102"), "T1w", "IM0001.dcm"))
    os.makedirs(pm.fastsurfer_subject("103"))
    os.makedirs(pm.freesurfer_subject("104"))
    return pm


def test_mti_meshes_and_niftis_are_reported(srv, project):
    out = inspect(srv, project.project_dir, subject="101")
    sim = out["subjects"][0]["simulations"]["S"]
    assert sim["has_mti_dir"] is True
    assert sim["mti_mesh_files"] == ["S_mTI.msh"]
    assert sim["mti_nifti_files"] == ["S_mTI_max.nii", "grey_S_mTI_max.nii.gz"]
    # The intermediate TI meshes stay where they were.
    assert sim["mesh_files"] == ["S_TI_AB.msh", "S_TI_CD.msh"]


def test_a_ti_only_simulation_has_no_mti_files(srv, project):
    _touch(os.path.join(project.ti_mesh_dir("101", "T"), "T_TI.msh"))
    sim = inspect(srv, project.project_dir, subject="101")["subjects"][0]
    assert sim["simulations"]["T"]["has_mti_dir"] is False
    assert sim["simulations"]["T"]["mti_mesh_files"] == []


def _agrees_with_catalog(out: dict, pm) -> None:
    from tit import catalog

    rows = catalog.list_subjects(pm)
    assert rows, "the catalog lists no subject: nothing to compare"
    by_id = {s["id"]: s for s in out["subjects"]}
    for row in rows:
        sid = row["id"]
        assert sid in by_id, f"sub-{sid} is in the catalog but not in inspect_project"
        got = by_id[sid]
        assert got["has_m2m"] is row["has_m2m"], sid
        assert got["has_fastsurfer"] is row["has_fastsurfer"], sid
        assert got["has_freesurfer"] is row["has_freesurfer"], sid
        if row.get("has_sourcedata"):
            assert got["has_sourcedata"] is True, sid
        sims = catalog.list_simulations(pm, sid)
        if sims is not None:
            assert sorted(got["simulations"]) == sorted(s["name"] for s in sims), sid
            for s in sims:
                assert got["simulations"][s["name"]]["has_mti_dir"] is s["has_mti"]
        else:
            assert got["simulations"] == {}, sid
        runs = catalog.flex_runs(pm, sid) or []
        assert {r["name"] for r in runs} <= set(got["flex_search_runs"]), sid


def test_synthetic_project_agrees_with_the_catalog(srv, project):
    out = inspect(srv, project.project_dir)
    assert [s["id"] for s in out["subjects"]] == ["101", "102", "103", "104"]
    _agrees_with_catalog(out, project)
    by_id = {s["id"]: s for s in out["subjects"]}
    assert by_id["101"]["has_fastsurfer"] and not by_id["101"]["has_freesurfer"]
    assert by_id["102"]["has_sourcedata"] and not by_id["102"]["has_m2m"]
    assert by_id["103"]["has_fastsurfer"] and not by_id["103"]["has_sourcedata"]
    assert by_id["104"]["has_freesurfer"] and not by_id["104"]["has_fastsurfer"]


def _listing(root: str) -> dict[str, tuple[int, int]]:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            st = os.lstat(p)
            out[p] = (st.st_mtime_ns, st.st_size)
    return out


@pytest.mark.skipif(
    not DATASET or not os.path.isdir(DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)
def test_dataset_000_agrees_with_the_catalog(srv):
    from tit.paths import get_path_manager

    before = _listing(DATASET)
    pm = get_path_manager(DATASET)
    out = inspect(srv, DATASET)
    _agrees_with_catalog(out, pm)
    # Something real was compared: a FastSurfer subject and a sourcedata-only one.
    by_id = {s["id"]: s for s in out["subjects"]}
    assert any(s["has_fastsurfer"] for s in by_id.values())
    assert any(s["has_sourcedata"] and not s["has_m2m"] for s in by_id.values())
    assert _listing(DATASET) == before, "the inspection wrote into the dataset"
