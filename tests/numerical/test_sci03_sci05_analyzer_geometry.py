"""SCI-03 / SCI-05 -- voxel focality units and sheared-affine geometry.

SCI-03  ``_compute_focality_metrics`` divided the summed weights by 100 in
        every case.  That is the mm^2 -> cm^2 factor of the *mesh* path; the
        voxel path feeds it mm^3 weights, where the factor to cm^3 is 1000.
        Every ``focality_*_area`` value from a voxel-space analysis in v2.x is
        therefore exactly 10x too large.

SCI-05  Voxel geometry was taken from the NIfTI header *zooms* -- the column
        norms of the affine.  For a sheared affine the voxel axes are not
        orthogonal in world space, so ``prod(zooms)`` overestimates the voxel
        volume and ``sqrt(sum (zoom_k * dv_k)^2)`` is not the world distance.
        Both must come from the affine itself: ``|det(A)|`` and ``||A dv||``.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.unit


def _sheared_affine():
    """Anisotropic voxels plus a genuine shear; deliberately not orthogonal."""
    a = np.array(
        [
            [2.0, 0.7, 0.0],
            [0.0, 1.5, 0.4],
            [0.0, 0.0, 3.0],
        ]
    )
    affine = np.eye(4)
    affine[:3, :3] = a
    affine[:3, 3] = [-10.0, 5.0, 2.0]
    return affine


# ─── SCI-05: volume from |det A|, not prod(zooms) ─────────────────────────


def test_voxel_volume_uses_determinant_not_header_zooms():
    import nibabel as nib

    from tit.analyzer.analyzer import voxel_volume_mm3

    affine = _sheared_affine()
    img = nib.Nifti1Image(np.zeros((2, 2, 2), np.float32), affine)

    zooms = np.array(img.header.get_zooms()[:3], dtype=float)
    v2_volume = float(np.prod(zooms))
    correct = float(abs(np.linalg.det(affine[:3, :3])))

    assert voxel_volume_mm3(affine) == pytest.approx(correct)
    assert correct == pytest.approx(2.0 * 1.5 * 3.0)  # upper-triangular A
    assert v2_volume > correct  # zooms overestimate under shear
    assert v2_volume / correct == pytest.approx(1.1133, abs=1e-3)  # +11.3% too large


def test_orthogonal_affine_still_agrees_with_zooms():
    from tit.analyzer.analyzer import voxel_volume_mm3

    affine = np.diag([1.0, 2.0, 3.0, 1.0])
    assert voxel_volume_mm3(affine) == pytest.approx(6.0)


def test_negative_determinant_gives_positive_volume():
    from tit.analyzer.analyzer import voxel_volume_mm3

    affine = np.diag([-2.0, 2.0, 2.0, 1.0])  # LAS storage
    assert voxel_volume_mm3(affine) == pytest.approx(8.0)


# ─── SCI-05: distance via the full affine metric ──────────────────────────


def test_world_distance_grid_matches_independently_transformed_points():
    """Reference: transform each voxel index to world coords, then subtract."""
    import nibabel as nib

    from tit.analyzer.analyzer import _world_distance_grid

    affine = _sheared_affine()
    shape = (6, 5, 4)
    centre_voxel = np.array([2.3, 1.7, 1.1])

    got = _world_distance_grid(affine, centre_voxel, shape)

    idx = np.stack(np.meshgrid(*[np.arange(s) for s in shape], indexing="ij"), -1)
    world = nib.affines.apply_affine(affine, idx.reshape(-1, 3))
    centre_world = nib.affines.apply_affine(affine, centre_voxel)
    want = np.linalg.norm(world - centre_world, axis=1).reshape(shape)

    assert np.allclose(got, want, atol=1e-9)

    zooms = np.array(nib.Nifti1Image(np.zeros(shape), affine).header.get_zooms()[:3])
    g = np.ogrid[: shape[0], : shape[1], : shape[2]]
    v2 = np.sqrt(sum(((g[k] - centre_voxel[k]) * zooms[k]) ** 2 for k in range(3)))
    assert not np.allclose(v2, want, atol=1e-6), "v2.x formula must differ under shear"


def test_world_distance_grid_reduces_to_zooms_when_orthogonal():
    from tit.analyzer.analyzer import _world_distance_grid

    affine = np.diag([1.0, 2.0, 3.0, 1.0])
    shape = (4, 4, 4)
    c = np.array([1.0, 1.0, 1.0])
    got = _world_distance_grid(affine, c, shape)
    g = np.ogrid[:4, :4, :4]
    want = np.sqrt(
        ((g[0] - 1) * 1.0) ** 2 + ((g[1] - 1) * 2.0) ** 2 + ((g[2] - 1) * 3.0) ** 2
    )
    assert np.allclose(got, want)


# ─── SCI-03: cm^2 for areas, cm^3 for volumes ─────────────────────────────


class _Bare:
    """Bind the unbound method without constructing a full Analyzer."""

    from tit.analyzer.analyzer import Analyzer

    compute = Analyzer._compute_focality_metrics


@pytest.mark.parametrize("cutoff", ["50", "75", "90", "95"])
def test_voxel_focality_volumes_are_cm3_all_cutoffs(cutoff):
    # 1000 voxels of 1 mm^3, values 1..1000 -> the 99.9th percentile is 1000.
    values = np.arange(1, 1001, dtype=float)
    weights = np.ones(1000)

    area = _Bare.compute(None, values, weights, weight_to_cm=100.0)
    vol = _Bare.compute(None, values, weights, weight_to_cm=1000.0)

    key = f"focality_{cutoff}_area"
    # n voxels >= cutoff% of 1000, each 1 mm^3
    expected_mm3 = float(np.sum(values >= float(cutoff) / 100.0 * 1000.0))
    assert vol[key] == pytest.approx(expected_mm3 / 1000.0)
    assert area[key] == pytest.approx(expected_mm3 / 100.0)
    assert area[key] / vol[key] == pytest.approx(10.0)  # the v2.x error factor


def test_anisotropic_voxels_weight_the_volume_correctly():
    values = np.array([10.0, 10.0, 1.0, 1.0])
    voxel_vol = 2.0 * 1.5 * 3.0  # 9 mm^3
    weights = np.full(4, voxel_vol)

    out = _Bare.compute(None, values, weights, weight_to_cm=1000.0)
    # 99.9th percentile is 10; the 50% cutoff (5.0) admits the two 10s.
    assert out["focality_50_area"] == pytest.approx(2 * voxel_vol / 1000.0)
    assert out["focality_95_area"] == pytest.approx(2 * voxel_vol / 1000.0)


def test_mesh_area_default_is_unchanged():
    """Mesh callers pass mm^2 and must keep the historical /100."""
    values = np.array([5.0, 5.0, 0.1])
    weights = np.array([300.0, 200.0, 50.0])
    out = _Bare.compute(None, values, weights)
    assert out["focality_50_area"] == pytest.approx(500.0 / 100.0)
