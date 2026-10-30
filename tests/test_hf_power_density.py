"""``hf_power_density``: time-averaged carrier power per volume, and the simulators that write it.

Pins (2026-10-26):
* ``tit.volume_fields.hf_power_density(fields, sigma)`` is the time average of ``E(t)^T sigma E(t)``
  for ``E(t) = sum_c E_c cos(2 pi f_c t + phi_c)`` at incommensurate carrier frequencies -- for a
  scalar conductivity and for a full (symmetric, anisotropic) tensor -- and, with ``coherent``,
  of one sinusoid of amplitude ``sum_c E_c``. Expected values come from that time signal sampled
  numerically here (an independent reader of the definition), not from the closed form.
* ``TISimulation`` / ``mTISimulation`` write it with the conductivity of the solve's own output
  mesh, cropped together with the mesh: an element dropped by the brain crop never shifts the
  conductivity onto its neighbour. The conductivity per element is fixed by hand below.

Reproduce: ``.venv/bin/python -m pytest tests/test_hf_power_density.py -q``.
Deliberately elsewhere: that ``_element_conductivity`` returns SimNIBS's solve conductivity needs
real SimNIBS (``tests/numerical``); ``hf_power`` itself is ``tests/test_calc.py``. The writers'
``hf_sar`` (``sum_c |E_c|^2``, unchanged on disk) is checked on the same runs.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit import constants as const
from tit.volume_fields import hf_power_density

# incommensurate carrier frequencies (Hz-free units): no common period
_FREQS = np.array([1.0, np.sqrt(2.0), (1 + np.sqrt(5.0)) / 2, np.sqrt(7.0)])


def _time_average(fields, sigma, coherent=False):
    """Mean over a long window of E(t)^T sigma E(t), sigma (N, 3, 3)."""
    E = np.stack(fields)  # (F, N, 3)
    t = np.linspace(0.0, 4000.0, 400_001)
    phases = np.array([0.3, 1.1, 2.0, 0.7])[: len(E)]
    w = np.cos(2 * np.pi * _FREQS[: len(E), None] * t + phases[:, None])  # (F, T)
    if coherent:
        w = np.broadcast_to(w[:1], w.shape)  # one frequency, in phase
    Et = np.einsum("ft,fnx->ntx", w, E)
    return np.einsum("ntx,nxy,nty->n", Et, sigma, Et) / len(t)


def _fields(n_fields, n_el=4, seed=0):
    rng = np.random.default_rng(seed)
    return [rng.normal(size=(n_el, 3)) for _ in range(n_fields)]


@pytest.mark.parametrize("n_fields", [1, 2, 4])
def test_scalar_conductivity_is_the_time_averaged_joule_heating(n_fields):
    fields = _fields(n_fields)
    sigma = np.array([0.275, 0.126, 1.654, 0.465])
    expected = _time_average(fields, sigma[:, None, None] * np.eye(3))
    np.testing.assert_allclose(hf_power_density(fields, sigma), expected, rtol=2e-3)


@pytest.mark.parametrize("n_fields", [2, 4])
def test_tensor_conductivity_uses_the_full_tensor(n_fields):
    fields = _fields(n_fields, seed=1)
    tensors = _spd_tensors()
    expected = _time_average(fields, tensors)
    got = hf_power_density(fields, tensors.reshape(4, 9))
    np.testing.assert_allclose(got, expected, rtol=2e-3)
    # an isotropic approximation (mean eigenvalue) would differ: the tensor matters here
    iso = hf_power_density(fields, np.trace(tensors, axis1=1, axis2=2) / 3)
    assert np.max(np.abs(iso - expected) / expected) > 0.05


def _spd_tensors(seed=2):
    A = np.random.default_rng(seed).normal(size=(4, 3, 3))
    return np.einsum("nij,nkj->nik", A, A) + 0.1 * np.eye(3)  # SPD, anisotropic


@pytest.mark.parametrize("kind", ["scalar", "tensor"])
def test_coherent_is_one_sinusoid_of_the_summed_field(kind):
    fields = _fields(2, seed=3)
    if kind == "scalar":
        sigma = np.full(4, 0.3)
        tensors = sigma[:, None, None] * np.eye(3)
    else:
        tensors = _spd_tensors()
        sigma = tensors.reshape(4, 9)
    expected = _time_average(fields, tensors, coherent=True)
    got = hf_power_density(fields, sigma, coherent=True)
    np.testing.assert_allclose(got, expected, rtol=2e-3)


# ── the simulators write it with the cropped conductivity ───────────────────────


class _Mesh:
    """The slice of ``simnibs.mesh_io.Msh`` the post-processing touches."""

    def __init__(self, tags, fields):
        self.elm = SimpleNamespace(tag1=np.asarray(tags))
        self.elmdata = [
            SimpleNamespace(field_name=k, value=np.asarray(v))
            for k, v in fields.items()
        ]

    @property
    def field(self):  # like Msh.field: derived from elmdata
        return {d.field_name: d for d in self.elmdata}

    def add_element_field(self, value, name):
        self.elmdata.append(SimpleNamespace(field_name=name, value=np.asarray(value)))

    def crop_mesh(self, tags):
        keep = np.isin(self.elm.tag1, tags)
        return _Mesh(
            self.elm.tag1[keep], {d.field_name: d.value[keep] for d in self.elmdata}
        )

    def view(self, **kwargs):
        return SimpleNamespace(write_opt=lambda path: None)


class _Written(Exception):
    pass


# GM, WM, an electrode rubber (100), GM, saline (500), a GM surface triangle (1002)
_TAGS = np.array([2, 1, 100, 2, 500, 1002])
_KEEP = np.isin(_TAGS, np.arange(1, 100)) | np.isin(_TAGS, np.arange(1001, 1100))
_SIGMA_FULL = np.array([0.275, 0.126, 29.4, 0.30, 1.0, 0.275])  # per element, by hand


def _run_post_process(sim_cls, n_carriers, carrier_only=False):
    rng = np.random.default_rng(7)
    carriers = [rng.normal(size=(len(_TAGS), 3)) for _ in range(n_carriers)]
    reads = iter(carriers)

    def read_msh(path):
        return _Mesh(_TAGS, {"E": next(reads)})

    def write_msh(mesh, path):
        if const.FIELD_HF_POWER_DENSITY in mesh.field:
            raise _Written(mesh)

    mesh_io = SimpleNamespace(read_msh=read_msh, write_msh=write_msh)
    pairs = [(f"E{2 * i}", f"E{2 * i + 1}") for i in range(n_carriers)]
    from tit.sim.config import Montage, SimulationConfig

    config = SimulationConfig(
        subject_id="001",
        montages=[
            Montage(
                name="m", mode=Montage.Mode.NET, electrode_pairs=pairs, eeg_net="x.csv"
            )
        ],
        intensities=[1.0] * n_carriers,
        output_fields=[const.FIELD_HF_SAR, const.FIELD_HF_POWER_DENSITY],
        carrier_only=carrier_only,
    )
    with (
        patch("tit.sim.base.get_path_manager"),
        patch("tit.sim.base.mesh_io", mesh_io),
        patch.object(sim_cls, "_element_conductivity", lambda self, m: _SIGMA_FULL),
    ):
        sim = sim_cls(config, config.montages[0], MagicMock())
        dirs = {k: "/fake" for k in ("hf_dir", "ti_mesh", "mti_mesh")}
        with pytest.raises(_Written) as written:
            sim._post_process(dirs)
    mout = written.value.args[0]
    kept = [c[_KEEP] for c in carriers]
    # hf_sar on disk is sum_c |E_c|^2 (= 2 * hf_power), coherent: |sum_c E_c|^2
    summed = [sum(kept)] if carrier_only else kept
    expected_sar = sum(np.sum(e * e, axis=1) for e in summed)
    np.testing.assert_allclose(
        mout.field[const.FIELD_HF_SAR].value, expected_sar, rtol=1e-12
    )
    return mout.field[const.FIELD_HF_POWER_DENSITY].value, kept


def test_ti_writes_power_density_with_the_cropped_conductivity():
    from tit.sim.TI import TISimulation

    got, kept = _run_post_process(TISimulation, 2)
    sigma = _SIGMA_FULL[_KEEP]
    expected = 0.5 * sigma * sum(np.sum(e * e, axis=1) for e in kept)
    np.testing.assert_allclose(got, expected, rtol=1e-12)


def test_ti_carrier_only_power_density_is_coherent():
    from tit.sim.TI import TISimulation

    got, kept = _run_post_process(TISimulation, 2, carrier_only=True)
    total = kept[0] + kept[1]
    expected = 0.5 * _SIGMA_FULL[_KEEP] * np.sum(total * total, axis=1)
    np.testing.assert_allclose(got, expected, rtol=1e-12)


def test_mti_writes_power_density_over_all_carriers():
    from tit.sim.mTI import mTISimulation

    got, kept = _run_post_process(mTISimulation, 4)
    expected = 0.5 * _SIGMA_FULL[_KEEP] * sum(np.sum(e * e, axis=1) for e in kept)
    np.testing.assert_allclose(got, expected, rtol=1e-12)
