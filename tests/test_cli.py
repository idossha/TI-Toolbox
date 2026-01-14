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
    rc = _run_cli(gui_cli.GUICLI(), [])
    assert rc == 0
    assert seen["name"] == "tit.gui.main"


def test_pre_process_direct_calls_structural(monkeypatch, tmp_path: Path):
    from tit.cli import pre_process as pp

    calls = []

    def fake_run_pipeline(project_dir, subject_ids, **kwargs):
        calls.append((project_dir, list(subject_ids), kwargs))
        return 0

    monkeypatch.setattr(pp, "run_pipeline", fake_run_pipeline)

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))
    cli = pp.PreProcessCLI()
    rc = _run_cli(cli, ["--subs", "101,102"])
    assert rc == 0
    assert calls, "expected pipeline to be invoked"
    project_dir, subject_ids, _kwargs = calls[0]
    assert project_dir == str(proj)
    assert set(subject_ids) == {"101", "102"}


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
    cap = tmp_path / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101" / "eeg_positions" / "GSN-HydroCel-185"
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
    rc = _run_cli(cli, ["--sub", "101", "--eeg", "GSN-HydroCel-185"])
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
    (eeg_pos / "GSN-HydroCel-185").write_text("x,y,z,label\n0,0,0,F3\n0,0,0,F4\n0,0,0,P3\n0,0,0,P4\n")

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
    lf = tmp_path / "101_leadfield_GSN-HydroCel-185.hdf5"
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
    rc = _run_cli(cli, ["--sub", "101", "--framework", "montage", "--montages", "m1", "--eeg", "GSN-HydroCel-185"])
    assert rc == 0
    assert captured["config"].subject_id == "101"


def test_simulator_direct_comprehensive_argument_coverage(monkeypatch, tmp_path: Path):
    """Test all simulator CLI argument combinations for direct mode."""
    from tit.cli import simulator as sim_cli

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Create minimal project structure
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101").mkdir(parents=True, exist_ok=True)

    captured_calls = []

    def fake_load_montages(*, montage_names, project_dir, eeg_net, include_flex=True):
        from tit.sim.config import MontageConfig
        captured_calls.append(("load_montages", montage_names, eeg_net, include_flex))
        return [MontageConfig(name="test_montage", electrode_pairs=[("A", "B"), ("C", "D")], is_xyz=False, eeg_net=eeg_net)]

    def fake_run_simulation(config, montages, logger=None):
        captured_calls.append(("run_simulation", config.subject_id, len(montages)))
        return [{"montage_name": "test_montage", "status": "completed"}]

    # Mock the actual simnibs-dependent functions
    monkeypatch.setattr('tit.sim.run_simulation', fake_run_simulation)
    monkeypatch.setattr('tit.sim.montage_loader.load_montages', fake_load_montages)
    monkeypatch.setattr('tit.sim.montage_loader.list_montage_names', lambda *args, **kwargs: ["test_montage"])

    cli = sim_cli.SimulatorCLI()

    # Test 1: Basic montage mode with all arguments
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--framework", "montage",
        "--montages", "test_montage",
        "--eeg", "GSN-HydroCel-185",
        "--mode", "U",
        "--conductivity", "scalar",
        "--intensity", "2.0",
        "--electrode-shape", "ellipse",
        "--dimensions", "8,8",
        "--thickness", "4.0"
    ])
    assert rc == 0
    assert len(captured_calls) == 2

    # Test 2: Flex framework shorthand flags (requires flex-search directory and montages)
    captured_calls.clear()
    flex_dir = proj / "derivatives" / "SimNIBS" / "sub-101" / "flex-search" / "test_search"
    flex_dir.mkdir(parents=True, exist_ok=True)
    (flex_dir / "electrode_positions.json").write_text('{"optimized_positions": [[0,0,0], [10,10,10], [20,20,20], [30,30,30]]}')
    rc = _run_cli(cli, ["--sub", "101", "--flex", "--montages", "test_search"])
    assert rc == 0

    # Test 3: Montage shorthand flag
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--montage", "--montages", "test_montage", "--eeg", "GSN-HydroCel-185"])
    assert rc == 0

    # Test 4: M mode (mTI)
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--framework", "montage", "--montages", "test_montage", "--eeg", "GSN-HydroCel-185", "--mode", "M"])
    assert rc == 0

    # Test 5: Multiple montages
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--montages", "montage1,montage2", "--eeg", "GSN-HydroCel-185"])
    assert rc == 0

    # Test 6: Different conductivity types
    for conductivity in ["scalar", "vn", "dir", "mc"]:
        captured_calls.clear()
        rc = _run_cli(cli, ["--sub", "101", "--montages", "test_montage", "--eeg", "GSN-HydroCel-185", "--conductivity", conductivity])
        assert rc == 0

    # Test 7: Different electrode shapes
    for shape in ["rect", "ellipse"]:
        captured_calls.clear()
        rc = _run_cli(cli, ["--sub", "101", "--montages", "test_montage", "--eeg", "GSN-HydroCel-185", "--electrode-shape", shape])
        assert rc == 0

    # Test 8: mTI intensity format
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--montages", "test_montage", "--eeg", "GSN-HydroCel-185", "--mode", "M", "--intensity", "1.0,2.0,1.5,2.5"])
    assert rc == 0

    # Test 9: List commands (should not run simulation)
    captured_calls.clear()
    rc = _run_cli(cli, ["--list-subjects"])
    assert rc == 0
    assert len(captured_calls) == 0  # No simulation should be run

    rc = _run_cli(cli, ["--list-eeg-caps", "--sub", "101"])
    assert rc == 0

    rc = _run_cli(cli, ["--list-montages", "--eeg", "GSN-HydroCel-185"])
    assert rc == 0


