"""The pipeline document: nodes, edges, typed ports (plan §1-D, D1).

A *pipeline* is a DAG whose nodes are **existing job kinds** carrying **exactly the config the
matching v3 page already builds** -- there is no new job kind, no new runner and no runtime graph
engine.  Edges are typed: an edge carries one named **output** of the upstream node into the
matching **input** of the downstream node (``subjects``, ``montages``, ``simulation``, ``roi``,
``leadfield``), which is what makes "Optimizer -> Simulator" mean *the simulator's montage list is
the flex result* rather than a drawn line with no semantics.

This module is pure data with **no heavy imports**: it is reached from
``tit.server.routes.pipelines`` at import time and must stay inside the 400 ms route-import budget
(``dev/route_import_guard.py``).  Everything that needs ``tit.config_io`` (and therefore SimNIBS)
is imported lazily inside :mod:`tit.pipeline.plan`.

The wire shape is ``contracts/pipeline.schema.json``::

    {"version": 1,
     "name": "my pipeline",
     "nodes": [{"id": "n1", "kind": "flex", "label": "...", "config": {...},
                "position": {"x": 0, "y": 0}}],
     "edges": [{"from": "n1", "to": "n2", "port": "montages"}]}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DOCUMENT_VERSION",
    "NODE_KINDS",
    "PORT_TYPES",
    "PORTS",
    "Edge",
    "Node",
    "PipelineDocument",
    "PipelineDocumentError",
    "node_inputs",
    "node_outputs",
    "port_label",
]

#: ``pipeline.schema.json``'s ``version``. Bumped only for a breaking document change.
DOCUMENT_VERSION = 1

#: Port types an edge may carry. Each is a *value* produced by one node and consumed by another.
PORT_TYPES: tuple[str, ...] = (
    "subjects",
    "montages",
    "simulation",
    "roi",
    "leadfield",
)

_PORT_LABELS: dict[str, str] = {
    "subjects": "Subjects",
    "montages": "Montage names",
    "simulation": "Simulation name",
    "roi": "ROI",
    "leadfield": "Leadfield",
}


def port_label(port: str) -> str:
    """Human wording for *port*, for a refusal reason or a canvas handle tooltip."""
    return _PORT_LABELS.get(port, port)


@dataclass(frozen=True)
class _KindPorts:
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    #: Inputs that must be bound by an edge *or* already satisfied by the node's own config.
    required: tuple[str, ...] = ()


#: kind -> its typed ports. Every kind here is an existing :data:`tit.jobs.spec.JOB_KINDS` entry.
PORTS: dict[str, _KindPorts] = {
    # Preprocessing produces the subject set every downstream node runs over.
    "pre": _KindPorts(inputs=(), outputs=("subjects",)),
    "leadfield": _KindPorts(inputs=("subjects",), outputs=("subjects", "leadfield")),
    "flex": _KindPorts(inputs=("subjects", "roi"), outputs=("subjects", "montages", "roi")),
    "ex": _KindPorts(
        inputs=("subjects", "roi", "leadfield"),
        outputs=("subjects", "montages", "roi"),
    ),
    "mex": _KindPorts(
        inputs=("subjects", "roi", "leadfield"),
        outputs=("subjects", "montages", "roi"),
    ),
    "sim": _KindPorts(
        inputs=("subjects", "montages"),
        outputs=("subjects", "simulation"),
        required=("subjects",),
    ),
    "analyzer": _KindPorts(
        inputs=("subjects", "simulation", "roi"),
        outputs=("subjects",),
        required=("subjects", "simulation"),
    ),
    "source": _KindPorts(inputs=("subjects",), outputs=("subjects",), required=("subjects",)),
    "stats": _KindPorts(inputs=("subjects",), outputs=(), required=("subjects",)),
}

#: Node kinds the canvas offers, in palette order.
NODE_KINDS: tuple[str, ...] = (
    "pre",
    "leadfield",
    "flex",
    "ex",
    "mex",
    "sim",
    "analyzer",
    "source",
    "stats",
)


def node_inputs(kind: str) -> tuple[str, ...]:
    ports = PORTS.get(kind)
    return ports.inputs if ports else ()


def node_outputs(kind: str) -> tuple[str, ...]:
    ports = PORTS.get(kind)
    return ports.outputs if ports else ()


class PipelineDocumentError(ValueError):
    """A document that is not even shaped like a pipeline (bad JSON structure, unknown kind)."""


@dataclass
class Node:
    id: str
    kind: str
    config: dict[str, Any] = field(default_factory=dict)
    label: str | None = None
    position: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "config": dict(self.config),
            "position": {
                "x": float(self.position.get("x", 0.0)),
                "y": float(self.position.get("y", 0.0)),
            },
        }
        if self.label:
            out["label"] = self.label
        return out

    @property
    def display_name(self) -> str:
        return self.label or f"{self.kind} ({self.id})"


@dataclass
class Edge:
    source: str
    target: str
    port: str

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.source, "to": self.target, "port": self.port}


@dataclass
class PipelineDocument:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    name: str = "pipeline"
    version: int = DOCUMENT_VERSION

    # -- construction ------------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Any) -> "PipelineDocument":
        """Parse a wire document. Raises :class:`PipelineDocumentError` on a shape problem.

        Structural problems (not a dict, a node without an id) are errors here; *semantic*
        problems (a cycle, an unbound required input) are :mod:`tit.pipeline.validate`'s job and
        come back as reasons a user can act on, not exceptions.
        """
        if not isinstance(data, dict):
            raise PipelineDocumentError("pipeline document must be a JSON object")
        version = data.get("version", DOCUMENT_VERSION)
        if version != DOCUMENT_VERSION:
            raise PipelineDocumentError(
                f"unsupported pipeline document version {version!r} "
                f"(this build reads version {DOCUMENT_VERSION})"
            )
        raw_nodes = data.get("nodes")
        raw_edges = data.get("edges", [])
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise PipelineDocumentError("`nodes` and `edges` must be arrays")

        nodes: list[Node] = []
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                raise PipelineDocumentError("each node must be an object")
            node_id = raw.get("id")
            kind = raw.get("kind")
            if not isinstance(node_id, str) or not node_id:
                raise PipelineDocumentError("each node needs a non-empty string id")
            if kind not in PORTS:
                raise PipelineDocumentError(
                    f"node {node_id!r}: unknown kind {kind!r} (expected one of {NODE_KINDS})"
                )
            config = raw.get("config") or {}
            if not isinstance(config, dict):
                raise PipelineDocumentError(f"node {node_id!r}: config must be an object")
            position = raw.get("position") or {}
            if not isinstance(position, dict):
                raise PipelineDocumentError(f"node {node_id!r}: position must be an object")
            label = raw.get("label")
            if label is not None and not isinstance(label, str):
                raise PipelineDocumentError(f"node {node_id!r}: label must be a string")
            nodes.append(
                Node(
                    id=node_id,
                    kind=kind,
                    config=dict(config),
                    label=label,
                    position={
                        "x": float(position.get("x", 0.0) or 0.0),
                        "y": float(position.get("y", 0.0) or 0.0),
                    },
                )
            )

        edges: list[Edge] = []
        for raw in raw_edges:
            if not isinstance(raw, dict):
                raise PipelineDocumentError("each edge must be an object")
            source = raw.get("from")
            target = raw.get("to")
            port = raw.get("port")
            if not isinstance(source, str) or not isinstance(target, str):
                raise PipelineDocumentError("each edge needs string `from` and `to` node ids")
            if port not in PORT_TYPES:
                raise PipelineDocumentError(
                    f"edge {source}->{target}: unknown port {port!r} "
                    f"(expected one of {PORT_TYPES})"
                )
            edges.append(Edge(source=source, target=target, port=port))

        name = data.get("name") or "pipeline"
        if not isinstance(name, str):
            raise PipelineDocumentError("`name` must be a string")
        return cls(nodes=nodes, edges=edges, name=name, version=DOCUMENT_VERSION)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    # -- lookups -----------------------------------------------------------------------------

    def node(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def incoming(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == node_id]

    def outgoing(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node_id]
