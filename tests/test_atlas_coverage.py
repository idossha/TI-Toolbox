#!/usr/bin/env python3
"""
Unit tests for TI-Toolbox atlas module: overlap.py and voxel.py

Targets the low-coverage files to bring them to high coverage.
"""

import os
import pytest
import numpy as np
from unittest.mock import MagicMock, patch, mock_open


# ============================================================================
# overlap.py — check_and_resample_atlas
# ============================================================================


@pytest.mark.unit
class TestCheckAndResampleAtlas:
    """Tests for check_and_resample_atlas."""

    def test_matching_dimensions_3d(self):
        """When atlas and reference shapes match (3D), return atlas data as int."""
        import sys
        sys.modules.setdefault("nibabel.processing", MagicMock())
        from tit.atlas.overlap import check_and_resample_atlas

        data = np.array([[[1.0, 2.0], [3.0, 4.0]]])
        atlas_img = MagicMock()
        atlas_img.shape = (1, 2, 2)
        atlas_img.get_fdata.return_value = data

        ref_img = MagicMock()
        ref_img.shape = (1, 2, 2)

        result = check_and_resample_atlas(atlas_img, ref_img, "test_atlas")

        assert result.dtype == int
        np.testing.assert_array_equal(result, data.astype(int))

    def test_matching_dimensions_4d_atlas(self):
        """When shapes match but atlas is 4D, the 4th dim is sliced off."""
        import sys
        sys.modules.setdefault("nibabel.processing", MagicMock())
        from tit.atlas.overlap import check_and_resample_atlas

        data_4d = np.ones((2, 3, 4, 1))
        atlas_img = MagicMock()
        atlas_img.shape = (2, 3, 4)
        atlas_img.get_fdata.return_value = data_4d

        ref_img = MagicMock()
        ref_img.shape = (2, 3, 4)

        result = check_and_resample_atlas(atlas_img, ref_img, "test_atlas")

        assert result.dtype == int
        # get_fdata returns (2,3,4,1) but astype(int) preserves shape;
        # then the >3 check slices off 4th dim: [:,:,:,0] => (2,3,4)
        assert result.shape == (2, 3, 4)

    def test_matching_dimensions_returns_int_array(self):
        """Returned data should be integer dtype."""
        import sys
        sys.modules.setdefault("nibabel.processing", MagicMock())
        from tit.atlas.overlap import check_and_resample_atlas

        data = np.array([[[5.7, 3.2]]])
        atlas_img = MagicMock()
        atlas_img.shape = (1, 1, 2)
        atlas_img.get_fdata.return_value = data

        ref_img = MagicMock()
        ref_img.shape = (1, 1, 2)

        result = check_and_resample_atlas(atlas_img, ref_img, "test_atlas")
        assert result.dtype == int
        np.testing.assert_array_equal(result, np.array([[[5, 3]]]))

    @patch("tit.atlas.overlap.check_and_resample_atlas.__module__", "tit.atlas.overlap")
    def test_mismatched_dimensions_triggers_resampling(self):
        """When shapes differ, resample_from_to should be called."""
        import sys

        # We need to mock nibabel and nibabel.processing inside the function
        nib_mock = sys.modules["nibabel"]
        nib_processing_mock = MagicMock()
        sys.modules["nibabel.processing"] = nib_processing_mock

        from tit.atlas.overlap import check_and_resample_atlas

        atlas_data = np.array([[[1.0, 2.0], [3.0, 4.0]]])  # (1,2,2)
        atlas_img = MagicMock()
        atlas_img.shape = (1, 2, 2)
        atlas_img.get_fdata.return_value = atlas_data
        atlas_img.affine = np.eye(4)

        ref_data = np.ones((2, 3, 4))  # different shape
        ref_img = MagicMock()
        ref_img.shape = (2, 3, 4)
        ref_img.get_fdata.return_value = ref_data
        ref_img.affine = np.eye(4)

        resampled_data = np.array([[[5, 6, 7], [8, 9, 10]]])
        resampled_img = MagicMock()
        resampled_img.get_fdata.return_value = resampled_data.astype(float)

        nib_processing_mock.resample_from_to.return_value = resampled_img

        result = check_and_resample_atlas(atlas_img, ref_img, "test_atlas")

        nib_processing_mock.resample_from_to.assert_called_once()
        assert result.dtype == int
        np.testing.assert_array_equal(result, resampled_data)

    def test_mismatched_dimensions_4d_reference(self):
        """When reference is 4D, the first volume should be extracted."""
        import sys

        nib_processing_mock = MagicMock()
        sys.modules["nibabel.processing"] = nib_processing_mock

        from tit.atlas.overlap import check_and_resample_atlas

        atlas_data = np.ones((2, 2, 2))
        atlas_img = MagicMock()
        atlas_img.shape = (2, 2, 2)
        atlas_img.get_fdata.return_value = atlas_data
        atlas_img.affine = np.eye(4)

        ref_data_4d = np.ones((3, 3, 3, 5))
        ref_img = MagicMock()
        ref_img.shape = (3, 3, 3, 5)
        ref_img.get_fdata.return_value = ref_data_4d
        ref_img.affine = np.eye(4)

        resampled_img = MagicMock()
        resampled_img.get_fdata.return_value = np.ones((3, 3, 3))
        nib_processing_mock.resample_from_to.return_value = resampled_img

        result = check_and_resample_atlas(atlas_img, ref_img, "test_atlas")

        assert result.shape == (3, 3, 3)
        assert result.dtype == int

    def test_mismatched_dimensions_4d_atlas(self):
        """When atlas is 4D and shapes differ, squeeze atlas before resampling."""
        import sys

        nib_processing_mock = MagicMock()
        sys.modules["nibabel.processing"] = nib_processing_mock

        from tit.atlas.overlap import check_and_resample_atlas

        atlas_data_4d = np.ones((2, 2, 2, 1))
        atlas_img = MagicMock()
        atlas_img.shape = (2, 2, 2)
        atlas_img.get_fdata.return_value = atlas_data_4d
        atlas_img.affine = np.eye(4)

        ref_data = np.ones((3, 3, 3))
        ref_img = MagicMock()
        ref_img.shape = (3, 3, 3)
        ref_img.get_fdata.return_value = ref_data
        ref_img.affine = np.eye(4)

        resampled_img = MagicMock()
        resampled_img.get_fdata.return_value = np.ones((3, 3, 3))
        nib_processing_mock.resample_from_to.return_value = resampled_img

        result = check_and_resample_atlas(atlas_img, ref_img, "test_atlas")

        assert result.dtype == int
        nib_processing_mock.resample_from_to.assert_called_once()


