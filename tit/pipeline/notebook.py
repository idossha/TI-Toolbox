"""Notebook export: a pipeline document -> an ``nbformat`` v4 notebook (D4).

Export is a **pure function of the document** -- no project, no job server, no filesystem.  The
notebook it writes uses only the *documented public* ``tit`` scripting API (``docs/wiki/scripting.md``):
``SimulationConfig``/``run_simulation``, ``FlexConfig``/``run_flex_search``, ``ExConfig``/
``run_ex_search``, ``Analyzer``, ``run_pipeline``.  Bindings become plain Python variables passed
from one cell to the next, which is the whole point: the graph the user drew is legible as code
they can edit, share, and run without the desktop app.

The document itself rides along in ``metadata.ti_toolbox.pipeline``, so a future "import notebook"
restores the canvas without parsing Python (importing an *arbitrary* edited notebook is a non-goal).

``nbformat`` is imported lazily so this module stays free for the route-import guard.
"""

from __future__ import annotations

import json
from typing import Any

from tit.pipeline.document import PipelineDocument
from tit.pipeline.plan import _config_subjects, _simulation_names
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
    """A Python identifier for a node id (canvas ids are free-form strings)."""
    cleaned = "".join(c if (c.isalnum() or c == "_") else "_" for c in node_id)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _lit(value: Any) -> str:
    """A Python literal for *value* -- JSON is a subset of Python for these shapes."""
    return (
        json.dumps(value, indent=None, ensure_ascii=False)
        .replace("true", "True")
        .replace("false", "False")
        .replace("null", "None")
        if isinstance(value, (dict, list))
        else repr(value)
    )


def mermaid_graph(doc: PipelineDocument) -> str:
    """The pipeline as a Mermaid ``graph LR`` block body (no fence)."""
    lines = ["graph LR"]
    for node in doc.nodes:
        title = _KIND_TITLE.get(node.kind, node.kind)
        label = node.label or title
        lines.append(f'  {_var(node.id)}["{label}<br/><i>{node.kind}</i>"]')
    for edge in doc.edges:
        lines.append(f"  {_var(edge.source)} -->|{edge.port}| {_var(edge.target)}")
    return "\n".join(lines)


# -- per-kind code emitters ---------------------------------------------------------------------


def _subjects_expr(doc: PipelineDocument, node_id: str) -> str:
    """``SUBJECTS`` for an unbound node, else the upstream node's own subject variable."""
    for edge in doc.incoming(node_id):
        if edge.port == "subjects":
            return f"{_var(edge.source)}_subjects"
    node = doc.node(node_id)
    subjects = _config_subjects(node.config if node else {})
    return _lit(subjects) if subjects else "SUBJECTS"


def _cell_pre(doc: PipelineDocument, node: Any) -> str:
    flags = {
        key: True
        for key in (
            "convert_dicom",
            "run_fastsurfer",
            "run_freesurfer",
            "create_m2m",
            "run_tissue_analysis",
            "run_qsiprep",
            "run_qsirecon",
            "extract_dti",
        )
        if node.config.get(key)
    }
    args = "".join(f",\n    {k}=True" for k in flags) or ",\n    create_m2m=True"
    if node.config.get("run_freesurfer"):
        for key in (
            "freesurfer_recon_all",
            "freesurfer_subregions",
            "freesurfer_threads",
        ):
            if key in node.config:
                args += f",\n    {key}={_lit(node.config[key])}"
    return (
        f"{_var(node.id)}_subjects = {_subjects_expr(doc, node.id)}\n"
        f"run_pipeline(\n    subject_ids={_var(node.id)}_subjects{args},\n)"
    )


def _cell_flex(doc: PipelineDocument, node: Any, func: str, cls: str) -> str:
    config = {
        k: v for k, v in node.config.items() if k not in ("subject_id", "subject_ids")
    }
    return (
        f"{_var(node.id)}_subjects = {_subjects_expr(doc, node.id)}\n"
        f"{_var(node.id)}_results = []\n"
        f"for subject_id in {_var(node.id)}_subjects:\n"
        f"    config = deserialize_config(\n"
        f"        {cls}, dict({_lit(config)}, subject_id=subject_id)\n"
        f"    )\n"
        f"    {_var(node.id)}_results.append({func}(config))\n"
        f"\n"
        f"# The optimizer names its own run directory at run time, so the montage name a\n"
        f"# downstream Simulator node consumes is that directory's basename.\n"
        f"{_var(node.id)}_montages = [\n"
        f"    os.path.basename(r.output_folder) for r in {_var(node.id)}_results\n"
        f"]"
    )


def _cell_sim(doc: PipelineDocument, node: Any) -> str:
    config = {
        k: v
        for k, v in node.config.items()
        if k not in ("subject_id", "subject_ids", "montages")
    }
    bound_montages = any(e.port == "montages" for e in doc.incoming(node.id))
    if bound_montages:
        source = next(e.source for e in doc.incoming(node.id) if e.port == "montages")
        names_expr = f"{_var(source)}_montages"
    else:
        names_expr = _lit(_simulation_names(node.config))
    config = {k: v for k, v in config.items() if k != "eeg_net"}
    return (
        f"{_var(node.id)}_subjects = {_subjects_expr(doc, node.id)}\n"
        f"{_var(node.id)}_simulations = []\n"
        f"for subject_id in {_var(node.id)}_subjects:\n"
        f"    montages = load_montages(montage_names={names_expr}, eeg_net=EEG_NET)\n"
        f"    config = deserialize_config(\n"
        f"        SimulationConfig, dict({_lit(config)}, subject_id=subject_id)\n"
        f"    )\n"
        f"    config.montages = montages\n"
        f"    run_simulation(config)\n"
        f"    {_var(node.id)}_simulations.extend(m.name for m in montages)"
    )


