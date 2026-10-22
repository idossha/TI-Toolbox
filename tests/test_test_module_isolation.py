"""Host test modules do not change each other's libraries, whatever order pytest imports them in.

What this pins
    1. No test module swaps ``numpy`` or ``scipy`` in ``sys.modules`` while it is being
       collected. Four stats modules used to pop the scipy mocks at import time and never put
       them back, so every module collected after them ran against real scipy and every module
       before against the mock. The real-scipy modules now use the ``real_scipy`` fixture
       (``tests/conftest.py``), which swaps for one module's tests and restores afterwards.
    2. The order that used to break runs green in a fresh interpreter:
       ``test_pre_pipeline.py`` first made numpy a ``MagicMock`` for the whole session (its
       ``sys.modules.setdefault("numpy", MagicMock())`` ran before anything imported numpy),
       which failed ``test_plotting.py`` and broke collection of the real-scipy modules
       (``ImportError: cannot import name '__version__'``).

Where the expectations come from
    Pytest's own exit status and summary for the named orders; the rule in (1) is read from the
    test sources with ``ast``.

Deliberately elsewhere
    The full reversed/shuffled proof over the stats modules is in the p02 build report
    (scratch, 2026-10-22); running it here would add ~30 s to every host run.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARDED_ROOTS = {"numpy", "scipy"}


def _module_level_statements(tree: ast.Module):
    """Top-level statements, descending into module-level if/for/try/with blocks only."""
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        for field in ("body", "orelse", "finalbody", "handlers"):
            stack.extend(getattr(node, field, []) or [])


def _own_expressions(statement: ast.stmt):
    """Nodes of one statement, without nested statements (they are visited on their own)."""
    stack = [statement]
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.stmt, ast.Lambda)):
                stack.append(child)


def _is_sys_modules(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "modules"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def _guarded_key(key: ast.AST | None, loop_keys: dict[str, list[str]]) -> bool:
    """Whether a ``sys.modules`` key may be numpy/scipy.

    A literal is checked; a name bound by a module-level ``for`` over literal strings is
    checked against those strings; any other expression (the old pattern: a comprehension
    over ``sys.modules`` itself) may be anything, so it counts.
    """
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value.split(".")[0] in GUARDED_ROOTS
    if isinstance(key, ast.Name) and key.id in loop_keys:
        return any(k.split(".")[0] in GUARDED_ROOTS for k in loop_keys[key.id])
    return True


def collection_time_swaps(source: str) -> list[int]:
    """Line numbers where module-level code pops or assigns a numpy/scipy ``sys.modules`` key.

    ``del`` and ``setdefault`` are allowed: deleting a mock only lets the real package import,
    and ``tests/conftest.py`` imports real numpy before any module, so a ``setdefault`` of it
    is a no-op.
    """
    loop_keys: dict[str, list[str]] = {}
    lines = set()
    for statement in _module_level_statements(ast.parse(source)):
        if (
            isinstance(statement, ast.For)
            and isinstance(statement.target, ast.Name)
            and isinstance(statement.iter, (ast.Tuple, ast.List))
            and all(
                isinstance(e, ast.Constant) and isinstance(e.value, str)
                for e in statement.iter.elts
            )
        ):
            loop_keys[statement.target.id] = [e.value for e in statement.iter.elts]
        for node in _own_expressions(statement):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "pop"
                and _is_sys_modules(node.func.value)
                and _guarded_key(node.args[0] if node.args else None, loop_keys)
            ):
                lines.add(node.lineno)
            if isinstance(node, ast.Assign) and any(
                isinstance(item, ast.Subscript)
                and _is_sys_modules(item.value)
                and _guarded_key(item.slice, loop_keys)
                for item in node.targets
            ):
                lines.add(node.lineno)
    return sorted(lines)


def test_the_rule_flags_the_old_collection_time_pop():
    """The pattern four stats modules carried until 2026-10-22, and clean neighbours."""
    old = (
        "import sys\n"
        '_keys = [k for k in list(sys.modules) if k.startswith("scipy")]\n'
        "_saved = {k: sys.modules.pop(k) for k in _keys}\n"
        'sys.modules["scipy.optimize"] = object()\n'
        'for _m in ("simnibs", "scipy.sparse"):\n'
        "    sys.modules[_m] = object()\n"
    )
    assert collection_time_swaps(old) == [3, 4, 6]
    clean = (
        "import sys\n"
        "def test_x(monkeypatch):\n"
        '    sys.modules.pop("scipy")\n'
        'sys.modules["simnibs"] = object()\n'
        'for _m in ("bpy", "h5py"):\n'
        "    sys.modules[_m] = object()\n"
        'if "numpy" in sys.modules:\n'
        '    del sys.modules["numpy"]\n'
        'sys.modules.setdefault("numpy", object())\n'
    )
    assert collection_time_swaps(clean) == []


def test_no_test_module_swaps_numpy_or_scipy_while_it_is_collected():
    modules = sorted(
        path
        for path in (ROOT / "tests").rglob("test_*.py")
        if "numerical" not in path.parts
    )
    assert len(modules) > 150, "the host test modules were not found"
    offenders = {
        str(path.relative_to(ROOT)): lines
        for path in modules
        if (lines := collection_time_swaps(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}, (
        "use the real_scipy fixture (tests/conftest.py) instead of changing sys.modules "
        f"at import time: {offenders}"
    )


def test_the_once_breaking_order_runs_green_in_a_fresh_interpreter(tmp_path):
    order = (
        "test_pre_pipeline.py",
        "test_plotting.py",
        "test_stats_main.py",
        "test_stats_engine.py",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *(f"tests/{name}" for name in order),
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            "-o",
            f"log_file={tmp_path / 'pytest.log'}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert " passed" in summary and "failed" not in summary and "error" not in summary