def test_analyzer_direct_comprehensive_argument_coverage(monkeypatch, tmp_path: Path):
    """Test all analyzer CLI argument combinations for direct mode."""
    from tit.cli import analyzer as analyzer_cli

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Create minimal project structure
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101").mkdir(parents=True, exist_ok=True)
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "Simulations" / "test_sim" / "TI" / "mesh").mkdir(parents=True, exist_ok=True)

    captured_calls = []

    # Mock analyzer dependencies
    def fake_run_main_with_argv(prog, argv, main_func):
        captured_calls.append(("run_main_with_argv", argv))
        return 0

    def fake_select_field_file(*args, **kwargs):
        return ("dummy_field.h5", "dummy_type")

    # Mock the actual functions that get called
    monkeypatch.setattr('tit.analyzer.main_analyzer.main', lambda: captured_calls.append("analyzer_main_called"))
    monkeypatch.setattr('tit.analyzer.field_selector.select_field_file', fake_select_field_file)
    monkeypatch.setattr('tit.cli.analyzer.utils.run_main_with_argv', fake_run_main_with_argv)

    cli = analyzer_cli.AnalyzerCLI()

    # Test 1: Spherical mesh analysis with all arguments
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--sim", "test_sim",
        "--space", "mesh",
        "--analysis-type", "spherical",
        "--coordinates", "0", "0", "0",
        "--radius", "10",
        "--coordinate-space", "subject",
        "--visualize"
    ])
    assert rc == 0
    assert len(captured_calls) == 1
    argv = captured_calls[0][1]
    assert "--analysis_type" in argv and argv[argv.index("--analysis_type") + 1] == "spherical"

    # Test 2: Spherical voxel analysis
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--sim", "test_sim",
        "--space", "voxel",
        "--analysis-type", "spherical",
        "--coordinates", "-5", "10", "15",
        "--radius", "8",
        "--coordinate-space", "MNI"
    ])
    assert rc == 0

    # Test 3: Cortical mesh analysis with atlas
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--sim", "test_sim",
        "--space", "mesh",
        "--analysis-type", "cortical",
        "--atlas-name", "DK40",
        "--region", "precentral",
        "--visualize"
    ])
    assert rc == 0

    # Test 4: Cortical mesh analysis whole head
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--sim", "test_sim",
        "--space", "mesh",
        "--analysis-type", "cortical",
        "--atlas-name", "HCP_MMP1",
        "--whole-head"
    ])
    assert rc == 0

    # Test 5: Cortical voxel analysis with atlas path
    captured_calls.clear()
    atlas_path = str(tmp_path / "atlas.nii.gz")
    with open(atlas_path, "w") as f:
        f.write("fake atlas")
    rc = _run_cli(cli, [
        "--sub", "101",
        "--sim", "test_sim",
        "--space", "voxel",
        "--analysis-type", "cortical",
        "--atlas-path", atlas_path,
        "--region", "region1"
    ])
    assert rc == 0

    # Test 6: Default arguments
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--sim", "test_sim"])
    assert rc == 0  # Should use defaults: mesh, spherical

    # Test 7: Different coordinate spaces
    for coord_space in ["MNI", "subject"]:
        captured_calls.clear()
        rc = _run_cli(cli, [
            "--sub", "101",
            "--sim", "test_sim",
            "--analysis-type", "spherical",
            "--coordinates", "1", "2", "3",
            "--radius", "5",
            "--coordinate-space", coord_space
        ])
        assert rc == 0

    # Test 8: Different atlas names for mesh
    for atlas in ["DK40", "HCP_MMP1", "a2009s"]:
        captured_calls.clear()
        rc = _run_cli(cli, [
            "--sub", "101",
            "--sim", "test_sim",
            "--space", "mesh",
            "--analysis-type", "cortical",
            "--atlas-name", atlas,
            "--region", "test_region"
        ])
        assert rc == 0


