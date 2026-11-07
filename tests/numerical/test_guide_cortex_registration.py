"""The packaged guides' midlayer cortex against the NIfTI files it is drawn with (2026-11-07).

What this pins
    A cortical MNI atlas painted on the central surfaces says what its own NIfTI says, each
    hemisphere's vertices carry that hemisphere's regions, and the surfaces made from label
    volumes sit in the same frame as the cortex: both land on the right tissue of the head's own
    ``final_tissues.nii.gz``.

Where the numbers come from
    nibabel reads the source volumes and looks up the voxel holding each vertex, a route the
    builder does not use (it searches a KD-tree of labelled voxels and then mode-filters).
    ``final_tissues`` was written by charm, not by any of this. The bounds sit below the values
    measured 2026-11-07 (quoted beside each), which the mode filter and the surfaces' own distance
    from a tissue border keep from reaching 1.

Run it in the image::

    docker exec -w /ti-toolbox -e TIT_DATASET_000=/mnt/000 <container> \\
      simnibs_python -m pytest tests/numerical/test_guide_cortex_registration.py -q -s

The dataset half skips with a reason without ``TIT_DATASET_000``. The package's shape (closed
cortex, which atlas is on which part) is ``tests/test_scene_guide.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from tit.atlas.constants import mni_resources_dir
from tit.scene import guide, tvsc
from tit.scene.guide_build import MNI_CORTICAL_VOLUMES

#: SimNIBS tissue indices in ``final_tissues``: white matter, grey matter, CSF.
WM, GM, CSF = 1, 2, 3


def _surface(part: str, guide_id: str) -> np.ndarray:
    return tvsc.decode(
        guide.surface(part, "tvsc", guide_id).path.read_bytes()
    ).positions


def _labels(atlas: str) -> np.ndarray:
    return tvsc.decode(guide.labels(atlas, "tvsc", "mni").path.read_bytes()).labels


def _at(image, points: np.ndarray) -> np.ndarray:
    """The voxel value holding each world point, 0 outside the grid."""
    import nibabel as nib

    ijk = np.rint(nib.affines.apply_affine(np.linalg.inv(image.affine), points)).astype(
        int
    )
    inside = ((ijk >= 0) & (ijk < np.array(image.shape[:3]))).all(axis=1)
    values = np.asarray(image.dataobj)
    out = np.zeros(len(points), dtype=np.int64)
    out[inside] = values[tuple(ijk[inside].T)].astype(np.int64).ravel()
    return out


@pytest.mark.parametrize("atlas", MNI_CORTICAL_VOLUMES)
def test_a_painted_cortical_atlas_says_what_its_nifti_says(atlas: str) -> None:
    import nibabel as nib

    labels = _labels(atlas)
    image = nib.load(str(Path(mni_resources_dir()) / atlas))
    voxel = _at(image, _surface("gm", "mni"))
    in_a_region = voxel != 0
    agree = float((labels[in_a_region] == voxel[in_a_region]).mean())
    print(
        f"{atlas}: {in_a_region.mean():.3f} of vertices in a labelled voxel, {agree:.3f} agree"
    )
    assert in_a_region.mean() > 0.5
    assert agree > 0.9


@pytest.mark.parametrize(
    ("atlas", "left", "right"),
    [
        ("HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz", "Left-", "Right-"),
        ("MNI_Glasser_HCP_v1.0.nii.gz", "L-", "R-"),
        (
            "Schaefer2018_400Parcels_7Networks_order_FSLMNI152_1mm.nii.gz",
            "7Networks_LH",
            "7Networks_RH",
        ),
    ],
)
def test_no_vertex_takes_a_region_of_the_other_hemisphere(
    atlas: str, left: str, right: str
) -> None:
    """The medial wall lies within the transfer radius of the opposite hemisphere.

    A hemisphere's own surface crosses the midline by up to 2.1 mm (measured on these vertices),
    so the wrong side begins past the 3 mm radius, where the old transfer would have reached.
    """
    names = {row["label"]: row["name"] for row in guide.legend(atlas, "mni")["legend"]}
    labels = _labels(atlas)
    x = _surface("gm", "mni")[:, 0]
    is_left = np.isin(labels, [i for i, n in names.items() if n.startswith(left)])
    is_right = np.isin(labels, [i for i, n in names.items() if n.startswith(right)])
    assert is_left.any() and is_right.any()
    assert not (is_left & (x > 3)).any()
    assert not (is_right & (x < -3)).any()


def _dataset() -> Path:
    root = os.environ.get("TIT_DATASET_000")
    if not root:
        pytest.skip(
            "skipping: TIT_DATASET_000 names no Dataset 000 to read final_tissues from"
        )
    return Path(root) / "derivatives" / "SimNIBS"


@pytest.mark.parametrize(
    ("guide_id", "subject"), [("default", "ernie"), ("mni", "MNI152")]
)
def test_cortex_and_volume_surfaces_share_the_heads_frame(
    guide_id: str, subject: str
) -> None:
    """The midlayer lands on grey matter and the deep regions in brain tissue, on one head."""
    import nibabel as nib

    path = _dataset() / f"sub-{subject}" / f"m2m_{subject}" / "final_tissues.nii.gz"
    if not path.is_file():
        pytest.skip(f"skipping: {path} is not in this dataset")
    tissues = nib.load(str(path))
    cortex = _at(tissues, _surface("gm", guide_id))
    on_grey = float((cortex == GM).mean())
    in_brain = float(np.isin(cortex, (WM, GM, CSF)).mean())
    print(f"{subject} cortex: {on_grey:.3f} on GM, {in_brain:.3f} in WM/GM/CSF")
    assert on_grey > 0.85
    assert in_brain > 0.99
    parts = [
        p["id"]
        for p in guide.manifest(guide_id)["parts"]
        if p["id"] not in ("skin", "gm")
    ]
    assert parts, "no volume surface to check"
    for part in parts:
        deep = _at(tissues, _surface(part, guide_id))
        brain = float(np.isin(deep, (WM, GM, CSF)).mean())
        print(f"{subject} {part}: {brain:.3f} in WM/GM/CSF")
        assert brain > 0.9, part


def test_a_subjects_own_midlayer_lands_on_its_grey_matter() -> None:
    import nibabel as nib

    m2m = _dataset() / "sub-CHN" / "m2m_CHN"
    tissues = m2m / "final_tissues.nii.gz"
    if not tissues.is_file():
        pytest.skip(f"skipping: {tissues} is not in this dataset")
    points = np.concatenate(
        [
            nib.load(str(m2m / "surfaces" / f"{hemi}.central.gii")).darrays[0].data
            for hemi in ("lh", "rh")
        ]
    )
    on_grey = float((_at(nib.load(str(tissues)), points) == GM).mean())
    print(f"CHN cortex: {on_grey:.3f} on GM")
    assert on_grey > 0.85
