"""tit.tract geometry, field-on-tract metrics, edges and selection (host; numpy is real).

Pins (2026-11-04):

* a uniform two-carrier field on a straight streamline gives
  ``ti_along = ||(E1+E2).d| - |(E1-E2).d||`` (Grossman 2017's directional envelope, written
  out here in scalars, not through ``tit.calc``), zero activating function, and
  ``align = ti_along / ti_max <= 1``;
* a helix's resampled tangents and curvature match the analytic ``(-R sin, R cos, c)/sqrt(R^2+c^2)``
  and ``R/(R^2+c^2)``;
* on a circle in a uniform field the activating function equals ``-kappa E.n_hat``
  (``E0 cos(theta) / R`` per mm; the bend term of d(E.t)/ds) times the smoothing triangle's
  gain ``(sin x / x)^2``, in V/m^2; on a piecewise-constant mesh-like field it is
  step-independent (max within 5 %, mean within 1 % across 1 / 0.5 / 0.25 mm) where the
  pointwise derivative more than doubles;
* ``ti_avg`` equals a Monte Carlo average of the envelope over random directions, and the
  ratios are what they are named; world -> voxel directions step along the planted world
  direction for LPS, PSR and oblique anisotropic affines (DIPY's stepping rule);
* ``derivative`` equals ``numpy.gradient`` streamline by streamline; arc-length means and
  fractions follow the trapezoid rule on a ramp; ``orient`` runs region_a -> region_b (else
  lower x first) whatever the input direction, and oriented profiles line up;
* edge numbering, connectome symmetry and the region selectors (including ``to_cortex``)
  on hand-made labels.

Every expected value is a closed form or numpy's own routine. The KD-tree endpoint
association (real scipy) is in ``tests/numerical/test_tract_association.py``; the
directional envelope against a time-domain Hilbert envelope and the mesh sampling are in
``tests/numerical/test_tract_fields.py``.
"""

import numpy as np
import pytest

from tit.tract import geometry
from tit.tract.config import AssessConfig, Selection, TargetConfig, TractConfig
from tit.tract.network import connectome, edges_from_labels, select


def _resampled(streamlines, step):
    pts, off, h = geometry.resample(streamlines, step)
    return pts, off, h, geometry.tangents(pts, off, h)


def test_uniform_field_straight_streamline_has_analytic_ti_along():
    d = np.array([1.0, 2.0, -2.0]) / 3.0
    line = np.outer(np.linspace(0, 60, 7), d) + [5.0, -3.0, 10.0]
    pts, off, h, t = _resampled([line], 0.5)
    e1, e2 = np.array([0.3, -0.1, 0.2]), np.array([-0.05, 0.25, 0.1])
    E1, E2 = np.tile(e1, (len(pts), 1)), np.tile(e2, (len(pts), 1))
    m = geometry.point_metrics([E1, E2], t, off, h)
    expected = abs(abs((e1 + e2) @ d) - abs((e1 - e2) @ d))
    np.testing.assert_allclose(m["ti_along"], expected, rtol=1e-12)
    np.testing.assert_allclose(m["e_par"][0], e1 @ d, rtol=1e-12)
    np.testing.assert_allclose(m["e_par_pk"], abs(e1 @ d) + abs(e2 @ d), rtol=1e-12)
    np.testing.assert_allclose(m["p_par"], 0.5 * ((e1 @ d) ** 2 + (e2 @ d) ** 2))
    assert np.all(np.abs(m["f"]) < 1e-9) and np.all(m["f_am"] < 1e-9)
    assert np.all(m["align"] <= 1 + 1e-12) and np.all(m["ti_max"] >= m["ti_along"])


def test_two_pair_mti_uses_every_channel():
    # K = 2 pairs: E_AM(d) = | |S d| - |D d| |, S/D rows E_ka +/- E_kb (Grossman's form,
    # the left-hand side of tit.calc.envelope's docstring; the code evaluates the right-hand one)
    d = np.array([0.0, 0.6, 0.8])
    line = np.outer(np.linspace(0, 30, 4), d)
    pts, off, h, t = _resampled([line], 1.0)
    rng = np.random.default_rng(1)
    e = rng.normal(size=(4, 3))
    fields = [np.tile(v, (len(pts), 1)) for v in e]
    m = geometry.point_metrics(fields, t, off, h)
    s = np.array([(e[0] + e[1]) @ d, (e[2] + e[3]) @ d])
    dd = np.array([(e[0] - e[1]) @ d, (e[2] - e[3]) @ d])
    expected = abs(np.linalg.norm(s) - np.linalg.norm(dd))
    np.testing.assert_allclose(m["ti_along"], expected, rtol=1e-10)
    assert m["e_par"].shape == (4, len(pts))


