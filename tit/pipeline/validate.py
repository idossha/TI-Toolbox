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
    "CAPABILITIES",
    "CAPABILITY_LABELS",
    "ISSUE_CODES",
    "Issue",
    "KIND_READINESS",
    "Readiness",
    "ValidationResult",
    "can_connect",
    "capabilities_at",
    "readiness_from_overview",
    "satisfied_by_config",
    "topological_order",
    "validate",
]


# -- the readiness table -------------------------------------------------------------------------
#
# One table, in one place, answering one question: **may these subjects be wired into this node?**
#
# Before it existed the canvas would let any wire be drawn between compatible port *types*, so
# `Subjects(raw data only) -> Analyzer` was a graph you could build, submit, and watch fail one job
# at a time twenty minutes later. A port type says what a wire *carries*; it says nothing about
# whether the subjects on it have what the target needs. This says the second thing, and it says it
# at drag time, in the receipt and on the server, from the same data.

#: What a subject can *have*. Each is a fact `GET /api/catalog/overview` already reports.
CAPABILITIES: tuple[str, ...] = ("raw", "m2m", "leadfield", "simulation")

CAPABILITY_LABELS: dict[str, str] = {
    "raw": "raw MRI",
    "m2m": "head model",
    "leadfield": "leadfield",
    "simulation": "simulations",
}


@dataclass(frozen=True)
class _KindReadiness:
    #: Every capability each subject reaching this node must already have.
    requires: tuple[str, ...] = ()
    #: What running this node gives its subjects, for the nodes downstream of it.
    produces: tuple[str, ...] = ()


#: kind -> what it needs of a subject, and what it leaves behind.
#:
#: This is what makes `Subjects(raw) -> Pre -> Simulator -> Analyzer` validate while
#: `Subjects(raw) -> Simulator` does not: `pre` *produces* `m2m`, so by the time the wire reaches
#: the Simulator its subjects have a head model even though they did not when the graph started.
KIND_READINESS: dict[str, _KindReadiness] = {
    # The cohort itself needs nothing and produces nothing: what its subjects have is a fact about
    # the project, read from the overview, not something the graph confers.
    "subjects": _KindReadiness(),
    "pre": _KindReadiness(requires=("raw",), produces=("m2m",)),
    "leadfield": _KindReadiness(requires=("m2m",), produces=("leadfield",)),
    "flex": _KindReadiness(requires=("m2m",)),
    "ex": _KindReadiness(requires=("m2m", "leadfield")),
    "mex": _KindReadiness(requires=("m2m", "leadfield")),
    "sim": _KindReadiness(requires=("m2m",), produces=("simulation",)),
    "analyzer": _KindReadiness(requires=("simulation",)),
    "source": _KindReadiness(requires=("m2m",)),
    "stats": _KindReadiness(requires=("simulation",)),
}

#: subject id -> the capabilities that subject already has in the project.
Readiness = dict[str, set[str]]


def readiness_from_overview(overview: Any) -> Readiness:
    """Turn ``GET /api/catalog/overview``'s rows into the capability sets this module reads.

    Deliberately tolerant of both the dataclass and its ``to_dict``/JSON form, because the route
    hands it whichever is cheaper and a test hands it a literal.
    """

    def get(row: Any, key: str, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        return getattr(row, key, default)

    def present(value: Any) -> bool:
        # The overview reports a five-state presence, not a boolean: only `present` counts as
        # "this subject has it". `partial` deliberately does not -- a subject with a leadfield for
        # one net out of three is not ready for a search over the net it lacks, and telling them so
        # now is cheaper than a job that fails on a missing file.
        if isinstance(value, str):
            return value == "present"
        return bool(value)

    out: Readiness = {}
    for row in get(overview, "subjects", None) or []:
        sid = str(get(row, "id", "") or "")
        if not sid:
            continue
        caps: set[str] = set()
        if present(get(row, "raw")):
            caps.add("raw")
        if present(get(row, "m2m")):
            caps.add("m2m")
        if present(get(row, "leadfield")) or get(row, "leadfield") == "partial":
            caps.add("leadfield")
        counts = get(row, "counts") or {}
        if int(get(counts, "simulations", 0) or 0) > 0:
            caps.add("simulation")
        out[sid] = caps
    return out


#: Every ``Issue.code`` this module can emit.  The code is what a *client* keys on; the message
#: is what a human reads.  Before it existed the canvas had to match on message text to tell an
#: "it will run on its own" note (which is fine, and which a canvas should state once for the
#: whole graph) from a real blocker, and it did not -- it printed both as a wall of warnings.
ISSUE_CODES = (
    "empty",  # the document has no nodes at all
    "duplicate_id",  # two nodes share an id
    "edge_unknown_node",  # an edge names a node that is not on the canvas
    "self_edge",  # a node feeds itself
    "bad_output",  # the producer does not produce that port type
    "bad_input",  # the consumer does not take that port type
    "double_bound",  # one input port wired twice
    "cycle",  # the graph is not a DAG
    "missing_input",  # a required input is neither wired nor set in the node's config
    "unconfigured",  # the node carries an empty config
    "unconnected",  # the node has no edges; it runs on its own
    "not_ready",  # the subjects reaching this node lack something it requires
)


@dataclass
class Issue:
    """One finding. ``level`` is ``"error"`` (blocks Run) or ``"warning"`` (does not).

    ``code`` is the stable, machine-readable name of the finding (see :data:`ISSUE_CODES`) and
    ``port`` names the port type a ``missing_input`` is about, so a client can render the finding
    as a chip on the node's own card and open the editor at that field instead of parsing English.
    """

    level: str
    message: str
    node_id: str | None = None
    edge: dict[str, Any] | None = None
    code: str = ""
    port: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"level": self.level, "message": self.message}
        if self.node_id is not None:
            out["node_id"] = self.node_id
        if self.edge is not None:
            out["edge"] = self.edge
        if self.code:
            out["code"] = self.code
        if self.port is not None:
            out["port"] = self.port
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


