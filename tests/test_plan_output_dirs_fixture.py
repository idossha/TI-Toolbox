"""``tests/fixtures/plan_output_dirs.json`` is what the real ``POST /api/plan/{kind}`` answers.

What this pins (2026-10-22, package p38): the committed table of project-relative output
directories for the group kinds (``stats`` of both types, ``nifti_average``, ``nilearn``) and
the four Visual Exporter modes (with and without an explicit ``output_dir``), plus
``tit.jobs.kinds.MODULE_FOR_KIND``, is regenerated in-process by ``dev/gen_plan_output_dirs.py``
and must match byte for byte. The mock server (``desktop/tests/mock-server/server.mjs``) and the
Visual Exporter's queued-toast hint are held to this table by
``desktop/tests/mock-server/plan-output-dirs.test.ts`` and
``desktop/tests/unit/visual-exporter-output-hint.test.ts``; before this the mock planned stats
into ``derivatives/group/stats/NewRun`` and named ``tit.tools.nilearn_visuals`` as a runner.

Where the numbers come from: the real FastAPI route, through ``TestClient``, against a throwaway
project. The spec checks below read the expected folder off each case's own config (the
``analysis_name``, ``output_name``, ``subdir_name``, explicit ``output_dir``), not off the code.
Whether each runner writes where its plan says is ``tests/test_plan_vs_runner_output_dir.py``
and ``tests/test_blender_output_dir.py`` (packages p21/p22), deliberately not here.

Reproduce: ``.venv/bin/python dev/gen_plan_output_dirs.py && .venv/bin/python -m pytest
tests/test_plan_output_dirs_fixture.py -q``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "plan_output_dirs.json"
GENERATOR = ROOT / "dev" / "gen_plan_output_dirs.py"


def _generator():
    spec = importlib.util.spec_from_file_location("gen_plan_output_dirs", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def table() -> dict:
    return json.loads(FIXTURE.read_text())


def test_the_committed_table_is_what_the_real_plan_route_answers_today() -> None:
    gen = _generator()
    assert gen.render(gen.build()) == FIXTURE.read_text(), (
        "tests/fixtures/plan_output_dirs.json is stale: run "
        "`.venv/bin/python dev/gen_plan_output_dirs.py` and review the diff "
        "(the mock server and the Visual Exporter hint read this table)"
    )


def test_the_table_covers_every_group_kind_and_every_export_mode(table: dict) -> None:
    cases = table["cases"]
    assert cases, "has cases to check"
    kinds = {c["kind"] for c in cases}
    assert {"stats", "nifti_average", "nilearn", "blender"} <= kinds
    stats_types = {c["config"].get("_type") for c in cases if c["kind"] == "stats"}
    assert {"GroupComparisonConfig", "CorrelationConfig", None} <= stats_types
    blender = [c for c in cases if c["kind"] == "blender"]
    for mode in ("RegionConfig", "VectorConfig", "MontageConfig", "SubcorticalConfig"):
        explicit = {
            "output_dir" in c["config"]
            for c in blender
            if c["config"].get("_type") == mode
        }
        assert explicit == {
            True,
            False,
        }, f"{mode} with and without an explicit output_dir"
    assert all(len(c["jobs"]) == 1 for c in cases), "one planned job per config"


def test_group_kinds_are_project_level_and_named_by_their_own_config(
    table: dict,
) -> None:
    # ARCHITECTURE: group outputs live under derivatives/ti-toolbox/<product>/<user's name>.
    product = {
        "GroupComparisonConfig": "stats/group_comparison",
        None: "stats/group_comparison",  # the server's default class for kind=stats
        "CorrelationConfig": "stats/correlation",
    }
    for case in table["cases"]:
        (job,) = case["jobs"]
        cfg = case["config"]
        if case["kind"] == "stats":
            expected = f"derivatives/ti-toolbox/{product[cfg.get('_type')]}/{cfg['analysis_name']}"
        elif case["kind"] == "nifti_average":
            expected = f"derivatives/ti-toolbox/nifti_average/{cfg['output_name']}"
        elif case["kind"] == "nilearn":
            # NilearnConfig.subdir_name defaults to the product folder's own name.
            sub = cfg.get("subdir_name", "nilearn_visuals")
            expected = f"derivatives/ti-toolbox/nilearn_visuals/{sub}"
        else:
            continue
        assert job == {"subject": "", "output_dir": expected}, case["id"]


def test_an_explicit_export_folder_is_planned_verbatim(table: dict) -> None:
    placeholder = table["project_placeholder"]
    explicit = [c for c in table["cases"] if "output_dir" in c["config"]]
    assert explicit, "has explicit-folder cases to check"
    for case in explicit:
        wanted = case["config"]["output_dir"].replace(placeholder + "/", "")
        assert case["jobs"] == [{"subject": "001", "output_dir": wanted}], case["id"]


def test_the_module_map_is_the_job_runner_s(table: dict) -> None:
    from tit.jobs.kinds import MODULE_FOR_KIND

    assert table["module_for_kind"] == MODULE_FOR_KIND
    for kind, module in MODULE_FOR_KIND.items():
        package = table["runner_package_for_kind"][kind]
        assert module == package or module.startswith(package + "."), kind
