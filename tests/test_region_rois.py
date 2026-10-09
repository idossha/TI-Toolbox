"""Atlas region -> ROI construction and the region search behind the agent's find_regions
(2026-10-08).

Pins: ``tit.catalog.region_roi`` builds exactly the ROI the desktop picker's ``roiToConfig``
builds, from the cases in ``tests/fixtures/region_rois.json`` (groundTruth: authored), which
``desktop/tests/unit/roi-region-table.test.ts`` reads too; and ``find_regions`` /
``GET /api/catalog/regions`` match every word, ignore side words and split left/right.
The catalog's own atlas/region discovery is stubbed (it is pinned in tests/test_atlas*.py).
Reproduce: ``pytest tests/test_region_rois.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tit import catalog

TABLE = json.loads(
    (Path(__file__).parent / "fixtures" / "region_rois.json").read_text(
        encoding="utf-8"
    )
)


def test_there_are_cases_to_check():
    assert len(TABLE["cases"]) >= 4


@pytest.mark.parametrize("case", TABLE["cases"], ids=lambda c: c["why"])
def test_region_roi_matches_the_shared_table(case):
    extra = {k: case[k] for k in ("tissues", "space") if k in case}
    assert catalog.region_roi(case["atlas"], case["regions"], **extra) == case["roi"]


LAB = "/mnt/p/derivatives/SimNIBS/sub-101/m2m_101/segmentation/labeling.nii.gz"
ANNOT = "/mnt/p/derivatives/SimNIBS/sub-101/m2m_101/segmentation/lh.101_DK40.annot"
REGIONS = {
    "labeling.nii.gz": [
        {"id": 10, "name": "Left-Thalamus", "hemi": None},
        {"id": 49, "name": "Right-Thalamus", "hemi": None},
        {"id": 17, "name": "Left-Hippocampus", "hemi": None},
    ],
    "DK40": [
        {"id": 24, "name": "precentral", "hemi": "lh"},
        {"id": 24, "name": "precentral", "hemi": "rh"},
    ],
}


MNI = "/ti-toolbox/resources/atlas/HarvardOxford-sub-maxprob-thr25-1mm.nii.gz"
REGIONS["HarvardOxford-sub-maxprob-thr25-1mm.nii.gz"] = [
    {"id": 4, "name": "Left-Thalamus", "hemi": None},
    {"id": 15, "name": "Right-Thalamus", "hemi": None},
]


@pytest.fixture()
def atlases(monkeypatch):
    found = {
        ("subject", None): [
            {"id": "labeling.nii.gz", "path": LAB, "kind": "volume"},
            {"id": "DK40", "path": ANNOT, "kind": "surface"},
        ],
        # What the Optimizer's picker lists in MNI space: the shipped volume atlases.
        ("mni", "subcortical"): [
            {
                "id": "HarvardOxford-sub-maxprob-thr25-1mm.nii.gz",
                "path": MNI,
                "kind": "volume",
            }
        ],
    }
    monkeypatch.setattr(
        catalog,
        "atlases",
        lambda pm, sid, space=None, kind=None: (
            found.get((space or "subject", kind), []) if sid == "101" else None
        ),
    )
    monkeypatch.setattr(catalog, "atlas_regions", lambda pm, sid, atlas: REGIONS[atlas])


def test_find_regions_splits_sides_and_ignores_side_words(atlases):
    hit, _mni = catalog.find_regions(None, "101", "bilateral thalamus")
    assert hit["atlas"] == "labeling.nii.gz" and hit["kind"] == "volume"
    assert hit["space"] == "subject" and hit["rois"]["all"]["atlas_space"] == "subject"
    assert [m["side"] for m in hit["matches"]] == ["left", "right"]
    assert hit["rois"]["all"]["label"] == [10, 49]
    assert hit["rois"]["left"]["label"] == [10]
    assert hit["rois"]["right"]["label"] == [49]

    [hit] = catalog.find_regions(None, "101", "precentral")
    assert hit["rois"]["all"]["atlas_path"] == [ANNOT, ANNOT.replace("/lh.", "/rh.")]
    assert catalog.find_regions(None, "101", "amygdala") == []
    assert [h["space"] for h in catalog.find_regions(None, "101", "precentral")] == [
        "subject"
    ]
    assert catalog.find_regions(None, "999", "thalamus") is None
    with pytest.raises(ValueError, match="name a structure"):
        catalog.find_regions(None, "101", "left")


def test_there_are_search_cases_to_check():
    assert any(c["matches"] for c in TABLE["search"])
    assert any(not c["matches"] for c in TABLE["search"])


@pytest.mark.parametrize("case", TABLE["search"], ids=lambda c: c["why"])
def test_find_regions_matches_whole_words_of_a_name(case, atlases, monkeypatch):
    monkeypatch.setattr(
        catalog, "atlas_regions", lambda pm, sid, atlas: [{"id": 1, "name": case["name"], "hemi": None}]
    )
    hits = catalog.find_regions(None, "101", case["query"])
    assert bool(hits) is case["matches"]


def test_regions_route(atlases, monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tit.server.app import create_app
    from tit.server.routes import catalog_v1
    from tit.server.settings import ServerSettings

    monkeypatch.setattr(catalog_v1, "_pm", lambda: None)
    client = TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="t")),
        base_url="http://127.0.0.1:8765",
    )
    auth = {"Authorization": "Bearer t"}
    ok = client.get("/api/catalog/regions?subject=101&q=thalamus", headers=auth)
    assert ok.status_code == 200 and ok.json()[0]["rois"]["all"]["label"] == [10, 49]
    assert (
        client.get("/api/catalog/regions?subject=101&q=both", headers=auth).status_code
        == 422
    )
    assert (
        client.get(
            "/api/catalog/regions?subject=999&q=thalamus", headers=auth
        ).status_code
        == 404
    )


def test_find_regions_searches_the_shipped_mni_volumes_after_the_subjects_own(atlases):
    """An MNI hit is the ROI the picker builds for the same selection in MNI space (the shared
    table's Harvard-Oxford case)."""
    [case] = [c for c in TABLE["cases"] if c["atlas"]["path"] == MNI]
    hits = catalog.find_regions(None, "101", "thalamus")
    assert [(h["atlas"], h["space"]) for h in hits] == [
        ("labeling.nii.gz", "subject"),
        ("HarvardOxford-sub-maxprob-thr25-1mm.nii.gz", "mni"),
    ]
    assert hits[1]["rois"]["all"] == case["roi"]
    assert hits[1]["rois"]["left"]["label"] == [4]
    assert hits[1]["rois"]["right"]["label"] == [15]