def test_helix_tangent_and_curvature_match_closed_form():
    R, c = 10.0, 3.0
    theta = np.linspace(0, 4 * np.pi, 20001)
    helix = np.column_stack([R * np.cos(theta), R * np.sin(theta), c * theta])
    pts, off, h, t = _resampled([helix], 0.25)
    th = np.arctan2(pts[:, 1], pts[:, 0])
    exact = np.column_stack([-R * np.sin(th), R * np.cos(th), np.full_like(th, c)])
    exact /= np.hypot(R, c)
    inner = slice(1, -1)  # the two ends are one-sided differences
    assert np.max(np.linalg.norm(t[inner] - exact[inner], axis=1)) < 1e-3
    kappa = geometry.curvature(t, off, h)[2:-2]
    np.testing.assert_allclose(kappa, R / (R**2 + c**2), rtol=2e-3)


def test_activating_function_on_circle_is_bend_term():
    R, E0 = 20.0, 0.5  # mm, V/m
    theta = np.linspace(0, 2 * np.pi, 40001)
    circle = np.column_stack(
        [R * np.cos(theta), R * np.sin(theta), np.zeros_like(theta)]
    )
    pts, off, h, t = _resampled([circle], 0.2)
    E = np.tile([E0, 0.0, 0.0], (len(pts), 1))
    a = 2.0  # smoothing half-width, mm
    m = geometry.point_metrics([E, 0.5 * E], t, off, h, scale_mm=a)
    th = np.arctan2(pts[:, 1], pts[:, 0])
    # -kappa E.n_hat (per mm -> per m), times the triangle kernel's gain at wavenumber 1/R:
    # (sin(x)/x)^2 with x = a / (2R)
    x = a / (2 * R)
    expected = E0 * np.cos(th) / R * 1e3 * (np.sin(x) / x) ** 2
    inner = slice(11, -11)  # the window is clamped within a = 2 mm of the ends
    np.testing.assert_allclose(
        m["f"][0][inner], expected[inner], atol=2e-3 * E0 / R * 1e3
    )


def test_smoothed_activating_function_does_not_depend_on_the_step():
    # a piecewise-constant field like a mesh's: cells 0.6-1.4 mm, value = a smooth
    # function at the cell centre. The pointwise derivative grows as the step shrinks
    # (jumps / h); the smoothed one must not.
    rng = np.random.default_rng(0)
    edges = np.r_[0, np.cumsum(rng.uniform(0.6, 1.4, 200))]
    edges = edges[edges < 80.0]
    centres = 0.5 * (edges[:-1] + edges[1:])
    g = lambda s: 0.2 * np.sin(2 * np.pi * s / 25.0) + 0.05 * np.cos(
        2 * np.pi * s / 9.0
    )
    vals = g(centres)
    line = np.column_stack([np.linspace(0, 80.0, 3), np.zeros(3), np.zeros(3)])
    smooth, pointwise = {}, {}
    for step in (1.0, 0.5, 0.25):
        pts, off, h = geometry.resample([line], step)
        cell = np.clip(
            np.searchsorted(edges, pts[:, 0], side="right") - 1, 0, len(vals) - 1
        )
        smooth[step] = np.abs(geometry.smoothed_derivative(vals[cell], off, h, 2.0))
        pointwise[step] = np.abs(geometry.derivative(vals[cell], off, h)).max()
    for step in (0.5, 0.25):
        assert smooth[step].max() == pytest.approx(smooth[1.0].max(), rel=0.05)
        assert smooth[step].mean() == pytest.approx(smooth[1.0].mean(), rel=0.01)
    assert pointwise[0.25] > 2 * pointwise[1.0]
    # and it approximates the derivative of the field it discretises (|g'| <= 0.085 / mm)
    assert smooth[0.25].max() == pytest.approx(0.085, rel=0.1)


def test_random_directions_average_to_ti_avg_and_alignment_index():
    rng = np.random.default_rng(3)
    e1, e2 = np.array([0.3, -0.1, 0.2]), np.array([-0.05, 0.25, 0.1])
    n = rng.normal(size=(200_000, 3))
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    # Monte Carlo over the sphere of the scalar envelope written out here
    mc = np.mean(np.abs(np.abs(n @ (e1 + e2)) - np.abs(n @ (e1 - e2))))
    line = np.outer(np.linspace(0, 10, 3), [1.0, 0, 0])
    pts, off, h, t = _resampled([line], 1.0)
    E1, E2 = np.tile(e1, (len(pts), 1)), np.tile(e2, (len(pts), 1))
    m = geometry.point_metrics([E1, E2], t, off, h)
    assert m["ti_avg"][0] == pytest.approx(mc, rel=0.01)
    np.testing.assert_allclose(m["align_index"], m["ti_along"] / m["ti_avg"])
    np.testing.assert_allclose(m["avg_ratio"], m["ti_avg"] / m["ti_max"])


