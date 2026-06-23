"""Tests for the microscale (field -> neuron) coupling module.

Covers the NEURON-free core: config validation, unit conversion, and
quasipotential math.  NEURON and SimNIBS are mocked at the conftest level, so
these exercise pure NumPy logic with real arrays.
"""

import numpy as np
import pytest

from tit.microscale.config import (
    DEFAULT_CARRIERS,
    MicroscaleConfig,
    NeuronModelSpec,
)
from tit.microscale.field_sampler import (
    mm_to_um,
    path_quasipotential,
    uniform_quasipotential,
    um_to_mm,
)


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------


def test_mm_um_roundtrip():
    coords = np.array([[1.0, -2.5, 3.0], [0.0, 0.1, 100.0]])
    assert np.allclose(um_to_mm(mm_to_um(coords)), coords)
    assert np.allclose(mm_to_um(np.array([1.0, 0.0, 0.0])), [1000.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# Uniform quasipotential
# ---------------------------------------------------------------------------


def test_uniform_quasipotential_soma_is_zero():
    e = np.array([1.0, 0.0, 0.0])
    soma_um = np.array([0.0, 0.0, 0.0])
    segs_um = np.array([[0.0, 0.0, 0.0], [1000.0, 0.0, 0.0]])
    v = uniform_quasipotential(e, segs_um, soma_um)
    assert v[0] == pytest.approx(0.0)


def test_uniform_quasipotential_units_mv():
    # E = 1 V/m == 1 mV/mm; a segment 1 mm (1000 um) along +x sits at -1 mV.
    e = np.array([1.0, 0.0, 0.0])
    soma_um = np.array([0.0, 0.0, 0.0])
    segs_um = np.array([[1000.0, 0.0, 0.0]])
    v = uniform_quasipotential(e, segs_um, soma_um)
    assert v[0] == pytest.approx(-1.0)


def test_uniform_quasipotential_orientation_dependence():
    # A field perpendicular to the cell axis produces no potential difference;
    # a parallel field does. This is the orientation sensitivity that matters.
    soma_um = np.array([0.0, 0.0, 0.0])
    segs_um = np.array([[1000.0, 0.0, 0.0]])  # cell extends along +x
    v_parallel = uniform_quasipotential([1.0, 0.0, 0.0], segs_um, soma_um)
    v_perp = uniform_quasipotential([0.0, 1.0, 0.0], segs_um, soma_um)
    assert abs(v_parallel[0]) > 0.0
    assert v_perp[0] == pytest.approx(0.0)


def test_uniform_quasipotential_scales_with_field():
    soma_um = np.array([0.0, 0.0, 0.0])
    segs_um = np.array([[500.0, 0.0, 0.0]])
    v1 = uniform_quasipotential([2.0, 0.0, 0.0], segs_um, soma_um)
    v2 = uniform_quasipotential([4.0, 0.0, 0.0], segs_um, soma_um)
    assert v2[0] == pytest.approx(2.0 * v1[0])


# ---------------------------------------------------------------------------
# Path (full-field) quasipotential
# ---------------------------------------------------------------------------


def test_path_quasipotential_uniform_field_matches_uniform():
    # With a spatially constant field, the path integral must equal the
    # uniform-field result.
    coords_um = np.array(
        [[0.0, 0.0, 0.0], [1000.0, 0.0, 0.0], [2000.0, 0.0, 0.0]]
    )
    parent = np.array([0, 0, 1])
    e = np.tile([1.0, 0.0, 0.0], (3, 1))
    v_path = path_quasipotential(e, coords_um, parent, root=0)
    v_uniform = uniform_quasipotential([1.0, 0.0, 0.0], coords_um, coords_um[0])
    assert np.allclose(v_path, v_uniform)


def test_path_quasipotential_root_is_zero():
    coords_um = np.array([[0.0, 0.0, 0.0], [1000.0, 0.0, 0.0]])
    parent = np.array([0, 0])
    e = np.tile([3.0, 0.0, 0.0], (2, 1))
    v = path_quasipotential(e, coords_um, parent, root=0)
    assert v[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_config_defaults_valid():
    cfg = MicroscaleConfig(sim_name="sim1")
    assert cfg.carrier_freqs == DEFAULT_CARRIERS
    assert cfg.envelope_freq == pytest.approx(10.0)


def test_config_requires_sim_name():
    with pytest.raises(ValueError, match="sim_name"):
        MicroscaleConfig(sim_name="")


def test_config_rejects_coarse_dt():
    # 2010 Hz carrier -> period ~0.4975 ms -> need dt <= ~0.0498 ms.
    with pytest.raises(ValueError, match="too coarse"):
        MicroscaleConfig(sim_name="s", dt=0.5)


def test_config_accepts_fine_dt():
    cfg = MicroscaleConfig(sim_name="s", dt=0.005)
    assert cfg.dt == 0.005


def test_config_rejects_bad_carrier_pair():
    with pytest.raises(ValueError, match="pair"):
        MicroscaleConfig(sim_name="s", carrier_freqs=(2000.0,))


def test_config_rejects_negative_frequency():
    with pytest.raises(ValueError, match="positive"):
        MicroscaleConfig(sim_name="s", carrier_freqs=(2000.0, -1.0))


def test_config_rejects_bad_target_shape():
    with pytest.raises(ValueError, match="x, y, z"):
        MicroscaleConfig(sim_name="s", targets=((1.0, 2.0),))


def test_config_equal_carriers_zero_envelope():
    cfg = MicroscaleConfig(sim_name="s", carrier_freqs=(2000.0, 2000.0))
    assert cfg.envelope_freq == pytest.approx(0.0)


def test_neuron_model_spec_defaults():
    spec = NeuronModelSpec(name="ball_stick")
    assert spec.has_active_channels is True
    assert spec.mechanisms == ()
