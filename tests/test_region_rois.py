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
    (Path(__file__).parent / "fixtures" / "region_rois.json").read_text(encoding="utf-8")
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


@pytest.fixture()
def atlases(monkeypatch):
    found = [
        {"id": "labeling.nii.gz", "path": LAB, "kind": "volume"},
        {"id": "DK40", "path": ANNOT, "kind": "surface"},
    ]
    monkeypatch.setattr(
        catalog, "atlases", lambda pm, sid: found if sid == "101" else None
    )
    monkeypatch.setattr(
        catalog, "atlas_regions", lambda pm, sid, atlas: REGIONS[atlas]
    )


def test_find_regions_splits_sides_and_ignores_side_words(atlases):
    [hit] = catalog.find_regions(None, "101", "bilateral thalamus")
    assert hit["atlas"] == "labeling.nii.gz" and hit["kind"] == "volume"
    assert [m["side"] for m in hit["matches"]] == ["left", "right"]
    assert hit["rois"]["all"]["label"] == [10, 49]
    assert hit["rois"]["left"]["label"] == [10]
    assert hit["rois"]["right"]["label"] == [49]

    [hit] = catalog.find_regions(None, "101", "precentral")
    assert hit["rois"]["all"]["atlas_path"] == [ANNOT, ANNOT.replace("/lh.", "/rh.")]
    assert catalog.find_regions(None, "101", "amygdala") == []
    assert catalog.find_regions(None, "999", "thalamus") is None
    with pytest.raises(ValueError, match="name a structure"):
        catalog.find_regions(None, "101", "left")


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
    assert client.get("/api/catalog/regions?subject=101&q=both", headers=auth).status_code == 422
    assert client.get("/api/catalog/regions?subject=999&q=thalamus", headers=auth).status_code == 404
