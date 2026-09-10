"""2026-09-09: target geometry on asymmetric oblique grids.

Independent expectations use scipy cKDTree Euclidean sphere selection and raw
voxel labels; real nibabel performs file IO. Run pytest tests/numerical/test_target_preview.py.
Registration delegates to existing SimNIBS; its real-data accuracy is elsewhere.
"""

from types import SimpleNamespace

import pytest


def test_sphere_union_uses_world_mm(tmp_path):
    import nibabel as nib
    import numpy as np
    from scipy.spatial import cKDTree
    from tit.scene.target_preview import target_image

    affine = np.array([[0, -2, 0.3, 10], [1.5, 0, 0, -4], [0, 0, 3, 7], [0, 0, 0, 1.0]])
    shape = (7, 9, 5)
    path = tmp_path / "T1.nii"
    nib.save(nib.Nifti1Image(np.zeros(shape), affine), path)
    spheres = [
        SimpleNamespace(center=[6, 0, 10], radius=4),
        SimpleNamespace(center=[-2, 3, 15], radius=3),
    ]
    roi = SimpleNamespace(kind="spherical", space="subject", spheres=spheres)
    image = target_image(path, roi, tmp_path, tmp_path)
    # Independent spatial query; avoids reusing production's squared-distance code.
    points = nib.affines.apply_affine(affine, np.indices(shape).reshape(3, -1).T)
    tree = cKDTree(points)
    selected = set()
    for sphere in spheres:
        selected.update(tree.query_ball_point(sphere.center, sphere.radius))
    assert selected
    actual = set(np.flatnonzero(image.get_fdata()))
    assert actual == selected
    np.testing.assert_allclose(image.affine, affine)


@pytest.mark.parametrize("kind", ["mask", "subcortical"])
def test_only_selected_voxels_reach_subject_grid(tmp_path, kind):
    import nibabel as nib
    import numpy as np
    from tit.scene.target_preview import target_image

    shape = (5, 7, 9)
    affine = np.diag([2.0, 3.0, 4.0, 1.0])
    anatomy = tmp_path / "T1.nii"
    source = tmp_path / "target.nii"
    nib.save(nib.Nifti1Image(np.zeros(shape), affine), anatomy)
    values = np.zeros(shape)
    values[1, 3, 5] = 17
    values[3, 2, 1] = -2 if kind == "mask" else 18
    nib.save(nib.Nifti1Image(values, affine), source)
    roi = SimpleNamespace(kind=kind, space="subject", labels=[17])
    image = target_image(anatomy, roi, tmp_path, tmp_path, source)
    assert np.argwhere(image.get_fdata()).tolist() == [[1, 3, 5]]
    assert set(np.unique(image.get_fdata())) == {0, 1}


def test_nonoverlapping_sphere_is_unavailable(tmp_path):
    import nibabel as nib
    import numpy as np
    from tit.scene.target_preview import target_image

    path = tmp_path / "T1.nii"
    nib.save(nib.Nifti1Image(np.zeros((3, 4, 5)), np.eye(4)), path)
    roi = SimpleNamespace(
        kind="spherical",
        space="subject",
        spheres=[SimpleNamespace(center=[900, 0, 0], radius=2)],
    )
    with pytest.raises(ValueError, match="does not overlap"):
        target_image(path, roi, tmp_path, tmp_path)


