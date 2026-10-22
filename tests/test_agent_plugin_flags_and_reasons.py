"""Every inspect_project flag obeys the project jail, and plan_job's reason and the rail digits
say what is true, 2026-10-22.

What this pins (each case was a surviving mutant of p31's round-3 verification):

* ``inspect_project`` reads nothing through a symlink that leads out of the project -- the
  rule its result's notes state -- for *every* presence flag, not only the subject listing:
  ``has_head_mesh``, ``has_freesurfer``, ``freesurfer_recon``, ``qsiprep``, ``dti_tensor``,
  ``has_ti_dir``, ``has_mti_dir``, ``has_fsaverage``, ``looks_like_ti_project`` and the job
  store's ``status.json``;
* a subject known only from ``derivatives/SimNIBS/sub-<id>/m2m_<id>`` is listed, as
  ``tit.catalog.subject_ids`` lists it, and ``mesh_files`` holds only ``.msh`` files;
* a zero-job plan's ``reason`` carries the server's own warnings, and a refused config's plan
  has no ``reason`` (its errors are the reason);
* every "Cmd+N is ..." the quick facts state matches the rail in ``registry.ts``: rows take
  ⌘0 upwards, and a digit past the last row belongs to nothing (``SHORTCUT_ALIASES`` maps no
  digit).

Where the expected values come from: the note ``inspect_project`` itself returns ("a folder
that is a symlink leading out of the project is not read"), ``tit.catalog.subject_ids`` on
the same directory, ``POST /api/plan`` and ``/api/validate`` called directly on the same live
server, and ``NAV_ORDER``/``SHORTCUT_ALIASES`` read from ``registry.ts``.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_flags_and_reasons.py -q
Deliberately elsewhere: the subject-level jail and order (tests/test_agent_plugin_inspect_project.py),
plan_job's per-kind refusals (tests/test_agent_plugin_plan_job.py).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

from tests.test_agent_plugin_plan_job import ROI, call, live  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "agent-plugin" / "mcp" / "server.py"


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("ti_mcp_server_flags", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _inspect(srv, root, **args) -> dict:
    err, out = call(srv, "inspect_project", project_root=str(root), **args)
    assert not err, out
    return out


def _touch(path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def _link_out(inside, outside_root: Path, name: str, *, is_dir: bool) -> None:
    """Make *inside* a symlink to a real file or folder outside the project."""
    target = outside_root / name
    if is_dir:
        target.mkdir(parents=True, exist_ok=True)
        _touch(target / "content.txt")
    else:
        _touch(target)
    Path(inside).parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, inside)


def test_every_presence_flag_ignores_what_a_symlink_brings_in_from_outside(
    srv, tmp_path
):
    from tit.paths import get_path_manager, reset_path_manager

    root = tmp_path / "proj"
    out = tmp_path / "outside"
    root.mkdir()
    reset_path_manager()
    pm = get_path_manager(str(root))
    sid = "101"
    m2m = Path(pm.m2m(sid))
    m2m.mkdir(parents=True)  # the subject is listed from its own, real m2m folder
    # charm's segmentation is real, so only the outward mesh can decide has_m2m.
    _touch(m2m / "final_tissues.nii.gz")
    deriv = root / "derivatives"
    _link_out(m2m / f"{sid}.msh", out, "mesh.msh", is_dir=False)
    _link_out(m2m / "DTI_coregT1_tensor.nii.gz", out, "tensor.nii.gz", is_dir=False)
    # A real recon outside, so an unjailed reader would see mri/aparc+aseg.mgz through it.
    _touch(out / "fs" / "mri" / "aparc+aseg.mgz")
    (deriv / "freesurfer").mkdir(parents=True)
    os.symlink(out / "fs", deriv / "freesurfer" / f"sub-{sid}")
    _link_out(deriv / "qsiprep" / f"sub-{sid}", out, "qsiprep", is_dir=True)
    sim = Path(pm.simulation(sid, "S"))
    _touch(sim / "TI" / "mesh" / "S_TI.msh")  # a real simulation...
    for part in ("mTI", "fsaverage"):  # ...whose other parts link out
        _link_out(sim / part, out, f"sim_{part}", is_dir=True)
    jobs = root / "code" / "ti-toolbox" / "jobs"
    status = {"id": "j1", "kind": "sim", "state": "failed", "error": {"type": "lost"}}
    _touch(jobs / "j1" / "spec.json")
    out_status = out / "status.json"
    out_status.write_text(json.dumps(status))
    os.symlink(out_status, jobs / "j1" / "status.json")

    result = _inspect(srv, root)
    assert any(
        "symlink leading out of the project is not read" in n for n in result["notes"]
    )
    [entry] = result["subjects"]
    assert entry["id"] == sid
    for flag in (
        "has_m2m",
        "has_head_mesh",
        "dti_tensor",
        "has_freesurfer",
        "freesurfer_recon",
        "qsiprep",
    ):
        assert entry[flag] is False, flag
    s = entry["simulations"]["S"]
    assert s["has_ti_dir"] is True and s["mesh_files"] == ["S_TI.msh"]  # the real part
    assert s["has_mti_dir"] is False and s["has_fsaverage"] is False
    tools = result["code_ti_toolbox"]
    assert tools["jobs_count"] == 1  # the job folder is real...
    assert (
        tools["jobs_by_state"] == {} and tools["recent_failures"] == []
    )  # ...its status is not
    reset_path_manager()


def test_a_ti_folder_that_links_out_is_not_a_simulation_result(srv, tmp_path):
    root = tmp_path / "proj"
    sim = root / "derivatives" / "SimNIBS" / "sub-101" / "Simulations" / "S"
    (root / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101").mkdir(parents=True)
    sim.mkdir(parents=True)
    _touch(tmp_path / "outside" / "TI" / "mesh" / "S_TI.msh")
    os.symlink(tmp_path / "outside" / "TI", sim / "TI")
    s = _inspect(srv, root)["subjects"][0]["simulations"]["S"]
    assert s["has_ti_dir"] is False and s["mesh_files"] == []


def test_a_project_whose_toolbox_folders_link_out_does_not_look_like_one(srv, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _link_out(root / "derivatives" / "SimNIBS", tmp_path / "outside", "sn", is_dir=True)
    _link_out(root / "code" / "ti-toolbox", tmp_path / "outside", "code", is_dir=True)
    assert _inspect(srv, root)["looks_like_ti_project"] is False
    # The same folders, really inside: it does.
    real = tmp_path / "real"
    (real / "derivatives" / "SimNIBS").mkdir(parents=True)
    assert _inspect(srv, real)["looks_like_ti_project"] is True


def test_a_subject_known_only_from_its_head_model_is_listed(srv, tmp_path):
    from tit import catalog
    from tit.paths import get_path_manager, reset_path_manager

    reset_path_manager()
    pm = get_path_manager(str(tmp_path))
    Path(pm.m2m("ernie")).mkdir(parents=True)
    (Path(pm.simnibs()) / "sub-noheadmodel").mkdir(parents=True)
    sim = Path(pm.ti_mesh_dir("ernie", "S"))
    _touch(sim / "S_TI.msh")
    _touch(sim / "S_TI.msh.opt")  # the SimNIBS view file beside the mesh, not a mesh
    out = _inspect(srv, tmp_path)
    assert [s["id"] for s in out["subjects"]] == catalog.subject_ids(pm) == ["ernie"]
    assert out["subjects"][0]["simulations"]["S"]["mesh_files"] == ["S_TI.msh"]
    reset_path_manager()


def test_a_zero_job_plan_says_the_servers_warnings_and_a_refusal_has_no_reason(live):
    js, _, _, as_user = live
    config = {"montages": []}
    direct = as_user(
        "POST",
        "/api/plan/sim",
        {
            "config": {**config, "subject_id": "101"},
            "subject_ids": ["101"],
            "created_by": "agent",
        },
    )
    assert direct["jobs"] == [] and direct["warnings"]  # the premise
    err, plan = call(js, "plan_job", kind="sim", config=config, subject_ids=["101"])
    assert not err and plan["ok"] is False
    for warning in direct["warnings"]:
        assert warning in plan["reason"]

    err, refused = call(js, "plan_job", kind="flex", config={}, subject_ids=["101"])
    assert not err and refused["errors"] and refused["jobs"] == []
    assert "reason" not in refused  # the errors say why; no second, vaguer reason


def test_every_cmd_digit_the_quick_facts_state_is_the_registrys(srv):
    registry = (REPO / "desktop/src/renderer/app/registry.ts").read_text()
    nav = re.findall(
        r'"([\w-]+)"',
        re.search(r"export const NAV_ORDER = \[(.*?)\] as const", registry, re.S).group(
            1
        ),
    )
    aliases = re.search(r"SHORTCUT_ALIASES[^=]*=\s*\{([^}]*)\}", registry).group(1)
    assert not re.search(r'"\d"\s*:', aliases)  # no digit is an alias
    titles = [
        re.search(
            rf'id: "{i}",\s*title: "([^"]+)"',
            (REPO / f"desktop/src/renderer/pages/{i}/index.tsx").read_text(),
        ).group(1)
        for i in nav
    ]
    assert len(titles) == 9  # the parse found the rail
    facts = json.dumps(call(srv, "get_quick_facts")[1])
    claims = re.findall(r"Cmd\+(\d) is (\w+)", facts)
    assert claims  # the facts make at least one such claim
    for digit, said in claims:
        d = int(digit)
        expected = titles[d] if d < len(titles) else "unassigned"
        assert said == expected, f"Cmd+{d} is {said}; the rail says {expected}"
