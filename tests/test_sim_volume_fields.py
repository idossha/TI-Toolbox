"""What the simulators write on the volume mesh: each selected field from its ``tit.calc`` function.

Pins (2026-10-26) the wiring of ``TISimulation._post_process`` and ``mTISimulation._post_process``
on fake carrier meshes (SimNIBS is mocked on the host): the channel fields are cropped to
``BRAIN_TISSUE_TAG_RANGES`` before anything is computed; the volume mesh carries exactly the
selected fields, in registry order, under their on-disk names (``mTI_max`` for mTI); each value is
the ``tit.calc`` function for that quantity over ALL channel fields in channel order
(``envelope_max``, ``envelope_mean``, ``hf_peak``, ``2 * hf_power`` for ``hf_sar``,
``sigma * hf_power`` for ``hf_power_density``); a carrier-only TI run adds the carriers
coherently; mTI writes one ``TI_vectors`` mesh per adjacent channel pair, the K=1 envelope
maximum times its direction; and, before field extraction, TI writes ``<montage>_normal.msh`` and
mTI ``<montage>_mTI_normal.msh`` holding ``TI_normal`` over every channel's central-surface field,
while a carrier-only run writes no ``TI_normal`` at all.

Where the expected numbers come from: the carrier metrics by hand (``sum_c |E_c|^2``,
``|E1 + E2|``) and ``TI_normal`` by hand (``| |S n| - |D n| |`` over the channel pairs' sums
and differences projected on the normal); the volume envelopes from ``tit.calc`` on the hand-cropped fields, because what is pinned
here is which function runs on which fields -- the functions themselves are ``tests/test_calc.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_sim_volume_fields.py -q``.
"""

from __future__ import annotations

import contextlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import tit.sim.base
import tit.sim.mTI
import tit.sim.TI
from tit import constants as const
from tit.calc import envelope_max, envelope_mean, hf_peak

# GM, WM, an electrode rubber (100), CSF, saline (500), a GM surface triangle, a skin triangle
_TAGS = np.array([2, 1, 100, 3, 500, 1002, 1005])
_KEEP = np.isin(_TAGS, np.arange(1, 100)) | np.isin(_TAGS, np.arange(1001, 1100))
_SIGMA = np.array([0.275, 0.126, 29.4, 1.654, 1.0, 0.275, 0.465])


class _Mesh:
    """The slice of ``simnibs.mesh_io.Msh`` the post-processing touches."""

    def __init__(self, tags, fields):
        self.elm = SimpleNamespace(tag1=np.asarray(tags))
        self.elmdata = [
            SimpleNamespace(field_name=k, value=np.asarray(v))
            for k, v in fields.items()
        ]

    @property
    def field(self):
        return {d.field_name: d for d in self.elmdata}

    def add_element_field(self, value, name):
        self.elmdata.append(SimpleNamespace(field_name=name, value=np.asarray(value)))

    def crop_mesh(self, tags):
        keep = np.isin(self.elm.tag1, tags)
        return _Mesh(
            self.elm.tag1[keep], {d.field_name: d.value[keep] for d in self.elmdata}
        )

    def view(self, **kwargs):
        self.viewed = kwargs
        return SimpleNamespace(write_opt=lambda path: None)


class _Surface:
    """The slice of a SimNIBS central-surface overlay ``_write_ti_normal`` touches."""

    def __init__(self, e, normals):
        self.field = {"E": SimpleNamespace(value=e)}
        self.normals = normals
        self.nodedata = []

    def nodes_normals(self):
        return SimpleNamespace(value=self.normals)

    def add_node_field(self, value, name):
        self.nodedata.append(SimpleNamespace(field_name=name, value=np.asarray(value)))

    def view(self, **kwargs):
        return SimpleNamespace(write_opt=lambda path: None)


class _VolumeWritten(Exception):
    pass


_N_NODES = 9


