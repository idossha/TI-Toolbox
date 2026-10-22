"""Analyzer empty-ROI refusal, TI_normal mesh analysis and .msh headers with the real libraries (2026-10-22).

What this pins (the real-library leg of tests/test_analyzer_empty_roi.py and
tests/test_analyzer_ti_normal.py)
    1. The runner, run as ``python -m tit.analyzer config.json`` on a real NIfTI field, exits 1
       with the empty-ROI sentence for a sphere outside the head and writes no analysis folder;
       the same config with a sphere inside the field exits 0 and reports the voxel count a
       hand count gives.
    2. On a surface SimNIBS itself writes and reads (``mesh_io``), ``field="TI_normal"`` reads
       the normal mesh: ``roi_mean`` equals the area-weighted mean of the authored values with
       node areas computed here from the triangles (one third of each triangle's area to each
       of its corners), and the ``TI_max`` run of the same ROI reports the same numbers as
       ``normal_mean``/``normal_max``.
    3. ``msh_field_names`` reads the field names of binary meshes SimNIBS wrote (SimNIBS 4.6's
       ASCII writer raises TypeError, so ASCII is pinned by the hand-written host fixture).
    4. Dataset 000 (``TIT_DATASET_000``): on sub-101's Thalamus_example the central surface
       carries only TI_max and the normal mesh only TI_normal, and a DK40 lh.insula analysis of
       TI_normal reports roi_max <= the TI_max analysis's roi_max (TI_normal is the envelope
       along one direction, TI_max its maximum over directions; wiki analyzer.md).

Where the numbers come from
    Authored meshes and fields (coordinates, triangles and values below), hand counts and an
    independent node-area formula; Dataset 000 only through inequalities and field names.

Run (in the image; SimNIBS runs in a subprocess because tests/conftest.py mocks it):
    simnibs_python -m pytest tests/numerical/test_analyzer_p06_real.py -q -p no:cacheprovider
    with ``-v <Dataset 000>:/data/000:ro -e TIT_DATASET_000=/data/000`` for case 4.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
SID = "101"
SIM = "M1"


def _python(code: str, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _require(modules: str) -> None:
    probe = _python(f"import {modules}")
    if probe.returncode:
        pytest.skip(f"skipping: needs {modules} (run with simnibs_python in the image)")


# -- 1. the runner on a real NIfTI ---------------------------------------------------------------


def _voxel_project(tmp_path: Path) -> tuple[Path, np.ndarray]:
    import nibabel as nib

    project = tmp_path / "project"
    sim = project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / SIM
    niftis = sim / "TI" / "niftis"
    niftis.mkdir(parents=True)
    m2m = project / "derivatives" / "SimNIBS" / f"sub-{SID}" / f"m2m_{SID}"
    m2m.mkdir(parents=True)
    (m2m / f"{SID}.msh").write_bytes(b"")
    field = np.zeros((10, 10, 10), dtype=np.float32)
    field[2:8, 2:8, 2:8] = np.linspace(0.1, 1.0, 216).reshape(6, 6, 6)
    field[4, 4, 4] = 0.0  # inside the sphere below, not positive: not counted
    affine = np.diag([2.0, 2.0, 2.0, 1.0])  # 2 mm voxels, origin at voxel (0, 0, 0)
    nib.save(
        nib.Nifti1Image(field, affine),
        str(niftis / f"grey_{SIM}_TI_subject_TI_max.nii"),
    )
    return project, field


def _run_analyzer(tmp_path: Path, project: Path, center, radius):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "project_dir": str(project),
                "mode": "single",
                "subject_id": SID,
                "simulation": SIM,
                "space": "voxel",
                "analysis_type": "spherical",
                "center": list(center),
                "radius": radius,
                "visualize": False,
            }
        )
    )
    code = "import runpy, sys; sys.argv = ['tit.analyzer', sys.argv[1]]; runpy.run_module('tit.analyzer', run_name='__main__')"
    return _python(code, str(config))


def test_runner_refuses_an_empty_voxel_roi_and_measures_a_real_one(tmp_path):
    _require("nibabel, pandas, matplotlib, tit.analyzer")
    project, field = _voxel_project(tmp_path)
    analyses = (
        project
        / "derivatives"
        / "SimNIBS"
        / f"sub-{SID}"
        / "Simulations"
        / SIM
        / "Analyses"
    )

    run = _run_analyzer(tmp_path, project, (500.0, 500.0, 500.0), 10.0)
    text = run.stdout + run.stderr
    assert run.returncode == 1, text
    assert "does not overlap positive TI_max values in the selected tissue (GM" in text
    assert "zero-size" not in text
    assert not analyses.exists()

    # Sphere at world (9, 9, 9) = voxel (4.5, 4.5, 4.5), r = 2.5 mm: the 8 voxels around it
    # (each sqrt(3) mm away), one of them (4, 4, 4) set to 0 -> 7 positive voxels of 8 mm^3.
    run = _run_analyzer(tmp_path, project, (9.0, 9.0, 9.0), 2.5)
    assert run.returncode == 0, run.stdout + run.stderr
    (results,) = list(analyses.rglob("results.csv"))
    rows = dict(csv.reader(results.open()))
    assert int(rows["n_elements"]) == 7
    assert float(rows["total_area_or_volume"]) == pytest.approx(7 * 8.0)
    block = field[4:6, 4:6, 4:6]
    assert float(rows["roi_mean"]) == pytest.approx(block[block > 0].mean(), rel=1e-6)


# -- 2 and 3. SimNIBS-written meshes -------------------------------------------------------------

_SURFACE_SCRIPT = r"""
import json, sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
from simnibs.mesh_tools import mesh_io

