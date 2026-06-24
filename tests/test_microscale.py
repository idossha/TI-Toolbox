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
from tit.microscale.coupling import (
    build_extracellular_timeseries,
    count_spikes,
)
from tit.microscale.field_sampler import (
    mm_to_um,
    path_quasipotential,
    place_morphology,
    rotation_align,
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
    coords_um = np.array([[0.0, 0.0, 0.0], [1000.0, 0.0, 0.0], [2000.0, 0.0, 0.0]])
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


# ---------------------------------------------------------------------------
# Orientation / placement geometry
# ---------------------------------------------------------------------------


def test_rotation_align_identity():
    r = rotation_align([0, 0, 1], [0, 0, 1])
    assert np.allclose(r, np.eye(3))


def test_rotation_align_maps_axis():
    r = rotation_align([0, 0, 1], [1, 0, 0])
    mapped = r @ np.array([0, 0, 1.0])
    assert np.allclose(mapped, [1, 0, 0])


def test_rotation_align_antiparallel():
    r = rotation_align([0, 0, 1], [0, 0, -1])
    mapped = r @ np.array([0, 0, 1.0])
    assert np.allclose(mapped, [0, 0, -1], atol=1e-9)


def test_rotation_align_is_orthonormal():
    r = rotation_align([1, 2, 3], [-2, 1, 0.5])
    assert np.allclose(r @ r.T, np.eye(3), atol=1e-9)
    assert np.isclose(np.linalg.det(r), 1.0)


def test_place_morphology_soma_lands_on_target():
    local = np.array([[0, 0, 0], [0, 0, 100.0]])
    soma_local = np.array([0, 0, 0.0])
    target = np.array([10.0, 20.0, 30.0])
    world = place_morphology(local, soma_local, target, normal=[0, 0, 1])
    assert np.allclose(world[0], target)


def test_place_morphology_preserves_length():
    local = np.array([[0, 0, 0], [0, 0, 100.0]])
    soma_local = np.array([0, 0, 0.0])
    world = place_morphology(local, soma_local, [5, 5, 5], normal=[1, 0, 0])
    seg_len = np.linalg.norm(world[1] - world[0])
    assert seg_len == pytest.approx(100.0)
    # Apical (local +z) should now point along +x.
    assert np.allclose((world[1] - world[0]) / 100.0, [1, 0, 0], atol=1e-9)


# ---------------------------------------------------------------------------
# Two-carrier extracellular drive + spike counting
# ---------------------------------------------------------------------------


def test_timeseries_shape_and_amplitude():
    ve1 = np.array([1.0, -2.0, 0.5])
    ve2 = np.array([0.0, 1.0, 1.0])
    t = np.linspace(0, 10, 500)
    ts = build_extracellular_timeseries(ve1, ve2, t, 2000.0, 2010.0, amplitude=3.0)
    assert ts.shape == (3, 500)
    # Per-segment bound: |A*(ve1*s1 + ve2*s2)| <= A*(|ve1|+|ve2|)
    bound = 3.0 * (np.abs(ve1) + np.abs(ve2))
    assert np.all(np.abs(ts) <= bound[:, None] + 1e-9)


def test_timeseries_equal_carriers_no_beat():
    # Equal frequencies -> pure sinusoid, no envelope modulation.
    ve1 = np.array([1.0])
    ve2 = np.array([1.0])
    t = np.linspace(0, 5, 2000)
    ts = build_extracellular_timeseries(ve1, ve2, t, 2000.0, 2000.0)[0]
    # Envelope (analytic-free proxy): peak amplitude constant ~ 2.0
    assert np.max(ts) == pytest.approx(2.0, abs=0.02)


def test_count_spikes_counts_upward_crossings():
    # Two bumps above 0 mV.
    v = np.array([-65, -65, 10, 10, -65, -65, 20, 20, -65])
    assert count_spikes(v, threshold=0.0) == 2


def test_count_spikes_none_below_threshold():
    v = np.full(100, -65.0)
    assert count_spikes(v) == 0


# ---------------------------------------------------------------------------
# config_io round-trip + PathManager wiring + metrics IO
# ---------------------------------------------------------------------------


def test_config_io_roundtrip(init_pm):
    from tit.config_io import read_config_json, serialize_config, write_config_json

    cfg = MicroscaleConfig(
        sim_name="sim1", targets=((1.0, 2.0, 3.0),), carrier_freqs=(2000.0, 2020.0)
    )
    data = serialize_config(cfg)
    assert data["_type"] == "MicroscaleConfig"
    assert data["sim_name"] == "sim1"
    assert "project_dir" in data

    path = write_config_json(cfg, prefix="microscale")
    back = read_config_json(path)
    assert back["sim_name"] == "sim1"
    assert back["carrier_freqs"] == [2000.0, 2020.0]


def test_pathmanager_microscale_helpers(init_pm):
    pm = init_pm
    assert pm.microscale("001").endswith("/sub-001/microscale")
    assert pm.microscale_sim("001", "simX").endswith("/sub-001/microscale/simX")
    # Distinct from simulations() and leadfields().
    assert "microscale" in pm.microscale("001")
    assert "Simulations" not in pm.microscale("001")


def test_metrics_targets_csv(tmp_path):
    from tit.microscale.metrics import write_targets_csv

    path = str(tmp_path / "out" / "targets.csv")
    write_targets_csv(path, [(1.0, 2.0, 3.0)], [(0.0, 0.0, 1.0)])
    text = (tmp_path / "out" / "targets.csv").read_text()
    assert "x_mm" in text
    assert "1.0,2.0,3.0,0.0,0.0,1.0" in text


def test_metrics_response_npz(tmp_path):
    from tit.microscale.metrics import write_response_npz

    path = str(tmp_path / "r.npz")
    write_response_npz(path, [{"n_spikes": 3, "ve1_max": 0.5}, {"n_spikes": 0}])
    loaded = np.load(path)
    assert list(loaded["n_spikes"]) == [3.0, 0.0]
    assert np.isnan(loaded["threshold"]).all()


def test_viz_crop_surface_patch():
    from tit.microscale.viz import crop_surface_patch

    # 4 nodes; node 3 is far away. Triangles (0,1,2) near, (1,2,3) spans far.
    coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [50, 0, 0]], dtype=float)
    tris = np.array([[0, 1, 2], [1, 2, 3]])
    pc, pt, mask = crop_surface_patch(coords, tris, [0, 0, 0], radius_mm=5.0)
    assert mask.tolist() == [True, True, True, False]
    assert pt.shape == (1, 3)  # only the near triangle survives
    assert pc.shape == (3, 3)
    # remapped indices reference the cropped node set
    assert pt.max() < pc.shape[0]


