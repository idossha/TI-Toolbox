"""Framing rules for the ROI scene, on synthetic masks with known geometry.

Real libraries only (``tests/numerical``): the host suite mocks nibabel and
scipy, and every assertion here is about what those two actually compute.

The expected numbers are geometry, not a second copy of the implementation: a
box from voxel 10 to 19 on a 1 mm grid whose affine puts voxel 0 at −50 mm has
its centroid at −35.5 mm and its edges at −40 and −30, and that is what is
asserted.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tit.figures import roi_plate  # noqa: E402

AFFINE = np.array(
    [[1.0, 0, 0, -50.0], [0, 1.0, 0, -50.0], [0, 0, 1.0, -50.0], [0, 0, 0, 1.0]]
)


def _grid():
    return np.zeros((100, 100, 100), dtype=np.int16)


def _box(mask, lo, hi, value=1):
    mask[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]] = value
    return mask


def _sphere(mask, centre_vox, radius_vox, value=1):
    grid = np.indices(mask.shape).astype(float)
    distance = np.sqrt(sum((grid[i] - centre_vox[i]) ** 2 for i in range(3)))
    mask[distance <= radius_vox] = value
    return mask


# --------------------------------------------------------------------------- #
# single
# --------------------------------------------------------------------------- #


def test_single_region_puts_the_cursor_on_the_centroid_and_fills_the_panel():
    mask = _box(_grid(), (40, 40, 40), (50, 50, 50))
    plan = roi_plate.plan_framing(mask, AFFINE)

    assert plan.rule == "single"
    assert len(plan.rows) == 1
    # Voxels 40..49 on a 1 mm grid with origin -50 -> centres -10..-1, mean -5.5.
    assert plan.cursor_ras == pytest.approx([-5.5, -5.5, -5.5], abs=0.51)
    region = plan.regions[0]
    assert region.voxels == 1000
    assert region.bbox_min_ras == pytest.approx([-10.5] * 3)
    assert region.bbox_max_ras == pytest.approx([-0.5] * 3)
    # A 10 mm box at 60 % of the panel, with 4 mm of margin on each side:
    # the binding axis is the vertical one (10 / 0.75), so 13.33 / 0.6 + 8.
    assert plan.rows[0].width_mm == pytest.approx(10.0 / 0.75 / 0.6 + 8.0)


def test_the_roi_actually_fills_about_sixty_percent_of_the_panel():
    mask = _box(_grid(), (40, 40, 40), (70, 45, 45))
    row = roi_plate.plan_framing(mask, AFFINE).rows[0]
    # Axial draws x across: a 30 mm span in a view this wide.
    assert 30.0 / row.width_mm == pytest.approx(0.60, abs=0.15)


def test_a_c_shaped_region_snaps_the_cursor_into_the_mask():
    """A C's centroid is in its hollow; the rule must still land on a voxel."""
    mask = _grid()
    _box(mask, (40, 40, 40), (60, 60, 45))  # the full block
    mask[45:60, 45:55, 40:45] = 0  # bitten out from one side -> a C
    plan = roi_plate.plan_framing(mask, AFFINE)

    assert plan.rule == "single"
    region = plan.regions[0]
    centroid_voxel = np.round(
        np.linalg.inv(AFFINE) @ np.array(region.centroid_ras + [1.0])
    ).astype(int)[:3]
    assert (
        mask[tuple(centroid_voxel)] == 0
    ), "the centroid must be outside, or this proves nothing"
    cursor_voxel = np.round(
        np.linalg.inv(AFFINE) @ np.array(region.cursor_ras + [1.0])
    ).astype(int)[:3]
    assert mask[tuple(cursor_voxel)] > 0


# --------------------------------------------------------------------------- #
# union vs per-region
# --------------------------------------------------------------------------- #


def test_bilateral_regions_within_the_span_limit_share_one_row():
    mask = _grid()
    _box(mask, (40, 45, 45), (48, 55, 55))  # left, 4000 voxels
    _box(mask, (52, 45, 45), (58, 55, 55))  # right, 3000 voxels
    plan = roi_plate.plan_framing(mask, AFFINE)

    assert plan.rule == "union"
    assert len(plan.rows) == 1
    assert [r.voxels for r in plan.regions] == [800, 600]  # largest first
    # The cursor snaps into the LARGEST region, not into whichever is nearest
    # the midpoint between them.
    cursor_voxel = np.round(
        np.linalg.inv(AFFINE) @ np.array(plan.cursor_ras + [1.0])
    ).astype(int)[:3]
    assert cursor_voxel[0] < 50
    assert mask[tuple(cursor_voxel)] > 0


