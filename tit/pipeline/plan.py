"""Pipeline -> ``PlannedJob`` DAG, and the binding rules that make an edge mean something (D2/D3).

**A pipeline run is one job group.** :func:`plan_pipeline` turns a validated document into a flat
list of :class:`tit.jobs.spec.PlannedJob` whose ``after_labels`` are exactly the document's edges,
and ``tit.jobs.manager.JobManager.submit_plan`` submits that list under **one** ``group_id`` --
the same mechanism ``plan_preprocessing``'s G1-G6 DAG already uses.  There is no new scheduler, no
new job kind and no runtime graph engine: the scheduler stays the only executor.

Two flavours of binding
-----------------------

**Static** (``subjects``, ``simulation``, ``roi``) -- the value is already knowable from the
upstream node's *config*, so it is resolved here, at submit time, and written straight into the
downstream config.  ``sim -> analyzer`` is the important case: the simulation names are the
Simulator node's own montage names, so the analyzer fans out to one job per
``(subject, simulation)`` with nothing to look up at run time.

**Dynamic** (``montages``, ``leadfield``) -- the value only exists once the upstream job has
*run*: a flex-search run directory is named from the ROI and goal at run time
(``PathManager.flex_search_run``), so no amount of reading the config tells you what the optimized
montage will be called.  For those, a small ``tools`` job (:mod:`tit.tools.pipeline_resolve`) is
planned **between** the producer and the consumer, inheriting the producer's ``after`` and becoming
the consumer's, and it records the resolved values under
``code/ti-toolbox/pipelines/runs/<pipeline>/<node>.<port>.json``.

The write-back closes the loop: the consumer job carries :data:`tit.jobs.bindings.BINDINGS_KEY`
naming the file each of its resolve steps will write, and
:meth:`tit.jobs.manager.JobManager._runner_config_path` merges the resolved value into the
runner's ``config.json`` at **admission** -- which happens only after every job the consumer waits
on has finished, i.e. exactly when the file exists.  A resolve step that found nothing leaves the
field as the canvas set it, so the failure mode is the form asking for the value, not a crash.
"""

from __future__ import annotations

import os
from typing import Any

# The key a consumer job's ``config`` carries to name the binding files its ``resolve`` steps will
# write.  It is defined in :mod:`tit.jobs.bindings` -- the manager reads it back at admission --
# and re-exported here because this is the module that writes it.  One definition, two readers.
from tit.jobs.bindings import BINDINGS_KEY
from tit.pipeline.document import PipelineDocument
from tit.pipeline.validate import validate

__all__ = [
    "DYNAMIC_PORTS",
    "STATIC_PORTS",
    "PipelinePlanError",
    "BINDINGS_KEY",
    "bindings_dir_name",
    "bindings_relpath",
    "plan_pipeline",
    "resolve_subjects",
]

#: Ports whose value is *always* knowable from the upstream node's config alone.
STATIC_PORTS: frozenset[str] = frozenset({"subjects", "roi"})
#: Ports whose value only exists after the upstream job ran (needs a ``resolve`` step).
#: ``simulation`` is the one *conditional* member: it is static when the producing Simulator node
#: names its montages itself, and dynamic when those montages are themselves an optimizer's
#: run-time output (the pre -> flex -> sim -> analyzer chain).
DYNAMIC_PORTS: frozenset[str] = frozenset({"montages", "leadfield", "simulation"})

#: node kind -> the ``tit.config_io.CONFIG_CLASS_REGISTRY`` key its config round-trips through.
#: A deliberate copy of ``tit.jobs.plans._KIND_CONFIG_CLASS`` extended with the cohort kinds, kept
#: honest by ``tests/test_pipeline_plan.py::test_kind_config_classes_match_jobs_plans``.
KIND_CONFIG_CLASS: dict[str, str] = {
    "sim": "SimulationConfig",
    "flex": "FlexConfig",
    "ex": "ExConfig",
    "mex": "MExConfig",
    "analyzer": "AnalyzerConfig",
    "pre": "PreprocessConfig",
    "leadfield": "LeadfieldConfig",
    "source": "SourceConfig",
    "stats": "GroupComparisonConfig",
}

#: Kinds whose job is one job for the whole cohort rather than one per subject.
COHORT_KINDS: frozenset[str] = frozenset({"stats"})

