"""Notebook export (D4) and its gate: the emitted code must actually *run*.

``nbformat.validate`` only says the JSON is a notebook.  The claim that matters -- "exported code
uses only documented public API calls" (plan §3, *Notebook honesty*) -- is checked by executing
every code cell in a **subprocess against a stub ``tit``** that defines exactly the public names
``docs/wiki/scripting.md`` documents and nothing else: a cell that reached for a private helper, a
renamed argument or a method that does not exist fails here with an ``AttributeError`` or a
``TypeError``, not in a user's kernel three weeks later.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tit.pipeline.document import PipelineDocument
from tit.pipeline.notebook import export_notebook, mermaid_graph, notebook_json

nbformat = pytest.importorskip("nbformat")


FOUR_NODE = {
    "version": 1,
    "name": "four node demo",
    "nodes": [
        {
            "id": "pre1",
            "kind": "pre",
            "label": "Head models",
            "config": {"subject_ids": ["ernie", "101"], "create_m2m": True},
        },
        {"id": "flex1", "kind": "flex", "config": {"goal": "mean", "postproc": "max_TI"}},
        {"id": "sim1", "kind": "sim", "config": {"conductivity": "scalar"}},
        {
            "id": "an1",
            "kind": "analyzer",
            "config": {
                "space": "mesh",
                "analysis_type": "spherical",
                "center": [-35.0, 5.0, 5.0],
                "radius": 10.0,
                "coordinate_space": "subject",
            },
        },
    ],
    "edges": [
        {"from": "pre1", "to": "flex1", "port": "subjects"},
        {"from": "pre1", "to": "sim1", "port": "subjects"},
        {"from": "flex1", "to": "sim1", "port": "montages"},
        {"from": "sim1", "to": "an1", "port": "subjects"},
        {"from": "sim1", "to": "an1", "port": "simulation"},
    ],
}


@pytest.fixture()
def doc() -> PipelineDocument:
    return PipelineDocument.from_dict(FOUR_NODE)


def test_notebook_validates(doc: PipelineDocument) -> None:
    text = export_notebook(doc, project_dir="/proj")
    notebook = nbformat.reads(text, as_version=4)
    nbformat.validate(notebook)
    assert notebook.nbformat == 4


def test_pipeline_rides_along_in_metadata(doc: PipelineDocument) -> None:
    """Round-trippable without parsing Python: the canvas restores from the metadata."""
    notebook = json.loads(export_notebook(doc))
    carried = notebook["metadata"]["ti_toolbox"]["pipeline"]
    assert PipelineDocument.from_dict(carried).to_dict() == doc.to_dict()


def test_title_cell_carries_the_graph_as_mermaid(doc: PipelineDocument) -> None:
    first = notebook_json(doc)["cells"][0]
    assert first["cell_type"] == "markdown"
    assert "```mermaid" in first["source"]
    assert mermaid_graph(doc) in first["source"]
    assert "flex1 -->|montages| sim1" in first["source"]


def test_one_markdown_and_one_code_cell_per_node_in_topological_order(
    doc: PipelineDocument,
) -> None:
    cells = notebook_json(doc)["cells"]
    code = [c["source"] for c in cells if c["cell_type"] == "code"]
    # setup + one per node + run-everything
    assert len(code) == 2 + len(doc.nodes)
    positions = [next(i for i, s in enumerate(code) if s.startswith(f"{n}_subjects")) for n in
                 ("pre1", "flex1", "sim1", "an1")]
    assert positions == sorted(positions)


def test_bindings_are_python_variables_passed_between_cells(doc: PipelineDocument) -> None:
    code = "\n".join(
        c["source"] for c in notebook_json(doc)["cells"] if c["cell_type"] == "code"
    )
    assert "flex1_subjects = pre1_subjects" in code
    assert "montage_names=flex1_montages" in code
    assert "for simulation in sim1_simulations" in code


def test_export_is_byte_stable(doc: PipelineDocument) -> None:
    assert export_notebook(doc, project_dir="/p") == export_notebook(doc, project_dir="/p")


# -- the D6 gate: the code cells execute ---------------------------------------------------------

_STUB = {
    "tit/__init__.py": """
class _PM:
    def __init__(self, project_dir=None):
        self.project_dir = project_dir

def get_path_manager(project_dir=None):
    return _PM(project_dir)
""",
    "tit/config_io.py": """
def deserialize_config(cls, data):
    return cls(**data)
""",
    "tit/pre.py": """
def run_pipeline(subject_ids, **flags):
    print("run_pipeline", subject_ids, sorted(flags))
    return True
""",
    "tit/sim.py": """
class Montage:
    def __init__(self, name):
        self.name = name

class SimulationConfig:
    def __init__(self, **kwargs):
        self.montages = []
        for key, value in kwargs.items():
            setattr(self, key, value)

def load_montages(montage_names, eeg_net):
    print("load_montages", montage_names, eeg_net)
    return [Montage(n) for n in montage_names]

def run_simulation(config):
    print("run_simulation", config.subject_id, [m.name for m in config.montages])
""",
    "tit/opt.py": """
class _Roi:
    def __init__(self, **kw):
        pass

class FlexConfig:
    SphericalROI = AtlasROI = SubcorticalROI = _Roi
    class ElectrodeConfig:
        def __init__(self, **kw):
            pass
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class ExConfig(FlexConfig):
    pass

class _Result:
    output_folder = "/derivatives/SimNIBS/sub-x/flex-search/L_Insula_mean"

def run_flex_search(config):
    print("run_flex_search", config.subject_id)
    return _Result()

def run_ex_search(config):
    print("run_ex_search", config.subject_id)
    return _Result()
""",
    "tit/analyzer.py": """
class _AnalysisResult:
    mean = 0.0
    max = 0.0

class Analyzer:
    def __init__(self, subject_id, simulation, space):
        self.subject_id = subject_id
        self.simulation = simulation
        self.space = space

    def analyze_sphere(self, center, radius, coordinate_space, visualize=False):
        print("analyze_sphere", self.subject_id, self.simulation, center, radius)
        return _AnalysisResult()

    def analyze_cortex(self, atlas, region, visualize=False):
        print("analyze_cortex", self.subject_id, self.simulation, atlas, region)
        return _AnalysisResult()
""",
}


def _write_stub(root: Path) -> Path:
    package = root / "stub"
    (package / "tit").mkdir(parents=True)
    for relative, body in _STUB.items():
        (package / relative).write_text(textwrap.dedent(body), encoding="utf-8")
    return package


def test_every_code_cell_executes_against_a_stub_tit(doc: PipelineDocument, tmp_path: Path) -> None:
    """D6's notebook gate: import + construct configs + call the documented entry points.

    The stub defines only the names ``docs/wiki/scripting.md`` documents, so this fails if the
    emitter reaches for anything private or misspells an argument.
    """
    stub = _write_stub(tmp_path)
    notebook = nbformat.reads(export_notebook(doc, project_dir=str(tmp_path)), as_version=4)
    script = "\n\n".join(c.source for c in notebook.cells if c.cell_type == "code")
    script_path = tmp_path / "pipeline_script.py"
    script_path.write_text(script, encoding="utf-8")

    env = dict(os.environ, PYTHONPATH=str(stub))
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=120,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "run_pipeline ['ernie', '101']" in result.stdout
    assert "run_flex_search ernie" in result.stdout
    assert "run_simulation ernie ['L_Insula_mean'" in result.stdout
    assert "analyze_sphere ernie L_Insula_mean [-35.0, 5.0, 5.0] 10.0" in result.stdout
    assert "four node demo finished:" in result.stdout