def _cell_analyzer(doc: PipelineDocument, node: Any) -> str:
    config = node.config
    sims_edge = next((e for e in doc.incoming(node.id) if e.port == "simulation"), None)
    if sims_edge is not None:
        sims = f"{_var(sims_edge.source)}_simulations"
    else:
        sims = _lit([config.get("simulation")] if config.get("simulation") else [])
    space = _lit(config.get("space") or "mesh")
    analysis_type = config.get("analysis_type") or "spherical"
    if analysis_type == "spherical":
        center = config.get("center") or [0.0, 0.0, 0.0]
        call = (
            f"        result = analyzer.analyze_sphere(\n"
            f"            center={_lit(list(center))},\n"
            f"            radius={_lit(config.get('radius') or 10.0)},\n"
            f"            coordinate_space={_lit(config.get('coordinate_space') or 'subject')},\n"
            f"        )\n"
        )
    elif analysis_type == "cortical":
        call = (
            f"        result = analyzer.analyze_cortex(\n"
            f"            atlas={_lit(config.get('atlas'))},\n"
            f"            region={_lit(config.get('region'))},\n"
            f"        )\n"
        )
    else:
        # Subcortical targets go through the same atlas entry point (Analyzer.analyze_cortex is
        # the only atlas API; the atlas name is what distinguishes the two).
        call = (
            f"        result = analyzer.analyze_cortex(\n"
            f"            atlas={_lit(config.get('atlas'))},\n"
            f"            region={_lit(config.get('region'))},\n"
            f"        )\n"
        )
    return (
        f"{_var(node.id)}_subjects = {_subjects_expr(doc, node.id)}\n"
        f"{_var(node.id)}_results = []\n"
        f"for subject_id in {_var(node.id)}_subjects:\n"
        f"    for simulation in {sims}:\n"
        f"        analyzer = Analyzer(subject_id=subject_id, simulation=simulation, "
        f"space={space})\n"
        f"{call}"
        f"        {_var(node.id)}_results.append(result)"
    )


def _cell_generic(doc: PipelineDocument, node: Any) -> str:
    """A kind with no hand-written scripting recipe: run it through its JSON config runner."""
    return (
        f"{_var(node.id)}_subjects = {_subjects_expr(doc, node.id)}\n"
        f"# `{node.kind}` has no hand-written scripting recipe; run it from its JSON config\n"
        f"# exactly as the desktop app does (see docs/wiki/scripting.md, 'JSON config runners').\n"
        f"{_var(node.id)}_config = {_lit(node.config)}"
    )


def _node_code(doc: PipelineDocument, node: Any) -> str:
    if node.kind == "pre":
        return _cell_pre(doc, node)
    if node.kind == "flex":
        return _cell_flex(doc, node, "run_flex_search", "FlexConfig")
    if node.kind == "ex":
        return _cell_flex(doc, node, "run_ex_search", "ExConfig")
    if node.kind == "sim":
        return _cell_sim(doc, node)
    if node.kind == "analyzer":
        return _cell_analyzer(doc, node)
    return _cell_generic(doc, node)


_IMPORTS = """\
import os

from tit import get_path_manager
from tit.config_io import deserialize_config
from tit.pre import run_pipeline
from tit.sim import SimulationConfig, load_montages, run_simulation
from tit.opt import ExConfig, FlexConfig, run_ex_search, run_flex_search
from tit.analyzer import Analyzer

# Bind the project once; every call below resolves its paths through this.
get_path_manager({project_dir!r})

SUBJECTS = {subjects}
EEG_NET = {eeg_net!r}
"""


def _setup_code(doc: PipelineDocument, project_dir: str | None) -> str:
    subjects: list[str] = []
    eeg_net = "GSN-HydroCel-185.csv"
    for node in doc.nodes:
        subjects = subjects or _config_subjects(node.config)
        net = node.config.get("eeg_net")
        if isinstance(net, str) and net:
            eeg_net = net
    return _IMPORTS.format(
        project_dir=project_dir or "/path/to/your/BIDS/project",
        subjects=_lit(subjects),
        eeg_net=eeg_net,
    )


def notebook_json(
    doc: PipelineDocument, *, project_dir: str | None = None
) -> dict[str, Any]:
    """The notebook as a plain dict (``nbformat`` v4), ready for ``nbformat.validate``."""
    order = topological_order(doc) or [n.id for n in doc.nodes]
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
        "in dependency order, written against the public `tit` scripting API.\n\n"
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
    finished = ", ".join(f"{_var(n)}_subjects" for n in order) or "nothing"
    code(
        "# Every cell above is one node, in dependency order: 'Run All Cells' in Jupyter (or\n"
        "# `jupyter nbconvert --to notebook --execute <this file>`) runs the whole pipeline.\n"
        f"print({doc.name!r}, 'finished:', {finished})"
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
