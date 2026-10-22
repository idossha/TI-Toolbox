"""The analyzer's atlas resample cache is a miss once the source atlas changed.

What this pins (package c1_5, 2026-10-22): ``Analyzer._resample_if_needed`` caches a
label volume resampled onto the field's grid beside the source atlas (seen on Dataset 000:
``freesurfer/sub-ernie/mri/aparc_DKTatlas+aseg_resampled_256x256x208_45dfa12d.nii.gz``), keyed
on the target grid only. A sub-region re-run or a recon outside the app rewrites the atlas in
place and left that cache serving the old labels. The key now carries the source's size and
modification time: a rewritten atlas (here with the same size, only its labels and time
changed) is resampled again, and an untouched one still hits the cache without a second write.

Where the numbers come from: the label volumes are authored here on a 1 mm identity grid and
the target is the 2 mm grid with the same origin, so nearest-neighbour sampling of target voxel
``(i, j, k)`` reads source voxel ``(2i, 2j, 2k)`` exactly -- the expected array is
``labels[::2, ::2, ::2]``, computed from the authored array, not by the resampler.

Needs only real numpy/nibabel (``host_numerical``); the host suite mocks nibabel.

Reproduce:
  host:      ``.venv/bin/python -m pytest tests/numerical/test_analyzer_resample_cache_fresh.py -q -m host_numerical``
  container: ``simnibs_python -m pytest tests/numerical/test_analyzer_resample_cache_fresh.py -q``
Deliberately elsewhere: the cache name's grid key, the unwritable-cache and corrupt-cache
fallbacks (``tests/test_analyzer_voxel_resample.py``).
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical

SOURCE_SHAPE = (8, 8, 8)
TARGET_SHAPE = (4, 4, 4)
TARGET_AFFINE = np.diag([2.0, 2.0, 2.0, 1.0])  # same origin as the 1 mm identity source


def _write_labels(path: Path, labels: np.ndarray) -> None:
    import nibabel as nib

    nib.save(nib.Nifti1Image(labels, np.eye(4)), str(path))


def _resample(path: Path, calls: list) -> np.ndarray:
    import nibabel as nib

    from tit.analyzer.analyzer import Analyzer

    img = nib.load(str(path))
    return np.asarray(
        Analyzer._resample_if_needed(
            img, np.asanyarray(img.dataobj), TARGET_SHAPE, TARGET_AFFINE, path
        )
    )


@pytest.fixture()
def counted(monkeypatch) -> list:
    """Every call the analyzer makes to nibabel's resampler (the real one still runs)."""
    import nibabel.processing as processing

    calls: list = []
    real = processing.resample_from_to

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(processing, "resample_from_to", spy)
    return calls


def _caches(folder: Path) -> list[Path]:
    return sorted(folder.glob("*_resampled_*"))


def test_a_rewritten_atlas_is_resampled_again_and_an_untouched_one_hits_the_cache(
    tmp_path: Path, counted: list
) -> None:
    atlas = (
        tmp_path / "aparc.DKTatlas+aseg.nii"
    )  # uncompressed: a rewrite keeps the size
    old = np.arange(np.prod(SOURCE_SHAPE), dtype=np.int16).reshape(SOURCE_SHAPE)
    _write_labels(atlas, old)

    first = _resample(atlas, counted)
    np.testing.assert_array_equal(first, old[::2, ::2, ::2])
    (cache,) = _caches(tmp_path)
    written = cache.stat().st_mtime_ns
    assert len(counted) == 1

    # Untouched source: served from the cache, nothing resampled or written again.
    again = _resample(atlas, counted)
    np.testing.assert_array_equal(again, old[::2, ::2, ::2])
    assert len(counted) == 1
    assert _caches(tmp_path) == [cache] and cache.stat().st_mtime_ns == written

    # The atlas is rewritten in place: other labels, same size, a later time.
    size, mtime = atlas.stat().st_size, atlas.stat().st_mtime_ns
    new = (old[::-1, ::-1, ::-1] + 1000).astype(np.int16)
    _write_labels(atlas, new)
    os.utime(atlas, ns=(mtime + 2_000_000_000, mtime + 2_000_000_000))
    assert atlas.stat().st_size == size

    fresh = _resample(atlas, counted)
    np.testing.assert_array_equal(fresh, new[::2, ::2, ::2])
    assert len(counted) == 2
    # And that result is what the next analysis of the new atlas is served.
    np.testing.assert_array_equal(_resample(atlas, counted), new[::2, ::2, ::2])
    assert len(counted) == 2