def test_group_analyzer_direct_comprehensive_argument_coverage(monkeypatch, tmp_path: Path):
    """Test all group analyzer CLI argument combinations for direct mode."""
    from tit.cli import group_analyzer as ga

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)

    # Create minimal project structure for two subjects
    for sid in ["101", "102"]:
        (proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / f"m2m_{sid}").mkdir(parents=True, exist_ok=True)
        (proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / "test_sim" / "TI" / "mesh").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("PROJECT_DIR", str(proj))

    captured_calls = []

    # Mock group analyzer dependencies
    def fake_run_group_analyzer(argv):
        captured_calls.append(("group_analyzer_main", argv))
        return 0

    def fake_select_field_file(*args, **kwargs):
        return ("dummy_field.h5", "dummy_type")

    # Mock the actual functions that get called
    monkeypatch.setattr('tit.cli.group_analyzer._run_group_analyzer_with_argv', fake_run_group_analyzer)
    monkeypatch.setattr('tit.analyzer.field_selector.select_field_file', fake_select_field_file)

    cli = ga.GroupAnalyzerCLI()

    # Test 1: Basic spherical analysis with multiple subjects
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--subs", "101,102",
        "--sim", "test_sim",
        "--space", "mesh",
        "--analysis-type", "spherical",
        "--coordinates", "0 0 0",
        "--radius", "10",
        "--coordinate-space", "MNI",
        "--visualize"
    ])
    assert rc == 0
    assert len(captured_calls) == 1
    argv = captured_calls[0][1]
    assert argv.count("--subject") == 2  # Two subjects

    # Test 2: Space-separated subjects
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--subs", "101", "102",
        "--sim", "test_sim",
        "--space", "mesh",
        "--analysis-type", "spherical",
        "--coordinates", "5 5 5",
        "--radius", "15"
    ])
    assert rc == 0
    assert argv.count("--subject") == 2

    # Test 3: Cortical mesh analysis
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--subs", "101,102",
        "--sim", "test_sim",
        "--space", "mesh",
        "--analysis-type", "cortical",
        "--atlas-name", "DK40",
        "--region", "precentral"
    ])
    assert rc == 0

    # Test 4: Cortical whole head analysis
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--subs", "101,102",
        "--sim", "test_sim",
        "--space", "mesh",
        "--analysis-type", "cortical",
        "--atlas-name", "HCP_MMP1",
        "--whole-head"
    ])
    assert rc == 0

    # Test 5: Voxel space analysis
    captured_calls.clear()
    atlas_path = str(tmp_path / "atlas.nii.gz")
    with open(atlas_path, "w") as f:
        f.write("fake atlas")
    rc = _run_cli(cli, [
        "--subs", "101,102",
        "--sim", "test_sim",
        "--space", "voxel",
        "--analysis-type", "cortical",
        "--atlas-path", atlas_path,
        "--region", "region1",
        "--quiet"
    ])
    assert rc == 0

    # Test 6: Different coordinate spaces
    for coord_space in ["MNI", "subject"]:
        captured_calls.clear()
        rc = _run_cli(cli, [
            "--subs", "101,102",
            "--sim", "test_sim",
            "--analysis-type", "spherical",
            "--coordinates", "1 2 3",
            "--radius", "5",
            "--coordinate-space", coord_space
        ])
        assert rc == 0

    # Test 7: Custom output directory
    captured_calls.clear()
    out_dir = str(tmp_path / "custom_output")
    rc = _run_cli(cli, [
        "--subs", "101,102",
        "--sim", "test_sim",
        "--analysis-type", "spherical",
        "--coordinates", "0 0 0",
        "--radius", "10",
        "--out", out_dir
    ])
    assert rc == 0
    argv = captured_calls[0][1]
    assert "--output_dir" in argv and out_dir in argv


