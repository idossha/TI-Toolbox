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
    PopulationConfig,
)
from tit.microscale.coupling import (
    build_extracellular_timeseries,
    count_spikes,
)
from tit.microscale.population import (
    analytic_polarization_map,
    azimuths,
    select_cluster,
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


def test_morphology_pyramidal_l5_structure():
    from tit.microscale.morphology import pyramidal_l5

    m = pyramidal_l5(seed=0)
    kinds = {s.kind for s in m.sections}
    # a realistic pyramidal cell has all the major regions
    assert {"soma", "basal", "apical", "tuft", "ais", "axon", "node"} <= kinds
    assert m.soma_name == "soma"
    # branched: many more sections than a ball-stick
    assert len(m.sections) > 20
    # every non-soma section has a parent that exists
    names = {s.name for s in m.sections}
    for s in m.sections:
        if s.parent is not None:
            assert s.parent in names
    # deterministic given the seed
    m2 = pyramidal_l5(seed=0)
    assert len(m2.sections) == len(m.sections)
    assert m2.sections[5].points == m.sections[5].points


def test_morphology_load_swc(tmp_path):
    from tit.microscale.morphology import load_swc

    # minimal SWC: soma (1) -> dendrite (3) chain -> branch
    swc = tmp_path / "cell.swc"
    swc.write_text(
        "# id type x y z r parent\n"
        "1 1 0 0 0 5 -1\n"
        "2 3 0 0 10 1 1\n"
        "3 3 0 0 20 1 2\n"
        "4 3 5 0 25 1 3\n"
        "5 3 -5 0 25 1 3\n"
    )
    m = load_swc(str(swc))
    assert len(m.sections) >= 3  # soma path + two branches
    assert m.sections[0].kind == "soma"
    # branch children present
    assert sum(1 for s in m.sections if s.kind == "basal") >= 2


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


# ---------------------------------------------------------------------------
# Instantaneous TI field (rotating modulation vector)
# ---------------------------------------------------------------------------


def test_instantaneous_field_shape_and_units():
    from tit.microscale.viz import instantaneous_field

    e1 = np.array([1.0, 0.0, 0.0])
    e2 = np.array([0.0, 1.0, 0.0])
    t = np.linspace(0, 10, 250)
    e = instantaneous_field(e1, e2, 100.0, 120.0, t)
    assert e.shape == (250, 3)
    # At a time where sin(2π f1 t)=1 and sin(2π f2 t)=0 the result equals e1.
    f1, f2 = 100.0, 0.0  # f2=0 -> s2 identically 0
    t_peak_ms = np.array([1000.0 / (4.0 * f1)])  # quarter period -> sin=1
    e_peak = instantaneous_field(e1, e2, f1, f2, t_peak_ms)[0]
    assert np.allclose(e_peak, e1, atol=1e-9)


def test_instantaneous_field_rotates_when_nonparallel():
    from tit.microscale.viz import instantaneous_field

    e1 = np.array([1.0, 0.0, 0.0])
    e2 = np.array([0.0, 1.0, 0.0])
    t = np.linspace(0, 50, 4000)
    e = instantaneous_field(e1, e2, 100.0, 120.0, t)
    mag = np.linalg.norm(e, axis=1)
    keep = mag > 1e-6
    units = e[keep] / mag[keep][:, None]
    # Direction is not constant over time.
    assert not np.allclose(units, units[0], atol=1e-3)
    # The resultant sweeps a plane: cross products over time are nonzero.
    crosses = np.cross(units[:-1], units[1:])
    assert np.linalg.norm(crosses, axis=1).max() > 1e-3


def test_instantaneous_field_collinear_when_parallel():
    from tit.microscale.viz import instantaneous_field

    e1 = np.array([1.0, 0.0, 0.0])
    e2 = np.array([2.0, 0.0, 0.0])  # parallel to e1
    t = np.linspace(0, 50, 2000)
    e = instantaneous_field(e1, e2, 100.0, 120.0, t)
    # Every instantaneous vector is collinear with e1 (no y/z components).
    assert np.allclose(e[:, 1:], 0.0, atol=1e-12)
    mag = np.linalg.norm(e, axis=1)
    keep = mag > 1e-6
    units = e[keep] / mag[keep][:, None]
    crosses = np.cross(units[:-1], units[1:])
    assert np.linalg.norm(crosses, axis=1).max() < 1e-9


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


# ---------------------------------------------------------------------------
# Population: azimuth placement geometry
# ---------------------------------------------------------------------------


def test_place_morphology_azimuth_default_unchanged():
    # azimuth_deg=0.0 must reproduce the un-spun placement exactly.
    local = np.array([[0, 0, 0], [10.0, 0, 100.0]])
    soma_local = np.array([0, 0, 0.0])
    base = place_morphology(local, soma_local, [5, 5, 5], normal=[0, 0, 1])
    same = place_morphology(
        local, soma_local, [5, 5, 5], normal=[0, 0, 1], azimuth_deg=0.0
    )
    assert np.allclose(base, same)


def test_place_morphology_azimuth_rotates_about_normal():
    # Normal = +z; a 90 deg azimuth should rotate an off-axis point about z,
    # keep the soma on target, and preserve lengths.
    local = np.array([[0, 0, 0], [10.0, 0.0, 100.0]])
    soma_local = np.array([0, 0, 0.0])
    target = np.array([5.0, 5.0, 5.0])
    world = place_morphology(
        local, soma_local, target, normal=[0, 0, 1], azimuth_deg=90.0
    )
    # Soma stays on target.
    assert np.allclose(world[0], target)
    # The point's offset from the soma: (10, 0, 100) -> (0, 10, 100) under +90z.
    offset = world[1] - world[0]
    assert np.allclose(offset, [0.0, 10.0, 100.0], atol=1e-9)
    # Length preserved.
    assert np.linalg.norm(offset) == pytest.approx(np.hypot(10.0, 100.0))
    # The z (normal) component is unchanged by an azimuthal spin.
    assert offset[2] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Population: pure math
# ---------------------------------------------------------------------------


def test_analytic_polarization_map_linear():
    e = np.array([0.0, 1.0, -2.0, 5.0])
    dvm = analytic_polarization_map(e, 0.27)
    assert np.allclose(dvm, 0.27 * e)
    # Doubling the coupling doubles the polarization.
    assert np.allclose(analytic_polarization_map(e, 0.54), 2.0 * dvm)


def test_select_cluster_threshold_and_all():
    vals = np.array([0.1, 0.5, 0.9, 0.2, 0.7])
    rng = np.random.default_rng(0)
    # No threshold -> whole surface.
    cluster, _ = select_cluster(vals, None, 0, rng)
    assert cluster.tolist() == [0, 1, 2, 3, 4]
    # Threshold keeps field >= 0.5.
    cluster, _ = select_cluster(vals, 0.5, 0, rng)
    assert cluster.tolist() == [1, 2, 4]


def test_select_cluster_subsample_deterministic_and_capped():
    vals = np.linspace(0, 1, 20)
    a = select_cluster(vals, None, 5, np.random.default_rng(42))[1]
    b = select_cluster(vals, None, 5, np.random.default_rng(42))[1]
    # Deterministic given the same seeded generator.
    assert a.tolist() == b.tolist()
    assert a.size == 5
    # Subsample is a subset of the cluster, sorted, unique.
    assert np.all(np.diff(a) > 0)
    assert set(a.tolist()) <= set(range(20))
    # Capped at cluster size.
    capped = select_cluster(vals, None, 1000, np.random.default_rng(0))[1]
    assert capped.size == 20


def test_select_cluster_zero_subsample_empty():
    vals = np.array([1.0, 2.0, 3.0])
    cluster, sub = select_cluster(vals, None, 0, np.random.default_rng(0))
    assert cluster.size == 3
    assert sub.size == 0


def test_azimuths_evenly_spaced():
    assert azimuths(1) == [0.0]
    assert azimuths(4) == [0.0, 90.0, 180.0, 270.0]
    a = azimuths(6)
    assert len(a) == 6
    assert a[0] == 0.0
    assert max(a) < 360.0


def test_azimuths_rejects_zero():
    with pytest.raises(ValueError):
        azimuths(0)


# ---------------------------------------------------------------------------
# PopulationConfig validation
# ---------------------------------------------------------------------------


def test_population_config_defaults_valid():
    cfg = PopulationConfig(sim_name="sim1")
    assert cfg.carrier_freqs == DEFAULT_CARRIERS
    assert cfg.polarization_coupling == 0.27
    assert cfg.n_clones == 5 and cfg.n_azimuth == 6
    assert cfg.cluster_threshold is None
    assert cfg.envelope_freq == pytest.approx(10.0)


def test_population_config_requires_sim_name():
    with pytest.raises(ValueError, match="sim_name"):
        PopulationConfig(sim_name="")


def test_population_config_rejects_coarse_dt():
    with pytest.raises(ValueError, match="too coarse"):
        PopulationConfig(sim_name="s", dt=0.5)


def test_population_config_rejects_bad_counts():
    with pytest.raises(ValueError, match="n_clones"):
        PopulationConfig(sim_name="s", n_clones=0)
    with pytest.raises(ValueError, match="n_azimuth"):
        PopulationConfig(sim_name="s", n_azimuth=0)
    with pytest.raises(ValueError, match="n_subsample"):
        PopulationConfig(sim_name="s", n_subsample=-1)


# ---------------------------------------------------------------------------
# Population metrics IO
# ---------------------------------------------------------------------------


def _fake_population_result():
    return {
        "cluster_idx": np.array([0, 1, 2]),
        "vertices_mm": np.zeros((3, 3)),
        "normals": np.tile([0.0, 0.0, 1.0], (3, 1)),
        "ti_normal": np.array([0.5, 0.7, 0.9]),
        "analytic_delta_vm": np.array([0.135, 0.189, 0.243]),
        "subsample_idx": np.array([0, 2]),
        "neuron_delta_vm": np.array(
            [[[0.10, 0.12], [0.11, 0.13]], [[0.20, 0.22], [0.21, 0.23]]]
        ),
        "amplification": np.array(
            [[[1.0, 1.1], [1.0, 1.1]], [[0.9, 0.95], [0.9, 0.95]]]
        ),
        "summary": {"neuron_delta_vm_mean": 0.165, "amplification_mean": 1.0},
    }


def test_write_population_npz(tmp_path):
    from tit.microscale.metrics import write_population_npz

    path = str(tmp_path / "pop.npz")
    write_population_npz(path, _fake_population_result())
    loaded = np.load(path, allow_pickle=True)
    assert loaded["neuron_delta_vm"].shape == (2, 2, 2)
    assert np.allclose(loaded["analytic_delta_vm"], [0.135, 0.189, 0.243])
    assert "neuron_delta_vm_mean" in loaded["summary_keys"].tolist()


def test_write_population_summary_csv(tmp_path):
    from tit.microscale.metrics import write_population_summary_csv

    path = str(tmp_path / "pop_summary.csv")
    write_population_summary_csv(path, _fake_population_result())
    text = (tmp_path / "pop_summary.csv").read_text()
    assert "neuron_delta_vm_mean_mV" in text
    # One header + 2 subsample rows.
    assert len(text.strip().splitlines()) == 3
