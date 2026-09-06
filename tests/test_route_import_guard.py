"""Self-test for ``dev/route_import_guard.py``, and the guard run over this repo.

What this pins
    That no ``tit/server/routes/*.py`` module does work when it is imported --
    no exception, no filesystem call, no ``PathManager``, no ``simnibs`` -- and
    that each of those rules actually fails red, driven by a planted route
    package that breaks one rule per module. The failure it prevents is not
    hypothetical: route modules are auto-discovered, so an import-time
    ``assert`` in one of them took the shared dev container down for about four
    minutes on 2026-09-04 and broke the maintainer's ``pnpm dev`` while it was
    down (``dev/notes/v3-scene-ia-plan.md`` §6 F1).

Where the numbers come from
    The 400 ms budget is measured, not guessed: this file's own prober timed
    every route module on 2026-09-04, slowest legitimate ``scene`` at 131 ms in
    the container (``simnibs_python``, ``numpy`` via ``tit.scene.build``) and
    40 ms on the host. The number it must catch is ``import tit.opt`` ->
    ``simnibs`` at 3 197 ms (``dev/notes/v3-scene-ia/sca-notes.md`` §A4).
    Reproduce with ``python3 dev/route_import_guard.py`` (host) or
    ``docker exec <container> bash -lc 'simnibs_python
    /ti-toolbox/dev/route_import_guard.py --repo /ti-toolbox --python
    "$(command -v simnibs_python)"'``.

Deliberately elsewhere
    What the routes *answer* is ``tests/test_scene_routes.py`` and friends;
    this file only cares what they do while being imported.

Dated 2026-09-04.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_guard():
    """``dev/`` is not a package (the loading pattern test_config_schema.py uses)."""
    spec = importlib.util.spec_from_file_location(
        "route_import_guard", REPO_ROOT / "dev" / "route_import_guard.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: ``@dataclass`` resolves a field's type
    # through ``sys.modules[cls.__module__]``, which is ``None`` for a module
    # loaded by spec alone (Python 3.14 raises where 3.11 did not).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


# ── the pure rules, driven red one at a time ─────────────────────────────────


def test_a_clean_report_is_clean() -> None:
    assert (
        guard.report_violations(
            {"module": "m", "ms": 12.0, "events": [], "path_manager": False, "heavy": []}
        )
        == []
    )


def test_an_import_that_raised_is_the_outage_itself() -> None:
    found = guard.report_violations({"module": "m", "error": "AssertionError: "})
    assert [v.rule for v in found] == ["imports"]


def test_filesystem_work_at_import_time_is_a_violation() -> None:
    found = guard.report_violations(
        {
            "module": "m",
            "ms": 1.0,
            "events": [
                {"event": "open", "arg": "/p/x.csv", "where": "tit/server/routes/m.py:9"}
            ],
        }
    )
    assert [v.rule for v in found] == ["filesystem"]
    assert "m.py:9" in found[0].detail


def test_a_path_manager_built_at_import_time_is_a_violation() -> None:
    found = guard.report_violations({"module": "m", "ms": 1.0, "path_manager": True})
    assert [v.rule for v in found] == ["path-manager"]


def test_a_heavy_import_is_a_violation() -> None:
    found = guard.report_violations({"module": "m", "ms": 1.0, "heavy": ["simnibs"]})
    assert [v.rule for v in found] == ["heavy-import"]
    assert "simnibs" in found[0].detail


def test_the_budget_rule_is_the_measured_one() -> None:
    assert guard.report_violations({"module": "m", "ms": guard.DEFAULT_BUDGET_MS}) == []
    over = guard.report_violations({"module": "m", "ms": guard.DEFAULT_BUDGET_MS + 0.1})
    assert [v.rule for v in over] == ["budget"]
    # The number the budget exists to catch, measured in the container.
    assert guard.report_violations({"module": "m", "ms": 3197.0})[0].rule == "budget"


def test_the_source_rule_catches_the_incident_that_prompted_it() -> None:
    """SCA's ``assert _HEADER.size == HEADER_SIZE``, at module level."""
    found = guard.source_violations(
        "m",
        "import struct\n_H = struct.Struct('<4sIIII8s')\nassert _H.size == 32\n",
    )
    assert [v.rule for v in found] == ["import-time-assert"]
    assert "line 3" in found[0].detail


