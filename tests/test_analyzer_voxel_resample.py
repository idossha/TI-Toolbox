#!/usr/bin/env python3
"""Unit tests for the pure-Python FreeSurfer-binary replacements in
tit/analyzer/analyzer.py:

- ``Analyzer._resample_if_needed``: was ``mri_convert --reslice_like``, now
  ``nibabel.processing.resample_from_to(..., order=0)``.
- ``Analyzer._find_voxel_region_id``: was a ``mri_segstats`` subprocess +
  temp-file parse, now ``tit.atlas.segstats.compute_segstats``.

Voxel-for-voxel validation against real ``mri_convert``/``mri_segstats``
output on sub-ernie's actual recon-all data lives in
docs/dev/SPIKES.md; this suite covers the pure-function
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
    def test_matching_shape_returns_input_unchanged(self):
        """No resampling (and no nibabel.processing call) when shapes already match."""
        atlas_arr = np.ones((4, 4, 4))
        atlas_img = MagicMock()

        result = Analyzer._resample_if_needed(
            atlas_img, atlas_arr, (4, 4, 4), np.eye(4), Path("/unused/atlas.mgz")
        )
        assert result is atlas_arr

    def test_mismatched_shape_calls_resample_from_to(self, tmp_path):
        import sys as _sys

        nib_processing_mock = MagicMock()
        _sys.modules["nibabel.processing"] = nib_processing_mock

        atlas_arr = np.ones((2, 2, 2))
        atlas_img = MagicMock()
        atlas_path = tmp_path / "aparc.DKTatlas+aseg.mgz"
        atlas_path.touch()

        target_affine = np.eye(4)
        resampled_img = MagicMock()
        nib_processing_mock.resample_from_to.return_value = resampled_img

        saved_data = np.array(
            [
                [[9.0, 9.0], [9.0, 9.0]],
                [[9.0, 9.0], [9.0, 9.0]],
                [[9.0, 9.0], [9.0, 9.0]],
            ]
        )
        with patch("nibabel.save") as mock_save, patch("nibabel.load") as mock_load:
            mock_load.return_value.get_fdata.return_value = saved_data
            result = Analyzer._resample_if_needed(
                atlas_img, atlas_arr, (3, 2, 2), target_affine, atlas_path
            )

        nib_processing_mock.resample_from_to.assert_called_once_with(
            atlas_img, ((3, 2, 2), target_affine), order=0
        )
        mock_save.assert_called_once()
        np.testing.assert_array_equal(result, saved_data)

    def test_mismatched_shape_writes_shape_encoded_cache_name(self, tmp_path):
        """The cache filename convention (other lanes/tools may glob it) is preserved."""
        import sys as _sys

        nib_processing_mock = MagicMock()
        _sys.modules["nibabel.processing"] = nib_processing_mock
        nib_processing_mock.resample_from_to.return_value = MagicMock()

        atlas_arr = np.ones((2, 2, 2))
        atlas_path = tmp_path / "aparc.DKTatlas+aseg.mgz"
        atlas_path.touch()

        with patch("nibabel.save") as mock_save, patch("nibabel.load"):
            Analyzer._resample_if_needed(
                MagicMock(), atlas_arr, (256, 256, 208), np.eye(4), atlas_path
            )

        saved_path = mock_save.call_args[0][1]
        assert saved_path == str(tmp_path / "aparc_resampled_256x256x208.nii.gz")

    def test_existing_cache_is_reused_without_resampling(self, tmp_path):
        """A cached resampled file short-circuits resample_from_to entirely."""
        import sys as _sys

        nib_processing_mock = MagicMock()
        _sys.modules["nibabel.processing"] = nib_processing_mock

        atlas_arr = np.ones((2, 2, 2))
        atlas_path = tmp_path / "atlas.mgz"
        atlas_path.touch()
        cached_path = tmp_path / "atlas_resampled_3x3x3.nii.gz"
        cached_path.touch()  # presence alone triggers the cache-hit branch

        cached_data = np.full((3, 3, 3), 5.0)
        with patch("nibabel.load") as mock_load:
            mock_load.return_value.get_fdata.return_value = cached_data
            result = Analyzer._resample_if_needed(
                MagicMock(), atlas_arr, (3, 3, 3), np.eye(4), atlas_path
            )

        nib_processing_mock.resample_from_to.assert_not_called()
        np.testing.assert_array_equal(result, cached_data)


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
