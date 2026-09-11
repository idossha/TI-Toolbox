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

import pytest

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

    (run_dir / "electrode_positions.json").write_text(
        json.dumps(
            {"optimized_positions": [[1, 2, 3], [4, 5, 6], [-1, -2, -3], [-4, -5, -6]]}
        )
    )
    monkeypatch.setattr(
        pipeline_resolve,
        "producer_records",
        lambda _: (
            [
                {
                    "kind": "flex",
                    "subject_ids": ["ernie"],
                    "config": {},
                    "events": [
                        {"type": "result", "outputs": {"output_folder": str(run_dir)}}
                    ],
                }
            ],
            "run123",
        ),
    )
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
    from tit.jobs.bindings import binding_path

    written = json.loads(
        open(binding_path(str(project), descriptor["path"], run_id="run123")).read()
    )
    montage = written["values"]["ernie"][0]
    assert montage["electrode_pairs"] == [
        [[1, 2, 3], [4, 5, 6]],
        [[-1, -2, -3], [-4, -5, -6]],
    ]
    assert montage["mode"] == "flex_free"


def test_the_resolve_tool_refuses_a_traversing_pipeline_or_node(
    tmp_path, monkeypatch
) -> None:
    """RUN-06: --pipeline and --node become path components of the file it writes."""
    from tit.tools import pipeline_resolve

    project = tmp_path / "project"
    (project / "code").mkdir(parents=True)
    monkeypatch.setenv("TI_PROJECT_DIR", str(project))
    base = ["--port", "montages", "--subjects", "ernie", "--project-dir", str(project)]
    for pipeline, node in (
        ("../../../escape", "sim1"),
        ("demo", "../../escape"),
        ("/abs", "sim1"),
    ):
        with pytest.raises(SystemExit):
            pipeline_resolve.main(["--pipeline", pipeline, "--node", node, *base])
    assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.parent.glob("escape*"))


def test_the_resolve_tool_refuses_an_invalid_subject_id(tmp_path, monkeypatch) -> None:
    from tit.tools import pipeline_resolve

    project = tmp_path / "project"
    project.mkdir()
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
                "--subjects",
                "../../evil",
                "--project-dir",
                str(project),
            ]
        )
        == 2
    )


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


def test_a_missing_or_unreadable_binding_refuses_admission(tmp_path) -> None:
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
    with pytest.raises(ValueError, match="binding"):
        merge_pipeline_bindings(dict(payload), str(tmp_path))

    # File present, but the search wrote no run for this subject.
    target = os.path.join(str(tmp_path), payload[BINDINGS_KEY][0]["path"])
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump({"values": {"ernie": []}}, fh)
    with pytest.raises(ValueError, match="binding"):
        merge_pipeline_bindings(dict(payload), str(tmp_path))

    # And a file that is not JSON at all.
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("not json")
    with pytest.raises(ValueError, match="binding"):
        merge_pipeline_bindings(dict(payload), str(tmp_path))


def test_a_scalar_port_refuses_ambiguous_outputs(tmp_path) -> None:
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
    with pytest.raises(ValueError, match="exactly one"):
        merge_pipeline_bindings(dict(payload), str(tmp_path))


def test_an_ordinary_job_is_untouched(tmp_path) -> None:
    """Every non-pipeline job goes through this hook too; it must cost them nothing."""
    payload = {"subject_id": "ernie", "montages": ["hand-made"]}
    assert merge_pipeline_bindings(dict(payload), str(tmp_path)) == payload


