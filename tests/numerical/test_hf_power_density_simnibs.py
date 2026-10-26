"""``hf_power_density`` with the solve's conductivity equals SimNIBS's own ``(1/2) J . E``.

Pins (2026-10-26): ``BaseSimulation._element_conductivity`` hands back the conductivity a SimNIBS
TDCS list builds for its mesh (``cond2elmdata``, triangles assigned from their tetrahedra as
``fem.calc_fields`` does), and ``tit.sim.base.hf_power_density`` applied to it equals
``(1/2) sum_c J_c . E_c`` with ``J_c`` from SimNIBS's ``fem.calc_J`` -- the current density
SimNIBS itself would write. Both for the default isotropic ("scalar") conductivities and for a
"dir" anisotropic model with a synthetic, strongly anisotropic DTI tensor volume, where the
power density must use the full tensor.

Where the expected numbers come from: SimNIBS ``fem.calc_J`` (an independent implementation of
``sigma E``) on SimNIBS's test mesh ``sphere3.msh``; the scalar conductivities are also checked
against SimNIBS ``standard_cond()`` by tissue tag. Random carrier fields, no FEM solve.

Reproduce in the image: ``simnibs_python -m pytest tests/numerical/test_hf_power_density_simnibs.py -q``
(the subprocess avoids the host conftest's SimNIBS mocks).
Deliberately elsewhere: the time-average definition and the writers' crop alignment
(``tests/test_hf_power_density.py``).
"""

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = r"""
import os
from types import SimpleNamespace
import numpy as np
import simnibs
from simnibs.mesh_tools import mesh_io
from simnibs.simulation import fem, sim_struct
from simnibs.utils.cond_utils import standard_cond
from tit.sim.base import BaseSimulation, hf_power_density

mesh = mesh_io.read_msh(os.path.join(os.path.dirname(simnibs.__file__),
                        "_internal_resources", "testing_files", "sphere3.msh"))
rng = np.random.default_rng(0)
E = [rng.normal(size=(mesh.elm.nr, 3)) for _ in range(2)]

def conductivity(tdcs):
    stub = SimpleNamespace(_session=SimpleNamespace(poslists=[tdcs]))
    return BaseSimulation._element_conductivity(stub, mesh)

def j_dot_e(cond_value):
    cond = mesh_io.ElementData(cond_value, mesh=mesh)
    return 0.5 * sum(
        np.sum(fem.calc_J(mesh_io.ElementData(e, mesh=mesh), cond) * e, axis=1) for e in E
    )

# isotropic
tdcs = sim_struct.TDCSLIST()
tdcs.anisotropy_type = "scalar"
sigma = conductivity(tdcs)
assert sigma.shape == (mesh.elm.nr,)
std = [c.value for c in standard_cond()]
tets = mesh.elm.elm_type == 4
assert np.array_equal(sigma[tets], np.array(std)[mesh.elm.tag1[tets] - 1])
assert np.all(sigma[~tets] > 0)  # triangles took their tetrahedron's value
np.testing.assert_allclose(hf_power_density(E, sigma), j_dot_e(sigma), rtol=1e-12)

# anisotropic: a uniform tensor with eigenvalues 0.1/0.1/1.0 S/m along a tilted axis
axis = np.array([1.0, 2.0, 2.0]) / 3.0
T = 0.1 * np.eye(3) + 0.9 * np.outer(axis, axis)
vol = np.broadcast_to(T[[0, 0, 0, 1, 1, 2], [0, 1, 2, 1, 2, 2]], (40, 40, 40, 6)).copy()
tdcs = sim_struct.TDCSLIST()
tdcs.anisotropy_type = "dir"
tdcs.anisotropic_tissues = list(np.unique(mesh.elm.tag1[tets]))
tdcs.anisotropy_vol = vol
tdcs.anisotropy_affine = np.array([[5.0, 0, 0, -100], [0, 5.0, 0, -100], [0, 0, 5.0, -100], [0, 0, 0, 1]])
sigma = conductivity(tdcs)
assert sigma.shape == (mesh.elm.nr, 9)
tensors = sigma.reshape(-1, 3, 3)
ev = np.linalg.eigvalsh(tensors[tets])
assert np.median(ev[:, 2] / ev[:, 0]) > 3  # really anisotropic
pd = hf_power_density(E, sigma)
np.testing.assert_allclose(pd, j_dot_e(sigma), rtol=1e-12)
iso = hf_power_density(E, np.trace(tensors, axis1=1, axis2=2) / 3)
assert np.median(np.abs(iso - pd) / pd) > 0.1  # the scalar shortcut would be wrong
"""


def test_power_density_matches_simnibs_current_density():
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
