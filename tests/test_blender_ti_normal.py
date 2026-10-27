"""Blender's ``TI_normal`` arrows are the simulation's ``TI_normal``: the envelope along the normal.

Pins (2026-10-26): ``vector_field_exporter._compute_ti_normal`` gives each central-surface
triangle the arrow ``E_AM(n) * n``, ``n`` the triangle's unit normal and ``E_AM(n)`` the envelope
of every channel field along ``n`` -- not the projection of the ``TI`` (``TI_max``) vector onto
``n``. The two differ because the envelope is not linear in the fields: with ``E1 = x``,
``E2 = y`` and ``n = x`` the ``TI`` vector projects to 1, but ``E2`` has no normal component to
beat with, so ``TI_normal`` is 0 (``docs/wiki/analyzer.md``).

Where the expected numbers come from: written here from the definitions, not from ``tit.calc``.
Two channels: Grossman 2017's ``2 min(|E1.n|, |E2.n|)``. Four channels: the power-envelope form
``sqrt(2(P + |Q|)) - sqrt(2(P - |Q|))`` with ``P = (1/2) sum (a_k^2 + b_k^2)`` and
``Q = sum a_k b_k``. The triangle normals are oblique and differ per face.

Reproduce: ``.venv/bin/python -m pytest tests/test_blender_ti_normal.py -q``.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from tit.blender.vector_field_exporter import _compute_ti_normal

pytestmark = pytest.mark.unit

_NODES = np.array(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 1.0],
        [0.0, 1.0, 0.0],
        [1.0, 0.0, 2.0],
        [0.0, 0.0, 1.0],
    ]
)
# 1-based node numbers, as SimNIBS stores them
_TRIANGLES = np.array([[1, 2, 3], [1, 4, 5], [1, 4, 6]])
_NORMALS = np.array(
    [[0.0, -1.0, 1.0] / np.sqrt(2), [2.0, 0.0, -1.0] / np.sqrt(5), [1.0, 0.0, 0.0]]
)
_SURFACE = SimpleNamespace(
    nodes=SimpleNamespace(node_coord=_NODES),
    elm=SimpleNamespace(node_number_list=_TRIANGLES, elm_type=np.full(3, 2)),
)
_ON = SimpleNamespace(export_ti_normal=True)


def _arrows(channels):
    return _compute_ti_normal(_ON, _SURFACE, None, channels)


def test_two_channels_are_grossman_along_each_face_normal():
    rng = np.random.default_rng(2)
    e1, e2 = rng.normal(size=(2, 3, 3))
    a, b = np.sum(e1 * _NORMALS, axis=1), np.sum(e2 * _NORMALS, axis=1)
    expected = 2 * np.minimum(np.abs(a), np.abs(b))
    assert np.all(expected > 1e-3)
    np.testing.assert_allclose(_arrows([e1, e2]), expected[:, None] * _NORMALS)


def test_four_channels_are_the_joint_envelope_along_each_face_normal():
    rng = np.random.default_rng(4)
    fields = list(rng.normal(size=(4, 3, 3)))
    a1, b1, a2, b2 = (np.sum(e * _NORMALS, axis=1) for e in fields)
    P = 0.5 * (a1**2 + b1**2 + a2**2 + b2**2)
    Q = np.abs(a1 * b1 + a2 * b2)
    expected = np.sqrt(2 * (P + Q)) - np.sqrt(2 * (P - Q))
    assert np.all(expected > 1e-3)
    np.testing.assert_allclose(
        _arrows(fields), expected[:, None] * _NORMALS, rtol=1e-10
    )


def test_it_is_not_the_projection_of_the_ti_vector():
    e1 = np.tile([1.0, 0.0, 0.0], (3, 1))
    e2 = np.tile([0.0, 1.0, 0.0], (3, 1))
    # face 3's normal is x: the TI vector (along (1, 1, 0)) projects to 1 there
    np.testing.assert_allclose(_arrows([e1, e2])[2], [0.0, 0.0, 0.0], atol=1e-12)


def test_off_by_default():
    assert (
        _compute_ti_normal(SimpleNamespace(export_ti_normal=False), _SURFACE, None, [])
        is None
    )
