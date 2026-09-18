"""The one scene an analysis writes (``tit/analyzer/scene.py``), on synthetic data.

Real numpy/nibabel (this directory's conftest swaps the host suite's mocks out):
the claims are the layer keys Tetravox reads, the window read off the ROI's own
values, the cursor on the ROI, and paths relative to the scene when the data is
inside the project.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("nibabel")
pytest.importorskip("scipy")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tit.analyzer import scene as analysis_scene  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402

AFFINE = np.array(
    [[1.0, 0, 0, -50.0], [0, 1.0, 0, -50.0], [0, 0, 1.0, -50.0], [0, 0, 0, 1.0]]
)


@pytest.fixture
def project(tmp_path):
    """A project with a subject T1 and an analysis folder, as the PathManager sees it."""
    import nibabel as nib

    get_path_manager(str(tmp_path))
    m2m = tmp_path / "derivatives" / "SimNIBS" / "sub-x" / "m2m_x"
    m2m.mkdir(parents=True)
    rng = np.random.default_rng(0)
    nib.save(
        nib.Nifti1Image(rng.uniform(0, 500, (100, 100, 100)).astype(np.float32), AFFINE),
        str(m2m / "T1.nii.gz"),
    )
    out = tmp_path / "derivatives" / "SimNIBS" / "sub-x" / "Simulations" / "s" / "Analyses"
    out = out / "Voxel" / "cortical_x"
    out.mkdir(parents=True)
    return m2m, out


def _scene(out: Path) -> dict:
    assert sorted(p.name for p in out.iterdir()) == [analysis_scene.SCENE_NAME]
    return json.loads((out / analysis_scene.SCENE_NAME).read_text())


def test_voxel_scene_is_the_t1_and_the_masked_overlay_windowed_on_the_roi(project):
    import nibabel as nib

    m2m, out = project
    mask = np.zeros((100, 100, 100), dtype=bool)
    mask[60:70, 60:70, 60:70] = True
    field = np.zeros(mask.shape, dtype=np.float32)
    field[mask] = np.linspace(0.05, 0.2, int(mask.sum()))
    overlay = out / "roi_overlay.nii.gz"
    nib.save(nib.Nifti1Image(field, AFFINE), str(overlay))

    written = analysis_scene.write_voxel_scene(
        out_dir=str(out),
        anatomy=str(m2m / "T1.nii.gz"),
        overlay=str(overlay),
        roi_mask=mask,
        affine=AFFINE,
        roi_values=field[mask],
        field_name="TI_max",
        region_name="lh.box",
        meta={"roi": "lh.box", "space": "voxel"},
    )
    assert written == str(out / analysis_scene.SCENE_NAME)
    overlay.unlink()  # the listing below is the scene alone
    scene = _scene(out)

    # Two datasets, both relative to the scene file (they are inside the project).
    assert [d["kind"] for d in scene["datasets"]] == ["volume", "volume"]
    assert scene["datasets"][0]["path"] == "../../../../../m2m_x/T1.nii.gz"
    assert scene["datasets"][1]["path"] == "roi_overlay.nii.gz"

    t1, field_layer = scene["layers"]
    assert (t1["kind"], t1["colormap"], t1["showColorbar"]) == ("volume", "gray", False)
    assert field_layer["datasetId"] == "ds1"
    assert field_layer["colormap"] == "inferno"
    assert field_layer["opacity"] == 0.85
    assert field_layer["showColorbar"] is True
    # The window is read off the ROI's own values: [floor, p99.9], not [0, max].
    hi = float(np.percentile(field[mask], 99.9))
    assert field_layer["scale"] == {"kind": "linear", "lo": pytest.approx(0.2 * hi, abs=1e-6), "hi": pytest.approx(hi, abs=1e-6)}
    # Hide the zeros outside the ROI; never `clamp`, which paints a black wash.
    assert field_layer["threshold"] == {
        "lo": analysis_scene.ZERO_EPSILON,
        "hi": None,
        "symmetric": False,
        "mode": "hide",
        "softEdge": 0.0,
    }
    # No surface, no .annot: the field is what this scene shows.
    assert all(layer["kind"] == "volume" for layer in scene["layers"])

    # Cursor on the ROI: voxels 60..69 at -50 mm origin -> centre 14.5 mm.
    assert scene["cursor"] == pytest.approx([14.5, 14.5, 14.5], abs=1.0)
    assert scene["layout"]["kind"] == "2x2"
    assert scene["meta"]["field"] == {
        "name": "TI_max",
        "unit": "V/m",
        "max_in_roi": pytest.approx(0.2, abs=1e-6),
        "scale": [field_layer["scale"]["lo"], field_layer["scale"]["hi"]],
    }
    assert scene["meta"]["unit"] == "voxels"
    assert scene["meta"]["voxels"] == 1000


def test_mesh_scene_is_the_overlay_twice_translucent_then_field_in_roi(project):
    m2m, out = project
    out = out.parent.parent / "Mesh" / "cortical_x"
    out.mkdir(parents=True)
    mesh = out / "roi_overlay.msh"
    mesh.write_bytes(b"$MeshFormat\n")
    (out / "roi_overlay.msh.opt").write_text("// opt\n")
    rng = np.random.default_rng(1)
    nodes = rng.uniform(-70, 70, (500, 3))
    roi = np.zeros(500, dtype=bool)
    roi[:50] = True
    nodes[:50] = rng.uniform(20, 30, (50, 3))
    values = np.zeros(500)
    values[:50] = np.linspace(0.04, 0.13, 50)

    analysis_scene.write_mesh_scene(
        out_dir=str(out),
        mesh=str(mesh),
        roi_coords=nodes[roi],
        node_coords=nodes,
        roi_values=values[roi],
        field_name="TI_max",
        region_name="lh.box",
        meta={"roi": "lh.box", "space": "mesh"},
        normal_max=0.11,
    )
    mesh.unlink()
    (out / "roi_overlay.msh.opt").unlink()
    scene = _scene(out)

    # One dataset: the overlay the analysis wrote, with its .opt beside it.
    assert scene["datasets"] == [
        {
            "id": "ds0",
            "kind": "mesh",
            "name": "roi_overlay.msh",
            "path": "roi_overlay.msh",
            "fingerprint": "",
            "sidecars": {"opt": {"path": "roi_overlay.msh.opt"}},
        }
    ]
    cortex, field_layer, normal = scene["layers"]
    assert all(layer["datasetId"] == "ds0" and layer["kind"] == "mesh" for layer in scene["layers"])
    # (i) the whole cortex, translucent and not pickable
    assert (cortex["colorMode"], cortex["opacity"], cortex["pickable"]) == ("solid", 0.25, False)
    assert cortex["name"] == "roi_overlay.msh"
    # (ii) the field at the ROI's nodes, zeros hidden, bar from 0 to the ROI max
    assert field_layer["name"] == "TI_max_ROI"
    assert field_layer["colorMode"] == "field"
    assert field_layer["field"] == {"source": "node", "name": "TI_max_ROI", "component": "mag"}
    assert field_layer["colormap"] == "inferno"
    assert field_layer["scale"] == {"kind": "linear", "lo": 0.0, "hi": pytest.approx(0.13)}
    assert field_layer["threshold"]["mode"] == "hide"
    assert field_layer["threshold"]["lo"] == analysis_scene.ZERO_EPSILON
    # Finite, above every value: an open `hi` makes Tetravox 0.5.2 hide the whole mesh layer.
    assert field_layer["threshold"]["hi"] == pytest.approx(0.26)
    assert field_layer["showColorbar"] is True
    assert field_layer["contoursIn2D"] is True
    assert field_layer["faceMode"] == "both"
    # (iii) the normal component, there but hidden
    assert normal["name"] == "TI_normal_ROI"
    assert normal["visible"] is False
    assert normal["field"]["name"] == "TI_normal_ROI"
    assert normal["scale"]["hi"] == pytest.approx(0.11)

    assert scene["transparency"] == {"mode": "peel"}
    assert scene["layout"] == {"kind": "1+3", "cells": ["view3d", "axial", "coronal", "sagittal"]}
    # Cursor on the ROI's nodes (all within 20..30 mm), camera fitted to every node.
    assert all(20.0 <= v <= 30.0 for v in scene["cursor"])
    assert scene["view3d"]["camera"]["target"] == scene["cursor"]
    assert scene["view3d"]["camera"]["distance"] > 100.0
    assert scene["meta"]["unit"] == "vertices"
    assert scene["meta"]["voxels"] == 50


def test_mesh_scene_without_a_normal_has_two_layers(project, tmp_path):
    _, out = project
    mesh = out / "roi_overlay.msh"
    mesh.write_bytes(b"")
    analysis_scene.write_mesh_scene(
        out_dir=str(out),
        mesh=str(mesh),
        roi_coords=np.full((10, 3), 5.0),
        node_coords=np.array([[-50.0, -50.0, -50.0], [50.0, 50.0, 50.0]]),
        roi_values=np.linspace(0.1, 0.2, 10),
        field_name="hf_peak",
        region_name="r",
        meta={},
    )
    scene = json.loads((out / analysis_scene.SCENE_NAME).read_text())
    assert [layer["name"] for layer in scene["layers"]] == ["roi_overlay.msh", "hf_peak_ROI"]
    assert "sidecars" not in scene["datasets"][0]


def test_an_empty_roi_or_a_failure_is_a_log_line_not_an_exception(project, caplog):
    m2m, out = project
    assert (
        analysis_scene.write_voxel_scene(
            out_dir=str(out),
            anatomy=str(m2m / "T1.nii.gz"),
            overlay=str(out / "missing.nii.gz"),
            roi_mask=np.zeros((100, 100, 100), dtype=bool),
            affine=AFFINE,
            roi_values=np.array([]),
            field_name="TI_max",
            region_name="r",
            meta={},
        )
        is None
    )
    assert (
        analysis_scene.write_mesh_scene(
            out_dir=str(out),
            mesh=str(out / "roi_overlay.msh"),
            roi_coords="not coordinates",
            node_coords=None,
            roi_values=None,
            field_name="TI_max",
            region_name="r",
            meta={},
        )
        is None
    )
    assert list(out.iterdir()) == []


def test_the_scene_can_be_switched_off(project, monkeypatch):
    m2m, out = project
    monkeypatch.setenv("TIT_NO_ROI_PLATE", "1")
    assert (
        analysis_scene.write_mesh_scene(
            out_dir=str(out),
            mesh=str(out / "roi_overlay.msh"),
            roi_coords=np.ones((3, 3)),
            node_coords=np.ones((3, 3)),
            roi_values=np.ones(3),
            field_name="TI_max",
            region_name="r",
            meta={},
        )
        is None
    )
    assert list(out.iterdir()) == []