# ============================================================================
# overlap.py — atlas_overlap_analysis
# ============================================================================


@pytest.mark.unit
class TestAtlasOverlapAnalysis:
    """Tests for atlas_overlap_analysis."""

    @pytest.fixture(autouse=True)
    def _reset_nib_mock(self):
        """Reset nibabel mock state before each test to avoid leaks."""
        import sys
        nib_mock = sys.modules["nibabel"]
        nib_mock.load.side_effect = None
        nib_mock.load.reset_mock()
        yield

    def test_missing_atlas_file_skipped(self, tmp_path):
        """If atlas file does not exist, it is skipped with a warning."""
        from tit.atlas.overlap import atlas_overlap_analysis

        sig_mask = np.ones((2, 2, 2), dtype=bool)
        result = atlas_overlap_analysis(
            sig_mask,
            atlas_files=["nonexistent_atlas.nii.gz"],
            data_dir=str(tmp_path),
        )
        assert result == {}

    def test_no_atlas_files(self, tmp_path):
        """Empty atlas_files list returns empty dict."""
        from tit.atlas.overlap import atlas_overlap_analysis

        sig_mask = np.ones((2, 2, 2), dtype=bool)
        result = atlas_overlap_analysis(
            sig_mask,
            atlas_files=[],
            data_dir=str(tmp_path),
        )
        assert result == {}

    def test_single_atlas_no_overlap(self, tmp_path):
        """Atlas with no region overlapping the sig mask returns empty list."""
        import sys

        nib_mock = sys.modules["nibabel"]

        from tit.atlas.overlap import atlas_overlap_analysis

        # Create a dummy atlas file
        atlas_file = "test_atlas.nii.gz"
        (tmp_path / atlas_file).touch()

        # Atlas has region 1 in voxels where sig_mask is 0
        atlas_data = np.zeros((3, 3, 3))
        atlas_data[0, 0, 0] = 1  # region 1 is in one voxel

        sig_mask = np.zeros((3, 3, 3), dtype=bool)
        sig_mask[2, 2, 2] = True  # significant voxel in different location

        atlas_img = MagicMock()
        atlas_img.get_fdata.return_value = atlas_data
        nib_mock.load.return_value = atlas_img

        result = atlas_overlap_analysis(
            sig_mask,
            atlas_files=[atlas_file],
            data_dir=str(tmp_path),
        )

        assert atlas_file in result
        assert result[atlas_file] == []

    def test_single_atlas_with_overlap(self, tmp_path):
        """Atlas regions overlapping sig_mask are reported correctly."""
        import sys

        nib_mock = sys.modules["nibabel"]

        from tit.atlas.overlap import atlas_overlap_analysis

        atlas_file = "test_atlas.nii.gz"
        (tmp_path / atlas_file).touch()

        atlas_data = np.zeros((4, 4, 4))
        atlas_data[0, 0, 0] = 1
        atlas_data[0, 0, 1] = 1
        atlas_data[1, 0, 0] = 2
        atlas_data[1, 1, 0] = 2
        atlas_data[1, 1, 1] = 2

        sig_mask = np.zeros((4, 4, 4), dtype=bool)
        sig_mask[0, 0, 0] = True  # overlaps region 1
        sig_mask[1, 0, 0] = True  # overlaps region 2
        sig_mask[1, 1, 0] = True  # overlaps region 2

        atlas_img = MagicMock()
        atlas_img.get_fdata.return_value = atlas_data
        nib_mock.load.return_value = atlas_img

        result = atlas_overlap_analysis(
            sig_mask,
            atlas_files=[atlas_file],
            data_dir=str(tmp_path),
        )

        assert atlas_file in result
        regions = result[atlas_file]
        assert len(regions) == 2

        # Sorted by overlap_voxels descending: region 2 (2 voxels) then region 1 (1 voxel)
        assert regions[0]["region_id"] == 2
        assert regions[0]["overlap_voxels"] == 2
        assert regions[0]["region_size"] == 3
        assert regions[1]["region_id"] == 1
        assert regions[1]["overlap_voxels"] == 1
        assert regions[1]["region_size"] == 2

    def test_with_reference_img_calls_resample(self, tmp_path):
        """When reference_img is provided, check_and_resample_atlas is used."""
        import sys

        nib_mock = sys.modules["nibabel"]

        from tit.atlas.overlap import atlas_overlap_analysis

        atlas_file = "atlas.nii.gz"
        (tmp_path / atlas_file).touch()

        atlas_data = np.zeros((3, 3, 3))
        atlas_data[0, 0, 0] = 5

        atlas_img = MagicMock()
        atlas_img.get_fdata.return_value = atlas_data
        nib_mock.load.return_value = atlas_img

        reference_img = MagicMock()
        sig_mask = np.ones((3, 3, 3), dtype=bool)

        with patch(
            "tit.atlas.overlap.check_and_resample_atlas",
            return_value=atlas_data.astype(int),
        ) as mock_resample:
            result = atlas_overlap_analysis(
                sig_mask,
                atlas_files=[atlas_file],
                data_dir=str(tmp_path),
                reference_img=reference_img,
            )
            mock_resample.assert_called_once_with(atlas_img, reference_img, atlas_file)

        assert atlas_file in result

    def test_multiple_atlas_files(self, tmp_path):
        """Multiple atlas files are each processed."""
        import sys

        nib_mock = sys.modules["nibabel"]

        from tit.atlas.overlap import atlas_overlap_analysis

        atlas1 = "atlas1.nii.gz"
        atlas2 = "atlas2.nii.gz"
        (tmp_path / atlas1).touch()
        (tmp_path / atlas2).touch()

        data1 = np.zeros((2, 2, 2))
        data1[0, 0, 0] = 1

        data2 = np.zeros((2, 2, 2))
        data2[1, 1, 1] = 3

        img1 = MagicMock()
        img1.get_fdata.return_value = data1
        img2 = MagicMock()
        img2.get_fdata.return_value = data2

        nib_mock.load.side_effect = [img1, img2]

        sig_mask = np.ones((2, 2, 2), dtype=bool)

        result = atlas_overlap_analysis(
            sig_mask,
            atlas_files=[atlas1, atlas2],
            data_dir=str(tmp_path),
        )

        assert atlas1 in result
        assert atlas2 in result
        assert len(result[atlas1]) == 1
        assert result[atlas1][0]["region_id"] == 1
        assert len(result[atlas2]) == 1
        assert result[atlas2][0]["region_id"] == 3

    def test_mixed_existing_and_missing(self, tmp_path):
        """Mix of existing and missing atlas files: only existing ones appear."""
        import sys

        nib_mock = sys.modules["nibabel"]
        nib_mock.load.side_effect = None  # clear leaked side_effect

        from tit.atlas.overlap import atlas_overlap_analysis

        existing = "exists.nii.gz"
        (tmp_path / existing).touch()

        atlas_data = np.zeros((2, 2, 2))
        atlas_data[0, 0, 0] = 1

        atlas_img = MagicMock()
        atlas_img.get_fdata.return_value = atlas_data
        nib_mock.load.return_value = atlas_img

        sig_mask = np.ones((2, 2, 2), dtype=bool)

        result = atlas_overlap_analysis(
            sig_mask,
            atlas_files=["missing.nii.gz", existing],
            data_dir=str(tmp_path),
        )

        assert "missing.nii.gz" not in result
        assert existing in result

    def test_results_sorted_by_overlap_descending(self, tmp_path):
        """Region overlap counts are sorted in descending order."""
        import sys

        nib_mock = sys.modules["nibabel"]
        nib_mock.load.side_effect = None  # clear leaked side_effect

        from tit.atlas.overlap import atlas_overlap_analysis

        atlas_file = "sorted_test.nii.gz"
        (tmp_path / atlas_file).touch()

        # Region 1: 1 voxel overlap, Region 2: 3 voxel overlap, Region 3: 2 voxels
        atlas_data = np.zeros((4, 4, 4))
        atlas_data[0, 0, 0] = 1
        atlas_data[1, 0, 0] = 2
        atlas_data[1, 1, 0] = 2
        atlas_data[1, 1, 1] = 2
        atlas_data[2, 0, 0] = 3
        atlas_data[2, 1, 0] = 3

        sig_mask = np.ones((4, 4, 4), dtype=bool)

        atlas_img = MagicMock()
        atlas_img.get_fdata.return_value = atlas_data
        nib_mock.load.return_value = atlas_img

        result = atlas_overlap_analysis(
            sig_mask,
            atlas_files=[atlas_file],
            data_dir=str(tmp_path),
        )

        regions = result[atlas_file]
        assert len(regions) == 3
        assert regions[0]["region_id"] == 2
        assert regions[0]["overlap_voxels"] == 3
        assert regions[1]["region_id"] == 3
        assert regions[1]["overlap_voxels"] == 2
        assert regions[2]["region_id"] == 1
        assert regions[2]["overlap_voxels"] == 1

    def test_atlas_without_reference_uses_raw_data(self, tmp_path):
        """Without reference_img, atlas data is used directly as int."""
        import sys

        nib_mock = sys.modules["nibabel"]
        nib_mock.load.side_effect = None  # clear leaked side_effect

        from tit.atlas.overlap import atlas_overlap_analysis

        atlas_file = "raw.nii.gz"
        (tmp_path / atlas_file).touch()

        atlas_data = np.array([[[7.0]]])  # float data
        atlas_img = MagicMock()
        atlas_img.get_fdata.return_value = atlas_data
        nib_mock.load.return_value = atlas_img

        sig_mask = np.ones((1, 1, 1), dtype=bool)

        result = atlas_overlap_analysis(
            sig_mask,
            atlas_files=[atlas_file],
            data_dir=str(tmp_path),
            reference_img=None,
        )

        assert atlas_file in result
        assert len(result[atlas_file]) == 1
        assert result[atlas_file][0]["region_id"] == 7