def test_route_scene_binary_overlay_and_cache(tmp_path, monkeypatch):
    import json
    from pathlib import Path
    import jsonschema
    import nibabel as nib
    import numpy as np
    from tit.server.routes import target_preview as route

    anatomy = tmp_path / "T1.nii"
    nib.save(nib.Nifti1Image(np.zeros((5, 7, 9)), np.eye(4)), anatomy)
    pm = SimpleNamespace(
        project_dir=str(tmp_path), t1=lambda sid: anatomy, m2m=lambda sid: tmp_path
    )
    monkeypatch.setattr(route, "get_path_manager", lambda: pm)
    monkeypatch.setattr(route.catalog, "subject_ids", lambda pm: ["sample"])
    body = route.TargetPreviewRequest.model_validate(
        {
            "subject": "sample",
            "roi": {
                "kind": "spherical",
                "space": "subject",
                "spheres": [{"center": [2, 3, 4], "radius": 1}],
            },
        }
    )
    response = route.target_preview(body)
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts/tetravox-viewspec-v2.schema.json"
        ).read_text()
    )
    jsonschema.validate(response["scene"], schema)
    target = response["scene"]["layers"][1]
    assert target["threshold"]["lo"] == 0.5
    assert target["scale"] == {"kind": "linear", "lo": 0, "hi": 1}
    assert target["colormap"] == "turbo"
    assert target["interpolation"] == "nearest"
    assert all(not layer["pickable"] for layer in response["scene"]["layers"])
    previews = list(tmp_path.rglob("target-*.nii"))
    assert len(previews) == 1
    before = previews[0].stat().st_mtime_ns

    def forbidden_lock(*args):
        raise AssertionError("Warm preview waited for the subject build lock")

    monkeypatch.setattr(route.cache, "subject_lock", forbidden_lock)
    assert route.target_preview(body)["scene"] == response["scene"]
    assert previews[0].stat().st_mtime_ns == before


def test_mni_sphere_transforms_center_and_preserves_radius(tmp_path, monkeypatch):
    import nibabel as nib
    import numpy as np
    import simnibs
    from tit.scene.target_preview import target_image

    path = tmp_path / "T1.nii"
    nib.save(nib.Nifti1Image(np.zeros((7, 8, 9)), np.eye(4)), path)
    calls = []

    def transform(centers, m2m):
        calls.append((centers.tolist(), m2m))
        return [[3, 4, 5]]

    monkeypatch.setattr(simnibs, "mni2subject_coords", transform)
    roi = SimpleNamespace(
        kind="spherical",
        space="mni",
        spheres=[SimpleNamespace(center=[40, 50, 60], radius=1)],
    )
    image = target_image(path, roi, tmp_path, tmp_path)
    # Unit-radius sphere on a unit grid: center plus six axial neighbours.
    expected = {
        (3, 4, 5),
        (2, 4, 5),
        (4, 4, 5),
        (3, 3, 5),
        (3, 5, 5),
        (3, 4, 4),
        (3, 4, 6),
    }
    assert set(map(tuple, np.argwhere(image.get_fdata()))) == expected
    assert calls == [([[40.0, 50.0, 60.0]], str(tmp_path))]


def test_saved_centers_union_and_csv_cache_invalidation(tmp_path, monkeypatch):
    import nibabel as nib
    import numpy as np
    from tit.server.routes import target_preview as route

    anatomy = tmp_path / "T1.nii"
    nib.save(nib.Nifti1Image(np.zeros((8, 9, 10)), np.eye(4)), anatomy)
    csv = tmp_path / "first.csv"
    csv.write_text("x,y,z\n2,3,4\n")
    (tmp_path / "second.csv").write_text("5,6,7\n")
    pm = SimpleNamespace(
        project_dir=str(tmp_path),
        t1=lambda sid: anatomy,
        m2m=lambda sid: tmp_path,
        rois=lambda sid: tmp_path,
    )
    monkeypatch.setattr(route, "get_path_manager", lambda: pm)
    monkeypatch.setattr(route.catalog, "subject_ids", lambda pm: ["sample"])
    body = route.TargetPreviewRequest.model_validate(
        {
            "subject": "sample",
            "roi": {
                "kind": "saved",
                "space": "subject",
                "names": ["first", "second.csv"],
                "radius": 0.4,
            },
        }
    )
    route.target_preview(body)
    previews = list(tmp_path.rglob("target-*.nii"))
    assert len(previews) == 1
    cached = nib.load(previews[0])
    assert nib.affines.apply_affine(
        cached.affine, np.argwhere(cached.get_fdata())
    ).tolist() == [
        [2, 3, 4],
        [5, 6, 7],
    ]
    csv.write_text("x,y,z\n3,3,4\n")
    route.target_preview(body)
    assert len(list(tmp_path.rglob("target-*.nii"))) == 2