def test_create_leadfield_direct_comprehensive_argument_coverage(monkeypatch, tmp_path: Path):
    """Test all create leadfield CLI argument combinations for direct mode."""
    from tit.cli import create_leadfield as cl

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Create minimal subject structure
    m2m_dir = proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101"
    eeg_dir = m2m_dir / "eeg_positions"
    eeg_dir.mkdir(parents=True, exist_ok=True)

    # Create fake EEG cap files
    for cap_name in ["GSN-HydroCel-185", "GSN-HydroCel-185.csv"]:
        cap_file = eeg_dir / cap_name
        cap_file.write_text("x,y,z,label\n0,0,0,F3\n0,0,0,F4\n")

    captured_calls = []

    # Mock leadfield dependencies
    def mock_leadfield_generator(*args, **kwargs):
        class MockGen:
            def generate_leadfield(self, output_dir=None, tissues=None, eeg_cap_path=None, cleanup=True):
                captured_calls.append(("generate_leadfield", str(output_dir), tissues, str(eeg_cap_path)))
                from pathlib import Path
                return str(Path(output_dir) / "leadfield.hdf5")
        return MockGen()

    # Mock the actual class that gets instantiated
    monkeypatch.setattr('tit.opt.leadfield.LeadfieldGenerator', mock_leadfield_generator)

    cli = cl.CreateLeadfieldCLI()

    # Test 1: Basic usage with default tissues
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--eeg", "GSN-HydroCel-185"])
    assert rc == 0
    assert len(captured_calls) == 1
    assert captured_calls[0][2] == [1, 2]  # Default tissues (index 2: tissues parameter)

    # Test 2: Custom tissues
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--eeg", "GSN-HydroCel-185", "--tissues", "1", "2", "3"])
    assert rc == 0
    assert captured_calls[0][2] == [1, 2, 3]

    # Test 3: Comma-separated tissues
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--eeg", "GSN-HydroCel-185.csv", "--tissues", "1,2"])
    assert rc == 0
    assert captured_calls[0][2] == [1, 2]

    # Test 4: Single tissue
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--eeg", "GSN-HydroCel-185", "--tissues", "1"])
    assert rc == 0
    assert captured_calls[0][2] == [1]


def test_ex_search_direct_comprehensive_argument_coverage(monkeypatch, tmp_path: Path):
    """Test all ex-search CLI argument combinations for direct mode."""
    from tit.cli import ex_search as ex

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Create minimal project structure
    m2m_dir = proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101"
    eeg_dir = m2m_dir / "eeg_positions"
    lf_dir = proj / "derivatives" / "ti-toolbox" / "sub-101" / "leadfields"
    lf_dir.mkdir(parents=True, exist_ok=True)
    eeg_dir.mkdir(parents=True, exist_ok=True)

    # Create fake EEG cap and leadfield
    eeg_cap = eeg_dir / "GSN-HydroCel-185"
    eeg_cap.write_text("x,y,z,label\n0,0,0,F3\n0,0,0,F4\n0,0,0,P3\n0,0,0,P4\n0,0,0,C3\n0,0,0,C4\n0,0,0,O1\n0,0,0,O2\n")
    lf_file = lf_dir / "101_leadfield_GSN-HydroCel-185.hdf5"
    lf_file.write_text("fake leadfield")

    captured_calls = []

    # Mock ex-search dependencies
    def fake_ex_main():
        captured_calls.append("ex_main_called")

    # Mock the actual function that gets called (use importlib like the original test)
    import importlib
    ex_main_mod = importlib.import_module("tit.opt.ex.main")
    monkeypatch.setattr(ex_main_mod, "main", fake_ex_main)

    cli = ex.ExSearchCLI()

    # Test 1: Buckets mode with all electrodes specified
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--lf", str(lf_file),
        "--roi", "test_roi.csv",
        "--optimization-mode", "buckets",
        "--e1-plus", "F3",
        "--e1-minus", "F4",
        "--e2-plus", "P3",
        "--e2-minus", "P4",
        "--total-current", "1.0",
        "--current-step", "0.1",
        "--channel-limit", "2.0"
    ])
    assert rc == 0
    assert len(captured_calls) == 1

    # Test 2: Pool mode
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--lf", str(lf_file),
        "--roi", "test_roi.csv",
        "--pool",
        "--pool-electrodes", "F3,F4,P3,P4,C3,C4",
        "--total-current", "2.0",
        "--current-step", "0.2"
    ])
    assert rc == 0
    assert len(captured_calls) == 1

    # Test 3: Buckets shorthand flags
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--lf", str(lf_file),
        "--roi", "test_roi.csv",
        "--buckets",
        "--e1-plus", "F3,F4",
        "--e1-minus", "C3,C4",
        "--e2-plus", "P3,P4",
        "--e2-minus", "O1,O2"
    ])
    assert rc == 0

    # Test 4: Default values
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--lf", str(lf_file),
        "--roi", "test_roi.csv",
        "--pool",
        "--pool-electrodes", "F3,F4,P3,P4"
        # Using defaults for total-current, current-step, channel-limit
    ])
    assert rc == 0

    # Test 5: Space-separated electrode lists
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--lf", str(lf_file),
        "--roi", "test_roi.csv",
        "--buckets",
        "--e1-plus", "F3", "F4",
        "--e1-minus", "C3", "C4",
        "--e2-plus", "P3", "P4",
        "--e2-minus", "O1", "O2"
    ])
    assert rc == 0


