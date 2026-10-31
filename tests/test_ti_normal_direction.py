"""The central surface carries every volume field and ``TI_normal`` along each node's normal.

Pins (2026-10-30, docs/dev/DECISIONS.md "one central surface mesh per run"):
:func:`tit.volume_fields.central_surface`, which the simulator and the on-demand producer call,
interpolates the volume fields and the channel fields in one stacked call per hemisphere, keeps
them apart again by column (each volume field under its own name, each channel's ``E`` as its
own vector), joins the hemispheres lh then rh, and evaluates ``TI_normal`` -- the envelope along
``nodes_normals()`` of the joined surface, not along element normals or a fixed axis -- for TI
(two channels) and mTI (all N channels); without channel fields (a carrier-only run) there is no
``TI_normal``.

Where the expected numbers come from: written here from the definitions, not from ``tit.calc``.
Two channels: Grossman 2017's ``2 min(|E1.n|, |E2.n|)``. Two carriers (four channels): the
power-envelope form ``sqrt(2(P + |Q|)) - sqrt(2(P - |Q|))`` with ``P = (1/2) sum (a_k^2 + b_k^2)``
and ``Q = sum a_k b_k`` (``docs/wiki/analyzer.md``), algebraically distinct from the quotient the
code evaluates. The node normals are oblique and differ per node, so a fixed axis or another
normal set gives other numbers. SimNIBS is replaced by a fake whose "interpolation" hands node i
the stacked row i, so the bookkeeping is what is checked; the interpolation itself is SimNIBS's,
pinned against its own msh2cortex by tests/numerical/test_central_surface_real.py.

Reproduce: ``.venv/bin/python -m pytest tests/test_ti_normal_direction.py -q``.
Deliberately elsewhere: ``envelope`` itself (``tests/test_calc.py``) and its agreement with
SimNIBS ``get_dirTI`` (``tests/numerical/test_calc_vs_simnibs.py``).
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tit import volume_fields

_LH, _RH = 3, 4  # nodes per hemisphere; the volume has one element per surface node
_RNG = np.random.default_rng(11)
_NORMALS = _RNG.normal(size=(_LH + _RH, 3))
_NORMALS /= np.linalg.norm(_NORMALS, axis=1, keepdims=True)
_TAGS = SimpleNamespace(
    WM=1, GM=2, CSF=3, LH_CENTRAL_SURFACE=1101, RH_CENTRAL_SURFACE=1102
)


class _Data:
    def __init__(self, value, name):
        self.value, self.field_name = np.asarray(value), name
        self.nr_comp = 1 if self.value.ndim == 1 else self.value.shape[1]

    def interpolate_to_surface(self, surface, th_indices=None):
        return SimpleNamespace(value=self.value[surface.rows])


class _Volume:
    def __init__(self, data):
        self.nodes, self.elm = "nodes", SimpleNamespace(
            get_tags=lambda tag, return_element_numbers: np.arange(1, _LH + _RH + 1)
        )
        self.elmdata = [_Data(v, k) for k, v in data.items()]
        self.field = {d.field_name: d for d in self.elmdata}

    def add_element_field(self, value, name):
        self.elmdata.append(_Data(value, name))
        self.field = {d.field_name: d for d in self.elmdata}

    def crop_mesh(self, tags):
        assert sorted(tags) == [1, 2, 3]  # WM, GM and CSF, as msh2cortex crops
        return self


class _Surface:
    def __init__(self, rows):
        self.rows = rows
        self.nodes = SimpleNamespace(nr=len(rows))
        self.elm = SimpleNamespace(nr=1, tag1=None, tag2=None)
        self.nodedata, self.elmdata = [], []

    @property
    def field(self):
        return {d.field_name: d for d in self.nodedata}

    def join_mesh(self, other):
        assert self.elm.tag1[0] == 1101 and other.elm.tag1[0] == 1102
        return _Surface(np.concatenate([self.rows, other.rows]))

    def nodes_normals(self):
        return SimpleNamespace(value=_NORMALS[self.rows])

    def add_node_field(self, value, name):
        self.nodedata.append(_Data(value, name))


def _surface(channels: int | None, fields=("TI_max", "hf_peak")):
    """``central_surface`` on a fake volume; the channel normal projections ``E_c . n``."""
    n = _LH + _RH
    volume = _Volume({f: _RNG.normal(size=n) for f in fields})
    e_fields = (
        None
        if channels is None
        else [_RNG.normal(size=(n, 3)) for _ in range(channels)]
    )
    mesh_io = SimpleNamespace(
        Msh=lambda nodes, elm: _Volume({}),
        load_subject_surfaces=lambda subject, name: {
            "lh": _Surface(np.arange(_LH)),
            "rh": _Surface(np.arange(_LH, n)),
        },
    )
    with (
        patch.object(sys.modules["simnibs"], "mesh_io", mesh_io),
        patch.object(sys.modules["simnibs.mesh_tools.mesh_io"], "ElementTags", _TAGS),
        patch.object(sys.modules["simnibs.utils.file_finder"], "SubjectFiles"),
    ):
        got = volume_fields.central_surface(volume, "/m2m", e_fields=e_fields)
    proj = [np.sum(e * _NORMALS, axis=1) for e in e_fields or ()]
    return got, volume, proj


def test_each_volume_field_keeps_its_name_and_values_lh_then_rh():
    got, volume, _ = _surface(2)
    assert [d.field_name for d in got.nodedata] == ["TI_max", "hf_peak", "TI_normal"]
    for name in ("TI_max", "hf_peak"):
        np.testing.assert_array_equal(got.field[name].value, volume.field[name].value)


def test_ti_normal_is_grossman_along_the_node_normals():
    got, _, (a, b) = _surface(2)
    expected = 2 * np.minimum(np.abs(a), np.abs(b))
    assert np.all(expected > 1e-3)  # a non-degenerate fixture
    np.testing.assert_allclose(got.field["TI_normal"].value, expected, rtol=1e-12)


def test_mti_normal_is_the_joint_envelope_along_the_node_normals():
    got, _, (a1, b1, a2, b2) = _surface(4)
    P = 0.5 * (a1**2 + b1**2 + a2**2 + b2**2)
    Q = np.abs(a1 * b1 + a2 * b2)
    expected = np.sqrt(2 * (P + Q)) - np.sqrt(2 * (P - Q))
    assert np.all(expected > 1e-3)
    np.testing.assert_allclose(got.field["TI_normal"].value, expected, rtol=1e-10)


def test_without_channel_fields_there_is_no_ti_normal():
    got, _, _ = _surface(None, fields=("hf_peak", "hf_rms"))
    assert [d.field_name for d in got.nodedata] == ["hf_peak", "hf_rms"]


def test_one_field_alone_goes_in_as_a_scalar():
    """An old run's mesh with TI_max only: SimNIBS's interpolation breaks on an (N, 1) block."""
    stacked = []
    original = _Volume.add_element_field

    def record(self, value, name):
        stacked.append(np.asarray(value).ndim)
        original(self, value, name)

    with patch.object(_Volume, "add_element_field", record):
        got, volume, _ = _surface(None, fields=("TI_max",))
    assert stacked == [1]
    np.testing.assert_array_equal(
        got.field["TI_max"].value, volume.field["TI_max"].value
    )


def test_a_vector_volume_field_is_refused():
    volume = _Volume({"TI_max": np.zeros((_LH + _RH, 3))})
    with pytest.raises(ValueError, match="a volume field is a scalar"):
        volume_fields.central_surface(volume, "/m2m")


def test_a_field_outside_the_registry_is_not_carried_onto_the_surface():
    """An old run's retired field on its volume mesh never reaches a rebuilt surface."""
    got, _, _ = _surface(2, fields=("TI_max", "retired_field"))
    assert [d.field_name for d in got.nodedata] == ["TI_max", "TI_normal"]
