"""`tit.atlas.islands` — the detached-island cleanup, on synthetic volumes.

Real-library leg (see this directory's ``conftest.py``): the claim is numerical —
which connected components survive a threshold — so it needs the real
``scipy.ndimage`` and ``nibabel``, not the host suite's mocks.

The expected values here come from counting the blobs this file builds, not from
running the function under test.
"""

import os

import numpy as np
import pytest

from tit.atlas import islands


def _volume():
    """One 8x8x8 main body (512 voxels), one 27-voxel blob far away, one speck."""
    data = np.zeros((40, 40, 40), dtype=np.int16)
    data[4:12, 4:12, 4:12] = 7  # main body: 512 voxels
    data[30:33, 30:33, 30:33] = 7  # island: 27 voxels
    data[36, 36, 36] = 7  # speck: 1 voxel
    data[20:24, 20:24, 20:24] = 9  # a different label, one body: 64 voxels
    return data


def test_the_main_body_survives_and_the_debris_does_not():
    data = _volume()
    mask = data == 7
    assert mask.sum() == 512 + 27 + 1
    cleaned, removed, dropped = islands.keep_main_components(mask, what="Test-Region")
    # 27 and 1 are both under the 50-voxel floor, which is what the floor is for:
    # 5% of 512 is only 25.6, so the ratio alone would have kept the 27-voxel blob.
    assert removed == 28
    assert dropped == 2
    assert cleaned.sum() == 512
    # ...and it is the *right* 512: the cleaned mask is exactly the main cube.
    expected = np.zeros_like(mask)
    expected[4:12, 4:12, 4:12] = True
    assert np.array_equal(cleaned, expected)


def test_a_single_body_and_an_empty_mask_are_returned_untouched():
    data = _volume()
    for mask in (data == 9, data == 123):
        cleaned, removed, dropped = islands.keep_main_components(mask)
        assert (removed, dropped) == (0, 0)
        assert np.array_equal(cleaned, mask)


def test_a_genuinely_bipartite_region_keeps_both_halves():
    """The threshold is a ratio first: two comparable bodies are anatomy, not debris."""
    data = np.zeros((40, 40, 40), dtype=np.int16)
    data[4:12, 4:12, 4:12] = 3  # 512 voxels
    data[28:36, 28:36, 28:36] = 3  # 512 voxels, disconnected
    cleaned, removed, dropped = islands.keep_main_components(data == 3)
    assert (removed, dropped) == (0, 0)
    assert cleaned.sum() == 1024


def test_the_escape_hatch_returns_the_raw_segmentation(monkeypatch):
    monkeypatch.setenv("TIT_ROI_KEEP_ISLANDS", "1")
    assert islands.cleanup_enabled() is False
    mask = _volume() == 7
    cleaned, removed, dropped = islands.keep_main_components(mask)
    assert (removed, dropped) == (0, 0)
    assert cleaned.sum() == mask.sum()


def test_cleaned_label_mask_writes_a_file_only_when_there_is_something_to_remove(tmp_path):
    import nibabel as nib

    source = tmp_path / "labeling.nii.gz"
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    nib.save(nib.Nifti1Image(_volume(), affine), str(source))
    out = tmp_path / "prepared"

    # Label 9 is one body: nothing is written and the caller keeps (atlas, label).
    assert islands.cleaned_label_mask(str(source), 9, str(out)) is None
    assert not out.exists() or not list(out.iterdir())

    # Label 7 has islands: a binary mask is written, and it holds only the main body.
    path = islands.cleaned_label_mask(str(source), 7, str(out))
    assert path is not None
    written = np.asanyarray(nib.load(path).dataobj)
    assert written.dtype == np.uint8
    assert int(written.sum()) == 512
    assert np.allclose(nib.load(path).affine, affine)

    # A second call reuses the file rather than rewriting it.
    again = islands.cleaned_label_mask(str(source), 7, str(out))
    assert again == path
    assert len(list(out.iterdir())) == 1

    # An absent label is not an error and writes nothing.
    assert islands.cleaned_label_mask(str(source), 123, str(out)) is None


@pytest.mark.skipif(
    not os.environ.get("TIT_ERNIE_LABELING"),
    reason="set TIT_ERNIE_LABELING to a real m2m segmentation/labeling.nii.gz",
)
def test_ernie_left_putamen_loses_exactly_its_measured_islands():
    """The 2026-09-17 measurement, re-run: 6109 voxels in, 6032 out."""
    import nibabel as nib

    data = np.asanyarray(nib.load(os.environ["TIT_ERNIE_LABELING"]).dataobj)
    mask = data == 12  # Left-Putamen in charm's labeling LUT
    assert int(mask.sum()) == 6109
    cleaned, removed, dropped = islands.keep_main_components(mask, what="Left-Putamen")
    assert int(cleaned.sum()) == 6032
    assert (removed, dropped) == (77, 9)