def test_pre_process_direct_comprehensive_argument_coverage(monkeypatch, tmp_path: Path):
    """Test all pre-process CLI argument combinations for direct mode."""
    from tit.cli import pre_process as pp

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    captured_calls = []

    def fake_run_pipeline(project_dir, subject_ids, **kwargs):
        captured_calls.append((project_dir, list(subject_ids), kwargs))
        return 0

    monkeypatch.setattr(pp, "run_pipeline", fake_run_pipeline)

    cli = pp.PreProcessCLI()

    # Test 1: Basic structural processing
    captured_calls.clear()
    rc = _run_cli(cli, ["--subs", "101,102"])
    assert rc == 0
    assert len(captured_calls) == 1

    # Test 2: Convert DICOM
    captured_calls.clear()
    rc = _run_cli(cli, ["--subs", "101", "--convert-dicom"])
    assert rc == 0
    assert captured_calls[0][2]["convert_dicom"] is True

    # Test 3: Run recon-all
    captured_calls.clear()
    rc = _run_cli(cli, ["--subs", "101", "--run-recon"])
    assert rc == 0
    assert captured_calls[0][2]["run_recon"] is True

    # Test 4: Parallel recon
    captured_calls.clear()
    rc = _run_cli(cli, ["--subs", "101", "--run-recon", "--parallel-recon"])
    assert rc == 0
    assert captured_calls[0][2]["parallel_recon"] is True

    # Test 5: Create m2m
    captured_calls.clear()
    rc = _run_cli(cli, ["--subs", "101", "--create-m2m"])
    assert rc == 0
    assert captured_calls[0][2]["create_m2m"] is True

    # Test 6: Multiple subjects space-separated
    captured_calls.clear()
    rc = _run_cli(cli, ["--subs", "101", "102", "--run-recon"])
    assert rc == 0
    assert set(captured_calls[0][1]) == {"101", "102"}

    # Test 7: Run tissue analysis (requires labeling file in correct location)
    captured_calls.clear()
    rc = _run_cli(cli, ["--subs", "101", "--run-tissue-analysis"])
    assert rc == 0
    assert captured_calls[0][2]["run_tissue_analysis"] is True

    # Test 8: All options combined (requires labeling for both subjects)
    labeling_dir_102 = proj / "derivatives" / "SimNIBS" / "sub-102" / "m2m_102" / "segmentation"
    labeling_dir_102.mkdir(parents=True)
    (labeling_dir_102 / "Labeling.nii.gz").write_text("fake labeling")

    captured_calls.clear()
    rc = _run_cli(cli, [
        "--subs", "101,102",
        "--convert-dicom",
        "--run-recon",
        "--parallel-recon",
        "--create-m2m",
        "--run-tissue-analysis"
    ])
    assert rc == 0
    assert len(captured_calls) == 1