def test_preview_anatomy_preserves_sample_world_coordinates(tmp_path):
    """Only this case catches stride scaling that drops shear or translation."""
    import nibabel as nib
    import numpy as np
    from tit.scene.target_preview import preview_anatomy

    shape = (199, 11, 7)
    affine = np.array([[1, 0.2, 0, -12], [0, 2, 0.5, 8], [0, 0, 3, -3], [0, 0, 0, 1.0]])
    data = np.indices(shape)[0].astype(np.float32)
    path = tmp_path / "T1.nii"
    nib.save(nib.Nifti1Image(data, affine), path)
    result = preview_anatomy(path)
    assert result.shape == (100, 11, 7)
    np.testing.assert_array_equal(result.get_fdata(), data[::2])
    # Source voxel (198, 5, 4) and preview voxel (99, 5, 4) are the same sample.
    np.testing.assert_allclose(result.affine @ [99, 5, 4, 1], affine @ [198, 5, 4, 1])
    np.testing.assert_array_equal(nib.load(path).get_fdata(), data)


def test_crop_target_preserves_world_selection():
    """Only this case catches a cropped overlay retaining its old origin."""
    import nibabel as nib
    import numpy as np
    from tit.scene.target_preview import crop_target

    affine = np.array([[0, -2, 0.3, 10], [1.5, 0, 0, -4], [0, 0, 3, 7], [0, 0, 0, 1.0]])
    data = np.zeros((13, 17, 19), dtype=np.uint8)
    selected = np.array([[3, 5, 7], [4, 6, 9]])
    data[tuple(selected.T)] = 1
    result = crop_target(nib.Nifti1Image(data, affine))
    assert result.shape == (4, 4, 5)
    expected = nib.affines.apply_affine(affine, selected)
    actual = nib.affines.apply_affine(result.affine, np.argwhere(result.get_fdata()))
    np.testing.assert_allclose(actual, expected)


def test_route_reuses_anatomy_for_changed_target(tmp_path, monkeypatch):
    """Changed ROI geometry must not reread or republish the subject anatomy."""
    import nibabel as nib
    import numpy as np
    from tit.server.routes import target_preview as route
    from tit.scene import target_preview as geometry

    anatomy = tmp_path / "T1.nii"
    nib.save(nib.Nifti1Image(np.zeros((9, 11, 13)), np.eye(4)), anatomy)
    pm = SimpleNamespace(
        project_dir=str(tmp_path), t1=lambda sid: anatomy, m2m=lambda sid: tmp_path
    )
    monkeypatch.setattr(route, "get_path_manager", lambda: pm)
    monkeypatch.setattr(route.catalog, "subject_ids", lambda pm: ["sample"])
    body = route.TargetPreviewRequest(
        subject="sample",
        roi=route.SphereTarget(
            kind="spherical",
            space="subject",
            spheres=[route.PreviewSphere(center=(4, 5, 6), radius=1)],
        ),
    )
    route.target_preview(body)

    def forbidden(*args):
        raise AssertionError("Cached anatomy was regenerated")

    monkeypatch.setattr(geometry, "preview_anatomy", forbidden)
    body.roi.spheres[0].radius = 2
    route.target_preview(body)
    assert len(list(tmp_path.rglob("preview-anatomy-*.nii"))) == 1
    assert len(list(tmp_path.rglob("target-*.nii"))) == 2


