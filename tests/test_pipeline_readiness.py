"""The readiness table: may *these* subjects be wired into *this* node?

A port type says what a wire carries. It says nothing about whether the subjects on it have what
the target needs, and before this table existed the canvas would happily let you build
``Subjects(raw data only) -> Analyzer``, submit it, and watch it fail one job per subject twenty
minutes later. These tests pin the table, its propagation along a chain, and the wording of the
refusal -- which names the subjects, because "2 subjects are not ready" does not tell you which
two rows to go and look at.

Pure: no server, no filesystem, no SimNIBS.
"""

from __future__ import annotations

import pytest

from tit.pipeline.document import NODE_KINDS, PipelineDocument
from tit.pipeline.validate import (
    CAPABILITIES,
    CAPABILITY_LABELS,
    KIND_READINESS,
    can_connect,
    capabilities_at,
    readiness_from_overview,
    unmet,
    validate,
)


def doc(nodes, edges=()):
    return PipelineDocument.from_dict(
        {
            "version": 1,
            "name": "p",
            "nodes": [{"id": i, "kind": k, "config": dict(c)} for i, k, c in nodes],
            "edges": [{"from": a, "to": b, "port": p} for a, b, p in edges],
        }
    )


def cohort(*subject_ids):
    return ("s1", "subjects", {"subject_ids": list(subject_ids)})


#: ernie is a finished subject; 102 and test have been converted and nothing else.
PROJECT = {
    "ernie": {"raw", "m2m", "simulation"},
    "102": {"raw"},
    "test": {"raw"},
}


# -- the table itself ----------------------------------------------------------------------------


def test_every_kind_has_a_readiness_entry_over_known_capabilities() -> None:
    assert set(KIND_READINESS) == set(NODE_KINDS)
    for kind, entry in KIND_READINESS.items():
        assert set(entry.requires) <= set(CAPABILITIES), kind
        assert set(entry.produces) <= set(CAPABILITIES), kind
    assert set(CAPABILITY_LABELS) == set(CAPABILITIES)


def test_the_cohort_node_requires_and_produces_nothing() -> None:
    """What a cohort's subjects have is a fact about the project, not something a node confers."""
    assert KIND_READINESS["subjects"].requires == ()
    assert KIND_READINESS["subjects"].produces == ()


@pytest.mark.parametrize(
    "kind, requires",
    [
        ("pre", ("raw",)),
        ("leadfield", ("m2m",)),
        ("flex", ("m2m",)),
        ("ex", ("m2m", "leadfield")),
        ("mex", ("m2m", "leadfield")),
        ("sim", ("m2m",)),
        ("analyzer", ("simulation",)),
        ("source", ("m2m",)),
        ("stats", ("simulation",)),
    ],
)
def test_what_each_kind_requires(kind, requires) -> None:
    assert KIND_READINESS[kind].requires == requires


@pytest.mark.parametrize(
    "kind, produces",
    [("pre", ("m2m",)), ("leadfield", ("leadfield",)), ("sim", ("simulation",))],
)
def test_what_a_kind_leaves_behind_for_the_nodes_after_it(kind, produces) -> None:
    assert KIND_READINESS[kind].produces == produces


# -- reading the project's own facts ---------------------------------------------------------------


def test_readiness_is_read_from_the_overview_the_page_already_shows() -> None:
    overview = {
        "subjects": [
            {
                "id": "ernie",
                "raw": "present",
                "m2m": "present",
                "leadfield": "absent",
                "counts": {"simulations": 3},
            },
            {
                "id": "102",
                "raw": "present",
                "m2m": "absent",
                "leadfield": "absent",
                "counts": {"simulations": 0},
            },
        ]
    }
    assert readiness_from_overview(overview) == {
        "ernie": {"raw", "m2m", "simulation"},
        "102": {"raw"},
    }


def test_a_partial_presence_is_not_ready_except_for_leadfields() -> None:
    """`partial` means "some of it". For a head model that is not a head model.

    A leadfield is the exception because it is per EEG net, not per subject: a subject with one
    net's leadfield genuinely has *a* leadfield, and which net a search needs is the search's own
    business.
    """
    overview = {
        "subjects": [
            {"id": "a", "raw": "partial", "m2m": "partial", "leadfield": "partial", "counts": {}}
        ]
    }
    assert readiness_from_overview(overview) == {"a": {"leadfield"}}


# -- propagation along the graph -------------------------------------------------------------------


def test_a_cohorts_capabilities_are_the_projects_facts_about_it() -> None:
    graph = doc([cohort("ernie", "102")])
    assert capabilities_at(graph, "s1", PROJECT) == {
        "ernie": {"raw", "m2m", "simulation"},
        "102": {"raw"},
    }