def _post_process(
    sim_cls, n_channels, output_fields, carrier_only=False, through_normal=False
):
    """Run ``_post_process`` until the volume mesh is written; return every mesh written.

    With *through_normal*, run on until field extraction instead, past the ``TI_normal`` write,
    and also return each channel's central-surface field and the surface normals.
    """
    rng = np.random.default_rng(3)
    carriers = [rng.normal(size=(len(_TAGS), 3)) for _ in range(n_channels)]
    surface_e = [rng.normal(size=(_N_NODES, 3)) for _ in range(n_channels)]
    normals = rng.normal(size=(_N_NODES, 3))
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    reads = iter(carriers)
    surface_reads = iter(surface_e)
    written = {}

    def write_msh(mesh, path):
        written[os.path.basename(path)] = mesh
        if not through_normal and path.endswith(("m_TI.msh", "m_mTI.msh")):
            raise _VolumeWritten

    def read_msh(path):
        if path.endswith("_central.msh"):
            return _Surface(next(surface_reads), normals)
        return _Mesh(_TAGS, {"E": next(reads)})

    mesh_io = SimpleNamespace(read_msh=read_msh, write_msh=write_msh)
    from tit.sim.config import Montage, SimulationConfig

    pairs = [(f"E{2 * i}", f"E{2 * i + 1}") for i in range(n_channels)]
    config = SimulationConfig(
        subject_id="001",
        montages=[
            Montage(
                name="m", mode=Montage.Mode.NET, electrode_pairs=pairs, eeg_net="x.csv"
            )
        ],
        intensities=[1.0] * n_channels,
        output_fields=list(output_fields),
        carrier_only=carrier_only,
    )
    with contextlib.ExitStack() as stack:
        for module in (tit.sim.base, tit.sim.TI, tit.sim.mTI):
            if hasattr(module, "mesh_io"):
                stack.enter_context(patch.object(module, "mesh_io", mesh_io))
        stack.enter_context(patch("tit.sim.base.get_path_manager"))
        stack.enter_context(
            patch.object(sim_cls, "_element_conductivity", lambda self, m: _SIGMA)
        )
        if through_normal:
            stack.enter_context(
                patch.object(
                    sys.modules[sim_cls.__module__],
                    "extract_fields",
                    side_effect=_VolumeWritten,
                )
            )
        sim = sim_cls(config, config.montages[0], MagicMock())
        dirs = {k: "/fake" for k in ("hf_dir", "ti_mesh", "mti_mesh")}
        with pytest.raises(_VolumeWritten):
            sim._post_process(dirs)
    if through_normal:
        return written, surface_e, normals
    return written, [c[_KEEP] for c in carriers]


def _fields(mesh):
    return {d.field_name: d.value for d in mesh.elmdata}


def _power(fields):
    return sum(np.sum(e * e, axis=1) for e in fields)


def test_ti_writes_each_selected_field_from_its_calc_function():
    written, kept = _post_process(
        tit.sim.TI.TISimulation, 2, const.SELECTABLE_OUTPUT_FIELDS
    )
    got = _fields(written["m_TI.msh"])
    assert list(got) == list(const.SELECTABLE_OUTPUT_FIELDS)
    np.testing.assert_allclose(got["TI_max"], envelope_max(kept), rtol=1e-12)
    np.testing.assert_allclose(got["TI_avg"], envelope_mean(kept), rtol=1e-12)
    e1, e2 = kept
    by_hand_peak = np.maximum(
        np.linalg.norm(e1 + e2, axis=1), np.linalg.norm(e1 - e2, axis=1)
    )
    np.testing.assert_allclose(got["hf_peak"], by_hand_peak, rtol=1e-12)
    np.testing.assert_allclose(got["hf_sar"], _power(kept), rtol=1e-12)
    np.testing.assert_allclose(
        got["hf_power_density"], 0.5 * _SIGMA[_KEEP] * _power(kept), rtol=1e-12
    )


def test_ti_writes_only_the_selected_fields():
    written, _ = _post_process(
        tit.sim.TI.TISimulation, 2, [const.FIELD_HF_PEAK, const.FIELD_TI_MAX]
    )
    assert list(_fields(written["m_TI.msh"])) == [
        const.FIELD_TI_MAX,
        const.FIELD_HF_PEAK,
    ]


def test_ti_carrier_only_adds_the_carriers_coherently():
    written, (e1, e2) = _post_process(
        tit.sim.TI.TISimulation, 2, const.CARRIER_OUTPUT_FIELDS, carrier_only=True
    )
    got = _fields(written["m_TI.msh"])
    total = e1 + e2
    assert list(got) == list(const.CARRIER_OUTPUT_FIELDS)
    np.testing.assert_allclose(
        got["hf_peak"], np.linalg.norm(total, axis=1), rtol=1e-12
    )
    np.testing.assert_allclose(got["hf_sar"], _power([total]), rtol=1e-12)
    np.testing.assert_allclose(
        got["hf_power_density"], 0.5 * _SIGMA[_KEEP] * _power([total]), rtol=1e-12
    )


