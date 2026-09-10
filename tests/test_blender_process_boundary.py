"""Montage transport preserves scientific geometry; renderer imports no scientific stack."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("config_type", "memory_gb"),
    [
        ("MontageConfig", 16),
        (None, 16),
        ("FutureExportConfig", 16),
        ("VectorConfig", 2),
        ("RegionConfig", 2),
        ("SubcorticalConfig", 2),
    ],
)
def test_only_montage_reserves_full_blender_memory(config_type, memory_gb):
    from tit.jobs.costs import default_cost

    config = {"_type": config_type} if config_type else {}
    assert default_cost("blender", config).mem_gb == memory_gb
    # Explicit project/job resource requests still take precedence.
    assert default_cost("blender", {**config, "memory_gb": 24}).mem_gb == 24


def test_renderer_modules_do_not_import_scientific_packages():
    source = """
import importlib.abc, sys
class BlockScience(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'simnibs','scipy','nibabel','bpy'}:
            raise AssertionError('renderer eagerly imported ' + fullname)
sys.meta_path.insert(0, BlockScience())
import tit.blender
from tit.blender import montage_scene, electrode_placement, scene_setup
assert 'run_montage' in tit.blender.__all__
assert not {'simnibs','scipy','nibabel','bpy'}.intersection(sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", source], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_parent_passes_subject_geometry_exactly_and_inherits_process_group(tmp_path):
    from tit.blender import montage_publication as montage

    output = tmp_path / "out"
    output.mkdir()
    m2m = tmp_path / "m2m"
    m2m.mkdir()
    (m2m / "fixture.msh").touch()
    (tmp_path / "canonical_TI.msh").touch()
    (tmp_path / "net.csv").write_text("fixture")
    # Non-float32 coordinates expose a lossy STL transport immediately.
    vertices = np.array([[0.1234567890123, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 3.0, 0.0]])
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    pm = SimpleNamespace(
        simulation=lambda *a: str(tmp_path),
        ti_mesh=lambda *a: str(tmp_path / "canonical_TI.msh"),
        m2m=lambda *a: str(m2m),
        project_dir=str(tmp_path),
    )
    seen = []

    def child(argv, **kwargs):
        assert "--background" in argv and "--python-exit-code" in argv
        assert kwargs["check"] is True
        assert "start_new_session" not in kwargs and "preexec_fn" not in kwargs
        assert not {"PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"}.intersection(
            kwargs["env"]
        )
        manifest = json.loads(Path(argv[-1]).read_text())
        seen.append(manifest)
        with np.load(manifest["geometry"], allow_pickle=False) as mesh:
            np.testing.assert_array_equal(mesh["vertices"], vertices)
            np.testing.assert_array_equal(mesh["faces"], faces)
        assert manifest["placement"]["subject_msh_path"] is None
        assert manifest["electrodes"] == [["E1", 1.0, 2.0, 3.0]]
        (output / "fixture_electrodes_net.blend").write_bytes(b"BLENDER")
        (output / "fixture_pair_montage_publication.blend").write_bytes(b"BLENDER")
        return subprocess.CompletedProcess(argv, 0)

    with (
        patch.object(montage, "get_path_manager", return_value=pm),
        patch.object(
            montage.be_utils,
            "load_simulation_config",
            return_value={"eeg_net": "net.csv", "electrode_pairs": [["E1", "E2"]]},
        ),
        patch.object(montage, "export_scalp_stl_from_sim") as scalp,
        patch.object(montage, "export_gm_stl_from_sim"),
        patch.object(
            montage, "_resolve_eeg_net_csv", return_value=str(tmp_path / "net.csv")
        ),
        patch.object(
            montage.be_utils, "extract_scalp_from_msh", return_value=(vertices, faces)
        ) as extract,
        patch.object(
            montage, "read_electrodes", return_value=iter([["E1", 1.0, 2.0, 3.0]])
        ),
        patch.object(montage.subprocess, "run", side_effect=child),
    ):
        result = montage.build_montage_publication_blend(
            subject_id="fixture", simulation_name="pair", output_dir=str(output)
        )
    scalp.assert_called_once_with(
        str(tmp_path),
        output_stl=str(output / "scalp.stl"),
        mesh_path=str(tmp_path / "canonical_TI.msh"),
    )
    extract.assert_called_once_with(str(m2m / "fixture.msh"), 1005)
    assert result.final_blend == str(output / "fixture_pair_montage_publication.blend")
    assert len(seen) == 1
    assert not Path(seen[0]["geometry"]).exists()


def test_runtime_guard_does_not_hide_unexpected_dependency_failures():
    spec = importlib.util.spec_from_file_location(
        "verify_runtime", ROOT / "container/blueprint/verify_runtime.py"
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    expected = "\n".join(
        f"simnibs 4.6.0 requires {name}, which is not installed."
        for name in ("gmsh", "PyQt5", "mkl", "tbb")
    )
    assert guard.unexpected_dependency_errors(expected) == []
    for violation in (
        "simnibs 4.6.0 has requirement numpy>=2, but you have numpy 1.26.4.",
        "bpy 4.4.0 is not supported on this platform",
        "simnibs 4.6.0 requires scipy, which is not installed.",
        "pip could not inspect the environment",
    ):
        assert guard.unexpected_dependency_errors(expected + "\n" + violation) == [
            violation
        ]


def test_real_background_montage_saves_and_reopens(tmp_path):
    """Opt-in image leg: actual Blender geometry, template, materials and saved-file reopen."""
    import os

    executable = os.environ.get("TIT_TEST_BLENDER_BIN")
    if not executable:
        pytest.skip(
            "set TIT_TEST_BLENDER_BIN to the image standalone Blender executable"
        )
    from tit.blender.io import write_binary_stl

    vertices = np.array(
        [
            [100.0, 0, 0],
            [-100.0, 0, 0],
            [0, 100.0, 0],
            [0, -100.0, 0],
            [0, 0, 100.0],
            [0, 0, -100.0],
        ]
    )
    faces = np.array(
        [
            [0, 2, 4],
            [2, 1, 4],
            [1, 3, 4],
            [3, 0, 4],
            [2, 0, 5],
            [1, 2, 5],
            [3, 1, 5],
            [0, 3, 5],
        ]
    )
    np.savez(tmp_path / "scalp.npz", vertices=vertices, faces=faces)
    write_binary_stl(str(tmp_path / "scalp.stl"), vertices, faces)
    write_binary_stl(str(tmp_path / "gm.stl"), vertices * 0.7, faces)
    (tmp_path / "fixture.csv").write_text(
        "Electrode,0,0,100,E1\nElectrode,100,0,0,E2\n"
    )
    manifest = {
        "subject_id": "fixture",
        "simulation_name": "pair",
        "output_dir": str(tmp_path),
        "gm_stl": str(tmp_path / "gm.stl"),
        "geometry": str(tmp_path / "scalp.npz"),
        "electrodes": [["E1", 0.0, 0.0, 100.0], ["E2", 100.0, 0.0, 0.0]],
        "placement": {
            "subject_id": "fixture",
            "electrode_csv_path": str(tmp_path / "fixture.csv"),
            "electrode_blend_path": str(ROOT / "tit/blender/Electrode.blend"),
            "output_dir": str(tmp_path),
            "scalp_stl_path": str(tmp_path / "scalp.stl"),
            "subject_msh_path": None,
            "montage_pairs": [["E1", "E2"]],
            "show_full_net": False,
        },
    }
    (tmp_path / "montage.json").write_text(json.dumps(manifest))
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"}
    }
    completed = subprocess.run(
        [
            executable,
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(ROOT / "tit/blender/montage_scene.py"),
            "--",
            str(tmp_path / "montage.json"),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    final = tmp_path / "fixture_pair_montage_publication.blend"
    assert final.stat().st_size > 0
    expression = f"""import bpy,sys
assert bpy.app.background
bpy.ops.wm.open_mainfile(filepath={str(final)!r})
assert bpy.data.objects.get('Scalp') and bpy.data.objects.get('GM')
assert len([o for o in bpy.data.objects if o.type=='MESH'])==4
assert len([o for o in bpy.data.objects if o.type=='CAMERA'])==6
assert bpy.context.scene.render.engine=='BLENDER_EEVEE_NEXT'
assert bpy.context.scene.view_settings.look=='AgX - Medium High Contrast'
assert not {{'simnibs','scipy','nibabel'}}.intersection(sys.modules)
print('Montage geometry and camera assertions passed')
"""
    reopened = subprocess.run(
        [
            executable,
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python-expr",
            expression,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr


def test_prepared_electrodes_preserve_simnibs_row_selection():
    from tit.blender.montage_publication import read_electrodes

    reader = SimpleNamespace(
        read_csv_positions=lambda path: (
            ["Electrode", "Fiducial", "ReferenceElectrode"],
            np.array([[1.0, 2.0, 3.0], [9.0, 9.0, 9.0], [4.0, 5.0, 6.0]]),
            None,
            ["E1", "Nz", ""],
            None,
            None,
        )
    )
    with patch.dict(sys.modules, {"simnibs.utils.csv_reader": reader}):
        assert list(read_electrodes("fixture.csv")) == [
            ["E1", 1.0, 2.0, 3.0],
            ["Electrode", 4.0, 5.0, 6.0],
        ]