def _run_with_real_simnibs(test_name):
    """Preload SimNIBS in a child before the host conftest installs its mocks."""
    import os
    from pathlib import Path
    import subprocess
    import sys

    if os.environ.get("TIT_REAL_PREVIEW_TEST") == test_name:
        return False
    code = (
        "import importlib.util,sys; "
        "sys.exit(77) if importlib.util.find_spec('simnibs') is None else None; "
        "import simnibs,pytest; "
        f"sys.exit(pytest.main([{str(Path(__file__).resolve())!r}, '-q', '-k', {test_name!r}]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "TIT_REAL_PREVIEW_TEST": test_name},
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 77:
        pytest.skip("real SimNIBS is unavailable; run in the SimNIBS container")
    assert result.returncode == 0, result.stdout + result.stderr
    return True


def test_compact_mni_warp_and_nearest_mask_alignment(tmp_path, monkeypatch):
    """An authored translation pins deformation direction and nearest-label lookup."""
    if _run_with_real_simnibs("test_compact_mni_warp_and_nearest_mask_alignment"):
        return
    import nibabel as nib
    import numpy as np
    from simnibs.utils import file_finder
    from tit.scene.target_preview import preview_deformation, target_image

    warp_affine = np.eye(4)
    warp_affine[:3, 3] = 10
    # Authored subject-to-MNI map: MNI = subject + (3, -2, 1) mm.
    indices = np.indices((14, 18, 22)).transpose(1, 2, 3, 0)
    coordinates = (indices + 10 + [3, -2, 1]).astype(np.float32)
    warp = tmp_path / "warp.nii"
    nib.save(nib.Nifti1Image(coordinates, warp_affine), warp)
    monkeypatch.setattr(
        file_finder,
        "SubjectFiles",
        lambda **kwargs: SimpleNamespace(conf2mni_nonl=str(warp)),
    )
    affine = np.diag([2.0, 2.0, 2.0, 1.0])
    affine[:3, 3] = 10
    anatomy = tmp_path / "anatomy.nii"
    nib.save(nib.Nifti1Image(np.zeros((7, 9, 11)), affine), anatomy)
    compact = preview_deformation(tmp_path, anatomy)
    np.testing.assert_allclose(compact.get_fdata()[2, 3, 4], [17, 14, 19])
    compact_path = tmp_path / "compact.nii"
    nib.save(compact, compact_path)
    mask = np.zeros((40, 40, 40), dtype=np.uint8)
    mask[17, 14, 19] = 1
    source = tmp_path / "mask.nii"
    nib.save(nib.Nifti1Image(mask, np.eye(4)), source)
    roi = SimpleNamespace(kind="mask", space="mni")
    result = target_image(anatomy, roi, tmp_path, tmp_path, source, compact_path)
    assert np.argwhere(result.get_fdata()).tolist() == [[2, 3, 4]]
    np.testing.assert_allclose(result.affine, affine)
    # A positive target falling between display samples must explain this limit.
    mask[17, 14, 19] = 0
    mask[18, 14, 19] = 1
    nib.save(nib.Nifti1Image(mask, np.eye(4)), source)
    with pytest.raises(ValueError, match="too small for the lightweight preview grid"):
        target_image(anatomy, roi, tmp_path, tmp_path, source, compact_path)


def test_route_reuses_warp_and_invalidates_changed_registration(tmp_path, monkeypatch):
    """ROI changes reuse a warp; registration changes must never reuse it."""
    if _run_with_real_simnibs(
        "test_route_reuses_warp_and_invalidates_changed_registration"
    ):
        return
    import nibabel as nib
    import numpy as np
    from tit.server.routes import target_preview as route
    from tit.scene import target_preview as geometry

    anatomy = tmp_path / "T1.nii"
    nib.save(nib.Nifti1Image(np.zeros((7, 9, 11)), np.eye(4)), anatomy)
    registration = tmp_path / "toMNI"
    registration.mkdir()
    transform = registration / "transform.nii"
    transform.write_bytes(b"registration-v1")
    source = tmp_path / "source.nii"
    data = np.zeros((30, 30, 30), dtype=np.uint8)
    data[12:15, 12:15, 12:15] = 1
    nib.save(nib.Nifti1Image(data, np.eye(4)), source)
    pm = SimpleNamespace(
        project_dir=str(tmp_path), t1=lambda sid: anatomy, m2m=lambda sid: tmp_path
    )
    monkeypatch.setattr(route, "get_path_manager", lambda: pm)
    monkeypatch.setattr(route.catalog, "subject_ids", lambda pm: ["sample"])
    calls = []

    def warp(*args):
        calls.append(args)
        values = (np.indices((7, 9, 11)).transpose(1, 2, 3, 0) + 10).astype(np.float32)
        return nib.Nifti1Image(values, np.eye(4))

    monkeypatch.setattr(geometry, "preview_deformation", warp)
    body = route.TargetPreviewRequest(
        subject="sample",
        roi=route.MaskTarget(kind="mask", path=str(source), space="mni"),
    )
    route.target_preview(body)
    data[15, 15, 15] = 1
    nib.save(nib.Nifti1Image(data, np.eye(4)), source)
    route.target_preview(body)
    assert len(calls) == 1
    transform.write_bytes(b"changed-registration-v2")
    route.target_preview(body)
    assert len(calls) == 2
