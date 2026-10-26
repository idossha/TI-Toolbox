"""Flex ``dir_TI_tangential`` is the maximum TI envelope within the surface plane.

Pins (2026-10-26): ``postprocess_e(..., type="dir_TI_tangential")`` in the integration flex runs
(``resources/map-electrodes/tes_flex_optimization.py``, loaded by ``tit.opt.flex.runtime``)
returns ``max`` over unit ``n`` perpendicular to the surface normal of Grossman 2017's
``||(E1+E2).n| - |(E1-E2).n||``. The earlier ``sqrt(max_TI^2 - dir_TI^2)`` treated two envelope
maxima as orthogonal vector components; on these random fields it is off by more than 10 % at
about a third of the elements, so this test also asserts it is *not* what the branch returns.

Where the expected numbers come from: a dense sweep of 7200 in-plane angles over [0, pi) plus a
4001-point local refinement around each element's best angle (the maximum may sit on a cusp,
``|a| = |b|``, where grid error is first order), evaluating Grossman's expression directly --
no ``tit.calc`` code. Tolerance: the sweep may undershoot by its refinement step (measured
<1e-7 relative); it must never exceed the patched value.

Reproduce in the image (SimNIBS is real only there; the subprocess avoids the host mocks):
``simnibs_python -m pytest tests/numerical/test_flex_tangential.py -q``.
Deliberately elsewhere: ``envelope_max(perpendicular_to=)`` itself for K >= 2 (``tests/test_calc.py``).
"""

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = r"""
from pathlib import Path
import numpy as np
from simnibs.utils.TI_utils import get_dirTI, get_maxTI
from tit.opt.flex.runtime import integration_module

module = integration_module()
assert Path(module.__file__).resolve() == Path("resources/map-electrodes/tes_flex_optimization.py").resolve()

rng = np.random.default_rng(42)
N = 1000
e1 = rng.normal(size=(N, 3))
e2 = rng.normal(size=(N, 3)) * rng.uniform(0.2, 2.0, size=(N, 1))
nrm = rng.normal(size=(N, 3))
nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
got = module.postprocess_e(e1, e2=e2, dirvec=nrm, type="dir_TI_tangential")

ref_ax = np.where(np.abs(nrm[:, :1]) > 0.9, [[0.0, 1.0, 0.0]], [[1.0, 0.0, 0.0]])
u = np.cross(nrm, ref_ax)
u /= np.linalg.norm(u, axis=1, keepdims=True)
v = np.cross(nrm, u)

def sweep(angles, sl):
    d = np.cos(angles)[..., None] * u[sl, None, :] + np.sin(angles)[..., None] * v[sl, None, :]
    s = np.abs(np.einsum("nx,npx->np", e1[sl] + e2[sl], d))
    t = np.abs(np.einsum("nx,npx->np", e1[sl] - e2[sl], d))
    return np.abs(s - t)

phi = np.linspace(0.0, np.pi, 7200, endpoint=False)
best = np.zeros(N)
for lo in range(0, N, 250):
    sl = slice(lo, lo + 250)
    f = sweep(phi[None, :], sl)
    fine = phi[f.argmax(axis=1)][:, None] + np.linspace(-np.pi / 7200, np.pi / 7200, 4001)
    best[sl] = np.maximum(f.max(axis=1), sweep(fine, sl).max(axis=1))

rel = (got - best) / best
assert rel.min() > -1e-9, rel.min()   # never below an in-plane value
assert rel.max() < 1e-6, rel.max()    # and attained in the plane

old = np.sqrt(np.maximum(0, get_maxTI(e1, e2) ** 2 - get_dirTI(e1, e2, nrm) ** 2))
assert np.mean(np.abs(old - best) / best > 0.10) > 0.2

z = module.postprocess_e(np.zeros((3, 3)), e2=np.zeros((3, 3)), dirvec=nrm[:3], type="dir_TI_tangential")
assert np.array_equal(z, np.zeros(3))
"""


def test_dir_ti_tangential_is_the_in_plane_envelope_maximum():
    root = Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True, text=True
    )
    if probe.returncode:
        pytest.skip(
            "real SimNIBS unavailable; run this test with simnibs_python in the image"
        )
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], cwd=root, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