def test_vis_blender_direct_comprehensive_argument_coverage(monkeypatch, tmp_path: Path):
    """Test all vis-blender CLI argument combinations for direct mode."""
    # Mock simnibs before any imports that depend on it
    import sys
    from unittest.mock import MagicMock

    # Create mock simnibs module to avoid import errors in test environment
    mock_simnibs = MagicMock()
    monkeypatch.setitem(sys.modules, 'simnibs', mock_simnibs)
    monkeypatch.setitem(sys.modules, 'simnibs.mesh_io', MagicMock())

    from tit.cli import vis_blender as vb

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Create minimal simulation structure
    sim_dir = proj / "derivatives" / "SimNIBS" / "sub-101" / "Simulations" / "test_sim"
    config_dir = sim_dir / "documentation"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text('{"montage": {"pairs": [["F3", "F4"], ["C3", "C4"]]}}')

    captured_calls = []

    # Mock blender dependencies - need to create a full mock API
    def mock_create_montage(req, *, logger=None):
        # Capture the request object's attributes as a dict
        req_dict = {
            'subject_id': req.subject_id,
            'simulation_name': req.simulation_name,
            'output_dir': req.output_dir,
            'show_full_net': req.show_full_net,
            'electrode_diameter_mm': req.electrode_diameter_mm,
            'electrode_height_mm': req.electrode_height_mm,
            'export_glb': req.export_glb,
        }
        captured_calls.append(("create_montage_publication_blend", req_dict))
        class MockResult:
            scalp_stl = "scalp.stl"
            gm_stl = "gm.stl"
            electrodes_blend = "elec.blend"
            final_blend = "final.blend"
        return MockResult()

    # Create a real MontagePublicationRequest class for the mock
    from dataclasses import dataclass
    from typing import Optional as Opt

    @dataclass(frozen=True)
    class MockRequest:
        subject_id: str
        simulation_name: str
        output_dir: Opt[str] = None
        show_full_net: bool = True
        electrode_diameter_mm: float = 10.0
        electrode_height_mm: float = 6.0
        export_glb: bool = False

    # Create mock API module to avoid importing montage_publication
    mock_api = MagicMock()
    mock_api.MontagePublicationRequest = MockRequest
    mock_api.create_montage_publication_blend = mock_create_montage
    monkeypatch.setitem(sys.modules, 'tit.blender.api', mock_api)

    # Mock _setup_logging to return a valid log file path
    def mock_setup_logging(self, args):
        log_file = str(tmp_path / f"vis_blender_{args['simulation']}.log")
        return log_file
    monkeypatch.setattr(vb.VisBlenderCLI, "_setup_logging", mock_setup_logging)

    # Mock the logger setup function
    def mock_setup_logging_with_file(verbose, log_file):
        import logging
        return logging.getLogger("mock_logger")
    monkeypatch.setattr('tit.cli.vis_blender._setup_logging_with_file', mock_setup_logging_with_file)

    cli = vb.VisBlenderCLI()

    # Test 1: Basic usage with defaults
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--sim", "test_sim"])
    assert rc == 0
    assert len(captured_calls) == 1

    # Test 2: With montage-only flag
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--sim", "test_sim", "--montage-only"])
    assert rc == 0
    assert captured_calls[0][1]["show_full_net"] is False

    # Test 3: Custom electrode dimensions
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--sim", "test_sim",
        "--electrode-diameter-mm", "12.0",
        "--electrode-height-mm", "8.0"
    ])
    assert rc == 0
    assert captured_calls[0][1]["electrode_diameter_mm"] == 12.0
    assert captured_calls[0][1]["electrode_height_mm"] == 8.0

    # Test 4: Custom output directory
    captured_calls.clear()
    out_dir = str(tmp_path / "custom_output")
    rc = _run_cli(cli, ["--sub", "101", "--sim", "test_sim", "--out", out_dir])
    assert rc == 0
    assert captured_calls[0][1]["output_dir"] == out_dir

    # Test 5: Verbose logging
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--sim", "test_sim", "--verbose"])
    assert rc == 0

    # Test 6: Export GLB option
    captured_calls.clear()
    rc = _run_cli(cli, ["--sub", "101", "--sim", "test_sim", "--export-glb"])
    assert rc == 0
    assert captured_calls[0][1]["export_glb"] is True

    # Test 7: All options combined
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--sub", "101",
        "--sim", "test_sim",
        "--montage-only",
        "--electrode-diameter-mm", "15.0",
        "--electrode-height-mm", "7.5",
        "--export-glb",
        "--verbose"
    ])
    assert rc == 0
    assert captured_calls[0][1]["show_full_net"] is False
    assert captured_calls[0][1]["electrode_diameter_mm"] == 15.0
    assert captured_calls[0][1]["electrode_height_mm"] == 7.5
    assert captured_calls[0][1]["export_glb"] is True