_RESOLVE_MODULE = "tit.tools.pipeline_resolve"

#: dynamic port -> the (config key, empty value) the consumer's dataclass needs at plan time.
_DYNAMIC_PLACEHOLDER: dict[str, tuple[str, Any]] = {
    "montages": ("montages", []),
    "leadfield": ("leadfield_hdf", ""),
    "simulation": ("simulation", ""),
}


def _is_dynamic(doc: PipelineDocument, edge: Any) -> bool:
    """Does this edge need a run-time ``resolve`` step, or is its value already knowable?"""
    if edge.port not in DYNAMIC_PORTS:
        return False
    if edge.port == "simulation":
        producer = doc.node(edge.source)
        return not _simulation_names(producer.config if producer else {})
    return True


class PipelinePlanError(ValueError):
    """The document is valid JSON but cannot be turned into jobs (unbound input, bad config)."""

    def __init__(self, message: str, node_id: str | None = None):
        super().__init__(message)
        self.node_id = node_id


def bindings_dir_name(pipeline_name: str) -> str:
    """Filesystem-safe directory name for a pipeline's run-time binding files."""
    safe = "".join(
        c if (c.isalnum() or c in "-_.") else "_" for c in pipeline_name.strip()
    )
    return safe or "pipeline"


def bindings_relpath(pipeline_name: str, node_id: str, port: str) -> str:
    """Project-relative path of the file ``tit.tools.pipeline_resolve`` writes for one edge.

    Project-*relative* on purpose: the plan is built without a project directory, and the manager
    that reads it back already knows which project it is bound to.
    """
    return os.path.join(
        "code",
        "ti-toolbox",
        "pipelines",
        "runs",
        bindings_dir_name(pipeline_name),
        f"{node_id}.{port}.json",
    )


def resolve_subjects(
    doc: PipelineDocument, node_id: str, cache: dict[str, list[str]]
) -> list[str]:
    """The subject list a node runs over: its bound upstream set, else its own config.

    *cache* is filled in topological order, so a node three hops downstream of ``pre`` inherits
    exactly the subjects ``pre`` ran on without every node repeating the list.
    """
    if node_id in cache:
        return cache[node_id]
    node = doc.node(node_id)
    if node is None:  # pragma: no cover - callers pass ids from the document
        return []
    subjects: list[str] = []
    for edge in doc.incoming(node_id):
        if edge.port == "subjects":
            subjects = list(resolve_subjects(doc, edge.source, cache))
            break
    if not subjects:
        subjects = _config_subjects(node.config)
    cache[node_id] = subjects
    return subjects


def _config_subjects(config: dict[str, Any]) -> list[str]:
    raw = config.get("subject_ids")
    if isinstance(raw, list):
        out = [str(s).strip() for s in raw if str(s).strip()]
        if out:
            return out
    single = str(config.get("subject_id") or "").strip()
    return [single] if single else []


def _simulation_names(config: dict[str, Any]) -> list[str]:
    """The simulation names a ``sim`` node will write -- one per montage, in order."""
    names: list[str] = []
    for montage in config.get("montages") or []:
        if isinstance(montage, dict):
            name = str(montage.get("name") or "").strip()
        else:
            name = str(getattr(montage, "name", "") or "").strip()
        if name:
            names.append(name)
    return names


def _roi_fields(
    producer_kind: str, producer_config: dict[str, Any], consumer_kind: str
) -> dict[str, Any]:
    """The ROI fields an edge carries from *producer* into a *consumer* config.

    Only the shapes the two dataclasses genuinely share are copied; anything else is left alone
    (an unbound ROI is a validation warning, never a silently wrong config).
    """
    roi = producer_config.get("roi")
    if consumer_kind in {"flex", "ex", "mex"} and roi not in (None, {}, []):
        return {"roi": roi}
    if consumer_kind == "analyzer" and isinstance(roi, dict):
        out: dict[str, Any] = {}
        # A cortical/subcortical FlexConfig ROI carries the atlas the analyzer also reads.
        if roi.get("atlas") or roi.get("atlas_path"):
            out["atlas"] = roi.get("atlas") or roi.get("atlas_path")
        if roi.get("region") is not None:
            out["region"] = roi.get("region")
        if roi.get("center") is not None:
            out["center"] = roi.get("center")
            out["radius"] = roi.get("radius")
        return out
    if consumer_kind in {"ex", "mex"} and producer_kind in {"ex", "mex"}:
        return {k: v for k, v in producer_config.items() if k.startswith("roi_")}
    return {}


