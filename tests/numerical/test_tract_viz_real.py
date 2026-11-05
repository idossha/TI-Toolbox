"""Tract visuals against the real libraries: TRX reading, endpoint patches, the figure.

What this pins (2026-11-04)
    - :func:`tit.blender.tract_data.load_trx` (standard library) reads a TRX exactly as
      trx-python -- the reference implementation, an independent reader -- does, for a file
      written by ``dev/tract_synthetic.write_trx`` and for one written by trx-python itself.
    - :func:`tit.blender.tract_publication.region_geometry` takes cortical regions vertex for
      vertex from a FreeSurfer annotation and wraps subcortical labels found through the label
      volume's LUT (nibabel writes the inputs, so the expectations are the written arrays).
    - :func:`tit.plotting.tract_connectome.plot_connectome` writes a readable PNG.

Run in the image: simnibs_python -m pytest tests/numerical/test_tract_viz_real.py -q
(skips with a reason where trx-python or matplotlib is absent).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _synthetic():
    spec = importlib.util.spec_from_file_location(
        "tract_synthetic", ROOT / "dev" / "tract_synthetic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lines(rng, n=7):
    return [
        np.cumsum(rng.normal(0, 1, (int(rng.integers(2, 30)), 3)), 0) for _ in range(n)
    ]


def test_load_trx_reads_what_the_spec_writer_wrote(tmp_path):
    pytest.importorskip("trx", reason="trx-python is installed in the image only")
    from tit.blender import tract_data as td

    rng = np.random.default_rng(4)
    lines = _lines(rng)
    points = np.concatenate(lines).astype(np.float32)
    offsets = np.r_[0, np.cumsum([len(l) for l in lines])]
    dpv = {"ti_along": rng.random(len(points)), "ti_max": 1 + rng.random(len(points))}
    dps = {
        "edge_id": np.arange(len(lines), dtype=np.int32) - 1,
        "length_mm": rng.random(len(lines)),
    }
    _synthetic().write_trx(str(tmp_path / "a.trx"), points, offsets, dpv, dps)
    from trx import trx_file_memmap

    reference = trx_file_memmap.load(str(tmp_path / "a.trx"))
    trx_file_memmap.save(reference, str(tmp_path / "b.trx"))  # trx-python's own writer
    for name in ("a.trx", "b.trx"):
        got = td.load_trx(str(tmp_path / name))
        sl = reference.streamlines
        np.testing.assert_array_equal(got.points, np.asarray(sl._data))
        np.testing.assert_array_equal(
            got.offsets[:-1], np.asarray(sl._offsets)[: len(lines)]
        )
        np.testing.assert_array_equal(np.diff(got.offsets), np.asarray(sl._lengths))
        for key in dpv:
            np.testing.assert_array_equal(
                got.dpv[key], np.asarray(reference.data_per_vertex[key]._data)[:, 0]
            )
        for key in dps:
            np.testing.assert_array_equal(
                got.dps[key], np.asarray(reference.data_per_streamline[key])[:, 0]
            )
    np.testing.assert_array_equal(got.points, points)
    reference.close()


def test_region_geometry_reads_annotation_vertices_and_voxel_surfaces(tmp_path):
    """Cortical names come from the annot (vertex for vertex), subcortical ones from the LUT."""
    nib = pytest.importorskip("nibabel")
    pytest.importorskip("skimage")
    from tit.blender.tract_publication import region_geometry

    seg = tmp_path / "segmentation"
    seg.mkdir()
    labels = np.array([0, 1, 1, 2, 1, 0], dtype=np.int32)
    ctab = np.array([[0, 0, 0, 0, 0], [255, 0, 0, 0, 1], [0, 255, 0, 0, 2]], dtype=np.int32)
    names = [b"unknown", b"insula", b"precentral"]
    for hemi in ("lh", "rh"):
        nib.freesurfer.write_annot(str(seg / f"{hemi}.X_DK40.annot"), labels, ctab, names)
    data = np.zeros((12, 12, 12), np.int16)
    data[3:8, 4:9, 2:7] = 10
    affine = np.diag([2.0, 2.0, 2.0, 1.0])
    affine[:3, 3] = [-5.0, 3.0, 1.0]
    volume = tmp_path / "labeling.nii"
    nib.save(nib.Nifti1Image(data, affine), str(volume))
    (tmp_path / "labeling_LUT.txt").write_text("0 Unknown 0 0 0 0\n10 Left-Thalamus-Proper 0 118 14 0\n")
    glass = np.zeros((12, 3))
    cortical, deep = region_geometry(
        str(tmp_path), str(volume), ["lh.insula", "rh.precentral", "Left-Thalamus-Proper"], glass, 6
    )
    np.testing.assert_array_equal(cortical["lh.insula"], [1, 2, 4])
    np.testing.assert_array_equal(cortical["rh.precentral"], [9])  # rh vertices follow lh's 6
    verts, faces = deep["Left-Thalamus-Proper"]
    world = (np.argwhere(data == 10) @ affine[:3, :3].T) + affine[:3, 3]
    # the surface wraps the label's voxel centres: inside their box grown by one voxel
    assert (verts >= world.min(0) - 2.0 - 1e-6).all() and (verts <= world.max(0) + 2.0 + 1e-6).all()
    assert len(faces) > 20


def test_connectome_figure_is_written(tmp_path):
    pytest.importorskip("matplotlib", reason="matplotlib is real in the image leg")
    import matplotlib.image as mpimg

    from tit.plotting.tract_connectome import plot_connectome

    labels = [f"{h}.r{i}" for h in ("rh", "lh") for i in range(6)]
    m = np.random.default_rng(0).random((12, 12)) * 0.3
    m = np.triu(m, 1) + np.triu(m, 1).T
    np.savez(
        tmp_path / "connectome_ti_along_max.npz", matrix=m, labels=np.array(labels)
    )
    out = plot_connectome(
        str(tmp_path / "connectome_ti_along_max.npz"),
        str(tmp_path / "c.png"),
        title="t",
    )
    image = mpimg.imread(out)
    assert image.shape[0] > 800 and image.shape[1] > 1600
