"""Execute exported cells with real config classes and captured public scientific functions.

Expected configs are authored explicit settings, not copies of emitted source. No FEM is run.
"""

from __future__ import annotations
import json
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
    code = "\n".join(c.source for c in notebook.cells if c.cell_type == "code")
    for forbidden in (
        "tit.pipeline",
        "execute_job",
        "PIPELINE_DATA",
        "PlannedJob",
        "subprocess",
        "RUN_ID",
    ):
        assert forbidden not in code
    assert "run_pipeline(" in code
    assert "run_simulation(" in code
    assert ".analyze_mask(" in code


def capture_science(monkeypatch):
    from tit.config_io import serialize_config
    import tit.pre
    import tit.sim
    import tit.analyzer
    import tit.source
    import tit.opt.leadfield

    calls = []

    def pre(**kwargs):
        calls.append(("pre", kwargs))
        return 0

    def sim(config, *, overwrite=False):
        calls.append(("sim", serialize_config(config)))
        return [{"status": "success"}]

    class Analyzer:
        def __init__(self, **kwargs):
            self.config = kwargs

        def analyze_mask(self, **kwargs):
            calls.append(("analyzer", {**self.config, **kwargs}))

        def analyze_sphere(self, **kwargs):
            calls.append(("analyzer", {**self.config, **kwargs}))

        def analyze_cortex(self, **kwargs):
            calls.append(("analyzer", {**self.config, **kwargs}))

    def source(subject, config):
        calls.append(
            ("source", {"subject_ids": [subject], "forward": serialize_config(config)})
        )
        return ("forward", "surface", "morph")

    class Leadfield:
        def __init__(self, subject, electrode_cap):
            self.subject = subject
            self.net = electrode_cap

        def list_leadfields(self):
            return []

        def generate(self, *, tissues):
            calls.append(
                (
                    "leadfield",
                    {
                        "subject_id": self.subject,
                        "tissues": tissues,
                        "eeg_net": self.net,
                    },
                )
            )
            return "/result/leadfield.hdf5"

    monkeypatch.setattr(tit.pre, "run_pipeline", pre)
    monkeypatch.setattr(tit.sim, "run_simulation", sim)
    monkeypatch.setattr(tit.analyzer, "Analyzer", Analyzer)
    monkeypatch.setattr(tit.source, "prepare_forward", source)
    monkeypatch.setattr(tit.opt.leadfield, "LeadfieldGenerator", Leadfield)
    return calls


def execute_cells(doc, project):
    scope = {}
    for cell in notebook_json(doc, project_dir=str(project))["cells"]:
        if cell["cell_type"] == "code":
            exec(compile(cell["source"], "exported-notebook", "exec"), scope)
    return scope


def test_all_cells_call_public_functions_with_complete_inputs(tmp_path, monkeypatch):
    calls = capture_science(monkeypatch)
    execute_cells(document(), tmp_path)
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
        if kind == "pre":
            assert config["create_m2m"] is True
            assert config["freesurfer_threads"] == 3
        elif kind == "sim":
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


def test_failed_preprocessing_stops_before_simulation(tmp_path, monkeypatch):
    import tit.pre

    calls = capture_science(monkeypatch)
    monkeypatch.setattr(tit.pre, "run_pipeline", lambda **kwargs: 2)
    with pytest.raises(RuntimeError, match="Preprocessing failed"):
        execute_cells(document(), tmp_path)
    assert calls == []


def test_custom_conductivity_is_applied_and_restored_even_on_failure(
    tmp_path, monkeypatch
):
    import os
    import tit.sim

    graph = build(
        [("sim", "sim", sim_config(["M"], tissue_conductivities={1: 0.123, 2: 0.456}))]
    )
    monkeypatch.setenv("TISSUE_COND_1", "prior")
    monkeypatch.delenv("TISSUE_COND_2", raising=False)

    def run(config, *, overwrite):
        assert os.environ["TISSUE_COND_1"] == "0.123"
        assert os.environ["TISSUE_COND_2"] == "0.456"
        raise ValueError("simulation failure")

    monkeypatch.setattr(tit.sim, "run_simulation", run)
    with pytest.raises(ValueError, match="simulation failure"):
        execute_cells(graph, tmp_path)
    assert os.environ["TISSUE_COND_1"] == "prior"
    assert "TISSUE_COND_2" not in os.environ