# ============================================================================
# voxel.py — VoxelAtlasManager
# ============================================================================


@pytest.mark.unit
class TestVoxelAtlasManagerInit:
    """Tests for VoxelAtlasManager construction."""

    def test_default_construction(self):
        from tit.atlas.voxel import VoxelAtlasManager

        mgr = VoxelAtlasManager()
        assert mgr.freesurfer_mri_dir == ""
        assert mgr.seg_dir == ""

    def test_construction_with_paths(self, tmp_path):
        from tit.atlas.voxel import VoxelAtlasManager

        mgr = VoxelAtlasManager(
            freesurfer_mri_dir=str(tmp_path / "mri"),
            seg_dir=str(tmp_path / "seg"),
        )
        assert mgr.freesurfer_mri_dir == str(tmp_path / "mri")
        assert mgr.seg_dir == str(tmp_path / "seg")


@pytest.mark.unit
class TestVoxelAtlasManagerListAtlases:
    """Tests for VoxelAtlasManager.list_atlases."""

    def test_empty_dirs_returns_empty(self):
        from tit.atlas.voxel import VoxelAtlasManager

        mgr = VoxelAtlasManager()
        assert mgr.list_atlases() == []

    def test_nonexistent_freesurfer_dir(self):
        from tit.atlas.voxel import VoxelAtlasManager

        mgr = VoxelAtlasManager(freesurfer_mri_dir="/nonexistent/mri")
        assert mgr.list_atlases() == []

    def test_discovers_voxel_atlas_files(self, tmp_path):
        """Discovers atlas files from VOXEL_ATLAS_FILES list."""
        from tit.atlas.voxel import VoxelAtlasManager
        from tit.atlas.constants import VOXEL_ATLAS_FILES

        mri_dir = tmp_path / "mri"
        mri_dir.mkdir()

        # Create two atlas files
        (mri_dir / VOXEL_ATLAS_FILES[0]).touch()
        (mri_dir / VOXEL_ATLAS_FILES[1]).touch()

        mgr = VoxelAtlasManager(freesurfer_mri_dir=str(mri_dir))
        results = mgr.list_atlases()

        assert len(results) == 2
        names = [name for name, _ in results]
        assert VOXEL_ATLAS_FILES[0] in names
        assert VOXEL_ATLAS_FILES[1] in names

    def test_returns_tuples_of_name_and_path(self, tmp_path):
        """Each result is a (display_name, full_path) tuple."""
        from tit.atlas.voxel import VoxelAtlasManager
        from tit.atlas.constants import VOXEL_ATLAS_FILES

        mri_dir = tmp_path / "mri"
        mri_dir.mkdir()
        (mri_dir / VOXEL_ATLAS_FILES[0]).touch()

        mgr = VoxelAtlasManager(freesurfer_mri_dir=str(mri_dir))
        results = mgr.list_atlases()

        assert len(results) == 1
        name, path = results[0]
        assert name == VOXEL_ATLAS_FILES[0]
        assert path == os.path.join(str(mri_dir), VOXEL_ATLAS_FILES[0])

    def test_discovers_labeling_file(self, tmp_path):
        """Discovers labeling.nii.gz in seg_dir."""
        from tit.atlas.voxel import VoxelAtlasManager

        seg_dir = tmp_path / "seg"
        seg_dir.mkdir()
        (seg_dir / "labeling.nii.gz").touch()

        mgr = VoxelAtlasManager(seg_dir=str(seg_dir))
        results = mgr.list_atlases()

        assert len(results) == 1
        assert results[0] == ("labeling.nii.gz", os.path.join(str(seg_dir), "labeling.nii.gz"))

    def test_labeling_missing_not_included(self, tmp_path):
        """If labeling.nii.gz is absent, it is not in results."""
        from tit.atlas.voxel import VoxelAtlasManager

        seg_dir = tmp_path / "seg"
        seg_dir.mkdir()

        mgr = VoxelAtlasManager(seg_dir=str(seg_dir))
        results = mgr.list_atlases()
        assert results == []

    def test_both_dirs_combined(self, tmp_path):
        """Results combine FreeSurfer and segmentation atlases."""
        from tit.atlas.voxel import VoxelAtlasManager
        from tit.atlas.constants import VOXEL_ATLAS_FILES

        mri_dir = tmp_path / "mri"
        mri_dir.mkdir()
        (mri_dir / VOXEL_ATLAS_FILES[0]).touch()

        seg_dir = tmp_path / "seg"
        seg_dir.mkdir()
        (seg_dir / "labeling.nii.gz").touch()

        mgr = VoxelAtlasManager(
            freesurfer_mri_dir=str(mri_dir),
            seg_dir=str(seg_dir),
        )
        results = mgr.list_atlases()

        assert len(results) == 2
        names = [n for n, _ in results]
        assert VOXEL_ATLAS_FILES[0] in names
        assert "labeling.nii.gz" in names

    def test_no_atlas_files_present(self, tmp_path):
        """Empty mri dir returns no FreeSurfer atlases."""
        from tit.atlas.voxel import VoxelAtlasManager

        mri_dir = tmp_path / "mri"
        mri_dir.mkdir()

        mgr = VoxelAtlasManager(freesurfer_mri_dir=str(mri_dir))
        results = mgr.list_atlases()
        assert results == []

    def test_empty_seg_dir_string(self):
        """Empty string seg_dir does not trigger labeling check."""
        from tit.atlas.voxel import VoxelAtlasManager

        mgr = VoxelAtlasManager(seg_dir="")
        results = mgr.list_atlases()
        assert results == []


