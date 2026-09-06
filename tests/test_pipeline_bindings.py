"""The dynamic-binding write-back: what the ``resolve`` step found reaches the consumer's runner.

D3 has two halves.  ``tit.pipeline.plan`` plans a ``tit.tools.pipeline_resolve`` job between an
optimizer and the Simulator that consumes its montage, because a flex run directory is named at
run time.  This file tests the *other* half, which the PC lane stopped at the boundary of: the
consumer carries the file's project-relative path in its config, and
``tit.jobs.manager.JobManager._runner_config_path`` merges the resolved value into the runner's
``config.json`` at admission -- the first moment the file can exist, because admission happens
only after every ``after`` job has finished.

The whole chain is exercised end to end (plan -> resolve tool -> manager) rather than each half
against a hand-written fixture, so a change to the path convention in one module fails here.
"""

from __future__ import annotations

import json
import os

from tit.jobs.bindings import BINDINGS_KEY, merge_pipeline_bindings
from tit.jobs.manager import JobManager
from tit.jobs.spec import JobSpec
from tit.pipeline.document import PipelineDocument
from tit.pipeline.plan import bindings_relpath, plan_pipeline

from tests.test_pipeline_plan import (
    ANALYZER,
    build,
    flex_config,
    sim_config,
)  # noqa: F401


def flex_to_sim(name: str = "demo") -> PipelineDocument:
    """``flex -> sim``: the montage the Simulator runs is the optimizer's run-time output."""
    return build(
        [
            ("flex1", "flex", flex_config()),
            ("sim1", "sim", sim_config([])),
        ],
        [("flex1", "sim1", "subjects"), ("flex1", "sim1", "montages")],
        name=name,
    )


def test_the_consumer_carries_the_path_its_resolve_step_will_write() -> None:
    jobs = {j.label: j for j in plan_pipeline(flex_to_sim())}
    descriptors = jobs["sim1:0"].config[BINDINGS_KEY]
    assert len(descriptors) == 1
    assert descriptors[0]["port"] == "montages"
    assert descriptors[0]["field"] == "montages"
    assert descriptors[0]["subject_ids"] == ["ernie"]
    # The path is exactly the one the resolve tool computes from its own arguments.
    assert descriptors[0]["path"] == bindings_relpath("demo", "sim1", "montages")


def test_a_static_only_pipeline_carries_no_descriptor() -> None:
    """The key must never appear on a job that has nothing to wait for."""
    doc = build(
        [
            ("sim1", "sim", {**sim_config(["A"]), "subject_ids": ["ernie"]}),
            ("an1", "analyzer", ANALYZER),
        ],
        [("sim1", "an1", "subjects"), ("sim1", "an1", "simulation")],
    )
    for job in plan_pipeline(doc):
        assert BINDINGS_KEY not in job.config


def test_the_resolve_tool_writes_where_the_consumer_looks(
    tmp_path, monkeypatch
) -> None:
    """Plan, run the real tool over a real directory tree, and read the file back by the path
    the *plan* recorded -- not by the path the tool printed."""
    from tit.tools import pipeline_resolve

    project = tmp_path / "project"
    run_dir = (
        project
        / "derivatives"
        / "SimNIBS"
        / "sub-ernie"
        / "flex-search"
        / "L_Insula_mean"
    )
    run_dir.mkdir(parents=True)

    monkeypatch.setenv("TI_PROJECT_DIR", str(project))
    assert (
        pipeline_resolve.main(
            [
                "--pipeline",
                "demo",
                "--node",
                "sim1",
                "--port",
                "montages",
                "--from-kind",
                "flex",
                "--subjects",
                "ernie",
                "--project-dir",
                str(project),
            ]
        )
        == 0
    )

    jobs = {j.label: j for j in plan_pipeline(flex_to_sim())}
    descriptor = jobs["sim1:0"].config[BINDINGS_KEY][0]
    written = json.loads((project / descriptor["path"]).read_text())
    assert written["values"] == {"ernie": ["L_Insula_mean"]}


def test_the_manager_merges_the_resolved_value_into_the_runners_config(
    tmp_path,
) -> None:
    """The end of the chain: `config.json` names the montage the optimizer produced."""
    project = str(tmp_path)
    jobs = {j.label: j for j in plan_pipeline(flex_to_sim())}
    consumer = jobs["sim1:0"]
    assert consumer.config["montages"] == [], "the canvas leaves it empty on purpose"

    descriptor = consumer.config[BINDINGS_KEY][0]
    target = os.path.join(project, descriptor["path"])
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump({"port": "montages", "values": {"ernie": ["L_Insula_mean"]}}, fh)

    manager = JobManager(project, runner_cwd=project)
    status = manager.submit("sim", consumer.config, ["ernie"])
    spec = JobSpec(
        id=status["id"],
        kind="sim",
        config=consumer.config,
        subject_ids=["ernie"],
    )
    path = manager._runner_config_path(spec)

    written = json.loads(open(path, encoding="utf-8").read())
    assert written["montages"] == ["L_Insula_mean"]
    # The private key is the plan's business, not the runner's: it must never reach config.json.
    assert BINDINGS_KEY not in written
    assert written["project_dir"] == project


def test_a_resolve_step_that_found_nothing_leaves_the_field_alone(tmp_path) -> None:
    """The honest degradation: no crash, and the form's own value survives."""
    payload = {
        "montages": [],
        BINDINGS_KEY: [
            {
                "path": bindings_relpath("demo", "sim1", "montages"),
                "field": "montages",
                "port": "montages",
                "subject_ids": ["ernie"],
            }
        ],
    }
    # File absent entirely.
    assert merge_pipeline_bindings(dict(payload), str(tmp_path)) == {"montages": []}

    # File present, but the search wrote no run for this subject.
    target = os.path.join(str(tmp_path), payload[BINDINGS_KEY][0]["path"])
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump({"values": {"ernie": []}}, fh)
    assert merge_pipeline_bindings(dict(payload), str(tmp_path)) == {"montages": []}

    # And a file that is not JSON at all.
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("not json")
    assert merge_pipeline_bindings(dict(payload), str(tmp_path)) == {"montages": []}


def test_a_scalar_port_takes_the_newest_name(tmp_path) -> None:
    """``leadfield`` and ``simulation`` are one value; the resolve tool writes newest last."""
    payload = {
        "leadfield_hdf": "",
        BINDINGS_KEY: [
            {
                "path": "b.json",
                "field": "leadfield_hdf",
                "port": "leadfield",
                "subject_ids": ["ernie"],
            }
        ],
    }
    with open(os.path.join(str(tmp_path), "b.json"), "w", encoding="utf-8") as fh:
        json.dump({"values": {"ernie": ["/old.hdf5", "/new.hdf5"]}}, fh)
    merged = merge_pipeline_bindings(dict(payload), str(tmp_path))
    assert merged == {"leadfield_hdf": "/new.hdf5"}


def test_an_ordinary_job_is_untouched(tmp_path) -> None:
    """Every non-pipeline job goes through this hook too; it must cost them nothing."""
    payload = {"subject_id": "ernie", "montages": ["hand-made"]}
    assert merge_pipeline_bindings(dict(payload), str(tmp_path)) == payload