def test_viz_grid_around_shape():
    from tit.microscale.viz import grid_around

    g = grid_around([1.0, 2.0, 3.0], radius_mm=6.0, n=4)
    assert g.shape == (64, 3)
    assert np.allclose(g.mean(0), [1.0, 2.0, 3.0])


def test_viz_section_polylines_splits_by_span():
    from tit.microscale.viz import section_polylines

    world = np.arange(15, dtype=float).reshape(5, 3)
    spans = [("soma", "soma", 20.0, 0, 2), ("apic", "dendrite", 2.0, 2, 3)]
    lines = section_polylines(world, spans)
    assert len(lines) == 2
    assert lines[0]["kind"] == "soma" and lines[0]["coords"].shape == (2, 3)
    assert lines[1]["kind"] == "dendrite" and lines[1]["coords"].shape == (3, 3)
    assert np.allclose(lines[1]["coords"][0], world[2])


def test_metrics_polarization_npz(tmp_path):
    from tit.microscale.metrics import write_polarization_npz

    path = str(tmp_path / "p.npz")
    write_polarization_npz(
        path,
        [{"delta_vm": [0.1, 0.2], "seg_coords_um": [[0, 0, 0], [0, 0, 1]]}],
    )
    loaded = np.load(path)
    assert np.allclose(loaded["delta_vm_0"], [0.1, 0.2])


# ---------------------------------------------------------------------------
# find_threshold bisection logic (NEURON-free, via injected simulate_response)
# ---------------------------------------------------------------------------


def _patch_fires(monkeypatch, true_threshold):
    """Make simulate_response report firing iff amplitude_scale >= threshold."""
    import tit.microscale.coupling as coupling

    def fake(cfg, *a, **k):
        return {"n_spikes": 1 if cfg.amplitude_scale >= true_threshold else 0}

    monkeypatch.setattr(coupling, "simulate_response", fake)
    return coupling


def test_find_threshold_brackets_true_value(monkeypatch):
    coupling = _patch_fires(monkeypatch, true_threshold=12.5)
    cfg = MicroscaleConfig(sim_name="s")
    thr = coupling.find_threshold(cfg, None, None, None, None, lo=0.0, hi=100.0)
    # Within the 5% relative tolerance of the true threshold.
    assert thr == pytest.approx(12.5, rel=0.06)


def test_find_threshold_inf_when_never_fires(monkeypatch):
    coupling = _patch_fires(monkeypatch, true_threshold=1e9)
    cfg = MicroscaleConfig(sim_name="s")
    thr = coupling.find_threshold(cfg, None, None, None, None, hi=100.0)
    assert thr == float("inf")


def test_find_threshold_floor_not_zero_when_always_fires(monkeypatch):
    # Fires even at the smallest probe -> must report the positive floor, not 0.
    coupling = _patch_fires(monkeypatch, true_threshold=0.0)
    cfg = MicroscaleConfig(sim_name="s")
    thr = coupling.find_threshold(cfg, None, None, None, None, lo=0.0, hi=100.0)
    assert thr > 0.0
