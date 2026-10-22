"""Tissue analysis measures anatomy, not storage order, with real nibabel and scipy.

The head is authored in world space, so every expected value comes from its geometry and
not from ``tit.pre.tissue_analyzer``: concentric spheres around the head centre give a
brain (labels 3 left / 42 right, brainstem 16) of radius 30 mm, then shells of CSF (label 24)
4 mm thick, bone (515) 6 mm thick and skin (511) 3 mm thick, plus a bone "vertebra" below
the head so superior and inferior are not mirror images. The analysis box (brain
bounding box plus each tissue's padding) never cuts these shells, so the only voxels the
filter may drop are those inferior to ``brain centre - padding``: a count taken here straight
from the world z coordinate.

Dataset 000's sub-ernie T1 and ``final_tissues.nii.gz`` are stored ('P', 'S', 'R'), so the
same head is also saved in that order (and flipped to ('L', 'P', 'I')) with the matching
affine; the results must not change. ``tests/test_pre_tissue.py`` covers the same code with
nibabel and scipy mocked, which can say nothing about these numbers.

Host (real numpy/scipy/nibabel, matplotlib mocked)::

    .venv/bin/python -m pytest tests/numerical/test_tissue_geometry.py -q -p no:cacheprovider

The figure test needs real matplotlib, so it runs in the image only.
"""

from __future__ import annotations

import logging
import re
from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical

#: Radii of the authored head, mm (brain < 30 <= CSF < 34 <= bone < 40 <= skin < 43).
BRAIN_R, CSF_R, BONE_R, SKIN_R = 30.0, 34.0, 40.0, 43.0
THICKNESS_MM = {"csf": CSF_R - BRAIN_R, "bone": BONE_R - CSF_R, "skin": SKIN_R - BONE_R}
LABEL = {"csf": 24, "bone": 515, "skin": 511}
#: TISSUE_CONFIGS padding (voxels) per tissue, the documented filter parameter.
PADDING = {"csf": 40, "bone": 30, "skin": 35}


@pytest.fixture(scope="module")
def ta():
    """``tit.pre.tissue_analyzer`` bound to the real nibabel and scipy for this module.

    The module imports both at load time, and the host suite loads it with the mocks;
    the numerical conftest swaps the real packages into ``sys.modules`` but reloads only
    ``tit.stats``. Rebinding the two names (and putting them back) leaves the module as
    the rest of the session expects it.
    """
    import nibabel
    from scipy import ndimage

    import tit.pre.tissue_analyzer as module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(module, "nib", nibabel)
        mp.setattr(module, "ndimage", ndimage)
        yield module


def _head(shape, zooms, centre_index):
    """Label volume of the authored head on a RAS grid; returns (labels, affine, world)."""
    zooms = np.asarray(zooms, dtype=float)
    affine = np.diag([*zooms, 1.0])
    affine[:3, 3] = -np.asarray(centre_index, dtype=float) * zooms
    world = np.moveaxis(np.indices(shape).astype(float), 0, -1) * zooms + affine[:3, 3]
    r = np.linalg.norm(world, axis=-1)
    labels = np.zeros(shape, dtype=np.int16)
    brain = r < BRAIN_R
    labels[brain & (world[..., 0] < 0)] = 3
    labels[brain & (world[..., 0] >= 0)] = 42
    stem = (
        brain
        & (np.hypot(world[..., 0], world[..., 1]) < 5)
        & (world[..., 2] > -28)
        & (world[..., 2] < -15)
    )
    labels[stem] = 16
    labels[(r >= BRAIN_R) & (r < CSF_R)] = LABEL["csf"]
    labels[(r >= CSF_R) & (r < BONE_R)] = LABEL["bone"]
    labels[(r >= BONE_R) & (r < SKIN_R)] = LABEL["skin"]
    # A vertebra below the head, apart from the skull: superior and inferior differ, so a
    # cut on the wrong end of the axis is not hidden by the head's symmetry.
    vertebra = (
        (np.hypot(world[..., 0], world[..., 1]) < 8)
        & (world[..., 2] > -61)
        & (world[..., 2] < -46)
    )
    labels[vertebra] = LABEL["bone"]
    return labels, affine, world


