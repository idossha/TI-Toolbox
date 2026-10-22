"""The runner's Ex/mEx search-space count equals the shared fixture, through every layer.

What this pins (2026-10-22, package p05 "search-space-count-contract"): for each case of
``tests/fixtures/ex_search_counts.json``

* ``generate_current_ratios`` sweeps exactly the fixture's hand-checked splits;
* ``count_combinations`` / ``count_multipolar_combinations`` (what the runner logs and what
  ``run_ex_search`` refuses at zero) equal ``expected_combinations``;
* the generator the engines iterate yields that many rows;
* ``POST /api/plan/{ex,mex}`` reports it as ``search_space.n_combinations``.

``desktop/tests/unit/optimizer-ex-counts.test.ts`` holds ``exCost``/``mexCost`` to the same
table, so the cost line the Optimizer shows is the number of rows the run writes.

Where the numbers come from: ``dev/gen_ex_counts.py``, a brute force over ``itertools.product``
that imports nothing from ``tit`` (pool cases reduced to physical stimulations).
Reproduce: ``python3 dev/gen_ex_counts.py && pytest tests/test_ex_search_counts.py -q``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tit.opt.ex.logic import (
    count_combinations,
    generate_current_ratios,
    generate_montage_combinations,
)
from tit.opt.mex.logic import (
    count_multipolar_combinations,
    generate_multipolar_combinations,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ex_search_counts.json"
CASES = json.loads(FIXTURE.read_text())["cases"]
EX = [c for c in CASES if c["kind"] == "ex"]
MEX = [c for c in CASES if c["kind"] == "mex"]
EX_KEYS = ("e1_plus", "e1_minus", "e2_plus", "e2_minus")


def test_fixture_has_cases_of_every_shape():
    modes = {c.get("mode") for c in EX}
    assert modes == {"bucketed", "all"}
    assert len(MEX) >= 3
    assert any(c["expected_combinations"] == 0 for c in EX)
    assert any(c["expected_combinations"] == 0 for c in MEX)


def _ratios(case):
    limit = case["channel_limit"]
    return generate_current_ratios(
        case["total_current"],
        case["current_step"],
        limit if limit is not None else case["total_current"] - case["current_step"],
    )


def _lists(case):
    if case["mode"] == "all":
        pool = case["pool"]
        return [pool, pool, pool, pool], True
    return [case["buckets"][k] for k in EX_KEYS], False


@pytest.mark.parametrize("case", EX, ids=[c["id"] for c in EX])
def test_ex_sweep_matches_the_hand_checked_splits(case):
    ratios = _ratios(case)
    assert len(ratios) == len(case["splits"])
    for got, want in zip(ratios, case["splits"]):
        assert got == pytest.approx(tuple(want), abs=1e-9)


@pytest.mark.parametrize("case", EX, ids=[c["id"] for c in EX])
def test_ex_runner_count_equals_the_fixture(case):
    lists, pool = _lists(case)
    ratios = _ratios(case)
    expected = case["expected_combinations"]
    assert count_combinations(*lists, ratios, pool) == expected
    assert (
        sum(1 for _ in generate_montage_combinations(*lists, ratios, pool)) == expected
    )


@pytest.mark.parametrize("case", MEX, ids=[c["id"] for c in MEX])
def test_mex_runner_count_equals_the_fixture(case):
    expected = case["expected_combinations"]
    assert count_multipolar_combinations(case["buckets"]) == expected
    assert sum(1 for _ in generate_multipolar_combinations(case["buckets"])) == expected


# ── the server plan ─────────────────────────────────────────────────────────────────

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
# The plan app imports tit.stats (scipy.ndimage/scipy.stats) for other kinds; see
# tests/test_plan_routes.py for the same local fallback.
for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-p05"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    os.makedirs(get_path_manager(str(tmp_path)).m2m("001"))
    (tmp_path / "dataset_description.json").write_text("{}")
    settings = ServerSettings(project_dir=str(tmp_path), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def _ex_wire(case) -> dict:
    electrodes = (
        {"_type": "PoolElectrodes", "electrodes": case["pool"]}
        if case["mode"] == "all"
        else {"_type": "BucketElectrodes", **case["buckets"]}
    )
    return {
        "subject_id": "001",
        "leadfield_hdf": "001_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
        "roi_name": "target.csv",
        "run_name": "planned",
        "electrodes": electrodes,
        "total_current": case["total_current"],
        "current_step": case["current_step"],
        "channel_limit": case["channel_limit"],
    }


@pytest.mark.parametrize("case", EX, ids=[c["id"] for c in EX])
def test_plan_route_reports_the_fixture_count_for_ex(client, case):
    resp = client.post("/api/plan/ex", json={"config": _ex_wire(case)}, headers=BEARER)
    assert resp.status_code == 200, resp.text
    space = resp.json()["resolved"]["search_space"]
    assert space["n_combinations"] == case["expected_combinations"]
    assert space["n_current_ratios"] == len(case["splits"])


@pytest.mark.parametrize("case", MEX, ids=[c["id"] for c in MEX])
def test_plan_route_reports_the_fixture_count_for_mex(client, case, tmp_path):
    atlas = tmp_path / "CHARM.nii.gz"
    atlas.touch()
    config = {
        "subject_id": "001",
        "leadfield_hdf": "unused.hdf5",
        "roi_name": "atlas-target",
        "roi_names": [],
        "roi_atlas": [{"atlas_path": str(atlas), "label": 17}],
        "run_name": "planned-mex",
        "current_mA": case["current_mA"],
        "electrodes": {"_type": "BucketElectrodes", **case["buckets"]},
    }
    resp = client.post("/api/plan/mex", json={"config": config}, headers=BEARER)
    assert resp.status_code == 200, resp.text
    space = resp.json()["resolved"]["search_space"]
    assert space["n_combinations"] == case["expected_combinations"]
