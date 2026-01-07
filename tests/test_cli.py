import os
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def _run_cli(cli_obj, argv):
    import sys

    old = sys.argv[:]
    try:
        sys.argv = ["prog", *argv]
        return cli_obj.run()
    finally:
        sys.argv = old


def test_analyzer_direct_builds_expected_argv(monkeypatch, tmp_path: Path):
    from tit.cli import analyzer as analyzer_cli

    captured = {}

    def fake_run_main_with_argv(_prog, argv, _main):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(analyzer_cli.utils, "run_main_with_argv", fake_run_main_with_argv)

    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    cli = analyzer_cli.AnalyzerCLI()
    rc = _run_cli(
        cli,
        [
            "--sub",
            "101",
            "--sim",
            "test_montage",
            "--space",
            "mesh",
            "--analysis-type",
            "spherical",
            "--coordinates",
            "-50",
            "0",
            "0",
            "--radius",
            "5",
            "--coordinate-space",
            "subject",
        ],
    )
    assert rc == 0

    argv = captured["argv"]
    assert "--m2m_subject_path" in argv
    m2m_idx = argv.index("--m2m_subject_path") + 1
    assert argv[m2m_idx].endswith("/derivatives/SimNIBS/sub-101/m2m_101")
    assert "--analysis_type" in argv and argv[argv.index("--analysis_type") + 1] == "spherical"


def test_group_analyzer_from_project_builds_subject_specs(monkeypatch, tmp_path: Path):
    from tit.cli import group_analyzer as ga

    captured = {}

    def fake_run(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(ga, "_run_group_analyzer_with_argv", fake_run)

    proj = tmp_path / "proj"
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)

    # minimal project structure for subject specs
    for sid in ["101", "102"]:
        (proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / f"m2m_{sid}").mkdir(parents=True, exist_ok=True)
        (proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / "simA" / "TI" / "mesh").mkdir(
            parents=True, exist_ok=True
        )

    monkeypatch.setenv("PROJECT_DIR", str(proj))
    cli = ga.GroupAnalyzerCLI()
    rc = _run_cli(
        cli,
        [
            "--subs",
            "101,102",
            "--sim",
            "simA",
            "--space",
            "mesh",
            "--analysis-type",
            "spherical",
            "--out",
            str(out),
            "--coordinates",
            "0 0 0",
            "--coordinate-space",
            "MNI",
            "--radius",
            "10",
        ],
    )
    assert rc == 0

    argv = captured["argv"]
    assert argv[:2] == ["--space", "mesh"]
    # should include two --subject groups
    assert argv.count("--subject") == 2


def test_flex_search_direct_runs_per_subject(monkeypatch, tmp_path: Path):
    from tit.cli import flex_search as fs

    calls = []

    def fake_call(cmd):
        calls.append(cmd)
        return 0

    monkeypatch.setattr(fs.subprocess, "call", fake_call)

    cli = fs.FlexSearchCLI()
    rc = _run_cli(cli, ["--subject", "101", "--goal", "mean", "--postproc", "max_TI", "--roi-method", "spherical", "--roi-x", "0", "--roi-y", "0", "--roi-z", "0", "--roi-radius", "10"])
    assert rc == 0

    assert len(calls) == 1
    assert calls[0][:3] == ["simnibs_python", "-m", "tit.opt.flex"]
    assert "--subject" in calls[0]


def test_gui_cli_runs_gui_module(monkeypatch, tmp_path: Path):
    from tit.cli import gui as gui_cli

    seen = {}

    def fake_run_module(name, run_name=None):
        seen["name"] = name
        seen["run_name"] = run_name
        return None

    monkeypatch.setattr(gui_cli.runpy, "run_module", fake_run_module)
    rc = _run_cli(gui_cli.GuiCLI(), [])
    assert rc == 0
    assert seen["name"] == "tit.gui.main"


def test_pre_process_direct_calls_structural(monkeypatch, tmp_path: Path):
    from tit.cli import pre_process as pp

    structural = tmp_path / "structural.sh"
    structural.write_text("#!/bin/bash\nexit 0\n")

    monkeypatch.setattr(pp, "_script_path", lambda name: structural)

    calls = []

    def fake_call(cmd):
        calls.append(cmd)
        return 0

    monkeypatch.setattr(pp.subprocess, "call", fake_call)

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))
    cli = pp.PreProcessCLI()
    rc = _run_cli(cli, ["--subs", "101,102"])
    assert rc == 0
    assert calls, "expected structural.sh to be invoked"
    # structural.sh should be called once with two subject dirs
    assert str(proj / "sub-101") in calls[0]
    assert str(proj / "sub-102") in calls[0]


def test_vis_blender_direct_delegates(monkeypatch, tmp_path: Path):
    from tit.cli import vis_blender as vb

    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))

    class DummyResult:
        scalp_stl = "scalp.stl"
        gm_stl = "gm.stl"
        electrodes_blend = "elec.blend"
        final_blend = "final.blend"

    def fake_build(**_kwargs):
        return DummyResult()

    from tit.blender import montage_publication as mp
    monkeypatch.setattr(mp, "build_montage_publication_blend", fake_build)

    cli = vb.VisBlenderCLI()
    rc = _run_cli(cli, ["--sub", "101", "--sim", "simA"])
    assert rc == 0