def test_cluster_permutation_direct_comprehensive_argument_coverage(monkeypatch, tmp_path: Path):
    """Test all cluster permutation CLI argument combinations for direct mode."""
    from tit.cli import cluster_permuatation as cp

    captured_calls = []

    # Mock stats dependencies
    def fake_run_analysis(*args, **kwargs):
        captured_calls.append(("run_analysis", kwargs))

    # Mock the actual function that gets called
    monkeypatch.setattr('tit.stats.permutation_analysis.run_analysis', fake_run_analysis)

    cli = cp.PermutationCLI()

    # Test 1: Group comparison analysis
    captured_calls.clear()
    csv_file = tmp_path / "subjects.csv"
    csv_file.write_text("subject_id,simulation_name,response\n101,simA,1\n102,simA,0\n")
    rc = _run_cli(cli, [
        "--csv", str(csv_file),
        "--name", "test_analysis",
        "--analysis-type", "group_comparison"
    ])
    assert rc == 0
    assert len(captured_calls) == 1
    assert captured_calls[0][1]["analysis_name"] == "test_analysis"

    # Test 2: Correlation analysis
    captured_calls.clear()
    csv_file2 = tmp_path / "correlation.csv"
    csv_file2.write_text("subject_id,simulation_name,response,predictor\n101,simA,1.5,2.3\n102,simA,2.1,1.8\n")
    rc = _run_cli(cli, [
        "--csv", str(csv_file2),
        "--name", "corr_analysis",
        "--analysis-type", "correlation",
        "--use-weights"
    ])
    assert rc == 0
    assert captured_calls[0][1]["config"]["use_weights"] is True

    # Test 3: Custom permutation parameters
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--csv", str(csv_file),
        "--name", "custom_params",
        "--analysis-type", "group_comparison",
        "--cluster-threshold", "0.01",
        "--cluster-stat", "size",
        "--n-permutations", "2000",
        "--alpha", "0.01",
        "--n-jobs", "2"
    ])
    assert rc == 0
    config = captured_calls[0][1]["config"]
    assert config["cluster_threshold"] == 0.01
    assert config["cluster_stat"] == "size"
    assert config["n_permutations"] == 2000
    assert config["alpha"] == 0.01
    assert config["n_jobs"] == 2

    # Test 4: Tissue type options
    for tissue in ["grey", "white", "all"]:
        captured_calls.clear()
        rc = _run_cli(cli, [
            "--csv", str(csv_file),
            "--name", f"tissue_{tissue}",
            "--analysis-type", "group_comparison",
            "--tissue-type", tissue
        ])
        assert rc == 0
        assert captured_calls[0][1]["config"]["tissue_type"] == tissue

    # Test 5: With custom nifti pattern
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--csv", str(csv_file),
        "--name", "custom_pattern",
        "--analysis-type", "group_comparison",
        "--nifti-pattern", "*.nii.gz"
    ])
    assert rc == 0
    assert captured_calls[0][1]["config"]["nifti_pattern"] == "*.nii.gz"

    # Test 6: Quiet and save log options
    captured_calls.clear()
    rc = _run_cli(cli, [
        "--csv", str(csv_file),
        "--name", "quiet_test",
        "--analysis-type", "group_comparison",
        "--quiet",
        "--save-perm-log"
    ])
    assert rc == 0
    config = captured_calls[0][1]["config"]
    assert config["quiet"] is True
    assert config["save_perm_log"] is True


def test_cli_argument_validation_error_handling(monkeypatch, tmp_path: Path):
    """Test that CLI scripts properly handle invalid arguments and missing required args."""
    from tit.cli import analyzer as analyzer_cli
    from tit.cli import simulator as sim_cli
    from tit.cli import group_analyzer as ga
    from tit.cli import ex_search as ex

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Create minimal project structure
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101").mkdir(parents=True, exist_ok=True)
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "Simulations" / "test_sim" / "TI" / "mesh").mkdir(parents=True, exist_ok=True)

    # Test 1: Invalid argument types - should be caught by argparse
    sim_cli_inst = sim_cli.SimulatorCLI()
    # Mock execute to avoid actual execution
    def mock_execute(args):
        return 0
    monkeypatch.setattr(sim_cli_inst, "execute", mock_execute)

    # Invalid thickness type should be caught by argparse
    rc = _run_cli(sim_cli_inst, ["--sub", "101", "--montages", "test", "--eeg", "GSN-HydroCel-185", "--thickness", "not_a_number"])
    assert rc != 0  # Should fail due to invalid float type

    # Test 2: Invalid framework choice
    rc = _run_cli(sim_cli_inst, ["--sub", "101", "--framework", "invalid", "--montages", "test", "--eeg", "GSN-HydroCel-185"])
    assert rc != 0  # Should fail due to invalid choice

    # Test 3: Invalid conductivity choice
    rc = _run_cli(sim_cli_inst, ["--sub", "101", "--montages", "test", "--eeg", "GSN-HydroCel-185", "--conductivity", "invalid"])
    assert rc != 0  # Should fail due to invalid choice

    # Test 4: Invalid electrode shape choice
    rc = _run_cli(sim_cli_inst, ["--sub", "101", "--montages", "test", "--eeg", "GSN-HydroCel-185", "--electrode-shape", "invalid"])
    assert rc != 0  # Should fail due to invalid choice

    # Test 5: Invalid mode choice
    rc = _run_cli(sim_cli_inst, ["--sub", "101", "--montages", "test", "--eeg", "GSN-HydroCel-185", "--mode", "invalid"])
    assert rc != 0  # Should fail due to invalid choice