root = Path(sys.argv[1])
spec = json.loads(Path(sys.argv[2]).read_text())
coords = np.array(spec["coords"], float)
tris = np.array(spec["triangles"], int) + 1  # Gmsh numbering

def surface(fields, path):
    mesh = mesh_io.Msh(mesh_io.Nodes(coords), mesh_io.Elements(triangles=tris))
    mesh.elm.tag1 = mesh.elm.tag2 = np.full(len(tris), 1002)
    for name, values in fields.items():
        mesh.add_node_field(np.array(values, float), name)
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh_io.write_msh(mesh, str(path), mode="binary")

if spec["mode"] == "headers":
    surface({"TI_max": spec["ti_max"], "hf_peak": spec["ti_max"]}, root / "binary.msh")
    surface({"TI_normal": spec["ti_normal"]}, root / "normal.msh")
    sys.exit(0)

from tit.paths import get_path_manager
root.mkdir(parents=True, exist_ok=True)
pm = get_path_manager(str(root))
Path(pm.m2m("101")).mkdir(parents=True)
Path(pm.ti_mesh("101", "M1")).parent.mkdir(parents=True)
Path(pm.ti_mesh("101", "M1")).write_bytes(b"")
surface({"TI_max": spec["ti_max"]}, Path(pm.ti_central_surface("101", "M1")))
surface({"TI_normal": spec["ti_normal"]}, Path(pm.ti_mesh_dir("101", "M1")) / "M1_normal.msh")

from tit.analyzer.analyzer import Analyzer
out = {}
for field in ("TI_normal", None, "hf_peak"):
    with patch("tit.analyzer.analyzer.add_file_handler"):
        a = Analyzer("101", "M1", space="mesh", field=field)
    try:
        r = a.analyze_sphere(tuple(spec["center"]), spec["radius"])
        out[str(field)] = {k: getattr(r, k) for k in ("roi_mean", "roi_max", "roi_min", "n_elements", "normal_mean", "normal_max", "field_name")}
    except ValueError as exc:
        out[str(field)] = {"error": str(exc)}
print("RESULT " + json.dumps(out))
"""


def _surface_spec() -> dict:
    """A flat 5x5 grid, 10 mm apart, two triangles per square; authored node values."""
    xs = np.arange(5) * 10.0
    coords = [[x, y, 0.0] for y in xs for x in xs]
    tris = []
    for j in range(4):
        for i in range(4):
            a, b, c, d = j * 5 + i, j * 5 + i + 1, (j + 1) * 5 + i, (j + 1) * 5 + i + 1
            tris += [[a, b, d], [a, d, c]]
    n = len(coords)
    ti_max = (0.2 + 0.03 * np.arange(n)).tolist()
    ti_normal = (0.6 * np.array(ti_max) * np.cos(np.arange(n))).tolist()
    return {
        "coords": coords,
        "triangles": tris,
        "ti_max": ti_max,
        "ti_normal": ti_normal,
        "center": [20.0, 20.0, 0.0],
        "radius": 10.5,
    }


def _node_areas(spec: dict) -> np.ndarray:
    """One third of each triangle's area to each of its corners."""
    coords = np.array(spec["coords"])
    areas = np.zeros(len(coords))
    for tri in spec["triangles"]:
        p = coords[tri]
        areas[tri] += 0.5 * np.linalg.norm(np.cross(p[1] - p[0], p[2] - p[0])) / 3.0
    return areas


def test_ti_normal_mesh_analysis_on_a_simnibs_surface(tmp_path):
    _require("simnibs.mesh_tools.mesh_io, pandas, matplotlib")
    spec = _surface_spec()
    spec["mode"] = "analyze"
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    run = _python(_SURFACE_SCRIPT, str(tmp_path / "project"), str(spec_path))
    assert run.returncode == 0, run.stdout + run.stderr
    line = [l for l in run.stdout.splitlines() if l.startswith("RESULT ")][-1]
    out = json.loads(line[len("RESULT ") :])

    coords = np.array(spec["coords"])
    inside = np.linalg.norm(coords - np.array(spec["center"]), axis=1) <= spec["radius"]
    assert inside.sum() == 5  # the centre node and its four 10 mm neighbours
    normal = np.array(spec["ti_normal"])
    areas = _node_areas(spec)
    pos = inside & (normal > 0)
    expected_mean = float(np.sum(normal[pos] * areas[pos]) / np.sum(areas[pos]))

    got = out["TI_normal"]
    assert got["field_name"] == "TI_normal"
    assert got["n_elements"] == int(pos.sum())
    assert got["roi_mean"] == pytest.approx(expected_mean, rel=1e-9)
    assert got["roi_max"] == pytest.approx(normal[pos].max())
    # The TI_max run of the same ROI reports the same numbers through _get_normal_stats.
    assert out["None"]["normal_mean"] == pytest.approx(got["roi_mean"], rel=1e-12)
    assert out["None"]["normal_max"] == pytest.approx(got["roi_max"], rel=1e-12)
    assert "hf_peak" in out["hf_peak"]["error"] and "TI_max" in out["hf_peak"]["error"]