def test_regions_further_apart_than_the_span_limit_get_one_row_each():
    mask = _grid()
    _box(mask, (20, 45, 45), (30, 55, 55))
    _box(mask, (80, 48, 48), (86, 52, 52))  # smaller, so it earns its own zoom
    span = 66.0  # -30 .. +36 in world mm, comfortably over the 60 mm limit
    assert span > roi_plate.SPAN_LIMIT_MM
    plan = roi_plate.plan_framing(mask, AFFINE)

    assert plan.rule == "per-region"
    assert len(plan.rows) == 2
    assert plan.rows[0].regions[0].voxels > plan.rows[1].regions[0].voxels
    # Each row has its own cursor and its own zoom.
    assert plan.rows[0].cursor_ras != plan.rows[1].cursor_ras
    assert plan.rows[0].width_mm != plan.rows[1].width_mm
    assert "voxels" in plan.rows[0].label


def test_more_than_four_components_keep_four_rows_and_count_the_rest():
    mask = _grid()
    for index in range(6):
        start = 5 + index * 15
        _box(mask, (start, 45, 45), (start + 4 + index, 55, 55))
    plan = roi_plate.plan_framing(mask, AFFINE)

    assert plan.rule == "per-region"
    assert len(plan.rows) == roi_plate.MAX_ROWS
    assert len(plan.omitted_regions) == 2


def test_distinct_labels_get_distinct_fills_green_first():
    mask = _grid()
    _box(mask, (40, 45, 45), (48, 55, 55), value=10)
    _box(mask, (52, 45, 45), (58, 55, 55), value=49)
    plan = roi_plate.plan_framing(
        mask, AFFINE, names={10: "Left-Thalamus", 49: "Right-Thalamus"}
    )

    assert plan.rule == "union"
    assert [r.name for r in plan.regions] == ["Left-Thalamus", "Right-Thalamus"]
    assert [r.value for r in plan.regions] == [10, 49]
    assert plan.regions[0].color == roi_plate.PALETTE[0]
    assert plan.regions[1].color == roi_plate.PALETTE[1]
    assert plan.regions[0].color != plan.regions[1].color


# --------------------------------------------------------------------------- #
# spheres
# --------------------------------------------------------------------------- #


def test_a_sphere_takes_its_centre_and_its_radius_not_its_rasterisation():
    mask = _sphere(_grid(), (60, 50, 40), 6)
    plan = roi_plate.plan_framing(mask, AFFINE, spheres=[([10.0, 0.0, -10.0], 6.0)])

    assert plan.rule == "sphere"
    assert plan.cursor_ras == pytest.approx([10.0, 0.0, -10.0])
    region = plan.regions[0]
    assert region.bbox_min_ras == pytest.approx([4.0, -6.0, -16.0])
    assert region.bbox_max_ras == pytest.approx([16.0, 6.0, -4.0])
    assert plan.rows[0].width_mm == pytest.approx(12.0 / 0.75 / 0.6 + 8.0)


def test_two_spheres_follow_the_multi_region_rule():
    mask = _grid()
    _sphere(mask, (40, 50, 50), 5)
    _sphere(mask, (60, 50, 50), 5)
    plan = roi_plate.plan_framing(
        mask, AFFINE, spheres=[([-10.0, 0.0, 0.0], 5.0), ([10.0, 0.0, 0.0], 5.0)]
    )

    assert plan.rule == "union"
    assert len(plan.regions) == 2
    assert {tuple(r.cursor_ras) for r in plan.regions} == {
        (-10.0, 0.0, 0.0),
        (10.0, 0.0, 0.0),
    }


# --------------------------------------------------------------------------- #
# empty
# --------------------------------------------------------------------------- #


