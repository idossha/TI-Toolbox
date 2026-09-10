"""Custom mask geometry, authored asymmetric voxel landmarks (2026-09-09).

Run with real nibabel/SimNIBS: simnibs_python -m pytest tests/numerical/test_custom_masks.py.
A translated deformation field has an analytic inverse-sampling expectation;
no expected voxel is calculated through the implementation under test.
"""

import gzip
import numpy as np
import pytest


def save(image, path):
    import nibabel as nib

    plain = str(path).removesuffix(".gz")
    nib.save(image, plain)
    if str(path).endswith(".gz"):
        with open(plain, "rb") as source, gzip.open(path, "wb") as target:
            target.write(source.read())


def test_subject_mask_is_used_without_transform_or_rewrite(tmp_path):
    import nibabel as nib
    from tit.opt.masks import prepare_mask

    data = np.zeros((5, 6, 7), dtype=np.uint8)
    data[2, 3, 4] = 5
    source = tmp_path / "mask.nii"
    nib.save(nib.Nifti1Image(data, np.diag([2, 3, 4, 1])), source)
    original = source.read_bytes()
    assert prepare_mask(
        str(source), "subject", "/missing/m2m", str(tmp_path / "out")
    ) == str(source)
    assert source.read_bytes() == original
    assert not (tmp_path / "out").exists()


def _check_mni_mask_uses_inverse_sampling_and_nearest_neighbor(tmp_path):
    import nibabel as nib

    pytest.importorskip("simnibs.utils.region_of_interest")
    from tit.opt.masks import prepare_mask

    m2m = tmp_path / "m2m_s"
    (m2m / "toMNI").mkdir(parents=True)
    shape = (5, 6, 7)
    save(nib.Nifti1Image(np.zeros(shape, dtype=np.uint8), np.eye(4)), m2m / "T1.nii.gz")
    # Every subject point x samples MNI x+1.2: MNI voxel (3,3,4) lands at subject (2,3,4).
    deformation = np.moveaxis(np.indices(shape).astype(np.float32), 0, -1)
    deformation[..., 0] += 1.2
    save(
        nib.Nifti1Image(deformation, np.eye(4)),
        m2m / "toMNI" / "Conform2MNI_nonl.nii.gz",
    )
    data = np.zeros(shape, dtype=np.uint8)
    data[3, 3, 4] = 7
    source = tmp_path / "mni.nii"
    nib.save(nib.Nifti1Image(data, np.eye(4)), source)
    output = prepare_mask(str(source), "mni", str(m2m), str(tmp_path / "out"))
    result = nib.load(output).get_fdata()
    assert np.argwhere(result > 0).tolist() == [[2, 3, 4]]
    assert result[2, 3, 4] == 7  # Linear interpolation would dilute the label.
    assert nib.load(source).get_fdata()[3, 3, 4] == 7


def test_binary_flex_mask_selects_all_positive_values_without_changing_geometry(
    tmp_path,
):
    import nibabel as nib
    from tit.opt.masks import prepare_mask

    data = np.zeros((3, 4, 5), dtype=np.float32)
    data[1, 2, 3], data[2, 1, 4], data[0, 0, 0] = 0.2, 8, -1
    affine = np.array([[2, 0.2, 0, 10], [0, 3, 0, -5], [0, 0, 4, 6], [0, 0, 0, 1]])
    source = tmp_path / "mask.nii"
    nib.save(nib.Nifti1Image(data, affine), source)
    result = nib.load(
        prepare_mask(
            str(source), "subject", "unused", str(tmp_path / "out"), binary=True
        )
    )
    assert np.argwhere(result.get_fdata() > 0).tolist() == [[1, 2, 3], [2, 1, 4]]
    np.testing.assert_allclose(result.affine, affine)
    assert set(np.unique(result.get_fdata())) == {0, 1}


@pytest.mark.parametrize("kind", ["empty", "nonfinite", "four-dimensional"])
def test_invalid_masks_fail_before_search(tmp_path, kind):
    import nibabel as nib
    from tit.opt.masks import validate_mask

    data = np.zeros(
        (2, 3, 4, 2) if kind == "four-dimensional" else (2, 3, 4), dtype=np.float32
    )
    if kind == "nonfinite":
        data[0, 0, 0] = np.nan
    path = tmp_path / "invalid.nii"
    nib.save(nib.Nifti1Image(data, np.eye(4)), path)
    with pytest.raises(ValueError):
        validate_mask(str(path))


def test_mni_mask_uses_inverse_sampling_and_nearest_neighbor(tmp_path):
    import subprocess
    import sys

    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True
    )
    if probe.returncode:
        pytest.skip("Real SimNIBS is required; run in the toolbox container")
    code = "import runpy,sys; from pathlib import Path; runpy.run_path(sys.argv[1])['_check_mni_mask_uses_inverse_sampling_and_nearest_neighbor'](Path(sys.argv[2]))"
    result = subprocess.run(
        [sys.executable, "-c", code, __file__, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("compressed", [False, True])
def test_real_nifti_upload_preserves_values_and_affine(
    tmp_path, monkeypatch, compressed
):
    import nibabel as nib
    from fastapi.testclient import TestClient
    from tit import get_path_manager
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    pm = get_path_manager(str(tmp_path))
    monkeypatch.setattr("tit.catalog.subject_ids", lambda pm: ["s"])
    source = tmp_path / "source.nii"
    data = np.zeros((3, 4, 5), dtype=np.uint8)
    data[1, 2, 3] = 9
    affine = np.diag([2, 3, 4, 1])
    nib.save(nib.Nifti1Image(data, affine), source)
    payload = source.read_bytes()
    name = "mask.nii"
    if compressed:
        payload = gzip.compress(payload)
        name += ".gz"
    with TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="test")),
        base_url="http://127.0.0.1:8765",
    ) as client:
        response = client.post(
            "/api/files/mask",
            params={"subject": "s", "name": name},
            content=payload,
            headers={"Authorization": "Bearer test"},
        )
    assert response.status_code == 201, response.text
    result = nib.load(response.json()["path"])
    np.testing.assert_array_equal(result.get_fdata(), data)
    np.testing.assert_array_equal(result.affine, affine)