@pytest.mark.unit
class TestVoxelAtlasManagerListRegions:
    """Tests for VoxelAtlasManager.list_regions."""

    def test_reads_cached_labels_file(self, tmp_path):
        """When labels file exists, it is read without running mri_segstats."""
        from tit.atlas.voxel import VoxelAtlasManager

        atlas_path = str(tmp_path / "aparc.DKTatlas+aseg.mgz")
        labels_file = tmp_path / "aparc.DKTatlas+aseg_labels.txt"
        labels_file.write_text(
            "# ColHeaders\n"
            "# More header\n"
            " 1   2    1000   50.0  Left-Cerebellum-Cortex\n"
            " 2   47   2000   60.0  Right-Cerebellum-Cortex\n"
        )

        mgr = VoxelAtlasManager()
        regions = mgr.list_regions(atlas_path)

        assert "Left-Cerebellum-Cortex (ID: 2)" in regions
        assert "Right-Cerebellum-Cortex (ID: 47)" in regions
        assert len(regions) == 2

    def test_sorted_and_deduplicated(self, tmp_path):
        """Regions are sorted and deduplicated."""
        from tit.atlas.voxel import VoxelAtlasManager

        atlas_path = str(tmp_path / "test.mgz")
        labels_file = tmp_path / "test_labels.txt"
        labels_file.write_text(
            "# header\n"
            " 1   5    1000   50.0  Hippocampus\n"
            " 2   3    2000   60.0  Amygdala\n"
            " 3   5    1000   50.0  Hippocampus\n"
        )

        mgr = VoxelAtlasManager()
        regions = mgr.list_regions(atlas_path)

        assert regions == sorted(set(regions))
        assert len(regions) == 2  # Hippocampus deduplicated

    def test_handles_nii_gz_extension(self, tmp_path):
        """Atlas with .nii.gz extension resolves correct labels file name."""
        from tit.atlas.voxel import VoxelAtlasManager

        atlas_path = str(tmp_path / "myatlas.nii.gz")
        labels_file = tmp_path / "myatlas_labels.txt"
        labels_file.write_text(
            "# header\n"
            " 1   10   500   30.0  Thalamus\n"
        )

        mgr = VoxelAtlasManager()
        regions = mgr.list_regions(atlas_path)

        assert "Thalamus (ID: 10)" in regions

    def test_runs_mri_segstats_when_no_cache(self, tmp_path):
        """When labels file does not exist, mri_segstats is called."""
        from tit.atlas.voxel import VoxelAtlasManager

        atlas_path = str(tmp_path / "test.mgz")
        labels_file = tmp_path / "test_labels.txt"

        mgr = VoxelAtlasManager()

        def fake_subprocess_run(cmd, check, capture_output):
            # Write labels file as mri_segstats would
            labels_file.write_text(
                "# header\n"
                " 1   42   800   40.0  Putamen\n"
            )

        with patch("tit.atlas.voxel.subprocess.run", side_effect=fake_subprocess_run):
            regions = mgr.list_regions(atlas_path)

        assert "Putamen (ID: 42)" in regions

    def test_mri_segstats_called_with_correct_args(self, tmp_path):
        """Verify the exact command passed to subprocess.run."""
        from tit.atlas.voxel import VoxelAtlasManager

        atlas_path = str(tmp_path / "brain.mgz")
        labels_file = tmp_path / "brain_labels.txt"

        mgr = VoxelAtlasManager()

        def fake_run(cmd, check, capture_output):
            labels_file.write_text("# header\n 1 1 100 10.0 Region1\n")

        with patch("tit.atlas.voxel.subprocess.run", side_effect=fake_run) as mock_run:
            mgr.list_regions(atlas_path)
            mock_run.assert_called_once()
            call_cmd = mock_run.call_args[0][0]
            assert call_cmd[0] == "mri_segstats"
            assert "--seg" in call_cmd
            assert atlas_path in call_cmd
            assert "--excludeid" in call_cmd
            assert "0" in call_cmd
            assert "--ctab-default" in call_cmd
            assert "--sum" in call_cmd

    def test_empty_labels_file(self, tmp_path):
        """An empty labels file (all headers) returns empty list."""
        from tit.atlas.voxel import VoxelAtlasManager

        atlas_path = str(tmp_path / "empty.mgz")
        labels_file = tmp_path / "empty_labels.txt"
        labels_file.write_text("# header line 1\n# header line 2\n")

        mgr = VoxelAtlasManager()
        regions = mgr.list_regions(atlas_path)
        assert regions == []

    def test_skips_lines_with_few_parts(self, tmp_path):
        """Lines with fewer than 5 columns are skipped."""
        from tit.atlas.voxel import VoxelAtlasManager

        atlas_path = str(tmp_path / "partial.mgz")
        labels_file = tmp_path / "partial_labels.txt"
        labels_file.write_text(
            "# header\n"
            "short line\n"
            " 1   10   500   30.0  ValidRegion\n"
            "a b c\n"
        )

        mgr = VoxelAtlasManager()
        regions = mgr.list_regions(atlas_path)
        assert len(regions) == 1
        assert "ValidRegion (ID: 10)" in regions

    def test_multiword_region_names(self, tmp_path):
        """Region names with spaces are correctly joined."""
        from tit.atlas.voxel import VoxelAtlasManager

        atlas_path = str(tmp_path / "multi.mgz")
        labels_file = tmp_path / "multi_labels.txt"
        labels_file.write_text(
            "# header\n"
            " 1   99   500   30.0  Left Superior Temporal Gyrus\n"
        )

        mgr = VoxelAtlasManager()
        regions = mgr.list_regions(atlas_path)
        assert "Left Superior Temporal Gyrus (ID: 99)" in regions