def test_world_to_voxel_dirs_steps_along_the_planted_world_direction():
    from tit.tract.tracking import world_to_voxel_dirs

    rot = np.linalg.qr(np.random.default_rng(5).normal(size=(3, 3)))[0]
    affines = {
        "LPS": np.diag([-1.0, -1.0, 1.0, 1.0]),
        "PSR": np.array(
            [[0, 0, 1.0, 0], [-1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 0, 1]]
        ),
        "oblique anisotropic": np.block(
            [
                [rot @ np.diag([0.9, 1.2, 2.0]), np.zeros((3, 1))],
                [np.zeros((1, 3)), 1.0],
            ]
        ),
    }
    d_world = np.array([[0.48, -0.6, 0.64], [1.0, 0, 0], [0, 0, 1.0]])
    for name, aff in affines.items():
        d_vox = world_to_voxel_dirs(d_world, aff)
        zooms = np.linalg.norm(aff[:3, :3], axis=0)
        # DIPY's step in voxel index space is d_vox / voxel size; the affine takes it to world
        step = (aff[:3, :3] @ (d_vox / zooms).T).T
        step /= np.linalg.norm(step, axis=1, keepdims=True)
        np.testing.assert_allclose(step, d_world, atol=1e-12, err_msg=name)


def test_derivative_is_numpy_gradient_per_streamline():
    rng = np.random.default_rng(0)
    sls = [np.cumsum(rng.normal(size=(n, 3)), axis=0) for n in (2, 3, 9, 30)]
    pts, off, h = geometry.resample(sls, 0.7)
    vals = rng.normal(size=len(pts))
    d = geometry.derivative(vals, off, h)
    for s in range(len(sls)):
        a, b = off[s], off[s + 1]
        np.testing.assert_allclose(d[a:b], np.gradient(vals[a:b], h[s]), rtol=1e-12)


def test_resample_keeps_ends_and_uniform_step():
    sl = np.array([[0.0, 0, 0], [3.0, 4.0, 0], [3.0, 4.0, 12.0]])  # length 5 + 12
    pts, off, h = geometry.resample([sl], 1.0)
    assert off.tolist() == [0, 18] and h[0] == pytest.approx(1.0)
    np.testing.assert_allclose(pts[[0, -1]], sl[[0, -1]])
    assert geometry.lengths(off, h)[0] == pytest.approx(17.0)
    with pytest.raises(ValueError):
        geometry.resample([np.zeros((3, 3))], 1.0)


def test_streamline_stats_trapezoid_on_a_ramp():
    line = np.column_stack([np.linspace(0, 40, 5), np.zeros(5), np.zeros(5)])
    pts, off, h = geometry.resample([line], 0.5)
    s = pts[:, 0]  # value = arc position, mm
    stats = geometry.streamline_stats(s, off, h, thresholds=[10.0])
    assert stats["mean"][0] == pytest.approx(20.0)  # exact for a linear function
    assert stats["max"][0] == pytest.approx(40.0)
    assert (stats["start"][0], stats["end"][0]) == (0.0, 40.0)
    assert stats["frac_ge_10"][0] == pytest.approx(30.0 / 40.0, abs=h[0] / 40.0)


def test_orient_runs_region_a_to_b_else_from_lower_x():
    from tit.tract.network import orient

    a = np.column_stack([np.linspace(0, 30, 31), np.zeros(31), np.zeros(31)])
    sls = [a, a[::-1], a[::-1], a[::-1] + [0, 5.0, 0]]
    labels = np.array([[2, 7], [2, 7], [-1, 4], [3, 3]])
    out, lab, rev = orient(sls, labels)
    assert rev.tolist() == [False, False, True, True]
    assert lab.tolist() == [[2, 7], [2, 7], [4, -1], [3, 3]]
    assert [s[0, 0] for s in out] == [0.0, 30.0, 0.0, 0.0]
    # reversing the input does not change the result
    out2, lab2, _ = orient([s[::-1] for s in sls], labels[:, ::-1])
    for s, s2 in zip(out, out2):
        np.testing.assert_array_equal(s, s2)
    assert lab2.tolist() == lab.tolist()


