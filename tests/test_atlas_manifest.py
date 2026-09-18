"""The shipped-MNI-atlas manifest, and the kind that routes an atlas to a mode.

Every fact asserted here is read off ``resources/atlas/manifest.json`` and the
files beside it, not retyped from :mod:`tit.atlas.manifest` -- so a manifest that
describes an atlas that is not shipped, an atlas that is shipped and not
described, a missing LUT, or a missing licence field, fails.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tit.atlas.constants import mni_resources_dir
from tit.atlas.manifest import (
    KIND_FOR_MODE,
    MANIFEST_NAME,
    kind_for_path,
    mni_atlas_entries,
    mni_atlas_entry,
    mni_atlas_files,
)

RESOURCES = Path(mni_resources_dir())
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

    def test_the_non_redistributable_atlas_is_named(self):
        """Morel is CC BY-NC-SA and must stay flagged until it is moved out."""
        morel = mni_atlas_entry("MorelMNI152_labeling_1mm.nii.gz")
        assert morel is not None
        assert morel["redistribution"].startswith("no (")


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