@pytest.mark.unit
class TestVoxelAtlasManagerDetectMniAtlases:
    """Tests for VoxelAtlasManager.detect_mni_atlases (static method)."""

    def test_nonexistent_directory(self):
        from tit.atlas.voxel import VoxelAtlasManager

        result = VoxelAtlasManager.detect_mni_atlases("/nonexistent/dir")
        assert result == []

    def test_empty_directory(self, tmp_path):
        """No MNI atlas files present returns empty list."""
        from tit.atlas.voxel import VoxelAtlasManager

        result = VoxelAtlasManager.detect_mni_atlases(str(tmp_path))
        assert result == []

    def test_discovers_mni_atlases(self, tmp_path):
        """Detects MNI atlas files from the MNI_ATLAS_FILES list."""
        from tit.atlas.voxel import VoxelAtlasManager
        from tit.atlas.constants import MNI_ATLAS_FILES

        for f in MNI_ATLAS_FILES:
            (tmp_path / f).touch()

        result = VoxelAtlasManager.detect_mni_atlases(str(tmp_path))

        assert len(result) == len(MNI_ATLAS_FILES)
        for f in MNI_ATLAS_FILES:
            assert os.path.join(str(tmp_path), f) in result

    def test_partial_mni_atlases(self, tmp_path):
        """Only files that actually exist are returned."""
        from tit.atlas.voxel import VoxelAtlasManager
        from tit.atlas.constants import MNI_ATLAS_FILES

        # Create only the first MNI atlas file
        (tmp_path / MNI_ATLAS_FILES[0]).touch()

        result = VoxelAtlasManager.detect_mni_atlases(str(tmp_path))

        assert len(result) == 1
        assert os.path.join(str(tmp_path), MNI_ATLAS_FILES[0]) in result

    def test_returns_full_paths(self, tmp_path):
        """Returned paths are full (absolute) paths."""
        from tit.atlas.voxel import VoxelAtlasManager
        from tit.atlas.constants import MNI_ATLAS_FILES

        (tmp_path / MNI_ATLAS_FILES[0]).touch()

        result = VoxelAtlasManager.detect_mni_atlases(str(tmp_path))

        for path in result:
            assert os.path.isabs(path)