def test_an_empty_mask_is_a_reported_failure_not_a_scene(tmp_path):
    plan = roi_plate.plan_framing(_grid(), AFFINE)
    assert plan.rule == "empty"
    assert plan.empty
    assert "no non-zero voxels" in plan.reason

    out = tmp_path / "out"
    assert (
        roi_plate.write_roi_scene(
            out_dir=str(out),
            anatomy=str(tmp_path / "T1.nii.gz"),
            roi_layers=[],
            plan=plan,
            meta={},
            title="Nowhere",
        )
        is None
    )
    # No scene, and nothing else either: an empty transform is a failure to read
    # in the terminal, not a directory of files describing nothing.
    assert list(out.iterdir()) == []


# --------------------------------------------------------------------------- #
# a cortical target is framed from its vertices, with no rasterisation
# --------------------------------------------------------------------------- #


def test_a_cortical_target_is_framed_from_its_surface_vertices():
    rng = np.random.default_rng(0)
    patch = rng.uniform(-5.0, 5.0, size=(400, 3)) + np.array([20.0, -30.0, 40.0])
    plan = roi_plate.plan_surface([patch], names=["lh.superiorfrontal"])

    assert plan.rule == "single"
    assert plan.regions[0].name == "lh.superiorfrontal"
    assert plan.regions[0].voxels == 400
    # The cursor is one of the vertices, never a point invented between them.
    assert any(np.allclose(plan.cursor_ras, vertex) for vertex in patch)
    assert plan.rows[0].mm_per_px > 0


def test_two_hemispheres_of_a_cortical_target_share_one_framing():
    rng = np.random.default_rng(1)
    left = rng.uniform(-4.0, 4.0, size=(200, 3)) + np.array([-15.0, 0.0, 30.0])
    right = rng.uniform(-4.0, 4.0, size=(200, 3)) + np.array([15.0, 0.0, 30.0])
    plan = roi_plate.plan_surface([left, right], names=["lh.x", "rh.x"])

    assert plan.rule == "union"
    assert plan.regions[0].color != plan.regions[1].color


def test_a_sphere_is_framed_on_the_centre_and_radius_that_were_typed():
    plan = roi_plate.plan_spheres([((10.0, -20.0, 30.0), 8.0)], names=["target"])

    assert plan.rule == "sphere"
    assert plan.cursor_ras == pytest.approx([10.0, -20.0, 30.0])
    # 16 mm across; the binding axis is the panel's short one (aspect 0.75), so
    # the view is 16/0.75 mm tall at 60 % fill, plus 4 mm of margin on each side.
    assert plan.rows[0].width_mm == pytest.approx((16.0 / 0.75) / 0.6 + 8.0, abs=0.01)


# --------------------------------------------------------------------------- #
# the scene itself
# --------------------------------------------------------------------------- #


def _write_subject(tmp_path, mask):
    import nibabel as nib

    m2m = tmp_path / "m2m_synthetic"
    m2m.mkdir()
    rng = np.random.default_rng(0)
    nib.save(
        nib.Nifti1Image(rng.uniform(0, 500, mask.shape).astype(np.float32), AFFINE),
        str(m2m / "T1.nii.gz"),
    )
    mask_path = tmp_path / "roi.nii.gz"
    nib.save(nib.Nifti1Image(mask, AFFINE), str(mask_path))
    return str(m2m), str(mask_path)


def test_the_scene_is_one_file_that_references_only_files_that_exist(tmp_path):
    mask = _box(_grid(), (40, 40, 40), (50, 50, 50))
    m2m, mask_path = _write_subject(tmp_path, mask)
    out = tmp_path / "run"
    plan = roi_plate.plan_framing(mask, AFFINE, names=["Synthetic box"])

    meta = roi_plate.write_roi_scene(
        out_dir=str(out),
        anatomy=f"{m2m}/T1.nii.gz",
        roi_layers=[{"kind": "volume", "path": mask_path, "labels": {1: "#4caf50"}}],
        plan=plan,
        meta={"roi": "Synthetic box", "voxels": 1000, "gm_overlap": 0.87},
        title="Synthetic box",
    )

    assert meta["voxels"] == 1000
    assert [p.name for p in out.iterdir()] == [roi_plate.SCENE_NAME]

    scene = json.loads((out / roi_plate.SCENE_NAME).read_text())
    assert scene["version"] == 2
    for dataset in scene["datasets"]:
        assert (out / dataset["path"]).resolve().is_file()
    assert scene["meta"]["gm_overlap"] == 0.87
    # Fill under outline, two layers over one dataset (a VolumeLayer has one
    # opacity and one labelMode, so 40 % under an opaque edge needs two).
    roi_ids = [la["datasetId"] for la in scene["layers"] if la["datasetId"] == "ds1"]
    assert roi_ids == ["ds1", "ds1"]
    fill, outline = [la for la in scene["layers"] if la["datasetId"] == "ds1"]
    assert (fill["opacity"], fill["labelMode"]) == (0.4, "fill")
    assert (outline["opacity"], outline["labelMode"]) == (1.0, "outline")
    assert scene["layers"][-1] is outline, "the outline stays on top"


