"""``tit.opt.roi_spec.region_name`` / ``config_target``: what a job config targets, by name.

What this pins (ARCHITECTURE §6, 2026-10-08): a proposal step's plan names its target from the
server, for any ROI an agent or the app writes -- a volume label from the atlas's own colour
table (a shipped MNI atlas's from the table ``resources/atlas/manifest.json`` names), a cortical
label from its ``.annot`` colortable, a sphere from its centre and radius, an ex-search target
from its ROI CSV names and atlas regions -- and never fails over a name (the bare label instead).
The flex/ex reports' ``roi_summary`` names its regions through the same function
(tests/test_reporting_runs.py).

Where the names come from: every colour table and colortable is written here (the annot one is
what the monkeypatched ``nibabel.freesurfer.read_annot`` returns), so each expected name is
authored in this file, not produced by the code under test.

Reproduce: .venv/bin/python -m pytest tests/test_roi_target.py -q
Deliberately elsewhere: the route carrying it (tests/test_proposals_routes.py), the card
rendering it (desktop/tests/unit/proposal-card.test.tsx).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tit.opt.roi_spec import config_target, region_name


@pytest.fixture
def labeling(tmp_path: Path) -> Path:
    seg = tmp_path / "segmentation"
    seg.mkdir()
    (seg / "labeling.nii.gz").write_bytes(b"")
    (seg / "labeling_LUT.txt").write_text(
        "10  Left-Thalamus   0 118 14 0\n49  Right-Thalamus  0 118 14 0\n"
    )
    return seg / "labeling.nii.gz"


@pytest.fixture
def annot(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(
        "nibabel.freesurfer.read_annot",
        lambda p: ([0, 1, 2], [], [b"unknown", b"insula", b"precuneus"]),
    )
    return tmp_path / "lh.DK40.annot"


def test_a_volume_label_is_named_from_the_atlas_colour_table(labeling):
    assert region_name(str(labeling), 49) == "Right-Thalamus"


def test_a_shipped_mni_atlas_is_named_from_its_manifest_table(tmp_path):
    # Glasser's table is not <stem>_LUT.txt; the manifest names it (2026-10-08 region-search fix).
    atlas = tmp_path / "MNI_Glasser_HCP_v1.0.nii.gz"
    atlas.touch()
    (tmp_path / "MNI_Glasser_HCP_v1.0.txt").write_text("#No.\tLabel Name:\n1\tL-V1\t29\t130\t102\t255\n")
    assert region_name(str(atlas), 1, "mni") == "L-V1"


def test_a_cortical_label_is_named_from_its_annot(annot):
    assert region_name(str(annot), 2) == "lh.precuneus"


def test_an_unreadable_atlas_gives_the_bare_label(tmp_path, monkeypatch):
    def unreadable(path):
        raise OSError("not an annotation")

    monkeypatch.setattr("nibabel.freesurfer.read_annot", unreadable)
    assert region_name(str(tmp_path / "rh.DK40.annot"), 3) == "rh label 3"
    assert region_name(str(tmp_path / "missing.nii.gz"), 10) == "label 10"
    assert region_name(str(tmp_path / "missing.nii.gz"), "ten") == "label ten"


def test_a_subcortical_roi_names_every_region_once(labeling):
    roi = {"_type": "SubcorticalROI", "atlas_path": str(labeling), "label": [10, 49, 10], "atlas_space": "subject"}
    assert config_target({"roi": roi}) == "Left-Thalamus, Right-Thalamus"


def test_a_cortical_roi_reads_each_hemispheres_file(annot):
    roi = {"_type": "AtlasROI", "atlas_path": [str(annot), str(annot)], "label": [1, 2], "hemisphere": ["lh", "lh"]}
    assert config_target({"roi": roi}) == "lh.insula, lh.precuneus"


def test_a_sphere_is_named_by_centre_and_radius():
    roi = {"_type": "SphericalROI", "x": [-40, 40], "y": [5.5, 5.5], "z": [2, 2], "radius": 10.0, "use_mni": True}
    assert config_target({"roi": roi}) == (
        "sphere at (-40, 5.5, 2) mm MNI, radius 10 mm, sphere at (40, 5.5, 2) mm MNI, radius 10 mm"
    )


def test_an_ex_search_target_is_its_roi_csvs_and_atlas_regions(labeling):
    config = {"roi_name": "L-Insula.csv", "roi_atlas": [{"atlas_path": str(labeling), "label": 10}]}
    assert config_target(config) == "L-Insula, Left-Thalamus"
    # roi_names, when given, replaces roi_name; an explicit [] means no spherical centres.
    assert config_target({**config, "roi_names": ["a.csv", "b"]}) == "a, b, Left-Thalamus"
    assert config_target({**config, "roi_names": []}) == "Left-Thalamus"


def test_a_config_with_no_target_has_none():
    assert config_target({"montages": []}) is None
    assert config_target({"roi": "not an object"}) is None
