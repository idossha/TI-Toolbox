"""SCI-02 -- group stacking must require a common voxel grid, not just a shape.

v2.x kept only the *first* subject's affine and never compared the others, so
images that happened to share an array shape were stacked and analysed
voxel-by-voxel even when they were translated, rotated, differently scaled, or
left/right flipped relative to each other.  Voxelwise statistics then compared
anatomically different locations across subjects, silently.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.unit

BASE = np.diag([2.0, 2.0, 2.0, 1.0])
BASE[:3, 3] = [-90.0, -126.0, -72.0]


def _variants():
    translated = BASE.copy()
    translated[:3, 3] += [0.0, 4.0, 0.0]

    theta = np.deg2rad(7.0)
    rot = np.eye(4)
    rot[:2, :2] = [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]]
    rotated = rot @ BASE

    flipped = BASE.copy()
    flipped[0, 0] *= -1.0  # handedness change: LAS vs RAS

    rescaled = BASE.copy()
    rescaled[1, 1] = 2.5

    return {
        "translation": translated,
        "rotation": rotated,
        "handedness": flipped,
        "voxel size": rescaled,
    }


@pytest.mark.parametrize("name", sorted(_variants()))
def test_mismatched_affine_is_rejected_and_names_the_subject(name):
    from tit.stats.nifti import _check_same_grid

    with pytest.raises(ValueError) as exc:
        _check_same_grid(
            "042",
            "/proj/sub-042/field.nii.gz",
            (5, 5, 5),
            _variants()[name],
            (5, 5, 5),
            BASE,
            "/proj/sub-001/field.nii.gz",
        )
    msg = str(exc.value)
    assert "042" in msg and "sub-042/field.nii.gz" in msg
    assert "sub-001/field.nii.gz" in msg


def test_handedness_flip_is_called_out_explicitly():
    from tit.stats.nifti import _check_same_grid

    with pytest.raises(ValueError, match="handedness"):
        _check_same_grid(
            "042", "b.nii", (5, 5, 5), _variants()["handedness"], (5, 5, 5), BASE, "a"
        )


def test_shape_mismatch_is_rejected():
    from tit.stats.nifti import _check_same_grid

    with pytest.raises(ValueError, match="shape"):
        _check_same_grid("042", "b.nii", (5, 5, 6), BASE, (5, 5, 5), BASE, "a")


def test_identical_and_near_identical_grids_pass():
    from tit.stats.nifti import _check_same_grid

    jitter = BASE.copy()
    jitter[:3, 3] += 1e-6  # sub-micron float noise from a round-trip
    _check_same_grid("042", "b.nii", (5, 5, 5), jitter, (5, 5, 5), BASE, "a")


def test_stacking_rejects_a_translated_subject_end_to_end(tmp_path, monkeypatch):
    """The public loader must refuse the stack, not silently keep affine #1."""
    import nibabel as nib

    import tit.stats.nifti as nifti

    files = {}
    for sub, affine in (("001", BASE), ("002", _variants()["translation"])):
        path = tmp_path / f"sub-{sub}.nii.gz"
        nib.save(nib.Nifti1Image(np.zeros((4, 4, 4), np.float32), affine), path)
        files[sub] = str(path)

    def fake_load(subject_id, simulation_name, pattern, dtype=np.float32):
        img = nib.load(files[subject_id])
        return img.get_fdata(dtype=dtype), img, files[subject_id]

    monkeypatch.setattr(nifti, "load_subject_nifti_ti_toolbox", fake_load)

    configs = [
        {"subject_id": "001", "simulation_name": "S"},
        {"subject_id": "002", "simulation_name": "S"},
    ]
    with pytest.raises(ValueError, match="002"):
        nifti.load_group_data_ti_toolbox(configs)


def test_stacking_succeeds_and_preserves_order_on_a_common_grid(
    tmp_path, monkeypatch
):
    import nibabel as nib

    import tit.stats.nifti as nifti

    files = {}
    for i, sub in enumerate(("001", "002", "003")):
        path = tmp_path / f"sub-{sub}.nii.gz"
        data = np.full((3, 3, 3), float(i + 1), np.float32)
        nib.save(nib.Nifti1Image(data, BASE), path)
        files[sub] = str(path)

    def fake_load(subject_id, simulation_name, pattern, dtype=np.float32):
        img = nib.load(files[subject_id])
        return img.get_fdata(dtype=dtype), img, files[subject_id]

    monkeypatch.setattr(nifti, "load_subject_nifti_ti_toolbox", fake_load)

    data_4d, template, ids = nifti.load_group_data_ti_toolbox(
        [{"subject_id": s, "simulation_name": "S"} for s in ("001", "002", "003")]
    )
    assert ids == ["001", "002", "003"]
    assert data_4d.shape == (3, 3, 3, 3)
    assert [float(data_4d[0, 0, 0, i]) for i in range(3)] == [1.0, 2.0, 3.0]
    assert np.allclose(template.affine, BASE)
