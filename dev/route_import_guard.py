#!/usr/bin/env python3
"""Guard: a ``tit.server.routes`` module must do no work when it is imported.

Why this guard exists (the failure it prevents, measured 2026-09-04)
    Route modules are **auto-discovered**: ``tit/server/routes/__init__.py``
    imports every module in the package, so ``create_app`` imports all of them
    and one that raises at import time takes the *whole* server down. On the
    shared dev container that server runs under ``uvicorn --reload``, which
    restarts the worker on every save under ``tit/`` and leaves it dead until
    the file is fixed: lane SCA's module-level ``assert _HEADER.size ==
    HEADER_SIZE`` (with a 28-byte format string) took the container down for
    **~4 minutes** and broke the maintainer's ``pnpm dev`` while it was down
    (``docs/ARCHITECTURE.md``, ``dev/notes/v3-program-history.md``,
    2026-09-04). Import-time filesystem work is the same class of bug
    one step quieter: it makes every reload slower, and it fails on a machine
    where the file is absent -- for a module that is imported before any
    project is even bound.

What it checks, per module, in a **fresh interpreter** (isolation is the
point: a module imported second inherits whatever the first one loaded)

    imports        the module imports at all, with no exception
    filesystem     no ``open`` / ``listdir`` / ``scandir`` / ``glob`` / ``mkdir``
                   / ``rename`` performed *by code under ``tit/``* while the
                   module is being imported (audit hook; the import system's
                   own reads of ``.py`` files are not the module's own work
                   and are attributed to ``importlib``, not to ``tit``)
    path-manager   ``tit.paths._path_manager_instance`` is still ``None``: no
                   ``get_path_manager()`` call, so no dependence at import time
                   on a project being bound
    heavy-import   none of :data:`FORBIDDEN_MODULES` is in ``sys.modules``
    budget         the module's own import cost stays under the budget

The budget
    :data:`DEFAULT_BUDGET_MS` = 400 ms, against the slowest legitimate module
    measured on 2026-09-04 with this script's own prober: ``scene`` at
    **131 ms** in the container ``ti-toolbox-fad740e5-tit-1``
    (``simnibs_python``, it imports ``numpy`` through ``tit.scene.build``) and
    **40 ms** on the macOS host (Python 3.14). Next slowest: ``jobs`` 41 ms /
    27 ms, ``catalog_v1`` 38 ms / 19 ms. 400 ms is ~3x the slowest legitimate
    module, which is headroom for a cold ``__pycache__`` or a loaded machine,
    and still an order of magnitude below what this is meant to catch:
    ``import tit.opt`` (-> ``simnibs``) cost **3 197 ms** measured in the same
    container (``sca-notes.md`` §A4). A guard whose threshold sits 10 % above
    the truth is a guard that gets switched off; this one is 24x below the
    failure it names.

Usage::

    python3 dev/route_import_guard.py [--repo DIR] [--python EXE]
                                      [--budget-ms MS] [MODULE ...]

Exit codes: ``0`` clean, ``1`` violation, ``2`` could not check (the shape
``skills/testing-backend`` Procedure C asks for -- 2 is never a pass).
Importing this module runs nothing.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The package whose modules are auto-discovered, as a path and as a dotted name.
ROUTES_DIR = ("tit", "server", "routes")
ROUTES_PACKAGE = ".".join(ROUTES_DIR)

#: Import cost budget, in milliseconds. See the module docstring for the
#: measurements it is derived from.
DEFAULT_BUDGET_MS = 400.0

#: Modules no route may pull in at import time. ``simnibs`` is the expensive
#: one (3.2 s) and the one that does not exist on a developer's host at all;
#: the rest are its usual travelling companions.
FORBIDDEN_MODULES = (
    "simnibs",
    "nibabel",
    "scipy",
    "h5py",
    "matplotlib",
    "pandas",
    "nilearn",
    "sklearn",
    "torch",
    "trimesh",
    "meshio",
)

#: Names whose module-level *call* is filesystem or singleton work. Checked in
#: the source as well as at runtime, because a call that happens to succeed on
#: the author's machine (the file is there, a project is bound) is the same bug
#: as one that fails -- it is just quieter until CI or a fresh container runs it.
FORBIDDEN_CALLS = (
    "open",
    "get_path_manager",
    "listdir",
    "scandir",
    "walk",
    "glob",
    "iglob",
    "makedirs",
    "mkdir",
    "read_text",
    "read_bytes",
    "exists",
    "isfile",
    "isdir",
)


@dataclass(frozen=True)
class Violation:
    """One broken rule, in the module that broke it."""

    module: str
    rule: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.module}: [{self.rule}] {self.detail}"


# ── pure rules ───────────────────────────────────────────────────────────────


def report_violations(
    report: Mapping[str, Any], budget_ms: float = DEFAULT_BUDGET_MS
) -> list[Violation]:
    """Rules over one module's import report. Pure: no I/O, no imports.

    *report* is what :func:`probe_module` produces: ``module``, ``ms``,
    ``events``, ``path_manager``, ``heavy``, and ``error`` when the import
    itself failed.
    """
    module = str(report.get("module", "<unknown>"))
    error = report.get("error")
    if error:
        # The outage itself: create_app imports every route module, so this
        # one exception is a dead server, not a dead module.
        return [Violation(module, "imports", f"import raised {error}")]

    found: list[Violation] = []
    for event in report.get("events") or []:
        found.append(
            Violation(
                module,
                "filesystem",
                f"{event.get('event')}({event.get('arg')!r}) at {event.get('where')}",
            )
        )
    if report.get("path_manager"):
        found.append(
            Violation(
                module,
                "path-manager",
                "get_path_manager() was called at import time; no project is "
                "bound when create_app imports the routes",
            )
        )
    for name in report.get("heavy") or []:
        found.append(
            Violation(module, "heavy-import", f"{name} was imported at import time")
        )
    ms = report.get("ms")
    if isinstance(ms, (int, float)) and ms > budget_ms:
        found.append(
            Violation(
                module,
                "budget",
                f"import cost {ms:.1f} ms, over the {budget_ms:.0f} ms budget",
            )
        )
    return found


def source_violations(module: str, source: str) -> list[Violation]:
    """Rules over one module's *source*. Pure: takes text, returns violations.

    Catches at review time what the runtime probe can only catch on a machine
    where it actually fails: a module-level ``assert`` (lane SCA's incident --
    it passed nowhere, but an assert about a platform detail can pass on a
    laptop and fail in the container), and a module-level call that touches the
    filesystem or builds the ``PathManager`` singleton.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # a module that cannot parse cannot import
        return [Violation(module, "imports", f"source does not parse: {exc}")]

    found: list[Violation] = []
    for node in tree.body:
        if isinstance(node, ast.Assert):
            found.append(
                Violation(
                    module,
                    "import-time-assert",
                    f"line {node.lineno}: a module-level assert; an auto-discovered "
                    "route module that raises on import takes the whole server down",
                )
            )
        for call in _calls_in(node):
            name = _called_name(call)
            if name in FORBIDDEN_CALLS:
                found.append(
                    Violation(
                        module,
                        "import-time-call",
                        f"line {call.lineno}: {name}() at module level",
                    )
                )
    return found


