"""tit.tract recovers a planted world fibre direction through every voxel frame (image).

Pins (2026-11-04), on synthetic volumes built here, for an LPS, a PSR (ernie's tensor grid)
and an oblique anisotropic affine, with an oblique planted direction
``d = (0.48, -0.6, 0.64)``:

* ``tensor_peaks`` of a stored (SimNIBS-frame) tensor ``l1 d d^T + l2 (I - d d^T)`` returns
  ``+/- d`` and its FA (closed form for two equal minor eigenvalues);
* the tensor route's EuDX tracking (``eudx_on_tensor``) runs every streamline along
  ``+/- d`` in world (|cos| > 0.995: EuDX snaps to repulsion724 vertices), and a flipped voxel
  axis does not (the frame check is sensitive);
* the csd route (``fit_csd`` on DWI simulated in world coordinates as
  ``S0 exp(-b g^T D g)``, then ``track_sh``) also runs along ``+/- d``.

Expected values are the planted direction and the FA formula; DIPY is the tracker. SimNIBS
and DIPY run in a child interpreter (``tests/conftest.py`` mocks them in-process). Reproduce::

    docker run --rm --platform linux/amd64 --entrypoint simnibs_python -v "$PWD":/ti-toolbox \\
      -w /ti-toolbox idossha/ti-toolbox:v3.1.3 -m pytest tests/numerical/test_tract_frames.py -q

Deliberately elsewhere: the world -> voxel direction algebra alone (host,
``tests/test_tract_geometry.py``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

_SETUP = """
import numpy as np
from tit.pre.qsi import tensor_math as tm
from tit.tract import tracking as tr
from tit.tract.config import TrackConfig

d = np.array([0.48, -0.6, 0.64])
l1, l2 = 1.7e-3, 0.3e-3
D = l1 * np.outer(d, d) + l2 * (np.eye(3) - np.outer(d, d))
rot = np.linalg.qr(np.random.default_rng(5).normal(size=(3, 3)))[0]
lin = {
    "LPS": np.diag([-1.0, -1.0, 1.0]),
    "PSR": np.array([[0, 0, 1.0], [-1.0, 0, 0], [0, 1.0, 0]]),
    "oblique": rot @ np.diag([1.0, 1.25, 1.5]),
}
def affine(m):
    a = np.eye(4); a[:3, :3] = m; a[:3, 3] = [10.0, -20.0, 5.0]; return a
def directions(sl):
    v = np.array([s[-1] - s[0] for s in sl if len(s) > 4])
    return np.abs(v @ d) / np.linalg.norm(v, axis=1)
cfg = TrackConfig(n_seeds=300, step_mm=0.5, min_length_mm=5.0, max_length_mm=250.0,
                  fa_threshold=0.2, max_angle=30.0)
"""


def _child(code: str) -> str:
    pytest.importorskip("dipy", reason="skipping: needs the image (SimNIBS, DIPY)")
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_SETUP + code)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.getcwd()},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def test_tensor_route_tracks_along_the_planted_direction():
    out = _child("""
shape = (30, 30, 30)
evals = np.array([l1, l2, l2])
fa_exact = np.sqrt(0.5) * np.sqrt(2 * (l1 - l2) ** 2) / np.sqrt(np.sum(evals ** 2))
for name, m in lin.items():
    A = affine(m)
    t6 = np.broadcast_to(tm.world_to_simnibs(D, A), shape + (6,)).astype(np.float32)
    mask = np.ones(shape, bool)
    e1, fa = tr.tensor_peaks(t6, A, mask)
    assert np.allclose(np.abs(e1 @ d), 1.0, atol=1e-5), name
    assert np.allclose(fa, fa_exact, rtol=1e-4), (name, fa[0], fa_exact)
    sl, _, _ = tr.eudx_on_tensor(t6, A, mask, cfg, 1, n_seeds=300, return_all=True)
    cos = directions(sl)
    # EuDX snaps to repulsion724 vertices (~5 deg apart): |cos| >= cos(5.7 deg) = 0.995
    assert len(cos) > 50 and cos.min() > 0.995, (name, len(cos), cos.min())
    sl_f, _, _ = tr.eudx_on_tensor(t6, A, mask, cfg, 1, n_seeds=300, flip=(-1, 1, 1),
                                   return_all=True)
    assert np.median(directions(sl_f)) < 0.99, name  # a flipped voxel axis is visible
    print(name, len(cos), round(float(cos.min()), 5))
""")
    print(out)


def test_csd_route_tracks_along_the_planted_direction():
    out = _child("""
rng = np.random.default_rng(1)
g = rng.normal(size=(60, 3)); g /= np.linalg.norm(g, axis=1, keepdims=True)
bvecs = np.vstack([np.zeros((6, 3)), g]); bvals = np.r_[np.zeros(6), np.full(60, 3000.0)]
signal = 1000.0 * np.exp(-bvals * np.einsum("ni,ij,nj->n", bvecs, D, bvecs))
shape = (24, 24, 24)
data = np.broadcast_to(signal, shape + (66,)).astype(np.float32)
wm = np.ones(shape, bool); none = np.zeros(shape, bool)
for name, m in lin.items():
    A = affine(m)
    shm, info = tr.fit_csd(data, A, bvals, bvecs, wm, wm, sh_order=8, n_jobs=1)
    sl, _ = tr.track_sh(shm, wm, none, none, A, wm, cfg, n_seeds=300, n_jobs=1,
                        return_all=True)
    cos = directions(sl)
    assert len(cos) > 50 and np.median(cos) > 0.995, (name, len(cos), np.median(cos))
    print(name, len(cos), round(float(np.median(cos)), 5))
""")
    print(out)