def test_cli_argument_type_validation(monkeypatch, tmp_path: Path):
    """Test that CLI scripts properly validate argument types."""
    from tit.cli import analyzer as analyzer_cli
    from tit.cli import simulator as sim_cli

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Create minimal project structure
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101").mkdir(parents=True, exist_ok=True)
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "Simulations" / "test_sim" / "TI" / "mesh").mkdir(parents=True, exist_ok=True)

    # Mock execute methods to avoid actual execution
    def mock_execute(args):
        return 0

    # Test 1: Analyzer invalid radius type - should be caught by argparse
    analyzer_cli_inst = analyzer_cli.AnalyzerCLI()
    monkeypatch.setattr(analyzer_cli_inst, "execute", mock_execute)
    rc = _run_cli(analyzer_cli_inst, [
        "--sub", "101",
        "--sim", "test_sim",
        "--coordinates", "0", "0", "0",
        "--radius", "not_a_number"
    ])
    assert rc != 0  # Should fail due to invalid radius type

    # Test 2: Simulator invalid thickness type - should be caught by argparse
    sim_cli_inst = sim_cli.SimulatorCLI()
    monkeypatch.setattr(sim_cli_inst, "execute", mock_execute)
    rc = _run_cli(sim_cli_inst, [
        "--sub", "101",
        "--montages", "test_montage",
        "--eeg", "GSN-HydroCel-185",
        "--thickness", "not_a_number"
    ])
    assert rc != 0  # Should fail due to invalid thickness type

    # Test 3: Analyzer invalid coordinate space - should be caught by argparse
    rc = _run_cli(analyzer_cli_inst, [
        "--sub", "101",
        "--sim", "test_sim",
        "--coordinates", "0", "0", "0",
        "--radius", "10",
        "--coordinate-space", "invalid_space"
    ])
    assert rc != 0  # Should fail due to invalid coordinate space

    # Test 4: Simulator invalid framework - should be caught by argparse
    rc = _run_cli(sim_cli_inst, [
        "--sub", "101",
        "--montages", "test_montage",
        "--eeg", "GSN-HydroCel-185",
        "--framework", "invalid_framework"
    ])
    assert rc != 0  # Should fail due to invalid framework

    # Test 5: Analyzer invalid analysis type - should be caught by argparse
    rc = _run_cli(analyzer_cli_inst, [
        "--sub", "101",
        "--sim", "test_sim",
        "--analysis-type", "invalid_type",
        "--coordinates", "0", "0", "0",
        "--radius", "10"
    ])
    assert rc != 0  # Should fail due to invalid analysis type

    # Test 6: Valid cases should work
    rc = _run_cli(analyzer_cli_inst, [
        "--sub", "101",
        "--sim", "test_sim",
        "--coordinates", "0", "0", "0",
        "--radius", "10"
    ])
    assert rc == 0  # Should work with valid arguments


def test_cli_list_commands_no_execution(monkeypatch, tmp_path: Path):
    """Test that list commands don't trigger actual execution."""
    from tit.cli import simulator as sim_cli

    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PROJECT_DIR", str(proj))

    # Create minimal subject structure for list commands
    (proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101" / "eeg_positions").mkdir(parents=True, exist_ok=True)
    eeg_cap = proj / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101" / "eeg_positions" / "GSN-HydroCel-185"
    eeg_cap.write_text("x,y,z,label\n0,0,0,F3\n")

    # Track what gets called
    captured_calls = []

    cli = sim_cli.SimulatorCLI()

    # Mock the execute method to track calls
    original_execute = cli.execute
    def mock_execute(args):
        captured_calls.append(("execute_called", args))
        return 0
    monkeypatch.setattr(cli, "execute", mock_execute)

    # Test list-subjects - should call execute since it handles the list internally
    captured_calls.clear()
    rc = _run_cli(cli, ["--list-subjects"])
    assert rc == 0
    # List commands are handled in execute, so execute should be called
    assert len(captured_calls) == 1
    assert captured_calls[0][1]["list_subjects"] is True

    # Test list-eeg-caps
    captured_calls.clear()
    rc = _run_cli(cli, ["--list-eeg-caps", "--sub", "101"])
    assert rc == 0
    assert len(captured_calls) == 1
    assert captured_calls[0][1]["list_eeg_caps"] is True

    # Test list-montages
    captured_calls.clear()
    rc = _run_cli(cli, ["--list-montages", "--eeg", "GSN-HydroCel-185"])
    assert rc == 0
    assert len(captured_calls) == 1
    assert captured_calls[0][1]["list_montages"] is True




