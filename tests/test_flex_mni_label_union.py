"""A union of the same label value from two MNI atlases keeps both regions.

What this pins (package p08, 2026-10-22): ``_mni_labels_to_subject`` selects each (atlas, label)
into a binary MNI mask before warping it into the subject. Before this date every selection of
label 10 was written to one shared ``mni-label-10.nii`` in the subject's mask cache, so the
second atlas's selection overwrote the first one's file: anything reading that file after the
loop -- a concurrent job of the same subject, the ROI confirmation, a re-run hitting the cache --
got atlas B's voxels under atlas A's name. Each (atlas, label) now has a file of its own.

How: nibabel is mocked on the host, so the test gives the function an in-memory "disk" (save
writes, load reads) and a ``prepare_mask`` that echoes the voxels of the file it is handed. The
two atlases put label 10 at different voxels; the expected masks are those voxels, written by the
test itself.

Reproduce: ``.venv/bin/python -m pytest tests/test_flex_mni_label_union.py -q``.
"""

from __future__ import annotations

import contextlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np


class _Img:
    def __init__(self, data, affine):
        self.dataobj = np.array(data, copy=True)
        self.affine = affine


def test_two_atlases_with_the_same_label_keep_their_own_masks(tmp_path, monkeypatch):
    shape, label = (4, 4, 4), 10
    atlas_a = np.zeros(shape, dtype=np.int16)
    atlas_a[0, 0, 0] = label
    atlas_b = np.zeros(shape, dtype=np.int16)
    atlas_b[3, 3, 3] = label
    atlas_b[2, 3, 3] = label
    disk = {
        str(tmp_path / "A_MNI.nii.gz"): _Img(atlas_a, np.eye(4)),
        str(tmp_path / "B_MNI.nii.gz"): _Img(atlas_b, np.eye(4)),
    }
    fake_nib = SimpleNamespace(
        load=lambda path: disk[str(path)],
        save=lambda img, path: disk.__setitem__(
            str(path), _Img(img.dataobj, img.affine)
        ),
        Nifti1Image=_Img,
    )
    monkeypatch.setitem(sys.modules, "nibabel", fake_nib)

    warped: list[str] = []

    def fake_prepare_mask(path, space, m2m, out, *, binary=False):
        assert space == "mni" and binary
        destination = f"{out}/warped-{len(warped)}.nii.gz"
        disk[destination] = _Img(disk[str(path)].dataobj, np.eye(4))
        warped.append(str(path))
        return destination

    pm = MagicMock()
    pm.m2m.return_value = str(tmp_path / "m2m_001")
    pm.ensure_cache.return_value = str(tmp_path / "cache")
    config = SimpleNamespace(subject_id="001")

    from tit.opt.flex.utils import _mni_labels_to_subject

    with (
        patch("tit.get_path_manager", return_value=pm),
        patch("tit.opt.masks.prepare_mask", fake_prepare_mask),
        patch("tit.opt.masks.keep_deformation_field", contextlib.nullcontext),
    ):
        paths, labels, space = _mni_labels_to_subject(
            sorted(disk), [label, label], config
        )

    assert space == "subject" and labels == [1, 1]
    # Each subject mask is its own atlas's region.
    assert np.argwhere(disk[paths[0]].dataobj).tolist() == [[0, 0, 0]]
    assert np.argwhere(disk[paths[1]].dataobj).tolist() == [[2, 3, 3], [3, 3, 3]]
    # And each atlas's MNI selection is a file of its own that still holds its region.
    assert len(set(warped)) == 2
    assert np.argwhere(disk[warped[0]].dataobj).tolist() == [[0, 0, 0]]
    assert np.argwhere(disk[warped[1]].dataobj).tolist() == [[2, 3, 3], [3, 3, 3]]


def test_the_same_atlas_and_label_reuses_one_selection_name(tmp_path):
    """Content-equal selections share a name, so the warp cache still hits across runs."""
    from tit.opt.flex.utils import _mni_selection_name

    atlas = str(tmp_path / "A_MNI.nii.gz")
    assert _mni_selection_name(atlas, 10) == _mni_selection_name(atlas, 10)
    assert _mni_selection_name(atlas, 10) != _mni_selection_name(atlas, 11)
    assert _mni_selection_name(atlas, 10) != _mni_selection_name(
        str(tmp_path / "B_MNI.nii.gz"), 10
    )
