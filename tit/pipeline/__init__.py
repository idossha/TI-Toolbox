"""Pipeline canvas: a DAG of existing job kinds, run as **one job group** (plan §1-D).

Four small pure modules, deliberately free of SimNIBS and of ``tit.server``:

``document``
    The wire document (``contracts/pipeline.schema.json``) and the typed-port table that gives an
    edge its meaning.
``validate``
    Acyclicity, port compatibility, unbound required inputs -- every refusal a sentence.
``plan``
    Document -> ``tit.jobs.spec.PlannedJob`` DAG whose ``after_labels`` **are** the edges, so
    ``JobManager.submit_plan`` submits the whole pipeline under one ``group_id``.
``notebook``
    Document -> an ``nbformat`` v4 notebook written against the public ``tit`` scripting API.

Nothing here executes anything: the job scheduler stays the only executor.
"""

from tit.pipeline.document import (
    DOCUMENT_VERSION,
    NODE_KINDS,
    PORT_TYPES,
    PORTS,
    Edge,
    Node,
    PipelineDocument,
    PipelineDocumentError,
    node_inputs,
    node_outputs,
    port_label,
)
from tit.pipeline.notebook import export_notebook, mermaid_graph, notebook_json
from tit.pipeline.plan import PipelinePlanError, plan_pipeline
from tit.pipeline.validate import Issue, ValidationResult, can_connect, validate

__all__ = [
    "DOCUMENT_VERSION",
    "NODE_KINDS",
    "PORTS",
    "PORT_TYPES",
    "Edge",
    "Issue",
    "Node",
    "PipelineDocument",
    "PipelineDocumentError",
    "PipelinePlanError",
    "ValidationResult",
    "can_connect",
    "export_notebook",
    "mermaid_graph",
    "node_inputs",
    "node_outputs",
    "notebook_json",
    "plan_pipeline",
    "port_label",
    "validate",
]
