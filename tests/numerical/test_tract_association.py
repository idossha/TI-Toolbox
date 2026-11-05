"""tit.tract endpoint association and mask selection with real scipy/nibabel (host_numerical).

Pins (2026-11-04), on toy files written here with nibabel:

* :func:`region_points` reads a FreeSurfer annotation on a GIFTI surface (names
  ``"<hemi>.<label>"``, ``unknown`` dropped) and a label volume named by the bundled
  FreeSurfer colour table (``10 -> "Left-Thalamus-Proper"``); the volume's cortex label (3) is
  dropped when an annotation supplies the cortex, and WM (2) is never a region;
* :func:`assign_endpoints` gives each endpoint the label of its nearest labelled point when
  that point is within the radius, else -1 -- the expectation is a brute-force numpy
  nearest-neighbour search, not the KD-tree;
* ``Selection(kind="through")`` keeps exactly the streamlines with a point in the mask.

Reproduce: ``.venv/bin/python -m pytest tests/numerical/test_tract_association.py -q``.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical


@pytest.fixture
def toy_subject(tmp_path):
    import nibabel as nib
    import nibabel.freesurfer as nfs

    m2m = tmp_path / "m2m_toy"
    (m2m / "surfaces").mkdir(parents=True)
    (m2m / "segmentation").mkdir()
    rng = np.random.default_rng(3)
    verts = rng.uniform(-40, 40, size=(400, 3)).astype(np.float32)
    verts[:, 0] = -np.abs(verts[:, 0]) - 20  # a left-hemisphere cloud, x < -20
    labels = (verts[:, 1] > 0).astype(np.int32) + 1  # 1 = "insula", 2 = "precentral"
    labels[:10] = 0  # "unknown"
    ctab = np.array([[25, 5, 25, 0, 0], [80, 160, 20, 0, 0], [60, 20, 220, 0, 0]])
    ctab[:, 4] = ctab[:, 0] + ctab[:, 1] * 256 + ctab[:, 2] * 65536
    nfs.write_annot(
        str(m2m / "segmentation" / "lh.toy_DK40.annot"),
        labels,
        ctab,
        [b"unknown", b"insula", b"precentral"],
    )
    gii = nib.gifti.GiftiImage(
        darrays=[nib.gifti.GiftiDataArray(verts, intent="NIFTI_INTENT_POINTSET")]
    )
    nib.save(gii, str(m2m / "surfaces" / "lh.central.gii"))
    vol = np.zeros((20, 20, 20), np.int16)
    vol[8:12, 8:12, 8:12] = 10  # Left-Thalamus-Proper
    vol[0:4, 0:4, 0:4] = 3  # cortex (replaced by the annotation)
    vol[15:, 15:, 15:] = 2  # WM: never a region
    affine = np.diag([2.0, 2.0, 2.0, 1.0])
    affine[:3, 3] = [10.0, -20.0, -20.0]
    vol_path = str(tmp_path / "labels.nii.gz")
    nib.save(nib.Nifti1Image(vol, affine), vol_path)
    return m2m, vol_path, verts, labels, vol, affine


def test_region_points_reads_annotation_and_volume(toy_subject):
    from tit.tract.network import region_points

    m2m, vol_path, verts, labels, vol, affine = toy_subject
    coords, region, names = region_points(str(m2m), vol_path, "DK40", "central")
    # resources/atlas/FreeSurferColorLUT.txt line 15: "10  Left-Thalamus-Proper"
    assert names == ["lh.insula", "lh.precentral", "Left-Thalamus-Proper"]
    np.testing.assert_allclose(coords[region == 0], verts[labels == 1])
    np.testing.assert_allclose(coords[region == 1], verts[labels == 2])
    thal = np.argwhere(vol == 10) @ affine[:3, :3].T + affine[:3, 3]
    np.testing.assert_allclose(coords[region == 2], thal)
    assert len(coords) == (labels > 0).sum() + 64


def test_assign_endpoints_matches_brute_force(toy_subject):
    from tit.tract.network import assign_endpoints, region_points

    m2m, vol_path, *_ = toy_subject
    coords, region, _ = region_points(str(m2m), vol_path)
    rng = np.random.default_rng(7)
    ends = rng.uniform(-70, 60, size=(500, 2, 3))
    got = assign_endpoints(ends, coords, region, radius=3.0)
    d = np.linalg.norm(ends.reshape(-1, 1, 3) - coords[None], axis=2)
    nearest = d.argmin(axis=1)
    expected = np.where(d.min(axis=1) <= 3.0, region[nearest], -1).reshape(500, 2)
    assert got.shape == (500, 2)
    np.testing.assert_array_equal(got, expected)
    assert (got >= 0).any() and (got == -1).any()  # both branches exercised


def test_through_selection_uses_mask_voxels(toy_subject):
    from tit.tract.config import Selection
    from tit.tract.network import select

    _, vol_path, _, _, vol, affine = toy_subject
    centre = (
        np.array([10, 10, 10]) @ affine[:3, :3].T + affine[:3, 3]
    )  # inside label 10
    far = centre + [100.0, 0, 0]
    sls = [
        np.stack([centre - [5, 0, 0], centre, centre + [5, 0, 0]]),
        np.stack([far, far + 1.0]),
        np.stack([centre + [0, 30, 0], centre + [0, 40, 0]]),
    ]
    sel = Selection(name="thal", kind="through", mask_path=vol_path, label=10)
    labels = np.full((3, 2), -1)
    got = select(sel, labels, [], np.full(3, -1), sls)
    assert got.tolist() == [True, False, False]
