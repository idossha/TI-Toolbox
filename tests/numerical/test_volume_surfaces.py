"""Real marching-cubes affine and label isolation checks on analytic fixtures."""

import numpy as np
import pytest


def test_world_affine_padding_and_distinct_labels():
    import nibabel as nib
    from tit.scene.volume_surfaces import surfaces

    data = np.zeros((8, 8, 8), dtype=np.uint8)
    data[0:2, 1:3, 2:4] = 7
    data[5:7, 5:7, 5:7] = 19
    affine = np.array(
        [[0, -2, 0.4, 10], [-3, 0, 0, 20], [0, 0, 4, -10], [0, 0, 0, 1.0]]
    )
    result = surfaces(
        nib.Nifti1Image(data, affine), {7: "Left-Hippocampus", 19: "Right-Amygdala"}, []
    )
    points = np.asarray(result["positions"]).reshape(-1, 3)
    faces = np.asarray(result["indices"]).reshape(-1, 3)
    labels = np.asarray(result["labels"])
    assert set(labels) == {7, 19}
    assert np.all(labels[faces] == labels[faces[:, :1]])
    voxels = (points - affine[:3, 3]) @ np.linalg.inv(affine[:3, :3]).T
    assert np.allclose(voxels[labels == 7].min(axis=0), [-0.5, 0.5, 1.5], atol=1e-5)
    assert np.allclose(voxels[labels == 7].max(axis=0), [1.5, 2.5, 3.5], atol=1e-5)
    for value in (7, 19):
        tris = points[faces[labels[faces[:, 0]] == value]]
        signed = (
            np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum()
            / 6
        )
        assert signed > 0


def test_selected_hidden_label_preserved_and_missing_rejected():
    import nibabel as nib
    from tit.scene.volume_surfaces import surfaces

    data = np.zeros((4, 4, 4), dtype=np.uint8)
    data[1:3, 1:3, 1:3] = 9
    image = nib.Nifti1Image(data, np.eye(4))
    assert surfaces(image, {9: "CSF"}, [])["positions"] == []
    assert set(surfaces(image, {9: "CSF"}, [9])["labels"]) == {9}
    with pytest.raises(ValueError, match="absent"):
        surfaces(image, {}, [42])
