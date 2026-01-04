import os
from pathlib import Path

import pytest


click = pytest.importorskip("click")
from click.testing import CliRunner  # noqa: E402


def test_analyzer_direct_builds_expected_argv(monkeypatch, tmp_path: Path):
    from tit.cli import analyzer as analyzer_cli

    captured = {}

    def fake_run(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(analyzer_cli, "_run_main_analyzer_with_argv", fake_run)

    # Minimal env for direct mode
    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("SUBJECT", "101")
    monkeypatch.setenv("SIMULATION_NAME", "test_montage")
    monkeypatch.setenv("SPACE_TYPE", "mesh")
    monkeypatch.setenv("ANALYSIS_TYPE", "spherical")
    monkeypatch.setenv("FIELD_PATH", str(tmp_path / "dummy.msh"))
    monkeypatch.setenv("COORDINATES", "-50 0 0")
    monkeypatch.setenv("RADIUS", "5")
    monkeypatch.setenv("COORDINATE_SPACE", "subject")
    monkeypatch.setenv("VISUALIZE", "false")

    res = CliRunner().invoke(analyzer_cli.cli, ["--run-direct", "--project-dir", str(tmp_path)])
    assert res.exit_code == 0, res.output

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

    res = CliRunner().invoke(
        ga.cli,
        [
            "from-project",
            "--project-dir",
            str(proj),
            "--subjects",
            "101,102",
            "--simulation",
            "simA",
            "--space",
            "mesh",
            "--analysis-type",
            "spherical",
            "--output-dir",
            str(out),
            "--coordinates",
            "0",
            "0",
            "0",
            "--coordinate-space",
            "MNI",
            "--radius",
            "10",
        ],
    )
    assert res.exit_code == 0, res.output

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

    monkeypatch.setenv("PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("SUBJECTS", "101,102")
    monkeypatch.setenv("GOAL", "mean")
    monkeypatch.setenv("POSTPROC", "max_TI")
    monkeypatch.setenv("CURRENT", "2.0")
    monkeypatch.setenv("ELECTRODE_SHAPE", "rect")
    monkeypatch.setenv("DIMENSIONS", "8,8")
    monkeypatch.setenv("THICKNESS", "5")
    monkeypatch.setenv("ROI_METHOD", "spherical")
    monkeypatch.setenv("ROI_X", "0")
    monkeypatch.setenv("ROI_Y", "0")
    monkeypatch.setenv("ROI_Z", "0")
    monkeypatch.setenv("ROI_RADIUS", "10")

    res = CliRunner().invoke(fs.cli, ["--run-direct", "--project-dir", str(tmp_path)])
    assert res.exit_code == 0, res.output

    assert len(calls) == 2
    assert calls[0][1:4] == ["-m", "tit.opt.flex", "--subject"]
    assert calls[0][4] == "101"
    assert calls[1][4] == "102"


def test_gui_cli_runs_gui_module(monkeypatch, tmp_path: Path):
    from tit.cli import gui as gui_cli

    seen = {}

    def fake_run_module(name, run_name=None):
        seen["name"] = name
        seen["run_name"] = run_name
        return None

    monkeypatch.setattr(gui_cli.runpy, "run_module", fake_run_module)
    monkeypatch.setattr(gui_cli, "_repo_root_from_this_file", lambda: tmp_path)

    res = CliRunner().invoke(gui_cli.cli, ["--run-direct"])
    assert res.exit_code == 0, res.output
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
    monkeypatch.setenv("PROJECT_DIR", str(proj))
    monkeypatch.setenv("SUBJECTS", "101,102")
    monkeypatch.setenv("CONVERT_DICOM", "false")
    monkeypatch.setenv("RUN_RECON", "false")
    monkeypatch.setenv("PARALLEL_RECON", "false")
    monkeypatch.setenv("CREATE_M2M", "false")
    monkeypatch.setenv("CREATE_ATLAS", "false")
    monkeypatch.setenv("RUN_TISSUE_ANALYSIS", "false")

    res = CliRunner().invoke(pp.cli, ["--run-direct", "--project-dir", str(proj)])
    assert res.exit_code == 0, res.output
    assert calls, "expected structural.sh to be invoked"
    # structural.sh should be called once with two subject dirs
    assert str(proj / "sub-101") in calls[0]
    assert str(proj / "sub-102") in calls[0]



