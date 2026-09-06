"""Document parsing, typed ports and validation reasons (``tit.pipeline.document``/``validate``).

No SimNIBS, no server, no filesystem: this is the pure half of the pipeline module, and it is the
half the canvas mirrors in TypeScript (``desktop/tests/unit/pipeline-graph.test.ts`` asserts the
same refusal table, so the two cannot drift into disagreeing about which wire is legal).
"""

from __future__ import annotations

import pytest

from tit.pipeline.document import (
    NODE_KINDS,
    PORT_TYPES,
    PORTS,
    PipelineDocument,
    PipelineDocumentError,
)
from tit.pipeline.validate import can_connect, topological_order, validate


def doc(nodes, edges=(), name="p"):
    return PipelineDocument.from_dict(
        {
            "version": 1,
            "name": name,
            "nodes": [
                {"id": i, "kind": k, "config": dict(c)} for i, k, c in nodes
            ],
            "edges": [{"from": a, "to": b, "port": p} for a, b, p in edges],
        }
    )


FOUR_NODE = (
    [
        ("pre1", "pre", {"subject_ids": ["ernie"], "create_m2m": True}),
        ("flex1", "flex", {"goal": "mean"}),
        ("sim1", "sim", {"montages": [{"name": "M1"}]}),
        ("an1", "analyzer", {"space": "mesh", "analysis_type": "spherical", "radius": 5.0}),
    ],
    [
        ("pre1", "flex1", "subjects"),
        ("pre1", "sim1", "subjects"),
        ("flex1", "sim1", "montages"),
        ("sim1", "an1", "subjects"),
        ("sim1", "an1", "simulation"),
    ],
)


# -- document ----------------------------------------------------------------------------------


def test_round_trips_through_to_dict() -> None:
    original = doc(*FOUR_NODE)
    again = PipelineDocument.from_dict(original.to_dict())
    assert again.to_dict() == original.to_dict()


@pytest.mark.parametrize(
    "payload, fragment",
    [
        ([], "must be a JSON object"),
        ({"version": 99, "nodes": []}, "unsupported pipeline document version"),
        ({"version": 1, "nodes": {}}, "must be arrays"),
        ({"version": 1, "nodes": [{"kind": "sim"}]}, "non-empty string id"),
        ({"version": 1, "nodes": [{"id": "a", "kind": "nope"}]}, "unknown kind"),
        (
            {
                "version": 1,
                "nodes": [{"id": "a", "kind": "sim"}, {"id": "b", "kind": "analyzer"}],
                "edges": [{"from": "a", "to": "b", "port": "bananas"}],
            },
            "unknown port",
        ),
    ],
)
def test_structural_problems_raise_with_a_reason(payload, fragment) -> None:
    with pytest.raises(PipelineDocumentError) as excinfo:
        PipelineDocument.from_dict(payload)
    assert fragment in str(excinfo.value)


def test_every_node_kind_has_ports_and_every_port_is_a_known_type() -> None:
    assert set(NODE_KINDS) == set(PORTS)
    for kind, ports in PORTS.items():
        assert set(ports.inputs) <= set(PORT_TYPES), kind
        assert set(ports.outputs) <= set(PORT_TYPES), kind
        assert set(ports.required) <= set(ports.inputs), kind


def test_every_node_kind_is_a_real_job_kind() -> None:
    """A pipeline introduces **no new job kind** (plan D1) -- it wires existing ones."""
    from tit.jobs.spec import JOB_KINDS

    assert set(NODE_KINDS) <= set(JOB_KINDS)


# -- validation --------------------------------------------------------------------------------


def test_the_four_node_pipeline_validates() -> None:
    result = validate(doc(*FOUR_NODE))
    assert result.ok, [i.message for i in result.errors]
    assert result.order == ["pre1", "flex1", "sim1", "an1"]


def test_cycle_is_reported_not_raised() -> None:
    result = validate(
        doc(
            [
                ("a", "sim", {"subject_ids": ["e"], "montages": [{"name": "M"}]}),
                ("b", "analyzer", {"simulation": "M"}),
            ],
            [("a", "b", "subjects"), ("b", "a", "subjects")],
        )
    )
    assert not result.ok
    assert "cycle" in " ".join(i.message for i in result.errors)


def test_unbound_required_input_names_the_node_and_the_port() -> None:
    result = validate(doc([("an1", "analyzer", {"subject_ids": ["e"]})]))
    messages = [i.message for i in result.errors]
    assert any("Simulation name" in m and "an1" in m for m in messages)


def test_config_can_satisfy_an_input_with_no_wire() -> None:
    """A Simulator whose montages were picked by hand is a legal one-node pipeline."""
    result = validate(
        doc([("sim1", "sim", {"subject_ids": ["ernie"], "montages": [{"name": "M1"}]})])
    )
    assert result.ok, [i.message for i in result.errors]


def test_isolated_node_is_a_warning_not_an_error() -> None:
    result = validate(
        doc(
            [
                ("sim1", "sim", {"subject_ids": ["e"], "montages": [{"name": "M"}]}),
                ("sim2", "sim", {"subject_ids": ["e"], "montages": [{"name": "N"}]}),
            ]
        )
    )
    assert result.ok
    assert any(i.level == "warning" and "not connected" in i.message for i in result.issues)


def test_port_wired_twice_is_an_error() -> None:
    result = validate(
        doc(
            [
                ("a", "sim", {"subject_ids": ["e"], "montages": [{"name": "M"}]}),
                ("b", "sim", {"subject_ids": ["e"], "montages": [{"name": "N"}]}),
                ("c", "analyzer", {"simulation": "M"}),
            ],
            [("a", "c", "subjects"), ("b", "c", "subjects")],
        )
    )
    assert not result.ok
    assert any("wired twice" in i.message for i in result.errors)


# -- can_connect (the canvas's refusal reasons) --------------------------------------------------


REFUSALS = [
    ("an1", "sim1", "montages", "does not produce"),
    ("pre1", "an1", "montages", "does not produce"),
    ("flex1", "pre1", "subjects", "does not take"),
    ("sim1", "sim1", "subjects", "cannot feed itself"),
    ("pre1", "sim1", "subjects", "already wired"),
]


@pytest.mark.parametrize("source, target, port, fragment", REFUSALS)
def test_can_connect_refuses_with_a_reason(source, target, port, fragment) -> None:
    ok, reason = can_connect(doc(*FOUR_NODE), source, target, port)
    assert not ok
    assert reason is not None and fragment in reason


def test_can_connect_refuses_a_wire_that_would_close_a_cycle() -> None:
    graph = doc(
        [
            ("flex1", "flex", {"subject_ids": ["e"], "goal": "mean"}),
            ("sim1", "sim", {"subject_ids": ["e"], "montages": [{"name": "M"}]}),
        ],
        [("flex1", "sim1", "montages")],
    )
    ok, reason = can_connect(graph, "sim1", "flex1", "subjects")
    assert not ok and reason == "that would make a cycle"


def test_can_connect_allows_a_legal_new_wire() -> None:
    graph = doc(
        [
            ("flex1", "flex", {"subject_ids": ["e"], "goal": "mean"}),
            ("sim1", "sim", {"subject_ids": ["e"], "montages": [{"name": "M"}]}),
        ]
    )
    assert can_connect(graph, "flex1", "sim1", "montages") == (True, None)


def test_topological_order_is_none_for_a_cycle() -> None:
    graph = doc(
        [("a", "sim", {}), ("b", "analyzer", {})],
        [("a", "b", "subjects"), ("b", "a", "subjects")],
    )
    assert topological_order(graph) is None
