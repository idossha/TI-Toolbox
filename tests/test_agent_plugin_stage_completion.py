"""What the agent plugin calls "done" and "failed" is what the app and the job manager call it, 2026-10-22.

What this pins, against ``main`` as it moved after the plugin's facts were written:

* ``inspect_project``'s ``has_m2m`` and ``has_fastsurfer`` mean the stage *finished*, not that
  its folder exists. Since ``tit.catalog`` started asking pre-processing's own completion rule
  (``tit.pre.preflight.step_output_complete``), an interrupted charm run (``m2m_<id>`` without
  its mesh or final segmentation) or FastSurfer run (Dataset 000's sub-101: ``orig.mgz`` and
  logs, no segmentation) is not shown as done in the app; the plugin told an agent it was.
* ``get_quick_facts`` ``failure_taxonomy`` lists exactly the ``error.type`` values the job
  manager writes, with the labels the app shows: it used to list ten values, six of which no
  code emits, and missed ``forced`` and ``spawn_error``.

Where the expected values come from: for the flags, ``step_output_complete`` run on the same
synthetic project (a second implementation of the rule, not the plugin) plus the file names
the producers write (charm: ``<id>.msh`` and ``final_tissues.nii.gz``; FastSurfer:
``tit.pre.fastsurfer.SEG_FILENAME``); for the taxonomy, every ``JobError(type=...)`` literal
under ``tit/jobs`` collected with :mod:`ast` and the ``ERROR_LABEL`` table of
``desktop/src/renderer/app/jobs-rail/format.ts`` read as text.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_stage_completion.py -q
Deliberately elsewhere: the subject list and the catalog comparison on Dataset 000
(tests/test_agent_plugin_inspect_project.py), the contract enum of ``JobError.type``.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "agent-plugin" / "mcp" / "server.py"


@pytest.fixture(scope="module")
def srv():
    spec = importlib.util.spec_from_file_location("ti_mcp_server_stages", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call(srv, name: str, **args) -> dict:
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
    )
    assert not resp["result"]["isError"], resp
    return json.loads(resp["result"]["content"][0]["text"])


def _touch(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_bytes(b"x")


# (what the stage folder holds, relative to it) -> a layout charm or FastSurfer leaves behind
CHARM_LAYOUTS = {
    "interrupted before the mesh": ["final_tissues.nii.gz", "charm_log.html"],
    "mesh without the segmentation": ["{sid}.msh"],
    "finished": ["{sid}.msh", "final_tissues.nii.gz"],
}
FASTSURFER_LAYOUTS = {
    # Dataset 000's sub-101 as it is on disk: the run stopped at the coronal prediction.
    "interrupted (orig.mgz and logs)": ["mri/orig.mgz", "scripts/deep-seg.log"],
    "finished": ["mri/orig.mgz", "mri/{seg}"],
}


@pytest.fixture()
def project(tmp_path):
    from tit.paths import get_path_manager, reset_path_manager
    from tit.pre.fastsurfer import SEG_FILENAME

    reset_path_manager()
    pm = get_path_manager(str(tmp_path))
    layouts = {}
    for i, (label, files) in enumerate(CHARM_LAYOUTS.items()):
        sid = f"c{i}"
        for f in files:
            _touch(os.path.join(pm.m2m(sid), f.format(sid=sid)))
        layouts[sid] = ("charm", label)
    for i, (label, files) in enumerate(FASTSURFER_LAYOUTS.items()):
        sid = f"f{i}"
        for f in files:
            _touch(os.path.join(pm.fastsurfer_subject(sid), f.format(seg=SEG_FILENAME)))
        layouts[sid] = ("fastsurfer", label)
    yield pm, layouts
    reset_path_manager()


def test_a_head_model_or_segmentation_counts_only_once_its_stage_finished(srv, project):
    from tit.pre.preflight import step_output_complete

    pm, layouts = project
    out = _call(srv, "inspect_project", project_root=pm.project_dir)
    flags = {s["id"]: s for s in out["subjects"]}
    assert set(flags) == set(layouts)  # every staged subject is listed
    for sid, (step, label) in layouts.items():
        key = "has_m2m" if step == "charm" else "has_fastsurfer"
        done = step_output_complete(pm.project_dir, sid, step)
        assert flags[sid][key] is done, f"{sid} ({step}, {label})"
        # The producers' own meaning, independent of the rule's implementation.
        assert done is (label == "finished"), f"{sid} ({step}, {label})"
    # An m2m folder still lists its subject (the app lists it too, without a head model).
    assert {"c0", "c1", "c2"} <= set(flags)


def test_the_completion_rule_is_stated_where_an_agent_reads_the_flags(srv, project):
    pm, _ = project
    notes = " ".join(
        _call(srv, "inspect_project", project_root=pm.project_dir)["notes"]
    )
    assert re.search(r"has_m2m\b[^.]*\.msh[^.]*final_tissues\.nii\.gz", notes)
    assert "aparc.DKTatlas+aseg.deep.mgz" in notes


def _emitted_error_types() -> set[str]:
    """Every literal ``type`` of a ``JobError(...)`` call under ``tit/jobs``."""
    found: set[str] = set()
    for path in sorted((REPO / "tit" / "jobs").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name != "JobError":
                continue
            value = next((k.value for k in node.keywords if k.arg == "type"), None)
            assert isinstance(value, ast.Constant), f"{path.name}: a non-literal type"
            found.add(value.value)
    return found


def test_the_failure_taxonomy_is_what_the_job_manager_writes_and_the_app_shows(srv):
    facts = _call(srv, "get_quick_facts")
    emitted = _emitted_error_types()
    assert {"runner_failed", "lost", "forced"} <= emitted  # the collector found them
    fmt = (REPO / "desktop/src/renderer/app/jobs-rail/format.ts").read_text()
    table = re.search(r"const ERROR_LABEL[^{]*\{(.*?)\};", fmt, re.S).group(1)
    labels = dict(re.findall(r'(\w+): "([^"]+)"', table))
    assert set(facts["failure_taxonomy"]) == emitted
    assert facts["failure_taxonomy"] == labels