def test_the_source_rule_catches_module_level_filesystem_calls() -> None:
    found = guard.source_violations("m", "import os\nNETS = os.listdir('/x')\n")
    assert [v.rule for v in found] == ["import-time-call"]
    found = guard.source_violations(
        "m", "from tit.paths import get_path_manager\nPM = get_path_manager()\n"
    )
    assert [v.rule for v in found] == ["import-time-call"]


def test_the_source_rule_leaves_a_real_route_module_alone() -> None:
    """The same calls *inside* a handler are the whole point of a route."""
    assert (
        guard.source_violations(
            "m",
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/api/x')\n"
            "def x():\n"
            "    assert True\n"
            "    return open('/etc/hosts').read()\n",
        )
        == []
    )


def test_unparseable_source_is_reported_not_swallowed() -> None:
    found = guard.source_violations("m", "def broken(:\n")
    assert [v.rule for v in found] == ["imports"]


# ── the prober and main(), against a planted route package ───────────────────


@pytest.fixture()
def planted(tmp_path: Path) -> Path:
    """A miniature repo whose route package breaks one rule per module."""
    routes = tmp_path / "tit" / "server" / "routes"
    routes.mkdir(parents=True)
    (tmp_path / "tit" / "__init__.py").write_text("")
    (tmp_path / "tit" / "server" / "__init__.py").write_text("")
    (routes / "__init__.py").write_text("")
    # A stand-in for tit.paths with the singleton the guard inspects.
    (tmp_path / "tit" / "paths.py").write_text(
        "_path_manager_instance = None\n"
        "def get_path_manager():\n"
        "    global _path_manager_instance\n"
        "    _path_manager_instance = object()\n"
        "    return _path_manager_instance\n"
    )
    # A stand-in for the 3.2 s import, so this test needs no simnibs anywhere.
    (tmp_path / "simnibs.py").write_text("VERSION = '4.6'\n")

    (routes / "good.py").write_text("from fastapi import APIRouter\nrouter = APIRouter()\n")
    (routes / "broken_assert.py").write_text(
        "import struct\n_H = struct.Struct('<4sIIII8s')\nassert _H.size == 32\n"
    )
    (routes / "reads_a_file.py").write_text(
        "import os\n_HERE = open(__file__).read()\nNAMES = os.listdir(os.path.dirname(__file__))\n"
    )
    (routes / "builds_a_path_manager.py").write_text(
        "from tit.paths import get_path_manager\n_PM = get_path_manager()\n"
    )
    (routes / "imports_simnibs.py").write_text("import simnibs\n_V = simnibs.VERSION\n")
    (routes / "_helpers.py").write_text("raise RuntimeError('never imported')\n")
    return tmp_path


def _probe(planted: Path, name: str) -> dict:
    return guard.probe_module(
        f"tit.server.routes.{name}", repo=planted, package="tit.server.routes"
    )


def test_discovery_skips_underscore_modules(planted: Path) -> None:
    found = guard.discover_modules(planted)
    assert "tit.server.routes.good" in found
    assert not [name for name in found if name.rsplit(".", 1)[-1].startswith("_")]


def test_the_prober_sees_a_clean_module_as_clean(planted: Path) -> None:
    report = _probe(planted, "good")
    assert "error" not in report and not report["events"]
    assert report["heavy"] == [] and report["path_manager"] is False
    assert guard.report_violations(report) == []


def test_the_prober_reports_an_import_time_assert(planted: Path) -> None:
    """The exact shape of the four-minute outage."""
    report = _probe(planted, "broken_assert")
    assert "AssertionError" in report["error"]
    assert [v.rule for v in guard.report_violations(report)] == ["imports"]


def test_the_prober_sees_filesystem_work_done_by_tit_code(planted: Path) -> None:
    report = _probe(planted, "reads_a_file")
    kinds = {event["event"] for event in report["events"]}
    assert {"open", "os.listdir"} <= kinds, report["events"]
    assert all(
        event["where"].startswith("tit/server/routes/reads_a_file.py")
        for event in report["events"]
    )
    assert [v.rule for v in guard.report_violations(report)] == ["filesystem"] * len(
        report["events"]
    )