@pytest.mark.unit
class TestVoxelAtlasManagerFindLabelingLut:
    """Tests for VoxelAtlasManager.find_labeling_lut."""

    def test_lut_found(self, tmp_path):
        """Returns path when labeling_LUT.txt exists."""
        from tit.atlas.voxel import VoxelAtlasManager

        seg_dir = tmp_path / "seg"
        seg_dir.mkdir()
        (seg_dir / "labeling_LUT.txt").touch()

        mgr = VoxelAtlasManager(seg_dir=str(seg_dir))
        result = mgr.find_labeling_lut()

        assert result == os.path.join(str(seg_dir), "labeling_LUT.txt")

    def test_lut_not_found(self, tmp_path):
        """Returns None when labeling_LUT.txt does not exist."""
        from tit.atlas.voxel import VoxelAtlasManager

        seg_dir = tmp_path / "seg"
        seg_dir.mkdir()

        mgr = VoxelAtlasManager(seg_dir=str(seg_dir))
        result = mgr.find_labeling_lut()

        assert result is None

    def test_lut_with_empty_seg_dir(self):
        """Empty seg_dir path returns None (file won't exist)."""
        from tit.atlas.voxel import VoxelAtlasManager

        mgr = VoxelAtlasManager(seg_dir="")
        result = mgr.find_labeling_lut()
        assert result is None