def subjects_at(
    doc: PipelineDocument, node_id: str, _seen: set[str] | None = None
) -> list[str]:
    """The subject ids reaching *node_id*: its bound upstream cohort, else its own config.

    Under the ``subjects``-source model the second half is only ever true of a ``subjects`` node
    itself; it is kept for a hand-written document that still names subjects on a processing node.
    """
    seen = _seen if _seen is not None else set()
    if node_id in seen:
        return []
    seen.add(node_id)
    for edge in doc.incoming(node_id):
        if edge.port == "subjects":
            return subjects_at(doc, edge.source, seen)
    node = doc.node(node_id)
    return _config_subjects(node.config) if node else []


def _config_subjects(config: dict[str, Any]) -> list[str]:
    raw = (config or {}).get("subject_ids")
    if isinstance(raw, list):
        out = [str(s).strip() for s in raw if str(s).strip()]
        if out:
            return out
    one = str((config or {}).get("subject_id") or "").strip()
    return [one] if one else []


def capabilities_at(
    doc: PipelineDocument,
    node_id: str,
    readiness: Readiness,
    _seen: set[str] | None = None,
) -> dict[str, set[str]]:
    """What each subject reaching *node_id* has **by the time the graph gets there**.

    The project's own facts at a ``subjects`` node, plus whatever every node on the way produces.
    A cycle resolves to the project's facts rather than recursing.
    """
    seen = _seen if _seen is not None else set()
    node = doc.node(node_id)
    if node is None or node_id in seen:
        return {}
    seen.add(node_id)

    upstream: str | None = None
    for edge in doc.incoming(node_id):
        if edge.port == "subjects":
            upstream = edge.source
            break

    if upstream is None:
        # A source: the subjects are this node's own, and what they have is what the project says.
        return {s: set(readiness.get(s, set())) for s in _config_subjects(node.config)}

    inherited = capabilities_at(doc, upstream, readiness, seen)
    produced = KIND_READINESS.get(
        doc.node(upstream).kind if doc.node(upstream) else "", _KindReadiness()
    ).produces
    producer = doc.node(upstream)
    if producer and producer.kind == "pre" and not producer.config.get("create_m2m"):
        produced = ()
    if (
        producer
        and producer.kind == "sim"
        and not producer.config.get("montages")
        and not any(e.port == "montages" for e in doc.incoming(producer.id))
    ):
        produced = ()
    return {sid: caps | set(produced) for sid, caps in inherited.items()}


def unmet(
    kind: str, caps_by_subject: dict[str, set[str]]
) -> list[tuple[str, list[str]]]:
    """``[(capability, [subjects missing it])]`` for *kind*, in table order. Empty when ready."""
    needed = KIND_READINESS.get(kind, _KindReadiness()).requires
    out: list[tuple[str, list[str]]] = []
    for capability in needed:
        missing = sorted(
            s for s, caps in caps_by_subject.items() if capability not in caps
        )
        if missing:
            out.append((capability, missing))
    return out


def readiness_reason(kind: str, caps_by_subject: dict[str, set[str]]) -> str | None:
    """One sentence naming the subjects that are not ready, or ``None`` when they all are.

    Names the subjects rather than counting them: "102, test have no head model" tells you which
    two rows to go and look at, and "2 subjects are not ready" does not.
    """
    problems = unmet(kind, caps_by_subject)
    if not problems:
        return None
    parts = []
    for capability, missing in problems:
        who = ", ".join(missing)
        verb = "has" if len(missing) == 1 else "have"
        parts.append(f"{who} {verb} no {CAPABILITY_LABELS.get(capability, capability)}")
    return "; ".join(parts)


