#!/usr/bin/env python3
"""Unit tests for the pure-Python FreeSurfer-binary replacements in
tit/analyzer/analyzer.py:

- ``Analyzer._resample_if_needed``: was ``mri_convert --reslice_like``, now
  ``nibabel.processing.resample_from_to(..., order=0)``, keyed on the full
  target grid (shape *and* affine).
- ``Analyzer._find_voxel_region_id``: was a ``mri_segstats`` subprocess +
  temp-file parse, now ``tit.atlas.segstats.compute_segstats``.

Voxel-for-voxel validation against real ``mri_convert``/``mri_segstats``
output on sub-ernie's actual recon-all data lives in
docs/dev/HISTORY.md § 2026-09-03; this suite covers the pure-function
contract with the repo's established nibabel-mocking pattern (nibabel is
mocked module-wide in tests/conftest.py; numpy is real).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.analyzer.analyzer import Analyzer

# ============================================================================
# _resample_if_needed
# ============================================================================


@pytest.mark.unit
class TestResampleIfNeeded:
    @pytest.fixture(autouse=True)
    def _nib_processing(self):
        """`nibabel` is mocked module-wide in conftest, so the submodule the
        implementation imports has to exist before any of these run."""
        import sys as _sys

        mock = MagicMock()
        _sys.modules["nibabel.processing"] = mock
        yield mock

    def test_matching_grid_returns_input_unchanged(self):
        """No resampling when shape *and* affine already match the target."""
        atlas_arr = np.ones((4, 4, 4))
        atlas_img = MagicMock()
        atlas_img.affine = np.eye(4)

        result = Analyzer._resample_if_needed(
            atlas_img, atlas_arr, (4, 4, 4), np.eye(4), Path("/unused/atlas.mgz")
        )
        assert result is atlas_arr

    def test_matching_shape_but_different_affine_still_resamples(self, tmp_path):
        """Shape alone does not identify a grid -- two volumes can share
        dimensions while sampling entirely different anatomy."""
        import sys as _sys

        nib_processing_mock = MagicMock()
        _sys.modules["nibabel.processing"] = nib_processing_mock
        nib_processing_mock.resample_from_to.return_value.dataobj = np.zeros((2, 2, 2))

        atlas_img = MagicMock()
        atlas_img.affine = np.eye(4)
        target_affine = np.eye(4)
        target_affine[0, 3] = 40.0  # same shape, 40 mm away

        atlas_path = tmp_path / "atlas.mgz"
        atlas_path.touch()
        with patch("nibabel.Nifti1Image"), patch("nibabel.save"), patch("nibabel.load"):
            Analyzer._resample_if_needed(
                atlas_img, np.ones((2, 2, 2)), (2, 2, 2), target_affine, atlas_path
            )
        nib_processing_mock.resample_from_to.assert_called_once()

    def test_mismatched_shape_calls_resample_from_to(self, tmp_path):
        import sys as _sys

        nib_processing_mock = MagicMock()
        _sys.modules["nibabel.processing"] = nib_processing_mock

        atlas_arr = np.ones((2, 2, 2))
        atlas_img = MagicMock()
        atlas_img.affine = np.eye(4)
        atlas_path = tmp_path / "aparc.DKTatlas+aseg.mgz"
        atlas_path.touch()

        target_affine = np.eye(4)
        resampled = np.full((3, 2, 2), 9.0)
        nib_processing_mock.resample_from_to.return_value.dataobj = resampled

        rebuilt = MagicMock()
        with patch("nibabel.Nifti1Image", return_value=rebuilt) as mock_image, patch(
            "nibabel.save"
        ), patch("nibabel.load"):
            result = Analyzer._resample_if_needed(
                atlas_img, atlas_arr, (3, 2, 2), target_affine, atlas_path
            )

        # The source image is rebuilt from the array actually passed in -- the
        # caller may have squeezed a trailing singleton axis off a 4D volume.
        # (called again by _cache_resample when writing the cache)
        np.testing.assert_array_equal(mock_image.call_args_list[0][0][0], atlas_arr)
        nib_processing_mock.resample_from_to.assert_called_once_with(
            rebuilt, ((3, 2, 2), target_affine), order=0
        )
        np.testing.assert_array_equal(result, resampled)

    def test_cache_name_encodes_both_shape_and_affine(self, tmp_path):
        """The cache key is the full target grid.

        Keying on shape alone would hand back a volume resampled to different
        anatomy whenever two grids happen to share dimensions; and the stem
        keeps every dotted component, so ``aparc.DKTatlas+aseg`` and
        ``aparc.a2009s+aseg`` cannot collide.
        """
        src = Path("/somewhere/aparc.DKTatlas+aseg.mgz")
        other = Path("/somewhere/aparc.a2009s+aseg.mgz")
        a1 = np.eye(4)
        a2 = np.eye(4)
        a2[0, 3] = 40.0

        n1 = Analyzer._resampled_name(src, (256, 256, 208), a1)
        assert n1.startswith("aparc_DKTatlas+aseg_resampled_256x256x208_")
        assert n1.endswith(".nii.gz")
        assert n1 != Analyzer._resampled_name(src, (256, 256, 208), a2)
        assert n1 != Analyzer._resampled_name(other, (256, 256, 208), a1)
        assert n1 == Analyzer._resampled_name(src, (256, 256, 208), a1.copy())

    def test_existing_cache_is_reused_without_resampling(self, tmp_path):
        """A cached resampled file short-circuits resample_from_to entirely."""
        import sys as _sys

        nib_processing_mock = MagicMock()
        _sys.modules["nibabel.processing"] = nib_processing_mock

        atlas_arr = np.ones((2, 2, 2))
        atlas_img = MagicMock()
        atlas_img.affine = np.eye(4)
        atlas_path = tmp_path / "atlas.mgz"
        atlas_path.touch()
        cached_path = tmp_path / Analyzer._resampled_name(
            atlas_path, (3, 3, 3), np.eye(4)
        )
        cached_path.touch()  # presence alone triggers the cache-hit branch

        cached_data = np.full((3, 3, 3), 5.0)
        with patch("nibabel.load") as mock_load:
            mock_load.return_value.dataobj = cached_data
            result = Analyzer._resample_if_needed(
                atlas_img, atlas_arr, (3, 3, 3), np.eye(4), atlas_path
            )

        nib_processing_mock.resample_from_to.assert_not_called()
        np.testing.assert_array_equal(result, cached_data)

    def test_unwritable_cache_degrades_to_in_memory(self, tmp_path):
        """Caching is best-effort: an OSError must not fail the analysis."""
        with patch("nibabel.save", side_effect=OSError("read-only")):
            Analyzer._cache_resample(
                np.zeros((2, 2, 2)), np.eye(4), tmp_path / "nope" / "x.nii.gz"
            )


# ============================================================================
# _find_voxel_region_id
# ============================================================================


@pytest.mark.unit
class TestFindVoxelRegionId:
    def test_digit_string_short_circuits_lookup(self):
        """A bare integer region string is returned as-is, no atlas read."""
        with patch("tit.analyzer.analyzer.compute_segstats") as mock_compute:
            result = Analyzer._find_voxel_region_id(
                np.zeros((1, 1, 1)), Path("/unused.mgz"), "  17  "
            )
        assert result == 17
        mock_compute.assert_not_called()

    def test_substring_match_returns_seg_id(self):
        from tit.atlas.segstats import SegStat

        stats = [
            SegStat(seg_id=10, name="Left-Thalamus-Proper", n_voxels=1, volume_mm3=1.0),
            SegStat(seg_id=17, name="Left-Hippocampus", n_voxels=1, volume_mm3=1.0),
        ]
        with patch("tit.analyzer.analyzer.resolve_lut_for_atlas", return_value={}):
            with patch("tit.analyzer.analyzer.compute_segstats", return_value=stats):
                result = Analyzer._find_voxel_region_id(
                    np.zeros((1, 1, 1)), Path("/unused.mgz"), "hippocampus"
                )
        assert result == 17

    def test_first_ascending_match_wins_on_ambiguity(self):
        """Matches ``mri_segstats``' own row order (ascending SegId): first hit wins."""
        from tit.atlas.segstats import SegStat

        stats = [
            SegStat(seg_id=3, name="Left-Cortex-A", n_voxels=1, volume_mm3=1.0),
            SegStat(seg_id=9, name="Right-Cortex-A", n_voxels=1, volume_mm3=1.0),
        ]
        with patch("tit.analyzer.analyzer.resolve_lut_for_atlas", return_value={}):
            with patch("tit.analyzer.analyzer.compute_segstats", return_value=stats):
                result = Analyzer._find_voxel_region_id(
                    np.zeros((1, 1, 1)), Path("/unused.mgz"), "Cortex-A"
                )
        assert result == 3

    def test_no_match_raises_value_error(self):
        with patch("tit.analyzer.analyzer.resolve_lut_for_atlas", return_value={}):
            with patch("tit.analyzer.analyzer.compute_segstats", return_value=[]):
                with pytest.raises(ValueError, match="not found"):
                    Analyzer._find_voxel_region_id(
                        np.zeros((1, 1, 1)), Path("/some/atlas.mgz"), "NoSuchRegion"
                    )