# ============================================================================
# mesh.py — MeshAtlasManager.list_regions
# ============================================================================


@pytest.mark.unit
class TestMeshListRegions:
    """Tests for MeshAtlasManager.list_regions (lines 39-63)."""

    def test_both_hemispheres_bytes_names_filters_unknown(self, tmp_path):
        """Both hemispheres match, bytes names are decoded, 'unknown' is filtered."""
        import sys

        from tit.atlas.mesh import MeshAtlasManager

        # Create .annot files for both hemispheres
        (tmp_path / "lh.aparc_DK40.annot").touch()
        (tmp_path / "rh.aparc_DK40.annot").touch()

        nfs_mock = sys.modules["nibabel.freesurfer"]
        nfs_mock.read_annot.return_value = (
            None,  # labels
            None,  # ctab
            [b"unknown", b"precentral", b"postcentral"],
        )

        mgr = MeshAtlasManager(str(tmp_path))
        regions = mgr.list_regions("DK40")

        assert "precentral-lh" in regions
        assert "postcentral-lh" in regions
        assert "precentral-rh" in regions
        assert "postcentral-rh" in regions
        # "unknown" must be filtered out
        assert "unknown-lh" not in regions
        assert "unknown-rh" not in regions
        # Should be sorted
        assert regions == sorted(regions)

    def test_single_hemisphere_match(self, tmp_path):
        """Only lh has a matching .annot file; rh is skipped."""
        import sys

        from tit.atlas.mesh import MeshAtlasManager

        (tmp_path / "lh.aparc_DK40.annot").touch()
        # No rh file

        nfs_mock = sys.modules["nibabel.freesurfer"]
        nfs_mock.read_annot.return_value = (
            None,
            None,
            [b"unknown", b"superiorfrontal"],
        )

        mgr = MeshAtlasManager(str(tmp_path))
        regions = mgr.list_regions("DK40")

        assert "superiorfrontal-lh" in regions
        assert len(regions) == 1  # only lh regions, unknown filtered

    def test_no_matching_files_returns_empty(self, tmp_path):
        """No .annot files match the atlas name -> returns []."""
        from tit.atlas.mesh import MeshAtlasManager

        # Create files that don't match the requested atlas
        (tmp_path / "lh.aparc_OTHER.annot").touch()

        mgr = MeshAtlasManager(str(tmp_path))
        regions = mgr.list_regions("DK40")

        assert regions == []

    def test_nonexistent_seg_dir_returns_empty(self):
        """seg_dir does not exist -> returns []."""
        from tit.atlas.mesh import MeshAtlasManager

        mgr = MeshAtlasManager("/nonexistent/path/to/segmentation")
        regions = mgr.list_regions("DK40")

        assert regions == []

    def test_str_names_not_bytes(self, tmp_path):
        """Region names as str (not bytes) are handled via str() path."""
        import sys

        from tit.atlas.mesh import MeshAtlasManager

        (tmp_path / "lh.aparc_DK40.annot").touch()

        nfs_mock = sys.modules["nibabel.freesurfer"]
        nfs_mock.read_annot.return_value = (
            None,
            None,
            ["unknown", "insula", "fusiform"],  # str, not bytes
        )

        mgr = MeshAtlasManager(str(tmp_path))
        regions = mgr.list_regions("DK40")

        assert "insula-lh" in regions
        assert "fusiform-lh" in regions
        assert "unknown-lh" not in regions

    def test_empty_directory_no_annot_files(self, tmp_path):
        """Directory exists but contains no .annot files -> returns []."""
        from tit.atlas.mesh import MeshAtlasManager

        mgr = MeshAtlasManager(str(tmp_path))
        regions = mgr.list_regions("DK40")

        assert regions == []


