"""What the simulators write on the volume mesh: each selected field from its ``tit.calc`` function.

Pins (2026-10-26) the wiring of ``TISimulation._post_process`` and ``mTISimulation._post_process``
on fake carrier meshes (SimNIBS is mocked on the host): the channel fields are cropped to
``BRAIN_TISSUE_TAG_RANGES`` before anything is computed; the volume mesh carries exactly the
selected fields, in registry order, under their on-disk names (``mTI_max`` for mTI); each value is
the ``tit.calc`` function for that quantity over ALL channel fields in channel order
(``envelope_max``, ``envelope_mean``, ``hf_peak``, ``sqrt(hf_power)`` for ``hf_rms``,
``sigma * hf_power`` for ``hf_power_density``); a carrier-only TI run adds the carriers
coherently; mTI writes its volume mesh and nothing per channel pair; no Gmsh ``.opt`` view is
written; and the central surface (``tit.volume_fields.central_surface``) is made from the volume
mesh just written and every brain-cropped channel field in channel order -- none for a
carrier-only run, which has no ``TI_normal``.

Where the expected numbers come from: the carrier metrics by hand (``sum_c |E_c|^2``,
``|E1 + E2|``); the volume envelopes from ``tit.calc`` on the hand-cropped fields, because what is
pinned here is which function runs on which fields -- the functions themselves are
``tests/test_calc.py``, and the surface's numbers tests/numerical/test_central_surface_real.py.

Reproduce: ``.venv/bin/python -m pytest tests/test_sim_volume_fields.py -q``.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import tempfile
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


class _VolumeWritten(Exception):
    pass


def _post_process(
    sim_cls, n_channels, output_fields, carrier_only=False, through_surface=False
):
    """Run ``_post_process`` until the central surface is made, right after the volume mesh is
    written; return every mesh written, by file name.

    With *through_surface*, also return what ``central_surface`` was given:
    ``(volume mesh, e_fields)``.
    """
    rng = np.random.default_rng(3)
    carriers = [rng.normal(size=(len(_TAGS), 3)) for _ in range(n_channels)]
    reads = iter(carriers)
    meshes = []
    surface_calls = []
    out_dir = tempfile.mkdtemp()

    def write_msh(mesh, path):
        # A real file holding the mesh's index: the simulator moves what it writes into place,
        # so what was written is read back from the directory under its final name.
        with open(path, "w") as f:
            f.write(str(len(meshes)))
        meshes.append(mesh)

    def read_msh(path):
        return _Mesh(_TAGS, {"E": next(reads)})

    def central_surface(volume, m2m, *, e_fields=None):
        surface_calls.append((volume, e_fields))
        raise _VolumeWritten

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
        stack.enter_context(
            patch.object(tit.sim.base, "central_surface", central_surface)
        )
        sim = sim_cls(config, config.montages[0], MagicMock())
        dirs = {
            k: out_dir
            for k in ("hf_dir", "ti_mesh", "mti_mesh", "ti_surfaces", "mti_surfaces")
        }
        with pytest.raises(_VolumeWritten):
            sim._post_process(dirs)
    written = {}
    for name in os.listdir(out_dir):
        with open(os.path.join(out_dir, name)) as f:
            written[name] = meshes[int(f.read())]
    shutil.rmtree(out_dir)
    kept = [c[_KEEP] for c in carriers]
    if through_surface:
        return written, kept, surface_calls
    return written, kept


def _fields(mesh):
    return {d.field_name: d.value for d in mesh.elmdata}


def _power(fields):
    """``sum_c |E_c|^2``: twice the time-averaged mean square of the carriers."""
    return sum(np.sum(e * e, axis=1) for e in fields)


def _rms(fields):
    """RMS over time of carriers at distinct frequencies: ``sqrt(sum_c |E_c|^2 / 2)``."""
    return np.sqrt(0.5 * _power(fields))


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
    np.testing.assert_allclose(got["hf_rms"], _rms(kept), rtol=1e-12)
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
    np.testing.assert_allclose(got["hf_rms"], _rms([total]), rtol=1e-12)
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
    np.testing.assert_allclose(got["hf_rms"], _rms(kept), rtol=1e-12)
    np.testing.assert_allclose(
        got["hf_power_density"], 0.5 * _SIGMA[_KEEP] * _power(kept), rtol=1e-12
    )


@pytest.mark.parametrize(
    "sim_cls, n_channels, volume",
    [
        (tit.sim.TI.TISimulation, 2, "m_TI.msh"),
        (tit.sim.mTI.mTISimulation, 4, "m_mTI.msh"),
    ],
)
def test_the_surface_is_made_from_the_volume_mesh_and_every_channel_field(
    sim_cls, n_channels, volume
):
    written, kept, calls = _post_process(
        sim_cls, n_channels, [const.FIELD_TI_MAX], through_surface=True
    )
    # The volume mesh is the only mesh written before the surface: no per-pair TI_AB/TI_CD
    # meshes, no TI_normal mesh, no grey/white copies.
    assert sorted(written) == [volume]
    ((given, e_fields),) = calls
    assert given is written[volume]
    assert len(e_fields) == n_channels
    for got, want in zip(e_fields, kept):
        np.testing.assert_array_equal(got, want)


def test_a_carrier_only_surface_gets_no_channel_fields():
    written, _, calls = _post_process(
        tit.sim.TI.TISimulation,
        2,
        const.CARRIER_OUTPUT_FIELDS,
        carrier_only=True,
        through_surface=True,
    )
    assert sorted(written) == ["m_TI.msh"]
    assert calls[0][1] is None  # no envelope, so no TI_normal


def test_no_gmsh_view_is_written():
    written, _ = _post_process(tit.sim.TI.TISimulation, 2, [const.FIELD_HF_PEAK])
    assert not hasattr(written["m_TI.msh"], "viewed")


class _Killed(Exception):
    pass


def test_a_failed_volume_write_leaves_no_result_mesh_and_no_partial(tmp_path):
    """The volume mesh is the "result exists" marker (``refuse_existing_result``), so a write
    killed half-way must leave nothing under its name: it is written aside and moved in.
    """
    from tit.sim.config import Montage, SimulationConfig

    def write_msh(mesh, path):
        with open(path, "wb") as f:
            f.write(b"$MeshFormat\n")  # truncated, then the run dies
        raise _Killed

    config = SimulationConfig(
        subject_id="001",
        montages=[
            Montage(
                name="m",
                mode=Montage.Mode.NET,
                electrode_pairs=[("E0", "E1"), ("E2", "E3")],
                eeg_net="x.csv",
            )
        ],
        intensities=[1.0, 1.0],
    )
    rng = np.random.default_rng(3)
    meshes = [_Mesh(_TAGS, {"E": rng.normal(size=(len(_TAGS), 3))}) for _ in "ab"]
    final = tmp_path / "m_TI.msh"
    with (
        patch("tit.sim.base.get_path_manager"),
        patch.object(tit.sim.base, "mesh_io", SimpleNamespace(write_msh=write_msh)),
    ):
        sim = tit.sim.TI.TISimulation(config, config.montages[0], MagicMock())
        with pytest.raises(_Killed):
            sim._write_volume_mesh(meshes, const.FIELD_TI_MAX, str(final))
    assert not final.exists()
    assert list(tmp_path.iterdir()) == [], "the half-written .partial is removed too"