def _save(path, labels, affine, axcodes=None):
    """Save *labels* (RAS) as NIfTI, reordered to *axcodes* with the matching affine."""
    import nibabel as nib
    from nibabel.orientations import (
        apply_orientation,
        axcodes2ornt,
        inv_ornt_aff,
        ornt_transform,
    )

    if axcodes is not None:
        transform = ornt_transform(axcodes2ornt("RAS"), axcodes2ornt(axcodes))
        affine = affine @ inv_ornt_aff(transform, labels.shape)
        labels = apply_orientation(labels, transform)
    img = nib.Nifti1Image(np.ascontiguousarray(labels), affine)
    nib.save(img, str(path))
    return nib.load(str(path))


def _analyze(ta, path, out, tissue, monkeypatch):
    analyzer = ta.TissueAnalyzer(path, out, tissue, logging.getLogger("tissue-test"))
    # Figures are checked once, below; drawing them here would only add minutes.
    monkeypatch.setattr(analyzer, "_create_visualizations", lambda *a, **k: None)
    return analyzer, analyzer.analyze()


# 1 mm isotropic; the head centre (50, 55, 62) leaves every shell inside the grid.
SHAPE, ZOOMS, CENTRE = (100, 110, 120), (1.0, 1.0, 1.0), (50, 55, 62)


@pytest.fixture(scope="module")
def head():
    return _head(SHAPE, ZOOMS, CENTRE)


def _expected_filtered(head, tissue):
    """Tissue voxels not inferior to (brain centre - padding), from world z alone."""
    labels, _, world = head
    # The brain spans world z -29..29 (voxel centres), so its centre is world z 0.
    cutoff = 0.0 - PADDING[tissue] * ZOOMS[2]
    return int(np.sum((labels == LABEL[tissue]) & (world[..., 2] >= cutoff)))


@pytest.mark.parametrize("tissue", ["csf", "bone", "skin"])
def test_ras_head_volume_and_thickness_follow_the_geometry(
    ta, head, tissue, tmp_path, monkeypatch
):
    labels, affine, _ = head
    path = tmp_path / "labeling.nii.gz"
    _save(path, labels, affine)

    analyzer, res = _analyze(ta, path, tmp_path / "out", tissue, monkeypatch)

    total = int(np.sum(labels == LABEL[tissue]))
    filtered = _expected_filtered(head, tissue)
    # CSF reaches 34 mm below the brain centre, inside its 40 mm padding: nothing to cut.
    assert 0 < filtered < total if tissue != "csf" else filtered == total
    assert res["voxels"] == {"total": total, "filtered": filtered}
    assert res["volume_mm3"] == pytest.approx(filtered * 1.0)
    assert res["volume_cm3"] == pytest.approx(filtered / 1000)

    # A shell of thickness T measured with 1 mm voxels: every statistic within one voxel.
    t = THICKNESS_MM[tissue]
    thick = res["thickness"]
    assert t - 1.0 <= thick["min"] <= thick["mean"] <= thick["max"] <= t + 1.0
    assert thick["mean"] == pytest.approx(t, abs=0.75)
    assert thick["std"] < 0.5


