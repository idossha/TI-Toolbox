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
    assert np.argwhere(nib.load(previews[0]).get_fdata()).tolist() == [
        [2, 3, 4],
        [5, 6, 7],
    ]
    csv.write_text("x,y,z\n3,3,4\n")
    route.target_preview(body)
    assert len(list(tmp_path.rglob("target-*.nii"))) == 2
