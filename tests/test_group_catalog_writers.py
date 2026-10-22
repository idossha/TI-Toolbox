"""Every project-level output a runner writes is listed by ``GET /api/catalog/group`` (2026-10-22).

What this pins
    ``tit.stats.nifti_average`` writes ``derivatives/ti-toolbox/nifti_average/<output_name>/``,
    but ``catalog.group_catalog`` listed only stats runs, nilearn visuals and group analyses,
    so a NIfTI Group Averaging run never appeared in Results (the desktop even refreshed the
    group catalog after the job, to the same empty list). Now the catalog has a
    ``nifti_average`` key, one row per run directory, whose ``artifacts`` are the files the
    runner wrote. The same writer -> reader agreement is pinned for every other project-level
    writer: stats (both analysis types), nilearn and the group analyzer.

Where the expectations come from
    The writers, not the reader: ``POST /api/plan/<kind>`` (the server's own statement of
    ``output_dir``, which mirrors the runner) for stats, nilearn and nifti_average; the
    group analyzer's own ``_resolve_output_dir`` for its timestamped folder; and, for
    ``nifti_average``, the real runner ``tit.stats.nifti_average.main`` run on the host with
    its NIfTI loader stubbed and ``nib.save`` writing placeholder bytes at the paths the runner
    chose -- so the artifact names are the runner's, read back with ``os.listdir``. The configs
    are the desktop's own (``tests/fixtures/desktop_configs/panels-*``).

Run: .venv/bin/python -m pytest tests/test_group_catalog_writers.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
CORPUS = Path(__file__).parent / "fixtures" / "desktop_configs"


def _desktop_config(case: str) -> dict:
    """The config the desktop page builds for this corpus case."""
    return json.loads((CORPUS / f"{case}.json").read_text())["jobs"][0]["config"]


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    for sid in ("001", "002", "003"):
        os.makedirs(pm.m2m(sid))
    (tmp_path / "dataset_description.json").write_text("{}")
    return tmp_path


@pytest.fixture()
def client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def _planned_dir(client: TestClient, kind: str, config: dict) -> str:
    resp = client.post(f"/api/plan/{kind}", json={"config": config}, headers=BEARER)
    assert resp.status_code == 200, resp.text
    (job,) = resp.json()["jobs"]
    return job["output_dir"]


def _group(client: TestClient) -> dict:
    resp = client.get("/api/catalog/group", headers=BEARER)
    assert resp.status_code == 200
    return resp.json()


def _run_nifti_average_runner(project: Path, config: dict) -> None:
    """``tit.stats.nifti_average.main`` on the host: loader stubbed, saves land as bytes."""
    from tit.stats import nifti_average

    config_path = project / "nifti_average_config.json"
    config_path.write_text(json.dumps({**config, "project_dir": str(project)}))
    groups = sorted({s["group"] for s in config["subjects"]})
    groups_data = {g: np.full((2, 2, 2, 1), float(i + 1)) for i, g in enumerate(groups)}
    template = SimpleNamespace(affine=np.eye(4), header=None)
    ids = {
        g: [s["subject_id"] for s in config["subjects"] if s["group"] == g]
        for g in groups
    }

    logger = logging.getLogger("tit.stats.nifti_average")
    handlers = list(logger.handlers)
    try:
        with (
            patch.object(sys, "argv", ["tit.stats.nifti_average", str(config_path)]),
            patch.object(
                nifti_average,
                "load_grouped_subjects_ti_toolbox",
                return_value=(groups_data, template, ids),
            ),
            patch.object(
                nifti_average.nib,
                "save",
                lambda _img, path: Path(path).write_bytes(b"nii"),
            ),
        ):
            with pytest.raises(SystemExit) as exit_info:
                nifti_average.main()
    finally:
        for handler in logger.handlers[:]:
            if handler not in handlers:
                logger.removeHandler(handler)
        config_path.unlink()
    assert exit_info.value.code == 0


def test_a_nifti_average_run_is_listed_where_the_plan_and_the_runner_put_it(
    client: TestClient, project: Path
) -> None:
    config = {**_desktop_config("panels-nifti/mni-space"), "output_name": "avg1"}
    planned = _planned_dir(client, "nifti_average", config)
    assert _group(client).get("nifti_average", []) == []

    _run_nifti_average_runner(project, config)
    assert os.path.isdir(planned), "the runner wrote where the plan said"

    rows = _group(client)["nifti_average"]
    assert [r["path"] for r in rows] == [planned]
    assert rows[0]["name"] == "avg1"
    on_disk = sorted(os.path.join(planned, n) for n in os.listdir(planned))
    # average_Group1, average_Group2, difference_Group1_minus_Group2, config.json
    assert len(on_disk) == 4, on_disk
    assert sorted(a["path"] for a in rows[0]["artifacts"]) == on_disk
    kinds = {os.path.basename(a["path"]): a["kind"] for a in rows[0]["artifacts"]}
    assert {n for n, k in kinds.items() if k == "nifti"} == {
        n for n in os.listdir(planned) if n.endswith(".nii.gz")
    }
    assert kinds["config.json"] == "json"
    assert all(a["label"] for a in rows[0]["artifacts"])


def test_two_nifti_average_runs_are_two_rows(client: TestClient, project: Path) -> None:
    base = _desktop_config("panels-nifti/mni-space")
    planned = [
        _planned_dir(client, "nifti_average", {**base, "output_name": name})
        for name in ("avg_b", "avg_a")
    ]
    for path in planned:
        os.makedirs(path)
        Path(path, "average_G1.nii.gz").write_bytes(b"x")
    rows = _group(client)["nifti_average"]
    assert sorted(r["path"] for r in rows) == sorted(planned)
    assert [r["name"] for r in rows] == ["avg_a", "avg_b"]


@pytest.mark.parametrize(
    "case, analysis_type",
    [
        ("panels-stats/classification-2-groups", "group_comparison"),
        ("panels-stats/correlation-3-rows", "correlation"),
    ],
)
def test_a_stats_run_is_listed_where_the_plan_puts_it(
    client: TestClient, case: str, analysis_type: str
) -> None:
    config = {**_desktop_config(case), "analysis_name": "run1"}
    planned = _planned_dir(client, "stats", config)
    os.makedirs(planned)
    Path(planned, f"{analysis_type}_analysis_20261022_000000.log").write_text("x\n")

    rows = _group(client)["stats"]
    assert [(r["path"], r["type"], r["name"]) for r in rows] == [
        (planned, analysis_type, "run1")
    ]


def test_same_named_stats_runs_of_both_types_are_two_rows(client: TestClient) -> None:
    planned = {
        _planned_dir(client, "stats", {**_desktop_config(case), "analysis_name": "X"})
        for case in (
            "panels-stats/classification-2-groups",
            "panels-stats/correlation-3-rows",
        )
    }
    assert len(planned) == 2
    for path in planned:
        os.makedirs(path)
    rows = _group(client)["stats"]
    assert {r["path"] for r in rows} == planned
    assert {(r["type"], r["name"]) for r in rows} == {
        ("group_comparison", "X"),
        ("correlation", "X"),
    }


def test_a_nilearn_run_is_listed_where_the_plan_puts_it(client: TestClient) -> None:
    config = _desktop_config("panels-nilearn/one-pair")
    planned = _planned_dir(client, "nilearn", config)
    os.makedirs(planned)
    rows = _group(client)["nilearn"]
    assert [r["path"] for r in rows] == [planned]
    assert rows[0]["name"] == config["subdir_name"]


def test_a_group_analysis_is_listed_under_the_runners_own_folder(
    client: TestClient, project: Path
) -> None:
    from tit.analyzer.group import _resolve_output_dir

    written = _resolve_output_dir(None, "M1_voxel_sphere_x1.00_y2.00_z3.00_r5.0_MNI")
    rows = _group(client)["group_analyses"]
    assert [r["path"] for r in rows] == [str(written)]
    assert rows[0]["name"] == written.name


def test_an_empty_project_lists_four_empty_groups(client: TestClient) -> None:
    assert _group(client) == {
        "stats": [],
        "nilearn": [],
        "group_analyses": [],
        "nifti_average": [],
    }