def _calls_in(node: ast.stmt) -> Iterable[ast.Call]:
    """Every call in *node* that runs at import time (not inside a def/class)."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return ()
    return [child for child in ast.walk(node) if isinstance(child, ast.Call)]


def _called_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


# ── the shell: discovery and the isolated probe ──────────────────────────────


def discover_modules(repo: Path) -> list[str]:
    """Dotted names of every auto-discovered route module, read off disk.

    Deliberately a directory listing and not an import of
    ``tit.server.routes``: a guard that imports the package it guards has
    already done the thing it is checking for, in its own process.
    ``__init__.iter_route_modules`` skips names starting with ``_``; so does
    this.
    """
    directory = repo.joinpath(*ROUTES_DIR)
    if not directory.is_dir():
        return []
    return sorted(
        f"{ROUTES_PACKAGE}.{path.stem}"
        for path in directory.glob("*.py")
        if not path.stem.startswith("_")
    )


#: Run in a fresh interpreter, one module per process. Prints one JSON object.
#: The baseline (``fastapi`` + the routes package) is imported *before* the
#: measurement so what is timed is the module's own cost, not pydantic's.
_CHILD = r'''
import importlib, json, os, sys, time

repo, target, package = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, repo)
result = {"module": target}
try:
    import fastapi  # noqa: F401
    importlib.import_module(package)
except Exception as exc:
    print(json.dumps({"module": target, "baseline_error": f"{type(exc).__name__}: {exc}"}))
    raise SystemExit(0)

tit_dir = os.path.join(repo, "tit") + os.sep
events = []

def _hook(event, args):
    if event not in ("open", "os.listdir", "os.scandir", "glob.glob", "os.mkdir", "os.rename"):
        return
    try:
        frame = sys._getframe(1)
    except ValueError:
        return
    # The *innermost* frame only: an import of another tit module is read by
    # importlib, whose frame is <frozen importlib._bootstrap_external>, so it
    # is not counted; a route module calling open() itself is.
    if frame.f_code.co_filename.startswith(tit_dir):
        events.append({
            "event": event,
            "arg": str(args[0])[:160] if args else "",
            "where": "%s:%d" % (frame.f_code.co_filename[len(repo) + 1:], frame.f_lineno),
        })

sys.addaudithook(_hook)
started = time.perf_counter()
try:
    importlib.import_module(target)
except BaseException as exc:
    result["error"] = "%s: %s" % (type(exc).__name__, exc)
result["ms"] = round((time.perf_counter() - started) * 1000.0, 1)
result["events"] = events
paths = sys.modules.get("tit.paths")
result["path_manager"] = bool(
    paths is not None and getattr(paths, "_path_manager_instance", None) is not None
)
result["heavy"] = sorted(m for m in FORBIDDEN if m in sys.modules)
print(json.dumps(result))
'''


def probe_module(
    module: str,
    repo: Path = REPO_ROOT,
    python: str | None = None,
    package: str = ROUTES_PACKAGE,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Import *module* in a fresh interpreter and report what it did.

    Returns the report :func:`report_violations` reads, or one carrying
    ``baseline_error`` when the child could not even import ``fastapi`` --
    "could not check", not "clean".
    """
    child = f"FORBIDDEN = {FORBIDDEN_MODULES!r}\n" + _CHILD
    try:
        completed = subprocess.run(
            [python or sys.executable, "-c", child, str(repo), module, package],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"module": module, "baseline_error": f"{type(exc).__name__}: {exc}"}
    line = (completed.stdout or "").strip().splitlines()
    if not line:
        return {
            "module": module,
            "baseline_error": (
                f"the probe printed nothing (exit {completed.returncode}): "
                f"{(completed.stderr or '').strip()[:400]}"
            ),
        }
    try:
        return json.loads(line[-1])
    except json.JSONDecodeError as exc:
        return {"module": module, "baseline_error": f"unreadable probe output: {exc}"}


