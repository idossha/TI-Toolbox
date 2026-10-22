"""The desktop's generated contract fixtures are what the real code produces today.

What this pins (2026-10-22, package p39): two committed generators write fixtures the desktop
tests and the mock server read, from the real server code on synthetic projects:

* ``dev/make_contract_fixtures.py`` -> ``desktop/tests/fixtures/contracts/`` (the real
  ``candidate_detail`` for a flex, an ex and an mEx run; the real ``build_overview``);
* ``dev/regen_mock_reports.py`` -> ``desktop/tests/fixtures/reports/<sid>/*.html`` (the real
  simulation and ex-search report generators) and ``reports.json`` (the real
  ``tit.catalog.reports`` listing of those pages).

Each generator is run in-process here and must reproduce the committed files byte for byte, so a
change to the producers (a renamed key, a new montage name, a report section) shows up as a
stale fixture instead of a desktop test that keeps passing against the old shape. The semantic
checks live with the readers: ``desktop/tests/unit/candidate-handoff.test.ts``,
``desktop/tests/unit/overview-contract.test.ts``, ``desktop/tests/mock-server/contract.test.ts``
and ``tests/test_mock_fixture_drift.py``.

Reproduce: ``.venv/bin/python dev/make_contract_fixtures.py && .venv/bin/python
dev/regen_mock_reports.py && .venv/bin/python -m pytest tests/test_contract_fixtures_fresh.py -q``.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "desktop" / "tests" / "fixtures"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "dev" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def contracts() -> dict[str, str]:
    return _load("make_contract_fixtures").build()


@pytest.fixture(scope="module")
def reports() -> dict[str, str]:
    return _load("regen_mock_reports").build()


def test_contract_fixtures_are_fresh(contracts: dict[str, str]) -> None:
    assert sorted(contracts) == [
        "candidate_detail_ex.json",
        "candidate_detail_flex.json",
        "candidate_detail_mex.json",
        "overview.json",
    ]
    committed = sorted(p.name for p in (FIXTURES / "contracts").iterdir())
    assert committed == sorted(
        contracts
    ), "a committed contract fixture no generator writes"
    for name, text in contracts.items():
        assert (FIXTURES / "contracts" / name).read_text(
            encoding="utf-8"
        ) == text, f"{name} is stale: run dev/make_contract_fixtures.py"


def test_candidate_fixtures_answer_their_own_requests(
    contracts: dict[str, str],
) -> None:
    """Each fixture is the detail of the candidate its request names, in its run and kind."""
    for kind, pairs in (("flex", 2), ("ex", 2), ("mex", 4)):
        data = json.loads(contracts[f"candidate_detail_{kind}.json"])
        request, response = data["request"], data["response"]
        assert request["kind"] == kind
        assert response["candidate"]["id"] == request["candidate_id"]
        config = response["simulation_config"]
        assert config["subject_id"] == request["subject"]
        (montage,) = config["montages"]
        assert montage["provenance"]["run"] == request["run"]
        assert montage["provenance"]["candidate_id"] == request["candidate_id"]
        assert len(montage["electrode_pairs"]) == pairs == len(config["intensities"])
        assert re.fullmatch(r"candidate_[0-9a-f]{16}", montage["name"])
        # No temporary path survives the rewrite to the mock's project root.
        assert "/tmp" not in contracts[f"candidate_detail_{kind}.json"]
        assert "/var/folders" not in contracts[f"candidate_detail_{kind}.json"]


def test_mock_reports_are_fresh(reports: dict[str, str]) -> None:
    pages = sorted(k for k in reports if k.startswith("reports/"))
    assert len(pages) == 4
    committed = sorted(
        str(p.relative_to(FIXTURES)) for p in (FIXTURES / "reports").rglob("*.html")
    )
    assert committed == pages, "a committed report page no generator writes"
    for rel, text in reports.items():
        assert (FIXTURES / rel).read_text(
            encoding="utf-8"
        ) == text, f"{rel} is stale: run dev/regen_mock_reports.py"


def test_mock_report_listing_names_every_generated_page(
    reports: dict[str, str],
) -> None:
    listing = json.loads(reports["reports.json"])
    listed = sorted(
        f"reports/{sid}/{row['id'].split('/', 1)[1]}.html"
        for sid, rows in listing.items()
        for row in rows
    )
    assert listed == sorted(k for k in reports if k.startswith("reports/"))
    # The page's own title is what links a simulation report to its simulation.
    for rel, text in reports.items():
        if "/simulation_report_" in rel:
            assert re.search(r"<title>[^<]+ simulation</title>", text), rel
