"""Tract visuals against the real libraries: TRX reading, endpoint patches, the figure.

What this pins (2026-11-04)
    - :func:`tit.blender.tract_data.load_trx` (standard library) reads a TRX exactly as
      trx-python -- the reference implementation, an independent reader -- does, for a file
      written by ``dev/tract_synthetic.write_trx`` and for one written by trx-python itself.
    - :func:`tit.blender.tract_publication.endpoint_patches` (SciPy KD-tree) equals a brute-force
      distance search.
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


def test_endpoint_patches_match_a_brute_force_search():
    pytest.importorskip("scipy.spatial")
    from tit.blender import tract_data as td
    from tit.blender.tract_publication import endpoint_patches

    rng = np.random.default_rng(5)
    lines = _lines(rng, 40)
    points = np.concatenate(lines)
    offsets = np.r_[0, np.cumsum([len(l) for l in lines])]
    tracts = td.Tracts(points, offsets, {}, {})
    surface = rng.uniform(points.min(0), points.max(0), (500, 3))
    start, end, gain = rng.uniform(20, 90, 40), rng.uniform(20, 90, 40), rng.random(40)
    frame, lit = endpoint_patches(surface, tracts, start, end, gain, radius=3.0)

    ends = np.concatenate([points[offsets[:-1]], points[offsets[1:] - 1]])
    when, strength = np.r_[start, end], np.r_[gain, gain]
    dist = np.linalg.norm(surface[:, None] - ends[None], axis=2)
    near = dist <= 3.0
    expect_frame = np.where(near.any(1), np.where(near, when, np.inf).min(1), 1e6)
    expect_lit = np.where(near, strength * (1 - dist / 3.0) ** 2, 0.0).max(1)
    assert near.any(1).sum() > 20  # the case has vertices to check
    np.testing.assert_allclose(frame, expect_frame, rtol=1e-6)
    np.testing.assert_allclose(lit, expect_lit, rtol=1e-6)


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
