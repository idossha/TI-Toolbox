"""Every listing ``inspect_project`` returns obeys the project jail, 2026-10-22.

What this pins: ``agent-plugin/mcp/server.py::tool_inspect_project`` makes 22 listings of a
project (``anat_files``, ``leadfields``, ``freehand_configs``, the flex/ex/mEx run lists, the
simulation names and each simulation's ``contents``, TI/mTI meshes and NIfTIs, ``analyses``
(Mesh and Voxel),
the job store, ``sourcedata_subjects``, ``config_files``, ``reports``, both levels of
``stats_analyses``, ``notebooks``, ``notebook_examples`` and ``viewer_scenes``). For each one:

* the folder, really inside the project, lists its own entry and not a sibling entry that is a
  symlink leading out of the project (the positive control also proves the test reads the
  right field for the right folder);
* the folder itself, a symlink leading out of the project, is read as empty -- both the entry
  the outside folder holds and the one in it that links back into the project.

Each location is one call site; reading any of them without the jail (``_ls(p)`` instead of the
jailed ``ls(p)``) lists the outward entry and fails its case. A new list field in the result
fails ``test_every_listing_inspect_project_returns_has_a_case`` until it has a case here, and the
README's one-line summary of what ``inspect_project`` reports names only fields it returns (no
``pipelines``: the canvas was removed).

Where the expected values come from: the note ``inspect_project`` returns ("a folder that is a
symlink leading out of the project is not read") and the app's jail, ``tit.paths.is_within``
(a path counts only when it resolves inside the project); the entry names are the ones each
case writes; the README items map to result keys by the hand table ``README_ITEMS``. The folder
of each location comes from ``PathManager`` where it names it
(``m2m``, ``simulation``, ``ti_mesh_dir``, ``mti_mesh_dir``, ``sourcedata``), else from the
v3 project layout the plugin documents.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_listing_jail.py -q
Deliberately elsewhere: the presence flags (tests/test_agent_plugin_flags_and_reasons.py), the
subject-level jail and its ``proj-twin`` edge (tests/test_agent_plugin_inspect_project.py).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "agent-plugin" / "mcp" / "server.py"
SID = "101"
SIM = "S"


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("ti_mcp_server_listing_jail", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def pm(tmp_path):
    from tit.paths import get_path_manager, reset_path_manager

    reset_path_manager()
    (tmp_path / "proj").mkdir()
    manager = get_path_manager(str(tmp_path / "proj"))
    # The subject is listed from its own, real head-model folder.
    os.makedirs(manager.m2m(SID))
    yield manager
    reset_path_manager()


def _subject(out: dict) -> dict:
    [entry] = [s for s in out["subjects"] if s["id"] == SID]
    return entry


def _sim(out: dict) -> dict:
    return _subject(out)["simulations"].get(SIM, {})


class Case(NamedTuple):
    folder: Callable[[Any], str]  # PathManager -> the listed folder
    names: tuple[str, str]  # (the entry kept inside, the entry that links out)
    is_dir: bool  # the entries are folders (a dirs-only listing) or files
    field: Callable[[dict], Any]  # inspect_project's result -> the listing
    seen: Callable[[list[str]], Any] = (
        sorted  # the visible names -> the expected listing
    )


def _code(pm, *parts: str) -> str:
    return os.path.join(pm.project_dir, "code", "ti-toolbox", *parts)


def _tt(pm, *parts: str) -> str:
    return os.path.join(pm.derivatives(), "ti-toolbox", *parts)


CASES = {
    "anat_files": Case(
        lambda pm: os.path.join(pm.bids_subject(SID), "anat"),
        ("sub-101_T1w.nii.gz", "sub-101_T2w.nii.gz"),
        False,
        lambda o: _subject(o)["anat_files"],
    ),
    "leadfields": Case(
        lambda pm: os.path.join(pm.sub(SID), "leadfields"),
        ("a_leadfield.hdf5", "b_leadfield.hdf5"),
        False,
        lambda o: _subject(o)["leadfields"],
    ),
    "freehand_configs": Case(
        lambda pm: os.path.join(pm.m2m(SID), "stim_configs"),
        ("a.json", "b.json"),
        False,
        lambda o: _subject(o)["freehand_configs"],
    ),
    "flex_search_runs": Case(
        lambda pm: os.path.join(pm.sub(SID), "flex-search"),
        ("run_a", "run_b"),
        True,
        lambda o: _subject(o)["flex_search_runs"],
    ),
    "ex_search_runs": Case(
        lambda pm: os.path.join(pm.sub(SID), "ex-search"),
        ("run_a", "run_b"),
        True,
        lambda o: _subject(o)["ex_search_runs"],
    ),
    "mex_search_runs": Case(
        lambda pm: os.path.join(pm.sub(SID), "m-ex-search"),
        ("run_a", "run_b"),
        True,
        lambda o: _subject(o)["mex_search_runs"],
    ),
    "simulations": Case(
        lambda pm: os.path.dirname(pm.simulation(SID, SIM)),
        (SIM, "T"),
        True,
        lambda o: sorted(_subject(o)["simulations"]),
    ),
    "simulation contents": Case(
        lambda pm: pm.simulation(SID, SIM),
        ("TI", "extra"),
        True,
        lambda o: _sim(o).get("contents", []),
    ),
    "TI mesh_files": Case(
        lambda pm: pm.ti_mesh_dir(SID, SIM),
        ("S_TI.msh", "X_TI.msh"),
        False,
        lambda o: _sim(o).get("mesh_files", []),
    ),
    "TI nifti_files": Case(
        lambda pm: os.path.join(os.path.dirname(pm.ti_mesh_dir(SID, SIM)), "niftis"),
        ("S_TI_max.nii.gz", "X_TI_max.nii.gz"),
        False,
        lambda o: _sim(o).get("nifti_files", []),
    ),
    "mTI mesh_files": Case(
        lambda pm: pm.mti_mesh_dir(SID, SIM),
        ("S_mTI.msh", "X_mTI.msh"),
        False,
        lambda o: _sim(o).get("mti_mesh_files", []),
    ),
    "mTI nifti_files": Case(
        lambda pm: os.path.join(os.path.dirname(pm.mti_mesh_dir(SID, SIM)), "niftis"),
        ("S_mTI_max.nii.gz", "X_mTI_max.nii.gz"),
        False,
        lambda o: _sim(o).get("mti_nifti_files", []),
    ),
    "analyses Mesh": Case(
        lambda pm: os.path.join(pm.simulation(SID, SIM), "Analyses", "Mesh"),
        ("roi_a", "roi_b"),
        True,
        lambda o: _sim(o).get("analyses", {}).get("Mesh", []),
    ),
    "analyses Voxel": Case(
        lambda pm: os.path.join(pm.simulation(SID, SIM), "Analyses", "Voxel"),
        ("roi_a", "roi_b"),
        True,
        lambda o: _sim(o).get("analyses", {}).get("Voxel", []),
    ),
    "job store": Case(
        lambda pm: _code(pm, "jobs"),
        ("job_a", "job_b"),
        True,
        lambda o: o["code_ti_toolbox"]["jobs_count"],
        len,
    ),
    "sourcedata_subjects": Case(
        lambda pm: pm.sourcedata(),
        ("sub-201", "sub-202"),
        True,
        lambda o: o["sourcedata_subjects"],
    ),
    "config_files": Case(
        lambda pm: _code(pm, "config"),
        ("a.json", "b.json"),
        False,
        lambda o: o["config_files"],
    ),
    "reports": Case(
        lambda pm: _tt(pm, "reports"),
        ("a.html", "b.html"),
        False,
        lambda o: o["reports"],
    ),
    "stats_analyses kinds": Case(
        lambda pm: _tt(pm, "stats"),
        ("group_a", "group_b"),
        True,
        lambda o: sorted(o["stats_analyses"]),
    ),
    "stats_analyses runs": Case(
        lambda pm: _tt(pm, "stats", "group"),
        ("run_a", "run_b"),
        True,
        lambda o: o["stats_analyses"].get("group", []),
    ),
    "notebooks": Case(
        lambda pm: _code(pm, "notebooks"),
        ("a.ipynb", "b.ipynb"),
        False,
        lambda o: o["code_ti_toolbox"]["notebooks"],
    ),
    "notebook_examples": Case(
        lambda pm: _code(pm, "notebooks", "examples"),
        ("a.ipynb", "b.ipynb"),
        False,
        lambda o: o["code_ti_toolbox"]["notebook_examples"],
    ),
    "viewer_scenes": Case(
        lambda pm: _code(pm, "viewer"),
        ("a.tetravox.json", "b.tetravox.json"),
        False,
        lambda o: o["code_ti_toolbox"]["viewer_scenes"],
    ),
}


def _inspect(srv, root: str) -> dict:
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "inspect_project", "arguments": {"project_root": root}},
        }
    )
    assert resp["result"]["isError"] is False, resp
    return json.loads(resp["result"]["content"][0]["text"])


def _make(path: Path, is_dir: bool) -> None:
    if is_dir:
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


def _outside(pm) -> Path:
    """A folder beside the project, never under it."""
    out = Path(pm.project_dir).parent / "outside"
    assert not str(out).startswith(pm.project_dir)
    return out


@pytest.mark.parametrize("name", list(CASES))
def test_a_folder_lists_its_own_entry_and_not_one_linking_out(srv, pm, name):
    case = CASES[name]
    folder = Path(case.folder(pm))
    kept, linked = case.names
    _make(folder / kept, case.is_dir)
    target = _outside(pm) / linked
    _make(target, case.is_dir)
    os.symlink(target, folder / linked)

    out = _inspect(srv, pm.project_dir)
    assert case.field(out) == case.seen([kept]), name


@pytest.mark.parametrize("name", list(CASES))
def test_a_folder_that_links_out_of_the_project_is_read_as_empty(srv, pm, name):
    case = CASES[name]
    folder = Path(case.folder(pm))
    target = _outside(pm) / "elsewhere"
    back, own = case.names
    # One entry of the outside folder is its own; the other links back into the project.
    # Behind a folder that leads out, neither is the project's (tit.paths.is_within on the
    # folder, not only on each entry).
    stash = Path(pm.project_dir) / "stash" / back
    _make(stash, case.is_dir)
    target.mkdir(parents=True)
    os.symlink(stash, target / back)
    _make(target / own, case.is_dir)
    folder.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, folder)

    out = _inspect(srv, pm.project_dir)
    assert any(
        "symlink leading out of the project is not read" in n for n in out["notes"]
    )
    assert case.field(out) == case.seen([]), name


def test_every_listing_inspect_project_returns_has_a_case(srv, pm):
    """A new listing added to inspect_project needs its own jail case here: every list field
    of a populated result is one this file covers."""
    covered_subject = {"anat_files", "leadfields", "freehand_configs"} | {
        f"{k}_search_runs" for k in ("flex", "ex", "mex")
    }
    covered_sim = {
        "contents",
        "mesh_files",
        "nifti_files",
        "mti_mesh_files",
        "mti_nifti_files",
    }
    covered_top = {"sourcedata_subjects", "config_files", "reports"}
    covered_tools = {"notebooks", "notebook_examples", "viewer_scenes"}
    # Populate every location so no list field is missing from the result.
    for case in CASES.values():
        _make(Path(case.folder(pm)) / case.names[0], case.is_dir)

    out = _inspect(srv, pm.project_dir)
    subject, sim = _subject(out), _sim(out)
    assert {k for k, v in subject.items() if isinstance(v, list)} == covered_subject
    assert {k for k, v in sim.items() if isinstance(v, list)} == covered_sim
    assert {k for k, v in out.items() if isinstance(v, list)} - {
        "subjects",
        "notes",
    } == covered_top
    tools = out["code_ti_toolbox"]
    assert {
        k for k, v in tools.items() if isinstance(v, list) and k != "recent_failures"
    } == covered_tools
    # The dict-valued listings: simulations, analyses and stats_analyses, each covered above.
    assert set(subject["simulations"]) == {SIM}
    assert set(sim["analyses"]) == {"Mesh", "Voxel"}
    assert set(out["stats_analyses"]) == {"group", "group_a"}


#: What each item of the README's "inspect a project directory (...)" list is, as result keys
#: (subject-level keys under ``subjects[]``, simulation-level under ``simulations{}``).
README_ITEMS = {
    "subjects": [("top", "subjects")],
    "m2m": [("subject", "has_m2m")],
    "FastSurfer/FreeSurfer": [
        ("subject", "has_fastsurfer"),
        ("subject", "has_freesurfer"),
    ],
    "TI and mTI simulations": [("sim", "has_ti_dir"), ("sim", "has_mti_dir")],
    "flex/ex runs": [("subject", "flex_search_runs"), ("subject", "ex_search_runs")],
    "the job store": [("tools", "jobs_count"), ("tools", "jobs_by_state")],
    "notebooks": [("tools", "notebooks")],
    "reports": [("top", "reports")],
}


def test_the_readme_says_inspect_project_reports_only_what_it_returns(srv, pm):
    readme = (REPO / "agent-plugin" / "README.md").read_text()
    said = re.search(r"inspect a project directory \(([^)]*)\)", readme).group(1)
    items = [i.strip() for i in said.split(",")]
    assert len(items) >= 5  # the parse found the list
    unknown = [i for i in items if i not in README_ITEMS]
    assert not unknown, f"the README says inspect_project reports {unknown}"
    _make(Path(pm.ti_mesh_dir(SID, SIM)) / "S_TI.msh", False)
    out = _inspect(srv, pm.project_dir)
    where = {
        "top": out,
        "subject": _subject(out),
        "sim": _sim(out),
        "tools": out["code_ti_toolbox"],
    }
    for item in items:
        for level, key in README_ITEMS[item]:
            assert key in where[level], f"{item}: no {key} in the result"