@pytest.mark.parametrize("axcodes", [("P", "S", "R"), ("L", "P", "I")])
def test_storage_order_does_not_change_any_result(ta, axcodes, tmp_path, monkeypatch):
    """Anisotropic voxels too: the reordered file carries permuted zooms."""
    import nibabel as nib

    zooms = (1.0, 0.8, 1.25)
    centre = (50, 70, 50)  # world origin; 43 mm fits in every direction
    labels, affine, _ = _head((100, 140, 100), zooms, centre)
    ras = _save(tmp_path / "ras.nii.gz", labels, affine)
    moved = _save(tmp_path / "moved.nii.gz", labels, affine, axcodes)
    assert nib.aff2axcodes(ras.affine) == ("R", "A", "S")
    assert nib.aff2axcodes(moved.affine) == axcodes
    order = ["RAS".index({"L": "R", "P": "A", "I": "S"}.get(c, c)) for c in axcodes]
    assert moved.header.get_zooms() == pytest.approx([zooms[i] for i in order])

    for tissue in ("csf", "bone", "skin"):
        _, a = _analyze(
            ta, tmp_path / "ras.nii.gz", tmp_path / "a", tissue, monkeypatch
        )
        _, b = _analyze(
            ta, tmp_path / "moved.nii.gz", tmp_path / "b", tissue, monkeypatch
        )
        assert b["voxels"] == a["voxels"], tissue
        assert b["volume_cm3"] == pytest.approx(a["volume_cm3"]), tissue
        for stat in ("mean", "std", "min", "max"):
            assert b["thickness"][stat] == pytest.approx(
                a["thickness"][stat], abs=1e-9
            ), (tissue, stat)
        if tissue == "bone":  # 30 x 1.25 mm padding < 40 mm: the inferior cut is real
            assert a["voxels"]["filtered"] < a["voxels"]["total"]


@pytest.mark.parametrize("axcodes", [None, ("P", "S", "R")])
def test_thickness_is_in_millimetres_across_anisotropic_voxels(
    ta, axcodes, tmp_path, monkeypatch
):
    """A flat bone plate 6 mm thick across 0.5 mm voxels (12 of them) reads 6 mm.

    The plate fills the grid in y and z and the brain sits against it, so nothing is cut
    and every medial voxel is one of the two central layers, 3 mm from either face.
    """
    labels = np.zeros((60, 40, 40), dtype=np.int16)
    labels[:20] = 3
    labels[20:32] = LABEL["bone"]
    affine = np.diag([0.5, 1.0, 1.0, 1.0])
    _save(tmp_path / "plate.nii.gz", labels, affine, axcodes)

    _, res = _analyze(
        ta, tmp_path / "plate.nii.gz", tmp_path / "o", "bone", monkeypatch
    )

    assert res["voxels"] == {"total": 12 * 40 * 40, "filtered": 12 * 40 * 40}
    assert res["volume_cm3"] == pytest.approx(12 * 40 * 40 * 0.5 / 1000)
    for stat in ("mean", "min", "max"):
        assert res["thickness"][stat] == pytest.approx(6.0), stat
    assert res["thickness"]["std"] == pytest.approx(0.0, abs=1e-12)


def test_brain_centre_closer_to_the_bottom_than_the_padding_removes_nothing(
    ta, tmp_path, monkeypatch
):
    """Brain centre at z index 20, CSF padding 40: the cut-off is below the volume."""
    shape, centre = (60, 60, 80), (30, 30, 20)
    affine = np.eye(4)
    affine[:3, 3] = -np.asarray(centre, dtype=float)
    world = np.moveaxis(np.indices(shape).astype(float), 0, -1) + affine[:3, 3]
    r = np.linalg.norm(world, axis=-1)
    labels = np.zeros(shape, dtype=np.int16)
    labels[r < 10] = 3  # brain z index 11..29, centre 20
    labels[(r >= 10) & (r < 14)] = LABEL["csf"]
    labels[(world[..., 2] > 25) & (r >= 30) & (r < 34)] = LABEL["csf"]  # high up
    _save(tmp_path / "low.nii.gz", labels, affine)

    _, res = _analyze(ta, tmp_path / "low.nii.gz", tmp_path / "o", "csf", monkeypatch)

    # Box: z from max(0, 11-40) to 29+40 = 69 > every CSF voxel (<= 53); lateral +-40
    # covers the grid. Nothing is inferior to 20 - 40 < 0, so every CSF voxel is kept.
    total = int(np.sum(labels == LABEL["csf"]))
    assert res["voxels"] == {"total": total, "filtered": total}