def test_a_node_confers_what_it_produces_on_everything_downstream() -> None:
    graph = doc(
        [cohort("102"), ("p1", "pre", {}), ("m1", "sim", {})],
        [("s1", "p1", "subjects"), ("p1", "m1", "subjects")],
    )
    # 102 arrives at the Simulator with a head model it did not have at the cohort, because
    # Pre-processing is planned in between and that is what Pre-processing makes.
    assert capabilities_at(graph, "s1", PROJECT)["102"] == {"raw"}
    assert capabilities_at(graph, "m1", PROJECT)["102"] == {"raw", "m2m"}
    assert unmet("sim", capabilities_at(graph, "m1", PROJECT)) == []


def test_the_whole_raw_to_analysis_chain_validates_for_raw_only_subjects() -> None:
    graph = doc(
        [
            cohort("102", "test"),
            ("p1", "pre", {"create_m2m": True}),
            ("m1", "sim", {"montages": [{"name": "M"}]}),
            ("a1", "analyzer", {"space": "mesh"}),
        ],
        [("s1", "p1", "subjects"), ("p1", "m1", "subjects"), ("m1", "a1", "subjects")],
    )
    result = validate(graph, PROJECT)
    assert result.ok, [i.message for i in result.errors]


def test_a_cycle_does_not_hang_the_capability_walk() -> None:
    graph = doc(
        [("a", "sim", {}), ("b", "analyzer", {})],
        [("a", "b", "subjects"), ("b", "a", "subjects")],
    )
    assert capabilities_at(graph, "a", PROJECT) == {}


# -- the refusal, and its wording --------------------------------------------------------------------


def test_raw_only_subjects_may_be_wired_to_preprocessing_and_to_nothing_else() -> None:
    for kind, accepted in [
        ("pre", True),
        ("sim", False),
        ("flex", False),
        ("analyzer", False),
        ("leadfield", False),
    ]:
        graph = doc([cohort("102", "test"), ("n1", kind, {})])
        ok, reason = can_connect(graph, "s1", "n1", "subjects", PROJECT)
        assert ok is accepted, (kind, reason)


def test_subjects_with_a_head_model_reach_the_simulator_but_not_the_analyzer() -> None:
    graph = doc([cohort("ernie"), ("m1", "sim", {}), ("a1", "analyzer", {})])
    assert can_connect(graph, "s1", "m1", "subjects", PROJECT) == (True, None)
    # ernie *does* have simulations, so the Analyzer accepts too -- that is the point of the
    # capability being a project fact rather than a graph fact.
    assert can_connect(graph, "s1", "a1", "subjects", PROJECT) == (True, None)


def test_the_refusal_names_the_subjects_that_are_not_ready_and_only_those() -> None:
    graph = doc([cohort("ernie", "102", "test"), ("a1", "analyzer", {})])
    ok, reason = can_connect(graph, "s1", "a1", "subjects", PROJECT)
    assert not ok
    assert reason == "102, test have no simulations"
    assert "ernie" not in reason


def test_one_missing_subject_reads_as_one_subject() -> None:
    graph = doc([cohort("ernie", "102"), ("m1", "sim", {})])
    ok, reason = can_connect(graph, "s1", "m1", "subjects", PROJECT)
    assert not ok and reason == "102 has no head model"


def test_a_search_says_leadfield_when_the_head_model_is_already_there() -> None:
    graph = doc([cohort("ernie"), ("e1", "ex", {})])
    ok, reason = can_connect(graph, "s1", "e1", "subjects", PROJECT)
    assert not ok and reason == "ernie has no leadfield"


def test_the_receipt_and_the_drag_refuse_for_the_same_reason() -> None:
    """Same table, same sentence -- the canvas cannot promise what the server will not run."""
    graph = doc([cohort("ernie", "102"), ("a1", "analyzer", {})], [("s1", "a1", "subjects")])
    errors = [i for i in validate(graph, PROJECT).errors if i.code == "not_ready"]
    assert len(errors) == 1
    assert errors[0].node_id == "a1"
    assert errors[0].message.endswith("102 has no simulations")

    unwired = doc([cohort("ernie", "102"), ("a1", "analyzer", {})])
    _, reason = can_connect(unwired, "s1", "a1", "subjects", PROJECT)
    assert reason is not None and errors[0].message.endswith(reason)


def test_without_readiness_the_graph_is_checked_for_shape_only() -> None:
    """A caller with no project bound still gets the structural answer, and no false refusal."""
    graph = doc([cohort("102"), ("a1", "analyzer", {})], [("s1", "a1", "subjects")])
    assert validate(graph).ok
    assert not validate(graph, PROJECT).ok
    assert can_connect(graph, "s1", "a1", "subjects") == (False, "Subjects is already wired from this node")


def test_a_subject_the_project_does_not_know_has_nothing() -> None:
    graph = doc([cohort("ghost"), ("m1", "sim", {})])
    ok, reason = can_connect(graph, "s1", "m1", "subjects", PROJECT)
    assert not ok and reason == "ghost has no head model"
