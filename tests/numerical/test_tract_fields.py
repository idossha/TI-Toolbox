"""tit.tract field sampling and the directional TI envelope, against independent references.

Pins (2026-11-04):

* **V3, directional envelope along per-point tangents.** ``tit.calc.envelope(fields, t)``
  with one tangent per point equals (a) the numpy closed form
  ``||(E1+E2).t| - |(E1-E2).t||`` written out here and (b) the peak-to-trough of the Hilbert
  envelope (``scipy.signal.hilbert``) of the time signal
  ``(E1.t) cos(2 pi f1 tau) + (E2.t) cos(2 pi f2 tau)`` over whole beats; and it never
  exceeds ``envelope_max``. (SimNIBS ``get_dirTI`` with one direction per point is already
  pinned in ``test_calc_vs_simnibs.py``.)
* **V2, mesh sampling (synthetic SimNIBS mesh).** On a tetrahedral cube mesh built with
  SimNIBS ``mesh_io`` (Kuhn subdivision, 6 tets per 2 mm cell), ``sample_carriers("tet")`` at
  element barycentres returns exactly the element values written to the ``.msh``; a point
  outside is flagged and gets 0; for a uniform field both ``"tet"`` and ``"linear"`` return
  the field; for a linear field the two differ by at most |grad E| x the cell diagonal, and
  ``"linear"`` is closer to the exact field than the element value.
* **V2, real carrier mesh (gated on ``TIT_DATASET_000``, read-only).** On sub-101
  ``L_Insula``'s two carrier meshes, 300 straight 40 mm streamlines centred on random WM
  element barycentres: ``"tet"`` and ``"linear"`` find the same points outside the brain
  tissues, and their ``ti_along`` agrees in distribution (correlation > 0.8, median
  difference < 10 % of the local ``ti_max``): properties, not pinned numbers (the measured
  values are printed).

SimNIBS runs in a child interpreter, as in ``test_calc_vs_simnibs.py``: ``tests/conftest.py``
mocks it in-process. Reproduce (image)::

    docker run --rm --platform linux/amd64 --entrypoint simnibs_python -v "$PWD":/ti-toolbox \\
      -w /ti-toolbox idossha/ti-toolbox:v3.1.3 -m pytest tests/numerical/test_tract_fields.py -q

Deliberately elsewhere: the per-point metric algebra (host, ``tests/test_tract_geometry.py``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import numpy as np
import pytest


def _fields(n=500, seed=11):
    rng = np.random.default_rng(seed)
    E1, E2 = rng.normal(size=(n, 3)), 0.7 * rng.normal(size=(n, 3))
    t = rng.normal(size=(n, 3))
    return E1, E2, t / np.linalg.norm(t, axis=1, keepdims=True)


def test_v3_envelope_along_tangent_matches_closed_form():
    from tit.calc import envelope, envelope_max

    E1, E2, t = _fields()
    got = envelope([E1, E2], t)
    closed = np.abs(
        np.abs(np.einsum("nk,nk->n", E1 + E2, t))
        - np.abs(np.einsum("nk,nk->n", E1 - E2, t))
    )
    np.testing.assert_allclose(got, closed, rtol=1e-10, atol=1e-12)
    assert np.all(got <= envelope_max([E1, E2]) + 1e-12)


def test_v3_envelope_matches_hilbert_time_domain():
    from scipy.signal import hilbert

    from tit.calc import envelope

    E1, E2, t = _fields(n=20, seed=5)
    a, b = np.einsum("nk,nk->n", E1, t), np.einsum("nk,nk->n", E2, t)
    f1, f2, fs = 1000.0, 1010.0, 200_000.0  # 10 Hz beat
    tau = np.arange(0, 0.5, 1 / fs)  # 5 beats
    core = slice(int(0.1 * fs), int(0.4 * fs))  # whole beats, away from the edges
    got = envelope([E1, E2], t)
    for i in range(len(a)):
        sig = a[i] * np.cos(2 * np.pi * f1 * tau) + b[i] * np.cos(2 * np.pi * f2 * tau)
        env = np.abs(hilbert(sig))[core]
        # tolerance: the Hilbert transform's edge ripple, relative to the carrier amplitude
        assert env.max() - env.min() == pytest.approx(
            got[i], abs=2e-3 * (abs(a[i]) + abs(b[i]))
        )


def _child(code: str, *args: str) -> str:
    """Run *code* in a fresh interpreter (real SimNIBS); fail with its output if it fails."""
    pytest.importorskip("dipy", reason="skipping: needs the image (SimNIBS, DIPY)")
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.getcwd()},
    )
    if proc.returncode == 3:
        pytest.skip(proc.stdout.strip().splitlines()[-1])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


_CUBE = """
import sys
import numpy as np
from simnibs.mesh_tools import mesh_io
from tit.tract.fields import sample_carriers

def cube_mesh(n=6, size=12.0):
    g = np.linspace(0.0, size, n + 1)
    nodes = np.stack(np.meshgrid(g, g, g, indexing="ij"), -1).reshape(-1, 3)
    idx = np.arange((n + 1) ** 3).reshape(n + 1, n + 1, n + 1)
    tets = []
    for i, j, k in np.ndindex(n, n, n):
        c = [idx[i + a, j + b, k + d] for a in (0, 1) for b in (0, 1) for d in (0, 1)]
        # Kuhn: one tet per monotone corner path v0 -> one axis -> two axes -> v7
        for p in ((1, 3), (1, 5), (2, 3), (2, 6), (4, 5), (4, 6)):
            tets.append([c[0], c[p[0]], c[p[1]], c[7]])
    mesh = mesh_io.Msh(nodes=mesh_io.Nodes(nodes),
                       elements=mesh_io.Elements(tetrahedra=np.array(tets) + 1))
    mesh.elm.tag1[:] = 1
    mesh.elm.tag2[:] = 1
    mesh.fix_th_node_ordering()
    return mesh