# ============================================================================
# mesh.py — MeshAtlasManager.list_annot_regions
# ============================================================================


@pytest.mark.unit
class TestMeshListAnnotRegions:
    """Tests for MeshAtlasManager.list_annot_regions (lines 99-112)."""

    def test_bytes_names(self, tmp_path):
        """Bytes region names are decoded to str."""
        import sys

        from tit.atlas.mesh import MeshAtlasManager

        # Ensure nibabel.freesurfer.io is in sys.modules
        nfs_mock = sys.modules["nibabel.freesurfer"]
        fsio_mock = MagicMock()
        sys.modules["nibabel.freesurfer.io"] = fsio_mock
        setattr(nfs_mock, "io", fsio_mock)

        fsio_mock.read_annot.return_value = (
            None,  # labels
            None,  # ctab
            [b"bankssts", b"caudalanteriorcingulate", b"unknown"],
        )

        mgr = MeshAtlasManager(str(tmp_path))
        result = mgr.list_annot_regions("/fake/path/lh.aparc.annot")

        assert result == [
            (0, "bankssts"),
            (1, "caudalanteriorcingulate"),
            (2, "unknown"),
        ]
        fsio_mock.read_annot.assert_called_once_with("/fake/path/lh.aparc.annot")

    def test_str_names(self, tmp_path):
        """String region names are passed through via str()."""
        import sys

        from tit.atlas.mesh import MeshAtlasManager

        nfs_mock = sys.modules["nibabel.freesurfer"]
        fsio_mock = MagicMock()
        sys.modules["nibabel.freesurfer.io"] = fsio_mock
        setattr(nfs_mock, "io", fsio_mock)

        fsio_mock.read_annot.return_value = (
            None,
            None,
            ["regionA", "regionB"],
        )

        mgr = MeshAtlasManager(str(tmp_path))
        result = mgr.list_annot_regions("/any/path.annot")

        assert result == [(0, "regionA"), (1, "regionB")]

    def test_returns_correct_index_tuples(self, tmp_path):
        """Indices match enumeration order of names list."""
        import sys

        from tit.atlas.mesh import MeshAtlasManager

        nfs_mock = sys.modules["nibabel.freesurfer"]
        fsio_mock = MagicMock()
        sys.modules["nibabel.freesurfer.io"] = fsio_mock
        setattr(nfs_mock, "io", fsio_mock)

        names = [b"alpha", b"beta", b"gamma", b"delta"]
        fsio_mock.read_annot.return_value = (None, None, names)

        mgr = MeshAtlasManager(str(tmp_path))
        result = mgr.list_annot_regions("/some/annot/file.annot")

        assert len(result) == 4
        for i, (idx, name) in enumerate(result):
            assert idx == i
            assert name == names[i].decode("utf-8")

    def test_empty_names_list(self, tmp_path):
        """Empty names list returns empty result."""
        import sys

        from tit.atlas.mesh import MeshAtlasManager

        nfs_mock = sys.modules["nibabel.freesurfer"]
        fsio_mock = MagicMock()
        sys.modules["nibabel.freesurfer.io"] = fsio_mock
        setattr(nfs_mock, "io", fsio_mock)

        fsio_mock.read_annot.return_value = (None, None, [])

        mgr = MeshAtlasManager(str(tmp_path))
        result = mgr.list_annot_regions("/any/path.annot")

        assert result == []
