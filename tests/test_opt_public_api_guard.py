"""Every name tit.opt.flex advertises as public API has a caller outside the tests.

Each ``tit/opt/flex`` module lists its public names in a ``Public API`` docstring section, and
the package exports ``__all__``. Several of those names (``validate_grid``,
``generate_summary_text``, ``parse_optimization_output``, ...) outlived every caller and were
kept alive only by their own unit tests. This guard reads the source off disk: a listed name
must be used (a name or attribute load, or an import) by production code under ``tit/`` or
``dev/`` other than its own definition, or be documented for users in ``docs/wiki`` or the
published API pages (``docs/api_mkdocs/docs``).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLEX = ROOT / "tit" / "opt" / "flex"
PRODUCTION = [ROOT / "tit", ROOT / "dev"]
USER_DOCS = [ROOT / "docs" / "wiki", ROOT / "docs" / "api_mkdocs" / "docs"]


def public_api_names(path: Path) -> list[str]:
    """Names listed under the module docstring's ``Public API`` heading."""
    doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    lines = doc.splitlines() + [""]
    if "Public API" not in lines:
        return []
    start = lines.index("Public API") + 2  # skip the heading and its underline
    names: list[str] = []
    for line, following in zip(lines[start:], lines[start + 1 :]):
        if not line or line[0].isspace():
            continue  # a description line or a blank
        if following and set(following) == {"-"}:
            break  # the next section's heading ("See Also", ...)
        names.append(line.strip())
    return names


def _uses(tree: ast.AST) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            used.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            used.update(alias.name for alias in node.names)
    return used


def _production_uses() -> dict[Path, set[str]]:
    out: dict[Path, set[str]] = {}
    for base in PRODUCTION:
        for path in base.rglob("*.py"):
            try:
                out[path] = _uses(ast.parse(path.read_text(encoding="utf-8")))
            except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
                continue
    return out


_DOC_TEXT: list[str] = []


def _documented(name: str) -> bool:
    if not _DOC_TEXT:
        _DOC_TEXT.extend(
            md.read_text(encoding="utf-8", errors="replace")
            for base in USER_DOCS
            for md in base.rglob("*.md")
        )
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    return any(pattern.search(text) for text in _DOC_TEXT)


def _advertised() -> list[tuple[str, str]]:
    pairs = [
        (path.relative_to(ROOT).as_posix(), name)
        for path in sorted(FLEX.glob("*.py"))
        for name in public_api_names(path)
    ]
    init = ast.parse((FLEX / "__init__.py").read_text(encoding="utf-8"))
    for node in init.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            pairs += [
                ("tit/opt/flex/__init__.py", n) for n in ast.literal_eval(node.value)
            ]
    return pairs


ADVERTISED = _advertised()
USES = _production_uses()


def test_the_guard_reads_the_docstrings_it_claims_to() -> None:
    """A parser that finds nothing would pass every case below vacuously."""
    by_module = {}
    for module, name in ADVERTISED:
        by_module.setdefault(module, []).append(name)
    assert by_module["tit/opt/flex/manifest.py"] == [
        "write_manifest",
        "read_manifest",
        "MANIFEST_FILENAME",
        "MANIFEST_VERSION",
    ]
    assert "save_results" in by_module["tit/opt/flex/pareto.py"]
    assert "run_flex_search" in by_module["tit/opt/flex/__init__.py"]


def test_a_dead_name_would_be_caught() -> None:
    """The deleted helpers are exactly what this guard exists to refuse."""
    for gone in ("validate_grid", "generate_summary_text", "parse_optimization_output"):
        assert not any(gone in used for used in USES.values()), gone
        assert not _documented(gone), gone


@pytest.mark.parametrize("module,name", ADVERTISED, ids=lambda v: str(v))
def test_advertised_flex_name_has_a_production_caller(module: str, name: str) -> None:
    called = any(name in used for path, used in USES.items())
    assert called or _documented(name), (
        f"{module} advertises {name!r} as public API, but nothing outside the tests uses it "
        "and no user page documents it: delete it (and its tests) or wire it in"
    )
