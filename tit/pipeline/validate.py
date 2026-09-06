"""Graph validation with reasons (plan §1-D, D3).

Every refusal is a sentence a user can act on, keyed to the node or edge it is about -- the canvas
renders `can_connect`'s reason inline while a wire is being dragged, and `validate`'s issues in the
receipt before Run.  Structural garbage (a node with no id) raises from
:mod:`tit.pipeline.document`; everything here is a *finding*, never an exception.

No heavy imports: this module is on the route-import path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tit.pipeline.document import (
    Edge,
    PipelineDocument,
    PORTS,
    node_inputs,
    node_outputs,
    port_label,
)

__all__ = [
    "Issue",
    "ValidationResult",
    "can_connect",
    "satisfied_by_config",
    "topological_order",
    "validate",
]


@dataclass
class Issue:
    """One finding. ``level`` is ``"error"`` (blocks Run) or ``"warning"`` (does not)."""

    level: str
    message: str
    node_id: str | None = None
    edge: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"level": self.level, "message": self.message}
        if self.node_id is not None:
            out["node_id"] = self.node_id
        if self.edge is not None:
            out["edge"] = self.edge
        return out


@dataclass
class ValidationResult:
    ok: bool
    issues: list[Issue]
    #: Node ids in a topological (dependency-first) order; empty when the graph has a cycle.
    order: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [i.to_dict() for i in self.issues],
            "order": list(self.order),
        }

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]


def satisfied_by_config(kind: str, port: str, config: dict[str, Any]) -> bool:
    """Is *port* already provided by the node's **own** config, with no incoming edge?

    This is what lets a pipeline start at a Simulator node whose montages were picked by hand:
    the port is an input, it just is not bound by a wire.
    """
    config = config or {}
    if port == "subjects":
        subject_ids = config.get("subject_ids")
        if isinstance(subject_ids, list) and any(str(s).strip() for s in subject_ids):
            return True
        return bool(str(config.get("subject_id") or "").strip())
    if port == "montages":
        montages = config.get("montages")
        return isinstance(montages, list) and len(montages) > 0
    if port == "simulation":
        return bool(str(config.get("simulation") or "").strip())
    if port == "leadfield":
        return bool(str(config.get("leadfield_hdf") or "").strip())
    if port == "roi":
        if config.get("roi") not in (None, {}, []):
            return True
        for key in ("roi_name", "roi_names", "region", "atlas", "center"):
            value = config.get(key)
            if value not in (None, "", [], {}):
                return True
        return False
    return False  # pragma: no cover - PORT_TYPES is closed


def can_connect(
    doc: PipelineDocument, source: str, target: str, port: str
) -> tuple[bool, str | None]:
    """May this wire be drawn? ``(True, None)`` or ``(False, reason)``.

    The canvas calls the mirror of this in TypeScript while dragging and this one on the server
    when the document is validated; ``tests/test_pipeline_validate.py`` and
    ``desktop/tests/unit/pipeline-graph.test.ts`` assert the same table of refusals so the two
    cannot drift into disagreeing about which wire is legal.
    """
    src = doc.node(source)
    dst = doc.node(target)
    if src is None:
        return False, f"no such node: {source}"
    if dst is None:
        return False, f"no such node: {target}"
    if source == target:
        return False, "a node cannot feed itself"
    if port not in node_outputs(src.kind):
        return False, f"{src.kind} does not produce {port_label(port)}"
    if port not in node_inputs(dst.kind):
        return False, f"{dst.kind} does not take {port_label(port)}"
    for edge in doc.incoming(target):
        if edge.port == port:
            if edge.source == source:
                return False, f"{port_label(port)} is already wired from this node"
            return False, (
                f"{port_label(port)} is already wired from "
                f"{doc.node(edge.source).display_name if doc.node(edge.source) else edge.source}"
            )
    if _reaches(doc, target, source):
        return False, "that would make a cycle"
    return True, None


def _reaches(doc: PipelineDocument, start: str, goal: str) -> bool:
    """Is *goal* downstream of *start* (following edges forwards)?"""
    seen: set[str] = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current == goal:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(e.target for e in doc.outgoing(current))
    return False


def topological_order(doc: PipelineDocument) -> list[str] | None:
    """Node ids dependency-first (Kahn, stable in document order), or ``None`` for a cycle."""
    ids = [n.id for n in doc.nodes]
    indegree = dict.fromkeys(ids, 0)
    for edge in doc.edges:
        if edge.target in indegree and edge.source in indegree:
            indegree[edge.target] += 1
    ready = [i for i in ids if indegree[i] == 0]
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for edge in doc.outgoing(current):
            if edge.target not in indegree:
                continue
            indegree[edge.target] -= 1
            if indegree[edge.target] == 0:
                # Preserve document order among newly-ready nodes.
                ready.append(edge.target)
                ready.sort(key=ids.index)
    return order if len(order) == len(ids) else None


def validate(doc: PipelineDocument) -> ValidationResult:
    """Every reason this pipeline cannot run, plus a topological order when it can."""
    issues: list[Issue] = []
    ids = [n.id for n in doc.nodes]

    if not doc.nodes:
        issues.append(Issue("error", "a pipeline needs at least one node"))

    seen: set[str] = set()
    for node_id in ids:
        if node_id in seen:
            issues.append(Issue("error", f"duplicate node id: {node_id}", node_id=node_id))
        seen.add(node_id)

    # -- edges ---------------------------------------------------------------------------------
    known = set(ids)
    bound: dict[tuple[str, str], Edge] = {}
    for edge in doc.edges:
        wire = edge.to_dict()
        if edge.source not in known or edge.target not in known:
            issues.append(
                Issue("error", "edge refers to a node that is not on the canvas", edge=wire)
            )
            continue
        src = doc.node(edge.source)
        dst = doc.node(edge.target)
        assert src is not None and dst is not None  # guarded by `known` above
        if edge.source == edge.target:
            issues.append(Issue("error", "a node cannot feed itself", edge=wire))
            continue
        if edge.port not in node_outputs(src.kind):
            issues.append(
                Issue(
                    "error",
                    f"{src.display_name} does not produce {port_label(edge.port)}",
                    edge=wire,
                )
            )
            continue
        if edge.port not in node_inputs(dst.kind):
            issues.append(
                Issue(
                    "error",
                    f"{dst.display_name} does not take {port_label(edge.port)}",
                    edge=wire,
                )
            )
            continue
        key = (edge.target, edge.port)
        if key in bound:
            issues.append(
                Issue(
                    "error",
                    f"{dst.display_name} has {port_label(edge.port)} wired twice",
                    edge=wire,
                )
            )
            continue
        bound[key] = edge

    order = topological_order(doc)
    if order is None:
        issues.append(Issue("error", "the pipeline has a cycle"))
        order = []

    # -- required inputs -----------------------------------------------------------------------
    for node in doc.nodes:
        ports = PORTS[node.kind]
        for port in ports.required:
            if (node.id, port) in bound:
                continue
            if satisfied_by_config(node.kind, port, node.config):
                continue
            issues.append(
                Issue(
                    "error",
                    f"{node.display_name} needs {port_label(port)}: wire it from an upstream "
                    f"node or set it in the node's form",
                    node_id=node.id,
                )
            )
        if not node.config:
            issues.append(
                Issue(
                    "warning",
                    f"{node.display_name} has no configuration yet",
                    node_id=node.id,
                )
            )

    # -- isolated nodes -------------------------------------------------------------------------
    if len(doc.nodes) > 1:
        wired = {e.source for e in doc.edges} | {e.target for e in doc.edges}
        for node in doc.nodes:
            if node.id not in wired:
                issues.append(
                    Issue(
                        "warning",
                        f"{node.display_name} is not connected to anything; it will run on its own",
                        node_id=node.id,
                    )
                )

    ok = not any(i.level == "error" for i in issues)
    return ValidationResult(ok=ok, issues=issues, order=order if ok else order)