def test_create_leadfield_direct_delegates(monkeypatch, tmp_path: Path):
    from tit.cli import create_leadfield as cl

    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))

    pm = cl.get_path_manager()
    pm.project_dir = str(tmp_path)

    (tmp_path / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101" / "eeg_positions").mkdir(parents=True, exist_ok=True)
    cap = tmp_path / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101" / "eeg_positions" / "EGI_template.csv"
    cap.write_text("x,y,z,label\n")

    called = {}

    class DummyGen:
        def __init__(self, m2m_dir, electrode_cap):
            called["m2m_dir"] = m2m_dir
            called["electrode_cap"] = electrode_cap

        def generate_leadfield(self, output_dir=None, tissues=None, eeg_cap_path=None, cleanup=True):
            called["output_dir"] = output_dir
            called["tissues"] = tissues
            called["eeg_cap_path"] = eeg_cap_path
            return str(Path(output_dir) / "leadfield.hdf5")

    from tit.opt import leadfield as lf
    monkeypatch.setattr(lf, "LeadfieldGenerator", DummyGen)

    cli = cl.CreateLeadfieldCLI()
    rc = _run_cli(cli, ["--sub", "101", "--eeg", "EGI_template.csv"])
    assert rc == 0
    assert "m2m_101" in str(called["m2m_dir"])


def test_ex_search_direct_sets_env_and_calls(monkeypatch, tmp_path: Path):
    from tit.cli import ex_search as ex

    # Minimal project layout for PathManager:
    #   <proj>/derivatives/SimNIBS/sub-101/m2m_101/eeg_positions/<net>.csv
    proj = tmp_path / "proj"
    m2m = proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101"
    eeg_pos = m2m / "eeg_positions"
    eeg_pos.mkdir(parents=True, exist_ok=True)
    (eeg_pos / "EGI_template.csv").write_text("x,y,z,label\n0,0,0,F3\n0,0,0,F4\n0,0,0,P3\n0,0,0,P4\n")

    monkeypatch.setenv("PROJECT_DIR", str(proj))
    pm = ex.get_path_manager()
    pm.project_dir = str(proj)

    seen = {"called": False}

    def fake_main():
        seen["called"] = True

    import importlib
    ex_main_mod = importlib.import_module("tit.opt.ex.main")
    monkeypatch.setattr(ex_main_mod, "main", fake_main)

    cli = ex.ExSearchCLI()
    lf = tmp_path / "101_leadfield_EGI_template.hdf5"
    lf.write_text("dummy")
    rc = _run_cli(
        cli,
        [
            "--sub",
            "101",
            "--roi",
            "roiA",
            "--lf",
            str(lf),
            "--optimization-mode",
            "buckets",
            "--e1-plus",
            "F3",
            "--e1-minus",
            "F4",
            "--e2-plus",
            "P3",
            "--e2-minus",
            "P4",
        ],
    )
    assert rc == 0
    assert seen["called"] is True


def test_cluster_permutation_direct_delegates(monkeypatch, tmp_path: Path):
    from tit.cli import cluster_permuatation as cp

    seen = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return None

    from tit.stats import permutation_analysis as pa
    monkeypatch.setattr(pa, "run_analysis", lambda *a, **k: fake_run(args=a, kwargs=k))

    csv = tmp_path / "subjects.csv"
    csv.write_text("subject_id,simulation_name,response\n101,simA,1\n")

    cli = cp.PermutationCLI()
    rc = _run_cli(cli, ["--csv", str(csv), "--name", "a", "--analysis-type", "group_comparison"])
    assert rc == 0
    assert seen["kwargs"]["analysis_name"] == "a"


def test_batch_simulate_imports():
    import tit.cli.advanced.batch_simulate as _  # noqa: F401


def test_simulator_direct_delegates_to_run_simulation(monkeypatch, tmp_path: Path):
    from tit.cli import simulator as sim_cli

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Minimal fake subject structure
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101").mkdir(parents=True, exist_ok=True)

    captured = {}

    def fake_load_montages(*, montage_names, project_dir, eeg_net, include_flex=True):
        from tit.sim.config import MontageConfig

        captured["load"] = dict(montage_names=montage_names, project_dir=project_dir, eeg_net=eeg_net, include_flex=include_flex)
        # 2 pairs => TI
        return [MontageConfig(name="m1", electrode_pairs=[("A", "B"), ("C", "D")], is_xyz=False, eeg_net=eeg_net)]

    def fake_run_simulation(config, montages):
        captured["config"] = config
        captured["montages"] = montages
        return [{"montage_name": "m1", "status": "completed"}]

    # Patch the imports inside execute by patching tit.sim
    import tit.sim as sim_pkg
    import tit.sim.montage_loader as ml

    monkeypatch.setattr(ml, "load_montages", fake_load_montages)
    monkeypatch.setattr(sim_pkg, "run_simulation", fake_run_simulation)

    cli = sim_cli.SimulatorCLI()
    rc = _run_cli(cli, ["--sub", "101", "--framework", "montage", "--montages", "m1", "--eeg", "EGI_template.csv"])
    assert rc == 0
    assert captured["config"].subject_id == "101"




