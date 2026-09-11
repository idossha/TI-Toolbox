"""Export editable pipeline documents using the same planner and JSON runners as Canvas."""

from __future__ import annotations

import html
import pprint
from typing import Any

from tit.pipeline.document import PipelineDocument
from tit.pipeline.plan import plan_pipeline
from tit.pipeline.validate import topological_order

__all__ = ["export_notebook", "mermaid_graph", "notebook_json"]

_KIND_TITLE: dict[str, str] = {
    "pre": "Pre-processing",
    "leadfield": "Leadfield",
    "flex": "Flex-search optimization",
    "ex": "Exhaustive search",
    "mex": "Multipolar exhaustive search",
    "sim": "Simulation",
    "analyzer": "Analysis",
    "source": "EEG source forward model",
    "stats": "Group statistics",
}


def _var(node_id: str) -> str:
    """Collision-free identifier, including punctuation and Python keywords."""
    return "node_" + node_id.encode("utf-8").hex()


def _lit(value: Any) -> str:
    """An exact Python literal: never rewrite substrings inside user strings."""
    return pprint.pformat(value, sort_dicts=False, width=88)


def mermaid_graph(doc: PipelineDocument) -> str:
    """The pipeline as a Mermaid ``graph LR`` block body (no fence)."""
    lines = ["graph LR"]
    for node in doc.nodes:
        title = _KIND_TITLE.get(node.kind, node.kind)
        label = html.escape(node.label or title, quote=True).replace("\n", " ")
        lines.append(f'  {_var(node.id)}["{label}<br/><i>{node.kind}</i>"]')
    for edge in doc.edges:
        lines.append(f"  {_var(edge.source)} -->|{edge.port}| {_var(edge.target)}")
    return "\n".join(lines)


def _setup_code(doc: PipelineDocument, project_dir: str | None) -> str:
    return (
        "import uuid\n"
        "from tit import get_path_manager\n"
        "from tit.pipeline.document import PipelineDocument\n"
        "from tit.pipeline.plan import plan_pipeline\n"
        "from tit.pipeline.execution import execute_job\n\n"
        f"PROJECT_DIR = {project_dir or '/path/to/your/BIDS/project'!r}\n"
        "# Full saved configuration; edit these values before running the remaining cells.\n"
        f"PIPELINE_DATA = {_lit(doc.to_dict())}\n"
        "get_path_manager(PROJECT_DIR)\n"
        "PLAN = plan_pipeline(PipelineDocument.from_dict(PIPELINE_DATA))\n"
        "RUN_ID = uuid.uuid4().hex\n"
        "completed = {}\n"
    )


def _node_code(doc: PipelineDocument, node: Any) -> str:
    return (
        f"# {' '.join(node.display_name.splitlines())}: only this node's existing jobs, in dependency order.\n"
        f"node_jobs = [job for job in PLAN if {'node:' + node.id!r} in job.tags]\n"
        "for job in node_jobs:\n"
        "    print(job.label, job.kind, 'after:', job.after_labels)\n"
        "    result = execute_job(job, completed, project_dir=PROJECT_DIR, run_id=RUN_ID)\n"
        "    print('Completed', job.label, '— events:', len(result['events']))"
    )


def notebook_json(
    doc: PipelineDocument, *, project_dir: str | None = None
) -> dict[str, Any]:
    """The notebook as a plain dict (``nbformat`` v4), ready for ``nbformat.validate``."""
    plan_pipeline(doc)  # Refuse invalid configs and unsupported bindings before export.
    order = topological_order(doc) or []
    cells: list[dict[str, Any]] = []

    # nbformat 4.5 requires a per-cell `id`; a deterministic one also makes the export
    # byte-stable, so re-exporting an unchanged pipeline produces an identical file.
    def markdown(text: str) -> None:
        cells.append(
            {
                "cell_type": "markdown",
                "id": f"cell-{len(cells)}",
                "metadata": {},
                "source": text,
            }
        )

    def code(text: str) -> None:
        cells.append(
            {
                "cell_type": "code",
                "id": f"cell-{len(cells)}",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": text,
            }
        )

    markdown(
        f"# {doc.name}\n\n"
        "Exported from the TI-Toolbox pipeline canvas. Each cell below is one node of the graph, "
        "in dependency order, using the same validated configurations and JSON runners as Canvas.\n\n"
        "Run this notebook in the TI-Toolbox Python environment with access to the project; no desktop or job server is required. Execution is sequential and stops on a failed prerequisite.\n\n"
        f"```mermaid\n{mermaid_graph(doc)}\n```\n"
    )
    markdown("## Setup")
    code(_setup_code(doc, project_dir))

    for node_id in order:
        node = doc.node(node_id)
        if node is None:  # pragma: no cover
            continue
        title = _KIND_TITLE.get(node.kind, node.kind)
        upstream = [
            f"`{e.port}` from **{doc.node(e.source).display_name}**"
            for e in doc.incoming(node_id)
            if doc.node(e.source) is not None
        ]
        bindings = ("\n\nInputs: " + ", ".join(upstream)) if upstream else ""
        markdown(
            f"## {node.label or title}\n\n*Node `{node.id}` — kind `{node.kind}`.*{bindings}"
        )
        code(_node_code(doc, node))

    markdown("## Run everything")
    code(
        "# Run All Cells executes each planned job above exactly once in dependency order.\n"
        "# completed contains each job's resolved configuration and producer events.\n"
        f"print({doc.name!r}, 'finished:', list(completed))"
    )

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
            "ti_toolbox": {"pipeline": doc.to_dict()},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def export_notebook(doc: PipelineDocument, *, project_dir: str | None = None) -> str:
    """The notebook as a JSON string, normalised and validated by ``nbformat``."""
    import nbformat

    notebook = nbformat.from_dict(notebook_json(doc, project_dir=project_dir))
    nbformat.validate(notebook)
    return nbformat.writes(notebook)