def can_connect(
    doc: PipelineDocument,
    source: str,
    target: str,
    port: str,
    readiness: Readiness | None = None,
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
    if port == "subjects" and readiness is not None:
        # The wire is type-legal; the question left is whether these particular subjects have what
        # the target needs. Asked here so the canvas can refuse the *drag* with the reason, rather
        # than accepting it and failing one job per subject after the run starts.
        hypothetical = PipelineDocument(
            nodes=list(doc.nodes),
            edges=[*doc.edges, Edge(source=source, target=target, port=port)],
            name=doc.name,
        )
        reason = readiness_reason(
            dst.kind, capabilities_at(hypothetical, target, readiness)
        )
        if reason:
            return False, reason
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


def validate(
    doc: PipelineDocument, readiness: Readiness | None = None
) -> ValidationResult:
    """Every reason this pipeline cannot run, plus a topological order when it can.

    Pass *readiness* (subject -> capabilities, from :func:`readiness_from_overview`) to also check
    that the subjects reaching each node have what that node needs. Without it the graph is checked
    for shape only, which is what a caller with no project bound can answer.
    """
    issues: list[Issue] = []
    ids = [n.id for n in doc.nodes]

    if not doc.nodes:
        issues.append(
            Issue("error", "a pipeline needs at least one node", code="empty")
        )

    seen: set[str] = set()
    for node_id in ids:
        if node_id in seen:
            issues.append(
                Issue(
                    "error",
                    f"duplicate node id: {node_id}",
                    node_id=node_id,
                    code="duplicate_id",
                )
            )
        seen.add(node_id)

    # -- edges ---------------------------------------------------------------------------------
    known = set(ids)
    bound: dict[tuple[str, str], Edge] = {}
    for edge in doc.edges:
        wire = edge.to_dict()
        if edge.source not in known or edge.target not in known:
            issues.append(
                Issue(
                    "error",
                    "edge refers to a node that is not on the canvas",
                    edge=wire,
                    code="edge_unknown_node",
                )
            )
            continue
        src = doc.node(edge.source)
        dst = doc.node(edge.target)
        assert src is not None and dst is not None  # guarded by `known` above
        if edge.source == edge.target:
            issues.append(
                Issue("error", "a node cannot feed itself", edge=wire, code="self_edge")
            )
            continue
        if edge.port not in node_outputs(src.kind):
            issues.append(
                Issue(
                    "error",
                    f"{src.display_name} does not produce {port_label(edge.port)}",
                    edge=wire,
                    code="bad_output",
                    port=edge.port,
                )
            )
            continue
        if edge.port not in node_inputs(dst.kind):
            issues.append(
                Issue(
                    "error",
                    f"{dst.display_name} does not take {port_label(edge.port)}",
                    edge=wire,
                    code="bad_input",
                    port=edge.port,
                )
            )
            continue
        if edge.port == "montages" and src.kind in {"ex", "mex"}:
            issues.append(
                Issue(
                    "error",
                    f"{src.display_name}: select and save a montage from the search results before simulating; automatic {src.kind} montage binding is unsupported",
                    node_id=dst.id,
                    edge=wire,
                    code="bad_output",
                    port=edge.port,
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
                    code="double_bound",
                    port=edge.port,
                )
            )
            continue
        bound[key] = edge

    order = topological_order(doc)
    if order is None:
        issues.append(Issue("error", "the pipeline has a cycle", code="cycle"))
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
                    code="missing_input",
                    port=port,
                )
            )
        if not node.config:
            issues.append(
                Issue(
                    "warning",
                    f"{node.display_name} has no configuration yet",
                    node_id=node.id,
                    code="unconfigured",
                )
            )

    # -- readiness: do the subjects reaching each node have what it needs? ----------------------
    if readiness is not None:
        for node in doc.nodes:
            caps = capabilities_at(doc, node.id, readiness)
            if not caps:
                continue
            for capability, missing in unmet(node.kind, caps):
                who = ", ".join(missing)
                verb = "has" if len(missing) == 1 else "have"
                issues.append(
                    Issue(
                        "error",
                        f"{node.display_name}: {who} {verb} no "
                        f"{CAPABILITY_LABELS.get(capability, capability)}",
                        node_id=node.id,
                        code="not_ready",
                        port="subjects",
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
                        f"{node.display_name} is not connected to anything; "
                        f"it will run on its own",
                        node_id=node.id,
                        code="unconnected",
                    )
                )

    ok = not any(i.level == "error" for i in issues)
    return ValidationResult(ok=ok, issues=issues, order=order if ok else order)