@pytest.mark.parametrize("n_channels", [4, 6])
def test_mti_writes_each_selected_field_over_all_channels(n_channels):
    written, kept = _post_process(
        tit.sim.mTI.mTISimulation, n_channels, const.SELECTABLE_OUTPUT_FIELDS
    )
    got = _fields(written["m_mTI.msh"])
    assert list(got) == [const.FIELD_MTI_MAX, *const.SELECTABLE_OUTPUT_FIELDS[1:]]
    np.testing.assert_allclose(got["mTI_max"], envelope_max(kept), rtol=1e-12)
    np.testing.assert_allclose(got["TI_avg"], envelope_mean(kept), rtol=1e-12)
    np.testing.assert_allclose(got["hf_peak"], hf_peak(kept), rtol=1e-12)
    np.testing.assert_allclose(got["hf_sar"], _power(kept), rtol=1e-12)
    np.testing.assert_allclose(
        got["hf_power_density"], 0.5 * _SIGMA[_KEEP] * _power(kept), rtol=1e-12
    )


def test_mti_writes_one_ti_vectors_mesh_per_adjacent_channel_pair():
    written, kept = _post_process(tit.sim.mTI.mTISimulation, 4, [const.FIELD_TI_MAX])
    assert sorted(written) == ["m_TI_AB.msh", "m_TI_CD.msh", "m_mTI.msh"]
    for name, (a, b) in (("m_TI_AB.msh", kept[:2]), ("m_TI_CD.msh", kept[2:])):
        vectors = _fields(written[name])["TI_vectors"]
        amp, direction = envelope_max([a, b], return_direction=True)
        np.testing.assert_allclose(vectors, amp[:, None] * direction, rtol=1e-12)


def _ti_normal_by_hand(fields, normals):
    """``| |S n| - |D n| |`` with S, D the channel pairs' sums and differences along n."""
    p = [np.sum(e * normals, axis=1) for e in fields]
    s = np.sqrt(sum((p[k] + p[k + 1]) ** 2 for k in range(0, len(p), 2)))
    d = np.sqrt(sum((p[k] - p[k + 1]) ** 2 for k in range(0, len(p), 2)))
    return np.abs(s - d)


@pytest.mark.parametrize(
    "sim_cls, n_channels, name",
    [
        (tit.sim.TI.TISimulation, 2, "m_normal.msh"),
        (tit.sim.mTI.mTISimulation, 4, "m_mTI_normal.msh"),
    ],
)
def test_ti_normal_is_the_envelope_of_every_channel_along_the_normal(
    sim_cls, n_channels, name
):
    written, surface_e, normals = _post_process(
        sim_cls, n_channels, [const.FIELD_TI_MAX], through_normal=True
    )
    assert name in written
    (ti_normal,) = written[name].nodedata
    assert ti_normal.field_name == const.FIELD_TI_NORMAL
    np.testing.assert_allclose(
        ti_normal.value, _ti_normal_by_hand(surface_e, normals), rtol=1e-12
    )


def test_ti_carrier_only_writes_no_ti_normal():
    written, _, _ = _post_process(
        tit.sim.TI.TISimulation,
        2,
        const.CARRIER_OUTPUT_FIELDS,
        carrier_only=True,
        through_normal=True,
    )
    assert "m_TI.msh" in written
    assert not any(name.endswith("_normal.msh") for name in written)


@pytest.mark.parametrize("shift", range(4))
def test_without_ti_max_the_view_opens_on_the_first_selected_field(shift):
    """Each rotation of the selection opens on its own first field, whatever the set order."""
    fields = [
        const.FIELD_TI_AVG,
        const.FIELD_HF_PEAK,
        const.FIELD_HF_SAR,
        const.FIELD_HF_POWER_DENSITY,
    ]
    selection = fields[shift:] + fields[:shift]
    written, _, _ = _post_process(
        tit.sim.TI.TISimulation, 2, selection, through_normal=True
    )
    assert written["m_TI.msh"].viewed["visible_fields"] == selection[0]