def test_report_states_plain_numbers_that_match_the_result(
    ta, head, tmp_path, monkeypatch
):
    import nibabel as nib

    labels, affine, _ = head
    affine = affine.copy()
    affine[0, 0] = 0.8  # float32 zooms (0.8, 1.0, 1.0) as in Dataset 000 sub-101
    path = tmp_path / "labeling.nii.gz"
    _save(path, labels, affine)
    assert nib.load(str(path)).header.get_zooms()[0].dtype == np.float32

    _, res = _analyze(ta, path, tmp_path / "out", "bone", monkeypatch)
    text = (tmp_path / "out" / "bone_analysis.txt").read_text()

    assert "np." not in text and "float32" not in text
    dims = re.search(r"Voxel dimensions: (.+) mm", text).group(1)
    assert [float(v) for v in re.findall(r"[\d.]+", dims)] == [0.8, 1.0, 1.0]

    total = int(re.search(r"Total voxels: ([\d,]+)", text).group(1).replace(",", ""))
    kept = int(re.search(r"Filtered voxels: ([\d,]+)", text).group(1).replace(",", ""))
    volume = float(re.search(r"Volume: ([\d.]+) cm", text).group(1))
    assert total == int(np.sum(labels == LABEL["bone"]))
    assert kept == res["voxels"]["filtered"] <= total
    # 0.8 mm^3 per voxel, reported in cm^3 to three decimals.
    assert volume == pytest.approx(round(kept * 0.8 / 1000, 3), abs=5e-4)
    mean = float(re.search(r"Mean: ([\d.]+) mm", text).group(1))
    assert mean == pytest.approx(res["thickness"]["mean"], abs=5e-4)


def test_figures_show_anatomical_views_whatever_the_storage_order(
    ta, head, tmp_path, monkeypatch
):
    """Real matplotlib: each view is the named anatomical plane, labelled as such."""
    import matplotlib.pyplot as plt

    if isinstance(plt, MagicMock):
        pytest.skip("needs real matplotlib; run tests/numerical in idossha/ti-toolbox")

    labels, affine, _ = head
    _save(tmp_path / "psr.nii.gz", labels, affine, ("P", "S", "R"))
    analyzer = ta.TissueAnalyzer(
        tmp_path / "psr.nii.gz", tmp_path / "out", "bone", logging.getLogger("t")
    )
    tissue = analyzer._create_tissue_mask()
    filtered = analyzer._filter_to_brain_region(tissue, analyzer._create_brain_mask())
    stats = analyzer._calculate_thickness(tissue, filtered)

    keep = {}
    real_close = plt.close
    monkeypatch.setattr(plt, "savefig", lambda *a, **k: None)
    monkeypatch.setattr(plt, "close", lambda *a: keep.setdefault("fig", plt.gcf()))
    analyzer._create_thickness_figure(filtered, stats, plt)
    fig = keep["fig"]
    views = {ax.get_title(): ax for ax in fig.axes if ax.get_title()}
    n_r, n_a, n_s = SHAPE  # the authored RAS extents
    expect = {
        "A. Axial View": ((n_a, n_r), "Left-Right", "Posterior-Anterior"),
        "B. Coronal View": ((n_s, n_r), "Left-Right", "Inferior-Superior"),
        "C. Sagittal View": ((n_s, n_a), "Posterior-Anterior", "Inferior-Superior"),
    }
    for title, (shape, xdir, ydir) in expect.items():
        ax = views[title]
        assert ax.images[0].get_array().shape == shape, title
        assert xdir in ax.get_xlabel(), (title, ax.get_xlabel())
        assert ydir in ax.get_ylabel(), (title, ax.get_ylabel())
    real_close(fig)
