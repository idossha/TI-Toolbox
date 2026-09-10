"""Grid vertex clustering — getting GM under the §S3 budget (lane SCA, 2026-09-04).

What this pins
    The properties decision S3 depends on: every output vertex is an *input*
    vertex at its original coordinate (so labels can be carried by index and
    electrodes stay registered), the triangle list stays valid and
    degenerate-free, the budget loop terminates, and a surface already under
    budget is returned untouched.

Where the numbers come from
    Synthetic grids whose vertex spacing is chosen so the expected cluster
    count is arithmetic, not a recorded run: a ``n x n`` lattice at 1 mm pitch
    clustered on a 2 mm grid must collapse to a ``ceil(n/2) x ceil(n/2))``
    lattice. Real triangle counts and the measured displacement on
    ``sub-ernie`` are ``tests/test_scene_realdata.py`` (env-gated), never
    retyped here.

Deliberately elsewhere
    Nothing here reads a mesh: ``simnibs`` is a ``MagicMock`` in this suite.
"""

from __future__ import annotations

import numpy as np
import pytest

from tit.scene.simplify import (
    cluster_simplify,
    mean_edge_length,
    simplify_to_budget,
)


def _grid_surface(n: int, pitch: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """An ``n x n`` vertex lattice in z=0, triangulated into 2*(n-1)^2 faces."""
    xs, ys = np.meshgrid(np.arange(n) * pitch, np.arange(n) * pitch, indexing="ij")
    vertices = np.stack([xs.ravel(), ys.ravel(), np.zeros(n * n)], axis=1)
    triangles = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b = i * n + j, i * n + j + 1
            c, d = (i + 1) * n + j, (i + 1) * n + j + 1
            triangles += [[a, b, c], [b, d, c]]
    return vertices, np.asarray(triangles, dtype=np.int64)


def test_mean_edge_length_is_the_lattice_pitch() -> None:
    """A unit lattice's edges are 1, 1 and sqrt(2): mean = (2 + sqrt2)/3."""
    vertices, triangles = _grid_surface(4)
    assert mean_edge_length(vertices, triangles) == pytest.approx(
        (2.0 + np.sqrt(2.0)) / 3.0
    )


def test_clustering_keeps_original_vertices_at_original_coordinates() -> None:
    """The property quadric decimation would not have.

    Every output vertex must be one of the input vertices, unmoved: an
    electrode measured in the mesh's own millimetres has to land on the
    surface, and a per-vertex label has to be selectable by index.
    """
    vertices, triangles = _grid_surface(9)
    result = cluster_simplify(vertices, triangles, cell=2.0)

    np.testing.assert_array_equal(result.vertices, vertices[result.source_index])
    assert len(np.unique(result.source_index)) == len(result.source_index)


def test_cluster_count_is_the_grid_arithmetic() -> None:
    """A 9x9 lattice at 1 mm on a 2 mm grid -> a 5x5 lattice, 25 vertices."""
    vertices, triangles = _grid_surface(9)
    result = cluster_simplify(vertices, triangles, cell=2.0)
    assert len(result.vertices) == 25
    # Every surviving vertex sits on the even sub-lattice its cell contains.
    assert set(np.unique(result.vertices[:, 0])) <= {0.0, 2.0, 4.0, 6.0, 8.0}


def test_output_triangles_are_valid_unique_and_non_degenerate() -> None:
    vertices, triangles = _grid_surface(9)
    result = cluster_simplify(vertices, triangles, cell=2.0)

    assert result.triangles.max() < len(result.vertices)
    corners = result.triangles
    assert (corners[:, 0] != corners[:, 1]).all()
    assert (corners[:, 1] != corners[:, 2]).all()
    assert (corners[:, 0] != corners[:, 2]).all()
    sorted_rows = np.sort(corners, axis=1)
    assert len(np.unique(sorted_rows, axis=0)) == len(sorted_rows)


def _hausdorff(original: np.ndarray, kept: np.ndarray) -> float:
    """One-sided Hausdorff distance, by exhaustive search -- the definition."""
    return float(
        np.linalg.norm(original[:, None, :] - kept[None, :, :], axis=2)
        .min(axis=1)
        .max()
    )


@pytest.mark.parametrize("cell", [1.5, 2.0, 3.0])
def test_max_deviation_is_the_one_sided_hausdorff_distance(cell: float) -> None:
    """The reported number must be the real maximum, measured independently.

    ``max_deviation`` is computed inside ``cluster_simplify`` from cluster
    bookkeeping; here it is measured again by brute force over the actual
    output vertices. A mean instead of a max, or a bound instead of the value,
    fails.
    """
    vertices, triangles = _grid_surface(9)
    result = cluster_simplify(vertices, triangles, cell=cell)
    assert result.max_deviation == pytest.approx(
        _hausdorff(vertices, result.vertices.astype(np.float64)), abs=1e-9
    )


def test_max_deviation_covers_a_vertex_whose_own_representative_was_dropped() -> None:
    """The case that made the first version of this number wrong.

    A cluster whose every triangle collapses keeps no representative in the
    output, so its members' distance to the surface is *not* the distance to
    their representative. Here a tiny isolated triangle 50 mm away from the
    main lattice collapses entirely; its vertices must be measured against the
    lattice, 50 mm off, not against the representative that vanished with it.
    """
    lattice, faces = _grid_surface(9)
    stray = np.array([[50.0, 0.0, 0.0], [50.2, 0.0, 0.0], [50.0, 0.2, 0.0]])
    vertices = np.vstack([lattice, stray])
    base = len(lattice)
    triangles = np.vstack([faces, [[base, base + 1, base + 2]]])

    result = cluster_simplify(vertices, triangles, cell=2.0)

    assert len(result.vertices) == 25, "the stray triangle should have collapsed"
    assert result.max_deviation == pytest.approx(
        _hausdorff(vertices, result.vertices.astype(np.float64)), abs=1e-9
    )
    assert result.max_deviation > 40.0


def test_a_surface_already_inside_the_budget_is_untouched() -> None:
    """The skin surface's path: no clustering, no error, no wasted work."""
    vertices, triangles = _grid_surface(5)
    result = simplify_to_budget(vertices, triangles, max_triangles=10_000)

    assert result.simplified is False
    assert result.rounds == 0
    assert result.cell == 0.0
    assert result.max_deviation == 0.0
    np.testing.assert_array_equal(result.triangles, triangles)
    np.testing.assert_array_equal(result.source_index, np.arange(len(vertices)))


def test_budget_loop_reaches_the_triangle_budget() -> None:
    vertices, triangles = _grid_surface(41)  # 3 200 triangles
    result = simplify_to_budget(vertices, triangles, max_triangles=400)

    assert result.simplified is True
    assert len(result.triangles) <= 400
    assert 1 <= result.rounds <= 4


def test_budget_loop_honours_the_byte_cap_too() -> None:
    """12V + 12T is what the §S3 3 MB cap actually bounds."""
    vertices, triangles = _grid_surface(41)
    cap = 12_000
    result = simplify_to_budget(
        vertices, triangles, max_triangles=100_000, max_bytes=cap
    )
    assert 12 * len(result.vertices) + 12 * len(result.triangles) <= cap


def test_clustering_is_deterministic() -> None:
    """Same mesh, same cell, same bytes -- the cache fingerprint depends on it."""
    vertices, triangles = _grid_surface(15)
    first = cluster_simplify(vertices, triangles, cell=2.5)
    second = cluster_simplify(vertices, triangles, cell=2.5)
    np.testing.assert_array_equal(first.source_index, second.source_index)
    np.testing.assert_array_equal(first.triangles, second.triangles)


@pytest.mark.parametrize("cell", [0.0, -1.0])
def test_a_nonpositive_cell_is_refused(cell: float) -> None:
    vertices, triangles = _grid_surface(3)
    with pytest.raises(ValueError, match="cell must be"):
        cluster_simplify(vertices, triangles, cell)


def test_an_unrepresentable_grid_is_refused_not_silently_wrapped() -> None:
    """int64 overflow in the flat key would scramble clusters, not raise."""
    vertices, triangles = _grid_surface(3, pitch=1000.0)
    with pytest.raises(ValueError, match="unrepresentable grid"):
        cluster_simplify(vertices, triangles, cell=1e-9)
