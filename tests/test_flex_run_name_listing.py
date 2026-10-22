"""One badly named flex run folder no longer hides every flex run of its subject.

What this pins (audit_flex #3, package p08, 2026-10-22): a flex-search folder whose name is
outside ``tit.paths.NAME_RE`` -- ``Thalamus (L)``, which v3.1 let the Optimizer's Run name create
-- made ``catalog.flex_runs`` raise ``ValueError: invalid run 'Thalamus (L)'`` (it validates
each listed name), so ``GET /api/catalog/flex-runs`` answered 500 and the Results and Simulator
flex lists of that subject went empty. ``PathManager.list_flex_search_runs`` now skips (and
logs) a name the rule refuses; every consumer of the listing -- the catalog, its route and the
Simulator's flex montage sources -- then sees exactly the well-named runs.

Expected values: the folders the test itself writes; which names pass comes from NAME_RE's
documented grammar (letters, digits, ``.``, ``_``, ``-``, inner spaces; no leading dot or space),
not from the listing code. New runs with such names are refused earlier, by
``FlexConfig.output_folder`` (tests/test_flexconfig_validation_edges.py).

Reproduce: ``.venv/bin/python -m pytest tests/test_flex_run_name_listing.py -q``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit import catalog  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402
from tit.sim.montage_sources import list_flex_run_options  # noqa: E402

TOKEN = "listing-token"
GOOD = ("good_run", "run 2")
BAD = ("Thalamus (L)", "a+b")


def _project(root: Path) -> Path:
    """A project with subject x, two well-named flex runs and two badly named ones."""
    sub = root / "derivatives" / "SimNIBS" / "sub-x"
    (sub / "m2m_x").mkdir(parents=True)
    (sub / "m2m_x" / "x.msh").write_bytes(b"")
    (root / "dataset_description.json").write_text("{}")
    for name in (*GOOD, *BAD):
        run = sub / "flex-search" / name
        run.mkdir(parents=True)
        (run / "flex_meta.json").write_text(
            json.dumps(
                {"version": 1, "goal": "mean", "label": name, "result": {}},
            )
        )
        (run / "electrode_positions.json").write_text(
            json.dumps({"optimized_positions": [[0, 0, 0]] * 4})
        )
    return root


def test_the_listing_skips_and_logs_names_outside_the_name_rule(tmp_path, caplog):
    pm = get_path_manager(str(_project(tmp_path)))
    with caplog.at_level(logging.WARNING, logger="tit.paths"):
        names = pm.list_flex_search_runs("x")
    assert names == sorted(GOOD)
    logged = " ".join(r.getMessage() for r in caplog.records)
    for name in BAD:
        assert repr(name) in logged


def test_catalog_lists_the_well_named_runs_instead_of_raising(tmp_path):
    pm = get_path_manager(str(_project(tmp_path)))
    runs = catalog.flex_runs(pm, "x")
    assert sorted(r["name"] for r in runs) == sorted(GOOD)


def test_the_flex_runs_route_answers_200_with_the_well_named_runs(tmp_path):
    project = _project(tmp_path)
    app = create_app(ServerSettings(project_dir=str(project), token=TOKEN))
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    resp = client.get(
        "/api/catalog/flex-runs",
        params={"subject": "x"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 200, resp.text
    assert sorted(r["name"] for r in resp.json()) == sorted(GOOD)


def test_simulator_flex_sources_list_only_the_well_named_runs(tmp_path):
    """Guard (it passed before the listing fix too): with a badly named run present,
    the Simulator's flex sources still offer each well-named run in both kinds."""
    pm = get_path_manager(str(_project(tmp_path)))
    options = list_flex_run_options(pm, "x")
    assert sorted({o["run_name"] for o in options}) == sorted(GOOD)
    # Each listed run offers its mapped montage and, with optimized positions, the optimized one.
    assert sorted((o["run_name"], o["electrode_type"]) for o in options) == sorted(
        (name, kind) for name in GOOD for kind in ("mapped", "optimized")
    )