@pytest.mark.parametrize("kind", ["ex", "mex", "stats"])
def test_search_and_statistics_export_executes_existing_function(
    kind, tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from tit.config_io import serialize_config
    import tit.opt
    import tit.stats

    config = {
        "subject_id": "101",
        "leadfield_hdf": "/data/exact.hdf5",
        "roi_name": "target.csv",
        "electrodes": {
            "_type": "PoolElectrodes",
            "electrodes": [f"E{i}" for i in range(8)],
        },
        "roi_radius": 4.5,
    }
    if kind == "stats":
        config = {
            "analysis_name": "true_false_null",
            "subject_ids": ["101", "102"],
            "subjects": [
                {"subject_id": "101", "simulation_name": "M", "response": 1},
                {"subject_id": "102", "simulation_name": "N", "response": 0},
            ],
            "n_permutations": 17,
        }
    captured = []

    def run(config):
        captured.append(serialize_config(config))
        return SimpleNamespace(success=True)

    module = tit.stats if kind == "stats" else tit.opt
    function = {
        "ex": "run_ex_search",
        "mex": "run_m_ex_search",
        "stats": "run_group_comparison",
    }[kind]
    monkeypatch.setattr(module, function, run)
    execute_cells(build([("step", kind, config)]), tmp_path)
    assert len(captured) == 1
    if kind == "stats":
        assert captured[0]["n_permutations"] == 17
        assert captured[0]["subjects"] == config["subjects"]
    else:
        assert captured[0]["leadfield_hdf"] == "/data/exact.hdf5"
        assert captured[0]["roi_radius"] == 4.5


@pytest.mark.parametrize(
    "mode,function",
    [
        ("flex", "run_flex_search"),
        ("flex_adaptive", "run_adaptive_focality"),
        ("flex_pareto", "run_pareto_sweep"),
    ],
)
def test_flex_modes_call_the_selected_public_driver(
    mode, function, tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from tests.test_pipeline_plan import flex_config
    import tit.opt
    import tit.opt.flex.drivers

    config = flex_config()
    config["mode"] = mode
    if mode != "flex":
        config["goal"] = "focality"
    called = []

    def run(config):
        called.append(config)
        return SimpleNamespace(success=True)

    monkeypatch.setattr(
        tit.opt if mode == "flex" else tit.opt.flex.drivers, function, run
    )
    execute_cells(build([("optimizer", "flex", config)]), tmp_path)
    assert len(called) == 1
    assert called[0].mode.value == mode


def test_group_analysis_exports_one_direct_call_with_complete_cohort(
    tmp_path, monkeypatch
):
    import tit.analyzer
    from tit.pipeline.plan import plan_pipeline

    graph = build(
        [
            ("subjects", "subjects", {"subject_ids": ["101", "102"]}),
            (
                "analysis",
                "analyzer",
                {
                    "mode": "group",
                    "simulation": "M",
                    "analysis_type": "spherical",
                    "center": [1, 2, 3],
                    "radius": 6,
                    "field": "TI_max",
                    "visualize": False,
                },
            ),
        ],
        [("subjects", "analysis", "subjects")],
    )
    planned = plan_pipeline(graph)
    assert len(planned) == 1
    assert planned[0].subject_ids == ["101", "102"]
    assert planned[0].config["subject_ids"] == ["101", "102"]
    assert planned[0].config["subject_id"] is None
    calls = []
    monkeypatch.setattr(
        tit.analyzer, "run_group_analysis", lambda **kwargs: calls.append(kwargs)
    )
    execute_cells(graph, tmp_path)
    assert len(calls) == 1
    assert calls[0]["subject_ids"] == ["101", "102"]
    assert calls[0]["simulation"] == "M"
    assert calls[0]["center"] == [1, 2, 3]
    assert calls[0]["radius"] == 6
    assert calls[0]["field"] == "TI_max"
    markdown = "\n".join(
        cell["source"]
        for cell in notebook_json(graph)["cells"]
        if cell["cell_type"] == "markdown"
    )
    assert "mermaid" not in markdown
    assert "— kind" not in markdown
    assert "*Node" not in markdown