def write(mesh, values, path):
    m = mesh_io.Msh(nodes=mesh.nodes, elements=mesh.elm)
    m.add_element_field(values, "E")
    mesh_io.write_msh(m, path)
    return path

tmp = sys.argv[1]
mesh = cube_mesh()
bary = mesh.elements_baricenters().value
rng = np.random.default_rng(2)
"""


def test_v2_tet_sampling_returns_element_values(tmp_path):
    _child(
        _CUBE + """
values = rng.normal(size=(mesh.elm.nr, 3))
path = write(mesh, values, tmp + "/toy_TDCS_1_scalar.msh")
(got,), outside = sample_carriers([path], bary, "tet")
assert not outside.any()
np.testing.assert_allclose(got, values, rtol=1e-12)
(got,), outside = sample_carriers([path], np.array([[50.0, 50.0, 50.0]]), "tet")
assert outside.all() and np.all(got == 0)
print("ok", mesh.elm.nr)
""",
        str(tmp_path),
    )


def test_v2_uniform_and_linear_fields(tmp_path):
    out = _child(
        _CUBE + """
pts = rng.uniform(1.0, 11.0, size=(300, 3))
e0 = np.array([0.3, -0.2, 0.1])
uni = write(mesh, np.tile(e0, (mesh.elm.nr, 1)), tmp + "/u_TDCS_1_scalar.msh")
for method in ("tet", "linear"):
    (got,), outside = sample_carriers([uni], pts, method)
    assert not outside.any()
    np.testing.assert_allclose(got, np.tile(e0, (len(pts), 1)), rtol=1e-9)
grad = np.array([[0.02, 0.0, 0.01], [0.0, -0.03, 0.0], [0.01, 0.0, 0.02]])
lin = write(mesh, bary @ grad.T, tmp + "/l_TDCS_1_scalar.msh")
(tet,), _ = sample_carriers([lin], pts, "tet")
(smooth,), _ = sample_carriers([lin], pts, "linear")
bound = np.linalg.norm(grad, 2) * 2.0 * np.sqrt(3.0)  # 2 mm cell diagonal bounds a tet
diff = np.linalg.norm(tet - smooth, axis=1)
assert diff.max() <= bound, (diff.max(), bound)
exact = pts @ grad.T
err_lin = np.median(np.linalg.norm(smooth - exact, axis=1))
err_tet = np.median(np.linalg.norm(tet - exact, axis=1))
assert err_lin < err_tet, (err_lin, err_tet)
print("median error linear", err_lin, "tet", err_tet)
""",
        str(tmp_path),
    )
    print(out)


def test_v2_real_mesh_tet_vs_linear():
    out = _child("""
import os, sys
import numpy as np
root = os.environ.get("TIT_DATASET_000", "")
mesh_dir = os.path.join(root, "derivatives/SimNIBS/sub-101/Simulations/L_Insula/high_Frequency/mesh")
if not root or not os.path.isdir(mesh_dir):
    print("skipping: TIT_DATASET_000 is unset or has no sub-101 L_Insula carrier meshes "
          "(export TIT_DATASET_000=/path/to/Dataset000, read-only)")
    sys.exit(3)
from simnibs.mesh_tools import mesh_io
from tit.paths import get_path_manager
from tit.tract import geometry
from tit.tract.fields import carrier_meshes, sample_carriers
pm = get_path_manager(root)
paths = carrier_meshes(pm, "101", "L_Insula")
# 300 straight 40 mm streamlines centred on random WM barycentres, random directions
wm = mesh_io.read_msh(str(paths[0])).crop_mesh(tags=[1])
rng = np.random.default_rng(0)
centres = wm.elements_baricenters().value[rng.choice(wm.elm.nr, 300, replace=False)]
dirs = rng.normal(size=(300, 3))
dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
sl = [c + np.outer(np.linspace(-20, 20, 41), d) for c, d in zip(centres, dirs)]
del wm
pts, off, h = geometry.resample(sl, 1.0)
t = geometry.tangents(pts, off, h)
tet, out_t = sample_carriers(paths, pts, "tet")
lin, out_l = sample_carriers(paths, pts, "linear")
ok = ~(out_t | out_l)
assert out_t.sum() == out_l.sum(), (out_t.sum(), out_l.sum())  # one search, two readings
assert ok.mean() > 0.8, ok.mean()  # straight lines leave the brain; those points drop
mt = geometry.point_metrics([f[ok] for f in tet], t[ok], np.array([0, ok.sum()]), np.ones(1))
ml = geometry.point_metrics([f[ok] for f in lin], t[ok], np.array([0, ok.sum()]), np.ones(1))
rel = np.abs(mt["ti_along"] - ml["ti_along"]) / np.maximum(ml["ti_max"], 1e-9)
r = np.corrcoef(mt["ti_along"], ml["ti_along"])[0, 1]
print(f"V2 real mesh: {ok.sum()} points, median |dTI_along|/TI_max {np.median(rel):.4f}, "
      f"p95 {np.percentile(rel, 95):.4f}, r {r:.4f}")
assert np.isfinite(r) and r > 0.8
assert np.median(rel) < 0.1
""")
    print(out)
