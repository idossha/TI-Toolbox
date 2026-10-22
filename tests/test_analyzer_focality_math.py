"""Weighted percentiles and focality areas by hand; mesh and voxel agree on identical data (2026-10-22).

What this pins
    ``Analyzer._compute_focality_metrics`` is a weighted percentile (the first sorted value
    whose cumulative weight fraction reaches q) plus "area/volume at or above X % of the
    99.9th percentile". Hand fixtures pin both, the NaN and +/-inf handling (dropped; an inf
    used to become the 99.9th percentile and zero every area), and the edge shapes (one
    element, all-equal values). A seeded property test pins the orderings that must hold for
    any input. The parity test builds one dataset twice -- as mesh nodes with 1 mm^2 areas
    and as voxels of 1 mm^3 -- with zero-valued and negative elements inside the ROI, runs the
    real spherical paths of both spaces, and requires every statistic to agree, the focality
    areas to differ by exactly the 100 vs 1000 cm divisor, and ``n_elements`` to count the
    same thing (positive ROI elements; the mesh used to count the non-positive nodes too).

Where the expectations come from
    Hand arithmetic, written out next to each assertion; the property test's bounds are
    definitions (a percentile cannot exceed the maximum, a higher cutoff cannot select more
    area). Parity compares the two spaces with each other, never with a retyped number.

Run: .venv/bin/python -m pytest tests/test_analyzer_focality_math.py -q -p no:cacheprovider
(numpy is real on the host; nibabel is replaced by an in-memory image here.)
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tit.analyzer.analyzer import Analyzer

KEYS = (
    "percentile_95",
    "percentile_99",
    "percentile_99_9",
    "focality_50_area",
    "focality_75_area",
    "focality_90_area",
    "focality_95_area",
)


def metrics(values, weights, weight_to_cm=100.0) -> dict:
    return Analyzer._compute_focality_metrics(
        None,
        np.asarray(values, dtype=float),
        np.asarray(weights, dtype=float),
        weight_to_cm=weight_to_cm,
    )


def test_weighted_percentiles_and_areas_by_hand() -> None:
    m = metrics([1, 2, 3, 4], [1, 1, 1, 97])
    # Cumulative fractions 0.01, 0.02, 0.03, 1.00: the first reaching 0.95/0.99/0.999 is 4.
    assert (m["percentile_95"], m["percentile_99"], m["percentile_99_9"]) == (4, 4, 4)
    # Cutoffs 2, 3, 3.6, 3.8; weights of values >= cutoff: 1+1+97, 1+97, 97, 97 (mm^2 / 100).
    assert m["focality_50_area"] == pytest.approx(0.99)
    assert m["focality_75_area"] == pytest.approx(0.98)
    assert m["focality_90_area"] == pytest.approx(0.97)
    assert m["focality_95_area"] == pytest.approx(0.97)


def test_percentiles_split_where_the_weight_does() -> None:
    m = metrics([10, 20, 30], [94, 4.5, 1.5], weight_to_cm=1000.0)
    # Cumulative 0.94, 0.985, 1.0: p95 -> 20 (0.985 >= 0.95), p99 and p99.9 -> 30.
    assert m["percentile_95"] == 20
    assert m["percentile_99"] == 30 and m["percentile_99_9"] == 30
    # Cutoffs 15, 22.5, 27, 28.5 of 30; volume (mm^3 / 1000) at or above each.
    assert m["focality_50_area"] == pytest.approx(0.006)
    assert m["focality_75_area"] == pytest.approx(0.0015)


def test_nan_and_infinities_are_not_field_values() -> None:
    clean = metrics([1, 2, 3, 4], [1, 1, 1, 97])
    dirty = metrics([np.nan, 1, 2, np.inf, 3, -np.inf, 4], [50, 1, 1, 50, 1, 50, 97])
    for key in KEYS:
        assert math.isfinite(dirty[key]), key
        assert dirty[key] == pytest.approx(clean[key]), key


def test_single_element_and_all_equal_values() -> None:
    one = metrics([0.7], [3.0])
    assert one["percentile_95"] == one["percentile_99_9"] == 0.7
    assert one["focality_95_area"] == pytest.approx(0.03)
    same = metrics([2.0, 2.0, 2.0], [1.0, 2.0, 3.0])
    assert same["percentile_95"] == same["percentile_99_9"] == 2.0
    # Every element is at the 99.9th percentile, so every cutoff keeps all 6 mm^2.
    assert all(same[k] == pytest.approx(0.06) for k in KEYS[3:])


@pytest.mark.parametrize("seed", range(20))
def test_orderings_hold_for_random_fields(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 400))
    values = rng.gamma(2.0, 0.1, n)
    weights = rng.uniform(0.01, 3.0, n)
    m = metrics(values, weights)
    assert m["percentile_95"] <= m["percentile_99"] <= m["percentile_99_9"]
    assert m["percentile_99_9"] <= values.max()
    assert m["percentile_95"] >= values.min()
    total = weights.sum() / 100.0
    areas = [m[k] for k in KEYS[3:]]
    assert areas == sorted(areas, reverse=True)
    assert 0 < areas[-1] and areas[0] <= total + 1e-12


# -- mesh vs voxel parity ----------------------------------------------------------------------


def _grid_values() -> np.ndarray:
    """A 6x6x6 field on 1 mm voxels: distinct positives, with zeros and negatives near the centre."""
    values = np.linspace(0.05, 2.0, 216).reshape(6, 6, 6)
    values[2, 3, 3] = 0.0
    values[3, 2, 3] = -0.4
    values[3, 3, 2] = 0.0
    values[0, 0, 0] = -1.0  # outside the ROI, outside the "grey matter" too
    return values


def _analyzer(space: str, tmp_path: Path) -> Analyzer:
    analyzer = object.__new__(Analyzer)
    analyzer.space = space
    analyzer.field_name = "TI_max"
    analyzer.tissue_type = "GM"
    analyzer.field_path = tmp_path / "grey_field_TI_max.nii.gz"
    analyzer.output_dir = str(tmp_path / space)
    analyzer._pm = SimpleNamespace(ensure=lambda p: Path(p).mkdir(parents=True) or p)
    analyzer._surface_mesh = None
    analyzer._is_mti = False
    return analyzer


def test_mesh_and_voxel_agree_on_identical_data(tmp_path: Path) -> None:
    values = _grid_values()
    ijk = np.argwhere(np.ones(values.shape, dtype=bool))  # C order, as values.ravel()
    surface = SimpleNamespace(
        nodes=SimpleNamespace(node_coord=ijk.astype(float)),
        field={"TI_max": SimpleNamespace(value=values.ravel())},
        nodes_areas=lambda: np.ones(len(ijk)),
    )
    mesh = _analyzer("mesh", tmp_path)
    mesh._surface_mesh = surface
    mesh._surface_mesh_path = tmp_path / "central.msh"
    mesh._get_normal_stats = lambda *a: None
    voxel = _analyzer("voxel", tmp_path)
    image = SimpleNamespace(get_fdata=lambda: values, affine=np.eye(4))

    # Sphere about voxel (3, 3, 3), r = 1.5: the centre, its 6 face and 12 edge neighbours.
    with patch("nibabel.load", lambda path: image):
        v = voxel.analyze_sphere((3.0, 3.0, 3.0), 1.5)
    m = mesh.analyze_sphere((3.0, 3.0, 3.0), 1.5)

    for key in (
        "roi_mean",
        "roi_max",
        "roi_min",
        "roi_focality",
        "gm_mean",
        "gm_max",
        "percentile_95",
        "percentile_99",
        "percentile_99_9",
        "total_area_or_volume",
    ):
        assert getattr(m, key) == pytest.approx(getattr(v, key), rel=1e-12), key
    # 19 elements in the sphere, three of them <= 0: both spaces count the other 16.
    assert m.n_elements == v.n_elements == 16
    for key in KEYS[3:]:
        # Same summed weight; mm^2 / 100 vs mm^3 / 1000.
        assert getattr(m, key) == pytest.approx(10.0 * getattr(v, key), rel=1e-12), key
