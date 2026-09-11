"""Execute exported cells through the real planner/adapter, capturing only scientific subprocesses.

Expected configs are authored explicit settings, not copies of emitted source. No FEM is run.
"""

from __future__ import annotations
import json
import subprocess
from pathlib import Path
import pytest
from tit.pipeline.document import PipelineDocument
from tit.pipeline.notebook import export_notebook, notebook_json
from tests.test_pipeline_plan import build, sim_config

nbformat = pytest.importorskip("nbformat")


def document():
    return build(
        [
            ("class", "subjects", {"subject_ids": ["101", "102"]}),
            ("a-b", "pre", {"create_m2m": True, "freesurfer_threads": 3}),
            ("a_b", "sim", sim_config(["true_false_null"], conductivity="scalar")),
            (
                "an",
                "analyzer",
                {
                    "analysis_type": "mask",
                    "space": "voxel",
                    "mask_path": "/project/true_false_null.nii.gz",
                    "coordinate_space": "subject",
                    "field": "TI_max",
                },
            ),
            (
                "source",
                "source",
                {"mode": "forward", "forward": {"cpus": 3, "eeg_net": "BioSemi64"}},
            ),
            ("lf", "leadfield", {"eeg_net": "BioSemi64", "tissues": [2]}),
        ],
        [
            ("class", "a-b", "subjects"),
            ("a-b", "a_b", "subjects"),
            ("a_b", "an", "subjects"),
            ("a_b", "an", "simulation"),
            ("a-b", "source", "subjects"),
            ("a-b", "lf", "subjects"),
        ],
    )


def test_notebook_is_valid_deterministic_and_preserves_document():
    doc = document()
    first = export_notebook(doc, project_dir="/project")
    assert first == export_notebook(doc, project_dir="/project")
    notebook = nbformat.reads(first, as_version=4)
    nbformat.validate(notebook)
    assert notebook.metadata.ti_toolbox.pipeline == doc.to_dict()
    assert (
        len([c for c in notebook.cells if c.cell_type == "code"]) == len(doc.nodes) + 2
    )


def test_all_cells_execute_exact_configs_in_dependency_order(tmp_path, monkeypatch):
    import tit.pipeline.execution as execution
    from tit.jobs import kinds

    calls = []
    monkeypatch.setattr(
        kinds, "command_for", lambda kind, config, path, **_: [kind, path]
    )

    def run(argv, *, env, check):
        assert check is True
        config = json.loads(Path(argv[1]).read_text())
        calls.append((argv[0], config))
        Path(env["TIT_EVENTS_FILE"]).write_text(
            json.dumps({"type": "result", "outputs": {"recorded": argv[0]}}) + "\n"
        )

    monkeypatch.setattr(execution.subprocess, "run", run)
    scope = {}
    notebook = notebook_json(document(), project_dir=str(tmp_path))
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            exec(compile(cell["source"], "exported-notebook", "exec"), scope)
    assert [kind for kind, _ in calls] == [
        "pre",
        "pre",
        "sim",
        "sim",
        "analyzer",
        "analyzer",
        "source",
        "source",
        "leadfield",
        "leadfield",
    ]
    for kind, config in calls:
        assert config["project_dir"] == str(tmp_path)
        if kind == "sim":
            assert config["montages"][0]["name"] == "true_false_null"
            assert config["montages"][0]["electrode_pairs"] == [
                ["E010", "E011"],
                ["E012", "E013"],
            ]
            assert config["montages"][0]["eeg_net"] == "GSN-HydroCel-185.csv"
        elif kind == "analyzer":
            assert config["mask_path"] == "/project/true_false_null.nii.gz"
            assert config["simulation"] == "true_false_null"
            assert config["field"] == "TI_max"
        elif kind == "source":
            assert config["subject_ids"] in [["101"], ["102"]]
            assert config["forward"]["cpus"] == 3
        elif kind == "leadfield":
            assert config["tissues"] == [2]
    assert len(scope["completed"]) == len(calls)
    assert all(record["events"] for record in scope["completed"].values())


def test_failed_or_repeated_job_cannot_supply_stale_results(tmp_path, monkeypatch):
    from tit.pipeline.execution import execute_job
    from tit.jobs.spec import PlannedJob
    from tit.jobs import kinds

    monkeypatch.setattr(kinds, "command_for", lambda *args, **kw: ["fake"])

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["fake"])

    monkeypatch.setattr(subprocess, "run", fail)
    completed = {}
    job = PlannedJob(label="sim:0", kind="sim", config={}, subject_ids=["101"])
    with pytest.raises(subprocess.CalledProcessError):
        execute_job(job, completed, project_dir=str(tmp_path), run_id="run123")
    assert completed == {}
    completed[job.label] = {"prior": True}
    with pytest.raises(ValueError, match="rerun Setup"):
        execute_job(job, completed, project_dir=str(tmp_path), run_id="run123")