def test_dynamic_bindings_use_only_named_producer_results_per_subject(tmp_path):
    from tit import get_path_manager
    from tit.tools.pipeline_resolve import resolve_from_producers

    pm = get_path_manager(str(tmp_path))
    # A historical file and another subject must never influence the binding.
    historical = tmp_path / "unrelated.hdf5"
    historical.write_bytes(b"old")
    records = [
        {
            "kind": "leadfield",
            "subject_ids": ["101"],
            "config": {},
            "events": [
                {"type": "result", "outputs": {"leadfield_hdf": "/expected/101.hdf5"}}
            ],
        },
        {
            "kind": "leadfield",
            "subject_ids": ["102"],
            "config": {},
            "events": [
                {"type": "result", "outputs": {"leadfield_hdf": "/expected/102.hdf5"}}
            ],
        },
    ]
    assert resolve_from_producers(pm, "leadfield", "leadfield", ["101"], records) == {
        "101": ["/expected/101.hdf5"]
    }
    with pytest.raises(ValueError, match="No leadfield producer"):
        resolve_from_producers(pm, "leadfield", "leadfield", ["103"], records)


def test_same_pipeline_runs_cannot_share_binding_files(tmp_path):
    from pathlib import Path
    from tit.jobs.bindings import binding_path

    relative = bindings_relpath("same", "sim", "montages")
    for run, name in [("run1", "first"), ("run2", "second")]:
        path = Path(binding_path(str(tmp_path), relative, run_id=run))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"values": {"101": [{"name": name}]}}))
    payload = {
        BINDINGS_KEY: [
            {
                "path": relative,
                "field": "montages",
                "port": "montages",
                "subject_ids": ["101"],
            }
        ]
    }
    assert merge_pipeline_bindings(dict(payload), str(tmp_path), run_id="run1")[
        "montages"
    ] == [{"name": "first"}]
    assert merge_pipeline_bindings(dict(payload), str(tmp_path), run_id="run2")[
        "montages"
    ] == [{"name": "second"}]


def test_notebook_dynamic_chain_passes_real_montage_to_simulation_and_analysis(
    tmp_path, monkeypatch
):
    from pathlib import Path
    from tit import get_path_manager
    from tit.jobs import kinds
    from tit.pipeline.notebook import notebook_json
    import tit.pipeline.execution as execution

    graph = build(
        [
            ("subjects", "subjects", {"subject_ids": ["101", "102"]}),
            ("flex", "flex", flex_config()),
            ("sim", "sim", {}),
            ("an", "analyzer", ANALYZER),
        ],
        [
            ("subjects", "flex", "subjects"),
            ("flex", "sim", "subjects"),
            ("flex", "sim", "montages"),
            ("sim", "an", "subjects"),
            ("sim", "an", "simulation"),
        ],
    )
    pm = get_path_manager(str(tmp_path))
    captured = []
    monkeypatch.setattr(
        kinds, "command_for", lambda kind, config, path, **_: [kind, path]
    )

    def run(argv, *, env, check):
        config = json.loads(Path(argv[1]).read_text())
        captured.append((argv[0], config))
        outputs = {}
        if argv[0] == "flex":
            folder = Path(pm.flex_search(config["subject_id"])) / "exact_run"
            folder.mkdir(parents=True)
            offset = 1 if config["subject_id"] == "101" else 100
            (folder / "electrode_positions.json").write_text(
                json.dumps(
                    {
                        "optimized_positions": [
                            [offset + i, i + 2, i + 3] for i in range(4)
                        ]
                    }
                )
            )
            outputs = {"output_folder": str(folder)}
        Path(env["TIT_EVENTS_FILE"]).write_text(
            json.dumps({"type": "result", "outputs": outputs}) + "\n"
        )

    monkeypatch.setattr(execution.subprocess, "run", run)
    scope = {}
    for cell in notebook_json(graph, project_dir=str(tmp_path))["cells"]:
        if cell["cell_type"] == "code":
            exec(cell["source"], scope)
    simulations = {c["subject_id"]: c for kind, c in captured if kind == "sim"}
    assert simulations["101"]["montages"][0]["electrode_pairs"][0][0] == [1, 2, 3]
    assert simulations["102"]["montages"][0]["electrode_pairs"][0][0] == [100, 2, 3]
    for kind, config in captured:
        if kind == "analyzer":
            assert (
                config["simulation"]
                == simulations[config["subject_id"]]["montages"][0]["name"]
            )