def source_of(module: str, repo: Path = REPO_ROOT) -> str | None:
    """The source text of a dotted module name, or ``None`` if it is not a file."""
    path = repo.joinpath(*module.split(".")).with_suffix(".py")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


# ── entry point ──────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None, log: Callable[[str], None] = print) -> int:
    """0 clean, 1 violation, 2 could not check."""
    parser = argparse.ArgumentParser(description="route import-time guard")
    parser.add_argument("modules", nargs="*", help="dotted names (default: discovered)")
    parser.add_argument("--repo", default=str(REPO_ROOT))
    parser.add_argument("--python", default=None, help="interpreter for the probes")
    parser.add_argument("--budget-ms", type=float, default=DEFAULT_BUDGET_MS)
    parser.add_argument(
        "--jobs", type=int, default=4, help="probes to run at once (timing is re-measured alone)"
    )
    parser.add_argument(
        "--package",
        default=ROUTES_PACKAGE,
        help="package imported as the baseline before the measurement",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    repo = Path(args.repo).resolve()
    modules = list(args.modules) or discover_modules(repo)
    if not modules:
        log(f"route_import_guard: no route modules found under {repo}/{'/'.join(ROUTES_DIR)}")
        return 2  # nothing to check is never a pass

    def probe(name: str) -> dict[str, Any]:
        return probe_module(name, repo=repo, python=args.python, package=args.package)

    # The probes are independent processes, so they run in parallel: serially
    # this is ~3.4 s of interpreter startup on 17 modules, which is 9 % of the
    # host suite. Only the *timing* rule is sensitive to the contention that
    # buys, and it is re-measured alone below before it can fail a build.
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        reports = list(pool.map(probe, modules))

    violations: list[Violation] = []
    for module, report in zip(modules, reports):
        if report.get("baseline_error"):
            log(f"route_import_guard: cannot check {module}: {report['baseline_error']}")
            return 2
        found = report_violations(report, args.budget_ms)
        if any(v.rule == "budget" for v in found):
            # Re-measure alone, with nothing else running: the number this
            # budget exists to catch is 24x over it, so one noisy measurement
            # on a loaded machine must never be a red build.
            again = probe(module)
            if not again.get("baseline_error"):
                report = again if again.get("ms", 1e9) < report["ms"] else report
                found = report_violations(report, args.budget_ms)
        source = source_of(module, repo)
        if source is None:
            log(f"route_import_guard: cannot read the source of {module}")
            return 2
        found += source_violations(module, source)
        log(f"  {module:<40} {report.get('ms', -1):7.1f} ms  {'FAIL' if found else 'ok'}")
        violations += found

    if violations:
        log(f"route_import_guard: {len(violations)} violation(s) in {len(modules)} module(s)")
        for violation in violations:
            log(f"  - {violation}")
        return 1
    log(f"route_import_guard: {len(modules)} route module(s) clean")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