def test_profiles_of_oriented_streamlines_line_up():
    from tit.tract.network import orient

    a = np.column_stack([np.linspace(0, 30, 31), np.zeros(31), np.zeros(31)])
    sls, _, _ = orient([a, a[::-1] + [0.0, 1.0, 0.0]], np.array([[0, 1], [1, 0]]))
    pts, off, h = geometry.resample(sls, 1.0)
    prof = geometry.profiles(pts[:, 0], off, 11)
    np.testing.assert_allclose(prof[0], np.linspace(0, 30, 11))
    np.testing.assert_allclose(prof[1], prof[0])


def test_edges_numbered_by_count_and_unassigned_is_minus_one():
    labels = np.array([[3, 1], [1, 3], [0, 0], [2, -1], [1, 3], [0, 0], [0, 2]])
    edge_id, pairs = edges_from_labels(labels)
    assert pairs.tolist() == [[1, 3], [0, 0], [0, 2]]  # 3, 2, 1 streamlines
    assert edge_id.tolist() == [0, 0, 1, -1, 0, 1, 2]
    mat = connectome(pairs, np.array([3.0, 2.0, 1.0]), 4)
    assert (
        mat[1, 3] == mat[3, 1] == 3.0 and mat[0, 0] == 2.0 and np.allclose(mat, mat.T)
    )


def test_selectors_on_hand_made_labels():
    names = ["lh.insula", "Left-Thalamus", "lh.precentral", "rh.insula"]
    labels = np.array([[0, 1], [1, 0], [1, 2], [2, 3], [-1, 1], [1, 2], [1, 2]])
    edge_id, _ = edges_from_labels(labels)
    pick = lambda **kw: select(
        Selection(name="b", **kw), labels, names, edge_id
    ).tolist()
    assert pick(kind="between", regions=["Left-Thalamus", "lh.insula"]) == [
        True,
        True,
        False,
        False,
        False,
        False,
        False,
    ]
    assert (
        pick(kind="from", regions=["rh.insula"]) == [False] * 3 + [True] + [False] * 3
    )
    top1 = pick(kind="top_edges", regions=["Left-Thalamus"], k=1)
    assert top1 == [False, False, True, False, False, True, True]
    tc = pick(kind="to_cortex", regions=["Left-Thalamus"])
    assert tc == [True, True, True, False, False, True, True]
    assert pick(kind="to_cortex", regions=["lh.precentral"]) == [
        False,
        False,
        False,
        True,
        False,
        False,
        False,  # rh.insula only; thalamus is not cortex
    ]
    assert sum(pick(kind="all")) == 7
    with pytest.raises(ValueError, match="Unknown region"):
        pick(kind="from", regions=["nope"])


def test_configs_reject_bad_values():
    with pytest.raises(ValueError):
        Selection(name="x", kind="between", regions=["a"])
    with pytest.raises(ValueError):
        Selection(name="bad name!")
    with pytest.raises(ValueError):
        TractConfig(subject_id="CHN", stages=["assess"])  # no simulations
    with pytest.raises(ValueError):
        TargetConfig(montages=[["F7", "P7", "F8"]])
    assert AssessConfig().thresholds == []  # no default threshold


def test_flip_verdict_treats_the_full_flip_as_unflipped():
    from tit.tract.tracking import flip_verdict

    rows = [
        {"flip": [1, 1, 1], "median_abs_cos": 0.98},
        {"flip": [1, 1, -1], "median_abs_cos": 0.87},
        {"flip": [1, -1, 1], "median_abs_cos": 0.88},
        {"flip": [-1, -1, -1], "median_abs_cos": 0.98},
    ]
    v = flip_verdict(rows)
    assert v["flip_test_passed"] and v["flip_test_margin"] == pytest.approx(0.10)
    rows[2]["median_abs_cos"] = 0.99
    v = flip_verdict(rows)
    assert not v["flip_test_passed"] and v["flip_test_winner"] == [1, -1, 1]


def test_tract_config_round_trips_through_config_io():
    from tit.config_io import _serialize, deserialize_config

    cfg = TractConfig(
        subject_id="CHN",
        stages=["network", "assess"],
        assess=AssessConfig(
            simulations=["thalamus"],
            selections=[
                Selection(),
                Selection(name="thal", kind="from", regions=["Left-Thalamus"]),
            ],
            thresholds=[0.1],
        ),
    )
    data = _serialize(cfg)
    assert data["_type"] == "TractConfig"
    back = deserialize_config(TractConfig, data)
    assert back == cfg
