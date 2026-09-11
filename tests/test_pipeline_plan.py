"""``tit.pipeline.plan`` — a pipeline is one job group whose ``after`` chain is its edges (D2/D3).

These tests touch the real config dataclasses (``tests/conftest.py`` mocks SimNIBS), so a config
shape the runner would reject fails here rather than at admission time in the container.
"""

from __future__ import annotations

import pytest

from tit.pipeline.document import PipelineDocument
from tit.pipeline.plan import (
    DYNAMIC_PORTS,
    KIND_CONFIG_CLASS,
    PipelinePlanError,
    STATIC_PORTS,
    plan_pipeline,
)
from tit.pipeline.document import PORT_TYPES


def build(nodes, edges=(), name="demo"):
    return PipelineDocument.from_dict(
        {
            "version": 1,
            "name": name,
            "nodes": [{"id": i, "kind": k, "config": dict(c)} for i, k, c in nodes],
            "edges": [{"from": a, "to": b, "port": p} for a, b, p in edges],
        }
    )


#: A real, minimal spherical ``AnalyzerConfig`` in wire form.
ANALYZER = {
    "analysis_type": "spherical",
    "space": "mesh",
    "center": [1.0, 2.0, 3.0],
    "radius": 5.0,
}


def sim_config(names, **extra) -> dict:
    """A real, minimal ``SimulationConfig`` in wire form with one montage per name."""
    from tit.config_io import serialize_config
    from tit.sim.config import Montage, SimulationConfig

    return serialize_config(
        SimulationConfig(
            subject_id="ernie",
            montages=[
                Montage(
                    name=name,
                    mode=Montage.Mode.NET,
                    electrode_pairs=[("E010", "E011"), ("E012", "E013")],
                    eeg_net="GSN-HydroCel-185.csv",
                )
                for name in names
            ],
            **extra,
        )
    )


def flex_config() -> dict:
    """A real, minimal ``FlexConfig`` in wire form (built from the dataclass, not hand-typed)."""
    from tit.config_io import serialize_config
    from tit.opt.config import FlexConfig

    return serialize_config(
        FlexConfig(
            subject_id="ernie",
            goal="mean",
            postproc="max_TI",
            current_mA=2.0,
            electrode=FlexConfig.ElectrodeConfig(),
            roi=FlexConfig.SubcorticalROI(atlas_path="aseg.mgz", label=[17]),
        )
    )


FOUR_NODE = build(
    [
        ("pre1", "pre", {"subject_ids": ["ernie", "101"], "create_m2m": True}),
        ("flex1", "flex", flex_config()),
        ("sim1", "sim", {}),
        (
            "an1",
            "analyzer",
            {
                "space": "mesh",
                "analysis_type": "spherical",
                "radius": 5.0,
                "center": [1, 2, 3],
            },
        ),
    ],
    [
        ("pre1", "flex1", "subjects"),
        ("pre1", "sim1", "subjects"),
        ("flex1", "sim1", "montages"),
        ("sim1", "an1", "subjects"),
        ("sim1", "an1", "simulation"),
    ],
)


def by_label(planned):
    return {job.label: job for job in planned}


def test_every_port_is_either_static_or_dynamic() -> None:
    """No port is left without a binding rule, and none has two."""
    assert STATIC_PORTS | DYNAMIC_PORTS == set(PORT_TYPES)
    assert not (STATIC_PORTS & DYNAMIC_PORTS)


def test_kind_config_classes_match_jobs_plans() -> None:
    """The copy of the kind->config-class table stays honest against ``tit.jobs.plans``."""
    from tit.jobs.plans import _KIND_CONFIG_CLASS

    for kind, class_name in _KIND_CONFIG_CLASS.items():
        if kind in KIND_CONFIG_CLASS:
            assert KIND_CONFIG_CLASS[kind] == class_name, kind


def test_subjects_flow_down_the_graph_from_the_pre_node() -> None:
    planned = plan_pipeline(FOUR_NODE)
    subjects = {job.label: job.subject_ids for job in planned}
    # Every non-cohort node fans out to one job per subject, and the subject list is `pre`'s.
    assert subjects["pre1:0"] == ["ernie"]
    assert subjects["pre1:1"] == ["101"]
    assert subjects["flex1:0"] == ["ernie"]
    assert subjects["flex1:1"] == ["101"]


def test_after_chain_is_exactly_the_edges() -> None:
    planned = plan_pipeline(FOUR_NODE)
    jobs = by_label(planned)
    # flex depends on pre (both subjects' pre jobs -- the DAG is per-node, not per-subject).
    assert jobs["flex1:0"].after_labels == ["pre1:0", "pre1:1"]
    # sim depends on pre *and* on the resolve step that binds flex's montage names.
    assert "sim1:resolve:montages" in jobs["sim1:0"].after_labels
    assert "pre1:0" in jobs["sim1:0"].after_labels
    # the resolve step itself waits for the optimizer.
    assert jobs["sim1:resolve:montages"].after_labels == ["flex1:0", "flex1:1"]
    # the analyzer waits for the simulator, through its own resolve step: this Simulator's
    # montages are themselves the optimizer's run-time output, so the simulation name it will
    # write is not knowable until it has run.
    assert jobs["an1:resolve:simulation"].after_labels == ["sim1:0", "sim1:1"]
    assert "an1:resolve:simulation" in jobs["an1:0"].after_labels


def test_a_dynamic_port_gets_a_resolve_step_that_is_an_ordinary_tools_job() -> None:
    resolve = by_label(plan_pipeline(FOUR_NODE))["sim1:resolve:montages"]
    assert resolve.kind == "tools"
    assert resolve.config["module"] == "tit.tools.pipeline_resolve"
    assert "--port" in resolve.config["args"] and "montages" in resolve.config["args"]
    # The allowlist in tit.jobs.kinds must actually accept it, or the job fails at admission.
    from tit.jobs.kinds import _resolve_tool_module_path

    assert _resolve_tool_module_path("tit.tools.pipeline_resolve") is not None


