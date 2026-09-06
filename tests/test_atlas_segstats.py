#!/usr/bin/env python3
"""Unit tests for tit/atlas/segstats.py.

Pure-Python replacement for ``mri_segstats``: labels present in a voxel
atlas, named via a LUT, with voxel counts/volumes computed from the array.
nibabel is mocked at the module level for the whole suite (see
tests/conftest.py), so these tests configure ``nibabel.load``'s return
value with real numpy arrays for ``.dataobj``/``.affine`` -- matching the
pattern used throughout tests/test_atlas_coverage.py.

Voxel-for-voxel validation against live ``mri_segstats`` on real recon-all
and charm data lives in dev/spikes/native/fs-binaries/REPORT.md (this suite
covers the pure-function contract, not that live comparison).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tit.atlas.segstats import (
    SegStat,
    compute_segstats,
    format_segstats_sum,
    load_lut,
    resolve_lut_for_atlas,
    write_segstats_sum,
)

# ============================================================================
# load_lut
# ============================================================================


@pytest.mark.unit
class TestLoadLut:
    def test_parses_id_name_rgb(self, tmp_path):
        lut_path = tmp_path / "colors.txt"
        lut_path.write_text(
            "#$Id: fake\n"
            "\n"
            "0   Unknown                 0   0   0   0\n"
            "10  Left-Thalamus-Proper    0   118 14  0\n"
        )
        lut = load_lut(str(lut_path))
        assert lut == {0: "Unknown", 10: "Left-Thalamus-Proper"}

    def test_multiword_name(self, tmp_path):
        lut_path = tmp_path / "lut.txt"
        lut_path.write_text("1002 ctx-lh-caudalanteriorcingulate 125 100 160 0\n")
        lut = load_lut(str(lut_path))
        assert lut[1002] == "ctx-lh-caudalanteriorcingulate"

    def test_name_with_internal_spaces(self, tmp_path):
        """A name split across whitespace-separated tokens is rejoined."""
        lut_path = tmp_path / "lut.txt"
        lut_path.write_text("99 Left Superior Temporal Gyrus 1 2 3\n")
        lut = load_lut(str(lut_path))
        assert lut[99] == "Left Superior Temporal Gyrus"

    def test_missing_file_returns_empty(self):
        assert load_lut("/nonexistent/lut.txt") == {}

    def test_empty_path_returns_empty(self):
        assert load_lut("") == {}

    def test_skips_comments_and_blank_lines(self, tmp_path):
        lut_path = tmp_path / "lut.txt"
        lut_path.write_text("# comment\n\n5 Region 1 2 3\n")
        assert load_lut(str(lut_path)) == {5: "Region"}

    def test_negative_id_supported(self, tmp_path):
        lut_path = tmp_path / "lut.txt"
        lut_path.write_text("-1 Undetermined\n")
        assert load_lut(str(lut_path)) == {-1: "Undetermined"}


# ============================================================================
# resolve_lut_for_atlas
# ============================================================================


@pytest.mark.unit
class TestResolveLutForAtlas:
    def test_labeling_nii_gz_uses_sidecar_lut(self, tmp_path):
        atlas_path = tmp_path / "labeling.nii.gz"
        atlas_path.touch()
        (tmp_path / "labeling_LUT.txt").write_text("10 Left-Thalamus-Proper\n")

        lut = resolve_lut_for_atlas(str(atlas_path))
        assert lut == {10: "Left-Thalamus-Proper"}

    def test_generic_atlas_uses_stem_lut_sidecar(self, tmp_path):
        atlas_path = tmp_path / "MorelMNI152_labeling_1mm.nii.gz"
        atlas_path.touch()
        (tmp_path / "MorelMNI152_labeling_1mm_LUT.txt").write_text("1 Pulvinar\n")

        lut = resolve_lut_for_atlas(str(atlas_path))
        assert lut == {1: "Pulvinar"}

    def test_falls_back_to_bundled_freesurfer_lut(self, tmp_path):
        """No sidecar at all: falls back to resources/atlas/FreeSurferColorLUT.txt."""
        atlas_path = tmp_path / "aparc.DKTatlas+aseg.mgz"
        atlas_path.touch()

        lut = resolve_lut_for_atlas(str(atlas_path))
        # Standard FreeSurfer aseg id, present in the bundled table.
        assert lut.get(17) == "Left-Hippocampus"

    def test_does_not_treat_labels_txt_cache_as_a_lut(self, tmp_path):
        """A `{stem}_labels.txt` mri_segstats-format cache is not a colour table.

        If it were mis-parsed as a LUT, "Index"/"NVoxels"/"Volume_mm3" would
        leak into region names -- see the module docstring's warning.
        """
        atlas_path = tmp_path / "custom.mgz"
        atlas_path.touch()
        (tmp_path / "custom_labels.txt").write_text(
            "  1     7        100      100.0000 Region\n"
        )

        lut = resolve_lut_for_atlas(str(atlas_path))
        # If custom_labels.txt were mis-parsed as a LUT, its Index column (1)
        # would map to "100.0000 Region" (NVoxels/Volume_mm3 swallowed into
        # the "name"). It must not: the fallback bundled table wins instead.
        assert "100.0000 Region" not in lut.values()
        assert lut.get(1) != "100.0000 Region"


# ============================================================================
# resolve_lut_for_atlas -- legacy ThalamicNuclei atlas family
#
# FX3 item 2 / qa-neuro-researcher-notes.md #2: ThalamicNuclei.v13.T1.mgz's 8100s/8200s ids
# used to fall through to the bundled FreeSurferColorLUT.txt (which has no entries in that
# range) and resolve to placeholder "Label 8103"-style names. resources/atlas/ThalamicNuclei_LUT.txt
# is the fix: FreeSurfer's own id -> name table for this atlas (see that file's header for the
# source and citation).
# ============================================================================


@pytest.mark.unit
class TestThalamicNucleiLut:
    def test_resolves_via_the_vendored_table_with_no_sidecar_present(self, tmp_path):
        atlas_path = tmp_path / "ThalamicNuclei.v13.T1.mgz"
        atlas_path.touch()

        lut = resolve_lut_for_atlas(str(atlas_path))
        assert lut.get(8103) == "Left-AV"
        assert lut.get(8203) == "Right-AV"

    def test_fsvoxelspace_sibling_also_resolves(self, tmp_path):
        atlas_path = tmp_path / "ThalamicNuclei.v13.T1.FSvoxelSpace.mgz"
        atlas_path.touch()

        lut = resolve_lut_for_atlas(str(atlas_path))
        assert lut.get(8103) == "Left-AV"

    def test_a_real_atlas_specific_sidecar_still_wins_over_the_vendored_table(
        self, tmp_path
    ):
        atlas_path = tmp_path / "ThalamicNuclei.v13.T1.mgz"
        atlas_path.touch()
        (tmp_path / "ThalamicNuclei.v13.T1_LUT.txt").write_text(
            "8103 Custom-Override\n"
        )

        lut = resolve_lut_for_atlas(str(atlas_path))
        assert lut == {8103: "Custom-Override"}

    def test_all_48_real_ernie_label_ids_resolve_to_a_real_name_not_a_placeholder(
        self, tmp_path
    ):
        # The exact set of unique nonzero voxel ids present in sub-ernie's real
        # derivatives/freesurfer/sub-ernie/mri/ThalamicNuclei.v13.T1.mgz (recorded via
        # nibabel's np.unique on the real file, qa-neuro-researcher-notes.md #2's own repro
        # case) -- not the full 8100s/8200s id space (some small nuclei carry zero voxels for
        # a given subject and so never appear here), but every one of these must resolve.
        ernie_ids = [
            8103,
            8104,
            8105,
            8106,
            8108,
            8109,
            8110,
            8111,
            8112,
            8113,
            8115,
            8116,
            8117,
            8118,
            8120,
            8121,
            8122,
            8123,
            8126,
            8127,
            8128,
            8129,
            8130,
            8133,
            8203,
            8204,
            8205,
            8206,
            8208,
            8209,
            8210,
            8211,
            8212,
            8213,
            8215,
            8216,
            8217,
            8218,
            8220,
            8221,
            8222,
            8223,
            8226,
            8227,
            8228,
            8229,
            8230,
            8233,
        ]
        assert len(ernie_ids) == 48

        atlas_path = tmp_path / "ThalamicNuclei.v13.T1.mgz"
        atlas_path.touch()
        lut = resolve_lut_for_atlas(str(atlas_path))

        for seg_id in ernie_ids:
            name = lut.get(seg_id)
            assert name is not None, seg_id
            assert not name.startswith("Label "), (seg_id, name)
        # Spot-check a few against the real ThalamicNuclei.v13.T1.volumes.txt sidecar sitting
        # next to ernie's atlas (names only, no ids -- see the LUT file's header for why that
        # file cannot itself supply the id mapping).
        assert lut[8106] == "Left-CM"
        assert lut[8109] == "Left-LGN"
        assert lut[8133] == "Left-VPL"
        assert lut[8233] == "Right-VPL"

    def test_an_unrelated_atlas_named_thalamicnuclei_prefixed_still_only_uses_it_as_fallback(
        self, tmp_path
    ):
        # The vendored table is tried after a real sidecar, same precedence as every other
        # atlas family (see test_a_real_atlas_specific_sidecar_still_wins_over_the_vendored_table).
        atlas_path = tmp_path / "ThalamicNucleiSomethingElse.mgz"
        atlas_path.touch()
        lut = resolve_lut_for_atlas(str(atlas_path))
        assert lut.get(8103) == "Left-AV"


# ============================================================================
# compute_segstats
# ============================================================================


@pytest.mark.unit
class TestComputeSegstats:
    def test_counts_and_volumes_from_unit_affine(self, tmp_path):
        atlas_img = MagicMock()
        atlas_img.dataobj = np.array([[[0, 5, 5], [5, 0, 3]]], dtype=np.int32)
        atlas_img.affine = np.eye(4)  # 1 mm^3 voxels

        with patch("nibabel.load", return_value=atlas_img):
            stats = compute_segstats(
                str(tmp_path / "atlas.mgz"), lut={5: "Foo", 3: "Bar"}
            )

        assert stats == [
            SegStat(seg_id=3, name="Bar", n_voxels=1, volume_mm3=1.0),
            SegStat(seg_id=5, name="Foo", n_voxels=3, volume_mm3=3.0),
        ]

    def test_excludes_background_zero(self, tmp_path):
        atlas_img = MagicMock()
        atlas_img.dataobj = np.zeros((2, 2, 2), dtype=np.int32)
        atlas_img.affine = np.eye(4)

        with patch("nibabel.load", return_value=atlas_img):
            stats = compute_segstats(str(tmp_path / "empty.mgz"))

        assert stats == []

    def test_unresolved_label_gets_placeholder_name(self, tmp_path):
        atlas_img = MagicMock()
        atlas_img.dataobj = np.array([[[9]]], dtype=np.int32)
        atlas_img.affine = np.eye(4)

        with patch("nibabel.load", return_value=atlas_img):
            stats = compute_segstats(str(tmp_path / "atlas.mgz"), lut={})

        assert stats == [SegStat(seg_id=9, name="Label 9", n_voxels=1, volume_mm3=1.0)]

    def test_non_unit_voxel_volume(self, tmp_path):
        """Volume scales with |det(affine[:3, :3])|, not just voxel count."""
        atlas_img = MagicMock()
        atlas_img.dataobj = np.array([[[4, 4]]], dtype=np.int32)
        affine = np.diag([2.0, 2.0, 2.0, 1.0])  # 8 mm^3 voxels
        atlas_img.affine = affine

        with patch("nibabel.load", return_value=atlas_img):
            stats = compute_segstats(str(tmp_path / "atlas.mgz"), lut={4: "Big"})

        assert len(stats) == 1
        assert (stats[0].seg_id, stats[0].name, stats[0].n_voxels) == (4, "Big", 2)
        assert stats[0].volume_mm3 == pytest.approx(16.0)

    def test_4d_volume_uses_first_frame(self, tmp_path):
        atlas_img = MagicMock()
        atlas_img.dataobj = np.zeros((2, 2, 2, 1), dtype=np.int32)
        atlas_img.dataobj[0, 0, 0, 0] = 6
        atlas_img.affine = np.eye(4)

        with patch("nibabel.load", return_value=atlas_img):
            stats = compute_segstats(str(tmp_path / "atlas.mgz"), lut={6: "Six"})

        assert stats == [SegStat(seg_id=6, name="Six", n_voxels=1, volume_mm3=1.0)]

    def test_sorted_by_seg_id(self, tmp_path):
        atlas_img = MagicMock()
        atlas_img.dataobj = np.array([[[30, 2, 15]]], dtype=np.int32)
        atlas_img.affine = np.eye(4)

        with patch("nibabel.load", return_value=atlas_img):
            stats = compute_segstats(str(tmp_path / "atlas.mgz"))

        assert [s.seg_id for s in stats] == [2, 15, 30]


# ============================================================================
# format_segstats_sum / write_segstats_sum
# ============================================================================


@pytest.mark.unit
class TestFormatSegstatsSum:
    def test_header_and_columns(self):
        stats = [
            SegStat(
                seg_id=17, name="Left-Hippocampus", n_voxels=4434, volume_mm3=4434.0
            )
        ]
        text = format_segstats_sum(stats)

        assert "# ColHeaders Index SegId NVoxels Volume_mm3 StructName" in text
        data_lines = [
            line
            for line in text.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert len(data_lines) == 1
        parts = data_lines[0].split()
        assert parts[0] == "1"  # Index
        assert parts[1] == "17"  # SegId
        assert parts[2] == "4434"  # NVoxels
        assert parts[4] == "Left-Hippocampus"

    def test_empty_stats_has_no_data_rows(self):
        text = format_segstats_sum([])
        data_lines = [
            line
            for line in text.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert data_lines == []

    def test_multiword_name_round_trips(self):
        stats = [
            SegStat(
                seg_id=1,
                name="Left Superior Temporal Gyrus",
                n_voxels=1,
                volume_mm3=1.0,
            )
        ]
        text = format_segstats_sum(stats)
        assert "Left Superior Temporal Gyrus" in text

    def test_write_segstats_sum_writes_file(self, tmp_path):
        stats = [SegStat(seg_id=1, name="Region", n_voxels=10, volume_mm3=10.0)]
        out_path = tmp_path / "out_labels.txt"
        write_segstats_sum(stats, str(out_path))
        assert out_path.read_text() == format_segstats_sum(stats)