def test_msh_field_names_reads_simnibs_written_meshes(tmp_path):
    _require("simnibs.mesh_tools.mesh_io")
    from tit.analyzer.analyzer import msh_field_names

    spec = {**_surface_spec(), "mode": "headers"}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    run = _python(_SURFACE_SCRIPT, str(tmp_path), str(spec_path))
    assert run.returncode == 0, run.stdout + run.stderr
    assert msh_field_names(tmp_path / "binary.msh") == {"TI_max", "hf_peak"}
    assert msh_field_names(tmp_path / "normal.msh") == {"TI_normal"}


# -- 4. Dataset 000 ------------------------------------------------------------------------------

_DATASET = os.environ.get("TIT_DATASET_000", "")
_THALAMUS = (
    Path(_DATASET)
    / "derivatives"
    / "SimNIBS"
    / "sub-101"
    / "Simulations"
    / "Thalamus_example"
)
needs_dataset = pytest.mark.skipif(
    not (_DATASET and _THALAMUS.is_dir()),
    reason="skipping: set TIT_DATASET_000 to a Dataset 000 copy with sub-101/Thalamus_example",
)

_REALDATA_SCRIPT = r"""
import json, sys
from pathlib import Path
from unittest.mock import patch
from tit.paths import get_path_manager
from tit.analyzer.analyzer import Analyzer

get_path_manager(sys.argv[1])
out = {}
for field in ("TI_normal", "TI_max"):
    with patch("tit.analyzer.analyzer.add_file_handler"):
        a = Analyzer("101", "Thalamus_example", space="mesh", field=field)
    r = a.analyze_cortex("DK40", "lh.insula")
    out[field] = {k: getattr(r, k) for k in ("roi_mean", "roi_max", "normal_mean", "normal_max", "n_elements")}
print("RESULT " + json.dumps(out))
"""


def _mtimes(paths) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in paths}


def _tree_state(root: Path) -> dict[str, tuple[int, int]]:
    """(mtime_ns, size) of *root* and everything under it: a new, changed or removed file shows."""
    entries = [root, *root.rglob("*")]
    return {str(p): (p.lstat().st_mtime_ns, p.lstat().st_size) for p in entries}


@needs_dataset
def test_dataset000_surface_fields_and_ti_normal_below_ti_max(tmp_path):
    from tit.analyzer.analyzer import msh_field_names

    central = _THALAMUS / "TI" / "mesh" / "surfaces" / "Thalamus_example_TI_central.msh"
    normal = _THALAMUS / "TI" / "mesh" / "Thalamus_example_normal.msh"
    head_model = Path(_DATASET) / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101"
    before = _mtimes([central, normal])
    # The head model is linked, not copied, into the tmp project below: guard all of it.
    head_before = _tree_state(head_model)
    assert len(head_before) > 1  # has files to guard
    assert msh_field_names(central) == {"TI_max"}
    assert msh_field_names(normal) == {"TI_normal"}

    _require("simnibs.utils.transformations, pandas, matplotlib")
    import shutil

    project = tmp_path / "project"
    sim = (
        project
        / "derivatives"
        / "SimNIBS"
        / "sub-101"
        / "Simulations"
        / "Thalamus_example"
    )
    (sim / "TI" / "mesh" / "surfaces").mkdir(parents=True)
    shutil.copy(central, sim / "TI" / "mesh" / "surfaces" / central.name)
    shutil.copy(normal, sim / "TI" / "mesh" / normal.name)
    (sim / "TI" / "mesh" / "Thalamus_example_TI.msh").write_bytes(
        b""
    )  # never read in mesh space
    # The head model is only read (atlas2subject); link it rather than copy gigabytes.
    (project / "derivatives" / "SimNIBS" / "sub-101" / "m2m_101").symlink_to(head_model)

    run = _python(_REALDATA_SCRIPT, str(project), timeout=600)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-3000:]
    line = [l for l in run.stdout.splitlines() if l.startswith("RESULT ")][-1]
    out = json.loads(line[len("RESULT ") :])
    assert out["TI_normal"]["n_elements"] > 0
    assert out["TI_normal"]["roi_max"] <= out["TI_max"]["roi_max"]
    assert out["TI_max"]["normal_max"] == pytest.approx(out["TI_normal"]["roi_max"])
    assert out["TI_max"]["normal_mean"] == pytest.approx(out["TI_normal"]["roi_mean"])
    assert _mtimes([central, normal]) == before  # the dataset was only read
    assert _tree_state(head_model) == head_before  # nothing written through the symlink