def test_the_prober_sees_a_path_manager_built_at_import_time(planted: Path) -> None:
    report = _probe(planted, "builds_a_path_manager")
    assert report["path_manager"] is True
    assert "path-manager" in {v.rule for v in guard.report_violations(report)}


def test_the_prober_sees_a_forbidden_heavy_import(planted: Path) -> None:
    report = _probe(planted, "imports_simnibs")
    assert report["heavy"] == ["simnibs"]
    assert "heavy-import" in {v.rule for v in guard.report_violations(report)}


def test_importing_a_route_module_is_not_itself_counted_as_filesystem_work(
    planted: Path,
) -> None:
    """Rule check: importlib reading ``good.py`` must not look like a violation.

    Without the innermost-frame rule the audit hook would fire on every module
    the import system reads, and the guard would be red on a clean tree -- a
    guard nobody could keep.
    """
    (planted / "tit" / "server" / "routes" / "importer.py").write_text(
        "from tit.server.routes import good\nrouter = good.router\n"
    )
    report = _probe(planted, "importer")
    assert report["events"] == []


def test_main_returns_1_and_names_every_planted_violation(planted: Path) -> None:
    lines: list[str] = []
    code = guard.main(
        ["--repo", str(planted), "--package", "tit.server.routes"], log=lines.append
    )
    assert code == 1
    text = "\n".join(lines)
    for rule in ("imports", "filesystem", "path-manager", "heavy-import"):
        assert f"[{rule}]" in text, text
    assert "import-time-assert" in text


def test_main_is_clean_on_a_package_with_nothing_wrong(planted: Path) -> None:
    for name in (
        "broken_assert",
        "reads_a_file",
        "builds_a_path_manager",
        "imports_simnibs",
    ):
        (planted / "tit" / "server" / "routes" / f"{name}.py").unlink()
    lines: list[str] = []
    assert (
        guard.main(
            ["--repo", str(planted), "--package", "tit.server.routes"], log=lines.append
        )
        == 0
    )
    assert "1 route module(s) clean" in "\n".join(lines)


# ── degraded modes: 2 is "could not check", never a pass ─────────────────────


def test_nothing_to_check_is_not_a_pass(tmp_path: Path) -> None:
    lines: list[str] = []
    assert guard.main(["--repo", str(tmp_path)], log=lines.append) == 2
    assert "no route modules found" in "\n".join(lines)


def test_a_prober_that_cannot_run_reports_could_not_check(planted: Path) -> None:
    lines: list[str] = []
    code = guard.main(
        [
            "--repo",
            str(planted),
            "--package",
            "tit.server.routes",
            "--python",
            str(planted / "no-such-python"),
        ],
        log=lines.append,
    )
    assert code == 2
    assert "cannot check" in "\n".join(lines)


def test_a_missing_prerequisite_reports_could_not_check(planted: Path) -> None:
    """No ``fastapi`` (here: an unimportable baseline package) is exit 2, not 0."""
    lines: list[str] = []
    code = guard.main(
        ["--repo", str(planted), "--package", "tit.server.no_such_package"],
        log=lines.append,
    )
    assert code == 2
    assert "cannot check" in "\n".join(lines)


# ── the repository passes its own guard ──────────────────────────────────────


def test_this_repository_has_route_modules_to_check() -> None:
    modules = guard.discover_modules(REPO_ROOT)
    assert len(modules) >= 10, modules
    for expected in ("health", "jobs", "scene"):
        assert f"tit.server.routes.{expected}" in modules


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="skipping: fastapi is not installed, so a route module cannot be imported",
)
def test_every_route_module_does_no_work_at_import_time() -> None:
    """~1.1 s: 17 fresh interpreters, four at a time (timing re-measured alone)."""
    lines: list[str] = []
    code = guard.main([f"--python={sys.executable}"], log=lines.append)
    assert code == 0, "\n".join(lines)
