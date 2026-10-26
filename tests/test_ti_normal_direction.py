"""``TI_normal`` is the envelope along each node's cortical-surface normal, for TI and mTI.

Pins (2026-10-26): ``TISimulation._calculate_ti_normal`` and ``mTISimulation._calculate_mti_normal``
evaluate the envelope along ``nodes_normals()`` of the first central-surface overlay -- not along
element normals, not along a fixed axis -- on both overlay layouts SimNIBS writes: a full ``E``
vector per node, and an ``E_normal`` scalar per node (the field is then ``E_normal * n``).

Where the expected numbers come from: written here from the definitions, not from ``tit.calc``.
Two channels: Grossman 2017's ``2 min(|E1.n|, |E2.n|)``. Two carriers (four channels): the
power-envelope form ``sqrt(2(P + |Q|)) - sqrt(2(P - |Q|))`` with ``P = (1/2) sum (a_k^2 + b_k^2)``
and ``Q = sum a_k b_k`` (``docs/wiki/analyzer.md``), algebraically distinct from the quotient the
code evaluates. The node normals are oblique and differ per node, so a fixed axis or another
normal set gives other numbers.

Reproduce: ``.venv/bin/python -m pytest tests/test_ti_normal_direction.py -q``.
Deliberately elsewhere: ``envelope`` itself (``tests/test_calc.py``) and its agreement with
SimNIBS ``get_dirTI`` (``tests/numerical/test_calc_vs_simnibs.py``).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_N_NODES = 5
_NORMALS = np.random.default_rng(11).normal(size=(_N_NODES, 3))
_NORMALS /= np.linalg.norm(_NORMALS, axis=1, keepdims=True)


class _Surface:
    """The slice of a SimNIBS central-surface ``Msh`` the normal path touches."""

    def __init__(self, fields):
        self.nodedata = [
            SimpleNamespace(field_name=k, value=np.asarray(v))
            for k, v in fields.items()
        ]

    @property
    def field(self):  # like Msh.field: derived from the data lists
        return {d.field_name: d for d in self.nodedata}

    def nodes_normals(self):
        return SimpleNamespace(value=_NORMALS.copy())

    def add_node_field(self, value, name):
        self.nodedata.append(SimpleNamespace(field_name=name, value=np.asarray(value)))

    def view(self, **kwargs):
        return SimpleNamespace(write_opt=lambda path: None)


def _channels(n, layout):
    """Per-channel overlay fields and the normal projections ``E_c . n`` they imply."""
    rng = np.random.default_rng(5)
    if layout == "E":
        E = [rng.normal(size=(_N_NODES, 3)) for _ in range(n)]
        return [{"E": e} for e in E], [np.sum(e * _NORMALS, axis=1) for e in E]
    proj = [rng.normal(size=_N_NODES) for _ in range(n)]
    return [{"E_normal": p} for p in proj], proj


def _written_ti_normal(sim_cls, n, layout):
    overlays, proj = _channels(n, layout)
    reads = iter(overlays)
    written = {}
    mesh_io = SimpleNamespace(
        read_msh=lambda path: _Surface(next(reads)),
        write_msh=lambda mesh, path: written.setdefault("mesh", mesh),
    )
    from tit.sim.config import Montage, SimulationConfig

    pairs = [(f"E{2 * i}", f"E{2 * i + 1}") for i in range(n)]
    config = SimulationConfig(
        subject_id="001",
        montages=[
            Montage(
                name="m", mode=Montage.Mode.NET, electrode_pairs=pairs, eeg_net="x.csv"
            )
        ],
        intensities=[1.0] * n,
    )
    module = __import__(sim_cls.__module__, fromlist=["mesh_io"])
    with (
        patch("tit.sim.base.get_path_manager"),
        patch.object(module, "mesh_io", mesh_io),
    ):
        sim = sim_cls(config, config.montages[0], MagicMock())
        if n == 2:
            sim._calculate_ti_normal("/hf", "/out", "m")
        else:
            sim._calculate_mti_normal("/hf", "/out", "m", n)
    return written["mesh"].field["TI_normal"].value, proj


@pytest.mark.parametrize("layout", ["E", "E_normal"])
def test_ti_normal_is_grossman_along_the_node_normals(layout):
    from tit.sim.TI import TISimulation

    got, (a, b) = _written_ti_normal(TISimulation, 2, layout)
    expected = 2 * np.minimum(np.abs(a), np.abs(b))
    assert np.all(expected > 1e-3)  # a non-degenerate fixture
    np.testing.assert_allclose(got, expected, rtol=1e-12)


@pytest.mark.parametrize("layout", ["E", "E_normal"])
def test_mti_normal_is_the_joint_envelope_along_the_node_normals(layout):
    from tit.sim.mTI import mTISimulation

    got, (a1, b1, a2, b2) = _written_ti_normal(mTISimulation, 4, layout)
    P = 0.5 * (a1**2 + b1**2 + a2**2 + b2**2)
    Q = np.abs(a1 * b1 + a2 * b2)
    expected = np.sqrt(2 * (P + Q)) - np.sqrt(2 * (P - Q))
    assert np.all(expected > 1e-3)
    np.testing.assert_allclose(got, expected, rtol=1e-10)