def test_a_static_simulation_binding_fans_the_analyzer_out_per_simulation() -> None:
    doc = build(
        [
            (
                "sim1",
                "sim",
                {**sim_config(["A", "B"]), "subject_ids": ["ernie"]},
            ),
            ("an1", "analyzer", ANALYZER),
        ],
        [("sim1", "an1", "subjects"), ("sim1", "an1", "simulation")],
    )
    planned = plan_pipeline(doc)
    analyzers = [j for j in planned if j.kind == "analyzer"]
    assert [j.config["simulation"] for j in analyzers] == ["A", "B"]


def test_every_job_carries_its_own_subject_only() -> None:
    for job in plan_pipeline(FOUR_NODE):
        if job.kind in ("pre",):
            assert job.config["subject_ids"] == job.subject_ids
        elif job.kind != "tools":
            assert job.config.get("subject_id") == job.subject_ids[0]


def test_pipeline_and_node_tags_trace_a_job_back_to_its_node() -> None:
    for job in plan_pipeline(FOUR_NODE):
        assert "pipeline:demo" in job.tags
        assert any(t.startswith("node:") for t in job.tags)


def test_an_invalid_graph_refuses_to_plan() -> None:
    # No cohort wired to it, and none in its own config: the Analyzer has no subjects at all.
    doc = build([("an1", "analyzer", {})])
    with pytest.raises(PipelinePlanError) as excinfo:
        plan_pipeline(doc)
    assert "does not validate" in str(excinfo.value)


def test_a_config_that_does_not_fit_its_kind_refuses_to_plan() -> None:
    doc = build([("sim1", "sim", {**sim_config(["M"]), "conductivity": "banana"})])
    with pytest.raises(PipelinePlanError) as excinfo:
        plan_pipeline(doc)
    assert "not a valid SimulationConfig" in str(excinfo.value)
    assert "banana" in str(excinfo.value)


def test_a_simulator_with_no_montages_refuses_to_run() -> None:
    doc = build(
        [
            ("sim1", "sim", sim_config(["M"])),
            ("an1", "analyzer", ANALYZER),
        ],
        [("sim1", "an1", "subjects"), ("sim1", "an1", "simulation")],
    )
    doc.node("sim1").config["montages"] = []
    with pytest.raises(PipelinePlanError, match="complete montages"):
        plan_pipeline(doc)


def test_roi_wire_copies_single_sphere_coordinates_and_refuses_atlas_guessing():
    config = flex_config()
    config["roi"] = {
        "_type": "SphericalROI",
        "x": [-12],
        "y": [3],
        "z": [45],
        "radius": 7,
        "use_mni": True,
    }
    graph = build(
        [
            ("flex", "flex", config),
            ("analysis", "analyzer", {**ANALYZER, "simulation": "known"}),
        ],
        [("flex", "analysis", "subjects"), ("flex", "analysis", "roi")],
    )
    output = next(job.config for job in plan_pipeline(graph) if job.kind == "analyzer")
    assert output["center"] == [-12, 3, 45]
    assert output["radius"] == 7
    assert output["coordinate_space"] == "mni"
    graph.node("flex").config["roi"] = flex_config()["roi"]
    with pytest.raises(PipelinePlanError, match="without changing its meaning"):
        plan_pipeline(graph)


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_search_result_requires_explicit_montage_selection(kind):
    graph = build(
        [("search", kind, {"subject_id": "101"}), ("sim", "sim", {})],
        [("search", "sim", "subjects"), ("search", "sim", "montages")],
    )
    with pytest.raises(
        PipelinePlanError, match="automatic .* montage binding is unsupported"
    ):
        plan_pipeline(graph)


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_multi_subject_search_requires_per_subject_leadfield_binding(kind):
    from tit.config_io import serialize_config
    from tit.opt.config import ExConfig, MExConfig

    cls = ExConfig if kind == "ex" else MExConfig
    config = serialize_config(
        cls(
            subject_id="ernie",
            leadfield_hdf="/project/sub-ernie/leadfield.hdf5",
            roi_name="target",
            electrodes=cls.PoolElectrodes(
                electrodes=["F3", "F4", "P3", "P4", "C3", "C4", "T7", "T8"]
            ),
        )
    )
    graph = build(
        [
            ("cohort", "subjects", {"subject_ids": ["ernie", "101"]}),
            ("search", kind, config),
        ],
        [("cohort", "search", "subjects")],
    )
    with pytest.raises(
        PipelinePlanError, match="static leadfield belongs to one subject"
    ):
        plan_pipeline(graph)
    graph.node("cohort").config["subject_ids"] = ["ernie"]
    jobs = plan_pipeline(graph)
    assert len(jobs) == 1
    assert jobs[0].config["leadfield_hdf"] == "/project/sub-ernie/leadfield.hdf5"
    wired = build(
        [
            ("cohort", "subjects", {"subject_ids": ["ernie", "101"]}),
            ("lf", "leadfield", {"eeg_net": "GSN-HydroCel-185"}),
            ("search", kind, config),
        ],
        [
            ("cohort", "lf", "subjects"),
            ("cohort", "search", "subjects"),
            ("lf", "search", "leadfield"),
        ],
    )
    searches = [job for job in plan_pipeline(wired) if job.kind == kind]
    assert [job.subject_ids for job in searches] == [["ernie"], ["101"]]
    assert all("_pipeline_bindings" in job.config for job in searches)
