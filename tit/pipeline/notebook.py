"""Export concrete inputs and public scientific calls, with no runtime graph machinery."""

from __future__ import annotations

import html
import pprint
from typing import Any

from tit.pipeline.document import PipelineDocument
from tit.pipeline.plan import KIND_CONFIG_CLASS, PipelinePlanError, plan_pipeline
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


def _setup_code(project_dir: str | None) -> str:
    return (
        "from tit import get_path_manager\n"
        "from tit.config_io import deserialize_config\n\n"
        f"PROJECT_DIR = {project_dir or '/path/to/your/BIDS/project'!r}\n"
        "pm = get_path_manager(PROJECT_DIR)"
    )


def _call(name: str, arguments: dict[str, str]) -> str:
    return (
        name
        + "(\n"
        + "".join(f"    {key}={value},\n" for key, value in arguments.items())
        + ")"
    )


def _direct_cells(doc: PipelineDocument, planned: list[Any]) -> dict[str, str]:
    """Compile bindings now; the exported cells contain only concrete configs and public calls."""
    cells: dict[str, list[str]] = {node.id: [] for node in doc.nodes}
    references: dict[tuple[str, str], list[str]] = {}
    counts: dict[str, int] = {}
    imports = {
        "pre": "from tit.pre.config import PreprocessConfig\nfrom tit.pre import run_pipeline",
        "sim": "from tit.sim import SimulationConfig, run_simulation",
        "flex": "from tit.opt import FlexConfig, run_flex_search\nfrom tit.opt.flex.drivers import run_adaptive_focality, run_pareto_sweep",
        "ex": "from tit.opt import ExConfig, run_ex_search",
        "mex": "from tit.opt import MExConfig, run_m_ex_search",
        "analyzer": "from tit.analyzer import Analyzer, run_group_analysis\nfrom tit.analyzer.config import AnalyzerConfig",
        "leadfield": "from tit.opt.leadfield_config import LeadfieldConfig\nfrom tit.opt.leadfield import LeadfieldGenerator",
        "source": "from tit.source.config import SourceConfig\nfrom tit.source import prepare_forward, project_fields_to_fsaverage",
        "stats": "from tit.stats import GroupComparisonConfig, run_group_comparison",
    }
    for job in planned:
        if job.kind == "tools":
            continue  # Its binding becomes the explicit producer result variable below.
        node_id = next(
            tag.removeprefix("node:") for tag in job.tags if tag.startswith("node:")
        )
        node = doc.node(node_id)
        counts[job.kind] = counts.get(job.kind, 0) + 1
        name = f"{job.kind}_{counts[job.kind]}"
        config_name = name + "_config"
        config = {
            k: v
            for k, v in job.config.items()
            if k not in {"project_dir", "_pipeline_bindings"}
        }
        lines = [
            imports[job.kind],
            f"{config_name} = deserialize_config({KIND_CONFIG_CLASS[job.kind]}, {_lit(config)})",
        ]
        for descriptor in job.config.get("_pipeline_bindings", []):
            port = descriptor["port"]
            source = next(
                edge.source for edge in doc.incoming(node_id) if edge.port == port
            )
            subject = job.subject_ids[0]
            producers = references.get((source, subject), [])
            if len(producers) != 1:
                raise PipelinePlanError(
                    f"Notebook {port} binding requires exactly one producer for {subject}",
                    node_id,
                )
            producer = producers[0]
            if port == "montages":
                lines.extend(
                    [
                        "from pathlib import Path",
                        "from tit.sim.montage_sources import resolve_flex_montage",
                        f"if Path({producer}_result.output_folder).resolve().parent != Path(pm.flex_search({subject!r})).resolve():",
                        "    raise ValueError('Optimizer output must be in this subject’s flex-search directory')",
                        f"{config_name}.montages = [resolve_flex_montage(pm, {subject!r}, Path({producer}_result.output_folder).name, 'optimized')]",
                    ]
                )
            elif port == "simulation":
                producer_configs = []
                for bound_subject in job.subject_ids:
                    bound = references.get((source, bound_subject), [])
                    if len(bound) != 1:
                        raise PipelinePlanError(
                            f"Notebook simulation binding requires one producer for {bound_subject}",
                            node_id,
                        )
                    producer_configs.append(bound[0] + "_config")
                lines.extend(
                    [
                        f"{name}_simulations = {{montage.name for config in [{', '.join(producer_configs)}] for montage in config.montages}}",
                        f"if len({name}_simulations) != 1:",
                        "    raise ValueError('Group analysis requires one shared simulation name; use separate analyses for different names')",
                        f"{config_name}.simulation = next(iter({name}_simulations))",
                    ]
                )
            elif port == "leadfield":
                lines.append(f"{config_name}.leadfield_hdf = str({producer}_result)")
            else:
                raise PipelinePlanError(f"Notebook export cannot bind {port}", node_id)
        args = {key: f"{config_name}.{key}" for key in config}
        if job.kind == "pre":
            # The public preprocessing API takes plain nested settings, as its JSON runner does.
            for key in ("qsiprep_config", "qsi_recon_config"):
                args[key] = _lit(config.get(key))
            lines.extend(
                [
                    f"{name}_result = " + _call("run_pipeline", args),
                    f"if {name}_result != 0:",
                    "    raise RuntimeError('Preprocessing failed; stop before downstream steps')",
                ]
            )
        elif job.kind == "sim":
            invocation = f"{name}_result = run_simulation({config_name}, overwrite={job.overwrite!r})"
            if config.get("tissue_conductivities"):
                lines.extend(
                    [
                        "# Match the simulation entry point’s conductivity overrides, then restore them.",
                        "import os",
                        f"{name}_environment = {{f'TISSUE_COND_{{key}}': str(value) for key, value in {config_name}.tissue_conductivities.items()}}",
                        f"{name}_previous = {{key: os.environ.get(key) for key in {name}_environment}}",
                        f"os.environ.update({name}_environment)",
                        "try:",
                        "    " + invocation,
                        "finally:",
                        f"    for key, value in {name}_previous.items():",
                        "        if value is None:",
                        "            os.environ.pop(key, None)",
                        "        else:",
                        "            os.environ[key] = value",
                    ]
                )
            else:
                lines.append(invocation)
            lines.extend(
                [
                    f"if any(result.get('status') == 'failed' for result in {name}_result):",
                    "    raise RuntimeError('Simulation failed; stop before downstream steps')",
                ]
            )
        elif job.kind in {"flex", "ex", "mex", "stats"}:
            function = {
                "ex": "run_ex_search",
                "mex": "run_m_ex_search",
                "stats": "run_group_comparison",
            }.get(job.kind)
            if job.kind == "flex":
                function = {
                    "flex": "run_flex_search",
                    "flex_adaptive": "run_adaptive_focality",
                    "flex_pareto": "run_pareto_sweep",
                }.get(config.get("mode", "flex"))
            if function is None:
                raise PipelinePlanError(
                    f"Unsupported notebook mode for {node.display_name}", node_id
                )
            lines.extend(
                [
                    f"{name}_result = {function}({config_name})",
                    f"if not {name}_result.success:",
                    "    raise RuntimeError('Step failed; stop before downstream steps')",
                ]
            )
        elif job.kind == "analyzer":
            analysis_type = config["analysis_type"]
            if analysis_type == "subcortical":
                raise PipelinePlanError(
                    "The public Analyzer does not implement subcortical analysis; notebook export cannot execute it",
                    node_id,
                )
            if config["mode"] == "group":
                lines.append(
                    f"{name}_result = "
                    + _call(
                        "run_group_analysis",
                        {
                            k: v
                            for k, v in args.items()
                            if k not in {"mode", "subject_id"}
                        },
                    )
                )
            else:
                lines.append(
                    f"{name} = "
                    + _call(
                        "Analyzer",
                        {
                            k: args[k]
                            for k in (
                                "subject_id",
                                "simulation",
                                "space",
                                "tissue_type",
                                "output_dir",
                                "field",
                            )
                        },
                    )
                )
                method, fields = {
                    "spherical": (
                        "analyze_sphere",
                        ("center", "radius", "coordinate_space", "visualize"),
                    ),
                    "mask": (
                        "analyze_mask",
                        ("mask_path", "coordinate_space", "visualize"),
                    ),
                    "cortical": ("analyze_cortex", ("atlas", "region", "visualize")),
                }[analysis_type]
                lines.append(
                    f"{name}_result = "
                    + _call(f"{name}.{method}", {k: args[k] for k in fields})
                )
        elif job.kind == "source":
            if config["mode"] == "forward":
                lines.append(
                    f"{name}_result = prepare_forward({job.subject_ids[0]!r}, {config_name}.forward)"
                )
            else:
                lines.extend(
                    [
                        f"{name}_result = project_fields_to_fsaverage([(pair.subject_id, pair.simulation) for pair in {config_name}.pairs], {config_name}.fsavg_map)",
                        f"if any(status == 'failed' for _, status, _ in {name}_result):",
                        "    raise RuntimeError('Field projection failed')",
                    ]
                )
        elif job.kind == "leadfield":
            lines.extend(
                [
                    f"{name} = LeadfieldGenerator({config_name}.subject_id, electrode_cap={config_name}.eeg_net)",
                    f"{name}_existing = [path for net, path, _ in {name}.list_leadfields() if net == {config_name}.eeg_net]",
                    f"if not {config_name}.overwrite and {name}_existing:",
                    f"    if len({name}_existing) != 1:",
                    "        raise ValueError('Leadfield selection is ambiguous')",
                    f"    {name}_result = {name}_existing[0]",
                    "else:",
                    f"    {name}_result = {name}.generate(tissues={config_name}.tissues)",
                ]
            )
        cells[node_id].append("\n".join(lines))
        for subject in job.subject_ids:
            references.setdefault((node_id, subject), []).append(name)
    return {node_id: "\n\n".join(parts) for node_id, parts in cells.items()}


def notebook_json(
    doc: PipelineDocument, *, project_dir: str | None = None
) -> dict[str, Any]:
    """The notebook as a plain dict (``nbformat`` v4), ready for ``nbformat.validate``."""
    planned = plan_pipeline(doc)
    node_code = _direct_cells(doc, planned)
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
        "in dependency order, as complete inputs and direct calls to the existing scientific functions.\n\n"
        "Run this notebook in the TI-Toolbox Python environment with access to the project; no desktop or job server is required. Execution is sequential and stops on a failed prerequisite.\n\n"
    )
    markdown("## Setup")
    code(_setup_code(project_dir))

    for node_id in order:
        node = doc.node(node_id)
        if node is None:  # pragma: no cover
            continue
        title = _KIND_TITLE.get(node.kind, node.kind)
        markdown(f"## {node.label or title}")
        if node_code[node_id]:
            code(node_code[node_id])
        elif node.kind == "subjects":
            markdown(f"Subjects: {node.config.get('subject_ids', [])}")

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