def _round_trip(kind: str, config: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Deserialize+reserialize *config* through its dataclass, so a job can only carry a shape
    the runner actually accepts. Unregistered kinds pass through unchanged."""
    class_name = KIND_CONFIG_CLASS.get(kind)
    if class_name is None:  # pragma: no cover - KIND_CONFIG_CLASS covers NODE_KINDS
        return dict(config)
    # Lazy: tit.config_io reaches tit.opt.config, whose package __init__ pulls in SimNIBS.
    from tit.config_io import deserialize_config, resolve_config_class, serialize_config

    cls = resolve_config_class(class_name)
    try:
        return serialize_config(deserialize_config(cls, config))
    except Exception as exc:
        raise PipelinePlanError(
            f"{node_id}: config is not a valid {class_name}: {exc}", node_id=node_id
        ) from exc


def plan_pipeline(
    doc: PipelineDocument,
    *,
    tags: list[str] | None = None,
    overwrite: bool = False,
) -> list[Any]:
    """The whole pipeline as one labelled DAG of :class:`~tit.jobs.spec.PlannedJob`.

    Parameters
    ----------
    doc
        A document that :func:`tit.pipeline.validate.validate` accepts.
    tags
        Copied onto every job, in addition to the per-node ``pipeline:<name>`` /
        ``node:<id>`` tags this function always adds so a group's jobs can be traced back to the
        node that produced them.
    overwrite
        Replace existing output instead of skipping it, for every job.

    Returns
    -------
    list of PlannedJob
        In topological order, most-upstream first -- the order
        :meth:`tit.jobs.manager.JobManager.submit_plan` needs to resolve labels to job ids.

    Raises
    ------
    PipelinePlanError
        The document does not validate, or a node's config does not fit its kind's dataclass.
    """
    from tit.jobs.spec import PlannedJob  # cheap, but keeps the import graph one-way

    result = validate(doc)
    if not result.ok:
        reasons = "; ".join(i.message for i in result.errors)
        raise PipelinePlanError(f"pipeline does not validate: {reasons}")

    base_tags = list(tags or [])
    bindings_dir = bindings_dir_name(doc.name)
    subject_cache: dict[str, list[str]] = {}
    node_labels: dict[str, list[str]] = {}
    planned: list[Any] = []

    for node_id in result.order:
        node = doc.node(node_id)
        assert node is not None
        # The cohort node runs nothing. It names who the graph is about, and its subjects reach
        # the rest of the graph over the `subjects` wire (`resolve_subjects` follows it), so it
        # contributes no job and no label -- a node downstream of it waits for whatever *it*
        # waits for, not for a set of names.
        if node.kind == "subjects":
            node_labels[node_id] = []
            continue
        incoming = doc.incoming(node_id)
        upstream_labels: list[str] = []
        for edge in incoming:
            # A dynamic edge's dependency is carried by its resolve step (appended below), which
            # already waits for the producer -- naming the producer here as well would put a
            # redundant edge in the submitted DAG that the document does not have.
            if _is_dynamic(doc, edge):
                continue
            upstream_labels.extend(node_labels.get(edge.source, []))

        # -- dynamic ports get a resolve step between producer and consumer --------------------
        for edge in incoming:
            if not _is_dynamic(doc, edge):
                continue
            resolve_label = f"{node_id}:resolve:{edge.port}"
            planned.append(
                PlannedJob(
                    label=resolve_label,
                    kind="tools",
                    config={
                        "module": _RESOLVE_MODULE,
                        "args": [
                            "--pipeline",
                            bindings_dir,
                            "--node",
                            node_id,
                            "--port",
                            edge.port,
                            "--from-kind",
                            doc.node(edge.source).kind if doc.node(edge.source) else "",
                            "--subjects",
                            ",".join(resolve_subjects(doc, edge.source, subject_cache)),
                        ],
                    },
                    subject_ids=list(resolve_subjects(doc, edge.source, subject_cache)),
                    after_labels=list(node_labels.get(edge.source, [])),
                    tags=[
                        *base_tags,
                        f"pipeline:{doc.name}",
                        f"node:{node_id}",
                        "resolve",
                    ],
                )
            )
            upstream_labels.append(resolve_label)

        # -- the node's own jobs ---------------------------------------------------------------
        config = dict(node.config)
        dynamic_ports: list[str] = []
        for edge in incoming:
            if _is_dynamic(doc, edge):
                dynamic_ports.append(edge.port)
                # The value arrives from the resolve step, not from the canvas, but the config
                # dataclass still has to be constructible now -- so the bound field is present
                # and empty rather than missing.
                config.setdefault(
                    _DYNAMIC_PLACEHOLDER[edge.port][0],
                    _DYNAMIC_PLACEHOLDER[edge.port][1],
                )
            if edge.port in ("roi",):
                producer = doc.node(edge.source)
                if producer is not None:
                    config.update(
                        _roi_fields(producer.kind, producer.config, node.kind)
                    )

        subjects = resolve_subjects(doc, node_id, subject_cache)
        if not subjects and node.kind != "stats":
            raise PipelinePlanError(f"{node.display_name} has no subjects to run on")

        simulations = _bound_simulations(doc, node_id)
        labels: list[str] = []

        if node.kind in COHORT_KINDS:
            cohort_config = _round_trip(
                node.kind, {**config, "subject_ids": subjects}, node_id
            )
            _attach_bindings(cohort_config, doc.name, node_id, dynamic_ports, subjects)
            label = f"{node_id}:0"
            planned.append(
                PlannedJob(
                    label=label,
                    kind=node.kind,
                    config=cohort_config,
                    subject_ids=list(subjects),
                    after_labels=sorted(set(upstream_labels)),
                    tags=[*base_tags, f"pipeline:{doc.name}", f"node:{node_id}"],
                    overwrite=overwrite,
                )
            )
            labels.append(label)
        else:
            index = 0
            for subject_id in subjects:
                for simulation in simulations or [None]:
                    entry = {**config, "subject_id": subject_id}
                    if node.kind == "pre":
                        entry["subject_ids"] = [subject_id]
                    else:
                        entry.pop("subject_ids", None)
                    if simulation is not None:
                        entry["simulation"] = simulation
                    resolved = _round_trip(node.kind, entry, node_id)
                    _attach_bindings(
                        resolved, doc.name, node_id, dynamic_ports, [subject_id]
                    )
                    label = f"{node_id}:{index}"
                    index += 1
                    planned.append(
                        PlannedJob(
                            label=label,
                            kind=node.kind,
                            config=resolved,
                            subject_ids=[subject_id],
                            after_labels=sorted(set(upstream_labels)),
                            tags=[
                                *base_tags,
                                f"pipeline:{doc.name}",
                                f"node:{node_id}",
                            ],
                            overwrite=overwrite,
                        )
                    )
                    labels.append(label)

        node_labels[node_id] = labels

    return planned


def _attach_bindings(
    config: dict[str, Any],
    pipeline_name: str,
    node_id: str,
    ports: list[str],
    subject_ids: list[str],
) -> None:
    """Record, in *config*, which binding files this job's ``resolve`` steps will write.

    One descriptor per dynamic port: the project-relative file, the config field the value lands
    in, and the subjects whose entries this particular job wants.  Nothing is read here -- the
    files do not exist yet; the manager reads them at admission (D3's write-back).
    """
    if not ports:
        return
    config[BINDINGS_KEY] = [
        {
            "path": bindings_relpath(pipeline_name, node_id, port),
            "field": _DYNAMIC_PLACEHOLDER[port][0],
            "port": port,
            "subject_ids": list(subject_ids),
        }
        for port in ports
    ]


def _bound_simulations(doc: PipelineDocument, node_id: str) -> list[str]:
    """Simulation names carried into *node_id* by a ``simulation`` edge (static binding)."""
    for edge in doc.incoming(node_id):
        if edge.port != "simulation":
            continue
        producer = doc.node(edge.source)
        if producer is None:
            continue
        # Empty means "resolved at run time by the resolve step planned for this edge".
        return _simulation_names(producer.config)
    return []
