"""Framing rules for the ROI plate, on synthetic masks with known geometry.

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


def test_an_empty_mask_is_a_reported_failure_not_a_plate(tmp_path):
    plan = roi_plate.plan_framing(_grid(), AFFINE)
    assert plan.rule == "empty"
    assert plan.empty
    assert "no non-zero voxels" in plan.reason

    import nibabel as nib

    mask_path = tmp_path / "empty.nii.gz"
    nib.save(nib.Nifti1Image(_grid(), AFFINE), str(mask_path))
    out = tmp_path / "out"
    summary = roi_plate.write_roi_plate(
        mask_path=str(mask_path), m2m=str(tmp_path), out_dir=str(out), title="Nowhere"
    )

    assert summary is not None
    assert summary["image"] is None
    assert summary["cursor_rule"] == "empty"
    assert "error" in summary
    assert not (out / roi_plate.PLATE_PNG).exists()
    written = json.loads((out / roi_plate.PLATE_JSON).read_text())
    assert written["error"] == summary["error"]


# --------------------------------------------------------------------------- #
# the plate itself
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


def test_the_matplotlib_plate_and_its_sidecar_and_its_request(tmp_path, monkeypatch):
    monkeypatch.delenv(roi_plate.TETRAVOX_ENV, raising=False)
    monkeypatch.setattr(roi_plate, "tetravox_executable", lambda: None)
    mask = _box(_grid(), (40, 40, 40), (50, 50, 50))
    m2m, mask_path = _write_subject(tmp_path, mask)
    out = tmp_path / "run"

    summary = roi_plate.write_roi_plate(
        mask_path=mask_path,
        m2m=m2m,
        out_dir=str(out),
        title="Synthetic box",
        extra={"gm_overlap": 0.87},
    )

    assert summary["renderer"] == "matplotlib"
    assert summary["cursor_rule"] == "single"
    assert summary["voxels"] == 1000
    assert summary["gm_overlap"] == 0.87
    assert summary["voxels_by_region"] == {"Synthetic box": 1000}
    assert (out / roi_plate.PLATE_PNG).stat().st_size > 5000
    request = json.loads((out / f"roi_plate{roi_plate.REQUEST_SUFFIX}").read_text())
    assert request["tetravox"] is True
    assert request["png"] == roi_plate.PLATE_PNG
    assert len(request["rows"]) == 1

    job = roi_plate.build_job(request)
    assert (
        job["scene"]["files"][1] == job["scene"]["files"][-1]
    ), "fill and outline are two layers"
    zooms = [
        a["mmPerPx"]
        for a in job["actions"]
        if a.get("type") == "set" and "mmPerPx" in a
    ]
    assert len(zooms) == 3 and len(set(zooms)) == 1
    shot = [a for a in job["actions"] if a["type"] == "screenshot"][0]
    assert shot["figure"]["panels"] == ["axial", "coronal", "sagittal"]


def test_a_field_plate_carries_its_window_and_a_colour_bar(tmp_path, monkeypatch):
    import nibabel as nib

    monkeypatch.setattr(roi_plate, "tetravox_executable", lambda: None)
    mask = _box(_grid(), (40, 40, 40), (50, 50, 50))
    m2m, mask_path = _write_subject(tmp_path, mask)
    field = np.zeros(mask.shape, dtype=np.float32)
    field[mask > 0] = np.linspace(0.0, 0.4, int(mask.sum()))
    field_path = tmp_path / "TI_max.nii.gz"
    nib.save(nib.Nifti1Image(field, AFFINE), str(field_path))
    out = tmp_path / "run"

    summary = roi_plate.write_roi_plate(
        mask_path=mask_path,
        m2m=m2m,
        out_dir=str(out),
        field_path=str(field_path),
        title="Synthetic box",
    )

    assert summary["image"] == roi_plate.FIELD_PLATE_PNG
    assert summary["field"]["colormap"] == "inferno"
    assert summary["field"]["p99_9_in_roi"] == pytest.approx(0.4, abs=0.01)
    assert summary["field"]["threshold_floor"] == pytest.approx(
        roi_plate.FIELD_FLOOR_FRACTION * summary["field"]["p99_9_in_roi"]
    )
    assert (out / roi_plate.FIELD_PLATE_PNG).stat().st_size > 5000
    job = roi_plate.build_job(
        json.loads((out / f"roi_field_plate{roi_plate.REQUEST_SUFFIX}").read_text())
    )
    field_layer = [
        a
        for a in job["actions"]
        if a.get("type") == "set" and a.get("patch", {}).get("colormap") == "inferno"
    ][0]
    # `clamp` (the default) would paint a black wash over the whole T1.
    assert field_layer["patch"]["threshold"]["mode"] == "hide"


def test_a_per_region_plate_is_matplotlib_only_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(roi_plate, "tetravox_executable", lambda: None)
    mask = _grid()
    _box(mask, (20, 45, 45), (30, 55, 55))
    _box(mask, (80, 45, 45), (86, 55, 55))
    m2m, mask_path = _write_subject(tmp_path, mask)
    out = tmp_path / "run"

    summary = roi_plate.write_roi_plate(mask_path=mask_path, m2m=m2m, out_dir=str(out))

    assert summary["cursor_rule"] == "per-region"
    request = json.loads((out / f"roi_plate{roi_plate.REQUEST_SUFFIX}").read_text())
    assert request["tetravox"] is False
    assert "one cursor per row" in request["tetravox_reason"]
    assert (
        roi_plate.run_tetravox(
            out / f"roi_plate{roi_plate.REQUEST_SUFFIX}", executable="/does/not/matter"
        )
        is False
    )


def test_the_plate_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv(roi_plate.DISABLE_ENV, "1")
    m2m, mask_path = _write_subject(tmp_path, _box(_grid(), (40, 40, 40), (50, 50, 50)))
    assert (
        roi_plate.write_roi_plate(
            mask_path=mask_path, m2m=m2m, out_dir=str(tmp_path / "run")
        )
        is None
    )


# --------------------------------------------------------------------------- #
# Ernie's own labelling (env-gated, like tests/numerical/test_roi_islands.py)
# --------------------------------------------------------------------------- #

LABELING = os.environ.get("TIT_TEST_LABELING", "")


@pytest.mark.skipif(
    not LABELING, reason="set TIT_TEST_LABELING to a subject labeling.nii.gz"
)
@pytest.mark.parametrize(
    "labels,expected_rule",
    [((10,), "single"), ((10, 49), "union")],
)
def test_real_thalamus_plate(tmp_path, labels, expected_rule):
    """Left thalamus, and the Left+Right union, from a real segmentation."""
    import nibabel as nib

    monkey = os.environ.get(roi_plate.TETRAVOX_ENV)
    assert monkey is None or os.path.isfile(monkey)
    image = nib.as_closest_canonical(nib.load(LABELING))
    data = np.rint(np.squeeze(np.asarray(image.dataobj))).astype(np.int32)
    mask = np.zeros(data.shape, dtype=np.int16)
    for label in labels:
        mask[data == label] = label
    assert mask.any(), f"labels {labels} are not in {LABELING}"
    mask_path = tmp_path / "roi.nii.gz"
    nib.save(nib.Nifti1Image(mask, image.affine), str(mask_path))
    out = tmp_path / "plate"

    summary = roi_plate.write_roi_plate(
        mask_path=str(mask_path),
        m2m=os.path.dirname(os.path.dirname(LABELING)),
        out_dir=str(out),
        names={10: "Left-Thalamus", 49: "Right-Thalamus"},
        title="+".join(str(label) for label in labels),
    )

    assert summary is not None
    assert summary["cursor_rule"] == expected_rule
    assert summary["voxels"] > 1000
    assert len(summary["voxels_by_region"]) == len(labels)
    assert summary["zoom_mm_per_px"] > 0
    assert (out / summary["image"]).stat().st_size > 10000