def test_the_camera_centres_the_roi_and_the_zoom_fills_the_panel(tmp_path):
    # A box far from the volume's centre: the in-plane offset is what proves the
    # ROI is centred rather than the head.
    mask = _box(_grid(), (10, 10, 10), (20, 20, 20))
    m2m, mask_path = _write_subject(tmp_path, mask)
    out = tmp_path / "run"
    plan = roi_plate.plan_framing(mask, AFFINE)

    roi_plate.write_roi_scene(
        out_dir=str(out),
        anatomy=f"{m2m}/T1.nii.gz",
        roi_layers=[{"kind": "volume", "path": mask_path, "labels": {1: "#4caf50"}}],
        plan=plan,
        meta={},
    )
    scene = json.loads((out / roi_plate.SCENE_NAME).read_text())

    # The T1 spans -50.5..49.5 mm, so its centre is -0.5; the cursor is at -35.5.
    axial = [s for s in scene["slices"] if s["id"] == "axial"][0]
    assert axial["camera"]["center"] == pytest.approx([-35.0, -35.0], abs=0.6)
    # Sagittal draws (y, z) with anterior to the left: right = -y.
    sagittal = [s for s in scene["slices"] if s["id"] == "sagittal"][0]
    assert sagittal["camera"]["center"] == pytest.approx([35.0, -35.0], abs=0.6)
    assert axial["camera"]["mmPerPx"] == pytest.approx(plan.rows[0].mm_per_px, rel=1e-4)


def test_a_cortical_scene_attaches_the_annot_to_the_surface(tmp_path):
    surfaces = tmp_path / "m2m" / "surfaces"
    surfaces.mkdir(parents=True)
    (surfaces / "lh.central.gii").write_bytes(b"")
    segmentation = tmp_path / "m2m" / "segmentation"
    segmentation.mkdir()
    annot = segmentation / "lh.sub_DK40.annot"
    annot.write_bytes(b"")
    m2m, _ = _write_subject(tmp_path, _box(_grid(), (40, 40, 40), (50, 50, 50)))
    plan = roi_plate.plan_surface(
        [np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])], names=["lh.cuneus"]
    )

    roi_plate.write_roi_scene(
        out_dir=str(tmp_path / "run"),
        anatomy=f"{m2m}/T1.nii.gz",
        roi_layers=[
            {
                "kind": "surface",
                "path": str(surfaces / "lh.central.gii"),
                "annot": str(annot),
                "labels": {5: "#4caf50"},
            }
        ],
        plan=plan,
        meta={},
    )
    scene = json.loads((tmp_path / "run" / roi_plate.SCENE_NAME).read_text())
    surface = scene["datasets"][1]
    assert surface["kind"] == "surface"
    # Relative to the *surface's* own directory -- the one path in a scene that
    # is never re-rooted, so it survives host and container alike.
    assert surface["sidecars"]["fields"] == [{"path": "../segmentation/lh.sub_DK40.annot"}]
    layer = scene["layers"][1]
    assert layer["kind"] == "surface"
    assert layer["colorMode"] == "annotation"
    assert layer["annotation"]["name"] == "lh.sub_DK40.annot"
    assert layer["annotation"]["visibleLabels"] == [5]


def test_the_scene_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv(roi_plate.DISABLE_ENV, "1")
    m2m, mask_path = _write_subject(tmp_path, _box(_grid(), (40, 40, 40), (50, 50, 50)))
    assert (
        roi_plate.write_roi_scene(
            out_dir=str(tmp_path / "run"),
            anatomy=f"{m2m}/T1.nii.gz",
            roi_layers=[],
            plan=roi_plate.plan_framing(_box(_grid(), (40, 40, 40), (50, 50, 50)), AFFINE),
            meta={},
        )
        is None
    )
    assert not (tmp_path / "run").exists()
