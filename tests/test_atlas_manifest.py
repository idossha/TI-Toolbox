"""The shipped-MNI-atlas manifest, and the kind that routes an atlas to a mode.

Every fact asserted here is read off ``resources/atlas/manifest.json`` and the
files beside it, not retyped from :mod:`tit.atlas.manifest` -- so a manifest that
describes an atlas that is not shipped, an atlas that is shipped and not
described, a missing LUT, or a missing licence field, fails.
"""

from __future__ import annotations

import gzip
import json
import os
import struct
from pathlib import Path

import pytest

from tit.atlas.constants import mni_resources_dir
from tit.atlas.manifest import (
    KIND_FOR_MODE,
    MANIFEST_NAME,
    check_shipped,
    kind_for_path,
    mni_atlas_entries,
    mni_atlas_entry,
    mni_atlas_files,
    not_shipped_message,
)

RESOURCES = Path(mni_resources_dir())
REPO = RESOURCES.parents[1]
REQUIRED = (
    "file",
    "kind",
    "template",
    "labels",
    "license",
    "attribution",
    "redistribution",
    "citation",
)


def _raw() -> dict:
    with open(RESOURCES / MANIFEST_NAME, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.unit
class TestManifestFile:
    def test_every_entry_carries_the_required_fields(self):
        for entry in _raw()["atlases"]:
            missing = [field for field in REQUIRED if not entry.get(field)]
            assert not missing, f"{entry.get('file')} is missing {missing}"

    def test_kind_is_surface_or_volume(self):
        for entry in _raw()["atlases"]:
            assert entry["kind"] in ("surface", "volume"), entry["file"]

    def test_every_described_atlas_and_its_labels_are_shipped(self):
        for entry in _raw()["atlases"]:
            assert (RESOURCES / entry["file"]).is_file(), entry["file"]
            assert (RESOURCES / entry["labels"]).is_file(), entry["labels"]

    def test_every_shipped_mni_label_volume_is_described(self):
        """A new atlas dropped into resources/atlas/ must be described, not guessed."""
        described = set(mni_atlas_files())
        described.add(_raw()["template_volume"]["file"])
        undescribed = sorted(
            name
            for name in os.listdir(RESOURCES)
            if name.endswith((".nii", ".nii.gz")) and name not in described
        )
        assert undescribed == [], (
            "these label volumes are shipped but not in "
            f"{MANIFEST_NAME}: {undescribed}"
        )

    def test_redistribution_is_a_yes_or_a_reasoned_no(self):
        for entry in _raw()["atlases"]:
            value = entry["redistribution"]
            assert value.startswith("yes") or value.startswith("no ("), (
                f"{entry['file']}: redistribution must be 'yes...' or "
                f"'no (<reason>)', was {value!r}"
            )

    def test_everything_shipped_may_be_redistributed(self):
        """Since 2026-09-17 nothing with a 'no (...)' redistribution is shipped."""
        for entry in _raw()["atlases"]:
            assert entry["redistribution"].startswith("yes"), entry["file"]

    def test_the_new_atlases_are_described_with_their_source(self):
        for name in NLIN6_ATLASES:
            entry = mni_atlas_entry(name)
            assert entry is not None, name
            assert entry["kind"] == "volume"
            assert entry["template"] == "MNI152NLin6Asym"
            assert entry["source"]["url"].startswith("http"), name
            assert len(entry["source"]["sha256"]) == 64, name


def _nifti_geometry(path: Path) -> tuple[tuple[int, ...], tuple[float, ...], list[float]]:
    """``(shape, pixdim, srow)`` read straight off a gzipped NIfTI-1 header.

    nibabel is mocked in this suite, and the header fields are all the test
    needs: a shipped atlas that claims the template's grid must have the
    template's ``dim``, ``pixdim`` and sform rows, byte for byte.
    """
    with gzip.open(path, "rb") as handle:
        header = handle.read(352)
    dim = struct.unpack_from("<8h", header, 40)
    pixdim = struct.unpack_from("<8f", header, 76)
    srow = list(struct.unpack_from("<12f", header, 280))
    return tuple(dim[1 : 1 + dim[0]]), tuple(pixdim[1:4]), srow


NLIN6_ATLASES = (
    "HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz",
    "HarvardOxford-sub-maxprob-thr25-1mm.nii.gz",
    "Cerebellum-MNIfnirt-maxprob-thr25-1mm.nii.gz",
    "Schaefer2018_400Parcels_7Networks_order_FSLMNI152_1mm.nii.gz",
)


@pytest.mark.unit
class TestGrid:
    """Each atlas that claims the template's grid is on it: shape, voxel size, affine."""

    @pytest.mark.parametrize("name", NLIN6_ATLASES)
    def test_header_matches_the_shipped_mni152_template(self, name):
        template = RESOURCES / _raw()["template_volume"]["file"]
        shape, pixdim, srow = _nifti_geometry(RESOURCES / name)
        t_shape, t_pixdim, t_srow = _nifti_geometry(template)
        assert shape == t_shape == (182, 218, 182), name
        assert pixdim == t_pixdim == (1.0, 1.0, 1.0), name
        assert srow == t_srow, name
        # And the manifest says the same thing.
        grid = mni_atlas_entry(name)["grid"]
        assert tuple(grid["shape"]) == shape
        assert grid["same_as_template_volume"] is True
        assert [srow[3], srow[7], srow[11]] == grid["origin_ras"]

    @pytest.mark.parametrize("name", NLIN6_ATLASES)
    def test_lut_covers_every_declared_region(self, name):
        entry = mni_atlas_entry(name)
        ids = [
            int(line.split()[0])
            for line in (RESOURCES / entry["labels"]).read_text().splitlines()
            if line.strip() and not line.startswith("#") and line.split()[0].isdigit()
        ]
        assert set(ids) - {0} == set(range(1, entry["regions"] + 1)), name


def _text_files_mentioning(word: bytes, roots: list[Path]) -> set[str]:
    """Relative paths of text files under *roots* containing *word* (binaries skipped)."""
    found = set()
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            data = path.read_bytes()
            if b"\0" in data[:8192]:
                continue
            if word in data:
                found.add(path.relative_to(REPO).as_posix())
    return found


@pytest.mark.unit
class TestNotShipped:
    """A removed atlas fails with one sentence, and its name is gone from the tree."""

    NOTES = {
        "resources/atlas/README.md",
        "resources/atlas/manifest.json",
        "tit/scene/guide-mni/PROVENANCE.md",
    }

    def test_a_configuration_naming_it_fails_with_the_reason(self):
        message = not_shipped_message("/ti-toolbox/resources/atlas/MorelMNI152_labeling_1mm.nii.gz")
        assert message == (
            "The Morel atlas is no longer shipped (CC BY-NC-SA); see docs/wiki/atlases.md"
        )
        with pytest.raises(ValueError, match="no longer shipped"):
            check_shipped("MorelMNI152_labeling_1mm.nii.gz")
        assert not_shipped_message("CIT168_labeling_lateralized_MNI152NLin2009cAsym.nii.gz") is None
        check_shipped("CIT168_labeling_lateralized_MNI152NLin2009cAsym.nii.gz")

    @pytest.mark.parametrize(
        "old, new",
        [
            ("CIT168_labeling_MNI152NLin2009cAsym.nii.gz", "CIT168_labeling_lateralized_MNI152NLin2009cAsym.nii.gz"),
            ("HarvardOxford-cort-maxprob-thr25-1mm.nii.gz", "HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz"),
        ],
    )
    def test_a_bilateral_atlas_names_its_lateralized_replacement(self, old, new):
        """2026-09-23: a config naming a bilateral atlas fails rather than silently re-meaning label k."""
        with pytest.raises(ValueError, match=new.replace(".", r"\.")):
            check_shipped(old)
        assert mni_atlas_entry(old) is None
        assert not (RESOURCES / old).exists()
        assert mni_atlas_entry(new) is not None

    def test_it_is_not_in_the_manifest_and_not_on_disk(self):
        assert mni_atlas_entry("MorelMNI152_labeling_1mm.nii.gz") is None
        assert not list(RESOURCES.glob("Morel*"))
        assert not list((REPO / "tit" / "scene" / "guide-mni").rglob("*Morel*"))

    def test_the_name_appears_only_in_the_not_shipped_notes(self):
        """A grep over tit/ and resources/ (text files; .gii/.tvsc/.nii.gz skipped)."""
        found = _text_files_mentioning(b"Morel", [REPO / "tit", REPO / "resources"])
        assert found <= self.NOTES, sorted(found - self.NOTES)


@pytest.mark.unit
class TestKind:
    def test_annot_is_a_surface_and_a_volume_is_a_volume(self):
        assert kind_for_path("/m2m/segmentation/lh.001_DK40.annot") == "surface"
        assert kind_for_path("/m2m/surfaces/lh.HCP_MMP1.label.gii") == "surface"
        assert kind_for_path("/m2m/segmentation/labeling.nii.gz") == "volume"
        assert kind_for_path("/fs/mri/aparc.DKTatlas+aseg.mgz") == "volume"

    def test_every_shipped_mni_atlas_is_a_volume_today(self):
        """Including Glasser: a cortical parcellation distributed as a volume."""
        assert {entry["kind"] for entry in mni_atlas_entries()} == {"volume"}

    def test_modes_map_to_the_kind_they_can_read(self):
        assert KIND_FOR_MODE == {"cortical": "surface", "subcortical": "volume"}


@pytest.mark.unit
class TestLookup:
    def test_entries_resolve_to_files_that_exist(self):
        for entry in mni_atlas_entries():
            assert os.path.isfile(entry["path"])

    def test_a_directory_without_a_manifest_still_resolves_the_packaged_one(
        self, tmp_path
    ):
        name = mni_atlas_files()[0]
        (tmp_path / name).touch()
        entries = mni_atlas_entries(str(tmp_path))
        assert [entry["id"] for entry in entries] == [name]
        assert entries[0]["path"] == str(tmp_path / name)
        assert entries[0]["kind"] == "volume"

    def test_unknown_id_is_none(self):
        assert mni_atlas_entry("not-an-atlas.nii.gz") is None
